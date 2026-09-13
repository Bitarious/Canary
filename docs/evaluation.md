# Backblaze OpenTSLM concept result

The training pipeline works, but this experiment did not establish useful signal
interpretation. The fine-tuned model gives the same answer for all 64 test windows.
It also gives that answer when every numerical channel is replaced with zero.
The checkpoint is a reproducible failed concept experiment, not a useful failure detector.

## Experiment

Run `artifacts/tslm/concept-v2` uses the pinned Gemma 3 270M/OpenTSLM-SP pair.
It updates 2,110,976 encoder parameters and 82,816 projector parameters.
All 268,098,816 loaded Gemma parameters remain frozen. No LoRA is enabled.
Parameter hashes and gradient checks confirm actual optimization.

The input contains four numerical SMART channels over 28 daily observations.
Targets come from the existing deterministic window-description rules.
The model receives neutral channel names and instructions, with targets supplied
only on the training side. Each channel uses normalization within its observed window.

| Partition | Distinct drives/windows | Cutoffs |
| --- | ---: | --- |
| Training | 256 | July 28 through August 18, 2024 |
| Validation | 32 | September 1 through September 22, 2024 |
| Test | 64 | November 1 through December 20, 2024 |

The existing device and date partitions remain intact. A fixed task hash selects
one window per drive without consulting targets. Test drives overlap neither development
partition. The calibration partition remains unused.

The main run allowed 1,200 steps and 30 minutes on eight local Ryzen AI Max+ 395 CPU
threads. It stopped after 680 steps because four validation checks did not improve.
Step 600 had the lowest validation loss, 0.123807. The initial 16-window training probe
loss was 3.047380. The final probe loss was 0.145132. These losses measure teacher-forced
answer prediction, which does not establish correct generated answers.

Training took 386.75 seconds and used 3,283.73 MiB of peak process memory. Two earlier
training diagnostics took 16.74 and 157.60 seconds. All three runs used local compute.
Cloud spending was $0. Electricity was not measured. The user reported a $605 Nebius
balance, while the project ceiling remains $600. No billable resource was created.

## Held-out results

Each test window has four channel labels, for 256 labels in total. Gold support is
188 constant, 15 rising, 27 falling, and 26 fluctuating labels. No reset label is present.
The macro-F1 score averages the four supported classes. Every invalid answer receives
zero credit for all its channels.

| Method | Valid answers | Channel accuracy | Whole-window accuracy | Macro-F1 |
| --- | ---: | ---: | ---: | ---: |
| Starting OpenTSLM, free text | 0/64 | 0.0% | 0.0% | 0.000 |
| Starting OpenTSLM, fixed format | 64/64 | 35.5% | 0.0% | 0.293 |
| Fine-tuned OpenTSLM, free text | 64/64 | 77.7% | 15.6% | 0.317 |
| Fine-tuned OpenTSLM, fixed format | 64/64 | 77.7% | 15.6% | 0.317 |
| Fine-tuned OpenTSLM, numerical inputs zeroed | 64/64 | 77.7% | 15.6% | 0.317 |
| All channels constant | 64/64 | 73.4% | 0.0% | 0.212 |
| Deterministic target rules | 64/64 | 100.0% | 100.0% | 1.000 |

The rules score perfectly because they generated the targets. Their score is not
independent validation. The fixed-format decoder permits all 625 combinations of five
patterns for the four known channel names. The model selects patterns. The grammar
supplies names and syntax, so its validity score is enforced rather than learned.
That secondary comparison was declared after a development validation sample invented
channel names, before final test predictions. The original free-text scores are retained.

The fine-tuned model's sole answer is:

```text
smart_5_raw: constant; smart_187_raw: constant; smart_194_raw: rising; smart_197_raw: constant.
```

All 64 zero-series outputs match their original outputs exactly. Falling and fluctuating
patterns each have zero F1. Constant-pattern F1 is 0.989, and rising-pattern F1 is 0.278.
The apparent 77.7% accuracy largely reflects constant channels and one repeated trend label.
It exceeds the all-constant baseline by 11 correct labels out of 256, or 4.3 percentage
points. It does not show that the model uses the observed trend to choose its answer.

Changed-channel precision is 100%, and recall is 94.1%. These scores are also misleading
in isolation. The model always marks temperature as changing, which matches the dominant
structure of this sample. It does not correctly identify the direction of those changes.

The paired drive-bootstrap interval for channel-accuracy improvement over the unformatted
starting model is 75.0 to 80.5 percentage points. That comparison is dominated by the
starting model's invalid output format. It should not support a signal-understanding claim.
Fine-tuned generation took 23.87 seconds for 64 windows at batch size four, or 0.373 seconds
per window when batch time is amortized. This is not an interactive single-request latency.

## Verification and limits

Both the working checkout and an isolated checkout passed all 20 tests. The isolated
checkout used a fresh environment and rebuilt all 3,000 TimeNet records and 13,616 tasks.
It then reproduced four model inputs and four generated answers exactly with the selected
checkpoint. It shared the existing Hugging Face weight cache and received the checkpoint
as an explicit input. This was a fresh clone with the uncommitted candidate source overlaid.

The checkpoint contains finite temporal weights, optimizer state, and RNG state. Its
sample-selection RNG matches an exact replay of 680 steps. An interrupted training process
was not resumed end to end. The reload and inference paths were exercised in fresh processes.

An early numerical-input probe changed embeddings and logits, confirming that the native
numerical path runs. The final generated-answer ablation shows that this integration alone
does not establish useful input dependence. The first eight frozen test cases also have a
raw-value and median audit in `evaluation/review-cases.json`. This is an agent numerical
audit, not independent expert labeling. In the first case, the temperature median falls
from 33 to 29 raw source units, but the model reports rising. Three of the eight
temperature descriptions agree with the recorded pattern. The other five do not.

Three channels are constant throughout the selected training sample. The test has only
64 drives from one HDD model and weak rule-derived targets. No physical-cause, remaining-life,
maintenance-effect, event-localization, or calibrated failure prediction was evaluated.

A next experiment should address the repeated-answer behavior on development data.
Balanced changing-window examples and per-channel questions are possible tests. A small
language-model adapter is another untested option if temporal-only adaptation still fails.
Any change informed by these test results needs a new untouched holdout.

## Artifacts

- [Selected temporal checkpoint](../artifacts/tslm/concept-v2/best.pt), 8,794,737 bytes, SHA-256 `377b192cb1529ecccdca7bb08f72a5a3a4820230bbceca86d789965cee97bf51`.
- [Training overview](../artifacts/tslm/concept-v2/overview.json), [training result](../artifacts/tslm/concept-v2/result.json), and [step log](../artifacts/tslm/concept-v2/progress.jsonl).
- [Evaluation protocol](../artifacts/tslm/concept-v2/evaluation/protocol.json), [metrics](../artifacts/tslm/concept-v2/evaluation/metrics.json), and [raw predictions](../artifacts/tslm/concept-v2/evaluation/finetuned.jsonl).
- [Isolated-checkout evidence](../artifacts/tslm/concept-v2/clean-smoke.json) and [reproduction commands](training.md).

This historical CPU experiment remained local at evaluation time. The later component model release is documented in [the release guide](project-release.md).
