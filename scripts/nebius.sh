#!/usr/bin/env bash
set -euo pipefail
exec nebius --profile "${DRIFTOPS_NEBIUS_PROFILE:-driftops}" "$@"
