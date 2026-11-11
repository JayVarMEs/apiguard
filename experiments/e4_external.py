"""E4 -- external validity on VAmPI and crAPI (L3 ground truth).  The final model (models/model.json) never saw these applications.
Inputs : a spec file per application and a filled L3 csv (see data/L3_template.csv: spec_file,method,path,label,category,design_visible).
Output : for each application, ROC-AUC / PR-AUC of the risk score against the documented flaws, the rank of every documented-flaw endpoint
         among all endpoints, the same for the design-visible subset only, and the scanner's own flags next to the model's score.
Optional --dynamic-findings: csv (tool,method,path) of endpoints where OWASP ZAP or Schemathesis found something when run against the live
         application (run them yourself; commands in README_RUN.md).  The script reports how many of them are in the model's top-k."""
import csv
from collections import defaultdict
import numpy as np
from sklearn.metrics import average_precision_score as AP, roc_auc_score
from _common import *
ap = parser(__doc__); ap.add_argument("--model", default="models/model.json"); ap.add_argument("--l3", default="data/L3_vampi.csv")
ap.add_argument("--dynamic-findings"); ap.add_argument("--spec-root", default=".", help="folder the spec_file column is relative to")
a = ap.parse_args(); Path(a.out).mkdir(parents=True, exist_ok=True)
from apiguard import cli, model as M
rows = L.load_l3(a.l3)
if not rows: sys.exit("%s has no filled label rows (label column)." % a.l3)
dyn = defaultdict(set)
if a.dynamic_findings:
    for r in csv.DictReader(open(a.dynamic_findings, encoding="utf-8-sig")): dyn[(r["method"].lower(), r["path"])].add(r["tool"])
res = {"apps": {}}
for spec in sorted({r["spec_file"] for r in rows}):
    rep = cli.scan(str(Path(a.spec_root) / spec), a.model, None, None, 0, True, 3)
    truth = {(r["method"], r["path"]): r for r in rows if r["spec_file"] == spec}
    ep = rep["endpoints"]                                  # already ranked by score
    y = np.array([truth.get((e["method"], e["path"]), {}).get("label", 0) for e in ep]); sc = np.array([e["score"] for e in ep])
    dv = np.array([truth.get((e["method"], e["path"]), {}).get("design_visible", 0) for e in ep])
    unmatched = [k for k in truth if k not in {(e["method"], e["path"]) for e in ep}]
    r = {"n_endpoints": len(ep), "n_flaw_endpoints": int(y.sum()), "n_design_visible": int(dv.sum()), "unmatched_L3_rows": [list(k) for k in unmatched],
         "tau": rep["threshold"], "rank_of_flaw_endpoints": [int(i + 1) for i in np.where(y == 1)[0]],
         "rank_of_design_visible": [int(i + 1) for i in np.where(dv == 1)[0]]}
    if 0 < y.sum() < len(y):
        r.update(roc_auc_all=float(roc_auc_score(y, sc)), pr_auc_all=float(AP(y, sc)), prevalence=float(y.mean()))
    if 0 < dv.sum() < len(y):
        r.update(roc_auc_design_visible=float(roc_auc_score(dv, sc)), pr_auc_design_visible=float(AP(dv, sc)))
    r["table"] = [dict(rank=i + 1, method=e["method"].upper(), path=e["path"], score=e["score"], above_tau=e["above_tau"], scanner=e["scanner_rules"],
                       because=[n for n, _ in e["reasons"]], documented_flaw=int(y[i]), category=";".join("API%d" % c for c in sorted(truth.get((e["method"], e["path"]), {}).get("cats", []))))
                  for i, e in enumerate(ep)]
    if dyn:
        top = {(e["method"], e["path"]) for e in ep[:max(5, int(y.sum()))]}
        r["dynamic"] = {"endpoints_with_dynamic_findings": len(dyn), "in_model_top_k": len(top & set(dyn)), "k": len(top)}
    res["apps"][spec] = r; print(spec, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k != "table"})
mdl = M.load(a.model)
res["label_source"] = "L3"; res["model_uses_scanner_features"] = any(n.startswith(("flagged_", "rule_count", "owasp_")) for n in mdl.names)
(Path(a.out) / "e4.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8"); print("wrote", Path(a.out) / "e4.json")
