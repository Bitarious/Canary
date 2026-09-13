# DriftOps

**Your infrastructure doesn't fail suddenly. It drifts.**

Predict infrastructure degradation before it becomes an incident. The hackathon implementation starts with drive telemetry and connects health trajectories, temporal evidence, operational priority, and maintenance decisions.

The first working demo uses **Backblaze HDD data only**, starting with one supported drive model. Additional hardware and data sources are recorded in the [dataset backlog](docs/dataset-backlog.md) for later work.

Built for the EHL Zurich Temporal AI Challenge, using Aionic's TimeNet for data preparation, OpenTSLM for signal-language modeling, and Nebius for training compute.

All thirteen component categories now have separate models that pass their declared signal-description tests. Selected checkpoints and evaluation exports are verified. The dated radiator-valve model failed twice. A separate industrial-valve sound model passed under the documented unknown-date exception. All three owned VMs are stopped. Estimated total spend is $111.35. These results do not establish failure prediction. Read [component results](docs/component-model-results.md) for metrics, checkpoints, and limitations.

The **bundled pilot** contains 3,000 HDDs of one model during July–December 2024, with 547,812 daily observations and 13,616 TimeNet signal-description tasks. The local browser still shows development windows and deterministic descriptions. The earlier local CPU concept failed its useful-input check. See its [measured result](docs/evaluation.md). The full operator workflow remains unfinished.

On the Linux server, install Git, uv, and Entire, then run from this checkout:

```bash
bash scripts/bootstrap.sh
uv run --no-sync driftops demo
```

Without uv, use pip with Python 3.12 or newer:

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt && pip install -e . --no-deps
driftops prepare && driftops demo
```

The 3D digital twin only needs `pip install -r driftops3d/requirements.txt`, then `python driftops3d/server.py`.

Open `http://127.0.0.1:8000`. Setup uses the bundled 1.2 MB public sample and needs no GPU or cloud login for the data preview. The [Linux handoff](docs/handoff.md) covers SSH browser access, Entire hook verification, account setup, and the overnight development launcher. **Entire logging and session pushes must stay enabled for submission.** The preview is not yet a trained-model demo.

- [Technical architecture](docs/architecture.md): TimeNet data boundaries, OpenTSLM training/inference, contracts, replay, maintenance reasoning, and evaluation.
- [Implementation plan](docs/implementation-plan.md): execution by Codex alone as prerequisites become ready, TimeNet preparation, TSLM training, held-out evaluation, and submission checks.
- [Nebius connection](docs/nebius-setup.md): installed CLI, authenticated profile, selected project, and PowerShell launcher.
- [Data preparation](docs/data-preparation.md): cohort, splits, limitations, and tested acquisition/conversion commands.
- [Model access](docs/model-setup.md): Hugging Face connection, selected Gemma/OpenTSLM weights, and remaining runtime checks.
- [Training and reload](docs/training.md): bounded CPU adaptation, pinned dependencies, checkpoint artifacts, and evaluation commands.
- [Linux and overnight handoff](docs/handoff.md): tested local workflow, development continuation, and training prerequisites.

The required submission includes a working demo, code and training configuration, a trained checkpoint or learned adapter, dataset documentation, and evaluation against baselines. The project compute ceiling is **$600**. The user reported a $605 Nebius balance before paid work. The first CPU experiment spent no cloud credits. Later runs use bounded Nebius compute, with costs in the [component results](docs/component-model-results.md). Every training run must be explained before it starts. Documentation and artifacts remain local. The user has prohibited commits and pushes.
