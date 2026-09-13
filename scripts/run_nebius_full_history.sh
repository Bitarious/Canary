#!/usr/bin/env bash
# Run the declared diagnostic and full training from the frozen RTX source directory.
set -euo pipefail

export HF_HOME=/opt/driftops/cache/huggingface
export HF_HUB_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=8

cd /opt/driftops/work
export PYTHONPATH=/opt/driftops/work/src
.venv/bin/python - <<'PY'
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

root = Path.cwd().resolve()
guard = json.loads(Path('/opt/driftops/guard.json').read_text())
if datetime.now(timezone.utc) >= datetime.fromisoformat(guard['deadline_utc']):
    raise ValueError('The provider stop deadline has passed')
run = root / 'artifacts/tslm/gpu-rtx6000-check-v1'
if (run / 'started.json').exists():
    raise ValueError('The diagnostic already started. Review its artifacts before a new launch')
for name, digest in json.loads((run / 'source-hashes.json').read_text()).items():
    source = (root / name).resolve()
    if not source.is_relative_to(root) or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError('The diagnostic source checksum is incorrect')
PY

timeout --signal=TERM --kill-after=30s 1800s \
  .venv/bin/torchrun --standalone --nnodes=1 --nproc-per-node=8 -- \
  scripts/gpu_runtime_check.py --run artifacts/tslm/gpu-rtx6000-check-v1

.venv/bin/python - <<'PY'
import hashlib
import json
from pathlib import Path

run = Path('artifacts/tslm/gpu-rtx6000-check-v1')
result = json.loads((run / 'result.json').read_text())
if result.get('passed') is not True or result.get('gpu_count') != 8 or result.get('steps') != 16:
    raise ValueError('The parallel diagnostic did not pass')
if hashlib.sha256((run / 'diagnostic.pt').read_bytes()).hexdigest() != result['checkpoint_sha256']:
    raise ValueError('The diagnostic checkpoint checksum is incorrect')
PY

/opt/driftops/work/.venv/bin/torchrun --standalone --nnodes=1 --nproc-per-node=8 -- \
  src/driftops/train_full.py train --run artifacts/tslm/full-history-rtx6000-v1

# Allow the controller to export the final artifacts. The unit stops the VM on exit.
sleep 300
