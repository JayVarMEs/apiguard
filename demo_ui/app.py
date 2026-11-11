"""APIGUARD demo UI: upload an OpenAPI file, get the gate decision and ranked endpoints.
Run:  python demo_ui/app.py   (then it opens http://127.0.0.1:8765)
Uses only the Python standard library; the scan itself is `python -m apiguard scan`."""
import json, os, subprocess, sys, tempfile, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = Path(__file__).resolve().parent / "index.html"
SPECS = ROOT / "demo" / "specs"
MODELS = {"l2plus": "models/model_l2plus.json", "scanner": "models/model.json", "l2only": "models/model_l2only.json"}
PORT = int(os.environ.get("PORT", 8765))
HOST = os.environ.get("HOST", "127.0.0.1")   # set HOST=0.0.0.0 when deployed
MAX_BYTES = 3_000_000                        # upload size cap
SLOTS = threading.BoundedSemaphore(2)        # at most 2 scans at once


def run_scan(body):
    ext = ".json" if body.get("filename", "").lower().endswith(".json") else ".yaml"
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / ("spec" + ext)
        spec.write_text(body["spec"], encoding="utf-8")
        out = Path(td) / "out.json"
        cmd = [sys.executable, "-m", "apiguard", "scan", str(spec), "--format", "json", "--out", str(out),
               "--model", MODELS.get(body.get("model", "l2plus"), MODELS["l2plus"]),
               "--max-above", str(int(body.get("k", 0)))]
        if body.get("base"):
            base = Path(td) / ("base" + ext)
            base.write_text(body["base"], encoding="utf-8")
            cmd += ["--base", str(base)]
        if body.get("tau") not in (None, ""):
            cmd += ["--threshold", str(float(body["tau"]))]
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
        p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        if not out.exists():
            return {"error": (p.stderr or p.stdout or "scan failed")[-1500:]}
        rep = json.loads(out.read_text(encoding="utf-8"))
        rep["exit_code"] = p.returncode
        return rep


class H(BaseHTTPRequestHandler):
    def _send(self, code, data, ctype="application/json"):
        b = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, UI.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/samples":
            return self._send(200, sorted(p.name for p in SPECS.glob("*") if p.suffix in (".yaml", ".yml", ".json") and "normalized" not in p.name and p.name != "test_api.yaml"))
        if self.path.startswith("/sample/"):
            f = SPECS / Path(self.path[8:]).name
            if f.exists():
                return self._send(200, f.read_bytes(), "text/plain; charset=utf-8")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/scan":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BYTES:
                return self._send(200, {"error": "file too large (limit 3 MB)"})
            body = json.loads(self.rfile.read(n))
            if not SLOTS.acquire(timeout=120):
                return self._send(200, {"error": "server busy, try again in a minute"})
            try:
                self._send(200, run_scan(body))
            finally:
                SLOTS.release()
        except subprocess.TimeoutExpired:
            self._send(200, {"error": "scan timed out (10 min)"})
        except Exception as e:
            self._send(200, {"error": str(e)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), H)
    print(f"APIGUARD demo UI: http://{HOST}:{PORT}   (Ctrl+C to stop)")
    if HOST == "127.0.0.1":
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
