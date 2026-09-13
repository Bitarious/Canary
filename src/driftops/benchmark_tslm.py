"""Target-free OpenTSLM readings for live benchmark telemetry.

A long-running worker for the DriftOps 3D server. It reads one JSON request per line on stdin and
writes one JSON response per line on stdout:

    {"id": 1, "op": "status"}
    {"id": 2, "op": "read", "component": "gpu", "channels": ["power", "core_temperature"],
     "values": [[28 floats], [28 floats]]}

Inputs are built with the same code the released models were trained and evaluated with
(``component_data.example`` for CPU/GPU, the full-history SMART format for HDD). The rule-based
weak label for the same window is returned separately as ``reference``; it never enters the prompt.
The models describe observed patterns only. They do not predict failure.

Run from the repository root:  python -m driftops.benchmark_tslm
"""

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

from driftops.annotations import describe_channel
from driftops.tslm_dataset import PATTERNS, input_hash, prepare_input

CATALOG = Path("results/2026-09-13/model-catalog.json")
MAX_LOADED = 2  # each model holds ~1.1 GB of float32 weights on CPU

# Released checkpoints this worker may serve, keyed by component.
RUNS = {"hdd": "full-history-rtx6000-v2", "cpu": "cpu-component-v1", "gpu": "gpu-component-v1"}


def log(message):
    print(message, file=sys.stderr, flush=True)


def catalog():
    models = json.loads(CATALOG.read_text(encoding="utf-8"))["models"]
    return {m["run"].rsplit("/", 1)[-1]: m for m in models if m["status"] == "passed"}


def checkpoint_path(run):
    return Path("artifacts/tslm") / run / "best.pt"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def base_model_cached():
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
        from driftops.windows import read_yaml
        config = read_yaml("config/model.yaml")
        snapshot_download(config["base_model"]["repo_id"], revision=config["base_model"]["revision"], local_files_only=True)
        temporal = config["temporal_checkpoint"]
        hf_hub_download(temporal["repo_id"], temporal["filename"], revision=temporal["revision"], local_files_only=True)
        return True
    except Exception:  # missing cache or gated access not yet granted
        return False


def build(component, channels, values):
    """Model inputs and the rule reference for one observed 28-sample window."""
    values = np.asarray(values, dtype=np.float64)
    if values.shape != (len(channels), 28) or not np.isfinite(values).all():
        raise ValueError("Each channel needs 28 finite observations")
    if component == "hdd":
        inputs = prepare_input({"time_series": values, "time_series_text": [c + "; raw source units" for c in channels]})
        # Same scale text as full-history training (driftops.full_training.example).
        inputs["time_series_text"] = [f"{c}; daily observations; original standard deviation: {s:.8g}."
                                      for c, s in zip(channels, values.std(axis=1, ddof=1))]
        reference = "; ".join(f"{c}: {describe_channel(c, row)['pattern']}" for c, row in zip(channels, values)) + "."
        return inputs, reference
    if sys.platform == "win32":
        # component_data imports dataset-build modules that lock files with the POSIX-only fcntl module.
        # Building one prompt never locks anything, so an empty stand-in keeps the exact training code usable here.
        import types
        sys.modules.setdefault("fcntl", types.ModuleType("fcntl"))
    from driftops.component_data import example, target
    from driftops.prepare_components import specification
    config = specification(component)
    reference = target(values, channels, config)
    row = {"values": values.tolist(), "channels": list(channels), "target": reference,
           "task_id": "benchmark", "drive_id": "benchmark", "group_id": "benchmark", "start": "", "cutoff": ""}
    return example(row, config)["inputs"], reference


def parse(answer, channels):
    """'channel: pattern; ...' -> {channel: pattern}; unknown or missing channels are reported as such."""
    found = {}
    for part in answer.replace("\n", " ").strip().rstrip(".").split(";"):
        name, _, pattern = part.partition(":")
        name, pattern = name.strip(), pattern.strip().rstrip(".")
        if name in channels and pattern in PATTERNS:
            found[name] = pattern
    return found


class Worker:
    def __init__(self):
        self.catalog = catalog()
        self.models = {}  # component -> (model, checkpoint sha), least recently used first

    def status(self):
        cached = base_model_cached()
        out = {}
        for component, run in RUNS.items():
            path = checkpoint_path(run)
            out[component] = {"run": run, "checkpoint": path.exists(), "base_model": cached,
                              "available": path.exists() and cached, "loaded": component in self.models}
        return out

    def model(self, component):
        if component in self.models:
            self.models[component] = self.models.pop(component)
            return self.models[component]
        run = RUNS[component]
        path = checkpoint_path(run)
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint not installed: {path}")
        expected = self.catalog[run]["checkpoint_sha256"]
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"{path} does not match the released checkpoint hash")
        while len(self.models) >= MAX_LOADED:
            self.models.pop(next(iter(self.models)))
        from driftops.opentslm import load_model
        started = time.time()
        self.models[component] = (load_model("cpu", checkpoint=path), actual)
        log(f"loaded {run} in {time.time() - started:.1f}s")
        return self.models[component]

    def read(self, component, channels, values):
        if component not in RUNS:
            raise ValueError(f"No released model serves '{component}'")
        inputs, reference = build(component, channels, values)
        model, checkpoint = self.model(component)
        from driftops.opentslm import generate
        started = time.time()
        answer = generate(model, [{"inputs": inputs}], max_new_tokens=128)[0].strip()
        return {"component": component, "run": RUNS[component], "checkpoint_sha256": checkpoint,
                "answer": answer, "patterns": parse(answer, channels), "reference": reference,
                "input_hash": input_hash(inputs), "latency_ms": round((time.time() - started) * 1000),
                "channel_accuracy": self.catalog[RUNS[component]].get("channel_accuracy")}


def main():
    # stdout carries only protocol lines; model and library chatter goes to stderr.
    protocol, sys.stdout = sys.stdout, sys.stderr
    worker = Worker()
    for line in sys.stdin:
        if not line.strip():
            continue
        request = {}
        try:
            request = json.loads(line)
            if request.get("op") == "status":
                result = worker.status()
            elif request.get("op") == "load":
                worker.model(request["component"])
                result = worker.status()
            elif request.get("op") == "read":
                result = worker.read(request["component"], request["channels"], request["values"])
            else:
                raise ValueError("Unknown operation")
            response = {"id": request.get("id"), "ok": True, "result": result}
        except Exception as error:  # reported to the UI, never fatal for the worker
            response = {"id": request.get("id"), "ok": False, "error": f"{type(error).__name__}: {error}"}
        print(json.dumps(response), file=protocol, flush=True)


if __name__ == "__main__":
    main()
