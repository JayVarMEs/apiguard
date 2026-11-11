"""E8 -- hybrid ranking: scanner + model.  Pre-specified, one setting only: score = mean of the percentile rank of the scanner score (severity, then rule count)
and the percentile rank of the out-of-fold model score.  No weight was tried or tuned.  Uses the out-of-fold scores of E6 (policy A) and E7 (policy B) cached in
results/e7_cache (copy or move the folder back if it was archived).   Output: results/e8.json"""
import pickle
import numpy as np
from scipy.stats import rankdata
from sklearn.metrics import average_precision_score as AP, roc_auc_score as AUC
from _common import *
ap = parser(__doc__); ap.add_argument("--cache", default="results/e7_cache"); a, ds, es, cols, _ = setup(ap)
ev = es.mask; y = es.y; w = es.w; idx = np.where(ev)[0]; yy, ww = y[idx], w[idx]; sc = scanner_score(ds)[idx]
pct = lambda v: (rankdata(v) - 1) / (len(v) - 1)
rng = np.random.default_rng(0)
def eff(score):
    o = np.argsort(-score, kind="stable"); pos = np.where(yy[o] == 1)[0]
    return {**{"p@%d" % k: float(yy[o[:k]].mean()) for k in (5, 10, 20)}, "read_all_tp": int(pos[-1] + 1)}
def eff_scanner():
    acc = {"p@5": [], "p@10": [], "p@20": [], "read_all_tp": []}
    for _ in range(200):
        o = np.lexsort((rng.random(len(idx)), -sc))
        for k in (5, 10, 20): acc["p@%d" % k].append(float(yy[o[:k]].mean()))
        pos = np.where(yy[o] == 1)[0]; acc["read_all_tp"].append(int(pos[-1] + 1))
    return {k: float(np.mean(v)) for k, v in acc.items()}
res = {"n_test": int(len(idx)), "n_pos": int(yy.sum()), "scanner": {"pr_auc": float(AP(yy, sc, sample_weight=ww)), "roc_auc": float(AUC(yy, sc, sample_weight=ww)), **eff_scanner()}}
for name in ("A", "B"):
    oofs = [pickle.load(open("%s/%s_%d.pkl" % (a.cache, name, s), "rb"))[0]["xgb"][idx] for s in range(a.seeds)]
    rows = {"model": [], "hybrid": []}
    for o in oofs:
        for kind, sc_ in (("model", o), ("hybrid", 0.5 * pct(sc) + 0.5 * pct(o))):
            rows[kind].append({"pr_auc": float(AP(yy, sc_, sample_weight=ww)), "roc_auc": float(AUC(yy, sc_, sample_weight=ww)), **eff(sc_)})
    res[name] = {k: {m: float(np.mean([r[m] for r in v])) for m in v[0]} for k, v in rows.items()}
    pm = np.mean(oofs, axis=0); ph = 0.5 * pct(sc) + 0.5 * pct(pm)
    f = lambda fn, p, q: (lambda i: fn(yy[i], p[i], sample_weight=ww[i]) - fn(yy[i], q[i], sample_weight=ww[i]))
    res[name]["bootstrap_ci95"] = {"hybrid_minus_scanner_pr": E.ci95(E.boot_providers(ds.prov[idx], f(AP, ph, sc), 1000, seed=21)),
        "hybrid_minus_scanner_roc": E.ci95(E.boot_providers(ds.prov[idx], f(AUC, ph, sc), 1000, seed=22)),
        "hybrid_minus_model_pr": E.ci95(E.boot_providers(ds.prov[idx], f(AP, ph, pm), 1000, seed=23)),
        "hybrid_minus_model_roc": E.ci95(E.boot_providers(ds.prov[idx], f(AUC, ph, pm), 1000, seed=24))}
save(a, "e8.json", res, es)
r3 = lambda d: {k: round(v, 3) for k, v in d.items()}
print("scanner", r3(res["scanner"]))
for n in "AB": print(n, "model", r3(res[n]["model"]), "\n  hybrid", r3(res[n]["hybrid"]), "\n  CI", res[n]["bootstrap_ci95"])
