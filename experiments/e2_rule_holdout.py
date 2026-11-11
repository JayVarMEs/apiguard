"""E2 -- rule hold-out (the headline experiment, RQ2).  For each OWASP category c with enough positives:
  1. drop from TRAINING every endpoint whose only findings are category c;
  2. recompute every group-E feature with all category-c findings deleted;
  3. train as in Algorithm 1 (training label = findings in OTHER categories, or the reference label minus c where L2 exists);
  4. on test folds: positives = L2 endpoints whose reference categories include c, negatives = ALL other L2 endpoints (including positives of other categories).
Reference (best case): same model trained WITH c.  Chance: prevalence.  A category 'generalises' when the lower end of the 95% provider
bootstrap interval of (PR-AUC - prevalence) is above zero.  RQ2 answer = number of categories that generalise out of those tested.
In --proxy mode (no reference labels) group E is dropped entirely and 'positives' are scanner findings in c: a pipeline check only."""
import numpy as np
from sklearn.metrics import average_precision_score as AP, roc_auc_score
from _common import *
ap = parser(__doc__); ap.add_argument("--min-pos", type=int, default=20, help="min positive endpoints (reference-label mode) per category")
a, ds, es, cols, train_ok = setup(ap)
bp = Path(a.out) / "e1_best_params.json"
tune = {int(k): v for k, v in json.load(open(bp)).items()} if bp.exists() else None
if tune is None: print("note: results/e1_best_params.json not found; tuning inside E2 (slower)")
H = E.cat_flags(ds.findings, ds.excluded_rules); n = len(ds.meta); prov = ds.prov
X0 = ds.X.copy(); fold = E.split_groups(prov, 0)
res = {"min_pos": a.min_pos, "categories": {}}
for c in range(1, 11):
    if es.proxy:
        has_c = H[:, c - 1]; other_train = H[:, [j for j in range(10) if j != c - 1]].any(1); evaluable = has_c | (~H.any(1))
        pos_mask = has_c; need = 500
    else:
        has_c = np.array([c in s for s in es.cats]); evaluable = es.mask; pos_mask = es.mask & has_c; need = a.min_pos
        # training label without c: L1 findings in other categories; L2 endpoints use the reference categories minus c
        other_train = H[:, [j for j in range(10) if j != c - 1]].any(1)
        for i in np.where(es.mask)[0]:
            other_train[i] = bool(es.cats[i] - {c}) if es.y[i] == 1 else False
    npos = int(pos_mask.sum()); nprov = int(len(np.unique(prov[pos_mask])))
    if npos < need or nprov < 10:
        res["categories"]["API%d" % c] = {"skipped": "only %d positive endpoints in %d providers" % (npos, nprov)}; print("API%d skipped" % c); continue
    X = ds.X.copy()
    if not es.proxy:
        X[:, E.GROUP_E_COLS] = E.group_e_matrix(ds.findings, drop_cat=c)                         # step 2
    Xs = X[:, cols]
    only_c = (H[:, c - 1] & ~other_train) if not es.proxy else (has_c & ~other_train)             # step 1
    oof_h = np.full(n, np.nan); oof_f = np.full(n, np.nan); tau_h = np.full(n, np.nan)
    for k in range(5):
        te = fold == k; trn = (~te) & train_ok
        keep = trn & ~only_c; v = E.holdout(prov[keep], 0); tr_i = np.where(keep)[0][~v]; va_i = np.where(keep)[0][v]
        pm = tune[k] if tune else E.tune_params(Xs[keep], other_train[keep].astype(int), prov[keep], 0, a.tune_iters)[0]
        b = E.fit_xgb(Xs[tr_i], other_train[tr_i].astype(int), Xs[va_i], other_train[va_i].astype(int), pm, 0)
        oof_h[te] = E.predict(b, Xs[te]); tau_h[te] = E.best_f1_threshold(other_train[va_i].astype(int), E.predict(b, Xs[va_i]))
        # reference: category c included (target = category-c label)
        tgt = has_c.astype(int); trn_i = np.where(trn)[0]; v2 = E.holdout(prov[trn_i], 0)
        bf = E.fit_xgb(Xs[trn_i[~v2]], tgt[trn_i[~v2]], Xs[trn_i[v2]], tgt[trn_i[v2]], pm, 0); oof_f[te] = E.predict(bf, Xs[te])
    ev = evaluable & ~np.isnan(oof_h)
    yy = has_c[ev].astype(int); ph, pf, pv = oof_h[ev], oof_f[ev], prov[ev]; ww = es.w[ev]
    prev = float(np.average(yy, weights=ww))
    bt = E.boot_providers(pv, lambda i: AP(yy[i], ph[i], sample_weight=ww[i]) - np.average(yy[i], weights=ww[i]), 1000, seed=c)
    tau = float(np.nanmedian(tau_h))
    r = dict(n_pos=npos, n_providers_pos=nprov, n_eval=int(ev.sum()), prevalence=prev,
             pr_auc_heldout=float(AP(yy, ph, sample_weight=ww)), pr_auc_reference=float(AP(yy, pf, sample_weight=ww)),
             roc_auc_heldout=float(roc_auc_score(yy, ph, sample_weight=ww)), lift_over_chance_ci95=E.ci95(bt),
             recall_at_tau=float(np.average(ph[yy == 1] >= tau, weights=ww[yy == 1])), fpr_at_tau=float(np.average(ph[yy == 0] >= tau, weights=ww[yy == 0])),
             tau=tau, generalised=bool(np.percentile(bt, 2.5) > 0))
    res["categories"]["API%d" % c] = r; print("API%d" % c, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}, flush=True)
tested = [v for v in res["categories"].values() if "skipped" not in v]
res["answer_RQ2"] = {"generalised": int(sum(v["generalised"] for v in tested)), "tested": len(tested)}
save(a, "e2.json", res, es)
