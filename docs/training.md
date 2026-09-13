# OpenTSLM concept experiment

The runner adapts the numerical encoder and projector of Gemma-based OpenTSLM-SP.
It uses TimeNet windows from the bundled Backblaze pilot. Gemma stays frozen.
The browser preview remains a deterministic data preview.

This is a signal-description experiment. Targets come from the existing observed-window
rules. Agreement with those targets does not establish independent reasoning or failure
prediction. Three channels are constant throughout the selected 256-drive training sample.
Temperature supplies most of the pattern variation. Counter resets have no support in
that training sample.

The source subset under `src/driftops/_vendor/opentslm/` comes from the pinned official
[OpenTSLM revision](https://github.com/OpenTSLM/OpenTSLM/tree/2968f4b891baab4307f7e9d0043e87677b593a30).
Its model methods are unchanged. The import namespace isolates the SP model from unrelated
Flamingo dependencies. `UPSTREAM.json` records the original file hashes and import changes.
The directory retains the upstream license and contributor list.

Our wrapper loads both pinned checkpoints with `weights_only=True` and strict temporal
state matching. It uses the upstream encoder, projector, and numerical embedding method.
The wrapper removes prompt padding before it appends answers. It masks prompt tokens and
answer padding from the loss, omits an extra answer BOS token, and appends EOS. Generation
uses left padding. These changes correct the upstream training and generation boundaries.

Inputs contain four daily numerical channels and neutral text. The bridge normalizes each
observed 28-day channel with its own mean and sample standard deviation. It calculates
these values in float64 before converting to float32. Constant channels become zero.
No fitted transform uses validation or test data. Answers, drive IDs, cutoff dates,
partitions, and outcomes do not enter the model prompt.

## Reproduce a local CPU run

Run these commands from the repository root. The training extra installs CPU PyTorch.
It does not provision a GPU or start cloud billing. The cached base model requires
Hugging Face access under its license.

```bash
uv sync --locked --extra training --extra model-access
uv run --no-sync driftops prepare
uv run --no-sync hf download google/gemma-3-270m --revision 9b0cfec892e2bc2afd938c98eabe4e4a7b1e0ca1
uv run --no-sync hf download OpenTSLM/gemma-3-270m-tsqa-sp model_checkpoint.pt --revision c97bd36131e07d53a7af9cd307eb3db628f9712f
uv run --no-sync python -m driftops.train_tslm prepare --run artifacts/tslm/my-diagnostic --diagnostic --steps 300
```

Read `overview.json` before training. An agent must explain its contents before it starts
each training run. The overview records the objective, data, parameters, compute, limits,
evaluation, and outputs. Preparation does not update weights.

```bash
uv run --no-sync python -m driftops.train_tslm train --run artifacts/tslm/my-diagnostic
uv run --no-sync python -m driftops.train_tslm reload --run artifacts/tslm/my-diagnostic
```

Prepare a separate concept run after the diagnostic. Choose its step limit before launch.
Explain the new overview before training.

```bash
uv run --no-sync python -m driftops.train_tslm prepare --run artifacts/tslm/my-concept --steps 1200
uv run --no-sync python -m driftops.train_tslm train --run artifacts/tslm/my-concept
uv run --no-sync python -m driftops.train_tslm reload --run artifacts/tslm/my-concept
uv run --no-sync python -m driftops.evaluate_tslm --run artifacts/tslm/my-concept
```

Each run directory must be new. Checkpoints replace files atomically. `last.pt` contains
the optimizer, PyTorch RNG, sample-selection RNG, completed step, selection state, and
consumed runtime. To continue an interrupted run within its original budget, add `--resume`
to its training command. Do not change its overview. The runner refuses an exhausted budget.

The runner saves progress every step and a checkpoint every ten steps. It stops for its
step limit, runtime limit, validation patience, or invalid loss/gradients. A process crash
can lose the steps since the last checkpoint. The model runs locally, so process exit
does not leave a billable cloud VM.

## Evaluation contract

Training uses 256 distinct drives in July/August. Validation uses 32 other drives in
September. The final evaluation uses one window each from 64 further drives in November/December.
The existing `drive-time-v1` partitions control membership. Sample selection uses a fixed
task hash and does not inspect targets. The calibration partition remains unused.

The evaluator saves its protocol before reading held-out targets. It compares the starting
checkpoint, the selected checkpoint, an all-constant baseline, and the deterministic rules.
It also zeros all numerical channels for the selected checkpoint while keeping text fixed.
The rules score perfectly because they generated the labels. That score is not independent
validation.

The experiment also reports a separate fixed-format comparison. A token grammar permits
all 625 combinations of five patterns for four known channel names. Greedy decoding lets
OpenTSLM select the patterns. The grammar does not calculate a trend or inspect a target.
It enforces channel names and syntax, so its valid-output rate is not a learned capability.
The starting and trained checkpoints use the same grammar. The report retains the full
free-text scores and their invalid answers. This secondary comparison was added after a
development validation sample invented channel names, before any final test predictions.

The strict parser requires exactly one allowed pattern for each supplied channel. An invalid
answer receives zero credit for all channels. Reports include pattern support, per-class F1,
macro-F1 across supported classes, channel accuracy, valid-output rate, changed-channel
precision/recall, and generation time. A paired bootstrap resamples distinct drives.

The prompt fixes the interval to the entire 28-day window. The experiment does not measure
event localization. It does not score physical causes, remaining life, or maintenance effects.
There is no independent expert review or calibrated failure forecast. Inspect the saved raw
outputs to assess errors. Do not tune on these test results and reuse the test as untouched data.

The selected checkpoint contains all learned encoder and projector weights. It still needs
the pinned Gemma base, this preprocessing version, and this code. Large artifacts stay outside
Git under `artifacts/tslm/`. No checkpoint is uploaded by these commands.
