"""Contract tests for S2a (features.py) and S3 (gate.py). Run with plain python: python tests/test_features_gate.py"""
import copy
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from apiguard.core import normalise_file                       # noqa: E402
from apiguard.core import features as F                        # noqa: E402
from apiguard.core import gate as G                            # noqa: E402

SPEC = ROOT / "demo" / "specs" / "vampi_openapi3.yaml"


def _eps():
    return [e.to_dict() for e in normalise_file(SPEC).endpoints]


def test_schema_is_consistent():
    assert len(F.FEATURE_NAMES) == F.N_FEATURES == len(set(F.FEATURE_NAMES))
    assert sum(len(v) for v in F.GROUPS.values()) == F.N_FEATURES
    assert set(F.GROUP_OF.values()) == set("ABCDEF")


def test_same_length_and_finite_for_every_endpoint():
    for ep in _eps():
        x = F.build_features(ep, spec_endpoint_count=14)
        assert len(x) == F.N_FEATURES
        assert all(isinstance(v, float) and math.isfinite(v) for v in x)


def test_deterministic_and_record_equals_dict():
    recs = normalise_file(SPEC).endpoints
    assert F.build_features(recs[0]) == F.build_features(recs[0].to_dict()) == F.build_features(recs[0])


def test_group_e_is_zero_when_nothing_fired():
    for ep in _eps():
        d = F.build_feature_dict(ep)
        assert all(d[n] == 0.0 for n in F.GROUPS["E"])


def test_group_e_reads_findings():
    ep = _eps()[0]
    d = F.build_feature_dict(ep, [{"rule": "owasp:api2:2023-no-http-basic", "severity": "error", "owasp": "API2:2023"},
                                  {"rule": "x", "severity": "warn", "owasp": "API8:2023"}])
    assert d["flagged_by_spectral"] == 1.0 and d["rule_count"] == 2.0
    assert d["severity_max"] == 3.0 and d["n_owasp_categories"] == 2.0
    assert d["owasp_api2"] == 1.0 and d["owasp_api8"] == 1.0 and d["owasp_api1"] == 0.0


def test_unauthenticated_endpoint_returning_password_is_seen():
    """VAmPI GET /users/v1/_debug returns every user's password and admin flag, with no auth."""
    dbg = [e for e in _eps() if e["path"].endswith("/_debug")]
    assert dbg, "VAmPI debug endpoint missing from the spec"
    d = F.build_feature_dict(dbg[0])
    assert d["has_security"] == 0.0
    assert d["sens_resp_max_weight"] == 3.0
    assert d["noauth_x_sens"] == 1.0 and d["noauth_x_sens_weight"] == 3.0


def test_term_weight_splits_names():
    assert F.term_weight("dateOfBirth") == 2
    assert F.term_weight("user_password_hash") == 3
    assert F.term_weight("accessToken") == 2
    assert F.term_weight("is_admin") == 2
    assert F.term_weight("status") == 0 and F.term_weight("") == 0


def test_id_like_path_param_and_versions():
    ep = {"path": "/api/v2/users/{user_id}", "method": "get", "path_parameters": ["user_id"],
          "source_version": "openapi-3.x"}
    d = F.build_feature_dict(ep)
    assert d["id_like_path_param"] == 1.0 and d["path_has_version"] == 1.0
    assert d["path_depth"] == 4.0 and d["is_oas3"] == 1.0 and d["m_get"] == 1.0


def test_minimal_record_has_no_nulls():
    d = F.build_feature_dict({"path": "/x", "method": "get"})
    assert len(d) == F.N_FEATURES


def test_columns_without_groups():
    keep = F.columns_without_groups(["E"])
    assert len(keep) == F.N_FEATURES - len(F.GROUPS["E"])
    assert all(F.GROUP_OF[F.FEATURE_NAMES[i]] != "E" for i in keep)


# ---------------- gate ----------------

def test_gate_rule():
    s = {("get", "/a"): 0.9, ("get", "/b"): 0.2}
    assert G.gate_decision(s, 0.7, k=0) == 1
    assert G.gate_decision(s, 0.7, k=1) == 0          # k=1 tolerates one endpoint
    assert G.gate_decision(s, 0.95, k=0) == 0
    assert G.gate_decision(s, 0.7, k=0, scope={("get", "/b")}) == 0


def test_changed_endpoints_ignores_file_identity_but_sees_content():
    base = _eps()
    head = copy.deepcopy(base)
    for e in head:                                     # different file, different hash: not a change
        e["spec_hash"] = "other"; e["endpoint_id"] = "other-" + e["endpoint_id"]; e["source_file"] = "new.yaml"
    assert G.changed_endpoints(base, head) == set()

    head[0]["deprecated"] = not head[0].get("deprecated", False)   # real content change
    new = copy.deepcopy(head[1]); new["path"] = "/brand/new"          # a new endpoint
    changed = G.changed_endpoints(base, head + [new])
    assert changed == {G.endpoint_key(head[0]), G.endpoint_key(new)}


def test_no_base_means_everything_is_new():
    eps = _eps()
    assert len(G.changed_endpoints(None, eps)) == len({G.endpoint_key(e) for e in eps})


def test_legacy_problem_does_not_fail_gate_but_new_one_does():
    scores = {("get", "/old"): 0.95, ("get", "/new"): 0.10}
    assert G.gate_decision(scores, 0.7, 0, scope={("get", "/new")}) == 0
    scores[("get", "/new")] = 0.80
    assert G.gate_decision(scores, 0.7, 0, scope={("get", "/new")}) == 1


def test_report_is_ranked_and_complete():
    rows = G.ranked_report({("get", "/a"): 0.1, ("post", "/b"): 0.9}, 0.5, scope={("get", "/a")})
    assert [r["path"] for r in rows] == ["/b", "/a"]
    assert rows[0]["above_tau"] and not rows[0]["in_scope"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t(); print("PASS", t.__name__)
        except Exception as ex:                         # noqa: BLE001
            failed += 1; print("FAIL", t.__name__, "->", repr(ex))
    print("\n%d/%d passed; d = %d features" % (len(tests) - failed, len(tests), F.N_FEATURES))
    sys.exit(1 if failed else 0)
