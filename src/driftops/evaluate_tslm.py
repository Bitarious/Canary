"""Frozen held-out comparison of generated SMART descriptions."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import time

import numpy as np
import torch

from driftops.cli import checksum
from driftops.opentslm import generate, load_model
from driftops.structured_tslm import generate_structured
from driftops.train_tslm import write_json
from driftops.tslm_dataset import input_hash, load_examples, PATTERNS, support


def parse_answer(text, channels):
    parsed = {}
    for entry in text.strip().rstrip(".").split(";"):
        if ":" not in entry:
            return None
        channel, pattern = (part.strip() for part in entry.split(":", 1))
        if channel not in channels or channel in parsed or pattern not in PATTERNS:
            return None
        parsed[channel] = pattern
    return parsed if set(parsed) == set(channels) else None


def metrics(examples, predictions):
    if len(predictions) != len(examples):
        raise ValueError("Prediction count does not match the evaluation set")
    gold, predicted, valid, exact = [], [], 0, 0
    changed_tp = changed_fp = changed_fn = 0
    per_drive_accuracy = []
    for example, text in zip(examples, predictions):
        channels = [x.split(";", 1)[0] for x in example["inputs"]["time_series_text"]]
        target = parse_answer(example["target"], channels)
        answer = parse_answer(text, channels)
        if target is None:
            raise ValueError("Evaluation target violates the frozen output rubric")
        valid += answer is not None
        exact += answer == target
        correct = 0
        for channel in channels:
            actual = target[channel]
            observed = answer[channel] if answer else "INVALID"
            gold.append(actual)
            predicted.append(observed)
            correct += actual == observed
            actual_changed = actual != "constant"
            reported_changed = observed not in {"constant", "INVALID"}
            changed_tp += actual_changed and reported_changed
            changed_fp += not actual_changed and reported_changed
            changed_fn += actual_changed and not reported_changed
        per_drive_accuracy.append(correct / len(channels))
    classes = {}
    for name in PATTERNS:
        tp = sum(a == name and b == name for a, b in zip(gold, predicted))
        fp = sum(a != name and b == name for a, b in zip(gold, predicted))
        fn = sum(a == name and b != name for a, b in zip(gold, predicted))
        count = gold.count(name)
        classes[name] = {"support": count, "precision": tp / (tp + fp) if tp + fp else 0,
                         "recall": tp / (tp + fn) if tp + fn else 0,
                         "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0}
    supported = [value["f1"] for value in classes.values() if value["support"]]
    return {"windows": len(examples), "channel_labels": len(gold),
            "valid_output_rate": valid / len(examples), "exact_window_accuracy": exact / len(examples),
            "channel_accuracy": sum(a == b for a, b in zip(gold, predicted)) / len(gold),
            "macro_f1_supported_classes": sum(supported) / len(supported),
            "classes": classes,
            "changed_channel_precision": changed_tp / (changed_tp + changed_fp) if changed_tp + changed_fp else 0,
            "changed_channel_recall": changed_tp / (changed_tp + changed_fn) if changed_tp + changed_fn else 0,
            "invalid_outputs": len(examples) - valid, "per_drive_accuracy": per_drive_accuracy}


def predict(model, examples, batch_size, max_tokens, output_path, structured=False):
    if output_path.exists():
        raise ValueError("Evaluation predictions already exist. Do not overwrite a held-out result")
    predictions, times = [], []
    with output_path.open("x", buffering=1) as stream:
        for index in range(0, len(examples), batch_size):
            batch = examples[index:index + batch_size]
            start = time.monotonic()
            outputs = (generate_structured if structured else generate)(model, batch, max_tokens)
            elapsed = time.monotonic() - start
            for example, output in zip(batch, outputs):
                stream.write(json.dumps({"audit": example["audit"], "target": example["target"],
                                         "output": output, "batch_seconds": elapsed}) + "\n")
            predictions.extend(outputs)
            times.append(elapsed)
            print(json.dumps({"file": output_path.name, "completed": len(predictions),
                              "batch_seconds": elapsed}), flush=True)
    return predictions, {"total_generation_seconds": sum(times),
                         "amortized_seconds_per_window": sum(times) / len(examples),
                         "batch_size": batch_size}


def evaluate(run):
    overview = json.loads((run / "overview.json").read_text())
    config = overview["config"]
    if overview["mode"] != "concept-finetune":
        raise ValueError("The tiny-batch diagnostic is not a held-out evaluation")
    result = json.loads((run / "result.json").read_text())
    if checksum(run / "best.pt") != result["selected_checkpoint_sha256"]:
        raise ValueError("The selected model changed after training")
    output_dir = run / "evaluation"
    output_dir.mkdir(exist_ok=False)
    # Freeze this protocol before reading any held-out target.
    write_json(output_dir / "protocol.json", {
        "checkpoint_sha256": checksum(run / "best.pt"), "test_windows": config["test_windows"],
        "selection": "One window per distinct test drive by fixed task hash, independent of targets.",
        "parser": "Exact channel and pattern allowlist; the entire invalid answer receives zero credit.",
        "primary": "Macro-F1 over classes with held-out support; report every class denominator.",
        "comparisons": ["starting", "finetuned", "finetuned_zero_series", "constant", "deterministic_rules"],
        "secondary_comparisons": ["starting_structured", "finetuned_structured", "finetuned_structured_zero_series"],
        "secondary_grammar": "Greedy decoding over the 625 combinations of five patterns for four fixed channel names. No measured trend rule chooses the patterns. Validity is enforced by the grammar, not learned.",
        "secondary_reason": "A development-only validation sample invented channel names. Retain all free-text scores and separately test pattern selection under fixed syntax.",
        "ablation": "Replace every normalized numerical channel with zero while keeping all text fixed.",
        "uncertainty": "2000 paired bootstrap samples of distinct drives, seed 42, for accuracy improvement.",
        "interval": "The whole 28-day window is fixed in the prompt. No event-localization score.",
        "limitations": "Weak-rule agreement, not expert validation, failure prediction, or a calibrated risk estimate.",
    })
    examples = load_examples("test", config["test_windows"])
    for name in ("train", "validation"):
        earlier = json.loads((run / f"{name}.json").read_text())
        if {x["audit"]["drive_id"] for x in earlier} & {x["audit"]["drive_id"] for x in examples}:
            raise ValueError("Evaluation drives overlap development drives")
    write_json(output_dir / "test.json", examples)
    torch.set_num_threads(config["threads"])
    torch.manual_seed(config["seed"])
    model = load_model(config["device"])
    comparisons = {}
    for name in ("starting", "starting_structured", "finetuned", "finetuned_structured",
                 "finetuned_zero_series", "finetuned_structured_zero_series"):
        if name == "finetuned":
            state = torch.load(run / "best.pt", weights_only=True, map_location=config["device"])
            model.encoder.load_state_dict(state["encoder_state"], strict=True)
            model.projector.load_state_dict(state["projector_state"], strict=True)
        inputs = deepcopy(examples)
        if name.endswith("zero_series"):
            for example in inputs:
                example["inputs"]["time_series"] = [[0.0] * len(x) for x in example["inputs"]["time_series"]]
                example["audit"]["original_input_hash"] = example["audit"]["input_hash"]
                example["audit"]["input_hash"] = input_hash(example["inputs"])
        predictions, latency = predict(model, inputs, config["batch_size"], config["max_new_tokens"],
                                       output_dir / f"{name}.jsonl", structured="structured" in name)
        comparisons[name] = metrics(examples, predictions) | {"latency": latency}
    rules = [x["target"] for x in examples]
    constants = ["; ".join(f"{text.split(';', 1)[0]}: constant" for text in x["inputs"]["time_series_text"]) + "." for x in examples]
    comparisons["deterministic_rules"] = metrics(examples, rules)
    comparisons["constant"] = metrics(examples, constants)
    difference = np.array(comparisons["finetuned"]["per_drive_accuracy"]) - np.array(comparisons["starting"]["per_drive_accuracy"])
    rng = np.random.default_rng(42)
    boot = np.mean(rng.choice(difference, size=(2000, len(difference)), replace=True), axis=1)
    report = {"support": support(examples), "comparisons": comparisons,
              "paired_channel_accuracy_improvement_ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
              "checkpoint_sha256": checksum(run / "best.pt"),
              "interpretation_limit": "The rules also generated the targets. Their perfect score is by construction. No independent expert labels or failure forecast were tested."}
    write_json(output_dir / "metrics.json", report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    evaluate(parser.parse_args().run)
