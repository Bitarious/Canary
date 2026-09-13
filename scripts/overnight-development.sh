#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
command -v codex >/dev/null || { echo 'Install and sign in to Codex first.' >&2; exit 1; }
command -v uv >/dev/null || { echo 'Run the bootstrap first.' >&2; exit 1; }
mkdir -p artifacts/development
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
echo "Starting one resumable development session; output: artifacts/development/${run_id}.*"
# Preserve the normal approval and sandbox policies.
codex exec --sandbox workspace-write --json \
  --output-last-message "artifacts/development/${run_id}.summary.md" - \
  < docs/overnight-task.md \
  > "artifacts/development/${run_id}.events.jsonl" \
  2> "artifacts/development/${run_id}.stderr.log"
