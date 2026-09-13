#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2; exit 1; }
command -v entire >/dev/null || { echo 'Entire is required for submission. Install it before development: https://docs.entire.io/installation' >&2; exit 1; }
entire enable --agent codex --local
entire status
uv sync --locked --extra model-access --extra training
uv run --no-sync driftops prepare
uv run --no-sync pytest -q
echo 'Pilot verified. Run: uv run --no-sync driftops demo'
echo 'Before starting Codex overnight, review its /hooks screen and confirm Entire hooks are trusted.'
