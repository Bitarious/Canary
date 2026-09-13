"""Constrain channel names and syntax while the model selects signal patterns."""

from itertools import product

import torch

from driftops.opentslm import collate
from driftops.tslm_dataset import PATTERNS


def answer_trie(tokenizer, channels):
    answers = ["; ".join(f"{channel}: {pattern}" for channel, pattern in zip(channels, patterns)) + "."
               for patterns in product(PATTERNS, repeat=len(channels))]
    tokenized = tokenizer(answers, add_special_tokens=False).input_ids
    root = {}
    for tokens in tokenized:
        node = root
        for token in [*tokens, tokenizer.eos_token_id]:
            node = node.setdefault(token, {})
    return root


@torch.inference_mode()
def generate_structured(model, examples, max_new_tokens=96):
    model.eval()
    inputs, masks = model.pad_and_apply_batch(collate(examples))
    padded = torch.zeros_like(inputs)
    attention = torch.zeros_like(masks)
    tries = []
    by_channels = {}
    for index, example in enumerate(examples):
        prompt = inputs[index, masks[index].bool()]
        padded[index, -len(prompt):] = prompt
        attention[index, -len(prompt):] = 1
        channels = tuple(text.split(";", 1)[0] for text in example["inputs"]["time_series_text"])
        if channels not in by_channels:
            by_channels[channels] = answer_trie(model.tokenizer, channels)
        tries.append(by_channels[channels])

    def allowed_tokens(batch_id, prefix):
        node = tries[batch_id]
        for token in prefix.tolist():
            if token in {model.tokenizer.eos_token_id, model.tokenizer.pad_token_id}:
                return [model.tokenizer.eos_token_id]
            if token not in node:
                raise ValueError("Generated prefix is outside the declared answer grammar")
            node = node[token]
        return list(node) or [model.tokenizer.eos_token_id]

    ids = model.llm.generate(inputs_embeds=padded, attention_mask=attention,
                             prefix_allowed_tokens_fn=allowed_tokens,
                             max_new_tokens=max_new_tokens, do_sample=False, use_cache=True,
                             pad_token_id=model.tokenizer.pad_token_id,
                             eos_token_id=model.tokenizer.eos_token_id)
    return model.tokenizer.batch_decode(ids, skip_special_tokens=True)
