"""Bridge from benchmark telemetry to the released OpenTSLM component models.

The trained models live in the repository's training package (``src/driftops``), which needs torch and
shares this package's name. They therefore run in a separate worker process
(``python -m driftops.benchmark_tslm``) using the interpreter in ``DRIFTOPS_TSLM_PYTHON`` or the
repository's ``.venv-tslm``. One request is served at a time.

``readings(runs)`` turns a device's stored runs into 28-sample windows in each model's input contract:

* GPU: power, core and memory temperature sampled during the stress run (nvidia-smi)
* CPU: package power and core temperature sampled during the stress run
* HDD: SMART 5/187/194/197 from ``drive_stats``, one value per day over 28 consecutive days

Each component gets a reading with a ``status``: ``ok``, ``insufficient`` (not enough samples for the
contract), or ``unavailable`` (no worker, weights or base model). The models describe observed patterns;
they are not failure predictors, and the UI labels them that way.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SAMPLES = 28
HDD_CHANNELS = ("smart_5_raw", "smart_187_raw", "smart_194_raw", "smart_197_raw")
# benchmark series key -> model channel name, per component model
CHANNELS = {
    "gpu": (("power_w", "power"), ("temp_c", "core_temperature"), ("mem_temp_c", "memory_temperature")),
    "cpu": (("power_w", "power"), ("temp_c", "core_temperature")),
}
CADENCE_NOTE = {
    "gpu": "Benchmark samples averaged into 28 steps; the model was trained on 28 ten-second means from OLCF Summit GPUs.",
    "cpu": "Benchmark samples averaged into 28 steps; the model was trained on 28 ten-second means from OLCF Summit processors.",
    "hdd": "One SMART reading per day over 28 consecutive days, as in Backblaze Drive Stats training data.",
}
TIMEOUT_S = 600  # the first request also loads a 683 MB checkpoint on CPU


def _python():
    explicit = os.environ.get("DRIFTOPS_TSLM_PYTHON")
    if explicit:
        return explicit
    for candidate in (REPO / ".venv-tslm" / "Scripts" / "python.exe", REPO / ".venv-tslm" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return None


def _bins(values, n=SAMPLES):
    """Average an evenly sampled series into n equal-count bins; None when there are fewer than n samples."""
    clean = [float(v) for v in values if isinstance(v, (int, float))]
    if len(clean) < n:
        return None
    size = len(clean) / n
    return [round(sum(chunk) / len(chunk), 4) for chunk in
            (clean[round(i * size):max(round(i * size) + 1, round((i + 1) * size))] for i in range(n))]


def benchmark_window(component, series):
    """(channels, values, missing) for a CPU/GPU component's raw benchmark samples."""
    channels, values, missing = [], [], []
    for key, name in CHANNELS[component]:
        window = _bins(series.get(key) or [])
        if window is None:
            missing.append(f"{name} ({len(series.get(key) or [])}/{SAMPLES} samples)")
        else:
            channels.append(name)
            values.append(window)
    return channels, values, missing


def hdd_window(runs, component_id):
    """(channels, values, days, missing) from the last 28 consecutive days with drive_stats for one disk."""
    daily = {}
    for run in runs:
        comp = next((c for c in run.get("components", []) if c.get("id") == component_id), None)
        stats = (comp or {}).get("drive_stats")
        if stats and run.get("collected_at"):
            daily[run["collected_at"][:10]] = stats   # runs are oldest first: keep the day's last reading
    if not daily:
        return [], [], 0, ["no SMART drive_stats in any run (ATA hard drive, admin rights needed)"]
    days = sorted(daily)
    end = datetime.fromisoformat(days[-1])
    wanted = [(end - timedelta(days=SAMPLES - 1 - i)).date().isoformat() for i in range(SAMPLES)]
    have = sum(1 for d in wanted if d in daily)
    if have < SAMPLES:
        return [], [], have, [f"{have}/{SAMPLES} consecutive daily SMART readings"]
    channels, values = [], []
    for name in HDD_CHANNELS:
        row = [daily[d].get(name) for d in wanted]
        if all(isinstance(v, (int, float)) for v in row):
            channels.append(name)
            values.append([float(v) for v in row])
    missing = [] if len(channels) >= 2 else ["fewer than two SMART channels reported every day"]
    return channels, values, have, missing


class TslmClient:
    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._seq = 0
        self._cache = {}   # (run stamp, component id) -> reading

    def _ensure(self):
        if self._proc and self._proc.poll() is None:
            return self._proc
        python = _python()
        if not python:
            raise RuntimeError("Model runtime not installed: create .venv-tslm or set DRIFTOPS_TSLM_PYTHON")
        paths = [str(REPO / "src"), *filter(None, [os.environ.get("PYTHONPATH")])]
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(paths), "PYTHONUNBUFFERED": "1"}
        module = os.environ.get("DRIFTOPS_TSLM_MODULE", "driftops.benchmark_tslm")   # overridable for tests
        self._proc = subprocess.Popen([python, "-u", "-m", module], cwd=REPO, env=env, text=True,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return self._proc

    def request(self, payload, timeout=TIMEOUT_S):
        with self._lock:
            proc = self._ensure()
            self._seq += 1
            payload = {**payload, "id": self._seq}
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            result = {}

            def read_reply():
                for line in proc.stdout:   # ignore anything that is not this request's protocol line
                    if line.startswith("{") and f'"id": {payload["id"]},' in line:
                        result["line"] = line
                        return
            reader = threading.Thread(target=read_reply, daemon=True)
            reader.start()
            reader.join(timeout)
            if reader.is_alive() or not result.get("line"):
                proc.kill()
                self._proc = None
                raise RuntimeError("Model worker timed out" if reader.is_alive() else "Model worker exited")
            response = json.loads(result["line"])
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "model error"))
            return response["result"]

    def preload(self):
        """Load models ahead of the first Analyze (DRIFTOPS_TSLM_PRELOAD, default "gpu,hdd"; empty disables)."""
        wanted = [c.strip() for c in os.environ.get("DRIFTOPS_TSLM_PRELOAD", "gpu,hdd").split(",") if c.strip()]
        if not wanted or not _python():
            return
        try:
            available = self.request({"op": "status"}, timeout=120)
            for component in wanted:
                if available.get(component, {}).get("available"):
                    self.request({"op": "load", "component": component})
                    print(f"trained model ready: {available[component]['run']}", flush=True)
        except RuntimeError as error:
            print(f"model preload skipped: {error}", flush=True)

    def status(self):
        try:
            return {"runtime": True, "models": self.request({"op": "status"}, timeout=120)}
        except RuntimeError as error:
            return {"runtime": False, "error": str(error), "models": {}}

    def readings(self, runs):
        """Model readings for every supported component of a device's latest run."""
        latest = runs[-1]
        stamp = latest.get("collected_at")
        out = {}
        for comp in latest.get("components", []):
            kind = comp.get("type")
            if kind == "gpu":
                component = "gpu"
            elif kind == "cpu":
                component = "cpu"
            elif kind == "storage" and (comp.get("static") or {}).get("media") == "hdd":
                component = "hdd"
            else:
                continue
            key = (stamp, comp["id"])
            if key in self._cache:
                out[comp["id"]] = self._cache[key]
                continue
            base = {"component": component, "note": CADENCE_NOTE[component],
                    "scope": "Describes observed signal patterns. Not a failure prediction."}
            if latest.get("source") == "demo":
                out[comp["id"]] = {**base, "status": "insufficient",
                                   "reason": "Synthetic demo telemetry; model readings run on benchmarked devices."}
                continue
            if component == "hdd":
                channels, values, days, missing = hdd_window(runs, comp["id"])
            else:
                channels, values, missing = benchmark_window(component, comp.get("tslm_series") or {})
            if len(channels) < 2:
                out[comp["id"]] = {**base, "status": "insufficient", "channels": channels,
                                   "reason": "Needs at least two channels with a full 28-sample window. Missing: " + "; ".join(missing)}
                continue
            try:
                reading = self.request({"op": "read", "component": component, "channels": channels, "values": values})
            except (RuntimeError, OSError) as error:
                out[comp["id"]] = {**base, "status": "unavailable", "reason": str(error), "channels": channels}
                continue
            reference = dict(part.split(": ", 1) for part in reading["reference"].rstrip(".").split("; "))
            patterns = reading["patterns"]
            # Models trained on more channels can append entries for channels that were not supplied; report, don't use them.
            extra = [p.split(":", 1)[0].strip() for p in reading["answer"].rstrip(".").split(";")
                     if p.strip() and p.split(":", 1)[0].strip() not in channels]
            reading.update(base, status="ok", channels=channels, values=values, skipped=missing, extra_output=extra,
                           answered=len(patterns) == len(channels),
                           agrees_with_rules=all(patterns.get(c) == reference.get(c) for c in channels))
            self._cache[key] = reading
            out[comp["id"]] = reading
        return out
