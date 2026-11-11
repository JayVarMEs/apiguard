"""E6 -- label-policy experiment.  E1 trains on ~81k scanner (L1) labels plus the L2 train folds, so the model mostly learns the scanner.
Here the model is trained ONLY on the LLM reference labels (L2: 304 endpoints, provider-grouped 5-fold CV, 5 seeds) and compared with the
scanner on the same test folds.  The variant is NOT chosen by looking at VAmPI/crAPI: E4 is run on it afterwards and reported as it comes.
Output: results/e6.json, models/model_l2only.json"""
import numpy as np
from sklearn.metrics import average_precision_score as AP
from _common import *
from apiguard import model as M
ap = parser(__doc__); a, ds, es, cols, _ = setup(ap)
ev = es.mask; y = es.y; w = es.w
res = {"n_train_pool": int(ev.sum()), "n_pos": int(y[ev].sum()), "policy": "L2 only (no L1 rows in training)", "seeds": a.seeds}
per_seed = {}; oofs = []
for s in range(a.seeds):
    fold, oof, taus, boosters, params = cv_run(ds, es, cols, ev, s, None, a.tune_iters, models=("xgb", "lr"))
    per_seed[s] = {m: E.wmetrics(y[ev], oof[m][ev], taus[m][ev], w[ev]) for m in oof}; oofs.append(oof)
agg = {m: {k: [float(np.mean([per_seed[s][m][k] for s in per_seed])), float(np.std([per_seed[s][m][k] for s in per_seed]))]
           for k in ("pr_auc", "roc_auc", "f1", "mcc")} for m in ("xgb", "lr")}
sc = scanner_score(ds); flagged = ds.y1
agg["scanner_B1"] = E.wmetrics(y[ev], sc[ev], 1.0, w[ev]); agg["scanner_B1"]["f1"] = E.wmetrics(y[ev], flagged[ev], 0.5, w[ev])["f1"]
agg["scanner_B1"]["mcc"] = E.wmetrics(y[ev], flagged[ev], 0.5, w[ev])["mcc"]
res["per_seed"] = per_seed; res["aggregate"] = agg; res["majority_pr_auc"] = float(np.average(y[ev], weights=w[ev]))
idx = np.where(ev)[0]; yy, ww = y[idx], w[idx]
px = np.mean([o["xgb"][idx] for o in oofs], axis=0); ps = sc[idx]      # seed-averaged out-of-fold score
bs = E.boot_providers(ds.prov[idx], lambda i: AP(yy[i], px[i], sample_weight=ww[i]) - AP(yy[i], ps[i], sample_weight=ww[i]), 1000, seed=2)
res["bootstrap"] = {"xgb_minus_scanner_ci95": E.ci95(bs), "xgb_pr_auc_seedavg": float(AP(yy, px, sample_weight=ww)),
                    "scanner_pr_auc": float(AP(yy, ps, sample_weight=ww)), "resamples": 1000,
                    "note": "seed-averaged out-of-fold score; seeds differ only in the fold split"}
from sklearn.metrics import roc_auc_score as AUC
br = E.boot_providers(ds.prov[idx], lambda i: AUC(yy[i], px[i], sample_weight=ww[i]) - AUC(yy[i], ps[i], sample_weight=ww[i]), 1000, seed=3)
res["bootstrap"]["xgb_minus_scanner_roc_auc_ci95"] = E.ci95(br)
res["bootstrap"]["xgb_roc_auc_seedavg"] = float(AUC(yy, px, sample_weight=ww)); res["bootstrap"]["scanner_roc_auc"] = float(AUC(yy, ps, sample_weight=ww))
m = M.train(ds.X[ev], y[ev], ds.prov[ev], cols, 0, a.tune_iters, corpus_info=ds.stats)
Path("models").mkdir(exist_ok=True); M.save(m, "models/model_l2only.json"); res["final_model_tau"] = float(m.tau)
save(a, "e6.json", res, es)
for k, v in agg.items(): print(k, {kk: (round(vv[0], 3) if isinstance(vv, list) else round(vv, 3)) for kk, vv in v.items()})
print("xgb-scanner CI", res["bootstrap"])
