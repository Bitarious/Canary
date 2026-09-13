# DriftOps

**Your infrastructure doesn't fail suddenly. It drifts.**

Predict infrastructure degradation before it becomes an incident. The hackathon implementation starts with drive telemetry and connects health trajectories, temporal evidence, operational priority, and maintenance decisions.

The first working demo uses **Backblaze HDD data only**, starting with one supported drive model. Additional hardware and data sources are recorded in the [dataset backlog](docs/dataset-backlog.md) for later work.

Built for the EHL Zurich Temporal AI Challenge, using Aionic's TimeNet for data preparation, OpenTSLM for signal-language modeling, and Nebius for training compute.

Current status: the **bundled pilot** contains 3,000 HDDs of one model during July–December 2024, with 547,812 daily observations and 13,616 TimeNet signal-description tasks. A local browser preview shows real development windows and rule-derived descriptions. This is a sample of the much larger public archive. Gemma 3 270M and its matching OpenTSLM checkpoint are selected and their weight access was verified; model runtime integration, training, evaluation, and the full operator workflow remain unfinished.

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
- [Linux and overnight handoff](docs/handoff.md): tested local workflow, development continuation, and training prerequisites.

The required submission includes a working demo, code and training configuration, a trained checkpoint or learned adapter, dataset documentation, and evaluation against baselines. The team's compute voucher is **$600**. Nebius CLI access and GPU quota are verified; remaining balance, GPU capacity, and model loading still need checking. Every training run will be explained to the user before it starts. A partner inference endpoint is optional when the trained model can run locally or on Nebius. Real measurements, derived scores, and illustrative operational context remain explicitly distinguishable.
