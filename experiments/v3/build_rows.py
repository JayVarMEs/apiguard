"""v3 step 1: dump every labelled endpoint (L2 main + extra) and every L3 endpoint as
{normalised endpoint, Spectral findings that belong to it (op-level) + doc-level findings kept separate, labels}.
Inputs: data/v3_find_*.json (raw Spectral results per corpus file, from export_rows.py `cache`),
        data/spectral_<app>.json (raw Spectral on the L3 apps).   Output: data/v3_rows.jsonl"""
import sys, json, csv, glob
from pathlib import Path
sys.path.insert(0, "src")
from apiguard.core import normalise_file
METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}

def tail(p):
    p = p.replace("\\", "/"); i = p.lower().rfind("corpus/"); return p[i:] if i >= 0 else p

def split_findings(raw, method, path):
    """op = findings on this operation or its path item; doc = findings on the rest of the document
    (components, securitySchemes, servers, info ...).  v1 merged both into one list -> every endpoint got the same rules."""
    op, doc = [], []
    for x in raw:
        p = x["path"]
        f = {"rule": x["rule"], "severity": x["severity"]}
        if len(p) >= 2 and p[0] == "paths":
            if p[1] != path: continue
            if len(p) >= 3 and p[2].lower() in METHODS and p[2].lower() != method: continue
            op.append(f)
        else:
            doc.append(f)
    dd = {}
    for f in op: dd[(f["rule"], f["severity"])] = f
    op = list(dd.values()); dd = {}
    for f in doc: dd[(f["rule"], f["severity"])] = f
    return op, list(dd.values())

def raw_from_spectral(js):
    return [{"rule": x["code"], "severity": int(x.get("severity", 3)), "path": [str(p) for p in x.get("path", [])]}
            for x in js if str(x.get("code", "")).startswith("owasp:")]

rows = {}
for split, key, final in [("main", "results/L2_main_KEY_do_not_show_labellers.csv", "results/L2_final.csv"),
                          ("extra", "results/L2_extra_KEY_do_not_show_labellers.csv", "results/L2_extra_final.csv")]:
    lab = {r["sample_id"]: r for r in csv.DictReader(open(final, encoding="utf-8-sig"))}
    for k in csv.DictReader(open(key, encoding="utf-8-sig")):
        l = lab.get(k["sample_id"])
        if not l or l["final_label"].strip() == "": continue
        rows[k["endpoint_id"]] = {"sid": k["sample_id"], "split": split, "file": tail(k["file"]), "provider": k["provider"],
                                  "weight": float(k["inverse_prob_weight"]), "label": int(l["final_label"]), "cats": l["final_category"]}
files = sorted({r["file"] for r in rows.values()})
located = {f: [] for f in files}
for p in glob.glob("data/v3_find_*.json"):
    for k, v in json.load(open(p)).items():
        if k in located: located[k].extend(v)
print("labelled", len(rows), "files", len(files), "files with findings", sum(1 for v in located.values() if v))
out = open("data/v3_rows.jsonl", "w", encoding="utf-8"); found = 0
for f in files:
    try: ns = normalise_file(f)
    except Exception as ex: print("parse fail", f, ex); continue
    n = len(ns.endpoints)
    for e in ns.endpoints:
        d = e.to_dict(); r = rows.get(d["endpoint_id"])
        if r is None: continue
        found += 1; op, doc = split_findings(located[f], d["method"], d["path"])
        out.write(json.dumps({**r, "kind": "L2", "n_spec": n, "ep": d, "op_findings": op, "doc_findings": doc}) + "\n")
print("matched", found, "of", len(rows))
l3 = list(csv.DictReader(open("data/L3_vampi.csv", encoding="utf-8-sig")))
for spec in sorted({r["spec_file"] for r in l3}):
    raw = raw_from_spectral(json.load(open("data/spectral_%s.json" % Path(spec).name)))
    lab = {(r["method"].lower(), r["path"]): r for r in l3 if r["spec_file"] == spec}
    ns = normalise_file(spec); n = len(ns.endpoints)
    for e in ns.endpoints:
        d = e.to_dict(); r = lab.get((d["method"], d["path"]))
        if r is None: print("no L3 row", spec, d["method"], d["path"]); continue
        op, doc = split_findings(raw, d["method"], d["path"])
        out.write(json.dumps({"sid": "%s %s %s" % (Path(spec).stem, d["method"].upper(), d["path"]), "kind": "L3", "app": Path(spec).stem.split("_")[0],
                              "label": int(r["label"]), "cats": r["category"], "design_visible": int(r["design_visible"] or 0), "n_spec": n, "ep": d,
                              "op_findings": op, "doc_findings": doc, "provider": Path(spec).stem, "weight": 1.0, "split": "L3", "file": spec}) + "\n")
    print(spec, n, "findings", len(raw))
