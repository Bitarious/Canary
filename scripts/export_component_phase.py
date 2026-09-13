"""Export completed component weights, release frozen tests, and verify results."""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

from driftops.evaluate_component import freeze


ROOT = Path(__file__).resolve().parents[1]
SSH = ROOT / ".local/nebius/full-history-v1/ssh-rtx6000-config"
ALIAS = "driftops-nebius-rtx6000"


def remote(script):
    result = subprocess.run(["ssh", "-F", str(SSH), ALIAS, "python3", "-"],
                            input=script, capture_output=True, text=True, check=True, timeout=60)
    return json.loads(result.stdout)


def transfer(source, target, names=None):
    command = ["rsync", "-a", "--timeout=90", "-e", "ssh -F " + shlex.quote(str(SSH))]
    if names is not None:
        command.append("--files-from=-")
    subprocess.run([*command, source, target], input=None if names is None else "\n".join(names) + "\n",
                   text=True, check=True, timeout=300)


def inspect(jobs):
    return remote("from pathlib import Path\nimport json\njobs=" + repr(jobs) + "\nresult={}\n"
        "for job in jobs:\n r=Path(job['run'])\n result[job['name']]={name:json.loads((r/name).read_text()) "
        "if (r/name).exists() else None for name in ['training-ready.json','component-terminal.json']}\nprint(json.dumps(result))\n")


def verify_export(run, remote_run):
    hashes = remote("from pathlib import Path\nimport json,hashlib\nr=Path(" + repr(remote_run) + ")\n"
        "print(json.dumps({str(p.relative_to(r)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() "
        "for p in r.rglob('*') if p.is_file() and p.suffix in ('.json','.pt')}))\n")
    for name, digest in hashes.items():
        path = (run / name).resolve()
        if not path.is_relative_to(run.resolve()) or hashlib.file_digest(path.open("rb"), "sha256").hexdigest() != digest:
            raise ValueError("An exported component artifact checksum is incorrect.")
    return hashes


def main(manifest_path):
    phase = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    jobs = manifest["jobs"]
    remote_source = manifest.get("source_root", "/opt/driftops/components-v1")
    if not re.fullmatch(r"/opt/driftops/components-v[1-9][0-9]*", remote_source):
        raise ValueError("The component source path is outside the owned phases.")
    for job in jobs:
        name = job["name"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,70}", name):
            raise ValueError("A component export name is invalid.")
        if job["run"] != remote_source + "/artifacts/tslm/" + name:
            raise ValueError("A component export path is outside the owned phase.")
    deadline = datetime.fromisoformat(json.loads((phase / "budget.json").read_text())["deadline_utc"])
    with (phase / "export-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while datetime.now(timezone.utc) < deadline:
            states = inspect(jobs)
            complete = 0
            for job in jobs:
                name, remote_run = job["name"], job["run"]
                run = ROOT / "artifacts/tslm" / name
                state = states[name]
                if state["training-ready.json"] and not (run / "test-release-transfer.json").exists():
                    transfer(f"{ALIAS}:{remote_run}/", str(run) + "/", ["best.pt", "selection.json", "training-result.json"])
                    digest = hashlib.file_digest((run / "best.pt").open("rb"), "sha256").hexdigest()
                    if digest != state["training-ready.json"]["selection"]["sha256"]:
                        raise ValueError("The exported component checkpoint differs from its selection.")
                    config = json.loads((run / "config.json").read_text())
                    if config.get("evaluation_kind") in ("small-industrial-v1", "slider-audio-benchmark-v1", "valve-audio-benchmark-v1"):
                        from driftops.evaluate_industrial import freeze as freeze_industrial
                        freeze_industrial(ROOT / "data/components" / name, run,
                                          audio_benchmark=config.get("evaluation_kind") in ("slider-audio-benchmark-v1", "valve-audio-benchmark-v1"))
                    else:
                        freeze(ROOT / "data/components" / name, run)
                    transfer(str(run) + "/", f"{ALIAS}:{remote_run}/", ["evaluation/protocol.json", "evaluation/test.json"])
                    transfer(str(run) + "/", f"{ALIAS}:{remote_run}/", ["test-release.json"])
                    (run / "test-release-transfer.json").write_text(json.dumps({"transferred_at": datetime.now(timezone.utc).isoformat(), "checkpoint_sha256": digest}) + "\n")
                    print(json.dumps({"component": name, "frozen_test_released": True}), flush=True)
                if state["component-terminal.json"]:
                    if not (run / "component-export.json").exists():
                        transfer(f"{ALIAS}:{remote_run}/", str(run) + "/")
                        hashes = verify_export(run, remote_run)
                        (run / "component-export.json").write_text(json.dumps({"verified_at": datetime.now(timezone.utc).isoformat(),
                            "sha256": hashes, "terminal": state["component-terminal.json"]}, indent=2) + "\n")
                        print(json.dumps({"component": name, "export_verified": True, **state["component-terminal.json"]}), flush=True)
                    complete += 1
            if complete == len(jobs):
                receipt = {"verified_at": datetime.now(timezone.utc).isoformat(), "components": complete}
                (phase / "export-complete.json").write_text(json.dumps(receipt, indent=2) + "\n")
                transfer(str(phase) + "/", f"{ALIAS}:{remote_source}/phase/", ["export-complete.json"])
                return
            # Failed jobs remain explicit. The parent can inspect and export their error records.
            time.sleep(15)
    raise TimeoutError("The component export controller reached the provider deadline.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    main(parser.parse_args().manifest)
