#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2; exit 1; }
uv sync --locked --extra model-access --extra training
uv run --no-sync driftops prepare
uv run --no-sync pytest -q
echo 'Pilot verified. Run: uv run --no-sync driftops demo'
