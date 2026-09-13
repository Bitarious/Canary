"""Streaming historical windows and memory-bounded answer-token loss."""

import hashlib
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import torch
from torch.utils.checkpoint import checkpoint

from driftops.opentslm import training_tensors
from driftops.tslm_dataset import PATTERNS, prepare_input


def example(row):
    values = np.asarray(row["values"], dtype=np.float64)
    inputs = prepare_input({"time_series": values,
                            "time_series_text": [c + "; raw source units" for c in row["channels"]]})
    # Causal scale metadata makes the rule's one-raw-unit band identifiable after z-scoring.
    inputs["time_series_text"] = [f"{c}; daily observations; original standard deviation: {std:.8g}."
                                  for c, std in zip(row["channels"], values.std(axis=1, ddof=1))]
    return {"inputs": inputs, "target": row["target"], "raw_values": values.tolist(), "audit": {
        "task_id": row["task_id"], "drive_id": row["drive_id"],
        "start": row["start"].isoformat(), "cutoff": row["cutoff"].isoformat()}}


def window_files(root, split, manifest):
    if split not in {"train", "validation", "calibration", "test"}:
        raise ValueError("Unknown dataset split")
    return [Path(root) / "prepared" / b / (split + ".parquet") for b in sorted(manifest["shards"])]


def raw_batches(root, manifest, batch_size, seed, cursor=None):
    """Visit every training row once, with deterministic shard and row-group shuffles."""
    rng = np.random.default_rng(seed)
    files = window_files(root, "train", manifest)
    rng.shuffle(files)
    resume = cursor or {"file": 0, "group": 0, "batch": 0}
    for fi, file in enumerate(files):
        parquet = pq.ParquetFile(file)
        groups = list(range(parquet.num_row_groups))
        np.random.default_rng(seed + fi + 1).shuffle(groups)
        if fi < resume["file"]:
            continue
        for gi, group in enumerate(groups):
            if fi == resume["file"] and gi < resume["group"]:
                continue
            rows = parquet.read_row_group(group).to_pylist()
            np.random.default_rng(seed + 100000 * fi + gi + 1).shuffle(rows)
            for bi, start in enumerate(range(0, len(rows), batch_size)):
                if fi == resume["file"] and gi == resume["group"] and bi < resume["batch"]:
                    continue
                yield rows[start:start+batch_size], {"file": fi, "group": gi, "batch": bi + 1}


def batches(root, manifest, batch_size, seed, cursor=None):
    for rows, position in raw_batches(root, manifest, batch_size, seed, cursor):
        yield [example(row) for row in rows], position


def heldout(root, manifest, split, limit):
    """Pick distinct devices and one window each by hashes, without reading targets for selection."""
    selected = sorted(manifest["drives"][split], key=lambda d: hashlib.sha256(("full-heldout-v1:"+d).encode()).digest())[:limit]
    wanted = set(selected)
    chosen = {}
    for path in window_files(root, split, manifest):
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=8192):
            for row in batch.to_pylist():
                drive = row["drive_id"]
                if drive not in wanted:
                    continue
                key = hashlib.sha256(("full-window-v1:" + row["task_id"]).encode()).digest()
                if drive not in chosen or key < chosen[drive][0]:
                    chosen[drive] = (key, row)
    if len(chosen) != len(selected):
        raise ValueError("Held-out drive inventory does not match the prepared windows")
    return [example(chosen[d][1]) for d in selected]


def class_weights(manifest):
    counts = {p: manifest["audit"].get("patterns_train:"+p, 0) for p in PATTERNS}
    total = sum(counts.values())
    if not total:
        raise ValueError("The dataset has no training targets")
    return {p: float(np.clip(total/(len(PATTERNS)*max(n, 1)), .1, 30)) for p, n in counts.items()}


def answer_weights(model, examples, labels, pattern_weights):
    weights = torch.zeros_like(labels, dtype=torch.float32)
    for index, item in enumerate(examples):
        target = item["target"]
        encoding = model.tokenizer(target, add_special_tokens=False, return_offsets_mapping=True)
        spans = []
        offset = 0
        for entry in target.rstrip(".").split("; "):
            pattern = entry.split(": ",1)[1]
            spans.append((offset, offset + len(entry), pattern_weights[pattern]))
            offset += len(entry) + 2
        token_weights = []
        for left, right in encoding["offset_mapping"]:
            matched = [weight for start, stop, weight in spans if left < stop and right > start]
            token_weights.append(matched[0] if matched else 1.)
        token_weights.append(1.)
        selected = labels[index] != -100
        if int(selected.sum()) != len(token_weights):
            raise ValueError("Answer weighting does not match the tokenizer")
        weights[index, selected] = torch.tensor(token_weights, device=labels.device)
    return weights


def compact_loss(model, examples, pattern_weights=None, chunk_tokens=256, return_normalizer=False):
    """Compute logits only for answer positions. Recompute chunks during backward to bound memory."""
    inputs, attention, labels = training_tensors(model, examples)
    base = model.llm.get_base_model() if model.lora_enabled else model.llm
    hidden = base.model(inputs_embeds=inputs, attention_mask=attention, use_cache=False).last_hidden_state
    mask = labels[:, 1:] != -100
    states = hidden[:, :-1][mask]
    targets = labels[:, 1:][mask]
    weights = (answer_weights(model, examples, labels, pattern_weights)[:, 1:][mask]
               if pattern_weights else torch.ones(len(targets), device=states.device))

    def token_loss(features, target, weight):
        logits = base.lm_head(features)
        cap = base.config.final_logit_softcapping
        if cap is not None:
            logits = torch.tanh(logits / cap) * cap
        return (torch.nn.functional.cross_entropy(logits.float(), target, reduction="none") * weight).sum()

    total = states.new_zeros((), dtype=torch.float32)
    for start in range(0, len(targets), chunk_tokens):
        args = (states[start:start+chunk_tokens], targets[start:start+chunk_tokens], weights[start:start+chunk_tokens])
        total = total + (checkpoint(token_loss, *args, use_reentrant=False) if torch.is_grad_enabled() else token_loss(*args))
    normalizer = weights.sum()
    result = total / normalizer
    return (result, normalizer.detach()) if return_normalizer else result
