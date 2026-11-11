"""
APIGUARD -- S2a Feature builder (shared core, also imported by T3 in the offline lane).

Input : one normalised endpoint (EndpointRecord or its dict form) from S0, plus the
        scanner findings S1 attributed to that endpoint (may be empty).
Output: a fixed-length, fixed-order vector of finite floats -- never None, never NaN.

Contract (Deliverable 2, Table "Component Interfaces and Their Contracts"):
  * Same length and ordering for every endpoint (see FEATURE_NAMES).
  * No null values.
  * Pure function: no randomness, no I/O, no global state.

Six groups, A-F (Table "Feature Groups Computed by S2a"):
  A structural, B security scheme, C data sensitivity, D documentation hygiene,
  E scanner-derived (all zero when nothing fired), F context.
Provider/repository identity is deliberately NOT a feature: it is only used to
group the train/test splits, so the model cannot learn "who wrote the spec".

Author: APIGUARD team (Thornkasidej Fuangfoo, Varit Mesri) -- SIIT, Thammasat University.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

FEATURE_SCHEMA_VERSION = "s2a-1.0"   # bump whenever FEATURE_NAMES or any definition changes
LEXICON_VERSION = "lex-1.0"

# ----------------------------------------------------------------------------
# Group C lexicon.  Weight 3 = credential / government-id / payment secret,
# 2 = token, session or sensitive personal attribute, 1 = ordinary personal data.
# Compiled by the authors from the OWASP API3:2023 examples and common
# personal-data categories, and FROZEN before any labelling.  It is English-only.
# L2 labelling passes must not be shown it (otherwise the false-positive claim is circular).
# Keys are lower-case tokens joined with "_" (multi-word terms are matched on the
# camelCase / snake_case split of the property name).
# ----------------------------------------------------------------------------
SENSITIVE_LEXICON: Dict[str, int] = {
    # 3
    "password": 3, "passwd": 3, "pwd": 3, "secret": 3, "api_key": 3, "apikey": 3,
    "private_key": 3, "ssn": 3, "social_security": 3, "card_number": 3,
    "credit_card": 3, "cvv": 3, "iban": 3, "passport": 3,
    # 2
    "token": 2, "access_token": 2, "refresh_token": 2, "session": 2, "otp": 2,
    "dob": 2, "birthdate": 2, "birth_date": 2, "date_of_birth": 2, "salary": 2,
    "balance": 2, "account_number": 2, "national_id": 2, "tax": 2, "admin": 2,
    "is_admin": 2, "auth": 2,
    # 1
    "email": 1, "phone": 1, "mobile": 1, "address": 1, "postcode": 1, "zip": 1,
    "birthday": 1, "gender": 1, "username": 1, "role": 1,
}

ID_PARAM_RE = re.compile(r"^(id|uuid|guid|pk)$|(_id|-id|Id|ID)$|uuid|guid")
VERSION_SEGMENT_RE = re.compile(r"^v\d+(\.\d+)?$", re.IGNORECASE)
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")

PAGINATION_NAMES = {"limit", "offset", "page", "per_page", "perpage", "page_size",
                    "pagesize", "size", "cursor", "after", "before", "page_token",
                    "pagetoken", "skip", "top"}
RATE_LIMIT_HEADER_PREFIXES = ("x-ratelimit", "ratelimit", "x-rate-limit", "retry-after")

SEVERITY_LEVEL = {"error": 3, "warn": 2, "warning": 2, "info": 1, "hint": 1,
                  0: 3, 1: 2, 2: 1, 3: 1}      # Spectral's numeric severities: 0 error .. 3 hint
OWASP_CATEGORIES = tuple("API%d" % i for i in range(1, 11))

# ----------------------------------------------------------------------------
# Feature schema -- the ORDER here is the contract.
# ----------------------------------------------------------------------------
_GROUP_A = [
    "path_depth", "n_path_params", "id_like_path_param",
    "m_get", "m_post", "m_put", "m_patch", "m_delete", "m_other",
    "n_query_params", "n_header_params", "has_request_body", "req_prop_count",
    "resp_prop_count", "n_status_codes", "declares_401", "declares_403", "deprecated",
]
_GROUP_B = [
    "has_security", "src_own", "src_inherited", "src_override_none", "src_own_none",
    "src_none", "scheme_apikey", "scheme_http_basic", "scheme_http_bearer",
    "scheme_oauth2", "scheme_oidc", "scope_count", "apikey_in_query", "server_http_insecure",
]
_GROUP_C = [
    "sens_resp_count", "sens_resp_max_weight", "sens_resp_ratio",
    "sens_req_count", "sens_req_max_weight", "noauth_x_sens", "noauth_x_sens_weight",
]
_GROUP_D = [
    "summary_len", "description_len", "has_example", "mean_param_desc_len",
    "frac_params_with_desc", "frac_params_with_example", "mean_resp_desc_len",
    "path_has_version", "has_pagination", "has_ratelimit_header", "n_tags",
]
_GROUP_E = (["flagged_by_spectral", "rule_count", "severity_max", "n_owasp_categories"]
            + ["owasp_%s" % c.lower() for c in OWASP_CATEGORIES])
_GROUP_F = ["spec_endpoint_count", "is_oas3"]

GROUPS: Dict[str, List[str]] = {
    "A": _GROUP_A, "B": _GROUP_B, "C": _GROUP_C,
    "D": _GROUP_D, "E": _GROUP_E, "F": _GROUP_F,
}
FEATURE_NAMES: List[str] = [n for g in "ABCDEF" for n in GROUPS[g]]
GROUP_OF: Dict[str, str] = {n: g for g in "ABCDEF" for n in GROUPS[g]}
N_FEATURES = len(FEATURE_NAMES)
assert len(set(FEATURE_NAMES)) == N_FEATURES, "duplicate feature name"

Finding = Mapping[str, Any]   # {"rule": str, "severity": "error"|"warn"|..., "owasp": "API1:2023"}


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def _as_dict(ep: Any) -> Dict[str, Any]:
    return ep if isinstance(ep, dict) else ep.to_dict()


def _tokens(name: str) -> List[str]:
    parts: List[str] = []
    for chunk in _SPLIT_RE.split(name or ""):
        parts.extend(p.lower() for p in _CAMEL_RE.split(chunk) if p)
    return parts


def term_weight(name: str) -> int:
    """Weight of the heaviest lexicon term found in one property name (0 = none)."""
    toks = _tokens(name)
    best = 0
    for n in (1, 2, 3):                       # unigrams, bigrams, trigrams
        for i in range(len(toks) - n + 1):
            best = max(best, SENSITIVE_LEXICON.get("_".join(toks[i:i + n]), 0))
    # glued forms such as "apikey" / "accesstoken" are caught by the unigram pass
    # only if listed; also try the whole name joined, e.g. "dateOfBirth" -> date_of_birth
    best = max(best, SENSITIVE_LEXICON.get("_".join(toks), 0))
    return best


def _sens_stats(names: Iterable[str]) -> Tuple[int, int, int]:
    count = total = maxw = 0
    for nm in names:
        total += 1
        w = term_weight(nm)
        if w > 0:
            count += 1
            maxw = max(maxw, w)
    return count, maxw, total


def _is_success_or_default(code: str) -> bool:
    return code.startswith("2") or code.lower() == "default"


def _finding_category(f: Finding) -> Optional[str]:
    m = re.search(r"API\s*(\d{1,2})", str(f.get("owasp", "")), re.IGNORECASE)
    if m and 1 <= int(m.group(1)) <= 10:
        return "API%d" % int(m.group(1))
    return None


def _finding_level(f: Finding) -> int:
    sev = f.get("severity", "hint")
    if isinstance(sev, str):
        sev = sev.lower()
    return SEVERITY_LEVEL.get(sev, 1)


def _mean(xs: Sequence[float]) -> float:
    return float(sum(xs)) / len(xs) if xs else 0.0


# ----------------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------------

def build_feature_dict(
    endpoint: Any,
    findings: Optional[Sequence[Finding]] = None,
    spec_endpoint_count: Optional[int] = None,
) -> Dict[str, float]:
    """Return {feature_name: value} in FEATURE_NAMES order."""
    ep = _as_dict(endpoint)
    findings = list(findings or [])
    f: Dict[str, float] = {}

    path = ep.get("path") or ""
    method = (ep.get("method") or "").lower()
    params = ep.get("parameters") or []
    body = ep.get("request_body")
    responses = ep.get("responses") or []
    sec = ep.get("security") or []
    sec_src = ep.get("security_source") or "none"
    servers = ep.get("servers") or []
    path_params = ep.get("path_parameters") or []

    # ---- A structural ----
    f["path_depth"] = float(len([s for s in path.split("/") if s]))
    f["n_path_params"] = float(len(path_params))
    f["id_like_path_param"] = float(any(ID_PARAM_RE.search(p) for p in path_params))
    for m in ("get", "post", "put", "patch", "delete"):
        f["m_" + m] = float(method == m)
    f["m_other"] = float(method not in ("get", "post", "put", "patch", "delete"))
    f["n_query_params"] = float(sum(1 for p in params if p.get("location") == "query"))
    f["n_header_params"] = float(sum(1 for p in params if p.get("location") == "header"))
    f["has_request_body"] = float(body is not None)
    f["req_prop_count"] = float(len(body.get("properties", []))) if body else 0.0
    ok_counts = [len(r.get("properties", [])) for r in responses
                 if str(r.get("status_code", "")).startswith("2")]
    f["resp_prop_count"] = float(max(ok_counts)) if ok_counts else 0.0
    codes = {str(r.get("status_code", "")) for r in responses}
    f["n_status_codes"] = float(len(codes))
    f["declares_401"] = float("401" in codes)
    f["declares_403"] = float("403" in codes)
    f["deprecated"] = float(bool(ep.get("deprecated")))

    # ---- B security scheme ----
    f["has_security"] = float(len(sec) > 0)
    for s in ("own", "inherited", "override_none", "own_none", "none"):
        f["src_" + s] = float(sec_src == s)
    types = [(r.get("scheme_type") or "", (r.get("scheme_subtype") or "").lower()) for r in sec]
    f["scheme_apikey"] = float(any(t == "apiKey" for t, _ in types))
    f["scheme_http_basic"] = float(any(t == "http" and st == "basic" for t, st in types))
    f["scheme_http_bearer"] = float(any(t == "http" and st == "bearer" for t, st in types))
    f["scheme_oauth2"] = float(any(t == "oauth2" for t, _ in types))
    f["scheme_oidc"] = float(any(t == "openIdConnect" for t, _ in types))
    f["scope_count"] = float(sum(len(r.get("scopes") or []) for r in sec))
    f["apikey_in_query"] = float(any(r.get("scheme_type") == "apiKey" and r.get("location") == "query"
                                     for r in sec))
    f["server_http_insecure"] = float(any(
        u.lower().startswith("http://") and not re.match(r"http://(localhost|127\.|0\.0\.0\.0)", u.lower())
        for u in servers))

    # ---- C data sensitivity ----
    resp_names: List[str] = []
    for r in responses:
        if _is_success_or_default(str(r.get("status_code", ""))):
            resp_names.extend(p.get("name", "") for p in r.get("properties", []))
    req_names = [p.get("name", "") for p in (body.get("properties", []) if body else [])]
    req_names += [p.get("name", "") for p in params]
    rc, rw, rt = _sens_stats(resp_names)
    qc, qw, _ = _sens_stats(req_names)
    f["sens_resp_count"] = float(rc)
    f["sens_resp_max_weight"] = float(rw)
    f["sens_resp_ratio"] = rc / rt if rt else 0.0
    f["sens_req_count"] = float(qc)
    f["sens_req_max_weight"] = float(qw)
    noauth = 0.0 if f["has_security"] else 1.0
    f["noauth_x_sens"] = float(noauth and rc > 0)
    f["noauth_x_sens_weight"] = noauth * rw

    # ---- D documentation hygiene ----
    f["summary_len"] = float(ep.get("summary_len") or 0)
    f["description_len"] = float(ep.get("description_len") or 0)
    f["has_example"] = float(bool(ep.get("has_example")))
    pdl = [float(p.get("description_len") or 0) for p in params]
    f["mean_param_desc_len"] = _mean(pdl)
    f["frac_params_with_desc"] = _mean([1.0 if x > 0 else 0.0 for x in pdl])
    f["frac_params_with_example"] = _mean([1.0 if p.get("has_example") else 0.0 for p in params])
    f["mean_resp_desc_len"] = _mean([float(r.get("description_len") or 0) for r in responses])
    f["path_has_version"] = float(any(VERSION_SEGMENT_RE.match(s) for s in path.split("/") if s))
    f["has_pagination"] = float(any((p.get("name") or "").lower() in PAGINATION_NAMES for p in params))
    f["has_ratelimit_header"] = float(any(
        h.lower().startswith(RATE_LIMIT_HEADER_PREFIXES)
        for r in responses for h in (r.get("header_names") or [])))
    f["n_tags"] = float(len(ep.get("tags") or []))

    # ---- E scanner-derived (all zero when nothing fired) ----
    cats = {c for c in (_finding_category(x) for x in findings) if c}
    f["flagged_by_spectral"] = float(len(findings) > 0)
    f["rule_count"] = float(len(findings))
    f["severity_max"] = float(max((_finding_level(x) for x in findings), default=0))
    f["n_owasp_categories"] = float(len(cats))
    for c in OWASP_CATEGORIES:
        f["owasp_%s" % c.lower()] = float(c in cats)

    # ---- F context ----
    f["spec_endpoint_count"] = float(spec_endpoint_count if spec_endpoint_count is not None else 1)
    f["is_oas3"] = float(str(ep.get("source_version", "")).startswith("openapi-3"))

    # contract: complete, ordered, finite
    out = {n: float(f[n]) for n in FEATURE_NAMES}
    for n, v in out.items():
        if not math.isfinite(v):
            raise ValueError("non-finite feature %s=%r" % (n, v))
    return out


def build_features(endpoint: Any, findings: Optional[Sequence[Finding]] = None,
                   spec_endpoint_count: Optional[int] = None) -> List[float]:
    """Return the feature vector x(e) as a list of floats, in FEATURE_NAMES order."""
    d = build_feature_dict(endpoint, findings, spec_endpoint_count)
    return [d[n] for n in FEATURE_NAMES]


def build_matrix(endpoints: Sequence[Any],
                 findings_by_endpoint: Optional[Mapping[str, Sequence[Finding]]] = None,
                 spec_endpoint_count: Optional[int] = None) -> List[List[float]]:
    """Feature table for a list of endpoints. findings_by_endpoint is keyed by endpoint_id."""
    findings_by_endpoint = findings_by_endpoint or {}
    rows = []
    for ep in endpoints:
        e = _as_dict(ep)
        rows.append(build_features(e, findings_by_endpoint.get(e.get("endpoint_id", ""), ()),
                                   spec_endpoint_count))
    return rows


def columns_without_groups(groups: Iterable[str]) -> List[int]:
    """Column indices that remain after removing whole groups (used by the E5 ablation)."""
    drop = set(groups)
    return [i for i, n in enumerate(FEATURE_NAMES) if GROUP_OF[n] not in drop]
