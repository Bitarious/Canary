#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
command -v codex >/dev/null || { echo 'Install and sign in to Codex first.' >&2; exit 1; }
command -v entire >/dev/null || { echo 'Entire is required; install and enable it before this run.' >&2; exit 1; }
command -v uv >/dev/null || { echo 'Run the bootstrap first.' >&2; exit 1; }
entire status
entire status --json | uv run --no-sync python -c 'import json,sys; state=json.load(sys.stdin); sys.exit(0 if state.get("enabled") and "Codex" in state.get("agents", []) else "Entire Codex recording must be enabled before unattended work.")'
mkdir -p artifacts/development
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
echo "Starting one resumable development session; output: artifacts/development/${run_id}.*"
# Keep the normal Codex configuration, permissions, and Entire hooks. Do not use
# ephemeral mode or bypass approval/sandbox policies to force overnight progress.
codex exec --sandbox workspace-write --json \
  --output-last-message "artifacts/development/${run_id}.summary.md" - \
  < docs/overnight-task.md \
  > "artifacts/development/${run_id}.events.jsonl" \
  2> "artifacts/development/${run_id}.stderr.log"
