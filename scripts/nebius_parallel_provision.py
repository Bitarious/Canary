#!/usr/bin/env python3
"""Create the approved eight-H200 job VM with the earlier spending deadline."""

from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path

import yaml

import nebius_provision as provider


def provision():
    root = Path("artifacts/nebius/full-history-v1")
    original = json.loads((root / "resources.json").read_text())
    budget = json.loads((root / "eight-gpu-budget.json").read_text())
    if budget["quoted_max_usd"] > 365 or budget["project_ceiling_usd"] != 600:
        raise ValueError("The parallel VM exceeds the reviewed budget")
    if datetime.now(timezone.utc) >= datetime.fromisoformat(budget["deadline_utc"]):
        raise ValueError("The job deadline has passed")
    output = root / "parallel"
    output.mkdir(exist_ok=True)
    provider.ARTIFACTS = output
    with (output / "provision.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior = provider.call(["compute", "instance", "get", "--id", original["instance_id"]])
        if prior["status"]["state"] != "STOPPED":
            raise ValueError("Stop the original VM before provisioning parallel compute")
        spec = json.loads((root / "vm-spec.json").read_text())
        spec["metadata"]["name"] = provider.JOB + "-parallel"
        spec["spec"]["resources"]["preset"] = "8gpu-128vcpu-1600gb"
        spec["spec"]["boot_disk"]["managed_disk"]["name"] = provider.JOB + "-parallel-boot"
        spec["spec"]["service_account_id"] = original["service_account_id"]
        init = yaml.safe_load(spec["spec"]["cloud_init_user_data"])
        for item in init["write_files"]:
            if item["path"] == "/opt/driftops/nebius_job_guard.py":
                item["content"] = Path("scripts/nebius_job_guard.py").read_text()
            elif item["path"] == "/opt/driftops/guard.json":
                item["content"] = json.dumps({"deadline_utc": budget["deadline_utc"],
                                              "instance_id": "FROM_CLOUD_METADATA", "cli": "/usr/local/bin/nebius"})
        spec["spec"]["cloud_init_user_data"] = "#cloud-config\n" + yaml.safe_dump(init)
        (output / "vm-spec.json").write_text(json.dumps(spec, indent=2) + "\n")
        instance = provider.ensure(["compute", "instance"], spec["metadata"]["name"], spec)
        group = original["group_id"]
        permits = provider.call(["iam", "access-permit", "list", "--parent-id", group]).get("items", [])
        allowed = [{"resource_id": identifier, "role": "compute.instance-power-operator"}
                   for identifier in (original["instance_id"], instance)]
        if any(permit["spec"] not in allowed for permit in permits):
            raise ValueError("The job's stop group has an unexpected permission")
        if not any(permit["spec"] == allowed[1] for permit in permits):
            permit = provider.call(["iam", "access-permit", "create", "--parent-id", group,
                                    "--resource-id", instance, "--role", "compute.instance-power-operator"])
            (output / "iam-permit.json").write_text(json.dumps(permit, indent=2) + "\n")
        state = {**original, "instance_id": instance, "job": spec["metadata"]["name"],
                 "original_instance_id": original["instance_id"], "budget": budget, "started": False}
        (output / "resources.json").write_text(json.dumps(state, indent=2) + "\n")
        print(json.dumps({"instance_id": instance, "stopped": True, "deadline_utc": budget["deadline_utc"]}), flush=True)


if __name__ == "__main__":
    provision()
