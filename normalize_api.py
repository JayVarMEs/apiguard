"""
APIGUARD -- S0 normaliser, one-click version for VS Code.

HOW TO USE
  1. Put your API specification file (.yaml / .yml / .json) somewhere in this project.
  2. Change INPUT_PATH below to point at it.
  3. Press Run  (the play button, or F5, or Ctrl+F5).

It writes a normalised file next to the input:  <name>.normalized.json
INPUT_PATH may also be a FOLDER -- then every spec inside it is normalised into
one .jsonl file, and unparsable specs are listed in a separate error file.

Needs one package:   pip install pyyaml
"""

# =============================================================================
# EDIT THIS
# =============================================================================

INPUT_PATH = r"C:\cyberProject\S0\input\test_api.yaml"   # file or folder, relative to this script

OUTPUT_PATH = r"C:\cyberProject\S0\normalizedOutput"   # "" = next to the input; a folder or a full file path also works
WRITE_CSV = True        # also write a one-row-per-endpoint .csv you can open in Excel
PRINT_TABLE = True      # print the endpoint table in the terminal

# =============================================================================
# You should not need to change anything below.
# =============================================================================

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

# Check the one dependency first, with a message that names YOUR interpreter.
try:
    import yaml  # noqa: F401
except ImportError:
    print("PyYAML is not installed for the Python that VS Code is running.\n")
    print("Copy this line into the VS Code terminal and press Enter:\n")
    print(f'    "{sys.executable}" -m pip install pyyaml\n')
    print("Then press Run again.")
    raise SystemExit(1)

try:
    from apiguard.core.normalizer import (
        SpecParseError, normalise_corpus, normalise_file,
    )
except ImportError as exc:
    print("ERROR: could not import the normaliser from src/apiguard/core/normalizer.py")
    print(f"       {exc}")
    print("       Run this script from inside the project folder.")
    raise SystemExit(1)

SPEC_SUFFIXES = (".yaml", ".yml", ".json")


def resolve(p: str) -> Path:
    """Accept forward or back slashes, and forgive stray spaces or quotes."""
    path = Path(str(p).strip().strip('"').strip("'"))
    return path if path.is_absolute() else (HERE / path)


def output_target(src: Path, default_name: str) -> Path:
    """
    Decide where to write, from OUTPUT_PATH:
      ""                      -> next to the input file, automatic name
      a folder                -> that folder, automatic name (created if missing)
      a full path with .json  -> exactly that file
    """
    if not OUTPUT_PATH.strip():
        return src.with_name(default_name)
    out = resolve(OUTPUT_PATH)
    if out.is_dir() or out.suffix == "":            # it is a folder
        out.mkdir(parents=True, exist_ok=True)
        return out / default_name
    out.parent.mkdir(parents=True, exist_ok=True)   # it is a file name
    return out


def endpoint_rows(endpoints):
    """Flat rows for the CSV / the printed table."""
    for e in endpoints:
        body = len(e.request_body.properties) if e.request_body else 0
        yield {
            "method": e.method.upper(),
            "path": e.path,
            "operation_id": e.operation_id or "",
            "security_source": e.security_source,
            "security_schemes": ";".join(s.scheme_name for s in e.security),
            "scheme_type": ";".join(
                (f"{s.scheme_type}/{s.scheme_subtype}" if s.scheme_subtype else s.scheme_type)
                for s in e.security
            ),
            "n_path_params": len(e.path_parameters),
            "n_parameters": len(e.parameters),
            "n_body_props": body,
            "n_response_props": sum(len(r.properties) for r in e.responses),
            "status_codes": ";".join(r.status_code for r in e.responses),
            "declares_401_403": int(any(r.status_code in ("401", "403") for r in e.responses)),
            "deprecated": int(e.deprecated),
            "summary_len": e.summary_len,
            "description_len": e.description_len,
            "tags": ";".join(e.tags),
            "servers": ";".join(e.servers),
            "endpoint_id": e.endpoint_id,
            "spec_id": e.spec_id,
            "source_version": e.source_version,
        }


def write_csv(rows, path: Path):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows):
    print(f"\n{'METHOD':7} {'PATH':38} {'AUTH':14} {'PARAM':5} {'BODY':5} {'RESP':5}")
    print("-" * 80)
    for r in rows:
        print(f"{r['method']:7} {r['path'][:38]:38} {r['security_source']:14} "
              f"{r['n_parameters']:<5} {r['n_body_props']:<5} {r['n_response_props']:<5}")


# ----------------------------------------------------------------------------
# one file  ->  <name>.normalized.json
# ----------------------------------------------------------------------------

def run_one_file(src: Path, out: Path):
    print(f"input : {src}")
    try:
        spec = normalise_file(src)
    except SpecParseError as exc:
        print(f"\nCOULD NOT PARSE THIS FILE\n  reason: {exc}")
        print("  Check that it is a valid OpenAPI 3.x or Swagger 2.0 document.")
        return 1

    document = {
        "spec_id": spec.spec_id,
        "spec_hash": spec.spec_hash,
        "source_file": src.name,
        "source_version": spec.source_version,
        "endpoint_count": spec.endpoint_count,
        "warnings": spec.warnings,
        "endpoints": [e.to_dict() for e in spec.endpoints],
    }
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")

    rows = list(endpoint_rows(spec.endpoints))
    print(f"format: {spec.source_version}")
    print(f"api   : {spec.spec_id}")
    print(f"found : {spec.endpoint_count} endpoints")
    if PRINT_TABLE:
        print_table(rows)

    # an endpoint is unauthenticated when it ends up with NO scheme at all --
    # that includes "security: []", which switches the global rule off
    no_auth = [r for r in rows if not r["security_schemes"]]
    print(f"\nsecurity: {len(rows) - len(no_auth)} endpoint(s) require authentication, "
          f"{len(no_auth)} do not")
    for r in no_auth:
        why = ("no rule anywhere" if r["security_source"] == "none"
               else "switched off with 'security: []'")
        print(f"          ! {r['method']} {r['path']}  ({why})")

    print(f"\nwrote : {out}")
    if WRITE_CSV:
        csv_path = out.with_suffix(".csv")
        write_csv(rows, csv_path)
        print(f"wrote : {csv_path}")
    return 0


# ----------------------------------------------------------------------------
# a folder  ->  <folder>.normalized.jsonl  (+ .errors.jsonl)
# ----------------------------------------------------------------------------

def run_folder(src: Path, out: Path):
    files = sorted(p for p in src.rglob("*") if p.suffix.lower() in SPEC_SUFFIXES)
    print(f"input : {src}  ({len(files)} candidate files)")
    if not files:
        print("Nothing to do -- no .yaml/.yml/.json files in that folder.")
        return 1

    err_path = out.with_name(out.stem + ".errors.jsonl")
    n_ok = n_bad = n_ep = 0
    all_rows = []

    with out.open("w", encoding="utf-8") as fo, err_path.open("w", encoding="utf-8") as fe:
        for spec, failure in normalise_corpus(files):
            if failure is not None:
                n_bad += 1
                fe.write(failure.to_json() + "\n")
                print(f"  skipped (logged): {Path(failure.source_file).name}")
                continue
            n_ok += 1
            for e in spec.endpoints:
                fo.write(e.to_json() + "\n")
                n_ep += 1
            all_rows.extend(endpoint_rows(spec.endpoints))

    total = n_ok + n_bad
    print(f"\nparsed: {n_ok} specs   failed: {n_bad} "
          f"({n_bad / total * 100:.1f}% parse-failure)   endpoints: {n_ep}")
    print(f"\nwrote : {out}")
    print(f"wrote : {err_path}")
    if WRITE_CSV:
        csv_path = out.with_suffix(".csv")
        write_csv(all_rows, csv_path)
        print(f"wrote : {csv_path}")
    return 0


def main() -> int:
    # a path given on the command line wins over INPUT_PATH
    raw = sys.argv[1] if len(sys.argv) > 1 else INPUT_PATH
    src = resolve(raw)

    print("=" * 80)
    print("APIGUARD  S0 -- normalise an API specification")
    print("=" * 80)

    if not src.exists():
        print(f"input : {src}")
        print("\nTHAT FILE DOES NOT EXIST.")
        print("Open normalize_api.py and set INPUT_PATH to your specification file.")
        return 1

    if src.is_dir():
        code = run_folder(src, output_target(src, f"{src.name}.normalized.jsonl"))
    else:
        code = run_one_file(src, output_target(src, src.stem + ".normalized.json"))

    print("=" * 80)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
