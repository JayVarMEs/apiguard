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
