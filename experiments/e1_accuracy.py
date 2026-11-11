"""E1 -- accuracy against the reference (LLM) labels.  Algorithm 1 (provider-grouped 5-fold CV, inner tuning, 5 seeds) for XGBoost, logistic
regression and random forest; baselines: majority, scanner (B1).  Scored on the L2 test endpoints (inverse-probability weighted).
Language-model baseline B4 is experiments/e1_llm_baseline.py.   Output: results/e1.json (+ out-of-fold scores in results/e1_oof.npz)."""
import numpy as np
from sklearn.metrics import precision_recall_curve
from _common import *

a, ds, es, cols, train_ok = setup(parser(__doc__))
res = {"n_endpoints": len(ds.meta), "n_eval": int(es.mask.sum()), "feature_set": "A-F" if len(cols) == len(E.NAMES) else "A,B,C,D,F (scanner-blind)",
       "train_policy": "oas3_only" if a.oas3_train_only else "all", "seeds": a.seeds}
ev = es.mask; y = es.y; w = es.w; oas3 = np.array([v.startswith("openapi-3") for v in ds.ver])
per_seed, tune, keep = {}, None, None
for s in range(a.seeds):
    print("seed", s, flush=True)
    fold, oof, taus, boosters, params = cv_run(ds, es, cols, train_ok, s, tune, a.tune_iters, models=("xgb", "lr", "rf") if s == 0 else ("xgb", "lr"))
    if s == 0:
        tune, keep = params, (fold, oof, taus, boosters)
    per_seed[s] = {m: E.wmetrics(y[ev], oof[m][ev], taus[m][ev], w[ev]) for m in oof}
res["per_seed"] = per_seed
agg = {m: {k: [float(np.mean([per_seed[s][m][k] for s in per_seed])), float(np.std([per_seed[s][m][k] for s in per_seed]))]
           for k in ("pr_auc", "roc_auc", "f1", "mcc")} for m in ("xgb", "lr")}
agg["rf"] = {k: [per_seed[0]["rf"][k], 0.0] for k in ("pr_auc", "roc_auc", "f1", "mcc")}
if not es.proxy:                                              # B1 scanner and B0 majority only make sense against reference labels
    sc = scanner_score(ds); flagged = ds.y1
    agg["scanner_B1"] = E.wmetrics(y[ev], sc[ev], 1.0, w[ev]); agg["scanner_B1"]["f1"] = E.wmetrics(y[ev], flagged[ev], 0.5, w[ev])["f1"]
    agg["scanner_B1"]["mcc"] = E.wmetrics(y[ev], flagged[ev], 0.5, w[ev])["mcc"]
res["majority_pr_auc"] = float(np.average(y[ev], weights=w[ev]))
res["aggregate"] = agg
fold, oof, taus, boosters = keep
res["by_version_seed0"] = {n: {m: E.wmetrics(y[ev & msk], oof[m][ev & msk], taus[m][ev & msk], w[ev & msk]) for m in ("xgb", "lr", "rf")}
                           for n, msk in (("openapi3", oas3), ("swagger2", ~oas3)) if (ev & msk).sum() > 10 and len(np.unique(y[ev & msk])) > 1}
# provider-level bootstrap (1000 resamples): XGB PR-AUC, and paired XGB - scanner / XGB - LR
idx = np.where(ev)[0]; px, pl = oof["xgb"][idx], oof["lr"][idx]; yy, ww = y[idx], w[idx]
from sklearn.metrics import average_precision_score as AP
bx = E.boot_providers(ds.prov[idx], lambda i: AP(yy[i], px[i], sample_weight=ww[i]), 1000)
bl = E.boot_providers(ds.prov[idx], lambda i: AP(yy[i], px[i], sample_weight=ww[i]) - AP(yy[i], pl[i], sample_weight=ww[i]), 1000, seed=1)
res["bootstrap"] = {"xgb_pr_auc_ci95": E.ci95(bx), "xgb_minus_lr_ci95": E.ci95(bl), "resamples": 1000}
if not es.proxy:
    ps = scanner_score(ds)[idx]
    bs = E.boot_providers(ds.prov[idx], lambda i: AP(yy[i], px[i], sample_weight=ww[i]) - AP(yy[i], ps[i], sample_weight=ww[i]), 1000, seed=2)
    res["bootstrap"]["xgb_minus_scanner_ci95"] = E.ci95(bs)
res["tau_default_f1"] = float(np.median(np.unique(taus["xgb"][~np.isnan(taus["xgb"])])))
np.savez_compressed(Path(a.out) / "e1_oof.npz", fold=fold, xgb=oof["xgb"], lr=oof["lr"], rf=oof["rf"], tau_xgb=taus["xgb"],
                    y=y, w=w, ev=ev, cols=np.array(cols))
json.dump({str(k): v for k, v in tune.items()}, open(Path(a.out) / "e1_best_params.json", "w"))
curves = {m: [x.tolist() for x in precision_recall_curve(y[ev], oof[m][ev], sample_weight=w[ev])[:2]] for m in ("xgb", "lr", "rf")}
res["pr_curves"] = curves
save(a, "e1.json", res, es)
