"""E5 -- which features carry the signal.
 (a) leave-one-group-out ablation (A,B,C,D,E,F) and 'all but E': PR-AUC lost against the full model, 2 seeds, same folds and parameters as E1.
 (b) global TreeSHAP: mean |SHAP| per feature (raw margin / log-odds) and per group, on up to 1500 test endpoints per fold.
 (c) text-inflation test: for test endpoints labelled 0, set the group-D length features to the 90th percentile of the training data, change
     nothing else, and report the mean score change and the share that cross tau.  Needs results/e1_best_params.json (run E1 first)."""
import numpy as np
from sklearn.metrics import average_precision_score as AP
from _common import *
a, ds, es, cols, train_ok = setup(parser(__doc__))
tune = {int(k): v for k, v in json.load(open(Path(a.out) / "e1_best_params.json")).items()}
X = ds.X; yt = es.train_label; prov = ds.prov; ev = es.mask; y = es.y; w = es.w
res = {"feature_set": "A-F" if len(cols) == len(E.NAMES) else "A,B,C,D,F (scanner-blind)"}
# (a) ablation
groups = sorted({E.GROUP[c] for c in cols}); abl = {}
for drop in ["none"] + groups:
    use = [c for c in cols if drop == "none" or E.GROUP[c] != drop]; aps = []
    for s in (0, 1):
        fl = E.split_groups(prov, s); o = np.full(len(X), np.nan)
        for k in range(5):
            te = fl == k; trn = (~te) & train_ok; v = E.holdout(prov[trn], s); tr_i = np.where(trn)[0][~v]; va_i = np.where(trn)[0][v]
            b = E.fit_xgb(X[tr_i][:, use], yt[tr_i], X[va_i][:, use], yt[va_i], tune[k], s); o[te] = E.predict(b, X[te][:, use])
        m = ev & ~np.isnan(o); aps.append(AP(y[m], o[m], sample_weight=w[m]))
    abl[drop] = [float(np.mean(aps)), float(np.std(aps))]; print("ablation", drop, abl[drop], flush=True)
res["ablation_pr_auc"] = abl
# (b) + (c) on the seed-0 fold models
import shap
fold = E.split_groups(prov, 0); rng = np.random.default_rng(0); absum = np.zeros(len(cols)); cnt = 0
Xc = X[:, cols]; len_feats = ["summary_len", "description_len", "mean_param_desc_len", "mean_resp_desc_len"]
li = [list(cols).index(F.FEATURE_NAMES.index(n)) for n in len_feats]; deltas, crossed, below_n = [], 0, 0
for k in range(5):
    te = fold == k; trn = (~te) & train_ok; v = E.holdout(prov[trn], 0); tr_i = np.where(trn)[0][~v]; va_i = np.where(trn)[0][v]
    b = E.fit_xgb(Xc[tr_i], yt[tr_i], Xc[va_i], yt[va_i], tune[k], 0)
    tau = E.best_f1_threshold(yt[va_i], E.predict(b, Xc[va_i]))
    samp = rng.choice(np.where(te)[0], size=min(1500, te.sum()), replace=False)
    absum += np.abs(shap.TreeExplainer(b).shap_values(Xc[samp])).sum(0); cnt += len(samp)
    neg = np.where(te & ev & (y == 0))[0]
    if len(neg):
        Xi = Xc[neg].copy()
        for j in li: Xi[:, j] = np.percentile(Xc[trn][:, j], 90)
        p0, p1 = E.predict(b, Xc[neg]), E.predict(b, Xi); deltas.append(p1 - p0); lo = p0 < tau
        below_n += int(lo.sum()); crossed += int((lo & (p1 >= tau)).sum())
imp = absum / cnt
res["shap_global"] = sorted([(E.NAMES[c], float(imp[j]), str(E.GROUP[c])) for j, c in enumerate(cols)], key=lambda t: -t[1])
gs = {}
for n, v, g in res["shap_global"]: gs[g] = gs.get(g, 0.0) + v
res["shap_by_group"] = gs
d = np.concatenate(deltas) if deltas else np.zeros(1)
res["text_inflation"] = {"mean_score_change": float(d.mean()), "median_score_change": float(np.median(d)),
                         "share_crossing_tau": crossed / max(1, below_n), "n_negative_endpoints": int(len(d))}
save(a, "e5.json", res, es)
