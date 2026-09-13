#!/usr/bin/env python3
"""Prepare a reviewable, stopped H200 VM specification for the historical training job."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

import yaml

PROJECT = "project-e00r5nydpr005rwf6beg1y"
SUBNET = "vpcsubnet-e00bhmp6s4akmam7bg"
IMAGE = "computeimage-e00kfme85bq2nnnppw"
JOB = "driftops-full-history-v1"


def prepare():
    if Path("artifacts/nebius/full-history-v1/compute-instance.json").exists():
        raise ValueError("The VM already exists. Preserve its original deadline and specification")
    local = Path(".local/nebius/full-history-v1")
    local.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = local / "id_ed25519"
    if not key.exists():
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", JOB, "-f", str(key)], check=True, capture_output=True)
    public_key = key.with_suffix(".pub").read_text().strip()
    deadline = datetime.now(timezone.utc) + timedelta(hours=96)
    guard_config = {"deadline_utc": deadline.isoformat(), "instance_id": "FROM_CLOUD_METADATA", "cli": "/usr/bin/nebius"}
    setup = """from pathlib import Path
import json,shutil,re,runpy
p=Path('/opt/driftops/guard.json')
c=json.loads(p.read_text())
c['instance_id']=runpy.run_path('/opt/driftops/nebius_job_guard.py')['get_instance_id']()
assert re.fullmatch(r'computeinstance-[a-z0-9]+',c['instance_id'])
c['cli']=shutil.which('nebius')
assert c['cli'], 'Nebius CLI is missing'
p.write_text(json.dumps(c))
"""
    cloud_init = {"users": [{"name": "driftops", "shell": "/bin/bash", "lock_passwd": True,
                   "groups": ["sudo"], "sudo": ["ALL=(ALL) NOPASSWD:ALL"], "ssh_authorized_keys": [public_key]}],
        "ssh_pwauth": False,
        "write_files": [
            {"path": "/opt/driftops/nebius_job_guard.py", "permissions": "0755", "content": Path("scripts/nebius_job_guard.py").read_text()},
            {"path": "/opt/driftops/guard.json", "permissions": "0644", "content": json.dumps(guard_config)},
            {"path": "/opt/driftops/setup_guard.py", "permissions": "0644", "content": setup},
            {"path": "/etc/systemd/system/driftops-deadline.service", "content": "[Unit]\nDescription=Stop the DriftOps VM at its spending deadline\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /opt/driftops/nebius_job_guard.py\nTimeoutStartSec=90\n"},
            {"path": "/etc/systemd/system/driftops-deadline.timer", "content": "[Unit]\nDescription=Check the DriftOps VM deadline\n[Timer]\nOnBootSec=20s\nOnUnitActiveSec=60s\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n"}],
        "runcmd": [["python3", "/opt/driftops/setup_guard.py"], ["systemctl", "daemon-reload"],
                   ["systemctl", "enable", "--now", "driftops-deadline.timer"],
                   ["mkdir", "-p", "/opt/driftops/work", "/opt/driftops/cache"],
                   ["chown", "-R", "driftops:driftops", "/opt/driftops/work", "/opt/driftops/cache"]]}
    spec = {"metadata": {"name": JOB, "parent_id": PROJECT, "labels": {"driftops-job": JOB}},
            "spec": {"stopped": True, "recovery_policy": "FAIL", "cloud_init_user_data": "#cloud-config\n" + yaml.safe_dump(cloud_init),
                     "resources": {"platform": "gpu-h200-sxm", "preset": "1gpu-16vcpu-200gb"},
                     "boot_disk": {"attach_mode": "READ_WRITE", "managed_disk": {"name": JOB + "-boot",
                         "spec": {"type": "NETWORK_SSD", "size_gibibytes": 128, "source_image_id": IMAGE}}},
                     "network_interfaces": [{"name": "eth0", "subnet_id": SUBNET, "ip_address": {}, "public_ip_address": {}}]}}
    output = Path("artifacts/nebius/full-history-v1")
    output.mkdir(parents=True, exist_ok=True)
    (output / "vm-spec.json").write_text(json.dumps(spec, indent=2)+"\n")
    (output / "vm-budget.json").write_text(json.dumps({"job": JOB, "created_at": datetime.now(timezone.utc).isoformat(),
        "deadline_utc": deadline.isoformat(), "max_vm_hours": 96, "vm_hourly_usd": 4.5, "disk_hourly_usd": .012444416,
        "quoted_max_usd": 96*(4.5+.012444416), "project_ceiling_usd": 600,
        "stop_method": "Provider API from the VM with resource-scoped power-operator permission, plus a controller stop timer.",
        "cleanup": "Export and verify model artifacts, delete this VM and its managed disk, then remove its service-account resources."}, indent=2)+"\n")
    print("Prepared stopped-VM specification and budget. No cloud resources were created.")


if __name__ == "__main__":
    prepare()
