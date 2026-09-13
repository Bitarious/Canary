#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
uv sync --locked --extra model-access --extra training
uv run --no-sync driftops prepare
uv run --no-sync pytest -q
python3 -m unittest discover -s driftops3d/tests -p 'test_*.py' -v
uv run --no-sync python scripts/check_release.py
