# Model setup

The recorded experiments use Gemma 3 270M with the matching OpenTSLM-SP checkpoint. Model access is separate from the GPU training environment.

| Dependency | Pinned revision |
| --- | --- |
| `google/gemma-3-270m` | `9b0cfec892e2bc2afd938c98eabe4e4a7b1e0ca1` |
| `OpenTSLM/gemma-3-270m-tsqa-sp` | `c97bd36131e07d53a7af9cd307eb3db628f9712f` |
| OpenTSLM source | `2968f4b891baab4307f7e9d0043e87677b593a30` |

`config/model.yaml` records these pins. The loader requires both model downloads in the local Hugging Face cache. It does not silently download a newer revision.

For CPU inference:

```bash
uv sync --locked --extra training --extra model-access
uv run --no-sync hf auth login
uv run --no-sync hf download google/gemma-3-270m \
  --revision 9b0cfec892e2bc2afd938c98eabe4e4a7b1e0ca1
uv run --no-sync hf download OpenTSLM/gemma-3-270m-tsqa-sp model_checkpoint.pt \
  --revision c97bd36131e07d53a7af9cd307eb3db628f9712f
```

Accept the applicable upstream terms through the provider's normal account flow. Keep credentials in local CLI storage. Do not paste credentials into source, issues, or logs.

Download a selected project checkpoint through [the release guide](project-release.md). Follow [the README replay example](../README.md#2-replay-a-released-model-on-cpu) to check saved predictions. The model loader needs the repository root as its working directory.

Use `--extra nebius-training` instead of `--extra training` for the CUDA environment. These extras conflict by design. Follow [the reproduction guide](reproduction.md) before any new training run.

The successful component models update the encoder, projector, and rank-8 attention LoRA. Original Gemma weights remain frozen. The earlier CPU concept updated only temporal modules and failed useful numerical dependence. See [component results](component-model-results.md) and [the concept evaluation](evaluation.md).
