#!/usr/bin/env python3
"""Create only this job's stopped VM and a resource-scoped stop service account."""

import fcntl
import json
from pathlib import Path
import subprocess

from prepare_nebius_spec import JOB, PROJECT

ARTIFACTS = Path("artifacts/nebius/full-history-v1")


def call(args, not_found=False, spec=None):
    command = ["bash", "scripts/nebius.sh", "--timeout", "180s", "--per-retry-timeout", "30s", "--retries", "2", *args, "--format", "json"]
    if spec is not None:
        path = ARTIFACTS / "resource-request.json"
        path.write_text(json.dumps(spec, indent=2)+"\n")
        command.extend(["--file", str(path)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    if result.returncode:
        if not_found and any(marker in result.stderr.lower() for marker in ("not found", "not_found", "code = notfound")):
            return None
        raise RuntimeError(result.stderr[-2500:])
    return json.loads(result.stdout)


def ensure(kind, name, spec=None):
    resource = call([*kind, "get-by-name", "--parent-id", PROJECT, "--name", name], not_found=True)
    if resource is None:
        body = spec or {"metadata": {"parent_id": PROJECT, "name": name, "labels": {"driftops-job": JOB}}}
        resource = call([*kind, "create"], spec=body)
    metadata = resource["metadata"]
    if metadata["parent_id"] != PROJECT or metadata.get("labels", {}).get("driftops-job") != JOB:
        raise ValueError("An existing resource with this name does not belong to the job")
    (ARTIFACTS / ("-".join(kind) + ".json")).write_text(json.dumps(resource, indent=2)+"\n")
    return metadata["id"]


def provision():
    budget = json.loads((ARTIFACTS / "vm-budget.json").read_text())
    if budget["quoted_max_usd"] > 450 or budget["project_ceiling_usd"] != 600:
        raise ValueError("VM specification exceeds the reviewed job budget")
    with (ARTIFACTS / "provision.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        account = ensure(["iam", "service-account"], JOB + "-stopper")
        group = ensure(["iam", "group"], JOB + "-power")
        members = call(["iam", "group-membership", "list-members", "--parent-id", group]).get("memberships", [])
        if any(m["spec"]["member_id"] != account for m in members):
            raise ValueError("The job's stop group has an unexpected member")
        if not any(m["spec"]["member_id"] == account for m in members):
            membership = call(["iam", "group-membership", "create", "--parent-id", group, "--member-id", account])
            (ARTIFACTS / "iam-membership.json").write_text(json.dumps(membership, indent=2)+"\n")
        spec = json.loads((ARTIFACTS / "vm-spec.json").read_text())
        spec["spec"]["service_account_id"] = account
        if spec["spec"]["stopped"] is not True:
            raise ValueError("Provisioning must create a stopped VM")
        instance = ensure(["compute", "instance"], JOB, spec)
        permits = call(["iam", "access-permit", "list", "--parent-id", group]).get("items", [])
        expected = {"resource_id": instance, "role": "compute.instance-power-operator"}
        if any(p["spec"] != expected for p in permits):
            raise ValueError("The job's stop group has an unexpected access permit")
        if not permits:
            permit = call(["iam", "access-permit", "create", "--parent-id", group,
                           "--resource-id", instance, "--role", expected["role"]])
            (ARTIFACTS / "iam-permit.json").write_text(json.dumps(permit, indent=2)+"\n")
        state = {"instance_id": instance, "service_account_id": account, "group_id": group,
                 "job": JOB, "project_id": PROJECT, "started": False, "budget": budget}
        (ARTIFACTS / "resources.json").write_text(json.dumps(state, indent=2)+"\n")
        print(json.dumps({"instance_id": instance, "stopped": True, "stop_permission_scope": instance}), flush=True)


if __name__ == "__main__":
    provision()
