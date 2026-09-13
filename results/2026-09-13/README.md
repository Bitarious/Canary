# Component model evidence

This directory preserves the measured results from September 13, 2026. Thirteen component categories passed their declared signal-description checks. Both dated radiator-valve failures remain included.

These tasks use numerical pattern rules as weak reference labels. Accuracy does not measure failure prediction, diagnostic correctness, or maintenance benefit.

| File or directory | Contents |
| --- | --- |
| `model-catalog.json` | Fifteen evaluations, fourteen distinct selected checkpoints, dataset pins, split groups, gates, and reload counts |
| `runs/<run>/` | Original training overviews, configurations, source hashes, dataset manifests, selection records, and compact metrics |
| `cpu-reload/` | Saved comparisons of CPU predictions with sixteen GPU predictions for each evaluated run |
| `backblaze/` | Historical archive inventory, acquisition receipt, row preparation totals, and hardware-model audit |
| `hdd-demo-cases.json` | Three post hoc presentation examples with raw signals, saved model outputs, and separate reference labels |
| `measured-metrics.json` | Values extracted for presentation charts, including measured latency and parameter counts |
| `training-code-verification.json` | The original fresh-checkout test receipt from the completed training program |
| `publication-verification.json` | Fresh-checkout pilot, 93 tests, and real demo API checks for the publication source commit |
| `release-manifest.json` | Release archive sizes, SHA-256 values, and run-to-checkpoint mapping |
| `SHA256SUMS` | SHA-256 checksums for the evidence files |

Run the integrity check from this directory:

```bash
sha256sum -c SHA256SUMS
```

The original run paths in the records are relative to the repository root, under `artifacts/tslm/`. They identify training artifacts and remain unchanged for reproducibility. The original checkpoint, metrics, and manifest hashes remain unchanged.

Download the selected weights and complete evaluation JSON using [the release guide](../../docs/project-release.md). The evaluation archive restores the original run paths, including frozen test inputs, protocols, predictions, and zero/reversal/shuffle comparisons.

HDD, storage, compute, and dated industrial studies preserve separate device groups and ordered dates. The two sound studies have separate machines but unknown acquisition chronology. Neither sound study has a calibration fit.

CPU-component, GPU-component, server, and both dated radiator-valve evaluations reproduced fifteen of sixteen saved answers on CPU. Their same-GPU reload checks reproduced all sixteen. The remaining CPU checks reproduced all sixteen.

Dataset source terms and Gemma-derived weight terms apply. Read [the license guide](../../docs/model-licenses.md).
