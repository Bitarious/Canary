# Project release

The public research release uses the verified Canary source, MIT licensing for original code, and the existing experiment artifacts. Normal Git history and model archives remain intact. Entire integration and dedicated checkpoint refs have been removed.

## Publication status

During release preparation, the repository was private and `v2026.09.13` was a draft release. Public clone and anonymous artifact-download checks remain pending until publication. This page does not claim that the project is already public.

The release branch preserves the verified local evidence demo. The two later remote benchmark-inference commits remain separate. The current [architecture](architecture.md) describes what this release runs. The original `v2026.09.13` source snapshot predates those local evidence-view improvements.

See [release notes](../CHANGELOG.md), [release verification](release-audit.md), [contribution instructions](../CONTRIBUTING.md), and [security reporting](../SECURITY.md).

## Download the experiment artifacts

While the release is private or a draft, authenticate `gh` with an account that can read it. Once published, use the GitHub release page or CLI. Read [the model terms](model-licenses.md) before using the weights.

From the repository root, use a new destination directory:

```bash
mkdir -p artifacts/github-release/v2026.09.13
gh release download v2026.09.13 \
  --repo M-10001/EHL_Zurich_hackathon_team_piloty \
  --dir artifacts/github-release/v2026.09.13
(cd artifacts/github-release/v2026.09.13 && sha256sum -c SHA256SUMS)
```

After all checks pass, extract into a checkout without existing experiment artifacts:

```bash
for archive in artifacts/github-release/v2026.09.13/*-model.tar.gz; do
  tar -xzf "$archive"
done
tar -xzf artifacts/github-release/v2026.09.13/evaluation-evidence.tar.gz
```

The archives restore `artifacts/tslm/<run>/best.pt`, evaluation inputs, predictions, metrics, and notices. Fourteen selected checkpoints support fifteen evaluations. The dated radiator-valve follow-up reused the original weights. For that failed follow-up, restore its expected checkpoint path:

```bash
cp artifacts/tslm/valve-industrial-v1/best.pt \
  artifacts/tslm/valve-industrial-followup-v1/best.pt
```

Each selected checkpoint contains 682,889,851 bytes before compression. All fourteen total 9,560,457,914 bytes. The [release manifest](../results/2026-09-13/release-manifest.json) maps runs, archive sizes, and hashes. Use `gh release download --pattern` to select one component.

The archives include Gemma-derived tensors and required notices. They are not self-contained language models or small pure adapters. The [README CPU example](../README.md#2-replay-a-released-model-on-cpu) downloads the pinned dependencies and checks sixteen saved SSD predictions without training.

## Source release procedure

1. Commit the reviewed source and run `bash scripts/verify.sh` plus `npm run test:browser` from a fresh checkout.
2. Scan source history and release metadata for secrets. Verify all original archive hashes.
3. Review the source comparison with remote main. Preserve the verified evidence demo and normal Git history.
4. Publish an explicit source tag and release notes after publication approval.
5. Publish the existing experiment artifact draft without replacing its archives.
6. Verify clone, quick start, checksums, and model downloads with no team credentials.

Use [the reproduction guide](reproduction.md) for new training. No release step should start training or paid cloud resources. Public repository access does not make the local demo server a production web service.

## Data and history

The repository contains the public pilot, source catalogs, compact results, source code, and documentation. Large raw archives and prepared datasets remain separate publisher downloads. Credentials and machine telemetry stay outside Git.

The user chose to retain normal source history. Old commits can include historical machine paths, old plans, and references to Entire. Dedicated Entire checkpoint refs were removed. This does not claim removal from other clones or provider backups.
