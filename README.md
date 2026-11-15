# APIGUARD

Continuous API security assessment in DevSecOps pipelines (final-year cyber project, SIIT, Thammasat University).

APIGUARD reads an OpenAPI/Swagger file, runs a Spectral + OWASP API Top 10 ruleset, turns every endpoint into 66 features, ranks endpoints by risk with an XGBoost model (SHAP explains each score), and decides a pass/fail gate for the pull request.

## Quick start
```
pip install -r requirements.txt
npm install                      # Spectral (the scanner step)
python -m apiguard scan demo/specs/vampi_openapi3.yaml --model models/model_l2plus.json --format text
python demo_ui/app.py            # web demo at http://127.0.0.1:8765
```
Windows helpers: `RUN_DEMO.bat`, `RUN_DEMO_CLI.bat`, `RUN_UI.bat`, `RUN_ALL.bat` (all experiments). Details: `README_RUN.md`. Paper source: `overleaf/`.

Labels for the reference sample (L2) and external ground truth (L3) were produced by language models against the OWASP checklist; no human labelling was used.

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

## Paper
The final report source is `overleaf/main_final.tex` (IEEEtran; compile with pdfLaTeX, two runs).
