"""
APIGUARD -- T1 corpus + T2 L1 labels + T3 shared core, assembled into one training table.

    python -m apiguard.dataset build --corpus corpus --out data/dataset

Steps (Methodology, "Corpus Preparation"):
  1. S1 scan of every file (cached in <out>/scan_cache, so a re-run resumes).
  2. S0 normalise every file; parse failures are logged, never dropped silently.
  3. De-duplicate by specification hash (first file in sorted order is kept).
  4. Tag every endpoint with its provider = first folder under the corpus root (APIs.guru layout).
  5. S2a features WITH the S1 findings (so group E is filled); L1 weak label = any OWASP finding of
     severity error or warn.
Output: <out>.npz (X, y1, feature_names), <out>.meta.jsonl, <out>.findings.jsonl, <out>.stats.json.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import scanner
from .core import features as F
from .core import normalise_file


@dataclass
class Dataset:
    X: np.ndarray
    y1: np.ndarray
    names: List[str]
    meta: List[Dict[str, Any]]
    findings: List[List[Tuple[str, int, str]]]      # per endpoint: (rule, severity, "API4")
    stats: Dict[str, Any]

    @property
    def prov(self) -> np.ndarray:
        return np.array([m["provider"] for m in self.meta])

    @property
    def ver(self) -> np.ndarray:
        return np.array([m["version"] for m in self.meta])

    @property
    def endpoint_ids(self) -> List[str]:
        return [m["endpoint_id"] for m in self.meta]

    @property
    def excluded_rules(self) -> frozenset:
        """Rules not used for L1 labels or category flags (they fire on most endpoints; see build())."""
        return frozenset(self.stats.get("l1_excluded_rules", []))


def l1_label(findings: Sequence[Tuple[str, int, str]], excluded=frozenset()) -> int:
    """L1 weak label: any OWASP finding of severity error or warn from a rule that is not excluded."""
    return int(any(sev <= 1 and rule not in excluded for rule, sev, _ in findings))


def rule_rates(fnd: Sequence[Sequence[Tuple[str, int, str]]]) -> Dict[str, float]:
    """Share of endpoints on which each rule fires (error/warn)."""
    cnt: Counter = Counter()
    for fl in fnd:
        for r in {rule for rule, sev, _ in fl if sev <= 1}:
            cnt[r] += 1
    return {r: c / max(1, len(fnd)) for r, c in cnt.items()}


def _work(args):
    path, provider, located = args
    try:
        ns = normalise_file(path)
    except Exception as ex:                          # noqa: BLE001 - logged, never silent
        return {"file": path, "failed": repr(ex)[:160]}
    eps = ns.endpoints
    attributed = scanner.attribute(located or [], [(e.method, e.path) for e in eps]) if located is not None else {}
    rows = []
    for e in eps:
        d = e.to_dict()
        fl = attributed.get((e.method, e.path), [])
        rows.append({"x": F.build_features(d, fl, len(eps)),
                     "meta": {"endpoint_id": d["endpoint_id"], "file": str(path), "provider": provider, "method": d["method"],
                              "path": d["path"], "version": d["source_version"], "n_spec": len(eps)},
                     "findings": list(dict.fromkeys((f["rule"], f["severity"], f["owasp"]) for f in fl))})   # unique: a rule hit many times in one spec is stored once
    return {"file": path, "spec_hash": eps[0].spec_hash if eps else None, "rows": rows}


def build(corpus: Path, out: Path, run_scan: bool = True, workers: int = 2, log=print, l1_policy: str = "prevalence",
          max_rule_rate: float = 0.25) -> Dataset:
    corpus = Path(corpus)
    files = sorted(p for p in corpus.rglob("*") if p.suffix.lower() in (".json", ".yaml", ".yml"))
    if not files:
        raise SystemExit("No specification files under %s" % corpus)
    out.parent.mkdir(parents=True, exist_ok=True)
    located: Dict[str, Optional[list]] = {}
    versions = {}
    if run_scan:
        located = scanner.scan_corpus(files, out.parent / (out.name + ".scan_cache"), workers=workers, log=log)
        versions = scanner.scanner_versions()
    log("S0/S2a: %d files" % len(files))
    jobs = [(str(f), f.relative_to(corpus).parts[0] if len(f.relative_to(corpus).parts) > 1 else "_root",
             (located.get(str(f.resolve())) if run_scan else None)) for f in files]
    results = []
    with mp.Pool(max(1, workers), maxtasksperchild=50) as pool:
        for i, r in enumerate(pool.imap(_work, jobs, chunksize=4), 1):
            results.append(r)
            if i % 250 == 0:
                log("  %d/%d" % (i, len(jobs)))
    failed = [r for r in results if "failed" in r]
    seen, kept, dups = set(), [], 0
    for r in results:
        if "failed" in r:
            continue
        if r["spec_hash"] is None:                       # a file with no endpoints: nothing to keep, not a duplicate
            continue
        if r["spec_hash"] in seen:
            dups += 1
            continue
        seen.add(r["spec_hash"])
        kept.append(r)
    scan_failed = [f for f, v in located.items() if v is None] if run_scan else []
    X, meta, fnd = [], [], []
    for r in kept:
        for row in r["rows"]:
            X.append(row["x"]); meta.append(row["meta"]); fnd.append(row["findings"])
    # L1 policy.  A pilot scan showed that "any error/warn finding" marks > 90% of endpoints (rules such as the missing-429 or
    # missing-401 response fire almost everywhere), which makes the label useless.  Default: rules that fire on more than
    # `max_rule_rate` of all endpoints are treated as hygiene and are NOT used for labels or category flags.
    rates = rule_rates(fnd)
    excluded = sorted(r for r, v in rates.items() if v > max_rule_rate) if l1_policy == "prevalence" else []
    if l1_policy == "error":
        fnd_l1 = [[f for f in fl if f[1] == 0] for fl in fnd]
    else:
        fnd_l1 = fnd
    y1 = [l1_label(fl, frozenset(excluded)) for fl in fnd_l1]
    p_all = float(np.mean([l1_label(fl) for fl in fnd])) if fnd else 0.0
    pr = float(np.mean(y1)) if y1 else 0.0
    if not 0.05 <= pr <= 0.70:
        log("WARNING: L1 positive rate is %.1f%%; a label this %s carries little signal. Try --max-rule-rate." % (100 * pr, "common" if pr > 0.5 else "rare"))
    Xa = np.array(X, dtype=np.float64)
    stats = {"files": len(files), "parse_failed": len(failed), "parse_failure_rate": len(failed) / len(files),
             "parse_failures": Counter(r["failed"][:70] for r in failed).most_common(10),
             "duplicates_dropped": dups, "specs_kept": len(kept), "endpoints": len(meta), "providers": len({m["provider"] for m in meta}),
             "scan_enabled": run_scan, "scan_failed_files": len(scan_failed), "scanner_versions": versions,
             "feature_schema": F.FEATURE_SCHEMA_VERSION, "lexicon": F.LEXICON_VERSION, "n_features": F.N_FEATURES,
             "positive_rate_L1": float(np.mean(y1)) if y1 else 0.0, "l1_policy": l1_policy, "l1_max_rule_rate": max_rule_rate,
             "l1_excluded_rules": excluded, "positive_rate_if_any_error_or_warn": p_all,
             "rule_rates_top": sorted(((r, round(v, 4)) for r, v in rates.items()), key=lambda t: -t[1])[:30]}
    np.savez_compressed(str(out) + ".npz", X=Xa, y1=np.array(y1, dtype=np.int8), feature_names=np.array(F.FEATURE_NAMES))
    with open(str(out) + ".meta.jsonl", "w", encoding="utf-8") as f:
        for m in meta:
            f.write(json.dumps(m) + "\n")
    with open(str(out) + ".findings.jsonl", "w", encoding="utf-8") as f:
        for fl in fnd:
            f.write(json.dumps(fl) + "\n")
    Path(str(out) + ".stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    log(json.dumps(stats, indent=1))
    return Dataset(Xa, np.array(y1), list(F.FEATURE_NAMES), meta, fnd, stats)


def load(path: str) -> Dataset:
    p = str(path)
    z = np.load(p + ".npz", allow_pickle=False)
    meta = [json.loads(l) for l in open(p + ".meta.jsonl", encoding="utf-8")]
    fnd = [[tuple(x) for x in json.loads(l)] for l in open(p + ".findings.jsonl", encoding="utf-8")]
    stats = json.loads(Path(p + ".stats.json").read_text(encoding="utf-8"))
    names = [str(n) for n in z["feature_names"]]
    if names != F.FEATURE_NAMES:
        raise SystemExit("Dataset was built with a different feature schema (%s). Rebuild it." % stats.get("feature_schema"))
    return Dataset(z["X"], z["y1"].astype(int), names, meta, fnd, stats)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="apiguard.dataset")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the training table from a corpus folder")
    b.add_argument("--corpus", required=True); b.add_argument("--out", default="data/dataset")
    b.add_argument("--no-scan", action="store_true", help="skip S1 (group E stays zero; for testing only)")
    b.add_argument("--workers", type=int, default=2)
    b.add_argument("--l1-policy", choices=["prevalence", "all", "error"], default="prevalence",
                   help="prevalence (default): ignore rules firing on > --max-rule-rate of endpoints; all: any error/warn; error: severity error only")
    b.add_argument("--max-rule-rate", type=float, default=0.25)
    a = ap.parse_args(argv)
    build(Path(a.corpus), Path(a.out), run_scan=not a.no_scan, workers=a.workers, l1_policy=a.l1_policy, max_rule_rate=a.max_rule_rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
