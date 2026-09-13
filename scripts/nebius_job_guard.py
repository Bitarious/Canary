#!/usr/bin/env python3
"""Stop this job's VM through the provider API at its absolute deadline."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.request import Request, urlopen


def should_stop(config, now):
    deadline = datetime.fromisoformat(config["deadline_utc"])
    if deadline.tzinfo is None:
        raise ValueError("The VM deadline must include a time zone")
    return now >= deadline


def get_instance_id(metadata_path=Path("/mnt/cloud-metadata/instance-id"), opener=urlopen):
    if metadata_path.is_file():
        instance = metadata_path.read_text().strip()
    else:
        request = Request("http://metadata.nebius.internal/v1/instance-data/id", headers={"Metadata": "true"})
        with opener(request, timeout=5) as response:
            instance = response.read(256).decode("ascii").strip()
    if not re.fullmatch(r"computeinstance-[a-z0-9]{1,64}", instance):
        raise ValueError("The metadata instance identifier is invalid")
    return instance


def stop_vm(config, instance_id, runner=subprocess.run):
    if not re.fullmatch(r"computeinstance-[a-z0-9]+", instance_id):
        raise ValueError("The instance identifier is invalid")
    if instance_id != config["instance_id"]:
        raise ValueError("The metadata instance does not match this job")
    result = runner([config.get("cli", "nebius"), "--timeout", "30s", "--retries", "2",
                     "compute", "instance", "stop", "--async", "--id", instance_id, "--format", "json"],
                    capture_output=True, text=True, timeout=70)
    if result.returncode:
        raise RuntimeError("The stop command failed. Check the provider state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/opt/driftops/guard.json"))
    parser.add_argument("--stop-now", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    now = datetime.now(timezone.utc)
    instance = get_instance_id()
    if args.stop_now or should_stop(config, now):
        stop_vm(config, instance)
        print(json.dumps({"stop_requested_at": now.isoformat(), "instance_id": instance}), flush=True)
    else:
        print(json.dumps({"armed": True, "deadline_utc": config["deadline_utc"], "checked_at": now.isoformat()}), flush=True)


if __name__ == "__main__":
    main()
