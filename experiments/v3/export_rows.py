"""v3 step 1 (runs on the laptop): dump every labelled endpoint (L2 main + extra) and every L3 endpoint
(VAmPI, crAPI) as  {normalised endpoint, raw Spectral findings WITH their JSON path, labels}.
Training/eval happens in train_v3.py on this small file, so the 80k-row dataset is not needed.
Run from Project/:  python experiments/v3/export_rows.py  -> data/v3_rows.jsonl"""
import sys, json, csv, glob
from pathlib import Path
sys.path.insert(0, "src")
from apiguard.core import normalise_file
from apiguard import scanner as S

def tail(p):  # 'c:/cyberProject/corpus/x/y.json' or 'corpus\\x\\y.json' -> 'corpus/x/y.json'
    p = p.replace("\\", "/"); i = p.lower().rfind("corpus/"); return p[i:] if i >= 0 else p

rows = {}   # endpoint_id -> row
for split, key, final in [("main", "results/L2_main_KEY_do_not_show_labellers.csv", "results/L2_final.csv"),
                          ("extra", "results/L2_extra_KEY_do_not_show_labellers.csv", "results/L2_extra_final.csv")]:
    lab = {r["sample_id"]: r for r in csv.DictReader(open(final, encoding="utf-8-sig"))}
    for k in csv.DictReader(open(key, encoding="utf-8-sig")):
        l = lab.get(k["sample_id"])
        if not l or l["final_label"].strip() == "": continue
        rows[k["endpoint_id"]] = {"sid": k["sample_id"], "split": split, "file": tail(k["file"]), "provider": k["provider"],
                                  "weight": float(k["inverse_prob_weight"]), "label": int(l["final_label"]), "cats": l["final_category"]}
files = sorted({r["file"] for r in rows.values()})
print("labelled endpoints", len(rows), "files", len(files))

# raw located findings for those files from the scan cache (done in chunks: `cache LO HI`, then `build`)
need = set(files)
batches = sorted(glob.glob("data/dataset.scan_cache/batch_*.json"))
if len(sys.argv) > 1 and sys.argv[1] == "cache":
    lo, hi = int(sys.argv[2]), int(sys.argv[3]); part = {}
    for b in batches[lo:hi]:
        d = json.load(open(b, encoding="utf-8"))
        for x in d.get("results") or []:
            t = tail(str(x.get("source", "")))
            if t in need and str(x.get("code", "")).startswith("owasp:"):
                part.setdefault(t, []).append({"rule": x["code"], "severity": int(x.get("severity", 3)), "path": [str(p) for p in x.get("path", [])]})
    json.dump(part, open("data/v3_find_%03d.json" % lo, "w")); print("chunk", lo, hi, "files", len(part)); sys.exit()
located = {f: [] for f in files}
for p in glob.glob("data/v3_find_*.json"):
    for k, v in json.load(open(p)).items(): located[k].extend(v)
print("files with findings", sum(1 for v in located.values() if v))

out = open("data/v3_rows.jsonl", "w", encoding="utf-8"); found = 0
for f in files:
    try: ns = normalise_file(f)
    except Exception as ex: print("parse fail", f, ex); continue
    n = len(ns.endpoints)
    for e in ns.endpoints:
        d = e.to_dict(); r = rows.get(d["endpoint_id"])
        if r is None: continue
        found += 1
        out.write(json.dumps({**r, "kind": "L2", "n_spec": n, "ep": d, "findings": located[f]}) + "\n")
print("matched", found, "of", len(rows))

# L3 apps: run Spectral now
l3 = list(csv.DictReader(open("data/L3_vampi.csv", encoding="utf-8-sig")))
for spec in sorted({r["spec_file"] for r in l3}):
    raw = S.run_spectral([Path(spec)])
    fl = [{"rule": x["code"], "severity": int(x.get("severity", 3)), "path": [str(p) for p in x.get("path", [])]}
          for x in raw if str(x.get("code", "")).startswith("owasp:")]
    lab = {(r["method"].lower(), r["path"]): r for r in l3 if r["spec_file"] == spec}
    ns = normalise_file(spec); n = len(ns.endpoints)
    for e in ns.endpoints:
        d = e.to_dict(); r = lab.get((d["method"], d["path"]))
        if r is None: print("no L3 row", spec, d["method"], d["path"]); continue
        out.write(json.dumps({"sid": spec + " " + d["method"] + " " + d["path"], "kind": "L3", "app": Path(spec).stem, "label": int(r["label"]),
                              "cats": r["category"], "design_visible": int(r["design_visible"] or 0), "n_spec": n, "ep": d, "findings": fl,
                              "provider": Path(spec).stem, "weight": 1.0, "split": "L3", "file": spec}) + "\n")
    print(spec, "endpoints", n, "findings", len(fl))
out.close()
