# APIGUARD

Continuous API security assessment in DevSecOps pipelines (final-year cyber project, SIIT, Thammasat University).

APIGUARD reads an OpenAPI/Swagger file, runs a Spectral + OWASP API Top 10 ruleset, turns every endpoint into 66 features, ranks endpoints by risk with an XGBoost model (SHAP explains each score), and decides a pass/fail gate for the pull request.

## Quick start
```
pip install -r requirements.txt
npm install                      # Spectral (the scanner step)
python -m apiguard scan demo/specs/vampi_openapi3.yaml --model models/model_v3.json --format text
python demo_ui/app.py            # web demo at http://127.0.0.1:8765
```
Windows helpers: `RUN_DEMO.bat`, `RUN_DEMO_CLI.bat`, `RUN_UI.bat`, `RUN_ALL.bat` (all experiments). Details: `README_RUN.md`. Paper source: `overleaf/`.

Labels for the reference sample (L2) and external ground truth (L3) were produced by language models against the OWASP checklist. A person audited a random sample of 28 of the LLM checker's accepted verdicts and agreed on all 28 (experiment E11).

## Install (summary)
- Python 3.11+ and Node.js 20+.
- `pip install -r requirements.txt` then `npm install` (Spectral 6.17.0 + OWASP ruleset 2.0.1).
- Linux/macOS: `export PYTHONPATH=src`. Windows PowerShell: `$env:PYTHONPATH="src"`.

## Test
```
python tests/test_components.py      # expected: 7/7 passed
python tests/test_normalizer.py
python tests/test_features_gate.py
```
Then scan the sample API (the command in Quick start). It prints a ranked risk list and a pass/fail gate; the exit code is 0 for pass and 1 for fail.

## Executable demo (Windows)
`APIGUARD.exe` is too large for GitHub (410 MB). Download it from the GitHub Release: https://github.com/JayVarMEs/apiguard/releases/download/v1.0/APIGUARD.exe (release page: https://github.com/JayVarMEs/apiguard/releases/tag/v1.0). Double-click it, load an API file, convert it to the APIGUARD format (S0), then click to continue the scan.

## Model v3 (final model in the paper, experiment E15)
v3 is trained on the 608 LLM reference labels only, matches each Spectral finding to its own endpoint, drops the context features (group F) and adds 14 flaw-pattern features (group H: BOLA-style object IDs, admin/debug paths, writes without login, mass-assignment fields, URL inputs, auth endpoints without rate limits, secrets in responses). On the 304 test endpoints it reaches PR-AUC 0.62 and ROC-AUC 0.85, against 0.47 and 0.69 for the Spectral scanner (provider-bootstrap 95% intervals exclude zero). It is still weak on crAPI (ROC-AUC 0.40) because the reference labels mark almost only unauthenticated endpoints as risky.

Reproduce (no corpus download needed; the labelled rows are in `data/v3_rows.jsonl`):
```
pip install -r requirements.txt scipy
python experiments/v3/train_v3.py        # prints every variant; writes results/v3/ and a fresh model_v3.json
```
Expected key line with xgboost 3.4.1 (the version used for the paper; `pip install "xgboost==3.4.1"` in a separate environment, since the demo's SHAP step needs xgboost < 3): `v3b: + flaw patterns H  xgb PR 0.617 ROC 0.848 ... crAPI ROC 0.40 VAmPI ROC 0.80`. With xgboost 2.1 the same script gives PR 0.59 / ROC 0.84 (tree building differs slightly between versions); the conclusions do not change. `models/model_v3.json` loads in both versions.
- Feature builder: `src/apiguard/core/features_v3.py` (schema s2a-3.0)
- Final model: `models/model_v3.json` (+ `model_v3.meta.json`, tau = 0.60)
- Write-up, results and the new labelling codebook: `experiments/v3/README.md`, `experiments/v3/v3_results.json`, `experiments/v3/CODEBOOK_v3.md`
- To rebuild `data/v3_rows.jsonl` from the full corpus: `experiments/v3/export_rows.py` (needs the scan cache) then `experiments/v3/build_rows.py`.

The demo (`demo_ui/app.py`, and `APIGUARD.exe` once rebuilt with `RUN_BUILD_UI_EXE.bat`) and `python -m apiguard scan` now use `models/model_v3.json` by default; the older models stay selectable in the demo. Quick check:
```
python -m apiguard scan demo/specs/vampi_openapi3.yaml --model models/model_v3.json
```
Expected: 4 endpoints above tau = 0.60 (`POST /users/v1/login`, `POST /users/v1/register`, `GET /users/v1/{username}`, `GET /users/v1/_debug`, all documented VAmPI flaws) and `GATE: FAIL (exit 1)`.

## Paper
The final report is `overleaf/main_final.pdf` (18 pages); its source is `overleaf/main_final.tex` (IEEEtran; compile with pdfLaTeX, two runs, with `architecture_v4.pdf`, `methodology_v3.png` and `results_a.png` in the same folder).
