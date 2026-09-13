# Changelog

## Unreleased public research release

Canary now includes a public project guide, MIT licensing for original code, contributor information, and a reproduction guide. The release retains the known-good local demo and its saved HDD evidence view.

- Preserve the three real HDD cases, including a stable control and a model mismatch.
- Keep synthetic fleet analysis separate from saved model evidence.
- Remove Entire hooks, local session state, and dedicated checkpoint refs. Preserve normal source history and model release archives.
- Use project metadata for pip dependencies and the lockfile for exact `uv` installs.
- Add demo API, browser, and evidence-integrity verification to CI.
- Make new training configuration and component budget-ledger paths explicit.

This is a research release. It adds no failure-prediction claim and does not enable live model inference in the demo.

## Experiment artifacts, September 13, 2026

The `v2026.09.13` artifact set contains fourteen selected checkpoints and fifteen evaluations. Thirteen component categories passed their declared signal-description gates. Both dated radiator-valve failures remain included.

The artifact set retains model licenses, dataset attribution, checksums, raw evaluation inputs, and predictions. The original source snapshot predates the Canary evidence-view updates. Publication status is recorded in the release guide.
