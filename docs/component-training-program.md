# Separate hardware TSLM program

This is the historical experiment log. All thirteen categories reached their terminal study results. Use [the current reproduction guide](reproduction.md) for portable commands and fresh compute configuration. Earlier active-phase descriptions and account balances below are historical.

The user authorized this program on September 12, 2026. First, complete and evaluate the historical Backblaze HDD model. If it passes, research the other hardware categories named in the implementation plan and dataset backlog. Train a separate TSLM for each component. Combine sources or components only if the data cannot support a separate model, and record the reason.

The total compute ceiling is $600 across setup, diagnostics, HDD training, evaluation, and all later component runs. The earlier $605 console balance was user-reported before spending. It is not a current measured balance. Keep an evaluation and artifact-export reserve inside the ceiling. Do not spend on invalid data or report a failed model as working to exhaust the budget.

Keep documentation and code in this GitHub repository. The user authorized commits and upload on September 13, 2026. This supersedes the earlier prohibition. Entire was removed after the hackathon at the user's request. Normal Git history and experiment artifacts remain intact.

## Success gate

Successful optimization alone does not pass the HDD gate. Require:

- Separate device identities and valid time boundaries across training, validation, and test.
- A completed pass through every eligible historical HDD training window.
- A checkpoint selected with validation data before opening its test subset.
- Better held-out signal descriptions than the starting checkpoint and the fixed all-constant baseline.
- A measured dependence on numerical input, tested with the predeclared zero, reversed, and shuffled input comparisons.
- A verified checkpoint reload and saved raw predictions, metrics, and uncertainty estimates.

Apply comparable checks to each later component. Define its task, baseline, acceptance criteria, and test protocol before training. Rule agreement does not prove failure prediction, physical root cause, or an operational maintenance benefit. If a model fails, retain the result and use validation evidence or a new untouched test cohort for further work.

The HDD criteria are now fixed in `evaluate_full.py`, before full training or test release. At least 95% of free-text answers must be valid. Supported-class macro F1 must exceed both baselines. The lower 95% paired drive accuracy difference bound must exceed zero against each baseline and the zero-input model. Reversal and shuffle must each improve accuracy over unchanged original answers on at least 32 drives with changed targets. Their lower 95% gain bounds must also exceed zero. Sixteen predictions must match after checkpoint reload. Save every check and its result, including failed checks.

## Component inventory

The inventory below follows the categories in [the dataset backlog](dataset-backlog.md). The [component dataset audit](component-dataset-audit.md) records source checks and measured coverage. The HDD model passed its frozen gate on September 13. Eleven further component categories have passed their frozen tests and verified exports. The industrial-valve sound trial also passed with verified export. Both dated radiator-valve failures remain recorded.

| Separate model | Current state |
| --- | --- |
| HDD | Complete training pass and all frozen held-out checks passed. Checkpoints and raw evaluation outputs exported and verified. |
| SSD | Passed frozen gate and verified export: 31,269 training windows, two verified SMART channels |
| NVMe | Passed frozen gate and verified export: 51,105 training windows and 268 independent validation groups |
| RAM / DRAM | Passed frozen gate and verified export: 34,089 training windows of recorded error-log counts |
| GPU | Passed frozen gate and verified export: 344,520 training windows of power and temperature |
| CPU / processor | Passed frozen gate and verified export: 114,840 training windows of power and temperature |
| Whole server / datacenter | Passed frozen gate and verified export: 57,420 training windows of power-supply inputs |
| Fan | Passed frozen gate and verified export: 203,264 training windows from 397 hosts, with 116 separate test hosts |
| Pump | Passed five-group industrial study: 18,405 gear-oil-pressure training windows |
| Valve | Radiator-valve model failed both tests. Separate industrial-valve sound model passed with 9,801 training windows. |
| Gearbox | Passed five-group industrial study: 14,628 oil-temperature training windows |
| Bearing | Passed five-group industrial study: 18,405 generator-bearing temperature training windows |
| Slide rail | MIMII-derived DCASE benchmark passed with verified export under the authorized unknown-date exception. Seven separate machines, limited development cohort. |

For every source, record provenance, access terms, download hashes, actual size, device count, modality, channel meanings, cadence, labels, gaps, and known limits. Keep training, validation, and test sets separate before fine-tuning. Retain native TimeF write/read verification. Each run needs its own advance overview, cost limit, data and source hashes, checkpoints, evaluation, reload proof, and result report.

The program remains active until the supported component models pass their declared checks or the available compute budget prevents further valid runs. Record any unavailable or unsuitable datasets explicitly. Do not invent a trained model for a missing component.

## Reproduce the prepared telemetry datasets

The pinned source catalog declares 45 files and 75,843,229,773 bytes. It includes checksums, source references, and required metadata snapshots. The downloader uses three transfers, resumes exact HTTP ranges, and retains 100 GB of free storage. Backblaze uses its separate [full-history acquisition](full-history-training.md).

Run these commands from a new checkout after installing the locked environment. Existing preparation outputs require inspection before a new attempt.

```bash
uv sync --locked --extra training
uv run --no-sync python scripts/download_component_sources.py
uv run --no-sync python -m driftops.prepare_components ssd --output data/components/ssd-component-v1
uv run --no-sync python -m driftops.prepare_components cpu --output data/components/cpu-component-v1
uv run --no-sync python -m driftops.prepare_components gpu --output data/components/gpu-component-v1
uv run --no-sync python -m driftops.prepare_components server --output data/components/server-component-v1
uv run --no-sync python -m driftops.memory_data --output data/components/dram-component-v1
uv run --no-sync python -m driftops.nvme_data --config config/nvme_component_v2.yaml --output data/components/nvme-component-v2
uv run --no-sync python scripts/download_component_sources.py --manifest config/m100_fan_sources.json
uv run --no-sync python -m driftops.fan_data --output data/components/fan-component-v1
```

Each output contains prepared split Parquet files, verified native TimeF shards, source records, audit counts, and a dataset manifest. Training receives only training windows and frozen validation examples. Test numerical inputs stay on the controller until checkpoint selection ends.

## Separate model procedure

`component_training.py prepare` requires the real passed HDD report and a fresh shared compute ledger. It rejects telemetry cohorts with fewer than 64 independent groups in any main split. Each component starts from the pinned upstream OpenTSLM weights. It updates the temporal encoder, projector, and rank-8 attention LoRA. Original Gemma parameters remain frozen.

The first epoch visits every eligible natural training window. Later epochs use a deterministic mix of natural, reversed, and shuffled observations. Counterfactual targets describe the changed numerical order. They do not add physical machines or failure events. Equal natural and counterfactual validation sets select completed-epoch checkpoints.

Each run allows at most 12 epochs or two training hours. Validation patience can stop it after three completed epochs without improvement. The planned component phase assigns one GPU per independent model inside the existing eight-GPU VM. Its shared 3.5-hour limit costs at most $50.45 at the recorded rate. A phase guard and the overall $600 ceiling remain mandatory.

`evaluate_component.py freeze` fixes the selected checkpoint and protocol before test release. Evaluation compares the upstream model, constant baseline, fitted model, and three numerical perturbations. It reports independent-group uncertainty and exact checkpoint reload. A released test prevents further fitting in that run directory.

The component, fan, supervisor, and export source passed all 77 tests in the working checkout and a fresh locked environment. The isolated check rebuilt the native pilot before testing, with no skipped tests. Evidence is in `artifacts/component-audit/v1/isolated-verification-v4/`. The phase supervisor assigns one GPU per model and waits for checkpoint export before test release. The controller verifies the selected checkpoint hash before it freezes and transfers test inputs. Each completed model retains separate predictions, metrics, and reload evidence.

The active seven-model phase uses frozen source bundle SHA-256 `332d47f08476cb1f2aa478238d98d62c64fa69e19a9dc70b54bc80415ec9d914`. Its artifacts are in `artifacts/nebius/full-history-v1/component-phase-v1/`. All 451 staged training shards passed checksum checks before launch. No numerical test or calibration shards were transferred. The shared deadline is September 13 at 07:51:32 UTC, with a $50.45 phase ceiling. The project ledger estimated $71.65 already spent when this phase was reserved. All seven jobs have started optimizer updates. Final results remain pending.

## Small industrial studies

Gearbox, generator bearing, gear-oil pump, and radiator valve models started separately at about 04:54 UTC. Each starts from the pinned upstream model. Each updates its own encoder, projector, and LoRA parameters, with original Gemma weights frozen. They share the previously unused GPU 7. They share no learned parameters or mixed-component training examples.

| Model | Training windows | Training groups | Validation groups | Calibration groups | Test groups |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gearbox | 14,628 | 10 | 3 | 2 | 5 |
| Generator bearing | 18,405 | 10 | 3 | 2 | 5 |
| Gear-oil pump | 18,405 | 10 | 3 | 2 | 5 |
| Radiator valve | 6,203 | 3 | 2 | 1 | 5 |

The [industrial study design](industrial-study-design.md) fixes component channels, ordered dates, and independent group assignments before fitting. These studies use at most 12 epochs or 45 training minutes each. Validation patience can stop a run after three completed epochs without improvement. The controller selects and exports a completed-epoch checkpoint before it releases numerical test inputs. The test uses at most 256 windows per held-out group. Group-level inference retains the five-group denominator.

This phase shares the existing $50.45 reservation and the 07:51:32 UTC provider deadline. It adds no VM. The parent seven-model service owns provider shutdown and can interrupt the industrial phase. Its selected checkpoints remain on the persistent disk for verified export or a later bounded evaluation. A released test prohibits further fitting of that run.

All 58 industrial training shards and 63 source files passed remote checksum checks. Frozen source bundle SHA-256 is `e475c598e0976751eb4471f90599cdb1183332700674d5b166c0a99ef0615c8d`. Phase artifacts are in `artifacts/nebius/full-history-v1/industrial-phase-v1/`. The industrial adapter, evaluator, and controllers pass all 83 tests in the working checkout and a fresh locked checkout. The isolated check rebuilt the native pilot and skipped no tests. Evidence is in `artifacts/component-audit/v1/isolated-verification-v5/`.

Reproduce the industrial datasets with the locked environment:

```bash
uv run --no-sync python scripts/download_component_sources.py --manifest config/industrial_sources.json
uv run --no-sync python -m driftops.industrial_data gearbox --output data/components/gearbox-industrial-v1
uv run --no-sync python -m driftops.industrial_data bearing --output data/components/bearing-industrial-v1
uv run --no-sync python -m driftops.industrial_data pump --output data/components/pump-industrial-v1
uv run --no-sync python -m driftops.industrial_data valve --output data/components/valve-industrial-v1
```

The source catalog contains 25 files totaling 4,225,595,495 bytes. It preserves publisher checksums, local SHA-256 values, and original metadata snapshots. A complete local `--verify-only` check passed before these commands were documented.

## Slide-rail benchmark and current results

The user authorized MIMII when the dated alternatives are inadequate, with the limitations documented. The [fixed sound design](slider-study-design.md) uses separate machines for training, validation, and test. It permits no acquisition-chronology claim. The mono PCM adapter calculates two causal energy-band signals, preserves clip-relative clocks in native TimeF, and excludes exact duplicate recordings. It uses CC-BY-NC-SA-4.0 source terms.

```bash
uv run python scripts/download_component_sources.py \
  --manifest config/slider_sources.json --output artifacts/component-audit/v1
uv run python -m driftops.slider_data --output data/components/slider-audio-v1
uv run python -m driftops.component_training prepare \
  --root data/components/slider-audio-v1 \
  --run artifacts/tslm/slider-audio-v1 \
  --hdd-report artifacts/tslm/full-history-rtx6000-v2/evaluation/metrics.json \
  --audio-benchmark
```

The recorded version already exists. These preparation commands deliberately reject an existing output. Download or verify the two files from `config/slider_sources.json` with the downloader's `--manifest` option before a new build. Refresh the shared compute ledger before preparing a training run. Do not run the training command until its overview, source, device allocation, and deadline checks are complete.

The real sound dataset contains 10,648 training windows, 10,648 validation windows, and 40,755 held-out windows. Its manifest hash is `5ad463c95f56bd20f29c131a9749ccff143baf099f2f389efcedf13b660bc37b`. The training transfer included 31 training shards and no test or calibration numeric shards. The frozen `/opt/driftops/components-v4` source contains 67 verified files. Training started at 06:09 UTC on free GPU2 in the existing VM. The shared reservation and provider deadline remain fixed.

All 88 repository tests pass in the working checkout and an isolated locked environment. The isolated check also rebuilt the bundled native pilot. Evidence is in `artifacts/component-audit/v1/isolated-verification-v8`. Initial TimeF checks rejected the unsupported source-license enum and a custom unit name. The corrected metadata retains the exact license URL and dimensionless digital-unit description. The original failed build records remain in the audit directory.

Read [current results](component-model-results.md) for completed gates and checkpoint hashes. The original valve failure remains unchanged. Its follow-up uses the same weights and all previously unused test windows. Parallel order calculations publish complete caches atomically only when the main evaluator has no destination directory. The original evaluator owns final metrics and checkpoint reload.

The completion-stop owner now has a bounded export grace period. It waits at most fifteen minutes for slide-rail and valve follow-up export receipts. It then invokes the unchanged provider guard. The absolute 07:51:32 UTC deadline remains active. This stays within the original $50.45 phase reservation. `scripts/stop_after_component_exports.py` and its unit override are recorded in `artifacts/nebius/full-history-v1/export-grace-v1/`. All 91 tests pass in working and isolated locked environments. The fresh checkout also rebuilt the native pilot. Evidence is in `artifacts/component-audit/v1/isolated-verification-v9/`.

## Final valve category trial

GPU, fan, and slide rail completed training, passed their frozen gates, and exported verified artifacts. Twelve component categories now pass. The dated radiator-valve follow-up failed its numerical-dependence group test. Preserve both dated valve failures.

The separate `valve-audio-v1` trial uses the fixed [industrial-valve sound design](valve-audio-study-design.md), new upstream initialization, and DCASE/MIMII valve data. Its preparation, split validation, native TimeF path, and phase routing pass all 93 tests. A fresh checkout with locked dependencies also rebuilt the native pilot and passed all 93 tests. Evidence is in `artifacts/component-audit/v1/isolated-verification-v10/`.

The previous component VM stopped at 06:38:09 UTC. Controller CLI authentication was restored and all three owned VM stops were verified. The new valve phase reserves $28.90 within the shared $600 ceiling. Its absolute deadline is September 13, 08:59:46 UTC. Sources, budget, guards, preflight, and launch records are in `artifacts/nebius/full-history-v1/valve-audio-phase-v1/`.

To reproduce data in a new output directory, use the verified `config/valve_audio_sources.json` with `scripts/download_component_sources.py`. Then run `driftops.slider_data` with `--config config/valve_audio_benchmark.yaml` and the new output path. Prepare separate run artifacts through `driftops.component_training prepare --audio-benchmark`. Refresh the compute ledger and replace the generic phase overview with an exact bounded budget before any future launch. Existing released runs must not be overwritten or trained again.

The valve trial completed six epochs in 334.6 seconds and selected epoch three on validation. The controller froze and released its 5,120-window test on five machines at 07:15:19 UTC. Reversal and shuffle comparisons ran on GPUs 1 and 3. A separately recorded zero-input helper uses idle GPU 4. Each helper uses the same frozen protocol and atomic cache publication without replacement. The main evaluator remains responsible for the final metrics and GPU reload check. These helpers change no weights, targets, thresholds, or budget limits.

## Completed result

All thirteen component categories have a separate model that passed its declared signal-description gate. The last industrial-valve sound model scored 77.08% channel accuracy and 0.7579 macro F1 on 5,120 windows from five machines. All 1,626 exported JSON and checkpoint files passed checksum verification. GPU and CPU reload each matched sixteen answers. Both dated radiator-valve failures remain recorded.

The final provider stop completed at 07:28:48.868937 UTC on September 13. All three owned VMs are stopped. The 07:29 UTC conservative ledger totals $111.35, leaving $488.65 under the $600 ceiling. Retained cloud disks still cost about $0.03734 per hour. This is not a live voucher balance. See [component results](component-model-results.md) for all metrics and caveats. Working tree changes remain uncommitted and unpushed.
