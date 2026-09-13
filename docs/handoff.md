# Canary development handoff

## Current source and scope

The user identified this machine's working code as the good version after a potentially unwanted teammate push. The local demo and presentation were secured in commit `bd87b0c` on `release/canary-v0.1.0`. That commit preserves the saved HDD evidence view and removes the active Entire integration.

Remote main was inspected at `d5b67fd`. Its two additional commits add benchmark collection and live component-model inference. Their code is excluded from the verified local demo. The release merge retains both commits in normal Git ancestry while preserving the local release content.

Canary contains a real Backblaze data pipeline, separate component models, and a saved-evidence inspection view. Its separate 3D fleet uses synthetic telemetry and rules. Neither browser application runs fresh trained-model inference. See [the current architecture](architecture.md).

## Experiment results

Thirteen component categories passed their declared signal-description gates. The full-history HDD model completed 11,315,069 eligible training windows. Its held-out result is 99.68% channel accuracy on 2,048 unseen drives and 6,777 weak labels. The constant baseline scored 69.43%; zero numerical input scored 86.01%.

The initial CPU concept failed useful numerical dependence. The dated radiator-valve model failed both its original evaluation and an unchanged-weight follow-up. The independent industrial-valve sound model passed its separate unknown-date study. Preserve all failures and study boundaries.

Selected checkpoints and evaluation artifacts retain their recorded hashes. See [component results](component-model-results.md), [versioned evidence](../results/2026-09-13/README.md), and [model terms](model-licenses.md). The final historical cost ledger estimated $111.35 under the original $600 ceiling. It is not a current account balance.

## Setup and verification

```bash
bash scripts/bootstrap.sh
bash scripts/verify.sh
npm ci
npx playwright install chromium
npm run test:browser
```

The bootstrap and verification need Python 3.12 or newer and `uv`. Browser verification needs Node 22 or newer. The browser harness starts and stops its own server and browser. Use an appropriate `TMPDIR` for local temporary files.

```bash
python3 driftops3d/server.py --host 127.0.0.1 --port 8765
uv run --no-sync driftops demo
```

The Canary demo uses port 8765. The real-data preview uses port 8000. Both are local applications. Private hosting configuration is outside this repository and is not a release dependency.

## Entire removal

The user explicitly requested Entire removal after the hackathon. This supersedes all earlier recording requirements. The CLI uninstall removed agent hooks, five Git hooks, six local session states, the local metadata directory, and one shadow branch. Three remaining local Entire checkpoint refs and sixteen remote Entire checkpoint refs were removed separately.

Normal source branches, tags, commit history, and model release archives remain intact. Earlier commits can still mention Entire or contain its former configuration. No normal Git history was rewritten. Do not recreate recording hooks. This repository removal does not claim deletion from other clones, external account services, or provider caches.

## Public release

The source uses MIT for original code. Upstream code, Gemma-derived weights, and datasets retain their separate terms. The public project is `Bitarious/Canary`. Its `main` branch preserves this machine's verified source and all normal hackathon history. The original repository remains unchanged by this publication. Experiment archives use `v2026.09.13` and retain their original provenance. The release implementation at `b284e65` passed a fresh-checkout pilot rebuild, 97 core tests, nine demo tests, full browser evidence/navigation checks, and package builds. All 15 original archive hashes and 187 committed evidence hashes passed. See [the release guide](project-release.md) and [release audit](release-audit.md) for details.

Source, model, and evidence publication must refer to their exact revisions. Preserve the selected checkpoint hashes and do not replace the original archives. The anonymous public clone passed the full pilot/API verification. All three GitHub Actions jobs passed. All 17 public model assets match their original digests. Anonymous checksum, manifest, and complete SSD archive downloads passed.

## Next work

Use [the implementation plan](implementation-plan.md) for future product scope. Use [the reproduction guide](reproduction.md) for new research runs. Do not reuse historical cloud instances, expired deadlines, stale budgets, or released run directories as a shortcut.

Before every training run, explain and record the objective, data splits, updated and frozen parameters, hardware/cost limit, stopping conditions, evaluation, and outputs. Training is separate from release verification and requires its own bounded plan.
