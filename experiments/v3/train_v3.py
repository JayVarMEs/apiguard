"""v3 step 2: compare model v1 features with v3 features on the SAME labelled endpoints and the SAME splits.

Training labels : L2 (LLM majority vote) only -- no scanner (L1) labels.   Main 304 = test set (5-fold, grouped by provider,
                  5 seeds); the extra 304 L2 rows are always in training, except rows whose provider is in the test fold.
Metrics         : sample-weighted (inverse sampling probability) PR-AUC / ROC-AUC, plus unweighted precision@k -- as in E1/E6-E8.
External test   : models trained on all 608 L2 rows score VAmPI and crAPI (L3, never seen in training).
Output          : results/v3/v3_results.json, results/v3/model_v3.json, results/v3/v3_oof.csv
"""
import sys, json, csv
from pathlib import Path
import numpy as np
import xgboost as xgb
from scipy.stats import rankdata
from sklearn.metrics import average_precision_score as AP, roc_auc_score as AUC, precision_recall_curve
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
sys.path.insert(0, "src")
from apiguard.core import features as F1, features_v3 as F3
from apiguard import evaluation as E

OUT = Path("results/v3"); OUT.mkdir(parents=True, exist_ok=True)
rows = [json.loads(l) for l in open("data/v3_rows.jsonl", encoding="utf-8")]
L2 = [r for r in rows if r["kind"] == "L2"]; L3 = [r for r in rows if r["kind"] == "L3"]

def v1_findings(r):        # what v1 saw: op + doc findings merged, de-duplicated
    seen = {}
    for x in r["op_findings"] + r["doc_findings"]:
        seen[(x["rule"], x["severity"])] = {"rule": x["rule"], "severity": x["severity"], "owasp": x["rule"]}
    return list(seen.values())

def fix_owasp(fl):
    return [{"rule": x["rule"], "severity": x["severity"], "owasp": x["rule"]} for x in fl]

def mat_v1(rs):  return np.array([F1.build_features(r["ep"], v1_findings(r), r["n_spec"]) for r in rs])
def mat_v3(rs):  return np.array([F3.build_features(r["ep"], fix_owasp(r["op_findings"]), fix_owasp(r["doc_findings"])) for r in rs])

# v1 features exactly as the v1 dataset stored them (data/v3_v1rows.csv is copied out of data/dataset.npz):
# v1's rule_count counts every finding instance in the spec, document-level ones included.
_orig = {r["endpoint_id"]: [float(v) for k, v in r.items() if k != "endpoint_id"] for r in csv.DictReader(open("data/v3_v1rows.csv"))}
X1 = np.array([_orig[r["ep"]["endpoint_id"]] for r in L2])
def v1_l3(r):           # same rule as scanner.attribute(): op-level + path-level + every doc-level finding, all instances
    raw = json.load(open("data/spectral_%s.json" % Path(r["file"]).name)); fl = []
    for x in raw:
        if not str(x.get("code", "")).startswith("owasp:"): continue
        p = [str(q) for q in x.get("path", [])]
        if len(p) >= 2 and p[0] == "paths":
            if p[1] != r["ep"]["path"]: continue
            if len(p) >= 3 and p[2].lower() in ("get","put","post","delete","options","head","patch","trace") and p[2].lower() != r["ep"]["method"]: continue
        fl.append({"rule": x["code"], "severity": int(x.get("severity", 3)), "owasp": x["code"]})
    return F1.build_features(r["ep"], fl, r["n_spec"])
X1e = np.array([v1_l3(r) for r in L3]); X3, X3e = mat_v3(L2), mat_v3(L3)
y = np.array([r["label"] for r in L2]); w = np.array([r["weight"] for r in L2]); prov = np.array([r["provider"] for r in L2])
main = np.array([r["split"] == "main" for r in L2]); idx = np.where(main)[0]
yL3 = np.array([r["label"] for r in L3]); dvL3 = np.array([r["design_visible"] for r in L3]); app = np.array([r["app"] for r in L3])
print("L2 rows", len(L2), "pos", y.sum(), "| main", main.sum(), "pos", y[main].sum(), "| L3", len(L3))

# scanner baseline B1 (as in E1/E8): highest severity first, then number of rules -- on what v1's scanner output gave
i_sev, i_cnt = F1.FEATURE_NAMES.index("severity_max"), F1.FEATURE_NAMES.index("rule_count")
scan = X1[:, i_sev] * 1000 + X1[:, i_cnt]; scanL3 = X1e[:, i_sev] * 1000 + X1e[:, i_cnt]

c1 = lambda groups: [i for i, n in enumerate(F1.FEATURE_NAMES) if F1.GROUP_OF[n] in set(groups)]
VARIANTS = {   # name: (matrix, train matrix L3, columns)
    "v1 (A-F, findings merged)": (X1, X1e, c1("ABCDEF")),
    "v1 minus F": (X1, X1e, c1("ABCDE")),
    "v3a: per-endpoint scanner, no F (A-E)": (X3, X3e, F3.columns("ABCDE")),
    "v3b: + flaw patterns H": (X3, X3e, F3.columns("ABCDEH")),
    "v3c: + doc-level scanner S": (X3, X3e, F3.columns("ABCDESH")),
    "v3 H only + A,B (no scanner)": (X3, X3e, F3.columns("ABH")),
}
PARAMS = dict(max_depth=3, eta=0.05, subsample=0.8, colsample_bytree=0.8, min_child_weight=3, reg_lambda=2)
SEEDS = range(5)

def fit(Xtr, ytr, ptr, seed):
    v = E.holdout(ptr, seed);
    if ytr[~v].sum() == 0 or ytr[v].sum() == 0: v = np.zeros(len(ytr), bool); v[::5] = True
    return E.fit_xgb(Xtr[~v], ytr[~v], Xtr[v], ytr[v], PARAMS, seed, rounds=600)

def fit_lr(Xtr, ytr):
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.3, class_weight="balanced", max_iter=3000)).fit(Xtr, ytr)

def pct(v): return (rankdata(v) - 1) / (len(v) - 1)
def p_at(score, yy, k):
    o = np.argsort(-score, kind="stable"); return float(yy[o[:k]].mean())

def cv(X, cols, model="xgb"):
    oofs = []
    for s in SEEDS:
        fold = np.full(len(y), -1); fold[idx] = E.split_groups(prov[idx], s)
        oof = np.full(len(y), np.nan)
        for k in range(5):
            te = fold == k; te_prov = set(prov[te])
            tr = ~te & np.array([p not in te_prov for p in prov])
            if model == "xgb":
                b = fit(X[tr][:, cols], y[tr], prov[tr], s); oof[te] = E.predict(b, X[te][:, cols])
            else:
                m = fit_lr(X[tr][:, cols], y[tr]); oof[te] = m.predict_proba(X[te][:, cols])[:, 1]
        oofs.append(oof[idx])
    return np.array(oofs)          # seeds x 304

def summarise(oofs):
    yy, ww = y[idx], w[idx]; sc = scan[idx]
    m = {"pr_auc": [], "roc_auc": [], "p@10": [], "p@20": [], "hyb_pr_auc": [], "hyb_roc_auc": [], "hyb_p@10": []}
    for o in oofs:
        h = 0.5 * pct(sc) + 0.5 * pct(o)
        m["pr_auc"].append(AP(yy, o, sample_weight=ww)); m["roc_auc"].append(AUC(yy, o, sample_weight=ww))
        m["p@10"].append(p_at(o, yy, 10)); m["p@20"].append(p_at(o, yy, 20))
        m["hyb_pr_auc"].append(AP(yy, h, sample_weight=ww)); m["hyb_roc_auc"].append(AUC(yy, h, sample_weight=ww)); m["hyb_p@10"].append(p_at(h, yy, 10))
    return {k: [float(np.mean(v)), float(np.std(v))] for k, v in m.items()}

def external(Xall, Xext, cols):
    """train on all 608 L2 rows, score the L3 apps (5 seeds averaged)"""
    p = np.mean([E.predict(fit(Xall[:, cols], y, prov, s), Xext[:, cols]) for s in SEEDS], axis=0)
    out = {}
    for a in sorted(set(app)):
        m = app == a; yy = yL3[m]; pp = p[m]; dv = dvL3[m]; order = np.argsort(-pp, kind="stable")
        rank = np.empty(len(pp), int); rank[order] = np.arange(1, len(pp) + 1)
        dvm = (dv == 1) | (yy == 0)
        out[a] = {"n": int(m.sum()), "n_flaw": int(yy.sum()), "roc_auc": float(AUC(yy, pp)), "pr_auc": float(AP(yy, pp)), "prevalence": float(yy.mean()),
                  "roc_auc_design_visible": float(AUC(yy[dvm] * dv[dvm], pp[dvm])) if dv.sum() else None,
                  "flaws_in_top5": int(yy[order[:5]].sum()), "flaws_in_top10": int(yy[order[:10]].sum()),
                  "rank_design_visible": sorted(rank[dv == 1].tolist())}
    return out, p

res = {"n_l2": int(len(y)), "n_pos": int(y.sum()), "n_test_main": int(len(idx)), "n_pos_main": int(y[idx].sum()),
       "label_source": "L2 (LLM majority vote); L3 for external", "params": PARAMS, "variants": {}}
yy, ww = y[idx], w[idx]
res["scanner_B1"] = {"pr_auc": float(AP(yy, scan[idx], sample_weight=ww)), "roc_auc": float(AUC(yy, scan[idx], sample_weight=ww)),
                     "p@10": p_at(scan[idx], yy, 10), "p@20": p_at(scan[idx], yy, 20)}
res["random_pr_auc"] = float(np.average(yy, weights=ww))
ext_scan = {}
for a in sorted(set(app)):
    m = app == a; ext_scan[a] = {"roc_auc": float(AUC(yL3[m], scanL3[m])), "pr_auc": float(AP(yL3[m], scanL3[m]))}
res["scanner_B1_external"] = ext_scan
OOF = {}
for name, (X, Xe, cols) in VARIANTS.items():
    o = cv(X, cols); OOF[name] = o
    r = {"n_features": len(cols), "xgb": summarise(o), "lr": summarise(cv(X, cols, "lr"))}
    r["external"], _ = external(X, Xe, cols)
    res["variants"][name] = r
    print("%-40s xgb PR %.3f ROC %.3f p@10 %.2f | hybrid PR %.3f | LR PR %.3f | crAPI ROC %.2f VAmPI ROC %.2f" % (
        name, r["xgb"]["pr_auc"][0], r["xgb"]["roc_auc"][0], r["xgb"]["p@10"][0], r["xgb"]["hyb_pr_auc"][0], r["lr"]["pr_auc"][0],
        r["external"]["crapi"]["roc_auc"], r["external"]["vampi"]["roc_auc"]))
print("scanner B1", res["scanner_B1"], "random", res["random_pr_auc"], "ext", ext_scan)

# provider-bootstrap CIs: final v3 vs v1 and vs scanner (seed-averaged OOF)
FINAL = "v3b: + flaw patterns H"
pf, p1 = OOF[FINAL].mean(0), OOF["v1 (A-F, findings merged)"].mean(0); hf = 0.5 * pct(scan[idx]) + 0.5 * pct(pf)
diff = lambda fn, p, q: (lambda i: fn(yy[i], p[i], sample_weight=ww[i]) - fn(yy[i], q[i], sample_weight=ww[i]))
res["final"] = FINAL
res["bootstrap_ci95"] = {
    "v3_minus_v1_pr": E.ci95(E.boot_providers(prov[idx], diff(AP, pf, p1), 1000, seed=31)),
    "v3_minus_v1_roc": E.ci95(E.boot_providers(prov[idx], diff(AUC, pf, p1), 1000, seed=32)),
    "v3_minus_scanner_pr": E.ci95(E.boot_providers(prov[idx], diff(AP, pf, scan[idx]), 1000, seed=33)),
    "v3_minus_scanner_roc": E.ci95(E.boot_providers(prov[idx], diff(AUC, pf, scan[idx]), 1000, seed=34)),
    "v3hybrid_minus_scanner_pr": E.ci95(E.boot_providers(prov[idx], diff(AP, hf, scan[idx]), 1000, seed=35)),
}
print("CI", res["bootstrap_ci95"])

# tau for the gate, from out-of-fold scores (rule from E14b: highest tau with recall >= 0.60)
pr, rc, th = precision_recall_curve(yy, pf, sample_weight=ww)
ok = [i for i in range(len(th)) if rc[i] >= 0.60]; i = max(ok, key=lambda i: th[i])
f1 = 2 * pr[:-1] * rc[:-1] / np.maximum(pr[:-1] + rc[:-1], 1e-12); j = int(np.argmax(f1))
res["tau"] = {"rule": "highest tau with weighted OOF recall >= 0.60", "tau": float(th[i]), "recall": float(rc[i]), "precision": float(pr[i]),
              "flagged_of_304": int((pf >= th[i]).sum()), "max_f1_tau": float(th[j]), "max_f1": float(f1[j])}
print("tau", res["tau"])

# final model on all 608 rows + SHAP
cols = F3.columns("ABCDEH"); names = [F3.FEATURE_NAMES[c] for c in cols]
d_all = xgb.DMatrix(X3[:, cols], label=y, feature_names=names)
n_rounds = int(np.median([fit(X3[:, cols], y, prov, s).best_iteration + 1 for s in SEEDS]))
booster = xgb.train(E._xgb_params(y, PARAMS, 0), d_all, n_rounds)
booster.save_model(str(OUT / "model_v3.json"))
json.dump({"feature_schema": F3.FEATURE_SCHEMA_VERSION, "feature_names": names, "groups": "ABCDEH", "tau": res["tau"]["tau"],
           "rounds": n_rounds, "params": PARAMS, "trained_on": "608 L2 endpoints (LLM labels)"}, open(OUT / "model_v3.meta.json", "w"), indent=1)
contrib = booster.predict(d_all, pred_contribs=True)[:, :-1]
imp = np.abs(contrib).mean(0); order = np.argsort(-imp)
res["shap_global_top15"] = [[names[k], float(imp[k]), F3.GROUP_OF[names[k]]] for k in order[:15]]
grp = {}
for k, n in enumerate(names): grp[F3.GROUP_OF[n]] = grp.get(F3.GROUP_OF[n], 0) + float(imp[k])
res["shap_by_group"] = grp
print("SHAP top", res["shap_global_top15"][:10])

# per-endpoint external table for the final model
_, pext = external(X3, X3e, cols)
res["external_table"] = sorted([{"app": L3[k]["app"], "endpoint": "%s %s" % (L3[k]["ep"]["method"].upper(), L3[k]["ep"]["path"]),
                                 "score": round(float(pext[k]), 3), "flaw": int(yL3[k]), "category": L3[k]["cats"], "design_visible": int(dvL3[k])}
                                for k in range(len(L3))], key=lambda d: (d["app"], -d["score"]))
json.dump(res, open(OUT / "v3_results.json", "w"), indent=1)
with open(OUT / "v3_oof.csv", "w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["sample_id", "provider", "label", "weight", "scanner_score", "v1_oof", "v3_oof"])
    for t, k in enumerate(idx): wr.writerow([L2[k]["sid"], prov[k], y[k], w[k], scan[k], round(float(p1[t]), 4), round(float(pf[t]), 4)])
print("wrote", OUT)
