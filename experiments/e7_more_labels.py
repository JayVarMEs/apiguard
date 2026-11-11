"""E7 -- does adding more LLM labels help?  Same test set as E6 (the 304 L2 endpoints, provider-grouped out-of-fold, 5 seeds).
Policy A: train on L2 train folds only (E6).   Policy B: train on L2 train folds + 304 EXTRA endpoints labelled by one LLM pass (single pass, codebook v2).
Extra endpoints of a provider that is in the test fold are never used for that fold (same provider-grouped split).
Output: results/e7.json, models/model_l2plus.json"""
import csv
import numpy as np
from sklearn.metrics import average_precision_score as AP, roc_auc_score as AUC
from _common import *
from apiguard import model as M
ap = parser(__doc__); ap.add_argument("--extra-final", default="results/L2_extra_final.csv"); ap.add_argument("--extra-key", default="results/L2_extra_KEY_do_not_show_labellers.csv")
a, ds, es, cols, _ = setup(ap)
ev = es.mask; y = es.y; w = es.w
key = {r["sample_id"]: r["endpoint_id"] for r in csv.DictReader(open(a.extra_key, encoding="utf-8-sig"))}
idx_of = {e: i for i, e in enumerate(ds.endpoint_ids)}
ex = np.zeros(len(ds.meta), bool); y_tr = es.train_label.copy()
for r in csv.DictReader(open(a.extra_final, encoding="utf-8-sig")):
    i = idx_of[key[r["sample_id"]]]
    assert not ev[i], "extra endpoint overlaps the test sample"
    ex[i] = True; y_tr[i] = int(r["final_label"])
print("extra rows", int(ex.sum()), "positives", int(y_tr[ex].sum()))
res = {"n_test": int(ev.sum()), "n_extra": int(ex.sum()), "extra_pos": int(y_tr[ex].sum()), "seeds": a.seeds}
oo = {"A": [], "B": []}; per = {"A": {}, "B": {}}
import pickle, time, os
os.makedirs("results/e7_cache", exist_ok=True); T0 = time.time()
for s in range(a.seeds):
    for name, ok in (("A", ev), ("B", ev | ex)):
        cp = "results/e7_cache/%s_%d.pkl" % (name, s)
        if os.path.exists(cp):
            oof, taus = pickle.load(open(cp, "rb"))
        else:
            if time.time() - T0 > 110: print("PAUSED: run the same command again"); raise SystemExit(3)
            fold, oof, taus, _, _ = cv_run(ds, es, cols, ok, s, None, a.tune_iters, models=("xgb", "lr"), y_train=y_tr)
            pickle.dump((oof, taus), open(cp, "wb"))
        per[name][s] = {m: E.wmetrics(y[ev], oof[m][ev], taus[m][ev], w[ev]) for m in oof}; oo[name].append(oof)
agg = {}
for name in "AB":
    for m in ("xgb", "lr"):
        agg["%s_%s" % (name, m)] = {k: [float(np.mean([per[name][s][m][k] for s in per[name]])), float(np.std([per[name][s][m][k] for s in per[name]]))] for k in ("pr_auc", "roc_auc", "f1", "mcc")}
sc = scanner_score(ds); flagged = ds.y1
agg["scanner_B1"] = E.wmetrics(y[ev], sc[ev], 1.0, w[ev]); agg["scanner_B1"]["f1"] = E.wmetrics(y[ev], flagged[ev], 0.5, w[ev])["f1"]; agg["scanner_B1"]["mcc"] = E.wmetrics(y[ev], flagged[ev], 0.5, w[ev])["mcc"]
res["per_seed"] = per; res["aggregate"] = agg
idx = np.where(ev)[0]; yy, ww = y[idx], w[idx]
pa = np.mean([o["xgb"][idx] for o in oo["A"]], axis=0); pb = np.mean([o["xgb"][idx] for o in oo["B"]], axis=0); ps = sc[idx]
f = lambda fn, p, q: (lambda i: fn(yy[i], p[i], sample_weight=ww[i]) - fn(yy[i], q[i], sample_weight=ww[i]))
res["seedavg"] = {"A_pr": float(AP(yy, pa, sample_weight=ww)), "B_pr": float(AP(yy, pb, sample_weight=ww)), "scanner_pr": float(AP(yy, ps, sample_weight=ww)),
                  "A_roc": float(AUC(yy, pa, sample_weight=ww)), "B_roc": float(AUC(yy, pb, sample_weight=ww)), "scanner_roc": float(AUC(yy, ps, sample_weight=ww))}
res["bootstrap_ci95"] = {
    "B_minus_scanner_pr": E.ci95(E.boot_providers(ds.prov[idx], f(AP, pb, ps), 1000, seed=11)),
    "B_minus_scanner_roc": E.ci95(E.boot_providers(ds.prov[idx], f(AUC, pb, ps), 1000, seed=12)),
    "B_minus_A_pr": E.ci95(E.boot_providers(ds.prov[idx], f(AP, pb, pa), 1000, seed=13)),
    "B_minus_A_roc": E.ci95(E.boot_providers(ds.prov[idx], f(AUC, pb, pa), 1000, seed=14))}
m = M.train(ds.X[ev | ex], y_tr[ev | ex], ds.prov[ev | ex], cols, 0, a.tune_iters, corpus_info=ds.stats)
M.save(m, "models/model_l2plus.json"); res["final_model_tau"] = float(m.tau)
save(a, "e7.json", res, es)
for k, v in agg.items(): print(k, {kk: (round(vv[0], 3) if isinstance(vv, list) else round(vv, 3)) for kk, vv in v.items()})
print(res["seedavg"]); print(res["bootstrap_ci95"])
