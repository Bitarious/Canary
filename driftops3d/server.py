"""DriftOps 3D server: fleet of sites/racks/devices, model results, copilot and the GUI.

    python server.py                    # http://127.0.0.1:8765
    python server.py --host 0.0.0.0     # accept telemetry from other machines on the LAN
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from driftops import copilot
from driftops.fleet import Fleet
from driftops.tslm import TslmClient

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = ROOT / "data" / "machines"
JOBS: dict[str, dict] = {}
FLEET: Fleet
TSLM = TslmClient()   # trained OpenTSLM component models, run in a separate worker process
WARM = {"done": False}


def start_benchmark(port, rounds):
    job = {"id": uuid.uuid4().hex[:8], "status": "running", "progress": 0, "rounds": rounds,
           "message": "Starting agent…", "machine_id": None, "log": []}
    JOBS[job["id"]] = job
    cmd = [sys.executable, "-u", str(ROOT / "agent" / "collect.py"), "--server", f"http://127.0.0.1:{port}",
           "--rounds", str(rounds)]

    def worker():
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
            for line in proc.stdout:
                line = line.strip()
                job["log"] = (job["log"] + [line])[-30:]
                if line.startswith("PROGRESS"):
                    done, total = line.split()[1].split("/")
                    job["progress"] = int(done) / int(total)
                    job["message"] = f"Benchmark round {done}/{total}"
                elif line.startswith("PHASE"):
                    job["message"] = line.split(":", 1)[-1].strip().capitalize()
                elif line.startswith("RESULT"):
                    job["machine_id"] = json.loads(line[6:]).get("machine_id")
            proc.wait()
            job["status"] = "done" if proc.returncode == 0 and job["machine_id"] else "error"
            if job["status"] == "error":
                job["message"] = job["log"][-1] if job["log"] else "Agent failed"
        except Exception as e:  # surfaced to the GUI
            job["status"], job["message"] = "error", str(e)

    threading.Thread(target=worker, daemon=True).start()
    return job


def machine_record(mid):
    runs = FLEET.runs(mid)
    if not runs:
        raise KeyError(mid)
    last = runs[-1]
    return {"id": mid, "runs": len(runs), "last_run": last.get("collected_at"), "source": last.get("source", "agent"),
            "machine": last.get("machine", {}), "summary": FLEET.summary(mid),
            "components": [{"id": c["id"], "type": c.get("type"), "name": c.get("name", c["id"])}
                           for c in last.get("components", [])]}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, fmt, *args):
        line = str(args[0] if args else "")
        if not any(p in line for p in ("/api/jobs/", "/api/status", "GET /js/", "GET /style")):
            sys.stderr.write("%s\n" % (fmt % args))

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        parts = path.split("/")
        try:
            if path == "/api/model-status":
                return self._json(TSLM.status())
            if path == "/api/status":
                return self._json({"ready": WARM["done"], "devices": len(FLEET.device_ids())})
            if path == "/api/sites":
                return self._json(FLEET.site_list())
            if path.startswith("/api/sites/") and len(parts) == 4:
                return self._json(FLEET.site_detail(parts[3]))
            if path.startswith("/api/sites/") and len(parts) == 5 and parts[4] == "timeline":
                return self._json(FLEET.timeline(parts[3]))
            if path == "/api/fleet":
                return self._json(FLEET.summaries())
            if path == "/api/incidents":
                return self._json(FLEET.incidents())
            if path.startswith("/api/machines/") and len(parts) == 4:
                return self._json(machine_record(parts[3]))
            if path.startswith("/api/jobs/"):
                job = JOBS.get(parts[-1])
                return self._json(job) if job else self._json({"error": "unknown job"}, 404)
        except KeyError as e:
            return self._json({"error": f"not found: {e}"}, 404)
        if path == "/favicon.ico":
            self.send_response(204)
            return self.end_headers()
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/telemetry":
                return self._json({"machine_id": FLEET.save_run(self._body())})
            if path == "/api/analyze":
                return self._json(FLEET.analyze(self._body().get("machine_id")))
            if path == "/api/model-readings":
                mid = self._body().get("machine_id")
                runs = FLEET.runs(mid)
                if not runs:
                    raise KeyError(mid)
                return self._json({"machine_id": mid, "readings": TSLM.readings(runs)})
            if path == "/api/copilot":
                body = self._body()
                return self._json(copilot.answer(FLEET, body.get("question", ""), body.get("context") or {}))
            if path == "/api/benchmark":
                rounds = max(3, min(40, int(self._body().get("rounds", 20))))
                return self._json(start_benchmark(self.server.server_address[1], rounds))
        except KeyError as e:
            return self._json({"error": f"unknown device {e}"}, 404)
        except (ValueError, json.JSONDecodeError) as e:
            return self._json({"error": str(e)}, 400)
        self._json({"error": "not found"}, 404)


def main():
    global FLEET
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-demo", action="store_true", help="do not load the demo sites")
    args = ap.parse_args()
    FLEET = Fleet(DATA, demo=not args.no_demo)

    def warm():
        FLEET.warm()
        WARM["done"] = True
        print(f"model results ready for {len(FLEET.device_ids())} devices", flush=True)

    threading.Thread(target=warm, daemon=True).start()
    threading.Thread(target=TSLM.preload, daemon=True).start()
    ThreadingHTTPServer.request_queue_size = 128  # default of 5 refuses connections under parallel page loads
    ThreadingHTTPServer.daemon_threads = True
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"DriftOps 3D running on http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
