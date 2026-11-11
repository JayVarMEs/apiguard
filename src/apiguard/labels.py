"""
APIGUARD -- T2 label store: L2 reference labels (three language-model passes, no human labels) and L3 ground truth.

Workflow (see README_RUN.md):
  1. python experiments/make_l2_sheets.py ...          -> results/L2_pilot_sheet.csv, results/L2_main_sheet.csv (+ KEY files)
  2. Each labelling pass (an LLM, shown only the sheet) fills ONE column pair (label_A_0or1/category_A  or  label_B_0or1/category_B).
  3. python -m apiguard.labels kappa results/L2_main_sheet.csv      -> Cohen's kappa + results/L2_disagreements.csv
  4. python -m apiguard.labels make-final results/L2_main_sheet.csv -> results/L2_final.csv (agreed rows filled in;
     disagreement rows are decided by majority vote of the passes, see results/L2_LABEL_PROVENANCE.txt)
  5. L3: fill data/L3_vampi.csv (see data/L3_template.csv)
Categories are written as API1 ... API10, several separated by ';'.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Set


def _read(path) -> List[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_cats(s: str) -> Set[int]:
    out = set()
    for tok in (s or "").replace(",", ";").split(";"):
        tok = tok.strip().upper().replace("API", "")
        if tok.isdigit() and 1 <= int(tok) <= 10:
            out.add(int(tok))
    return out


def kappa(sheet: str, disagreements_out: str = "results/L2_disagreements.csv") -> float:
    from sklearn.metrics import cohen_kappa_score
    rows = [r for r in _read(sheet) if r["label_A_0or1"].strip() != "" and r["label_B_0or1"].strip() != ""]
    if not rows:
        raise SystemExit("No row has both label_A_0or1 and label_B_0or1 filled.")
    a = [int(r["label_A_0or1"]) for r in rows]; b = [int(r["label_B_0or1"]) for r in rows]
    k = float(cohen_kappa_score(a, b))
    dis = [r for r, x, y in zip(rows, a, b) if x != y]
    Path(disagreements_out).parent.mkdir(parents=True, exist_ok=True)
    with open(disagreements_out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, list(rows[0].keys())); w.writeheader(); w.writerows(dis)
    agree = 1 - len(dis) / len(rows)
    print("rows labelled by both: %d | raw agreement: %.3f | Cohen's kappa: %.3f | disagreements: %d -> %s"
          % (len(rows), agree, k, len(dis), disagreements_out))
    if k < 0.6:
        print("kappa < 0.6: revise the codebook and label again (Methodology, step 4).")
    return k


def make_final(sheet: str, out: str = "results/L2_final.csv") -> None:
    rows = _read(sheet)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["sample_id", "final_label", "final_category", "decided_by"])
        for r in rows:
            a, b = r["label_A_0or1"].strip(), r["label_B_0or1"].strip()
            if a != "" and a == b:
                cats = sorted(parse_cats(r["category_A"]) & parse_cats(r["category_B"]) or parse_cats(r["category_A"]) | parse_cats(r["category_B"]))
                w.writerow([r["sample_id"], a, ";".join("API%d" % c for c in cats) if a == "1" else "", "agreed"])
            else:
                w.writerow([r["sample_id"], "", "", "DISCUSS / ADVISER"])
    print("wrote", out, "- fill the rows marked DISCUSS before running the experiments")


def load_l2(final_csv: str, key_csv: str) -> Dict[str, dict]:
    """endpoint_id -> {label, cats (set of ints), weight (inverse sampling probability)}."""
    key = {r["sample_id"]: r for r in _read(key_csv)}
    out: Dict[str, dict] = {}
    for r in _read(final_csv):
        lab = r["final_label"].strip()
        if lab == "":
            continue
        k = key.get(r["sample_id"])
        if not k:
            continue
        out[k["endpoint_id"]] = {"label": int(lab), "cats": parse_cats(r["final_category"]), "weight": float(k["inverse_prob_weight"])}
    return out


def load_l3(csv_path: str) -> List[dict]:
    """Rows: spec_file, method, path, label (0/1), category, design_visible (0/1)."""
    rows = []
    for r in _read(csv_path):
        if r["label"].strip() == "":
            continue
        rows.append({"spec_file": r["spec_file"], "method": r["method"].lower(), "path": r["path"], "label": int(r["label"]),
                     "cats": parse_cats(r.get("category", "")), "design_visible": int(r.get("design_visible") or 0)})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="apiguard.labels")
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kappa"); k.add_argument("sheet"); k.add_argument("--out", default="results/L2_disagreements.csv")
    m = sub.add_parser("make-final"); m.add_argument("sheet"); m.add_argument("--out", default="results/L2_final.csv")
    a = ap.parse_args(argv)
    if a.cmd == "kappa":
        kappa(a.sheet, a.out)
    else:
        make_final(a.sheet, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
