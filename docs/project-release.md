# Project release

The September 13, 2026 upload combines the trained component models with the teammates' `driftops3d` application and presentation draft. The repository remains private.

The source, configurations, tests, public Backblaze pilot, presentation review, and compact evaluation evidence live on `main`. Selected checkpoints and full evaluation JSON use [GitHub release assets](https://github.com/M-10001/EHL_Zurich_hackathon_team_piloty/releases/tag/v2026.09.13).

## Download the artifacts

Authenticate the GitHub CLI with an account that can read this private repository. Read [the model license guide](model-licenses.md) before using or distributing the weights.

From the repository root, download the release files:

```bash
mkdir -p artifacts/github-release/v2026.09.13

gh release download v2026.09.13 \
  --repo M-10001/EHL_Zurich_hackathon_team_piloty \
  --dir artifacts/github-release/v2026.09.13
```

Verify the files before extraction:

```bash
(cd artifacts/github-release/v2026.09.13 && sha256sum -c SHA256SUMS)
```

Each model archive restores `artifacts/tslm/<run>/best.pt` and includes license notices. The evaluation archive restores the associated run metadata and complete evaluation JSON.

```bash
for archive in artifacts/github-release/v2026.09.13/*-model.tar.gz; do
  tar -xzf "$archive"
done

tar -xzf artifacts/github-release/v2026.09.13/evaluation-evidence.tar.gz
```

There are fourteen unique selected checkpoints for fifteen evaluations. The dated radiator-valve follow-up reused the original radiator-valve weights. Restore its expected path if you inspect that failed follow-up:

```bash
cp artifacts/tslm/valve-industrial-v1/best.pt \
  artifacts/tslm/valve-industrial-followup-v1/best.pt
```

The release manifest maps each run to its archive and checkpoint checksum. Every selected checkpoint is 682,889,851 bytes before compression. All fourteen total 9,560,457,914 bytes. Download individual archives with `gh release download --pattern` if you need only one component.

## Load a selected model

Install the locked CPU inference environment:

```bash
uv sync --locked --extra training
```

The selected checkpoints need the pinned Gemma base and OpenTSLM assets. The [model setup guide](model-setup.md) and [training guide](training.md) contain the authenticated Hugging Face download commands. Credentials remain local.

Use the target-free reload example in [component results](component-model-results.md#exported-checkpoints). It performs inference on already released test inputs and does not train a model. Preserve the original files and hashes when reproducing the recorded evaluations.

These checkpoints contain trained temporal modules and attention LoRA, plus Gemma embedding and output-head tensors. They are not self-contained language models or small pure adapters.

## Included evidence and limits

The [evidence directory](../results/2026-09-13/README.md) contains fifteen evaluated runs, including the two failed dated radiator-valve evaluations. Full evaluation assets retain test inputs, original protocols, raw predictions, controls, and metrics. The release does not convert failed runs into passes.

The 3D application still uses synthetic telemetry and deterministic analysis. The real HDD examples contain saved model outputs. Connecting those examples to the application is proposed in [the demo review](reviews/2026-09-13/analysis.md), but is not part of this release.

The teammate presentation remains a draft. The [five-minute presentation plan](reviews/2026-09-13/presentation-plan.md) supplies measured results, limitations, timing, and an appendix outline.

## Data and private machine files

The repository includes the public pilot sample, full source inventories, checksums, dataset contracts, and preparation code. Large raw archives and prepared datasets are not release assets. Retrieve them from their documented publishers and apply their source terms.

Private credentials, environments, machine caches, cloud authentication logs, and machine telemetry are excluded. Optimizer and interrupted-run recovery files remain local. The selected weights and evaluation evidence are the reproducible model outputs for this release.

Entire remains enabled. Publication uses the normal Git hooks and checkpoint push workflow.
