#!/usr/bin/env python3
"""Create the bounded RTX PRO 6000 fallback after H200 capacity failures."""

from datetime import datetime, timezone
import json
from pathlib import Path

import nebius_provision as provider


def main():
    root = Path("artifacts/nebius/full-history-v1")
    for directory in (root, root / "parallel"):
        resource = json.loads((directory / "resources.json").read_text())
        state = provider.call(["compute", "instance", "get", "--id", resource["instance_id"]])
        if state["status"]["state"] != "STOPPED":
            raise ValueError("Stop both H200 VMs before provisioning the fallback")
    provider.ARTIFACTS = root / "rtx6000"
    provider.PROJECT = "project-e05ht2wqln00tc7zj5swv7"
    provider.JOB = "driftops-full-history-v1-rtx6000"
    budget = json.loads((provider.ARTIFACTS / "vm-budget.json").read_text())
    if budget["quoted_max_usd"] > 116 or datetime.now(timezone.utc) >= datetime.fromisoformat(budget["deadline_utc"]):
        raise ValueError("The RTX fallback budget is invalid or expired")
    provider.provision()


if __name__ == "__main__":
    main()
