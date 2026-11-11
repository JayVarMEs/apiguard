"""
APIGUARD -- S0 Normaliser (shared core, also used by T3 in the offline lane).

Input : one OpenAPI 3.x or Swagger 2.0 specification file (YAML or JSON).
Output: a list of normalised endpoint records, one per (path, method) pair.

Contract (Deliverable 2, Table "Component Interfaces and Their Contracts"):
  * Every endpoint of a parsable specification appears exactly once.
  * A specification that cannot be parsed is never dropped silently -- it is
    returned as a ParseFailure and written to the error log with a reason.
  * Circular $ref chains are cut at a fixed depth, so expansion always
    terminates.
  * Swagger 2.0 and OpenAPI 3.x are flattened into ONE internal form, so no
    component after S0 needs to know which version the document came from.
  * Path-level parameters are merged into each operation.
  * A global `security` block is propagated to operations that do not declare
    their own, and the record keeps WHY it holds that requirement
    (own / inherited / override_none / none) -- an operation that explicitly
    overrides global security with `security: []` is a different risk from one
    that simply inherits it.

Author: APIGUARD team (Thornkasidej Fuangfoo, Varit Mesri) -- SIIT, Thammasat University.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover - yaml is a hard requirement in practice
    yaml = None


# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

MAX_REF_DEPTH = 8          # how deep a $ref chain / nested schema may expand
MAX_PROPERTIES = 512       # hard cap so one pathological spec cannot blow up memory

SCHEMA_VERSION = "s0-1.0"  # bump when the record layout changes

# canonical OpenAPI 3 spelling for every security scheme type we may meet
CANONICAL_SCHEME_TYPE = {
    "apikey": "apiKey",
    "http": "http",
    "basic": "http",            # Swagger 2 "basic" is OAS3 http + scheme: basic
    "oauth2": "oauth2",
    "openidconnect": "openIdConnect",
}


# ----------------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------------

class SpecParseError(Exception):
    """The file is not readable, not valid YAML/JSON, or not an API spec."""


# ----------------------------------------------------------------------------
# Record types  (the internal form -- everything after S0 speaks only this)
# ----------------------------------------------------------------------------

@dataclass
class SchemaProperty:
    """One leaf or object node of an expanded request/response schema."""
    path: str                       # dotted path, e.g. "user.address.postal_code"
    name: str                       # leaf name only, e.g. "postal_code"
    type: str = "unknown"           # string / integer / object / array / unknown
    format: Optional[str] = None    # date-time, uuid, password, ...
    required: bool = False
    nullable: bool = False
    depth: int = 0
    read_only: bool = False
    write_only: bool = False
    truncated: bool = False         # True if expansion stopped here (cycle / depth cap)


@dataclass
class ParameterRecord:
    name: str
    location: str                   # query / header / path / cookie / formData
    required: bool = False
    type: str = "unknown"
    format: Optional[str] = None
    deprecated: bool = False
    has_example: bool = False
    description_len: int = 0


@dataclass
class BodyRecord:
    required: bool = False
    content_types: List[str] = field(default_factory=list)
    properties: List[SchemaProperty] = field(default_factory=list)


@dataclass
class ResponseRecord:
    status_code: str                # "200", "4XX", "default"
    content_types: List[str] = field(default_factory=list)
    properties: List[SchemaProperty] = field(default_factory=list)
    description_len: int = 0
    header_names: List[str] = field(default_factory=list)


@dataclass
class SecurityRequirementRecord:
    scheme_name: str                # key in securitySchemes
    scheme_type: str = "unknown"    # apiKey / http / oauth2 / openIdConnect
    scheme_subtype: Optional[str] = None   # basic / bearer for http, "" otherwise
    location: Optional[str] = None  # apiKey in: header/query/cookie
    scopes: List[str] = field(default_factory=list)


@dataclass
class EndpointRecord:
    """One (path, method) operation, version-independent."""
    # identity
    endpoint_id: str
    spec_id: str
    spec_hash: str
    source_file: str
    source_version: str             # "openapi-3.x" or "swagger-2.0"
    schema_version: str = SCHEMA_VERSION

    # location
    path: str = ""
    method: str = ""                # lower case
    operation_id: Optional[str] = None
    path_parameters: List[str] = field(default_factory=list)   # names in {braces}

    # interface
    parameters: List[ParameterRecord] = field(default_factory=list)
    request_body: Optional[BodyRecord] = None
    responses: List[ResponseRecord] = field(default_factory=list)

    # security design
    security: List[SecurityRequirementRecord] = field(default_factory=list)
    security_source: str = "none"   # own | inherited | override_none | none
    servers: List[str] = field(default_factory=list)

    # documentation
    summary_len: int = 0
    description_len: int = 0
    tags: List[str] = field(default_factory=list)
    deprecated: bool = False
    has_example: bool = False

    # bookkeeping
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass
class ParseFailure:
    """A spec that could not be normalised. Logged, never silently skipped."""
    source_file: str
    reason: str
    detail: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


@dataclass
class NormalisedSpec:
    spec_id: str
    spec_hash: str
    source_file: str
    source_version: str
    endpoints: List[EndpointRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def endpoint_count(self) -> int:
        return len(self.endpoints)


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------

def load_spec_text(text: str, source_file: str = "<string>") -> Dict[str, Any]:
    """Parse YAML or JSON text into a dict. YAML loader also accepts JSON."""
    if yaml is None:
        raise SpecParseError("PyYAML is not installed (pip install pyyaml)")
    try:
        doc = yaml.safe_load(text)
    except Exception as exc:                       # noqa: BLE001 - report any parser error
        raise SpecParseError(f"yaml/json parse error: {exc}") from exc
    if not isinstance(doc, dict):
        raise SpecParseError("top level of the document is not a mapping")
    return doc


def detect_version(doc: Dict[str, Any]) -> str:
    """Return 'openapi-3.x', 'swagger-2.0', or raise SpecParseError."""
    if isinstance(doc.get("openapi"), str) and doc["openapi"].startswith("3"):
        return "openapi-3.x"
    if str(doc.get("swagger", "")).startswith("2"):
        return "swagger-2.0"
    raise SpecParseError("no recognised 'openapi: 3.x' or 'swagger: 2.0' field")


def spec_hash_of(text: str) -> str:
    """Content hash used by T1 to de-duplicate the corpus before splitting."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ----------------------------------------------------------------------------
# The normaliser
# ----------------------------------------------------------------------------

class Normaliser:
    """Turns one parsed specification document into endpoint records."""

    def __init__(
        self,
        doc: Dict[str, Any],
        source_file: str = "<string>",
        spec_hash: str = "",
        max_depth: int = MAX_REF_DEPTH,
    ) -> None:
        self.doc = doc
        self.source_file = source_file
        self.spec_hash = spec_hash or spec_hash_of(json.dumps(doc, sort_keys=True, default=str))
        self.max_depth = max_depth
        self.version = detect_version(doc)
        self.warnings: List[str] = []

        self.spec_id = self._spec_id()
        self.security_schemes = self._collect_security_schemes()
        self.global_security = doc.get("security")
        self.servers = self._collect_servers()

    # -- identity ------------------------------------------------------------

    def _spec_id(self) -> str:
        info = self.doc.get("info") or {}
        title = str(info.get("title", "untitled")).strip()
        version = str(info.get("version", "0")).strip()
        return f"{title}@{version}"

    # -- version flattening --------------------------------------------------

    def _collect_security_schemes(self) -> Dict[str, Dict[str, Any]]:
        """securitySchemes (OAS3) and securityDefinitions (Swagger2) -> one map."""
        if self.version == "openapi-3.x":
            raw = ((self.doc.get("components") or {}).get("securitySchemes") or {})
        else:
            raw = self.doc.get("securityDefinitions") or {}

        out: Dict[str, Dict[str, Any]] = {}
        for name, scheme in raw.items():
            if not isinstance(scheme, dict):
                continue
            scheme = self._resolve(scheme)
            raw_type = str(scheme.get("type", "unknown")).lower()
            subtype = None
            if self.version == "swagger-2.0" and raw_type == "basic":
                subtype = "basic"            # Swagger 2 "basic" -> OAS3 http/basic
            elif raw_type == "http":
                subtype = str(scheme.get("scheme", "")).lower() or None
            stype = CANONICAL_SCHEME_TYPE.get(raw_type, raw_type)
            out[name] = {
                "type": stype,
                "subtype": subtype,
                "in": scheme.get("in"),
                "scopes": sorted((scheme.get("scopes") or {}).keys())
                if self.version == "swagger-2.0"
                else sorted(self._oas3_scopes(scheme)),
            }
        return out

    @staticmethod
    def _oas3_scopes(scheme: Dict[str, Any]) -> Iterable[str]:
        flows = scheme.get("flows") or {}
        scopes: List[str] = []
        for flow in flows.values():
            if isinstance(flow, dict):
                scopes.extend((flow.get("scopes") or {}).keys())
        return set(scopes)

    def _collect_servers(self) -> List[str]:
        if self.version == "openapi-3.x":
            servers = self.doc.get("servers") or []
            return [_clean_url(str(s.get("url", ""))) for s in servers if isinstance(s, dict)]
        # Swagger 2: schemes + host + basePath assemble into the same field
        host = str(self.doc.get("host", "")).strip()
        base = str(self.doc.get("basePath", "")).strip()
        schemes = self.doc.get("schemes") or (["https"] if host else [])
        if not host:
            return [_clean_url(base)] if base else []
        return [_clean_url(f"{s}://{host}{base}") for s in schemes]

    # -- $ref resolution -----------------------------------------------------

    def _resolve(self, node: Any, _seen: Optional[Tuple[str, ...]] = None) -> Any:
        """Follow internal $ref pointers. External refs are left unresolved."""
        seen = _seen or ()
        depth = 0
        while isinstance(node, dict) and "$ref" in node:
            ref = str(node["$ref"])
            if not ref.startswith("#/"):
                self.warnings.append(f"external $ref not resolved: {ref}")
                return {"__unresolved_ref__": ref}
            if ref in seen or depth >= self.max_depth:
                self.warnings.append(f"circular or too-deep $ref cut: {ref}")
                return {"__cycle_cut__": ref}
            seen = seen + (ref,)
            depth += 1
            target = self._deref_pointer(ref)
            if target is None:
                self.warnings.append(f"dangling $ref: {ref}")
                return {"__unresolved_ref__": ref}
            node = target
        return node

    def _deref_pointer(self, ref: str) -> Any:
        parts = [p.replace("~1", "/").replace("~0", "~") for p in ref[2:].split("/") if p != ""]
        node: Any = self.doc
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                return None
        return node

    # -- schema expansion ----------------------------------------------------

    def _expand_schema(
        self,
        schema: Any,
        prefix: str = "",
        depth: int = 0,
        seen_refs: Tuple[str, ...] = (),
        required: bool = False,
        out: Optional[List[SchemaProperty]] = None,
    ) -> List[SchemaProperty]:
        """Flatten a JSON Schema into a list of dotted-path properties."""
        if out is None:
            out = []
        if len(out) >= MAX_PROPERTIES:
            return out

        # remember the ref BEFORE resolving so cycles are detectable
        ref_key = schema.get("$ref") if isinstance(schema, dict) else None
        if ref_key and ref_key in seen_refs:
            if prefix:
                out.append(SchemaProperty(path=prefix, name=_leaf_name(prefix),
                                          type="object", depth=depth, required=required,
                                          truncated=True))
            return out
        # resolve with the CURRENT seen set, then mark this ref for the children
        schema = self._resolve(schema, seen_refs)
        if ref_key:
            seen_refs = seen_refs + (ref_key,)
        if not isinstance(schema, dict) or not schema:
            return out

        if depth >= self.max_depth:
            if prefix:
                out.append(SchemaProperty(path=prefix, name=_leaf_name(prefix),
                                          type=str(schema.get("type", "unknown")),
                                          depth=depth, required=required, truncated=True))
            return out

        # composition keywords: merge every branch
        for key in ("allOf", "anyOf", "oneOf"):
            for sub in schema.get(key) or []:
                self._expand_schema(sub, prefix, depth, seen_refs, required, out)

        stype = schema.get("type")
        if stype is None and "properties" in schema:
            stype = "object"

        if stype == "object" or "properties" in schema:
            req_names = set(schema.get("required") or [])
            props = schema.get("properties") or {}
            if prefix:
                out.append(SchemaProperty(path=prefix, name=_leaf_name(prefix),
                                          type="object", depth=depth, required=required))
            for name, sub in props.items():
                child = f"{prefix}.{name}" if prefix else str(name)
                self._expand_schema(sub, child, depth + 1, seen_refs,
                                    name in req_names, out)
            extra = schema.get("additionalProperties")
            if isinstance(extra, dict):
                child = f"{prefix}.*" if prefix else "*"
                self._expand_schema(extra, child, depth + 1, seen_refs, False, out)
            return out

        if stype == "array":
            child = f"{prefix}[]" if prefix else "[]"
            self._expand_schema(schema.get("items") or {}, child, depth + 1,
                                seen_refs, required, out)
            return out

        # primitive leaf
        if prefix:
            out.append(SchemaProperty(
                path=prefix,
                name=_leaf_name(prefix),
                type=str(stype or "unknown"),
                format=schema.get("format"),
                required=required,
                nullable=bool(schema.get("nullable", False)),
                depth=depth,
                read_only=bool(schema.get("readOnly", False)),
                write_only=bool(schema.get("writeOnly", False)),
            ))
        return out

    # -- parameters ----------------------------------------------------------

    def _parameter_record(self, raw: Any) -> Optional[ParameterRecord]:
        p = self._resolve(raw)
        if not isinstance(p, dict) or "name" not in p:
            return None
        location = str(p.get("in", "query"))
        if self.version == "swagger-2.0":
            ptype = str(p.get("type", "unknown"))
            pformat = p.get("format")
            has_example = "x-example" in p or "default" in p
        else:
            schema = self._resolve(p.get("schema") or {})
            ptype = str(schema.get("type", "unknown")) if isinstance(schema, dict) else "unknown"
            pformat = schema.get("format") if isinstance(schema, dict) else None
            has_example = "example" in p or "examples" in p
        return ParameterRecord(
            name=str(p["name"]),
            location=location,
            required=bool(p.get("required", location == "path")),
            type=ptype,
            format=pformat,
            deprecated=bool(p.get("deprecated", False)),
            has_example=bool(has_example),
            description_len=len(str(p.get("description", "") or "")),
        )

    @staticmethod
    def _merge_parameters(
        path_level: List[ParameterRecord],
        op_level: List[ParameterRecord],
    ) -> List[ParameterRecord]:
        """Operation parameters override path parameters with the same (name, in)."""
        merged: Dict[Tuple[str, str], ParameterRecord] = {
            (p.name, p.location): p for p in path_level
        }
        for p in op_level:
            merged[(p.name, p.location)] = p
        return sorted(merged.values(), key=lambda p: (p.location, p.name))

    # -- request body --------------------------------------------------------

    def _request_body(self, operation: Dict[str, Any],
                      raw_params: List[Any]) -> Optional[BodyRecord]:
        if self.version == "openapi-3.x":
            rb = self._resolve(operation.get("requestBody") or {})
            if not isinstance(rb, dict) or not rb.get("content"):
                return None
            content = rb["content"]
            props: List[SchemaProperty] = []
            for media in content.values():
                if isinstance(media, dict) and media.get("schema") is not None:
                    self._expand_schema(media["schema"], out=props)
            return BodyRecord(
                required=bool(rb.get("required", False)),
                content_types=sorted(str(k) for k in content.keys()),
                properties=props,
            )

        # Swagger 2.0: body / formData parameters become the request body
        consumes = [str(c) for c in (operation.get("consumes")
                                     or self.doc.get("consumes") or [])]
        body_props: List[SchemaProperty] = []
        required = False
        found = False
        for raw in raw_params:
            p = self._resolve(raw)
            if not isinstance(p, dict):
                continue
            if p.get("in") == "body":
                found = True
                required = required or bool(p.get("required", False))
                self._expand_schema(p.get("schema") or {}, out=body_props)
                if not consumes:
                    consumes = ["application/json"]
            elif p.get("in") == "formData":
                found = True
                required = required or bool(p.get("required", False))
                body_props.append(SchemaProperty(
                    path=str(p.get("name", "")),
                    name=str(p.get("name", "")),
                    type=str(p.get("type", "unknown")),
                    format=p.get("format"),
                    required=bool(p.get("required", False)),
                ))
                if not consumes:
                    consumes = ["application/x-www-form-urlencoded"]
        if not found:
            return None
        return BodyRecord(required=required,
                          content_types=sorted(set(consumes)),
                          properties=body_props)

    # -- responses -----------------------------------------------------------

    def _responses(self, operation: Dict[str, Any]) -> List[ResponseRecord]:
        raw_responses = operation.get("responses") or {}
        produces = [str(p) for p in (operation.get("produces")
                                     or self.doc.get("produces") or [])]
        out: List[ResponseRecord] = []
        for code, raw in raw_responses.items():
            resp = self._resolve(raw)
            if not isinstance(resp, dict):
                continue
            props: List[SchemaProperty] = []
            content_types: List[str] = []
            if self.version == "openapi-3.x":
                content = resp.get("content") or {}
                content_types = sorted(str(k) for k in content.keys())
                for media in content.values():
                    if isinstance(media, dict) and media.get("schema") is not None:
                        self._expand_schema(media["schema"], out=props)
            else:
                if resp.get("schema") is not None:
                    self._expand_schema(resp["schema"], out=props)
                    content_types = sorted(set(produces)) or ["application/json"]
            out.append(ResponseRecord(
                status_code=str(code),
                content_types=content_types,
                properties=props,
                description_len=len(str(resp.get("description", "") or "")),
                header_names=sorted(str(h) for h in (resp.get("headers") or {}).keys()),
            ))
        return sorted(out, key=lambda r: r.status_code)

    # -- security ------------------------------------------------------------

    def _security(self, operation: Dict[str, Any]) -> Tuple[List[SecurityRequirementRecord], str]:
        """Return (requirements, source) where source explains WHERE it came from."""
        if "security" in operation:
            raw = operation.get("security")
            source = "own"
            if isinstance(raw, list) and len(raw) == 0:
                # explicit opt-out: NOT the same risk as inheriting nothing
                return [], ("override_none" if self.global_security else "own_none")
        elif self.global_security is not None:
            raw = self.global_security
            source = "inherited"
        else:
            return [], "none"

        reqs: List[SecurityRequirementRecord] = []
        for entry in raw or []:
            if not isinstance(entry, dict):
                continue
            for scheme_name, scopes in entry.items():
                meta = self.security_schemes.get(str(scheme_name), {})
                reqs.append(SecurityRequirementRecord(
                    scheme_name=str(scheme_name),
                    scheme_type=str(meta.get("type", "unknown")),
                    scheme_subtype=meta.get("subtype"),
                    location=meta.get("in"),
                    scopes=[str(s) for s in (scopes or [])],
                ))
        if not reqs:
            return [], ("override_none" if source == "own" and self.global_security else "none")
        return sorted(reqs, key=lambda r: r.scheme_name), source

    # -- the main pass -------------------------------------------------------

    def normalise(self) -> NormalisedSpec:
        result = NormalisedSpec(
            spec_id=self.spec_id,
            spec_hash=self.spec_hash,
            source_file=self.source_file,
            source_version=self.version,
        )
        paths = self.doc.get("paths")
        if not isinstance(paths, dict):
            self.warnings.append("no 'paths' object -- zero endpoints emitted")
            result.warnings = list(self.warnings)
            return result

        seen: set = set()
        for path, path_item_raw in paths.items():
            path_item = self._resolve(path_item_raw)
            if not isinstance(path_item, dict):
                continue

            path_params = [self._parameter_record(p) for p in (path_item.get("parameters") or [])]
            path_params = [p for p in path_params if p is not None]
            path_servers = [str(s.get("url", "")) for s in (path_item.get("servers") or [])
                            if isinstance(s, dict)]

            for method in HTTP_METHODS:
                if method not in path_item:
                    continue
                operation = self._resolve(path_item[method])
                if not isinstance(operation, dict):
                    continue

                key = (str(path), method)
                if key in seen:                       # contract: exactly once
                    self.warnings.append(f"duplicate operation ignored: {method} {path}")
                    continue
                seen.add(key)

                raw_params = list(operation.get("parameters") or [])
                op_params = [self._parameter_record(p) for p in raw_params]
                op_params = [p for p in op_params if p is not None
                             and p.location not in ("body", "formData")]
                parameters = self._merge_parameters(path_params, op_params)

                security, security_source = self._security(operation)
                op_servers = [str(s.get("url", "")) for s in (operation.get("servers") or [])
                              if isinstance(s, dict)]

                record = EndpointRecord(
                    endpoint_id=self._endpoint_id(str(path), method),
                    spec_id=self.spec_id,
                    spec_hash=self.spec_hash,
                    source_file=self.source_file,
                    source_version=self.version,
                    path=str(path),
                    method=method,
                    operation_id=(str(operation["operationId"])
                                  if operation.get("operationId") else None),
                    path_parameters=_path_template_params(str(path)),
                    parameters=parameters,
                    request_body=self._request_body(operation, raw_params),
                    responses=self._responses(operation),
                    security=security,
                    security_source=security_source,
                    servers=op_servers or path_servers or self.servers,
                    summary_len=len(str(operation.get("summary", "") or "")),
                    description_len=len(str(operation.get("description", "") or "")),
                    tags=[str(t) for t in (operation.get("tags") or [])],
                    deprecated=bool(operation.get("deprecated", False)),
                    has_example=_operation_has_example(operation),
                )
                record.warnings = list(self.warnings)
                result.endpoints.append(record)

        result.warnings = list(self.warnings)
        return result

    def _endpoint_id(self, path: str, method: str) -> str:
        raw = f"{self.spec_hash}|{method}|{path}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def _clean_url(url: str) -> str:
    """Drop a trailing slash so the two spec versions produce the same server."""
    url = url.strip()
    return url[:-1] if len(url) > 1 and url.endswith("/") else url


def _leaf_name(dotted_path: str) -> str:
    """Last segment of a dotted schema path, without the array marker."""
    return dotted_path.split(".")[-1].replace("[]", "")


def _path_template_params(path: str) -> List[str]:
    out, buf, inside = [], [], False
    for ch in path:
        if ch == "{":
            inside, buf = True, []
        elif ch == "}" and inside:
            out.append("".join(buf))
            inside = False
        elif inside:
            buf.append(ch)
    return out


def _operation_has_example(operation: Dict[str, Any]) -> bool:
    blob = json.dumps(operation, default=str)
    return '"example"' in blob or '"examples"' in blob


# ----------------------------------------------------------------------------
# File / corpus level API  (what S1..S3 and T3 call)
# ----------------------------------------------------------------------------

def normalise_text(text: str, source_file: str = "<string>") -> NormalisedSpec:
    doc = load_spec_text(text, source_file)
    return Normaliser(doc, source_file=source_file, spec_hash=spec_hash_of(text)).normalise()


def normalise_file(path: str | Path) -> NormalisedSpec:
    """Raises SpecParseError -- callers decide whether to log or stop."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SpecParseError(f"cannot read file: {exc}") from exc
    return normalise_text(text, source_file=str(p))


def normalise_corpus(
    paths: Iterable[str | Path],
) -> Iterator[Tuple[Optional[NormalisedSpec], Optional[ParseFailure]]]:
    """
    Yield (spec, None) for each parsable spec and (None, failure) for each
    unparsable one. Nothing is dropped silently -- that is the S0 contract, and
    it is what lets T1 report an honest parse-failure rate for the corpus.
    """
    for path in paths:
        try:
            yield normalise_file(path), None
        except SpecParseError as exc:
            yield None, ParseFailure(source_file=str(path),
                                     reason=type(exc).__name__,
                                     detail=str(exc))
        except Exception as exc:              # noqa: BLE001 - never crash a corpus run
            yield None, ParseFailure(source_file=str(path),
                                     reason="UnexpectedError",
                                     detail=f"{type(exc).__name__}: {exc}")


# ----------------------------------------------------------------------------
# CLI:  python -m apiguard.core.normalizer spec.yaml -o endpoints.jsonl
# ----------------------------------------------------------------------------

def _expand_inputs(inputs: List[str]) -> List[Path]:
    out: List[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            for ext in ("*.yaml", "*.yml", "*.json"):
                out.extend(sorted(p.rglob(ext)))
        else:
            out.append(p)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="apiguard-s0",
        description="APIGUARD S0 -- normalise OpenAPI/Swagger specs into endpoint records.",
    )
    ap.add_argument("inputs", nargs="+", help="spec files or directories")
    ap.add_argument("-o", "--out", default="-", help="endpoint JSONL output (default stdout)")
    ap.add_argument("-e", "--errors", default=None, help="parse-failure JSONL log")
    ap.add_argument("--stats", action="store_true", help="print a summary to stderr")
    args = ap.parse_args(argv)

    files = _expand_inputs(args.inputs)
    out_fh = sys.stdout if args.out == "-" else open(args.out, "w", encoding="utf-8")
    err_fh = open(args.errors, "w", encoding="utf-8") if args.errors else None

    n_specs = n_endpoints = n_failed = 0
    try:
        for spec, failure in normalise_corpus(files):
            if failure is not None:
                n_failed += 1
                line = failure.to_json()
                (err_fh or sys.stderr).write(line + "\n")
                continue
            n_specs += 1
            for record in spec.endpoints:
                out_fh.write(record.to_json() + "\n")
                n_endpoints += 1
    finally:
        if out_fh is not sys.stdout:
            out_fh.close()
        if err_fh:
            err_fh.close()

    if args.stats:
        total = n_specs + n_failed
        rate = (n_failed / total * 100) if total else 0.0
        sys.stderr.write(
            f"[S0] specs parsed={n_specs} failed={n_failed} "
            f"({rate:.2f}% parse-failure) endpoints={n_endpoints}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
