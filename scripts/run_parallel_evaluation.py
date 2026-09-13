"""Generate frozen HDD comparisons on separate GPUs, then verify and score them."""

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def run_evaluation(run):
    processes, logs = [], []
    modes = ("starting", "finetuned", "zero_numerical_embeddings", "reversed", "shuffled")
    started = time.monotonic()

    def cancel(*_):
        raise InterruptedError("Parallel evaluation was canceled.")

    previous = {sig: signal.signal(sig, cancel) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for gpu, mode in enumerate(modes):
            log = (run / "evaluation" / f"{mode}-process.log").open("a")
            logs.append(log)
            environment = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "PYTHONUNBUFFERED": "1"}
            processes.append(subprocess.Popen([sys.executable, "-m", "driftops.evaluate_full", "comparison",
                "--run", str(run), "--comparison", mode], env=environment, stdout=log, stderr=subprocess.STDOUT))
        while any(p.poll() is None for p in processes):
            failed = [modes[i] for i, p in enumerate(processes) if p.poll() not in (None, 0)]
            if failed:
                raise RuntimeError("Evaluation comparison failed: " + ", ".join(failed))
            if time.monotonic() - started >= 7100:
                raise TimeoutError("Parallel evaluation reached its phase limit.")
            time.sleep(2)
        if any(p.returncode != 0 for p in processes):
            raise RuntimeError("An evaluation comparison failed.")
        subprocess.run([sys.executable, "-m", "driftops.evaluate_full", "evaluate", "--run", str(run)],
                       env={**os.environ, "CUDA_VISIBLE_DEVICES": "0"}, check=True,
                       timeout=max(1, 7200 - (time.monotonic() - started)))
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=10)
        for log in logs:
            log.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    run_evaluation(args.run)
