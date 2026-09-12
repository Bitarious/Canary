# Backblaze data preparation

Prepared on 12 September 2026. This is an implemented data pipeline, not evidence of trained-model performance. No model training or paid cloud resources were used.

## Source and cohort

The source is [Backblaze Drive Stats](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data), queried through Backblaze's publicly documented, read-only Iceberg table. The credentials in the acquisition module are the shared read-only dataset credentials published by Backblaze; they are not private account credentials. Data use remains subject to the source's terms and attribution requirements.

**Archive versus pilot:** Backblaze's download page lists annual files starting in 2013 and quarterly files through Q1 2026 as reviewed on 12 September 2026. Its Q1 2026 snapshot reports 341,263 drives and 30,203,180 drive-days. Our 3,000 drives are a deliberately capped local subset of one model over six months, selected to verify acquisition, conversion, splitting, and initial model integration. They are not a total count of the public dataset. One history means the collected daily observations for one selected drive during our chosen period, not that drive's entire lifetime.

The exact Iceberg metadata object and its checksum are pinned in [source-snapshot.json](../config/source-snapshot.json). Acquisition selects up to 3,000 `ST8000NM0055` drive identities observed on 1 July 2024, ordered deterministically by a hash of their serial numbers. It retains their observations through 31 December 2024, including normal histories and disappearance. Future failures do not control identity selection.

The July development audit guided hardware-model selection. An initial `ST4000DM000` extract was rejected because only two drives remained observable in October–December. That extract and manifest remain locally as `data/raw/backblaze-st4000dm000-audit.*`. Selection changed for calendar coverage, before model fitting or held-out performance measurement. This coverage decision inspected later observation availability and is a limitation to disclose.

| Acquired property | Value |
|---|---|
| Model | ST8000NM0055 |
| Drives | 3,000 |
| Source rows | 547,812 |
| Observation range | 2024-07-01 through 2024-12-31 |
| Recorded failure flags in the full source cohort | 33; these are not a model metric |
| Parquet size | 1,226,077 bytes |
| Parquet SHA-256 | `6de7fc9ebdf9d88d825607677c503c32c3a641c92b56235fcaaf7c592d79b0c1` |
| Missing days between each drive's first and last observation | 129 |

There are 3,000 observed drives in July and 2,966 in December. Missing days and missing SMART values remain visible; no forward/backward imputation is applied. Days after a drive's last observation are not counted as internal missing days. A disappearance without an observed event is not labeled healthy or failed.

The source flag describes recorded failure/removal under Backblaze's operating policy. It does not establish physical failure time, root cause, or a counterfactual benefit of replacement. This one-model cohort excludes later fleet entrants and cannot establish generalization to other hardware or operators.

The pilot cap can be expanded. For substantive failure-prediction work, first audit event/follow-up support in the development partitions, then widen same-model coverage and create a new frozen dataset/split version if needed. Thirty-three recorded flags across the entire pilot do not establish sufficient calibration/evaluation support. Additional years and models need schema and SMART-semantics checks; more daily rows alone do not guarantee more independent failure examples.

## TimeNet conversion

The connector uses the pinned `timenet[build,s3]==0.1.0` SDK, `BaseConnector`, `TimeFDataset`, `TimeFWriter`, and `TimeFReader`. `download()` verifies the local acquired extract's checksum; `convert()` performs offline conversion. The separate acquisition command handles filtered remote retrieval.

Each drive becomes one record with its source identity, model, capacity, actual daily calendar, and seven numerical channels: raw SMART 5, 9, 187, 188, 194, 197, and 198. Source raw encodings are preserved without claiming universal physical units. TimeNet 0.1.0 does not offer `int64` signal values, so the connector checks that each integer fits exactly in `float64` before conversion. Nullable values remain null. SMART 188 may contain packed vendor encoding and is excluded from the initial language task.

The source-day availability convention is the end of that day in UTC. Observation timestamps identify calendar days; inference cutoffs assume the day's record has become available. Recorded failure annotations remain in offline storage and are excluded from model inputs.

The connector writes `data/timef/driftops/backblaze-hdd/0.1.0`. Read-back verification compares records, channel specifications, numerical values, missingness, calendars, metadata, tasks, and scoped model inputs against the raw conversion. `data/preparation-audit.json` records results and configuration checksums; `data/split-manifest.json` records drive assignments. The 1.2 MB public pilot and its source manifest are committed under `examples/backblaze-pilot/` for portable setup. Working copies under `data/`, TimeF outputs, local dependencies, and authentication files are not committed.

## Tasks and partitions

The initial task describes direction/pattern in complete 28-day numerical windows, using two to four available channels from SMART 5, 187, 194, and 197. Windows advance in seven-day increments within each configured period. Missing-calendar windows and windows on/after a recorded event are excluded. A channel with missing values is omitted; at least two complete channels are required.

Targets are generated by the versioned rules in [annotations.py](../src/driftops/annotations.py). They distinguish constant, rising, falling, fluctuating, and counter reset/decrease patterns. These are weak annotations derived from observed values, not technician narratives. The prompt includes only a neutral question and channel descriptions; serial numbers, partition names, absolute dates, outcomes, and generated answers are excluded. The input builder crops values using each TimeNet task's explicit time scope.

Drive groups are disjoint, assigned by a stable hash independently of outcomes. Cutoff periods then advance through time. Earlier history belonging to a held-out drive can supply its own lookback.

| Partition | Assigned drives | Eligible tasks | Configured cutoff range |
|---|---:|---:|---|
| Train | 1,802 | 7,151 | July 28–August 24 |
| Validation | 467 | 1,842 | September 1–23 |
| Calibration, reserved for supported risk modeling | 290 | 1,157 | October 1–24 |
| Test | 441 | 3,466 | November 1–December 24 |

Ranges are eligibility bounds; the seven-day stride does not necessarily land on the last bound. Configuration is in [splits.yaml](../config/splits.yaml). Optional seven-day event labels require an observed event within the horizon, or complete follow-up for a negative. Inadequate follow-up produces an unknown label. No risk model has been fitted, and a calibrated event probability is not currently supported.

Constant channels dominate the development targets. Evaluation must report per-pattern results and compare with a simple constant-output baseline. A deterministic description baseline uses the same rules as the annotation generator, so agreement with those generated labels measures rule imitation, not independent maintenance correctness. Separate manual checks and explicit limits are required before making usefulness claims.

## Reproduce locally

Use Linux/WSL with Python 3.12 and `uv`. Run from the repository root. The project is now packaged, and `uv.lock` pins the tested dependency resolution. For the bundled pilot:

```bash
uv sync --locked --extra model-access
uv run --no-sync driftops prepare
uv run --no-sync pytest -q
uv run --no-sync driftops demo
```

Preparation is repeatable and checks source/configuration compatibility before reuse. The preview uses training-partition windows only and explicitly labels rule descriptions. Use [bootstrap.sh](../scripts/bootstrap.sh) when setting up a development machine so Entire is installed/enabled as part of the handoff. To independently reacquire from the official source into a fresh working-data directory:

```bash
uv sync --locked --extra model-access
uv run --no-sync python -m driftops.acquire fetch \
  --model ST8000NM0055 --start 2024-07-01 --end 2024-12-31 --max-drives 3000
uv run --no-sync python -m driftops.timenet_connector
uv run --no-sync pytest -q
```

Acquisition needs network access and reads the pinned snapshot. It refuses to overwrite an existing cohort. The TimeNet writer also protects an existing committed version. To verify the already-built dataset without replacing it:

```bash
uv run --no-sync python -m driftops.timenet_connector --verify-only
```

On this Windows machine, invoke a command through WSL, for example:

```powershell
wsl --distribution Ubuntu --cd '/mnt/c/Users/mariu/Desktop/ehl zurich' --exec .venv/bin/driftops prepare
```

The tests cover causal-window invariance under future mutations, gaps/duplicates, event-day exclusion, censored outcomes, device/time separation, malformed numeric data, TimeF serialization, exclusion of target/prompt metadata, source checksums, exact integer preservation, repeatable sample installation, and preview HTTP behavior. The real preview integration test requires `driftops prepare` first. These checks do not train a model. GPU training remains a separate stage with an advance overview required by the user.
