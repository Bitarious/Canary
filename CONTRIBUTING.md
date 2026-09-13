# Contribute to Canary

Report bugs and propose changes through the repository's GitHub issues and pull requests. Include the command, expected behavior, actual behavior, and relevant dependency versions. Remove credentials and private telemetry from reports.

## Development

Use Python 3.12 or newer and `uv`. Run `bash scripts/bootstrap.sh` from the repository root. This prepares the bundled pilot and runs core tests. No cloud account, model download, or agent recording tool is required.

Run `bash scripts/verify.sh` before submitting a change. For browser changes, install Node 22 or newer, run `npm ci`, then `npx playwright install chromium`. Run `npm run test:browser`. The browser harness starts and stops its own local server and uses temporary device storage.

Describe what changed and include the checks you ran in the pull request. Keep changes focused. Include a regression test for behavioral fixes. Do not change released evidence to make a test pass.

## Research changes

Preserve device separation, chronological boundaries, input allowlists, and frozen test protocols. Use a new run directory for a new study. Never train a run after its test release. Report negative results and retain raw predictions.

Explain and record every training run before launch. Include the objective, data splits, updated and frozen parameters, hardware, cost limit, stopping conditions, evaluation, and artifacts. Paid compute requires a current budget and verified provider stop control.

Read [the reproduction guide](docs/reproduction.md) before changing training procedures. Model weights and datasets retain their separate terms in [the license guide](docs/model-licenses.md).

Original contributions use the repository's MIT license. Preserve third-party notices. Git history records contributor attribution. Entire is no longer part of this project's workflow.
