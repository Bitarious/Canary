"""Allow a bounded export grace period, then invoke the unchanged provider stop guard."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


INSTANCE = "computeinstance-e05xkzn36ahww4gphc"
RECEIPTS = (
    Path("/opt/driftops/components-v4/phase/export-complete.json"),
    Path("/opt/driftops/components-v3/phase/followup-export-complete.json"),
)


def wait_seconds(config, now):
    deadline = datetime.fromisoformat(config["deadline_utc"])
    if config["instance_id"] != INSTANCE or deadline.utcoffset() is None:
        raise ValueError("The export grace period does not match the guarded instance.")
    return max(0., min(900., (deadline - now).total_seconds() - 75.))


def await_exports(receipts, limit, *, monotonic=time.monotonic, sleep=time.sleep):
    end = monotonic() + limit
    while not all(path.is_file() for path in receipts):
        remaining = end - monotonic()
        if remaining <= 0:
            return False
        sleep(min(5., remaining))
    return True


def main():
    try:
        config = json.loads(Path("/opt/driftops/guard.json").read_text())
        seconds = wait_seconds(config, datetime.now(timezone.utc))
        complete = await_exports(RECEIPTS, seconds)
        print(json.dumps({"export_grace_seconds_cap": seconds, "supplementary_exports_complete": complete}), flush=True)
    finally:
        # Malformed state and missing receipts still lead to the provider stop.
        subprocess.run(["/usr/bin/python3", "/opt/driftops/nebius_job_guard.py", "--stop-now"],
                       check=True, timeout=75)


if __name__ == "__main__":
    main()
