# APIGUARD source

Layout follows the D2 system model. `core/` is the **shared core (T3)**: the same
code is imported by the runtime lane (S0, S2a) and by the offline training lane,
so training features and inference features cannot drift apart.

```
src/apiguard/
  core/
    normalizer.py   S0 -- Normaliser   (implemented)
    features.py     S2a -- Feature builder (next)
  scanner.py        S1 -- Spectral + OWASP ruleset wrapper (next)
  verifier.py       S2b/S2c -- XGBoost + SHAP (next)
  gate.py           S3 -- risk gate, exit code (next)
```

## S0 -- Normaliser

Input: one OpenAPI 3.x or Swagger 2.0 file (YAML or JSON).
Output: one `EndpointRecord` per `(path, method)` pair, version-independent.

What it guarantees (the D2 contract):

| Contract | Where it is enforced |
|---|---|
| every endpoint appears exactly once | `seen` set in `Normaliser.normalise()` |
| parse failures logged, never dropped | `normalise_corpus()` yields `ParseFailure` |
| circular `$ref` always terminates | `seen_refs` + `MAX_REF_DEPTH = 8` |
| one internal form for both versions | `_collect_security_schemes`, `_collect_servers`, `_request_body`, `_responses` |
| path params merged into the operation | `_merge_parameters()` (operation wins on `name`+`in`) |
| inherited vs overridden security kept apart | `security_source`: `own` / `inherited` / `override_none` / `own_none` / `none` |

`security_source` is the one field worth defending in the write-up: an operation
with `security: []` under a global requirement (`override_none`) is a different
risk from one that simply inherits it (`inherited`), and collapsing the two would
destroy the signal before S2a ever sees it.

### Use

```bash
# one spec to stdout
PYTHONPATH=src python -m apiguard.core.normalizer spec.yaml

# a whole corpus, with an honest parse-failure rate for T1
PYTHONPATH=src python -m apiguard.core.normalizer corpus/ \
    -o endpoints.jsonl -e parse_errors.jsonl --stats
```

```python
from apiguard.core import normalise_file
spec = normalise_file("openapi.yaml")
for e in spec.endpoints:
    print(e.method, e.path, e.security_source)
```

### Tests

```bash
python tests/test_normalizer.py     # 9 contract tests, no pytest needed
```

Requires PyYAML only.
