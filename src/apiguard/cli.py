"""
APIGUARD -- S3 risk gate and command-line tool.  Implements Algorithm 2 (runtime scan with changed-endpoint gate).

    python -m apiguard scan api/openapi.yaml --model models/model.json --threshold 0.70 --max-above 0
    python -m apiguard scan new.yaml --base old.yaml --model models/model.json --format sarif --out apiguard.sarif

Exit code:  0 = gate passes,  1 = gate fails,  2 = tool error (bad input, missing model, Spectral not installed).
Add --no-scan to skip Spectral (only valid for a model trained with --no-group-e).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import __version__
from . import model as M
from . import scanner
from .core import features as F
from .core import gate as G
from .core import normalise_file


def scan(spec: str, model_path: str, base: Optional[str] = None, threshold: Optional[float] = None, max_above: int = 0,
         do_scan: bool = True, top_shap: int = 10, timings: Optional[dict] = None) -> Dict:
    t = {}
    c = time.perf_counter()
    mdl = M.load(model_path)
    tau = float(threshold) if threshold is not None else mdl.tau
    ns = normalise_file(spec); eps = [e.to_dict() for e in ns.endpoints]
    head_records = ns.endpoints
    base_eps = [e for e in normalise_file(base).endpoints] if base else None
    t["s0"] = time.perf_counter() - c; c = time.perf_counter()
    needs_scan = any(n.startswith(("flagged_", "rule_count", "severity_max", "n_owasp", "owasp_")) for n in mdl.names)
    if needs_scan and not do_scan:
        raise SystemExit("This model uses scanner features (group E); --no-scan is only valid for a model trained with --no-group-e.")
    keys = [(e["method"], e["path"]) for e in eps]
    attributed = scanner.scan_file(Path(spec), keys) if (do_scan and needs_scan) else {k: [] for k in keys}
    t["s1"] = time.perf_counter() - c; c = time.perf_counter()
    X = np.array([F.build_features(e, attributed.get((e["method"], e["path"]), []), len(eps)) for e in eps]) if eps else np.zeros((0, F.N_FEATURES))
    t["s2a"] = time.perf_counter() - c; c = time.perf_counter()
    r = mdl.score(X) if len(eps) else np.zeros(0)
    t["s2b"] = time.perf_counter() - c; c = time.perf_counter()
    order = np.argsort(-r)
    why = mdl.explain(X, [int(i) for i in order[:top_shap]]) if len(eps) else {}
    t["s2c"] = time.perf_counter() - c; c = time.perf_counter()
    scores = {keys[i]: float(r[i]) for i in range(len(eps))}
    scope = G.changed_endpoints(base_eps, head_records) if base else None
    decision = G.gate_decision(scores, tau, max_above, scope)
    rows = G.ranked_report(scores, tau, scope)
    for row in rows:
        i = keys.index((row["method"], row["path"]))
        row["reasons"] = why.get(i, [])
        row["reason_values"] = {n: float(X[i][F.FEATURE_NAMES.index(n)]) for n, _ in row["reasons"]}
        row["scanner_rules"] = sorted({f["rule"] for f in attributed.get((row["method"], row["path"]), [])})[:5]
    t["s3"] = time.perf_counter() - c
    if timings is not None:
        timings.update(t)
    return {"tool": "apiguard", "version": __version__, "spec": str(spec), "base": str(base) if base else None,
            "threshold": tau, "max_above": max_above, "gate": decision, "n_endpoints": len(eps),
            "n_in_scope": len(scope) if scope is not None else len(eps),
            "n_above_in_scope": sum(1 for x in rows if x["above_tau"] and x["in_scope"]),
            "model": {"path": model_path, "schema": mdl.meta["feature_schema"], "seed": mdl.meta["seed"]}, "endpoints": rows}


def to_text(rep: Dict, limit: int = 25) -> str:
    out = ["APIGUARD %s  %s%s" % (rep["version"], rep["spec"], ("  (vs base %s)" % rep["base"]) if rep["base"] else ""),
           "endpoints: %d | in gate scope: %d | at or above tau=%.2f in scope: %d | allowed (k): %d"
           % (rep["n_endpoints"], rep["n_in_scope"], rep["threshold"], rep["n_above_in_scope"], rep["max_above"]), ""]
    out.append("%-6s %-7s %-6s %-5s %s" % ("score", "method", "above", "scope", "path"))
    for r in rep["endpoints"][:limit]:
        out.append("%-6.3f %-7s %-6s %-5s %s" % (r["score"], r["method"].upper(), "YES" if r["above_tau"] else "", "yes" if r["in_scope"] else "no", r["path"]))
        if r["reasons"]:
            out.append("         because: " + ", ".join("%s=%g (+%.2f)" % (n, r["reason_values"].get(n, 0.0), v) for n, v in r["reasons"]))
        if r["scanner_rules"]:
            out.append("         scanner: " + ", ".join(r["scanner_rules"]))
    if len(rep["endpoints"]) > limit:
        out.append("... %d more endpoints in the JSON report" % (len(rep["endpoints"]) - limit))
    out.append("")
    out.append("GATE: " + ("FAIL (exit 1)" if rep["gate"] else "PASS (exit 0)"))
    return "\n".join(out)


def to_sarif(rep: Dict) -> Dict:
    results = []
    for r in rep["endpoints"]:
        if not (r["above_tau"] and r["in_scope"]):
            continue
        msg = "%s %s has risk score %.2f (threshold %.2f)." % (r["method"].upper(), r["path"], r["score"], rep["threshold"])
        if r["reasons"]:
            msg += " Main reasons: " + ", ".join(n for n, _ in r["reasons"]) + "."
        results.append({"ruleId": "apiguard/endpoint-risk", "level": "error", "message": {"text": msg},
                        "locations": [{"physicalLocation": {"artifactLocation": {"uri": rep["spec"].replace("\\", "/")},
                                                            "region": {"startLine": 1}}}],
                        "properties": {"score": r["score"], "method": r["method"], "path": r["path"]}})
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{"tool": {"driver": {"name": "APIGUARD", "version": rep["version"],
                                          "rules": [{"id": "apiguard/endpoint-risk", "shortDescription": {"text": "Endpoint design risk above threshold"}}]}},
                      "results": results}]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="apiguard", description="Continuous API security assessment gate.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="score every endpoint of an OpenAPI/Swagger file and decide the gate")
    s.add_argument("spec"); s.add_argument("--base", help="spec on the base branch: only new/changed endpoints count for the gate")
    s.add_argument("--model", default="models/model.json"); s.add_argument("--threshold", type=float, help="tau (default: the model's own)")
    s.add_argument("--max-above", type=int, default=0, help="k: tolerated number of endpoints at or above tau (default 0)")
    s.add_argument("--format", choices=["text", "json", "sarif"], default="text"); s.add_argument("--out", help="write the report here")
    s.add_argument("--no-scan", action="store_true"); s.add_argument("--top-shap", type=int, default=10)
    a = ap.parse_args(argv)
    try:
        rep = scan(a.spec, a.model, a.base, a.threshold, a.max_above, not a.no_scan, a.top_shap)
    except (FileNotFoundError, scanner.ScannerUnavailable) as ex:
        print("apiguard: error: %s" % ex, file=sys.stderr); return 2
    except Exception as ex:                                     # noqa: BLE001 - normaliser errors have plain-English messages
        print("apiguard: error: %s" % ex, file=sys.stderr); return 2
    text = {"text": lambda: to_text(rep), "json": lambda: json.dumps(rep, indent=1), "sarif": lambda: json.dumps(to_sarif(rep), indent=1)}[a.format]()
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8"); print("wrote %s (%s)" % (a.out, a.format)); print("GATE: " + ("FAIL" if rep["gate"] else "PASS"))
    else:
        print(text)
    return 1 if rep["gate"] else 0


if __name__ == "__main__":
    sys.exit(main())
