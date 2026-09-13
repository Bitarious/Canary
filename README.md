# DriftOps

DriftOps explores how small time-series language models can describe changes in hardware measurements. The project combines a 3D inspection demo, real dataset preparation, and separate component models.

Thirteen component models passed their declared signal-description tests. These tests measure agreement with numerical pattern rules. They do not establish failure prediction or maintenance benefit.

The `driftops3d` demo currently uses synthetic devices and deterministic analysis. It does not call the trained models. Saved Backblaze cases and an integration proposal are included below.

Built for the EHL Zurich Temporal AI Challenge with Aionic TimeNet, Gemma-based OpenTSLM, and Nebius training compute.

## Run the 3D demo

The demo server uses the Python standard library. Run this command from the repository root:

```bash
python3 driftops3d/server.py --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/#/site/site-a` after the initial data preparation completes, usually about 15 seconds. The browser needs network access for Three.js and fonts. Optional device collection dependencies are listed in [the demo README](driftops3d/README.md).

The demo contains 147 illustrative devices across two server sites and an HQ laptop scene. Its risk numbers, forecasts, and copilot answers come from rules. Read the [UI review](docs/reviews/2026-09-13/ui-review.md) before using those numbers in a presentation.

## Run the real Backblaze data preview

Install Git, `uv`, and Entire. Then run:

```bash
bash scripts/bootstrap.sh
uv run --no-sync driftops demo
```

Open `http://127.0.0.1:8000`. The bundled 1.2 MB sample covers 3,000 HDDs during July–December 2024. Preparation produces 547,812 observations and 13,616 signal-description tasks. This preview shows source measurements and deterministic descriptions. It needs no GPU or cloud account.

Keep Entire recording, agent hooks, and normal Git checkpoint pushes enabled for hackathon eligibility. The [Linux handoff](docs/handoff.md) explains setup and verification.

## Models and measured results

The full-history HDD model trained on all 11,315,069 eligible windows from the acquired historical archive through Q1 2026. On 2,048 unseen drives, it achieved 99.68% channel accuracy against weak pattern labels. The constant baseline scored 69.43%. Zeroing numerical input reduced model accuracy to 86.01%.

Separate passing models cover HDD, SSD, NVMe, DRAM, CPU, GPU, server power, fan, gearbox, generator bearing, gear-oil pump, slide-rail sound, and industrial-valve sound. The two failed radiator-valve evaluations remain in the evidence. Sound recordings lack verified acquisition dates and use the documented separate-device exception.

Each final model has 271,029,888 parameters, including 2,931,072 trained encoder, projector, and attention-LoRA parameters. A selected checkpoint is about 683 MB because it also includes Gemma embedding and output-head tensors. These are not small pure-adapter files.

- [Component results and limitations](docs/component-model-results.md)
- [Versioned evaluation evidence and model catalog](results/2026-09-13/README.md)
- [Model release and download instructions](docs/project-release.md)
- [Model and dataset licenses](docs/model-licenses.md)
- [Full-history HDD training](docs/full-history-training.md)
- [Dataset research and source choices](docs/component-dataset-audit.md)

All three training VMs were verified stopped at 07:29 UTC on September 13, 2026. The final ledger estimated $111.35 spent under the $600 compute ceiling. This is an estimate, not a current voucher balance. Retained cloud disks still incur storage charges.

## Demo data and five-minute presentation

- [Teammates' presentation draft](PresentationDraftDeck.html)
- [Five-minute presentation plan with metrics and technical appendix](docs/reviews/2026-09-13/presentation-plan.md)
- [Demo integration analysis](docs/reviews/2026-09-13/analysis.md)
- [Three real HDD examples with saved model outputs](results/2026-09-13/hdd-demo-cases.json)
- [Measured metrics for charts](results/2026-09-13/measured-metrics.json)

The HDD examples include a rising signal, a stable signal, and a model mistake. They were selected after evaluation for illustration. They are not a new benchmark.

## Development and reproduction

Use [the implementation plan](docs/implementation-plan.md) and [architecture](docs/architecture.md) for the intended operator workflow. The [training guide](docs/training.md), [component program](docs/component-training-program.md), and run configurations describe the completed experiments.

```bash
uv sync --locked --extra training
uv run --no-sync pytest -q
```

The repository contains source, configuration, documentation, a public pilot sample, and compact evaluation evidence. GitHub release assets carry selected weights and complete evaluation JSON. Large raw datasets, environments, private credentials, and machine runtime logs stay outside Git. Download manifests and preparation code reproduce the dataset inputs.

The user authorized this project upload on September 13, 2026. Normal Git and Entire hooks remain active.
