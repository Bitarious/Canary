"""Pinned OpenTSLM-SP loader with answer-only loss and correct batch padding."""

from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download
import torch
from torch.nn.utils.rnn import pad_sequence

from driftops._vendor.opentslm.model.llm.OpenTSLMSP import OpenTSLMSP
from driftops.windows import read_yaml


def load_model(device: str = "cpu", checkpoint: str | Path | None = None, lora_config: dict | None = None):
    config = read_yaml("config/model.yaml")
    base = config["base_model"]
    temporal = config["temporal_checkpoint"]
    base_path = snapshot_download(base["repo_id"], revision=base["revision"], local_files_only=True)
    original = hf_hub_download(temporal["repo_id"], temporal["filename"],
                              revision=temporal["revision"], local_files_only=True)
    model = OpenTSLMSP(llm_id=base_path, device=device)
    state = torch.load(checkpoint or original, map_location=device, weights_only=True)
    model.encoder.load_state_dict(state["encoder_state"], strict=True)
    model.projector.load_state_dict(state["projector_state"], strict=True)
    adapter = state.get("lora_config") if state.get("lora_enabled", False) else lora_config
    if state.get("lora_enabled", False) and not adapter:
        raise ValueError("LoRA checkpoint is missing its adapter configuration")
    if adapter:
        from peft import get_peft_model_state_dict, set_peft_model_state_dict
        model.enable_lora(**adapter)
        model.driftops_lora_config = adapter
        if state.get("lora_enabled", False):
            expected = get_peft_model_state_dict(model.llm)
            if expected.keys() != state["lora_state"].keys() or any(expected[k].shape != state["lora_state"][k].shape for k in expected):
                raise ValueError("LoRA checkpoint does not match the configured adapter")
            restored = set_peft_model_state_dict(model.llm, state["lora_state"])
            if restored.unexpected_keys:
                raise ValueError("LoRA checkpoint contains unexpected parameters")
    model.llm.config.use_cache = False
    model.eval()
    return model


def collate(examples: list[dict]) -> list[dict]:
    # Explicit input keys prevent targets and audit metadata from entering prompts.
    return [{"pre_prompt": x["inputs"]["pre_prompt"],
             "post_prompt": x["inputs"]["post_prompt"],
             "time_series_text": list(x["inputs"]["time_series_text"]),
             "time_series": torch.tensor(x["inputs"]["time_series"], dtype=torch.float32)}
            for x in examples]


def training_tensors(model, examples):
    prompts, masks = model.pad_and_apply_batch(collate(examples))
    embeddings, labels = [], []
    for index, example in enumerate(examples):
        prompt = prompts[index, masks[index].bool()]
        ids = model.tokenizer(example["target"], add_special_tokens=False, return_tensors="pt").input_ids[0]
        ids = torch.cat([ids, ids.new_tensor([model.tokenizer.eos_token_id])]).to(model.device)
        answer = model.llm.get_input_embeddings()(ids)
        embeddings.append(torch.cat([prompt, answer]))
        labels.append(torch.cat([ids.new_full((len(prompt),), -100), ids]))
    inputs = pad_sequence(embeddings, batch_first=True)
    targets = pad_sequence(labels, batch_first=True, padding_value=-100)
    attention = pad_sequence([torch.ones(len(x), dtype=torch.long, device=model.device)
                              for x in embeddings], batch_first=True)
    return inputs, attention, targets


def loss(model, examples):
    inputs, attention, targets = training_tensors(model, examples)
    return model.llm(inputs_embeds=inputs, attention_mask=attention,
                     labels=targets, use_cache=False).loss


@torch.inference_mode()
def generate(model, examples, max_new_tokens=96):
    model.eval()
    inputs, masks = model.pad_and_apply_batch(collate(examples))
    # Decoder-only generation requires left padding for unequal prompt lengths.
    padded = torch.zeros_like(inputs)
    attention = torch.zeros_like(masks)
    for index in range(len(examples)):
        prompt = inputs[index, masks[index].bool()]
        padded[index, -len(prompt):] = prompt
        attention[index, -len(prompt):] = 1
    ids = model.llm.generate(inputs_embeds=padded, attention_mask=attention,
                             max_new_tokens=max_new_tokens, do_sample=False,
                             pad_token_id=model.tokenizer.pad_token_id,
                             eos_token_id=model.tokenizer.eos_token_id, use_cache=True)
    return model.tokenizer.batch_decode(ids, skip_special_tokens=True)


def temporal_state(model):
    result = {"encoder_state": {k: v.detach().cpu().clone() for k, v in model.encoder.state_dict().items()},
            "projector_state": {k: v.detach().cpu().clone() for k, v in model.projector.state_dict().items()},
            "lora_enabled": False}
    if model.lora_enabled:
        from peft import get_peft_model_state_dict
        result.update(lora_enabled=True, lora_config=model.driftops_lora_config,
                      lora_state={k: v.detach().cpu().clone() for k, v in get_peft_model_state_dict(model.llm).items()})
    return result
