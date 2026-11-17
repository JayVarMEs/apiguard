"""APIGUARD demo UI: upload an OpenAPI file, convert it to APIGUARD format (S0), then continue to the scan (gate decision and ranked endpoints).
Run:  python demo_ui/app.py   (then it opens http://127.0.0.1:8765)
Uses only the Python standard library; the scan itself is `python -m apiguard scan`."""
import json, os, shutil, subprocess, sys, tempfile, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
if FROZEN:   # packaged exe: models, demo specs and node_modules sit next to the exe (or in its parent folder)
    _d = Path(sys.executable).resolve().parent
    ROOT = _d if (_d / "models").exists() else _d.parent
    UI = Path(getattr(sys, "_MEIPASS", _d)) / "demo_ui" / "index.html"
else:
    ROOT = Path(__file__).resolve().parent.parent
    UI = Path(__file__).resolve().parent / "index.html"
SPECS = ROOT / "demo" / "specs"
MODELS = {"v3": "models/model_v3.json", "l2plus": "models/model_l2plus.json", "scanner": "models/model.json", "l2only": "models/model_l2only.json"}
PORT = int(os.environ.get("PORT", 8765))
HOST = os.environ.get("HOST", "127.0.0.1")   # set HOST=0.0.0.0 when deployed
MAX_BYTES = 3_000_000                        # upload size cap
SLOTS = threading.BoundedSemaphore(2)        # at most 2 scans at once
LAST_PING = [0.0]                            # the page pings every 3 s; no ping for 10 min = window closed (minimised windows are throttled by the browser, so a short limit stopped the app)


def open_app_window(url):
    """Open in a chromeless 'app' window (Edge or Chrome, no address bar or tabs). Falls back to the normal browser."""
    pf = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
          os.environ.get("LOCALAPPDATA", "")]
    cands = [os.path.join(b, r"Microsoft\Edge\Application\msedge.exe") for b in pf] + \
            [os.path.join(b, r"Google\Chrome\Application\chrome.exe") for b in pf] + \
            [shutil.which("msedge") or "", shutil.which("google-chrome") or "", shutil.which("chromium") or ""]
    for exe in cands:
        if exe and os.path.exists(exe):
            subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860",
                              "--user-data-dir=" + os.path.join(tempfile.gettempdir(), "apiguard_app_profile")])
            return
    webbrowser.open(url)


def normalise_upload(body):
    """S0 only: convert the uploaded OpenAPI / Swagger file into APIGUARD's own format (one record per endpoint).
    Same document as normalize_api.py writes; the scan then continues from the same file."""
    if not FROZEN and str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from apiguard.core.normalizer import SpecParseError, normalise_text
    name = os.path.basename(body.get("filename") or "spec.yaml")
    t0 = time.time()
    try:
        ns = normalise_text(body["spec"], source_file=name)
    except SpecParseError as e:
        return {"error": "Could not convert this file: %s\nAPIGUARD reads OpenAPI 3.x and Swagger 2.0 files (.yaml, .yml, .json)." % e}
    rows = []
    for e in ns.endpoints:
        rows.append({
            "method": e.method.upper(), "path": e.path, "operation_id": e.operation_id or "",
            "security_source": e.security_source,
            "security_schemes": ";".join(x.scheme_name for x in e.security),
            "scheme_type": ";".join((x.scheme_type + "/" + x.scheme_subtype) if x.scheme_subtype else x.scheme_type for x in e.security),
            "n_parameters": len(e.parameters),
            "n_body_props": len(e.request_body.properties) if e.request_body else 0,
            "n_response_props": sum(len(r.properties) for r in e.responses),
            "status_codes": ";".join(r.status_code for r in e.responses),
            "deprecated": int(e.deprecated), "endpoint_id": e.endpoint_id})
    doc = {"spec_id": ns.spec_id, "spec_hash": ns.spec_hash, "source_file": name, "source_version": ns.source_version,
           "endpoint_count": ns.endpoint_count, "warnings": ns.warnings, "endpoints": [e.to_dict() for e in ns.endpoints]}
    saved = ""
    try:   # also keep the files on disk, so they can be opened from the Demo folder (S0\\input and S0\\normalizedOutput)
        import csv
        stem = Path(name).stem
        s0 = ROOT / "S0"
        (s0 / "input").mkdir(parents=True, exist_ok=True)
        (s0 / "normalizedOutput").mkdir(parents=True, exist_ok=True)
        (s0 / "input" / name).write_text(body["spec"], encoding="utf-8")
        (s0 / "normalizedOutput" / (stem + ".normalized.json")).write_text(json.dumps(doc, indent=2), encoding="utf-8")
        with open(s0 / "normalizedOutput" / (stem + ".normalized.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["method", "path"])
            w.writeheader(); w.writerows(rows)
        saved = str(s0 / "normalizedOutput")
    except Exception:
        pass
    return {"document": doc, "rows": rows, "seconds": round(time.time() - t0, 2), "saved_to": saved}


def save_feedback(body):
    """Learn loop, first half: a person's verdict on one endpoint goes into a queue file (learn/feedback.jsonl).
    The queue is NOT used by the model now; it is read only by a scheduled retrain (not run in this demo)."""
    f = ROOT / "learn" / "feedback.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    if body.get("verdict") not in ("risk", "false_alarm"):
        return {"error": "bad verdict"}
    rec = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "spec": str(body.get("spec", ""))[:200], "endpoint_id": str(body.get("endpoint_id", ""))[:64],
           "method": str(body.get("method", ""))[:10], "path": str(body.get("path", ""))[:300], "score": body.get("score"), "verdict": body["verdict"]}
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    n = sum(1 for _ in open(f, encoding="utf-8"))
    return {"ok": 1, "queued": n, "file": str(f)}


JOBS = {}


def run_job(body, job):
    """Runs one scan in the background; stage lines from `apiguard scan --progress` go to job['log']."""
    t0 = time.time()
    try:
        ext = ".json" if body.get("filename", "").lower().endswith(".json") else ".yaml"
        with tempfile.TemporaryDirectory() as td:
            spec = Path(td) / ("spec" + ext)
            spec.write_text(body["spec"], encoding="utf-8")
            out = Path(td) / "out.json"
            cmd = ([sys.executable] if FROZEN else [sys.executable, "-m", "apiguard"]) + ["scan", str(spec), "--format", "json", "--out", str(out),
                   "--progress", "--model", MODELS.get(body.get("model", "v3"), MODELS["v3"]),
                   "--max-above", str(int(body.get("k", 0)))]
            if body.get("base"):
                base = Path(td) / ("base" + ext)
                base.write_text(body["base"], encoding="utf-8")
                cmd += ["--base", str(base)]
            if body.get("tau") not in (None, ""):
                cmd += ["--threshold", str(float(body["tau"]))]
            env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
            job["log"].append({"t": 0.0, "m": "SCAN|start|Starting the scan engine"})
            p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            err = []

            def pump():
                for line in p.stderr:
                    if line.startswith("@@"):
                        job["log"].append({"t": round(time.time() - t0, 2), "m": line[2:].strip()})
                    else:
                        err.append(line)
            th = threading.Thread(target=pump, daemon=True)
            th.start()
            try:
                p.wait(timeout=600)
            except subprocess.TimeoutExpired:
                p.kill()
                job["result"] = {"error": "scan timed out (10 min)"}
                return
            th.join(2)
            if not out.exists():
                job["result"] = {"error": ("".join(err) or p.stdout.read() or "scan failed")[-1500:]}
                return
            rep = json.loads(out.read_text(encoding="utf-8"))
            rep["exit_code"] = p.returncode
            rep["seconds"] = round(time.time() - t0, 1)
            job["result"] = rep
    except Exception as e:
        job["result"] = {"error": str(e)}
    finally:
        job["done"] = True
        SLOTS.release()


def start_job(body):
    if not SLOTS.acquire(timeout=120):
        return {"error": "server busy, try again in a minute"}
    jid = os.urandom(6).hex()
    job = {"log": [], "done": False, "result": None}
    for k in list(JOBS)[:-20]:        # keep the last 20 jobs only
        JOBS.pop(k, None)
    JOBS[jid] = job
    threading.Thread(target=run_job, args=(body, job), daemon=True).start()
    return {"job": jid}


class H(BaseHTTPRequestHandler):
    def _send(self, code, data, ctype="application/json"):
        b = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, UI.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/ping":
            LAST_PING[0] = time.time()
            return self._send(200, {"ok": 1})
        if self.path.startswith("/job/"):
            from urllib.parse import urlparse, parse_qs
            u = urlparse(self.path)
            job = JOBS.get(u.path[5:])
            if not job:
                return self._send(200, {"error": "unknown job"})
            frm = int(parse_qs(u.query).get("from", ["0"])[0])
            return self._send(200, {"log": job["log"][frm:], "next": len(job["log"]), "done": job["done"],
                                    "result": job["result"] if job["done"] else None})
        if self.path == "/samples":
            ok = lambda p: p.suffix in (".yaml", ".yml", ".json") and "normalized" not in p.name and p.name != "test_api.yaml"
            return self._send(200, sorted(p.relative_to(SPECS).as_posix() for p in list(SPECS.glob("*")) + list((SPECS / "real").glob("*")) if p.is_file() and ok(p)))
        if self.path.startswith("/sample/"):
            from urllib.parse import unquote
            f = (SPECS / unquote(self.path[8:])).resolve()
            if SPECS.resolve() in f.parents and f.is_file():
                return self._send(200, f.read_bytes(), "text/plain; charset=utf-8")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/scan", "/normalize", "/feedback"):
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BYTES:
                return self._send(200, {"error": "file too large (limit 3 MB)"})
            body = json.loads(self.rfile.read(n))
            if self.path == "/feedback":
                return self._send(200, save_feedback(body))
            if self.path == "/normalize":
                return self._send(200, normalise_upload(body))
            self._send(200, start_job(body))
        except subprocess.TimeoutExpired:
            self._send(200, {"error": "scan timed out (10 min)"})
        except Exception as e:
            self._send(200, {"error": str(e)})

    def log_message(self, *a):
        pass


def serve():
    srv = ThreadingHTTPServer((HOST, PORT), H)
    print(f"APIGUARD demo UI: http://{HOST}:{PORT}   (Ctrl+C to stop)")
    if HOST == "127.0.0.1":
        threading.Timer(1.0, lambda: open_app_window(f"http://127.0.0.1:{PORT}")).start()

        def watchdog():      # closing the app window stops the program
            start = time.time()
            while True:
                time.sleep(3)
                now = time.time()
                if (LAST_PING[0] and now - LAST_PING[0] > 600) or (not LAST_PING[0] and now - start > 300):
                    os._exit(0)
        threading.Thread(target=watchdog, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve()
