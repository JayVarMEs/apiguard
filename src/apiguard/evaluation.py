"""
APIGUARD -- shared training/evaluation helpers (T4 pieces used by the model trainer and by experiments E1-E5).
Everything here is deterministic given the seed.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, f1_score, matthews_corrcoef, precision_recall_curve,
                             roc_auc_score)
import xgboost as xgb

from .core import features as F

NAMES = F.FEATURE_NAMES
GROUP = np.array([F.GROUP_OF[n] for n in NAMES])
ALL_COLS = np.arange(len(NAMES))
NOE = np.where(GROUP != "E")[0]                    # scanner-blind feature set: A, B, C, D, F
GROUP_E_COLS = np.where(GROUP == "E")[0]

SPACE = dict(max_depth=[3, 4, 5, 6, 7, 8], eta=[0.03, 0.06, 0.1, 0.2, 0.3], subsample=[0.6, 0.8, 1.0],
             colsample_bytree=[0.6, 0.8, 1.0], min_child_weight=[1, 3, 5, 10], reg_lambda=[0.5, 1, 2, 5])
DEFAULT_PARAMS = dict(max_depth=6, eta=0.1, subsample=0.8, colsample_bytree=0.8, min_child_weight=3, reg_lambda=1)


# ---------------------------------------------------------------- splits
def split_groups(groups, seed: int, k: int = 5) -> np.ndarray:
    """Fold index per row; every provider is in exactly one fold; folds are balanced by endpoint count."""
    groups = np.asarray(groups)
    ug, counts = np.unique(groups, return_counts=True)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(ug))                                   # seed changes tie-breaking between equal-size groups
    order = sorted(perm, key=lambda i: -counts[i])
    tot = [0] * k
    assign = {}
    for i in order:
        j = int(np.argmin(tot)); assign[ug[i]] = j; tot[j] += counts[i]
    return np.array([assign[g] for g in groups])


def holdout(groups_train, seed: int, frac: float = 0.2) -> np.ndarray:
    """Boolean mask of rows whose provider is in a validation set of ~frac of the providers."""
    groups_train = np.asarray(groups_train)
    ug = np.unique(groups_train)
    rng = np.random.default_rng(seed + 991)
    val = set(rng.choice(ug, size=max(1, int(len(ug) * frac)), replace=False).tolist())
    return np.array([g in val for g in groups_train])


# ---------------------------------------------------------------- xgboost
def sample_params(rng) -> dict:
    return {k: v[int(rng.integers(len(v)))] for k, v in SPACE.items()}


def _xgb_params(y, params, seed):
    spw = (y == 0).sum() / max(1, (y == 1).sum())
    return dict(params, objective="binary:logistic", eval_metric="aucpr", tree_method="hist", nthread=2,
                seed=seed, scale_pos_weight=float(spw))


def fit_xgb(Xtr, ytr, Xva, yva, params, seed, rounds: int = 400):
    d_tr = xgb.DMatrix(Xtr, label=ytr); d_va = xgb.DMatrix(Xva, label=yva)
    return xgb.train(_xgb_params(ytr, params, seed), d_tr, rounds, evals=[(d_va, "val")],
                     early_stopping_rounds=30, verbose_eval=False)


def predict(b, X) -> np.ndarray:
    n = b.best_iteration + 1 if getattr(b, "best_iteration", None) is not None and b.attr("best_iteration") is not None else 0
    return b.predict(xgb.DMatrix(X), iteration_range=(0, n)) if n else b.predict(xgb.DMatrix(X))


def tune_params(X, y, groups, seed: int, iters: int = 30, inner_k: int = 3):
    """Random search; inner grouped k-fold; returns (best_params, mean best round)."""
    rng = np.random.default_rng(seed + 17)
    inner = split_groups(groups, seed + 5, inner_k)
    best = (-1.0, None, None)
    for _ in range(iters):
        pm = sample_params(rng); scores = []; rounds = []
        for j in range(inner_k):
            va = inner == j; tr = ~va
            if y[tr].sum() == 0 or y[va].sum() == 0:
                continue
            b = fit_xgb(X[tr], y[tr], X[va], y[va], pm, seed)
            scores.append(average_precision_score(y[va], predict(b, X[va]))); rounds.append(b.best_iteration + 1)
        if scores and np.mean(scores) > best[0]:
            best = (float(np.mean(scores)), pm, int(np.mean(rounds)))
    if best[1] is None:
        return dict(DEFAULT_PARAMS), 200
    return best[1], best[2]


# ---------------------------------------------------------------- metrics
def best_f1_threshold(y, p) -> float:
    pr, rc, th = precision_recall_curve(y, p)
    f = 2 * pr[:-1] * rc[:-1] / np.maximum(pr[:-1] + rc[:-1], 1e-12)
    return float(th[int(np.argmax(f))]) if len(th) else 0.5


def wmetrics(y, p, tau, w=None) -> dict:
    """PR-AUC, ROC-AUC, F1, MCC (optionally sample-weighted; weights are inverse sampling probabilities)."""
    y = np.asarray(y); p = np.asarray(p); yh = (p >= np.asarray(tau)).astype(int)
    out = dict(pr_auc=float(average_precision_score(y, p, sample_weight=w)),
               f1=float(f1_score(y, yh, sample_weight=w, zero_division=0)),
               mcc=float(matthews_corrcoef(y, yh, sample_weight=w)))
    out["roc_auc"] = float(roc_auc_score(y, p, sample_weight=w)) if len(np.unique(y)) > 1 else float("nan")
    return out


def boot_providers(prov, fn, n: int = 1000, seed: int = 0):
    """Provider-level bootstrap: resample providers with replacement and return [fn(row_indices), ...]."""
    prov = np.asarray(prov); ug = np.unique(prov)
    idx = {g: np.where(prov == g)[0] for g in ug}
    rng = np.random.default_rng(seed); out = []
    for _ in range(n):
        pick = rng.choice(ug, size=len(ug), replace=True)
        try:
            out.append(fn(np.concatenate([idx[g] for g in pick])))
        except ValueError:                                              # resample without both classes
            continue
    return np.array(out)


def ci95(a) -> list:
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]


# ---------------------------------------------------------------- findings helpers
def cat_flags(findings, excluded=frozenset()) -> np.ndarray:
    """(n, 10) bool: error/warn scanner finding in OWASP category 1..10, ignoring the rules in `excluded` (see dataset.build)."""
    out = np.zeros((len(findings), 10), dtype=bool)
    for i, fl in enumerate(findings):
        for r, sv, c in fl:
            if sv <= 1 and r not in excluded and c.startswith("API"):
                out[i, int(c[3:]) - 1] = True
    return out


def group_e_matrix(findings, drop_cat: int | None = None) -> np.ndarray:
    """Recompute the group-E columns, optionally with every finding of one OWASP category deleted (E2, step 2)."""
    cols = F.GROUPS["E"]; out = np.zeros((len(findings), len(cols)))
    stub = {"path": "/x", "method": "get"}
    for i, fl in enumerate(findings):
        keep = [{"rule": r, "severity": s, "owasp": c} for r, s, c in fl if drop_cat is None or c != "API%d" % drop_cat]
        d = F.build_feature_dict(stub, keep)
        out[i] = [d[n] for n in cols]
    return out


# ---------------------------------------------------------------- evaluation labels
class EvalSet:
    """Which endpoints are scored, against which labels.
    source = 'L2' (LLM reference labels, inverse-probability weights) or 'L1_PROXY' (scanner labels: NOT valid evidence)."""
    def __init__(self, mask, y, w, cats, source, train_label):
        self.mask, self.y, self.w, self.cats, self.source, self.train_label = mask, y, w, cats, source, train_label

    @property
    def proxy(self) -> bool:
        return self.source != "L2"


def build_eval(ds, l2_final: str | None, l2_key: str | None, proxy: bool) -> EvalSet:
    from . import labels as L
    n = len(ds.meta)
    cf = cat_flags(ds.findings, ds.excluded_rules)
    if l2_final:
        l2 = L.load_l2(l2_final, l2_key)
        ids = ds.endpoint_ids
        mask = np.zeros(n, bool); y = np.zeros(n, int); w = np.ones(n); cats = [set() for _ in range(n)]
        train_label = ds.y1.copy()
        for i, eid in enumerate(ids):
            r = l2.get(eid)
            if r:
                mask[i] = True; y[i] = r["label"]; w[i] = r["weight"]; cats[i] = r["cats"]; train_label[i] = r["label"]
        if mask.sum() == 0:
            raise SystemExit("No L2 label matched the dataset (check the KEY file belongs to this dataset).")
        return EvalSet(mask, y, w, cats, "L2", train_label)
    if not proxy:
        raise SystemExit("No L2 reference labels given. Pass --l2-final results/L2_final.csv --l2-key results/L2_main_KEY_do_not_show_labellers.csv,\n"
                         "or pass --proxy to run on scanner labels (a smoke test only: the numbers are NOT valid results).")
    print("=" * 78, "\nPROXY MODE: scores are measured against SCANNER labels (L1). This is a pipeline check, not a result.\n" + "=" * 78)
    cats = [set(int(c) + 1 for c in np.where(cf[i])[0]) for i in range(n)]
    return EvalSet(np.ones(n, bool), ds.y1.copy(), np.ones(n), cats, "L1_PROXY", ds.y1.copy())
