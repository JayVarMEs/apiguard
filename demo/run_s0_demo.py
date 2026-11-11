"""
APIGUARD -- S0 Normaliser demo.

Runs the S0 normaliser over the VAmPI OpenAPI 3 specification (the ground-truth
API of experiment E4) and prints what the rest of the pipeline will see.

    python demo/run_s0_demo.py

Writes demo/out/vampi_endpoints.jsonl and demo/out/parse_errors.jsonl.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apiguard.core.normalizer import normalise_corpus, normalise_file  # noqa: E402

SPECS = ROOT / "demo" / "specs"
OUT = ROOT / "demo" / "out"

# S2a will own the real lexicon; the demo uses a short version only to show
# what an expanded response schema makes visible to a feature builder.
SENSITIVE = ("password", "secret", "token", "email", "admin", "ssn", "card", "balance")


def rule(title=""):
    print("\n" + "=" * 78)
    if title:
        print(title)
        print("=" * 78)


def sensitive_fields(endpoint):
    names = set()
    for resp in endpoint.responses:
        for prop in resp.properties:
            low = prop.name.lower()
            if any(term in low for term in SENSITIVE):
                names.add(prop.name)
    return sorted(names)


def main():
    OUT.mkdir(exist_ok=True)
    spec_file = SPECS / "vampi_openapi3.yaml"

    # ---------------------------------------------------------------- 1
    rule("1. S0 input")
    print(f"file            : {spec_file.relative_to(ROOT)}")
    print(f"size            : {spec_file.stat().st_size:,} bytes")

    spec = normalise_file(spec_file)

    print(f"spec id         : {spec.spec_id}")
    print(f"detected version: {spec.source_version}")
    print(f"content hash    : {spec.spec_hash[:16]}...   (T1 de-duplicates on this)")
    print(f"endpoints E(S)  : {spec.endpoint_count}")

    # ---------------------------------------------------------------- 2
    rule("2. One record per (path, method) -- this is E(S)")
    head = f"{'METHOD':7} {'PATH':30} {'AUTH':13} {'PARAM':5} {'BODY':5} {'RESP':5}"
    print(head)
    print("-" * 78)
    for e in spec.endpoints:
        body = len(e.request_body.properties) if e.request_body else 0
        resp = sum(len(r.properties) for r in e.responses)
        print(f"{e.method.upper():7} {e.path:30} {e.security_source:13} "
              f"{len(e.parameters):<5} {body:<5} {resp:<5}")

    # ---------------------------------------------------------------- 3
    rule("3. What S0 already exposes that a rule scanner does not")
    print("Endpoints with NO security requirement that return sensitive fields:")
    print("(feature group C -- 'no auth AND sensitive response' is one flag for S2a)\n")
    for e in spec.endpoints:
        if e.security_source == "none":
            hits = sensitive_fields(e)
            if hits:
                print(f"  {e.method.upper():6} {e.path:32} -> {', '.join(hits)}")

    print("\nEndpoints that DO require authentication:")
    for e in spec.endpoints:
        if e.security:
            s = e.security[0]
            kind = f"{s.scheme_type}/{s.scheme_subtype}" if s.scheme_subtype else s.scheme_type
            print(f"  {e.method.upper():6} {e.path:32} -> {s.scheme_name} ({kind}) [{e.security_source}]")

    # ---------------------------------------------------------------- 4
    rule("4. One full normalised record (what S2a receives)")
    target = next(e for e in spec.endpoints if e.path == "/users/v1/_debug")
    record = target.to_dict()
    # collapse the expanded schema to one line per property so the whole record fits
    for resp in record["responses"]:
        resp["properties"] = [
            f"{p['path']}: {p['type']}" + (" (required)" if p["required"] else "")
            + (" (truncated)" if p["truncated"] else "")
            for p in resp["properties"]
        ]
    if record["request_body"]:
        record["request_body"]["properties"] = [
            f"{p['path']}: {p['type']}" for p in record["request_body"]["properties"]
        ]
    record["source_file"] = Path(record["source_file"]).name
    print(json.dumps(record, indent=2))
    print("\n(the JSONL output keeps every property field in full)")

    # ---------------------------------------------------------------- 5
    rule("5. Same endpoint, two specification versions -> one internal form")
    sw2 = normalise_file(SPECS / "vampi_swagger2.yaml")
    a = next(e for e in spec.endpoints if (e.method, e.path) == ("get", "/users/v1/_debug"))
    b = next(e for e in sw2.endpoints if (e.method, e.path) == ("get", "/users/v1/_debug"))
    print(f"{'field':22} {'openapi 3.0.1':30} {'swagger 2.0':30}")
    print("-" * 78)
    rows = [
        ("source_version", a.source_version, b.source_version),
        ("operation_id", a.operation_id, b.operation_id),
        ("security_source", a.security_source, b.security_source),
        ("servers", ",".join(a.servers), ",".join(b.servers)),
        ("response props", ",".join(sorted({p.name for p in a.responses[0].properties})),
                           ",".join(sorted({p.name for p in b.responses[0].properties}))),
    ]
    for name, x, y in rows:
        mark = "  =" if str(x) == str(y) else "  <>"
        print(f"{name:22} {str(x)[:30]:30} {str(y)[:30]:30}{mark}")

    print("\nSwagger 2 'body' parameter became a request body, not a parameter:")
    login = next(e for e in sw2.endpoints if e.path == "/users/v1/login")
    print(f"  parameters   : {[p.name for p in login.parameters]}")
    print(f"  request body : required={login.request_body.required} "
          f"props={[p.path for p in login.request_body.properties]}")
    print(f"  content types: {login.request_body.content_types}")

    print("\nPath-level parameter merged into the operation (swagger 2 file):")
    dele = next(e for e in sw2.endpoints if e.method == "delete")
    print(f"  DELETE {dele.path} -> parameters {[ (p.name, p.location) for p in dele.parameters ]}")

    # ---------------------------------------------------------------- 6
    rule("6. Corpus mode -- a broken spec is logged, never dropped")
    broken = OUT / "broken_spec.yaml"
    broken.write_text("openapi: 3.0.0\npaths: [ this is not: valid: :\n", encoding="utf-8")

    endpoints_path = OUT / "vampi_endpoints.jsonl"
    errors_path = OUT / "parse_errors.jsonl"
    n_ok = n_ep = n_bad = 0
    with endpoints_path.open("w", encoding="utf-8") as fo, \
         errors_path.open("w", encoding="utf-8") as fe:
        for parsed, failure in normalise_corpus(
                [SPECS / "vampi_openapi3.yaml", SPECS / "vampi_swagger2.yaml", broken]):
            if failure is not None:
                n_bad += 1
                fe.write(failure.to_json() + "\n")
                print(f"  PARSE FAILURE  {Path(failure.source_file).name}: {failure.detail.splitlines()[0]}")
                continue
            n_ok += 1
            for e in parsed.endpoints:
                fo.write(e.to_json() + "\n")
                n_ep += 1

    total = n_ok + n_bad
    print(f"\n  specs parsed = {n_ok}   failed = {n_bad}   "
          f"parse-failure rate = {n_bad / total * 100:.1f}%   endpoints = {n_ep}")
    print(f"  -> {endpoints_path.relative_to(ROOT)}")
    print(f"  -> {errors_path.relative_to(ROOT)}")
    rule()


if __name__ == "__main__":
    main()
