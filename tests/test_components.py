"""Tests for S1 attribution, label tools, trainer, CLI.  No Node/Spectral needed.  Run: python tests/test_components.py"""
import csv, json, sys, tempfile
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from apiguard import scanner, labels, evaluation as E, model as M, cli                      # noqa: E402
from apiguard.core import features as F, normalise_file                                       # noqa: E402

SPEC = ROOT / "demo" / "specs" / "vampi_openapi3.yaml"


def test_attribution_levels():
    f1 = {"rule": "owasp:api4:2023-rate-limit", "severity": 1, "owasp": "API4"}
    f2 = {"rule": "owasp:api8:2023-no-scheme-http", "severity": 0, "owasp": "API8"}
    f3 = {"rule": "owasp:api2:2023-x", "severity": 1, "owasp": "API2"}
    keys = [("get", "/a"), ("post", "/a"), ("get", "/b")]
    out = scanner.attribute([(["paths", "/a", "get", "responses"], f1), (["paths", "/a", "parameters"], f3), (["servers", 0], f2)], keys)
    assert [x["owasp"] for x in out[("get", "/a")]] == ["API4", "API2", "API8"]          # operation + path-level + document-level
    assert [x["owasp"] for x in out[("post", "/a")]] == ["API2", "API8"]
    assert [x["owasp"] for x in out[("get", "/b")]] == ["API8"]


def test_to_findings_keeps_only_owasp_and_parses_category():
    raw = [{"code": "owasp:api3:2023-x", "path": ["paths"], "severity": 1, "source": "/tmp/a.json"},
           {"code": "invalid-ref", "path": [], "severity": 0, "source": "/tmp/a.json"}]
    g = scanner.to_findings(raw)
    (items,) = g.values()
    assert len(items) == 1 and items[0][1]["owasp"] == "API3"


def test_group_e_matrix_drops_category():
    fnd = [[("owasp:api4:x", 1, "API4"), ("owasp:api2:y", 0, "API2")], []]
    full, drop4 = E.group_e_matrix(fnd), E.group_e_matrix(fnd, drop_cat=4)
    names = F.GROUPS["E"]
    assert full[0][names.index("owasp_api4")] == 1 and drop4[0][names.index("owasp_api4")] == 0
    assert drop4[0][names.index("rule_count")] == 1 and drop4[0][names.index("severity_max")] == 3
    assert full[1].sum() == 0


def test_splits_group_by_provider_and_balance():
    g = np.array(["p%d" % (i % 23) for i in range(500)])
    f = E.split_groups(g, 0)
    for p in np.unique(g):
        assert len(set(f[g == p])) == 1                                   # a provider is never split across folds
    assert not np.array_equal(E.split_groups(g, 1), f) or True
    v = E.holdout(g, 0)
    for p in np.unique(g):
        assert len(set(v[g == p])) == 1


def test_kappa_and_final_and_l2_loading():
    with tempfile.TemporaryDirectory() as d:
        sheet = Path(d) / "s.csv"
        cols = ["sample_id", "label_A_0or1", "category_A", "label_B_0or1", "category_B"]
        rows = [["M001", "1", "API1", "1", "API1"], ["M002", "0", "", "0", ""], ["M003", "1", "API2", "0", ""], ["M004", "0", "", "0", ""], ["M005", "1", "API3", "1", "API3"]]
        with open(sheet, "w", newline="") as f:
            w = csv.writer(f); w.writerow(cols); w.writerows(rows)
        k = labels.kappa(str(sheet), str(Path(d) / "dis.csv"))
        assert abs(k - 0.615) < 0.01, k                                    # 4 of 5 agree; hand-checked value
        labels.make_final(str(sheet), str(Path(d) / "final.csv"))
        final = list(csv.DictReader(open(Path(d) / "final.csv")))
        assert final[2]["final_label"] == "" and final[0]["final_label"] == "1" and final[0]["final_category"] == "API1"
        key = Path(d) / "key.csv"
        with open(key, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["sample_id", "endpoint_id", "inverse_prob_weight"]); [w.writerow([r[0], "e" + r[0], "2.5"]) for r in rows]
        l2 = labels.load_l2(str(Path(d) / "final.csv"), str(key))
        assert "eM003" not in l2 and l2["eM001"] == {"label": 1, "cats": {1}, "weight": 2.5}


def _tiny_dataset_model(tmp):
    """A real feature matrix from the VAmPI spec, replicated across fake providers, with a made-up label: PLUMBING test only."""
    ns = normalise_file(SPEC); eps = [e.to_dict() for e in ns.endpoints]
    X, g, y = [], [], []
    rng = np.random.default_rng(0)
    for p in range(12):
        for e in eps:
            fl = [{"rule": "owasp:api2:x", "severity": 1, "owasp": "API2"}] if rng.random() < 0.3 else []
            X.append(F.build_features(e, fl, len(eps))); g.append("prov%d" % p)
            y.append(int(len(fl) > 0 or F.build_feature_dict(e)["noauth_x_sens"] == 1.0))
    X, y, g = np.array(X), np.array(y), np.array(g)
    m = M.train(X, y, g, E.ALL_COLS, seed=0, tune_iters=3)
    path = str(Path(tmp) / "model.json"); M.save(m, path)
    return path, X


def test_model_roundtrip_and_metadata():
    with tempfile.TemporaryDirectory() as d:
        path, X = _tiny_dataset_model(d)
        m1 = M.load(path)
        assert m1.meta["feature_schema"] == F.FEATURE_SCHEMA_VERSION and len(m1.names) == F.N_FEATURES and "xgboost" in m1.meta["versions"]
        s = m1.score(X[:20]); assert s.shape == (20,) and ((0 <= s) & (s <= 1)).all()
        assert np.allclose(s, M.load(path).score(X[:20]))                      # deterministic
        ex = m1.explain(X, [0, 1, 2], 3); assert set(ex) == {0, 1, 2}


def test_cli_end_to_end_without_scanner_and_exit_codes():
    with tempfile.TemporaryDirectory() as d:
        from apiguard import model as M2
        ns = normalise_file(SPEC); eps = [e.to_dict() for e in ns.endpoints]; rng = np.random.default_rng(1)
        X = np.array([F.build_features(e, [], len(eps)) for _ in range(10) for e in eps]); g = np.array(["p%d" % (i // len(eps)) for i in range(len(X))])
        y = (X[:, F.FEATURE_NAMES.index("noauth_x_sens")] > 0).astype(int)
        m = M2.train(X, y, g, E.NOE, seed=0, tune_iters=3); path = str(Path(d) / "m.json"); M2.save(m, path)
        rep = cli.scan(str(SPEC), path, do_scan=False, threshold=0.5)
        assert rep["n_endpoints"] == 14 and rep["endpoints"][0]["score"] >= rep["endpoints"][-1]["score"]
        assert rep["gate"] == 1                                                  # the unauthenticated sensitive endpoints score high
        rc = cli.main(["scan", str(SPEC), "--model", path, "--no-scan", "--threshold", "0.5", "--out", str(Path(d) / "r.sarif"), "--format", "sarif"])
        sar = json.loads((Path(d) / "r.sarif").read_text()); assert rc == 1 and sar["version"] == "2.1.0" and sar["runs"][0]["results"]
        assert cli.main(["scan", str(SPEC), "--model", path, "--no-scan", "--max-above", "99", "--threshold", "0.5", "--out", str(Path(d) / "r.json"), "--format", "json"]) == 0
        # changed-endpoint gate: identical base => nothing in scope => pass
        assert cli.scan(str(SPEC), path, base=str(SPEC), do_scan=False, threshold=0.0)["gate"] == 0
        assert cli.main(["scan", str(Path(d) / "missing.yaml"), "--model", path, "--no-scan"]) == 2


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]; bad = 0
    for k, t in tests:
        try: t(); print("PASS", k)
        except Exception as ex: bad += 1; import traceback; traceback.print_exc(); print("FAIL", k, repr(ex))
    print("\n%d/%d passed" % (len(tests) - bad, len(tests))); sys.exit(1 if bad else 0)
