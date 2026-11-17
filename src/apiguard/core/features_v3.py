"""
APIGUARD -- S2a feature builder, schema s2a-3.0 (model v3).

Changes from s2a-1.0 (features.py, model v1):
  1. Group E is built from the Spectral findings on THIS operation only (op-level).
     v1 also added every document-level finding (components, securitySchemes, servers ...)
     to every endpoint, so almost all endpoints of one spec had the same rules.
     Document-level findings now go into a separate, small group S.
  2. Group F (spec_endpoint_count, is_oas3) is removed: the E5 ablation showed it hurt
     (it mostly tells the model which provider wrote the spec).
  3. New group H: design patterns behind the OWASP API Top 10 flaws that the scanner rules
     do not express per endpoint (BOLA, admin/debug functions, mass assignment, SSRF,
     auth endpoints without rate limits, unauthenticated writes, secret data in responses).

Same contract as features.py: fixed order, finite floats, pure function.
Author: APIGUARD team (Thornkasidej Fuangfoo, Varit Mesri) -- SIIT, Thammasat University.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import features as F

FEATURE_SCHEMA_VERSION = "s2a-3.0"

_GROUP_S = ["doc_rule_count", "doc_owasp_api2", "doc_owasp_api4", "doc_owasp_api8", "doc_owasp_api9"]
_GROUP_H = [
    "h_bola_id_path",          # object id in the path + GET/PUT/PATCH/DELETE      (API1)
    "h_bola_user_object",      # ... and the object is a user/account/order-like resource
    "h_bola_noauth",           # ... and no security requirement
    "h_admin_path",            # admin / manage / role / permission words in the path (API5)
    "h_debug_path",            # debug / test / internal / createdb / backup words  (API5, API9)
    "h_write_noauth",          # POST/PUT/PATCH/DELETE with no security             (API2, API5)
    "h_mass_assign_count",     # writable privilege / money / ownership fields in the request body (API3)
    "h_mass_assign",
    "h_ssrf_param",            # parameter or body field that takes a URL            (API7)
    "h_auth_endpoint",         # login / token / otp / password / register ...       (API2)
    "h_auth_no_ratelimit",     # ... with no 429 response and no rate-limit header   (API4)
    "h_resp_secret",           # success response returns a weight-3 term (password, secret, card ...)  (API3)
    "h_list_no_pagination",    # GET collection (no path param) with no pagination parameter (API4)
    "h_numeric_id",            # integer path parameter (guessable ids)              (API1)
]
GROUPS: Dict[str, List[str]] = {g: list(F.GROUPS[g]) for g in "ABCDE"}
GROUPS["S"] = _GROUP_S
GROUPS["H"] = _GROUP_H
ORDER = "ABCDESH"
FEATURE_NAMES: List[str] = [n for g in ORDER for n in GROUPS[g]]
GROUP_OF: Dict[str, str] = {n: g for g in ORDER for n in GROUPS[g]}

_ADMIN = {"admin", "admins", "administrator", "manage", "management", "manager", "role", "roles", "permission",
          "permissions", "privilege", "privileges", "sudo", "superuser", "staff", "moderator", "acl", "grant", "grants"}
_DEBUG = {"debug", "test", "tests", "testing", "dev", "internal", "createdb", "backup", "dump", "console", "actuator",
          "phpinfo", "env", "trace", "diagnostics", "seed", "reset_db", "resetdb", "init", "setup", "maintenance"}
_USER_OBJ = {"user", "users", "account", "accounts", "profile", "profiles", "customer", "customers", "order", "orders",
             "member", "members", "employee", "employees", "invoice", "invoices", "payment", "payments", "wallet",
             "card", "cards", "vehicle", "vehicles", "message", "messages", "document", "documents", "file", "files",
             "book", "books", "post", "posts", "comment", "comments", "transaction", "transactions", "me"}
_AUTH = {"login", "logon", "signin", "sign_in", "token", "tokens", "oauth", "otp", "password", "passwd", "reset",
         "register", "signup", "sign_up", "verify", "verification", "forgot", "forget", "authenticate", "auth",
         "session", "sessions", "2fa", "mfa", "pin"}
_MASS = {"role", "roles", "is_admin", "isadmin", "admin", "permissions", "permission", "privilege", "balance", "credit",
         "credits", "verified", "is_verified", "isverified", "owner", "owner_id", "ownerid", "user_id", "userid",
         "account_id", "accountid", "price", "discount", "amount", "approved", "is_active", "isactive", "status",
         "group", "groups", "scope", "scopes", "tier", "plan", "level"}
_URLISH = {"url", "uri", "callback", "callback_url", "webhook", "webhook_url", "redirect", "redirect_uri", "redirect_url",
           "return_url", "link", "endpoint", "host", "hostname", "image_url", "avatar_url", "feed", "proxy", "target", "src",
           "source_url", "remote", "fetch"}


def _segments(path: str) -> List[str]:
    toks: List[str] = []
    for seg in path.split("/"):
        if not seg or seg.startswith("{"):
            continue
        toks.extend(F._tokens(seg))
        toks.append(seg.lower().strip("_"))
    return toks


def _name_hit(name: str, vocab) -> bool:
    toks = F._tokens(name)
    return name.lower() in vocab or "_".join(toks) in vocab or any(t in vocab for t in toks)


def build_feature_dict(endpoint: Any, op_findings: Optional[Sequence[Mapping[str, Any]]] = None,
                       doc_findings: Optional[Sequence[Mapping[str, Any]]] = None) -> Dict[str, float]:
    ep = F._as_dict(endpoint)
    base = F.build_feature_dict(ep, list(op_findings or []), 1)     # A-E (E from op-level findings only)
    f: Dict[str, float] = {n: base[n] for g in "ABCDE" for n in GROUPS[g]}

    # ---- S: document-level scanner findings (same for every endpoint of a spec) ----
    doc = list(doc_findings or [])
    cats = {F._finding_category(x) for x in doc}
    f["doc_rule_count"] = float(len({x.get("rule") for x in doc}))
    for c in ("api2", "api4", "api8", "api9"):
        f["doc_owasp_" + c] = float(c.upper() in cats)

    # ---- H: flaw patterns ----
    path = ep.get("path") or ""
    method = (ep.get("method") or "").lower()
    params = ep.get("parameters") or []
    body = ep.get("request_body")
    responses = ep.get("responses") or []
    noauth = not (ep.get("security") or [])
    segs = set(_segments(path))
    pparams = [p for p in params if p.get("location") == "path"]
    id_like = bool(base["id_like_path_param"]) or any(F.ID_PARAM_RE.search(p.get("name") or "") for p in pparams) \
        or (len(pparams) > 0 and any((p.get("name") or "").lower() in {"username", "user", "email", "name", "title", "slug"}
                                     for p in pparams))
    obj_method = method in ("get", "put", "patch", "delete")
    f["h_bola_id_path"] = float(id_like and obj_method)
    f["h_bola_user_object"] = float(id_like and obj_method and bool(segs & _USER_OBJ))
    f["h_bola_noauth"] = float(id_like and obj_method and noauth)
    f["h_admin_path"] = float(bool(segs & _ADMIN))
    f["h_debug_path"] = float(bool(segs & _DEBUG) or any(s.startswith("_") for s in path.split("/") if s))
    f["h_write_noauth"] = float(method in ("post", "put", "patch", "delete") and noauth)
    body_props = (body.get("properties") or []) if body else []
    mass = [p for p in body_props if not p.get("read_only") and _name_hit(p.get("name") or "", _MASS)]
    f["h_mass_assign_count"] = float(len(mass))
    f["h_mass_assign"] = float(len(mass) > 0)
    url_fields = [p for p in params + body_props
                  if (p.get("format") or "").lower() in ("uri", "url", "uri-reference", "iri")
                  or _name_hit(p.get("name") or "", _URLISH)]
    f["h_ssrf_param"] = float(len(url_fields) > 0)
    is_auth = bool(segs & _AUTH)
    f["h_auth_endpoint"] = float(is_auth)
    codes = {str(r.get("status_code", "")) for r in responses}
    f["h_auth_no_ratelimit"] = float(is_auth and "429" not in codes and not base["has_ratelimit_header"])
    resp_names = [p.get("name", "") for r in responses if F._is_success_or_default(str(r.get("status_code", "")))
                  for p in r.get("properties", [])]
    f["h_resp_secret"] = float(any(F.term_weight(n) >= 3 for n in resp_names))
    f["h_list_no_pagination"] = float(method == "get" and not pparams and not base["has_pagination"]
                                      and any("[]" in (p.get("path") or "") for r in responses for p in r.get("properties", [])))
    f["h_numeric_id"] = float(any((p.get("type") or "") in ("integer", "number") for p in pparams))

    out = {n: float(f[n]) for n in FEATURE_NAMES}
    return out


def build_features(endpoint: Any, op_findings=None, doc_findings=None) -> List[float]:
    d = build_feature_dict(endpoint, op_findings, doc_findings)
    return [d[n] for n in FEATURE_NAMES]


def columns(groups: str) -> List[int]:
    keep = set(groups)
    return [i for i, n in enumerate(FEATURE_NAMES) if GROUP_OF[n] in keep]
