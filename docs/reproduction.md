# Reproduce Canary experiments

There are three independent tasks: inspect evidence, replay existing weights, or fit a new model. The first two do not require a training run or paid compute. All commands run from the repository root.

## Verify and replay the release

Run `bash scripts/verify.sh` to rebuild the pilot and check the source tests and 187 committed evidence hashes. Use the [README CPU example](../README.md#2-replay-a-released-model-on-cpu) to compare sixteen SSD predictions with saved GPU outputs.

The [release guide](project-release.md) explains artifact downloads. The loader requires both pinned Hugging Face dependencies in `config/model.yaml`, plus the selected checkpoint. Download access and upstream terms remain separate requirements. The original `v2026.09.13` artifacts predate the current source cleanup.

## Rebuild the recorded data

For the bundled pilot, run `uv run --no-sync driftops prepare`.

For full HDD data, use a new checkout without existing full-history data:

```bash
mkdir -p data/backblaze-full
cp results/2026-09-13/backblaze/inventory.json data/backblaze-full/inventory.json
uv run --no-sync python -m driftops.full_archive download
uv run --no-sync python -m driftops.full_prepare
uv run --no-sync python -m driftops.full_dataset
```

Compare the archive hashes, source totals, split counts, and dataset manifest with the committed Backblaze receipts and run records. The archive inventory covers 44 files through Q1 2026. It occupies about 30.8 GiB compressed, with about 229.6 GiB of CSV content. Native prepared data requires additional storage.

For SSD, NVMe, DRAM, CPU, GPU, fan, server power, industrial telemetry, and sound datasets, use the commands in [the component program](component-training-program.md). Its dated phase descriptions are historical. Source manifests, adapter commands, and study designs identify the reproducible inputs.

## Prepare a new HDD run

Use a CUDA-capable training host. Install the CUDA environment and download the pinned model dependencies through the normal Hugging Face CLI:

```bash
uv sync --locked --extra nebius-training --extra model-access
cp config/train_full.yaml config/train_reproduction.yaml
```

Edit the copied configuration before preparation. Set the GPU name, memory, `world_size`, `batch_size`, current hourly rates, `budget_usd`, and machine/training time limits. Retain the recorded seeds, data contracts, learning rates, and evaluation settings for a comparable experiment. Hardware or batch changes define a new run and can change predictions.

`--config` accepts a YAML file directly inside the repository's `config/` directory. This keeps configuration in the frozen source manifest and makes the source tree transferable. The validator rejects invalid counts, nonfinite values, negative rates, and a quoted machine reservation above the configured budget.

```bash
uv run --no-sync python -m driftops.train_full prepare \
  --root data/backblaze-full \
  --run artifacts/tslm/hdd-reproduction-v1 \
  --config config/train_reproduction.yaml
```

This verifies data and writes run artifacts. It does not update model weights. Inspect `overview.json`, `config.json`, `dataset-manifest.json`, `validation.json`, and `source-hashes.json`. Explain the objective, splits, parameters, hardware, budget, stopping rules, evaluation, and outputs before launch.

Before using paid hardware, verify available funds and a current independent provider stop guard. A training-process timeout does not stop cloud billing. The historical Nebius provisioning scripts remain experiment records; they are not portable provisioning defaults.

## Train and evaluate

On the configured training host, set `GPU_COUNT` to the frozen `world_size`. For example, use eight only when the configuration and available hardware specify eight GPUs:

```bash
GPU_COUNT=8
uv run --no-sync torchrun --standalone --nnodes=1 --nproc-per-node="$GPU_COUNT" \
  --module driftops.train_full train \
  --root data/backblaze-full --run artifacts/tslm/hdd-reproduction-v1
```

The training runner checks the frozen source, GPU count, runtime limit, and released-test guard. It saves optimizer, random-state, and data-position checkpoints. Repeating the training command resumes within the original run limits. Do not change source or configuration after preparation.

After checkpoint selection, freeze the test protocol on the controller:

```bash
uv run --no-sync python -m driftops.evaluate_full freeze \
  --root data/backblaze-full --run artifacts/tslm/hdd-reproduction-v1
uv run --no-sync python -m driftops.evaluate_full evaluate \
  --root data/backblaze-full --run artifacts/tslm/hdd-reproduction-v1 --device cuda
```

The evaluator reports the starting model, fitted model, all-constant baseline, zero-input control, reversal, shuffle, and exact reload. Preserve every gate outcome. Compare metrics and raw predictions with the recorded experiment; do not assume identical weights or answers across hardware.

## Prepare separate components

Each component starts from upstream weights and needs a passed HDD report. Preparation also requires a fresh compute ledger. `--ledger` accepts an explicit file path, so another machine does not need the original controller layout.

The ledger must record `as_of` with a time zone and `remaining_under_ceiling_usd`. It must be at most five minutes old. Preserve the existing minimum $50.45 phase reserve and provide enough funds for the configured machine rate over the component's 3.5-hour reservation. Record the provider receipts and rates behind the ledger. Do not fabricate a balance or refresh an old timestamp without checking the account.

```bash
uv run --no-sync python -m driftops.component_training prepare \
  --root data/components/ssd-component-v1 \
  --run artifacts/tslm/ssd-reproduction-v1 \
  --hdd-report artifacts/tslm/hdd-reproduction-v1/evaluation/metrics.json \
  --config config/train_reproduction.yaml \
  --ledger artifacts/reproduction/cost-ledger.json
```

Component preparation fixes one GPU, at most twelve epochs, two training hours, and validation patience. Industrial and sound flags select their tighter study bounds. Read the generated overview rather than assuming the HDD settings all transfer.

Use `driftops.component_training train` with the same `--root` and `--run`. Use the `freeze` and `evaluate` actions of `driftops.evaluate_component` for telemetry. Use `driftops.evaluate_industrial` for industrial and sound studies. Their `--help` output describes the required arguments. Each model needs a new run directory and its own frozen protocol.

No reproduction command provisions a cloud machine automatically. Export the selected checkpoint and complete evaluation evidence, verify their hashes, and stop paid resources through the provider after each bounded job.
