#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
uv sync --locked --extra model-access
uv run --no-sync driftops prepare
uv run --no-sync pytest -q
