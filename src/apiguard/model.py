"""
APIGUARD -- S2b classifier + S2c explainer + T4 trainer.

    python -m apiguard.model train --dataset data/dataset --out models/model.json
    python -m apiguard.model train --dataset data/dataset --out models/model.json --l2-final results/L2_final.csv \
                                   --l2-key results/L2_main_KEY_do_not_show_labellers.csv

model.json is a plain XGBoost JSON model.  The metadata (feature names, tuned parameters, tau, seed,
tool versions, schema versions, corpus statistics) is stored INSIDE it as a booster attribute, so one
committed file carries everything needed to reproduce a result (Deliverable 2, T4 rule 3 and 4).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import xgboost as xgb

from . import evaluation as E
from .core import features as F

META_ATTR = "apiguard_meta"


class Model:
    def __init__(self, booster: xgb.Booster, meta: Dict[str, Any]):
        self.booster, self.meta = booster, meta
        self.names: List[str] = meta["feature_names"]
        self.tau: float = float(meta["tau_default"])
        self._idx = [F.FEATURE_NAMES.index(n) for n in self.names]
        self._explainer = None

    def select(self, X_full: np.ndarray) -> np.ndarray:
        return np.asarray(X_full, dtype=np.float64)[:, self._idx]

    def score(self, X_full) -> np.ndarray:
        """r(e) = f(x(e)) for every row of the FULL 66-column feature matrix."""
        X = self.select(X_full)
        n = int(self.meta["n_rounds"])
        return self.booster.predict(xgb.DMatrix(X, feature_names=None), iteration_range=(0, n))

    def explain(self, X_full, rows: Sequence[int], k: int = 3) -> Dict[int, List[tuple]]:
        """Top-k features pushing each chosen row's raw margin (log-odds) up.  Attributions sum to margin - base margin."""
        import shap
        if self._explainer is None:
            self._explainer = shap.TreeExplainer(self.booster)
        X = self.select(X_full)[list(rows)]
        sv = self._explainer.shap_values(X)
        out = {}
        for j, r in enumerate(rows):
            top = np.argsort(-sv[j])[:k]
            out[r] = [(self.names[t], float(sv[j][t])) for t in top if sv[j][t] > 0]
        return out


def _versions() -> Dict[str, str]:
    import sklearn
    v = {"xgboost": xgb.__version__, "numpy": np.__version__, "scikit-learn": sklearn.__version__, "python": sys.version.split()[0]}
    try:
        import shap
        v["shap"] = shap.__version__
    except Exception:                                   # noqa: BLE001
        pass
    try:
        from . import scanner
        v.update(scanner.scanner_versions())
    except Exception:                                   # noqa: BLE001
        pass
    return v


def train(X: np.ndarray, y: np.ndarray, groups: np.ndarray, cols: Sequence[int], seed: int = 0, tune_iters: int = 30,
          corpus_info: Optional[dict] = None) -> Model:
    """Algorithm 1, last two lines: tune with inner grouped CV, choose tau on pooled inner out-of-fold scores,
    refit on everything, and attach the metadata."""
    cols = list(cols); Xs = X[:, cols]
    params, rounds = E.tune_params(Xs, y, groups, seed, tune_iters)
    inner = E.split_groups(groups, seed + 5, 3); oof = np.zeros(len(y))
    for j in range(3):                                                  # tau from inner out-of-fold scores
        va = inner == j; tr = ~va
        b = E.fit_xgb(Xs[tr], y[tr], Xs[va], y[va], params, seed)
        oof[va] = E.predict(b, Xs[va])
    tau = E.best_f1_threshold(y, oof)
    spw = float((y == 0).sum() / max(1, (y == 1).sum()))
    final = xgb.train(E._xgb_params(y, params, seed), xgb.DMatrix(Xs, label=y), int(rounds * 1.1) + 1, verbose_eval=False)
    meta = {"feature_names": [E.NAMES[c] for c in cols], "feature_schema": F.FEATURE_SCHEMA_VERSION, "lexicon": F.LEXICON_VERSION,
            "params": params, "n_rounds": int(rounds * 1.1) + 1, "tau_default": tau, "seed": seed, "scale_pos_weight": spw,
            "n_train_endpoints": int(len(y)), "positive_rate": float(y.mean()), "versions": _versions(),
            "corpus": corpus_info or {}}
    final.set_attr(**{META_ATTR: json.dumps(meta)})
    return Model(final, meta)


def save(model: Model, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    model.booster.save_model(path)


def load(path: str) -> Model:
    b = xgb.Booster(); b.load_model(path)
    raw = b.attr(META_ATTR)
    if not raw:
        raise SystemExit("%s has no APIGUARD metadata; was it produced by `python -m apiguard.model train`?" % path)
    meta = json.loads(raw)
    if meta["feature_schema"] != F.FEATURE_SCHEMA_VERSION:
        raise SystemExit("Model feature schema %s does not match code schema %s. Retrain." % (meta["feature_schema"], F.FEATURE_SCHEMA_VERSION))
    return Model(b, meta)


def main(argv=None) -> int:
    from . import dataset as D
    ap = argparse.ArgumentParser(prog="apiguard.model")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train", help="fit the final model on all providers and write model.json")
    t.add_argument("--dataset", default="data/dataset"); t.add_argument("--out", default="models/model.json")
    t.add_argument("--seed", type=int, default=0); t.add_argument("--tune-iters", type=int, default=30)
    t.add_argument("--no-group-e", action="store_true", help="scanner-blind model (feature groups A,B,C,D,F only)")
    t.add_argument("--oas3-only", action="store_true", help="train on OpenAPI 3.x endpoints only (Methodology, corpus step 5)")
    t.add_argument("--l2-final"); t.add_argument("--l2-key", default="results/L2_main_KEY_do_not_show_labellers.csv")
    a = ap.parse_args(argv)
    ds = D.load(a.dataset)
    y = ds.y1.copy()
    if a.l2_final:                                              # reference (LLM) labels override scanner labels where they exist
        es = E.build_eval(ds, a.l2_final, a.l2_key, False); y = es.train_label
    keep = np.array([v.startswith("openapi-3") for v in ds.ver]) if a.oas3_only else np.ones(len(y), bool)
    cols = E.NOE if a.no_group_e else E.ALL_COLS
    m = train(ds.X[keep], y[keep], ds.prov[keep], cols, a.seed, a.tune_iters, corpus_info=ds.stats)
    save(m, a.out)
    print("wrote %s | %d features | tau=%.3f | rounds=%d | positive rate %.3f" % (a.out, len(m.names), m.tau, m.meta["n_rounds"], m.meta["positive_rate"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
