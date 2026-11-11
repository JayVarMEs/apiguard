"""EXTRA L2 sample (training only): endpoints NOT in the 304 test sample or the pilot.  Original docstring: Draw the stratified L2 sample (about 300 + a 30-endpoint pilot) and write BLIND labelling sheets.
Strata: scanner-flagged or not x read/write method x small/large specification; at most 6 endpoints per provider per stratum.
The SHEETS contain no scanner output, no model score and no lexicon feature.  The KEY files (stratum, inverse sampling weight) reveal the
scanner flag and must NOT be shown to the labellers.   Output: results/L2_pilot_sheet.csv, results/L2_main_sheet.csv + KEY files."""
import csv, json, random
import numpy as np
from _common import *
ap = argparse.ArgumentParser(); ap.add_argument("--dataset", default="data/dataset"); ap.add_argument("--out", default="results")
ap.add_argument("--n-main", type=int, default=304); ap.add_argument("--n-pilot", type=int, default=32); ap.add_argument("--seed", type=int, default=20261030)
ap.add_argument("--budget", type=float, default=1e9, help="seconds per run before pausing (resumable)")
a = ap.parse_args(); BUDGET = a.budget; Path(a.out).mkdir(parents=True, exist_ok=True)
from apiguard.core import normalise_file
ds = D.load(a.dataset); meta, y1 = ds.meta, ds.y1; rng = random.Random(a.seed + 777); strata = {}
for i, m in enumerate(meta):
    s = "%s|%s|%s" % ("flagged" if y1[i] else "unflagged", "read" if m["method"] in ("get", "head", "options") else "write", "small" if m["n_spec"] < 20 else "large")
    strata.setdefault(s, []).append(i)
def draw(total, exclude=frozenset()):
    per = max(1, total // len(strata)); picked = []
    for s, idx in sorted(strata.items()):
        pool = [i for i in idx if i not in exclude]; rng.shuffle(pool); cnt = {}; take = []
        for i in pool:
            p = meta[i]["provider"]
            if cnt.get(p, 0) >= 6: continue
            cnt[p] = cnt.get(p, 0) + 1; take.append(i)
            if len(take) == per: break
        picked += [(i, s, len(idx), len(take)) for i in take]
    return picked
used_ids = set()
for kf in ("results/L2_main_KEY_do_not_show_labellers.csv", "results/L2_pilot_KEY_do_not_show_labellers.csv"):
    used_ids |= {r["endpoint_id"] for r in csv.DictReader(open(kf, encoding="utf-8-sig"))}
used_idx = {i for i, m in enumerate(meta) if m["endpoint_id"] in used_ids}
print("already labelled/piloted endpoints:", len(used_idx))
extra = draw(a.n_main, used_idx); cache = {}
def describe(i):
    m = meta[i]; f = m["file"].replace("\\", "/")
    if f not in cache:
        cache[f] = ({e.endpoint_id: e for e in normalise_file(f).endpoints}, json.load(open(f, encoding="utf-8")) if f.endswith(".json") else {})
    eps, raw = cache[f]; ep = eps[m["endpoint_id"]]
    op = (raw.get("paths", {}).get(m["path"], {}) or {}).get(m["method"], {}) or {}
    return dict(api=str((raw.get("info") or {}).get("title", ""))[:80], spec_version=m["version"], method=m["method"].upper(), path=m["path"],
                summary=str(op.get("summary", ""))[:200], description=str(op.get("description", ""))[:400].replace("\n", " "),
                parameters=("; ".join("%s (%s%s)" % (p.name, p.location, ", required" if p.required else "") for p in ep.parameters) or "-")[:300],
                request_body_fields=(", ".join(p.path for p in (ep.request_body.properties[:25] if ep.request_body else [])) or "-")[:300],
                security_requirement="%s (%s)" % (", ".join("%s/%s" % (s.scheme_type, s.scheme_subtype or "") for s in ep.security) or "NONE", ep.security_source),
                responses_and_fields=(" | ".join("%s: %s" % (r.status_code, ", ".join(p.path for p in r.properties[:15]) or "-") for r in ep.responses[:6]) or "-")[:500])
def write(rows, name, prefix):
    cols = ["sample_id", "api", "spec_version", "method", "path", "summary", "description", "parameters", "request_body_fields",
            "security_requirement", "responses_and_fields", "label_A_0or1", "category_A", "label_B_0or1", "category_B", "notes"]
    import time
    fs, ks = Path(a.out) / (name + "_sheet.csv"), Path(a.out) / (name + "_KEY_do_not_show_labellers.csv")
    order = list(range(len(rows))); rng.shuffle(order)                         # shuffle so strata are not visible from the order
    done = 0
    if fs.exists() and ks.exists():                                            # RESUME: keep complete rows already written
        with open(fs, newline="", encoding="utf-8-sig") as f0:
            done = sum(1 for _ in csv.DictReader(f0))
        with open(ks, newline="", encoding="utf-8-sig") as k0:
            done = min(done, sum(1 for _ in csv.reader(k0)) - 1)
    mode = "a" if done else "w"
    t0 = time.time()
    with open(fs, mode, newline="", encoding="utf-8-sig") as f, open(ks, mode, newline="", encoding="utf-8-sig") as k:
        w = csv.DictWriter(f, cols); kw = csv.writer(k)
        if not done:
            w.writeheader(); kw.writerow(["sample_id", "endpoint_id", "file", "provider", "stratum", "stratum_size", "stratum_sampled", "inverse_prob_weight"])
        for n, j in enumerate(order, 1):
            if n <= done: continue
            if time.time() - t0 > BUDGET: print("PAUSED %s at %d of %d: run the same command again" % (name, n - 1, len(order))); raise SystemExit(3)
            i, s, sz, tk = rows[j]; r = describe(i); r["sample_id"] = "%s%03d" % (prefix, n); w.writerow({c: r.get(c, "") for c in cols})
            kw.writerow([r["sample_id"], meta[i]["endpoint_id"], meta[i]["file"], meta[i]["provider"], s, sz, tk, round(sz / max(tk, 1), 4)])
            f.flush(); k.flush()
write(extra, "L2_extra", "X")
print("extra", len(extra))
