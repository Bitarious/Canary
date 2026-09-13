"""Run independent component jobs under one bounded VM phase."""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def validate(manifest, source):
    jobs = manifest["jobs"]
    sharing = manifest.get("shared_gpu") == 7
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 8:
        raise ValueError("A component phase requires one to eight jobs.")
    if sharing and (len(jobs) > 4 or any(job["gpu"] != 7 for job in jobs)):
        raise ValueError("Small industrial jobs can share only the unused eighth GPU, with at most four processes.")
    names, gpus, runs = set(), set(), set()
    for job in jobs:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,70}", job["name"]):
            raise ValueError("A component job name is invalid.")
        gpu = job["gpu"]
        run, root = Path(job["run"]).resolve(), Path(job["data_root"]).resolve()
        if type(gpu) is not int or not 0 <= gpu < 8:
            raise ValueError("A component GPU assignment is invalid.")
        if job["name"] in names or (gpu in gpus and not sharing) or run in runs:
            raise ValueError("Component jobs must have separate names, GPUs, and run directories.")
        if not run.is_relative_to(source / "artifacts/tslm") or not root.is_dir():
            raise ValueError("A component job has an invalid run or data directory.")
        names.add(job["name"])
        gpus.add(gpu)
        runs.add(run)
        for name in ("overview.json", "config.json", "hdd-gate.json", "dataset-manifest.json", "source-hashes.json"):
            if not (run / name).is_file():
                raise ValueError("A component run lacks its preparation artifacts.")
        gate = json.loads((run / "hdd-gate.json").read_text())
        if gate["success_gate"]["passed"] is not True or gate["reload_predictions_equal"] != 16:
            raise ValueError("A component run lacks a passing HDD gate.")
        config = json.loads((run / "config.json").read_text())
        if sharing and config.get("evaluation_kind") != "small-industrial-v1":
            raise ValueError("GPU sharing is restricted to the declared small industrial studies.")
        if config["world_size"] != 1 or not 0 < config["max_train_hours"] <= 2:
            raise ValueError("A component run exceeds the phase training bounds.")
        for name, digest in json.loads((run / "source-hashes.json").read_text()).items():
            path = (source / name).resolve()
            if not path.is_relative_to(source) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("A component source checksum changed.")
        if (run / "hardware.json").exists() or (run / "test-release.json").exists():
            raise ValueError("A component run already started. Review it before another phase.")
    return jobs


def command(job, stage):
    if stage == "training":
        return [sys.executable, "-m", "driftops.component_training", "train",
                "--root", job["data_root"], "--run", job["run"]]
    config = json.loads((Path(job["run"]) / "config.json").read_text())
    kind = config.get("evaluation_kind")
    audio = kind in ("slider-audio-benchmark-v1", "valve-audio-benchmark-v1")
    module = "driftops.evaluate_industrial" if kind == "small-industrial-v1" or audio else "driftops.evaluate_component"
    return [sys.executable, "-m", module, "evaluate", "--run", job["run"],
            *(["--audio-benchmark"] if audio else [])]


def supervise(jobs, phase, command_builder=command, interval=2, phase_seconds=12000, release_seconds=900):
    states, children, logs = {}, {}, []
    started = time.monotonic()

    def launch(job, stage):
        log = (Path(job["run"]) / f"{stage}-process.log").open("a")
        logs.append(log)
        children[job["name"]] = subprocess.Popen(command_builder(job, stage), stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": str(job["gpu"]), "PYTHONUNBUFFERED": "1"})
        states[job["name"]] = {"stage": stage, "stage_started": time.monotonic()}

    def cancel(*_):
        raise InterruptedError("The component phase was canceled.")

    previous = {sig: signal.signal(sig, cancel) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for job in jobs:
            launch(job, "training")
        while True:
            if time.monotonic() - started >= phase_seconds:
                raise TimeoutError("The component phase reached its time limit.")
            for job in jobs:
                name, run = job["name"], Path(job["run"])
                state = states[name]
                if state["stage"] in ("complete", "failed"):
                    continue
                if state["stage"] == "awaiting_test_release":
                    if (run / "test-release.json").is_file():
                        launch(job, "evaluation")
                    elif time.monotonic() - state["stage_started"] > release_seconds:
                        states[name] = {"stage": "failed", "reason": "test_release_timeout"}
                    continue
                child = children[name]
                code = child.poll()
                if code is None:
                    limit = 7350 if state["stage"] == "training" else 3660
                    if time.monotonic() - state["stage_started"] > limit:
                        raise TimeoutError("A component process exceeded its stage limit.")
                    continue
                if code != 0:
                    states[name] = {"stage": "failed", "reason": state["stage"] + "_exit", "exit_code": code}
                    continue
                if state["stage"] == "training":
                    result = json.loads((run / "training-result.json").read_text())
                    if not result["full_data_training_complete"]:
                        states[name] = {"stage": "failed", "reason": "incomplete_training_pass"}
                        continue
                    states[name] = {"stage": "awaiting_test_release", "stage_started": time.monotonic()}
                    write(run / "training-ready.json", {"training_process_exit_code": 0,
                          "selection": json.loads((run / "selection.json").read_text())})
                else:
                    report = json.loads((run / "evaluation/metrics.json").read_text())
                    states[name] = {"stage": "complete", "gate_passed": report["success_gate"]["passed"],
                                    "reload_predictions_equal": report["reload_predictions_equal"]}
                    write(run / "component-terminal.json", states[name])
            write(phase / "progress.json", states)
            if all(s["stage"] in ("complete", "failed") for s in states.values()):
                write(phase / "result.json", {"jobs": states, "seconds": time.monotonic() - started})
                return states
            time.sleep(interval)
    finally:
        for child in children.values():
            if child.poll() is None:
                child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=60)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
        for log in logs:
            log.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(path):
    phase, source = path.resolve().parent, Path.cwd().resolve()
    manifest = json.loads(path.read_text())
    guard = json.loads(Path("/opt/driftops/guard.json").read_text())
    deadline = datetime.fromisoformat(guard["deadline_utc"])
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    audio = manifest.get("study") in ("slider-audio-benchmark-v1", "valve-audio-benchmark-v1")
    minimum_remaining = 5400 if manifest.get("shared_gpu") == 7 or audio else 10800
    if guard["instance_id"] != manifest["instance_id"] or not minimum_remaining < remaining <= 12600:
        raise ValueError("The component phase lacks its declared VM deadline.")
    jobs = validate(manifest, source)
    if audio:
        if len(jobs) != 1 or json.loads((Path(jobs[0]["run"]) / "config.json").read_text()).get("evaluation_kind") != manifest["study"]:
            raise ValueError("The supplementary sound phase requires one declared audio benchmark.")
        usage = subprocess.check_output(["nvidia-smi", f"--id={jobs[0]['gpu']}", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True, timeout=10)
        if int(usage.strip()) > 256:
            raise ValueError("The assigned sound GPU is occupied.")
    if manifest.get("shared_gpu") == 7:
        usage = subprocess.check_output(["nvidia-smi", "--id=7", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], text=True, timeout=10)
        used, total = [int(value.strip()) for value in usage.split(",")]
        if used > 256 or total < 90000:
            raise ValueError("The eighth GPU is occupied or lacks the declared memory capacity.")
    with (phase / "phase.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (phase / "started.json").open("x") as stream:
            json.dump({"started_at": datetime.now(timezone.utc).isoformat(), "deadline_utc": guard["deadline_utc"]}, stream)
        seconds = 5400 if manifest.get("shared_gpu") == 7 or audio else 12000
        supervise(jobs, phase, phase_seconds=min(seconds, remaining - 300))
        # The owning service stops the provider after this bounded export interval.
        end = time.monotonic() + 300
        while time.monotonic() < end and not (phase / "export-complete.json").is_file():
            time.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    main(parser.parse_args().manifest)
