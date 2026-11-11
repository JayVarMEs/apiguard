"""E3 -- analyst effort and speed.
(a) Reference-label mode: on the L2 test endpoints, precision@k (k=5,10,20) and 'findings read until all true positives are found' for the model
    ranking vs the scanner severity ranking (ties broken at random, mean of 200 draws); threshold sweep tau in 0.1..0.9 with the three operating
    points (max F1, precision>=0.9, recall>=0.9); share of specifications the gate would fail at each tau (k=0).
(b) Latency (needs a trained model): wall-clock S0, S1, S2a, S2b, S2c per specification on specs of 10-500 endpoints, 10 runs each, median.
Needs results/e1_oof.npz (run E1 first) and models/model.json (python -m apiguard.model train ...)."""
import random, subprocess, time
import numpy as np
from sklearn.metrics import precision_recall_curve
from _common import *
ap = parser(__doc__); ap.add_argument("--model", default="models/model.json"); ap.add_argument("--skip-latency", action="store_true")
ap.add_argument("--corpus", default="corpus"); ap.add_argument("--runs", type=int, default=10); ap.add_argument("--per-bin", type=int, default=8)
a, ds, es, cols, train_ok = setup(ap)
z = np.load(Path(a.out) / "e1_oof.npz"); px = z["xgb"]; ev = es.mask & ~np.isnan(px); y = es.y; w = es.w
res = {}
# ---- (a) effort + tau sweep
idx = np.where(ev)[0]; order = idx[np.argsort(-px[idx])]
def prec_at(order_, k): return float(y[order_[:k]].mean())
def last_tp(order_): pos = np.where(y[order_] == 1)[0]; return int(pos[-1] + 1) if len(pos) else None
sev = scanner_score(ds); rng = np.random.default_rng(0)
eff = {"model": {"precision_at": {k: prec_at(order, k) for k in (5, 10, 20)}, "findings_read_to_all_tp": last_tp(order)}}
sp = {k: [] for k in (5, 10, 20)}; lt = []
for _ in range(200):
    o = idx[np.lexsort((rng.random(len(idx)), -sev[idx]))]
    for k in sp: sp[k].append(prec_at(o, k))
    lt.append(last_tp(o))
eff["scanner_severity"] = {"precision_at": {k: float(np.mean(v)) for k, v in sp.items()}, "findings_read_to_all_tp": float(np.mean([t for t in lt if t]))}
res["effort"] = eff; res["n_eval"] = int(len(idx)); res["n_true_positives"] = int(y[idx].sum())
files = np.array([m["file"] for m in ds.meta]); uf = np.unique(files); sweep = []
for tau in np.round(np.arange(0.1, 0.95, 0.05), 2):
    yh = px[ev] >= tau
    prec = float(np.average(y[ev][yh], weights=w[ev][yh])) if yh.any() else None
    rec = float(np.average(yh[y[ev] == 1], weights=w[ev][y[ev] == 1])) if (y[ev] == 1).any() else None
    fail = float(np.mean([np.nanmax(px[files == f]) >= tau for f in uf if (files == f).any() and not np.all(np.isnan(px[files == f]))]))
    sweep.append(dict(tau=float(tau), precision=prec, recall=rec, spec_fail_rate_k0=fail))
res["tau_sweep"] = sweep
pr, rc, th = precision_recall_curve(y[ev], px[ev], sample_weight=w[ev])
f1 = 2 * pr[:-1] * rc[:-1] / np.maximum(pr[:-1] + rc[:-1], 1e-12)
res["operating_points"] = {"max_f1": float(th[int(np.argmax(f1))]),
                           "precision_ge_0.9": float(th[np.where(pr[:-1] >= 0.9)[0][0]]) if (pr[:-1] >= 0.9).any() else None,
                           "recall_ge_0.9": float(th[np.where(rc[:-1] >= 0.9)[0][-1]]) if (rc[:-1] >= 0.9).any() else None}
# ---- (b) latency
if not a.skip_latency:
    from apiguard import cli, model as M, scanner
    from apiguard.core import normalise_file
    mdl = M.load(a.model); pool = {}
    for i, m in enumerate(ds.meta): pool.setdefault(m["file"], m["n_spec"])
    random.seed(0); picks = []
    for lo, hi in [(10, 50), (50, 100), (100, 250), (250, 500)]:
        c = [f for f, n in pool.items() if lo <= n < hi and Path(f).stat().st_size < 3_000_000]; random.shuffle(c); picks += c[:a.per_bin]
    rows = []
    for f in picks:
        runs = []
        for _ in range(a.runs):
            t = {}; cli.scan(f, a.model, None, None, 0, True, 10, timings=t); runs.append(t)
        med = {k: float(np.median([r[k] for r in runs])) for k in runs[0]}; med["total"] = sum(med.values()); med["n_endpoints"] = pool[f]; med["bytes"] = Path(f).stat().st_size
        rows.append(med); print("latency", pool[f], "endpoints:", round(med["total"], 2), "s", flush=True)
    res["latency"] = {"runs_per_spec": a.runs, "rows": rows}
save(a, "e3.json", res, es)
