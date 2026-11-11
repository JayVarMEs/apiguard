"""
APIGUARD -- S1 Rule scanner (Spectral + @stoplight/spectral-owasp-ruleset).

Input : one or many specification files.
Output: findings attributed to endpoints.  A finding on one operation belongs to that operation;
        a finding on a path-level node belongs to every method of that path; a document-level
        finding (servers, securitySchemes, ...) belongs to every endpoint (Deliverable 2, S1).

Spectral is an external Node.js tool.  Install it once with `npm install` in the project root
(package.json pins the versions).  Finding it:  APIGUARD_SPECTRAL env var > ./node_modules/.bin/spectral
> `spectral` on PATH.  The ruleset file is config/owasp.mjs unless APIGUARD_RULESET is set.
The Spectral and ruleset versions are read back and stored in every model artefact, because a
version change silently changes every label.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
SEVERITY_NAME = {0: "error", 1: "warn", 2: "info", 3: "hint"}
_CAT_RE = re.compile(r"^owasp:(api\d+):", re.IGNORECASE)
if getattr(sys, "frozen", False):
    # Packaged exe: files live next to the exe (dist\apiguard.exe -> project root is its parent folder,
    # or the exe's own folder if node_modules sits beside it).
    _exe_dir = Path(sys.executable).resolve().parent
    PROJECT_ROOT = _exe_dir if (_exe_dir / "node_modules").exists() else _exe_dir.parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

EndpointKey = Tuple[str, str]          # (method, path)
Finding = Dict[str, Any]               # {"rule", "severity" (0 error .. 3 hint), "owasp" ("API4" or "")}


class ScannerUnavailable(RuntimeError):
    """Spectral could not be found or could not run."""


def find_spectral() -> str:
    env = os.environ.get("APIGUARD_SPECTRAL")
    if env and Path(env).exists():
        return env
    for name in ("spectral.cmd", "spectral") if os.name == "nt" else ("spectral",):
        local = PROJECT_ROOT / "node_modules" / ".bin" / name
        if local.exists():
            return str(local)
    found = shutil.which("spectral")
    if found:
        return found
    raise ScannerUnavailable("Spectral not found. Run `npm install` in the project folder (needs Node.js), "
                             "or set APIGUARD_SPECTRAL to the spectral executable.")


def ruleset_path() -> str:
    p = Path(os.environ.get("APIGUARD_RULESET", PROJECT_ROOT / "config" / "owasp.mjs"))
    if not p.exists():
        raise ScannerUnavailable("Ruleset file not found: %s" % p)
    return str(p)


def scanner_versions() -> Dict[str, str]:
    out = {"spectral-cli": "unknown", "spectral-owasp-ruleset": "unknown"}
    try:
        out["spectral-cli"] = subprocess.run([find_spectral(), "--version"], capture_output=True, text=True,
                                             timeout=60).stdout.strip() or "unknown"
    except Exception:                       # noqa: BLE001  - version is informational
        pass
    pkg = PROJECT_ROOT / "node_modules" / "@stoplight" / "spectral-owasp-ruleset" / "package.json"
    if pkg.exists():
        out["spectral-owasp-ruleset"] = json.loads(pkg.read_text(encoding="utf-8")).get("version", "unknown")
    return out


def _category(code: str) -> str:
    m = _CAT_RE.match(code or "")
    return m.group(1).upper() if m else ""


def run_spectral(files: Sequence[Path], timeout: int = 900) -> List[Dict[str, Any]]:
    """Run Spectral once over several files; returns the raw result list (each has `source`)."""
    cmd = [find_spectral(), "lint", *[str(Path(f)) for f in files], "--ruleset", ruleset_path(), "-f", "json", "-q"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as ex:
        raise ScannerUnavailable("Spectral timed out after %ds" % timeout) from ex
    text = r.stdout.strip()
    if not text:
        if r.returncode not in (0, 1) and r.stderr.strip():
            raise ScannerUnavailable("Spectral failed: " + r.stderr.strip()[:300])
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError as ex:
        raise ScannerUnavailable("Spectral gave unreadable output: " + text[:200]) from ex


def _norm(p: str) -> str:
    return str(Path(p).resolve())


UNATTRIBUTED = [0]   # OWASP results Spectral returned without a `source` (reported in the log)


def to_findings(raw: Iterable[Mapping[str, Any]]) -> Dict[str, List[Tuple[List[Any], Finding]]]:
    """Group raw Spectral results by source file; keep only OWASP-ruleset findings."""
    by_file: Dict[str, List[Tuple[List[Any], Finding]]] = {}
    for x in raw:
        code = str(x.get("code", ""))
        if not code.startswith("owasp:"):
            continue
        src = x.get("source")
        if not src:                                  # cannot attribute to a file: count it, never crash
            UNATTRIBUTED[0] += 1
            continue
        f = {"rule": code, "severity": int(x.get("severity", 3)), "owasp": _category(code)}
        by_file.setdefault(_norm(str(src)), []).append((list(x.get("path", [])), f))
    return by_file


def attribute(located: Sequence[Tuple[List[Any], Finding]],
              endpoint_keys: Iterable[EndpointKey]) -> Dict[EndpointKey, List[Finding]]:
    """Attribute findings to endpoints (see module docstring).  Every endpoint gets a list (maybe empty)."""
    keys = set(endpoint_keys)
    out: Dict[EndpointKey, List[Finding]] = {k: [] for k in keys}
    doc_level: List[Finding] = []
    for path, f in located:
        if len(path) >= 2 and path[0] == "paths":
            p = str(path[1])
            if len(path) >= 3 and str(path[2]).lower() in HTTP_METHODS:
                k = (str(path[2]).lower(), p)
                if k in out:
                    out[k].append(f)
                continue
            for m in HTTP_METHODS:                       # path-level node -> all methods of that path
                if (m, p) in out:
                    out[(m, p)].append(f)
        else:
            doc_level.append(f)
    if doc_level:
        for k in out:
            out[k].extend(doc_level)
    return out


def scan_file(path: Path, endpoint_keys: Iterable[EndpointKey]) -> Dict[EndpointKey, List[Finding]]:
    """Scan one specification and attribute its findings (used by the CLI)."""
    by_file = to_findings(run_spectral([Path(path)]))
    return attribute(by_file.get(_norm(str(path)), []), endpoint_keys)


def scan_corpus(files: Sequence[Path], cache_dir: Path, workers: int = 2, batch_files: int = 25,
                batch_bytes: int = 3_000_000, log=print) -> Dict[str, Optional[List[Tuple[List[Any], Finding]]]]:
    """Scan many files in size-balanced batches; each batch result is cached on disk, so a re-run resumes.
    Returns {resolved file path: located findings, or None if its batch failed}."""
    import concurrent.futures as cf
    cache_dir.mkdir(parents=True, exist_ok=True)
    files = sorted((Path(f) for f in files), key=lambda p: p.stat().st_size)
    batches: List[List[Path]] = []
    cur: List[Path] = []
    size = 0
    for f in files:
        s = f.stat().st_size
        if cur and (len(cur) >= batch_files or size + s > batch_bytes):
            batches.append(cur)
            cur, size = [], 0
        cur.append(f)
        size += s
    if cur:
        batches.append(cur)

    def one(ib):
        i, b = ib
        fn = cache_dir / ("batch_%04d.json" % i)
        if fn.exists():
            return i, json.loads(fn.read_text(encoding="utf-8"))
        try:
            raw = run_spectral(b)
            payload = {"files": [_norm(str(x)) for x in b], "results": raw, "error": None}
        except ScannerUnavailable as ex:
            if len(b) == 1:
                # a single spec Spectral cannot process: record it, but do not cache the failure
                return i, {"files": [_norm(str(b[0]))], "results": None, "error": str(ex)}
            # one bad spec must not drop the whole batch: rescan file by file
            raw, bad = [], []
            for x in b:
                try:
                    for r_ in run_spectral([x]):
                        r_.setdefault("source", str(x))      # single-file output may omit `source`
                        raw.append(r_)
                except ScannerUnavailable as ex2:
                    bad.append(_norm(str(x)))
                    log("  S1: cannot scan %s (%s)" % (x, str(ex2).splitlines()[-1][:120]))
            payload = {"files": [_norm(str(x)) for x in b if _norm(str(x)) not in bad],
                       "results": raw, "error": None, "unscannable": bad}
        fn.write_text(json.dumps(payload), encoding="utf-8")
        return i, payload

    out: Dict[str, Optional[List[Tuple[List[Any], Finding]]]] = {}
    log("S1: %d files in %d batches" % (len(files), len(batches)))
    with cf.ThreadPoolExecutor(max(1, workers)) as ex:
        for i, payload in ex.map(one, enumerate(batches)):
            if payload["results"] is None:
                for f in payload["files"]:
                    out[f] = None
            else:
                grouped = to_findings(payload["results"])
                for f in payload["files"]:
                    out[f] = grouped.get(f, [])
                for f in payload.get("unscannable", []):
                    out[f] = None
            if i % 20 == 0:
                log("  batch %d/%d" % (i + 1, len(batches)))
    if UNATTRIBUTED[0]:
        log("S1: WARNING %d OWASP results had no source file and were skipped" % UNATTRIBUTED[0])
    return out
