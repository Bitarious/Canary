# Full historical Backblaze fine-tuning

The user requested every historical HDD archive and Nebius training. The user also requested separate validation and test datasets.

Status on September 13, 2026: run `full-history-rtx6000-v2` completed all 11,315,069 training windows and passed every frozen held-out success check. It used eight RTX PRO 6000 GPUs in Nebius `uk-south2`. The selected completed-epoch validation loss is 0.00022362074014381506.

The final test contains 2,048 unseen drives and 6,777 channel labels. All fitted outputs are valid. Channel accuracy is 99.6754%, exact-window accuracy is 98.9258%, and supported-class macro F1 is 0.99124. The constant baseline reaches 69.4260% channel accuracy. Zero numerical inputs reduce accuracy to 86.0115%. The upstream model produces no answers valid under the frozen task format, so its strict task accuracy is zero. This format limitation is part of the baseline result.

Both order perturbations pass. Reversal changes weak targets for 928 test drives, and shuffle changes targets for 932. Their accuracy-gain intervals over unchanged original answers remain above zero. Sixteen predictions match exactly after checkpoint reload. The test contains no natural counter-reset labels, so it does not establish accuracy for that natural class. Results establish weak-rule signal interpretation and useful numerical dependence. They do not establish failure prediction, physical cause, or maintenance benefit.

The controller verified all 648 evaluation JSON files against remote SHA-256 hashes. The metrics file hash is `29f2ee0d4ee56c3407cb8b66b17f8de74a5a06776045e26c8afcf75a3100a433`. Results and raw generations are in `artifacts/tslm/full-history-rtx6000-v2/evaluation/`. The provider completed successful stop `computeoperation-e05dcw6j2bt4xz9vnb` at 04:20:37 UTC. Total estimated project spending was $71.65 at 04:21 UTC, including setup failures and storage. The passed HDD gate now permits the separate component runs.

The selected `best.pt` SHA-256 is `d941fc219865ee6cc54c62f5498f8ae180710d44c83ade1c3b145bdc57297b99`. The first-pass monitor requested a graceful stop after the completed-epoch selection met the declared 0.01 loss threshold. The terminal result confirms one complete epoch, 22,271 steps, and 11,335,861 total examples across both segments. A small part of epoch two ran before the monitor stopped the process. The selected checkpoint remains the completed first epoch at exactly 11,315,069 examples.

The controller exported and verified `best.pt`, `last.pt`, `selection.json`, and `training-result.json` at 03:56:41 UTC. The provider completed stop operation `computeoperation-e05qq5ypwsv5sy5tt5` at 04:02:18 UTC. `terminal-export.json` records this evidence. The conservative ledger estimated $68.06 spent at 04:05 UTC, leaving $531.94 under the shared ceiling. These are operation-based estimates, not the console balance.

The selected checkpoint and evaluation protocol were frozen before the controller released numerical test data for 2,048 distinct held-out devices. Further training in this run is prohibited. The evaluation phase uses separate frozen source with bundle SHA-256 `ffd3138e5599219d63f0a6131ad3a41199de399ab20261a750de6332b1615157`. Five GPUs generate the declared comparisons independently. The phase has a $36.03 maximum cost and an absolute provider/controller deadline of 06:27:57 UTC. Its overview, budget, and source hashes are in `artifacts/nebius/full-history-v1/hdd-evaluation-v1/`.

The sections below retain the setup and training history. The terminal state above supersedes their earlier active-run and unopened-test statements.

On September 12, 2026, all 44 ZIP files linked by the [official Backblaze page](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data) downloaded successfully. The files total 30.766 GiB and contain 229.578 GiB of dated CSV data. The original archives retain all source columns.

Conversion completed for 4,739 source days, from April 10, 2013, through March 31, 2026. It produced 712,322,056 rows that passed identity, date, and failure-flag checks. Another 235,631 rows remain in quarantine files. Quarantine excludes rows with missing device identity, a date that differs from the source filename, or an invalid failure flag. The converter does not invent replacement values. Original ZIP files and quarantine rows remain available for inspection.

The archive contains SSD boot drives as well as HDDs. The model-family audit separates these before preparing HDD windows. Seven rows have the incomplete model name `00MD00`. They remain in the source data and are excluded from HDD preparation. The complete model audit and manufacturer references are in `data/backblaze-full/model-audit.json` and `artifacts/nebius/full-history-v1/media-review.json`.

## Frozen split rules

[The split configuration](../config/full_history.yaml) preserves the pilot's serial hash assignment. Device ranges are half-open.

| Split | Serial hash buckets | Complete input-window dates |
| --- | --- | --- |
| Training | 0–59 | January 2013–December 2024 |
| Validation | 60–74 | January–September 2025 |
| Calibration reserve | 75–84 | January–September 2025 |
| Test | 85–99 | October 2025–March 2026 |

Each serial belongs to one split. A window must contain 28 consecutive daily observations and at least two complete language channels. No input window can include a recorded failure or observations after that failure. The input window must fit entirely inside its split's date interval. Windows do not overlap. Short segments and missing-channel exclusions receive audit counts.

The full preparation command writes native TimeF shards. SDK read-back checks compare every record, calendar, value, annotation, task, and scoped model input. The training export stores only the scoped numerical window, target, and separate audit fields. Model prompts use an explicit numerical/text allowlist. They exclude serials, absolute dates, failure flags, future observations, and target descriptions.

All validation and test windows remain available as separate files. A deterministic subset of 512 validation drives will guide checkpoint selection. A deterministic subset of 2,048 test drives is planned for final comparisons. Test numerical files stay on the controller until the selected checkpoint hash is frozen.

The native build verified 706,533,780 HDD source rows. Its final manifest SHA-256 is `fe868c96983b7688bab01fb6580c63931df188ae1ba6e90f79c0bfc37c3e48cd`.

| Split | Eligible windows | Distinct devices |
| --- | ---: | ---: |
| Training | 11,315,069 | 260,618 |
| Validation | 422,976 | 49,668 |
| Calibration reserve | 279,283 | 32,815 |
| Test | 295,377 | 50,886 |

## Training design

The starting model is the pinned Gemma 3 270M OpenTSLM-SP TSQA adapter. This run does not start from the unsuccessful CPU pilot checkpoint. It updates the temporal encoder, projector, and rank-8 LoRA adapters in Gemma attention projections. All original Gemma parameters remain frozen.

Targets use the existing deterministic `window-description-v1` rules. They are weak supervision. They do not represent technician reports, causal failure explanations, or calibrated failure risk. The model receives normalized observations and the same window's raw standard deviation. The scale statistic makes the rule's one-raw-unit threshold identifiable after normalization.

The iterator visits every eligible training window without replacement. It can complete up to two epochs. Checkpoint selection considers completed epochs only. A partial first epoch cannot be reported as full-data training. Pattern weights use training counts only. Validation selection uses unweighted answer loss.

The accelerated configuration uses eight GPUs and 64 examples per GPU. Each global batch contains up to 512 distinct windows. The distributed loss accounts for each rank's actual target-token weight, including incomplete batches and empty ranks. A two-process regression test matches the gradients of a single global batch. All 54 tests passed in a fresh clone with the RTX candidate source, a new locked environment, and a native rebuild of the bundled dataset. The later HTTP-metadata guard repair also passed its focused tests.

The chunked loss computes vocabulary logits only at answer positions. A synthetic regression check compares its loss and gradients with full logits. A real OpenTSLM CPU check also passed with no optimizer steps. Under gradient mode, both losses were `3.5848910808563232`. Under inference mode, both were `3.598093032836914`. The difference between modes came from the CPU execution paths. The encoder and projector had finite, nonzero gradients.

## Compute and stopping

The user confirmed $605 in Nebius credits. The project ceiling remains $600. A one-H200 diagnostic passed 16 optimizer steps and exact checkpoint reload. It used 1,024 training windows, took 19.51 seconds including model loading and reload, and averaged 0.174 seconds per warm batch of 64. Its peak GPU allocation was 7.13 GB. These measurements verify the runtime, not held-out model quality. Diagnostic weights will not initialize the full run.

A second one-H200 diagnostic tested batch 512 on 8,192 training-only windows. It passed 16 steps and exact checkpoint reload. Warm batches averaged 1.2237 seconds, with 61.85 GB peak allocation. The reload loss was `1.2546463012695312` before and after reload. Its checkpoint SHA-256 is `26de97ab2a7ba441be89f03ba00230c37c672cc4aba9249f5d9c868c04efce00`. The first export was interrupted by automatic VM stopping. A later resumable transfer recovered and verified the complete checkpoint. Both H200 VMs are now stopped.

The user authorized more compute to accelerate training. Nebius reports a regional H200 quota of 32 and quotes $36/hour for an eight-H200 VM. Each GPU has 141 GB memory. The 128 GiB network SSD costs $0.012444416/hour. The maximum additional interval is ten hours, approximately $360.12, with a seven-hour training limit. These are limits, not expected spending. Both stop deadlines were brought forward to September 13, 2026, at 09:13:36 UTC. The earlier one-H200 setup adds a small separate cost within the $600 ceiling.

Nebius requires its API or CLI to stop billable compute. A guest Linux shutdown can trigger recovery and continued billing. The proposed guard uses an absolute deadline and a service account with `compute.instance-power-operator` permission on this job's VM only. It must pass a real stop/start check before training. [Nebius stop behavior](https://docs.nebius.com/compute/virtual-machines/stop-start), [power-operator role](https://docs.nebius.com/iam/authorization/roles).

Nebius rejected a resize because this H200 platform does not permit a preset change. A separate eight-H200 VM now exists. The original one-H200 VM is stopped, with its diagnostic exported and checksum-verified. The service account has power-operator permission on these two job-owned VMs only. Both VMs passed a successful asynchronous CLI acknowledgement and the provider's `STOPPED` state. Guest guards and persistent controller timers enforce the earlier deadline. It will not move later when either VM restarts.

Paid runtime has been used for setup, stop-control checks, and the one-GPU diagnostic. The eight-GPU environment is installed. Its first training command failed during argument parsing, before model loading or optimizer steps. The corrected launcher syntax passed help-only checks. A later restart failed because Nebius could not allocate eight GPUs. Both VMs are stopped while the native data build finishes. Regional quota does not reserve hardware.

The conservative cost ledger estimated $14.99 used at September 12, 23:56 UTC, including failed scheduling intervals and disk storage. This is an upper estimate from operation times and quoted rates, not a billing-console balance. Refresh the ledger after each compute interval. The parallel diagnostic, full training, held-out evaluation, final reload verification, artifact export, and resource cleanup remain pending. The earlier CPU pilot remains a negative signal-interpretation result.

The [component program](component-training-program.md) states the HDD success criteria before full training and test release. The evaluation records paired uncertainty against zero numerical input as well as both baselines. Reversed and shuffled signals must produce correct changed descriptions. An unchanged answer does not pass that check. The full held-out test remains unopened.

## Active RTX fallback

The capacity advisor reported high availability for eight RTX PRO 6000 GPUs in the existing `uk-south2` project. The account-specific quote is $14.40/hour for the VM and $0.01244928/hour for its 128 GiB disk. The eight-hour maximum is $115.30, inside the shared $600 ceiling. Its absolute provider and controller deadline is September 13 at 08:34:30 UTC. Training has a separate seven-hour limit.

The selected image is `computeimage-e05sd0w38f33bx1kxv`, Ubuntu 24.04 with CUDA 13.0 and driver 580.173.02. The older CUDA 12 image explicitly excludes this GPU platform. The pinned PyTorch 2.8.0 CUDA 12.8 wheel passed a real bfloat16 matrix operation on every RTX GPU. Each device reports compute capability 12.0 and 97,887 MiB memory. The locked environment installed successfully.

This image uses HTTP instance metadata. The guard now reads the documented identity endpoint with a bounded request and retains support for older images. It does not read or print an authentication token. The new VM has its own service account and group, with power-operator permission on this VM only. A real stop completed at 00:49:31 UTC, and the provider confirmed `STOPPED` before restart. [Nebius metadata migration](https://docs.nebius.com/compute/virtual-machines/instance-metadata).

The first full segment was `artifacts/tslm/full-history-rtx6000-v1`. Its advance overview, data manifest, validation subset, class weights, source hashes, and cost limit are frozen locally. The transfer includes all 256 training Parquet files and the 512-drive validation subset. It includes no test numerical files. The separate 16-step RTX diagnostic passed before this segment started from the upstream weights.

At 00:51 UTC, the conservative cost ledger estimated $22.23 used across all three VMs, including scheduling intervals and storage. This is not a current voucher balance. Keep the H200 failure records, both successful single-GPU diagnostic exports, and the RTX setup evidence. No commit or push has been made.

## Commands

```bash
uv sync --locked --extra training
uv run --extra training python -m driftops.full_archive inventory
uv run --extra training python -m driftops.full_archive download
uv run --extra training python -m driftops.full_prepare
uv run --extra training python -m driftops.full_dataset --workers 2
uv run --extra training python -m driftops.train_full prepare --run artifacts/tslm/full-history-rtx6000-v1
```

The CPU and Nebius dependency extras are mutually exclusive. On the Nebius VM, use `uv sync --locked --extra nebius-training`. Do not install the CPU Torch wheel into that environment.

Launch the frozen parallel run with an explicit launcher argument boundary:

```bash
.venv/bin/torchrun --standalone --nnodes=1 --nproc-per-node=8 -- \
  src/driftops/train_full.py train --run artifacts/tslm/full-history-rtx6000-v1
```

The `--` before the script is required. Without it, this Torch launcher treats `--run` as an ambiguous launcher option. Both the diagnostic and training entry points passed a local help-only check with this form.

Do not launch training until the run overview, dataset hashes, source hashes, hardware check, and provider stop guard are ready. Explain each training launch in advance. Keep the same explanation in its artifacts.

## Input preparation and resumed run

The first full-data segment ran 795 optimizer steps and saw 404,525 training windows. Its measured rate was about 565 windows/second. Each GPU process prepared all 512 global inputs before selecting its own 64. A controller benchmark measured about 0.334 seconds for 512 inputs and 0.042 seconds for 64.

The revised iterator preserves the global shuffle and cursor, then prepares each GPU's assigned rows. Pre-change hashes matched all inputs, targets, and cursor positions for 6,144 real training examples. Regression checks cover incomplete batches, empty ranks, coverage, resume order, and distributed gradients. All 57 tests passed in the working tree and a fresh checkout with a new locked environment and native pilot rebuild.

The parent run stopped by signal and saved its model, optimizer, CPU and per-GPU random states, and exact cursor. Its exported checkpoint SHA-256 is `949205b40f2f4770c04e831e025f6b38f343e019edea7dd86e299c555b3a9d16`. It has no completed epoch and is not a full-data result.

The active continuation is `artifacts/tslm/full-history-rtx6000-v2`, using separate frozen source in `/opt/driftops/work-v2`. It reads the same immutable training exports. Data, class weights, validation inputs, optimizer settings, GPU count, and batch size remain identical. `resume.json` records the parent checkpoint and prior progress. The seven-hour training limit includes the parent's 723.49 training seconds. The provider/controller deadline remains 08:34:30 UTC.

Resumed steps initially took about 0.39 seconds per batch. This suggests about 2.4 hours per pass, subject to sustained throughput and checkpoint overhead. It is a timing estimate, not a quality result. The model has not yet completed its full training or opened its held-out test subset.

The advance `first-pass-stop-amendment.json` permits a graceful stop after the first completed epoch if its frozen validation loss is at most 0.01. Otherwise, the original two-epoch or seven-hour limit applies. This preserves a complete pass through all eligible training windows. The optional second pass gives way to held-out evaluation and the conditional component program. The active training source, parameter settings, splits, and success gate remain unchanged.

The later restart followed a provider `STOPPED` state, but overlapping stop requests and the subsequent start left aborted stop operations. Preserve those records. The cost ledger counts the interval conservatively. The earlier standalone RTX guard check has a separately completed successful stop operation.


## Early validation generation check

The saved v1 parent checkpoint at step 795 also passed a small validation-only generation check on September 13. This checkpoint had seen 404,525 training windows. The check selected 32 distinct devices by fixed hash from the frozen validation subset. It used the local CPU with eight threads and a ten-minute limit. No parameters changed. Test and calibration data remained unopened.

Original numerical inputs produced valid answers for all 32 windows and 95.37% channel accuracy. Zeroing numerical values while retaining the same text reduced accuracy to 84.26%. The paired drive accuracy gain interval was 0.0286–0.1953. Reversed and shuffled inputs also improved accuracy over unchanged original answers on the changed-target subsets. Those subsets contain only 18 and 16 drives, so this check does not replace the predeclared final gate.

Artifacts are in `artifacts/tslm/hdd-validation-generation-v1/`. They include the overview, fixed validation inputs, raw predictions, metrics, and checkpoint hash. The first attempt stopped before generation because the local environment lacked PEFT. The repository's locked `training` extra resolved that dependency. The second attempt completed. The full Nebius training continued independently.
