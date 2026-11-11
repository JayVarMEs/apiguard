"""E1 baseline B4 -- zero-shot language model.  Needs: pip install anthropic ; set ANTHROPIC_API_KEY.  Run only on the L2 sample (cost).
It sends the normalised endpoint (no scanner output, no model score) and asks for a risk score 0-100.  temperature 0.
Writes results/e1_llm_scores.csv (sample_id, endpoint_id, score, cost tokens) and prints weighted PR-AUC / ROC-AUC vs the reference labels.
Record the printed model name and date in the report: model output can change between versions."""
import csv, json, os, sys, time
from pathlib import Path
import numpy as np
from _common import *
ap = parser(__doc__); ap.add_argument("--model", required=True, help="model id, e.g. the current Claude model name you are allowed to use")
a, ds, es, cols, train_ok = setup(ap)
if es.proxy: sys.exit("B4 needs reference labels (--l2-final).")
import anthropic
from apiguard.core import normalise_file
client = anthropic.Anthropic()
PROMPT = ("You review OpenAPI endpoint designs for security problems that are visible in the specification itself "
          "(missing or weak authentication, object-level or function-level authorisation, excessive data in responses, "
          "missing limits, insecure transport). Reply with ONLY a number from 0 (no design problem) to 100 (certain design problem).\n\nEndpoint:\n%s")
cache, rows = {}, []
idx = np.where(es.mask)[0]; t_all = time.perf_counter(); tokens = 0
for i in idx:
    m = ds.meta[i]
    if m["file"] not in cache: cache[m["file"]] = {e.endpoint_id: e for e in normalise_file(m["file"]).endpoints}
    ep = cache[m["file"]][m["endpoint_id"]].to_dict()
    for k in ("endpoint_id", "spec_id", "spec_hash", "source_file", "warnings", "schema_version"): ep.pop(k, None)
    r = client.messages.create(model=a.model, max_tokens=8, temperature=0, messages=[{"role": "user", "content": PROMPT % json.dumps(ep)[:12000]}])
    txt = r.content[0].text.strip(); tokens += r.usage.input_tokens + r.usage.output_tokens
    try: sc = float("".join(ch for ch in txt if ch.isdigit() or ch == ".")) / 100.0
    except ValueError: sc = float("nan")
    rows.append((i, sc))
sc = np.array([s for _, s in rows]); ok = ~np.isnan(sc); yy = es.y[idx][ok]; ww = es.w[idx][ok]
out = Path(a.out) / "e1_llm_scores.csv"
with open(out, "w", newline="") as f:
    w_ = csv.writer(f); w_.writerow(["endpoint_id", "score"]); [w_.writerow([ds.meta[i]["endpoint_id"], s]) for i, s in rows]
print("model", a.model, "| date", time.strftime("%Y-%m-%d"), "| n", int(ok.sum()), "| tokens", tokens, "| seconds", round(time.perf_counter() - t_all))
print(E.wmetrics(yy, sc[ok], 0.5, ww))
