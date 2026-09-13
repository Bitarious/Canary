"""Apply the declared first-pass stop and export the owned HDD run."""

from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "artifacts/tslm/full-history-rtx6000-v2"
SSH_CONFIG = ROOT / ".local/nebius/full-history-v1/ssh-rtx6000-config"
ALIAS = "driftops-nebius-rtx6000"
REMOTE = "/opt/driftops/work-v2/artifacts/tslm/full-history-rtx6000-v2"

INSPECT = r'''
from pathlib import Path
import json,os,signal,subprocess
root=Path('/opt/driftops/work-v2/artifacts/tslm/full-history-rtx6000-v2')
def read(name):
 p=root/name
 return json.loads(p.read_text()) if p.exists() else None
result,selection,progress=read('training-result.json'),read('selection.json'),read('progress.json')
request=read('first-pass-stop-request.json')
if result is None and request is None and selection and progress:
 if selection['epoch']>=1 and selection['validation_loss']<=0.01 and progress['completed_epochs']>=1:
  if selection['examples_seen']<11315069:
   raise ValueError('The selected checkpoint lacks the required full pass.')
  unit='driftops-full-history-rtx6000-v2.service'
  cgroup=subprocess.check_output(['systemctl','show',unit,'--property=ControlGroup','--value'],text=True).strip()
  if cgroup!='/system.slice/'+unit:
   raise ValueError('The owned training control group changed.')
  pids=[]
  for pid in (Path('/sys/fs/cgroup')/cgroup.lstrip('/')/'cgroup.procs').read_text().split():
   try: argv=(Path('/proc')/pid/'cmdline').read_bytes().decode().rstrip('\0').split('\0')
   except FileNotFoundError: continue
   if argv[1:4]==['-u','src/driftops/train_full.py','train'] and 'artifacts/tslm/full-history-rtx6000-v2' in argv:
    pids.append(int(pid))
  if len(pids)!=8:
   raise ValueError('The owned job does not have exactly eight verified training workers.')
  os.kill(min(pids),signal.SIGTERM)
  request={'worker_pid':min(pids),'selection':selection,'method':'SIGTERM to one verified worker. Distributed stop handling saves all ranks and returns normally.'}
  temporary=root/'first-pass-stop-request.json.part'
  temporary.write_text(json.dumps(request,indent=2)+'\n')
  temporary.replace(root/'first-pass-stop-request.json')
print(json.dumps({'terminal':result,'selection':selection,'progress':progress,'stop_request':request}))
'''


def remote(script):
    result = subprocess.run(["ssh", "-F", str(SSH_CONFIG), ALIAS, "python3", "-"],
                            input=script, text=True, capture_output=True, timeout=60, check=True)
    return json.loads(result.stdout)


def main():
    with (RUN / "completion-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        deadline = datetime.fromisoformat("2026-09-13T08:34:30+00:00")
        previous_step = None
        while datetime.now(timezone.utc) < deadline:
            state = remote(INSPECT)
            (RUN / "completion-controller-state.json").write_text(json.dumps(state, indent=2) + "\n")
            step = (state["progress"] or {}).get("steps")
            if step != previous_step or state["terminal"]:
                print(json.dumps({"checkpoint_step": step, "stop_requested": bool(state["stop_request"]),
                                  "terminal": bool(state["terminal"])}), flush=True)
                previous_step = step
            if state["terminal"]:
                if not state["terminal"]["full_data_training_complete"]:
                    raise ValueError("The HDD job ended without a complete data pass.")
                break
            time.sleep(15)
        else:
            raise TimeoutError("The HDD completion controller reached the provider deadline.")
        transport = "ssh -F " + shlex.quote(str(SSH_CONFIG))
        subprocess.run(["rsync", "-a", "--timeout=90", "--exclude=completion-controller*", "-e", transport,
                        f"{ALIAS}:{REMOTE}/", str(RUN) + "/"], check=True, timeout=240)
        hashes = remote("from pathlib import Path\nimport hashlib,json\nr=Path(" + repr(REMOTE) + ")\n"
                        "print(json.dumps({n:hashlib.file_digest((r/n).open('rb'),'sha256').hexdigest() "
                        "for n in ['best.pt','last.pt','selection.json','training-result.json']}))\n")
        for name, expected in hashes.items():
            with (RUN / name).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError("An exported HDD artifact checksum differs from the remote source.")
        selection = json.loads((RUN / "selection.json").read_text())
        if selection["sha256"] != hashes["best.pt"]:
            raise ValueError("The exported checkpoint differs from the selected checkpoint.")
        receipt = {"verified_at": datetime.now(timezone.utc).isoformat(), "sha256": hashes,
                   "full_data_training_complete": True, "provider_stop_confirmation_pending": True}
        (RUN / "terminal-export.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
