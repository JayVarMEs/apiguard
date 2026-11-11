"""Shared plumbing for experiments E1-E5.  Run from the project root, e.g.  python experiments/e1_accuracy.py --l2-final ..."""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from apiguard import dataset as D, evaluation as E, labels as L           # noqa: E402
from apiguard.core import features as F                                    # noqa: E402


def parser(desc: str):
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("--dataset", default="data/dataset")
    ap.add_argument("--l2-final", help="reference labels, LLM majority vote (results/L2_final.csv)")
    ap.add_argument("--l2-key", default="results/L2_main_KEY_do_not_show_labellers.csv")
    ap.add_argument("--proxy", action="store_true", help="NO reference labels: run on scanner labels. Pipeline check only; numbers are not results.")
    ap.add_argument("--out", default="results")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--tune-iters", type=int, default=30)
    ap.add_argument("--oas3-train-only", action="store_true", help="train on OpenAPI 3.x endpoints only (Methodology, corpus step 5)")
    return ap


def setup(ap):
    a = ap.parse_args()
    ds = D.load(a.dataset)
    es = E.build_eval(ds, a.l2_final, a.l2_key, a.proxy)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    # Scanner features (group E) ARE the L1 label, so they may only be used when we score against the reference labels.
    cols = E.ALL_COLS if not es.proxy else E.NOE
    train_ok = np.array([v.startswith("openapi-3") for v in ds.ver]) if a.oas3_train_only else np.ones(len(ds.meta), bool)
    return a, ds, es, cols, train_ok


def save(a, name, res, es):
    res["label_source"] = es.source
    res["WARNING"] = "PROXY RUN: scored against scanner labels; not valid evidence" if es.proxy else ""
    p = Path(a.out) / name
    p.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print("wrote", p)


def cv_run(ds, es, cols, train_ok, seed, tune=None, tune_iters=30, models=("xgb", "lr", "rf"), y_train=None):
    """One pass of 5-fold provider-grouped CV (Algorithm 1).  Returns fold, oof, taus, boosters, params.
    Training label = reference (LLM) label where one exists (train folds), else the scanner label."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    X = ds.X[:, cols]; yt = es.train_label if y_train is None else y_train; prov = ds.prov
    fold = E.split_groups(prov, seed)
    oof = {m: np.full(len(X), np.nan) for m in models}; taus = {m: np.full(len(X), np.nan) for m in models}
    boosters, params = {}, {}
    for k in range(5):
        te = fold == k; trn = (~te) & train_ok
        v = E.holdout(prov[trn], seed); tr_i = np.where(trn)[0][~v]; va_i = np.where(trn)[0][v]
        if "xgb" in models:
            if tune is not None and k in tune:
                params[k] = tune[k]
            else:
                params[k], _ = E.tune_params(X[trn], yt[trn], prov[trn], seed, tune_iters)
            b = E.fit_xgb(X[tr_i], yt[tr_i], X[va_i], yt[va_i], params[k], seed); boosters[k] = b
            oof["xgb"][te] = E.predict(b, X[te]); taus["xgb"][te] = E.best_f1_threshold(yt[va_i], E.predict(b, X[va_i]))
        if "lr" in models:
            sc = StandardScaler().fit(np.log1p(X[tr_i]))
            lr = LogisticRegression(max_iter=300, class_weight="balanced").fit(sc.transform(np.log1p(X[tr_i])), yt[tr_i])
            oof["lr"][te] = lr.predict_proba(sc.transform(np.log1p(X[te])))[:, 1]
            taus["lr"][te] = E.best_f1_threshold(yt[va_i], lr.predict_proba(sc.transform(np.log1p(X[va_i])))[:, 1])
        if "rf" in models:
            rf = RandomForestClassifier(n_estimators=100, max_depth=14, min_samples_leaf=5, class_weight="balanced_subsample",
                                        n_jobs=2, random_state=seed).fit(X[tr_i], yt[tr_i])
            oof["rf"][te] = rf.predict_proba(X[te])[:, 1]; taus["rf"][te] = E.best_f1_threshold(yt[va_i], rf.predict_proba(X[va_i])[:, 1])
        print("  seed %d fold %d done" % (seed, k), flush=True)
    return fold, oof, taus, boosters, params


def scanner_score(ds):
    """B1 baseline score: scanner severity, ties broken by rule count (both come from group E)."""
    i_sev = F.FEATURE_NAMES.index("severity_max"); i_cnt = F.FEATURE_NAMES.index("rule_count")
    return ds.X[:, i_sev] * 1000.0 + ds.X[:, i_cnt]
