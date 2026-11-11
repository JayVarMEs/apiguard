"""
APIGUARD -- S3 gate decision and changed-endpoint selection.

Gate rule (Deliverable 2, Eq. 2):   G(S) = 1  iff  |{ e : r(e) >= tau }| > k.

Changed-endpoint gating (Deliverable 3): the gate counts only endpoints that are NEW or
CHANGED relative to the base branch, so a legacy API with old problems does not fail every
build forever.  The report still lists every endpoint.

An endpoint is matched across the two versions by its (method, path) key.  endpoint_id is
NOT used for this: it contains the spec hash, so it changes whenever any line of the file
changes.  "Changed" means the content fingerprint of the normalised record differs.

Author: APIGUARD team (Thornkasidej Fuangfoo, Varit Mesri) -- SIIT, Thammasat University.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

# fields that identify WHERE a record came from, not WHAT it says
_IDENTITY_FIELDS = ("endpoint_id", "spec_id", "spec_hash", "source_file", "warnings")

EndpointKey = Tuple[str, str]   # (method, path)


def _as_dict(ep: Any) -> Dict[str, Any]:
    return ep if isinstance(ep, dict) else ep.to_dict()


def endpoint_key(ep: Any) -> EndpointKey:
    d = _as_dict(ep)
    return ((d.get("method") or "").lower(), d.get("path") or "")


def endpoint_fingerprint(ep: Any) -> str:
    """Hash of everything about the endpoint except where the file lives."""
    d = {k: v for k, v in _as_dict(ep).items() if k not in _IDENTITY_FIELDS}
    return hashlib.sha1(json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def changed_endpoints(base: Optional[Iterable[Any]], head: Iterable[Any]) -> Set[EndpointKey]:
    """Keys of head endpoints that are new or whose content differs from base.

    base=None (no base branch, e.g. first commit) means every endpoint counts as new.
    A rename of a path is a new endpoint plus a removed one -- by design.
    """
    base_fp = {} if base is None else {endpoint_key(e): endpoint_fingerprint(e) for e in base}
    return {endpoint_key(e) for e in head
            if base_fp.get(endpoint_key(e)) != endpoint_fingerprint(e)}


def gate_decision(scores: Mapping[EndpointKey, float], tau: float, k: int = 0,
                  scope: Optional[Set[EndpointKey]] = None) -> int:
    """0 = pass, 1 = fail.  `scope` limits the count to those endpoints (None = all)."""
    n_above = sum(1 for key, r in scores.items()
                  if r >= tau and (scope is None or key in scope))
    return 1 if n_above > k else 0


def ranked_report(scores: Mapping[EndpointKey, float], tau: float,
                  scope: Optional[Set[EndpointKey]] = None) -> List[Dict[str, Any]]:
    """Every endpoint, highest risk first, with flags for 'above tau' and 'in gate scope'."""
    rows = [{"method": m, "path": p, "score": r, "above_tau": r >= tau,
             "in_scope": scope is None or (m, p) in scope}
            for (m, p), r in scores.items()]
    rows.sort(key=lambda x: (-x["score"], x["path"], x["method"]))
    return rows
