# APIGUARD model v3 — what changed and what it scored (2026-11-17)

## What changed from v1
1. **Train on LLM labels only.** v1's main model (E1) learned from 81k scanner (L1) labels, so it could only copy Spectral.
   v3 trains on the 608 L2 endpoints (main 304 + extra 304). Scanner output is still used, but only as input features.
2. **Scanner findings are matched to each endpoint.** v1 added every document-level finding (components, securitySchemes,
   servers …) to every endpoint, so most endpoints in one spec had the same rules. In v3, group E only counts findings on
   that operation. Document-level findings were tried as a separate group S; they made the score worse, so they are not used.
3. **Group F removed** (spec size, OAS version). It mostly tells the model which provider wrote the spec.
4. **New group H — flaw patterns** (14 features): object id in path (BOLA), user-object + id, BOLA with no auth,
   admin words in path, debug/internal words in path, write with no auth, mass-assignment fields in the request body,
   URL-type parameter (SSRF), auth endpoint, auth endpoint with no rate limit, secret in response, list with no paging,
   numeric path id. Code: `src/apiguard/core/features_v3.py` (schema s2a-3.0).
5. **τ set from LLM labels** (out-of-fold): τ = 0.598 (recall 0.61, precision 0.56). The max-F1 point is τ = 0.49 (F1 0.64).

## How it was tested (same as E6–E8)
Test set = main 304 L2 endpoints. 5-fold CV grouped by provider, 5 seeds. The extra 304 are always in training,
except rows from a provider in the test fold. Metrics are weighted by inverse sampling probability.
All variants use the same folds, the same fixed XGBoost settings (depth 3, eta 0.05, early stopping) and no tuning.
External test: train on all 608, then score VAmPI and crAPI (L3, never seen in training).
The harness reproduces the old numbers: scanner B1 PR-AUC 0.468 (E1: 0.468), v1 features on L2 0.52 (E7 B: 0.517).

## Results (mean of 5 seeds)
| Variant | PR-AUC | ROC-AUC | P@10 | Hybrid PR-AUC | crAPI ROC | VAmPI ROC |
|---|---|---|---|---|---|---|
| Random guess | 0.21 | 0.50 | – | – | – | – |
| Spectral scanner alone (B1) | 0.47 | 0.69 | 0.40 | – | 0.61 | 0.51 |
| v1 main model (E1, trained on 81k scanner labels) | 0.42 | 0.70 | – | – | 0.39 | 0.48 |
| v1 features, trained on L2 | 0.52 | 0.81 | 0.70 | 0.50 | 0.37 | 0.82 |
| v3a: per-endpoint scanner, no F | 0.51 | 0.80 | 0.72 | 0.53 | 0.40 | 0.85 |
| **v3b: + flaw patterns H (final)** | **0.62** | **0.85** | 0.76 | 0.60 | 0.40 | 0.80 |
| v3c: + document-level scanner S | 0.56 | 0.82 | 0.82 | 0.51 | 0.41 | 0.78 |
| v3 with no scanner features (A, B, H) | 0.63 | 0.83 | 0.82 | 0.60 | 0.53 | 0.82 |

Provider-bootstrap 95% CIs (final v3b):
- v3 − scanner: PR-AUC **+0.01 to +0.43**, ROC-AUC **+0.05 to +0.35** → v3 beats the scanner (the CI stays above 0).
- v3 − v1 features: PR-AUC −0.07 to +0.26, ROC-AUC −0.005 to +0.10 → better on average, but not proven with 304 test rows.

SHAP (final model): B security scheme carries most weight (has_security, src_none), then C sensitivity, A structure,
E per-endpoint scanner, H patterns (h_write_noauth is the 4th most important feature overall).

## What is still weak (say this in the report)
**crAPI stays at ROC 0.40.** The reason is the labels, not the features: in the 608 L2 rows, 117 of 129 positives are
endpoints with no authentication, and only 12 of 377 authenticated endpoints are positive. So the model learns
"no auth = risky". All crAPI endpoints are authenticated and its flaws are authorization/logic flaws (BOLA, mass assignment),
so the model ranks the public login/signup endpoints first. On crAPI the plain scanner (ROC 0.61) is better than every model. Fixing this needs labels where authenticated endpoints can be
positive (a codebook that asks about BOLA / mass assignment / admin functions separately) and more vulnerable apps for testing.

## Files
- `src/apiguard/core/features_v3.py` — feature builder s2a-3.0
- `experiments/v3/export_rows.py` (laptop: pulls raw Spectral findings out of the scan cache), `experiments/v3/build_rows.py`,
  `experiments/v3/train_v3.py` — rerun: `python experiments/v3/build_rows.py && python experiments/v3/train_v3.py`
- `data/v3_rows.jsonl` (666 rows: 608 L2 + 58 L3), `data/v3_v1rows.csv` (v1 features copied from dataset.npz),
  `data/spectral_*.json` (Spectral on VAmPI/crAPI)
- `experiments/v3/v3_results.json`, `experiments/v3/v3_oof.csv`, `models/model_v3.json` + `models/model_v3.meta.json` (final model, trained on all 608). A rerun writes fresh copies to `results/v3/`.

The demo/exe still uses the v1 model. Switching it needs `model.py` to load `model_v3.json` with `features_v3`, and
`scanner.attribute()` to keep document-level findings apart.
