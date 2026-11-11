# APIGUARD – how to run everything and get your numbers

All code is written and experiments E1 to E9 have been run (results in `results/`, numbers in `overleaf/main.tex`). The steps below reproduce them in order.
Use Windows PowerShell or cmd in `C:\cyberProject`. About 25 GB free disk and a few hours of machine time are needed for the full corpus.

## 0. Install (once)
```
npm install                       # installs Spectral 6.17.0 + OWASP ruleset 2.0.1 (needs Node.js 20+)
pip install -r requirements.txt   # Python 3.11+
set PYTHONPATH=src                # PowerShell: $env:PYTHONPATH="src"
python tests/test_components.py   # should print "7/7 passed"
```

## 1. Corpus (T1)
```
python tools/fetch_corpus.py --out corpus     # ~2,500 specs; writes corpus/manifest.json (keep it: report needs the snapshot date)
```

## 2. Dataset: normalise + scan + features + L1 labels (T1–T3)
```
python -m apiguard.dataset build --corpus corpus --out data/dataset --workers 4
```
Look at `data/dataset.stats.json`: parse-failure rate, duplicates dropped, `positive_rate_L1`, and `l1_excluded_rules`.
L1 ignores rules that fire on >25 % of endpoints (otherwise ~98 % of endpoints are "positive"). Put those numbers in the paper.
If you see a WARNING about the L1 rate, change `--max-rule-rate`.

## 3. Reference labels L2 (DONE, made by language models: no human step)
Decision (2026-11-10): no person labels or reviews anything. The reference labels come from LLM passes that apply the OWASP API Security Top 10 (2023) category definitions.
- `results/L2_final.csv` = majority vote of 3 LLM passes (2 Claude + 1 Codex) over the 304 endpoints in `results/L2_main_sheet.csv`; 62 positives. Provenance, kappas and the earlier 2-pass key: `results/L2_LABEL_PROVENANCE.txt`.
- To regenerate the sample sheets (only if the dataset changes): `python experiments/make_l2_sheets.py --out results`. Give the sheet (never the KEY file or the lexicon) to each LLM pass, then vote.
- `python -m apiguard.labels kappa <sheet>` still computes agreement if two label columns are filled (works for LLM passes too).
- The report must say the labels are LLM-produced (it does: Sections T2, Method, Threats).

## 4. Ground truth L3 (DONE for VAmPI, made by LLM + OWASP)
`data/L3_vampi.csv` maps VAmPI's documented flaws to endpoints and OWASP categories, from the README and the handler source. Reasoning per row: `data/L3_vampi_NOTES.md`. No human review. crAPI is done too (`demo/specs/crapi_openapi3.json`, 15 flaw endpoints from OWASP's 15 documented challenges, same file `data/L3_vampi.csv`). E4 was run on both apps on 2026-11-10 (`results/e4.json`): ROC-AUC 0.48 (VAmPI) and 0.39 (crAPI), a negative result that the paper reports.

## 5. Experiments (E1–E5)
Common flags: `--l2-final results/L2_final.csv --l2-key results/L2_main_KEY_do_not_show_labellers.csv` (the defaults point there already).
```
python experiments/e1_accuracy.py       --l2-final results/L2_final.csv     # E1: accuracy vs baselines, 5 seeds, provider-grouped CV
python experiments/e2_rule_holdout.py   --l2-final results/L2_final.csv     # E2: generalise to an OWASP category the labels never covered
python experiments/e5_ablation_shap.py  --l2-final results/L2_final.csv     # E5: ablation, SHAP, text-inflation test
python -m apiguard.model train --l2-final results/L2_final.csv --out models/model.json   # final model, needed by E3 and the CLI
python experiments/e3_effort_latency.py --model models/model.json --l2-final results/L2_final.csv   # E3: latency, effort
python experiments/e4_external.py       --model models/model.json --l3 data/L3_vampi.csv           # E4: VAmPI/crAPI (+ --dynamic-findings file from ZAP/Schemathesis)
python experiments/e1_llm_baseline.py   --model <claude-model-id> --l2-final results/L2_final.csv  # optional B4; needs pip install anthropic + ANTHROPIC_API_KEY
python experiments/e6_l2_only.py       --l2-final results/L2_final.csv --out results   # E6: train on L2 only (writes results/e6.json, models/model_l2only.json); then E4 with --model models/model_l2only.json --out results/e6_out
python experiments/make_l2_extra.py --out results   # 304 EXTRA endpoints for training only (sheet + KEY); labels: results/L2_extra_final.csv
python experiments/e7_more_labels.py   --l2-final results/L2_final.csv --out results   # E7: L2 vs L2+extra (resumable: rerun if it prints PAUSED)
python experiments/e8_hybrid.py        --l2-final results/L2_final.csv --out results   # E8: scanner+model hybrid ranking (needs results/e7_cache from E7)
python experiments/make_figures.py                                             # results/results_a.png, results_b.png
```
Results are JSON files in `results/`. The `--proxy` flag exists only to check the pipeline without reference labels; its numbers are NOT results (the script prints a banner).
For E4 dynamic comparison: run the VAmPI container, then OWASP ZAP baseline/API scan and Schemathesis against it, save their findings as the CSV described in `experiments/e4_external.py`.

## 6. Use it as a tool / in CI
Quick start: double-click `RUN_DEMO.bat` (scans VAmPI and crAPI with the exe, or Python if there is no exe). Use `--model models\model_l2plus.json` (trained on 608 LLM reference labels, E7); `models\model.json` is the scanner-trained model behind Tables E1 to E4. The exe needs Node.js and `npm install` (Spectral) next to it.
```
python -m apiguard scan demo/specs/vampi_openapi3.yaml --model models/model.json --format text
python -m apiguard scan new.yaml --base old.yaml --model models/model.json --max-above 0 --format sarif --out apiguard.sarif
```
Exit code 1 = gate FAIL. `.github/workflows/apiguard.yml` runs this on pull requests. `tools/build_exe.bat` (PyInstaller) builds `dist\apiguard.exe`; it is untested, so try it early.

## 7. Then
The numbers are already in `overleaf/main.tex`. Upload `overleaf/` to Overleaf and rebuild the PDF after any change.


## E9: dynamic check (Schemathesis on VAmPI)
1. Start Docker Desktop, then `docker run -d --name vampi -p 5000:5000 erev0s/vampi`.
2. `powershell -ExecutionPolicy Bypass -File RUN_DYNAMIC.ps1` writes `results\schemathesis_vampi_auth.txt`.
