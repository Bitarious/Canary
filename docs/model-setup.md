# Hugging Face and model readiness

Verified on 12 September 2026. Hugging Face browser sign-in completed as **Bitarious** using the official CLI in the project's WSL environment. Authentication state is stored in the WSL user's Hugging Face cache, outside the repository. No token should be pasted into chat or committed to source control.

| Dependency | Candidate and pinned revision | Last verified state |
|---|---|---|
| Selected temporal checkpoint | `OpenTSLM/gemma-3-270m-tsqa-sp` at `c97bd36131e07d53a7af9cd307eb3db628f9712f` | Authenticated weight metadata request succeeded; 26,423,633 bytes |
| Selected base language model | `google/gemma-3-270m` at `9b0cfec892e2bc2afd938c98eabe4e4a7b1e0ca1` | Authenticated weight metadata request succeeded; 536,223,056 bytes |
| Alternative temporal checkpoint | `OpenTSLM/llama-3.2-1b-tsqa-sp` at `1904441f0d87c458d6e9376de04ada5f4c9ab5b7` | Checkpoint metadata/weight access succeeded |
| Alternative base language model | `meta-llama/Llama-3.2-1B` at `4e20de362430cd3b72f300e6b0f18e50e7166e08` | Last request returned 403; user reports access review still pending |

The selected path is now Gemma-based OpenTSLM-SP. The [official repository](https://github.com/OpenTSLM/OpenTSLM) lists `google/gemma-3-270m` as supported, and the [matching checkpoint card](https://huggingface.co/OpenTSLM/gemma-3-270m-tsqa-sp) identifies a TSQA-trained soft-prompt model. Both weight endpoints were checked using the connected account. Only metadata/configuration and source files were downloaded during this check; no full model has been loaded, evaluated, or trained yet.

The [model selection file](../config/model.yaml) pins the Gemma base, its matching temporal checkpoint, and reviewed OpenTSLM source revision. Llama review can continue independently and is no longer the access dependency for the selected path. A temporal projector is specific to its base model's embedding dimensions; use the matching Gemma checkpoint when changing the base. Raw Gemma alone is a text model and does not replace OpenTSLM's numerical encoder and projector.

Source inspection confirms that the factory maps the selected repository name to `google/gemma-3-270m`. `OpenTSLMSP` freezes the base language model by default, leaving the numerical encoder and projector available for adaptation. The proposed initial training path keeps that configuration without LoRA; actual trainable parameters and compatibility still need a runtime check. Smaller base weights are useful for the pilot, but runtime cost and SMART-task quality have not been measured.

The upstream convenience factory does not expose revision arguments for both weight downloads. The model bridge must explicitly obtain the pinned artifacts and load those versions. The checkpoint card contains a copied Llama ID in its usage example, so use the selected Gemma ID above instead. First verify model loading and inference on development windows without updating weights, then provide the required overview before any training diagnostic or fine-tune.

The environment includes `huggingface-hub` through the `model-access` extra. If authentication expires, use the [official Hugging Face CLI browser flow](https://huggingface.co/docs/huggingface_hub/en/guides/cli) locally:

```bash
.venv/bin/hf auth login
.venv/bin/hf auth whoami
```

Before any training run, explain the task and why it is needed, actual data/splits, weights updated and frozen, hardware, estimated duration and cost, stopping conditions, evaluation, and saved artifacts. Begin with the smallest compatible temporal-module or adapter diagnostic after inspecting the loaded model and confirming gradients. Do not treat the $600 voucher as a target spend. Verify the remaining balance and current instance pricing before provisioning resources, set a run spending limit, and release billable resources when finished. No paid resource, training run, or learned artifact exists yet.
