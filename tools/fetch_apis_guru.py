"""
T1 corpus fetcher -- downloads real OpenAPI specifications from APIs.guru.

APIs.guru is the primary corpus named in the APIGUARD project plan
(~2,500 APIs / ~108,000 endpoints, CC0 licensed). This script pulls the
"preferred" version of each API as YAML and stores it under one folder per
provider, so the provider-grouped splits used in experiment E1 fall straight
out of the directory layout.

    python tools/fetch_apis_guru.py --limit 20 --out corpus/apis_guru
    python tools/fetch_apis_guru.py --all --out corpus/apis_guru     # full corpus

A manifest.jsonl records the source URL and the download date for every file,
which is what the deliverable needs in order to state a corpus snapshot date.
"""
import argparse
import json
import random
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

LIST_URL = "https://api.apis.guru/v2/list.json"
UA = {"User-Agent": "APIGUARD-corpus-fetcher/0.1 (SIIT student project)"}


def fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def safe_name(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in text)[:120]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download OpenAPI specs from APIs.guru")
    ap.add_argument("--out", default="corpus/apis_guru", help="output folder")
    ap.add_argument("--limit", type=int, default=20, help="how many APIs to download")
    ap.add_argument("--all", action="store_true", help="download every API (~2,500)")
    ap.add_argument("--seed", type=int, default=42, help="sampling seed (reproducibility)")
    ap.add_argument("--delay", type=float, default=0.2, help="seconds between requests")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] index: {LIST_URL}")
    index = json.loads(fetch(LIST_URL).decode("utf-8"))
    names = sorted(index.keys())
    print(f"      {len(names)} APIs listed")

    if not args.all:
        random.Random(args.seed).shuffle(names)
        names = names[: args.limit]

    manifest = out / "manifest.jsonl"
    snapshot = date.today().isoformat()
    ok = bad = 0
    with manifest.open("a", encoding="utf-8") as mf:
        for i, name in enumerate(names, 1):
            entry = index[name]
            version = entry.get("preferred") or sorted(entry.get("versions", {}))[-1]
            info = entry["versions"][version]
            url = info.get("swaggerYamlUrl") or info.get("swaggerUrl")
            if not url:
                bad += 1
                continue
            provider = safe_name(name.split(":")[0])          # e.g. googleapis.com
            (out / provider).mkdir(exist_ok=True)
            ext = ".yaml" if url.endswith((".yaml", ".yml")) else ".json"
            dest = out / provider / (safe_name(f"{name}@{version}") + ext)
            if dest.exists():
                continue
            try:
                dest.write_bytes(fetch(url))
                ok += 1
                mf.write(json.dumps({
                    "api": name, "version": version, "provider": provider,
                    "source_url": url, "file": str(dest).replace("\\", "/"),
                    "snapshot_date": snapshot,
                }) + "\n")
            except Exception as exc:                          # noqa: BLE001
                bad += 1
                print(f"      ! {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            print(f"\r[2/2] downloaded {ok}/{len(names)}", end="", flush=True)
            time.sleep(args.delay)

    print(f"\n      ok={ok} failed={bad} snapshot={snapshot}")
    print(f"      -> {out}  (manifest: {manifest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
