"""Release a frozen test subset after training and evaluate numerical dependence."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np
import torch

from driftops.acquire import write_json
from driftops.annotations import describe_channel
from driftops.evaluate_tslm import metrics
from driftops.full_archive import file_hash
from driftops.full_training import heldout, window_files
from driftops.opentslm import generate, load_model
from driftops.tslm_dataset import input_hash, support


SUCCESS_CRITERIA = {
    "minimum_valid_output_rate": 0.95,
    "baseline_comparisons": ["starting", "constant"],
    "baseline_requirement": "Higher supported-class macro F1 and a positive lower 95% paired drive accuracy difference bound against each baseline.",
    "numerical_requirement": "A positive lower 95% paired drive accuracy difference bound against zero numerical input with unchanged text.",
    "counterfactual_requirement": "For both reversal and shuffle, a positive lower 95% accuracy gain bound over unchanged original predictions on at least 32 drives whose targets change.",
    "minimum_changed_target_drives": 32,
    "reload_equal_predictions": 16,
    "scope": "Weak-rule signal interpretation only. This gate does not establish failure prediction or maintenance benefit.",
}


def paired_interval(first, second):
    if len(first) != len(second):
        raise ValueError("Paired scores must have equal lengths")
    if not first:
        return None
    difference = np.asarray(first) - np.asarray(second)
    boot = np.mean(np.random.default_rng(42).choice(difference, size=(2000, len(difference)), replace=True), axis=1)
    return np.quantile(boot, [.025, .975]).tolist()


def counterfactual_evidence(original, changed, original_outputs, changed_outputs):
    if len({len(original), len(changed), len(original_outputs), len(changed_outputs)}) != 1:
        raise ValueError("Counterfactual records must have equal lengths")
    indices = [i for i, (a, b) in enumerate(zip(original, changed)) if a["target"] != b["target"]]
    result = {"changed_target_drives": len(indices), "accuracy_gain_over_unchanged_output_ci95": None}
    if indices:
        subset = [changed[i] for i in indices]
        actual = metrics(subset, [changed_outputs[i] for i in indices])
        unchanged = metrics(subset, [original_outputs[i] for i in indices])
        result.update({"actual_channel_accuracy": actual["channel_accuracy"],
                       "unchanged_output_channel_accuracy": unchanged["channel_accuracy"],
                       "accuracy_gain_over_unchanged_output_ci95": paired_interval(actual["per_drive_accuracy"], unchanged["per_drive_accuracy"])})
    return result


def success_checks(comparisons, intervals, reload_equal):
    trained = comparisons["finetuned"]
    checks = {"valid_outputs": trained["valid_output_rate"] >= SUCCESS_CRITERIA["minimum_valid_output_rate"],
              "checkpoint_reload": reload_equal == SUCCESS_CRITERIA["reload_equal_predictions"]}
    for baseline in SUCCESS_CRITERIA["baseline_comparisons"]:
        checks[f"better_than_{baseline}"] = bool(
            trained["macro_f1_supported_classes"] > comparisons[baseline]["macro_f1_supported_classes"]
            and intervals[baseline] is not None and intervals[baseline][0] > 0)
    checks["numerical_input_benefit"] = intervals["zero_numerical_embeddings"] is not None and intervals["zero_numerical_embeddings"][0] > 0
    for mode in ("reversed", "shuffled"):
        evidence = comparisons[mode]["counterfactual_evidence"]
        interval = evidence["accuracy_gain_over_unchanged_output_ci95"]
        checks[f"{mode}_target_response"] = bool(
            evidence["changed_target_drives"] >= SUCCESS_CRITERIA["minimum_changed_target_drives"]
            and interval is not None and interval[0] > 0)
    return {"passed": all(checks.values()), "checks": checks, "criteria": SUCCESS_CRITERIA}


def freeze(root, run):
    selection = json.loads((run / "selection.json").read_text())
    result = json.loads((run / "training-result.json").read_text())
    if not result["full_data_training_complete"] or selection["epoch"] < 1:
        raise ValueError("A complete training epoch is required before test release")
    if file_hash(run / "best.pt") != selection["sha256"]:
        raise ValueError("Selected checkpoint hash changed")
    output = run / "evaluation"
    output.mkdir(exist_ok=True)
    if (run / "test-release.json").exists():
        release = json.loads((run / "test-release.json").read_text())
        if release["checkpoint_sha256"] != selection["sha256"] or file_hash(output / "test.json") != release["test_sha256"]:
            raise ValueError("Frozen test release changed")
        return
    manifest = json.loads((run / "dataset-manifest.json").read_text())
    config = json.loads((run / "config.json").read_text())
    # Write the protocol before reading held-out numerical values or targets.
    write_json(output / "protocol.json", {
        "checkpoint_sha256": selection["sha256"], "selected_completed_epoch": selection["epoch"],
        "test_drives": config["test_drives"], "selection": "Distinct test serials and one window per serial, selected by fixed hashes without target inspection.",
        "comparisons": ["starting", "finetuned", "constant", "deterministic_rules", "zero_numerical_embeddings", "reversed", "shuffled"],
        "primary": "Strict free-text channel accuracy, exact-window accuracy, and macro F1 over supported classes. Report every class denominator and invalid output rate.",
        "ablations": "Zero only normalized numerical values while retaining all text. Reverse or shuffle each observed window while retaining channel scale statistics. Recompute weak targets for reversed and shuffled observations.",
        "uncertainty": "2000 paired drive bootstrap samples, seed 42, for accuracy differences against starting, constant, and zero-input models. Counterfactual gains use only drives whose targets change and compare against unchanged original predictions.",
        "success_criteria": SUCCESS_CRITERIA,
        "concept_scope": "Agreement with weak SMART description rules on unseen devices and later dates. Check temporal dependence separately. This does not validate failure prediction or physical failure causes.",
        "generation": {"do_sample": False, "max_new_tokens": 128, "batch_size": 16},
        "time_limit_seconds": 7200,
    })
    for path in window_files(root, "test", manifest):
        if file_hash(path) != manifest["shards"][path.parent.name][path.name]:
            raise ValueError("Test dataset checksum changed")
    examples = heldout(root, manifest, "test", config["test_drives"])
    if len(examples) != config["test_drives"]:
        raise ValueError("Not enough independent test devices")
    test_ids = {e["audit"]["drive_id"] for e in examples}
    if any(test_ids & set(manifest["drives"][s]) for s in ("train", "validation", "calibration")):
        raise ValueError("Test devices overlap a development split")
    write_json(output / "test.json", examples)
    write_json(run / "test-release.json", {"checkpoint_sha256": selection["sha256"],
               "test_sha256": file_hash(output / "test.json"), "protocol_sha256": file_hash(output / "protocol.json"),
               "released_at": datetime.now(timezone.utc).isoformat(), "further_training_allowed": False})
    print(json.dumps({"frozen_test_drives": len(examples), "checkpoint_sha256": selection["sha256"]}), flush=True)


def perturb(examples, mode):
    altered = deepcopy(examples)
    rng = np.random.default_rng(612)
    for item in altered:
        values = np.asarray(item["inputs"]["time_series"])
        raw = np.asarray(item["raw_values"])
        if mode == "zero_numerical_embeddings":
            item["inputs"]["time_series"] = np.zeros_like(values).tolist()
        else:
            order = np.arange(27, -1, -1) if mode == "reversed" else rng.permutation(28)
            item["inputs"]["time_series"] = values[:, order].tolist()
            item["raw_values"] = raw[:, order].tolist()
            channels = [t.split(";",1)[0] for t in item["inputs"]["time_series_text"]]
            item["target"] = "; ".join(f"{c}: {describe_channel(c, v)['pattern']}" for c, v in zip(channels, raw[:,order])) + "."
    return altered


def predictions(model, examples, directory, checkpoint_hash):
    directory.mkdir(exist_ok=True)
    outputs = []
    elapsed = 0.
    for start in range(0, len(examples), 16):
        batch = examples[start:start+16]
        path = directory / f"batch-{start:06d}.json"
        hashes = [input_hash(e["inputs"]) for e in batch]
        if path.exists():
            record = json.loads(path.read_text())
            if record["input_hashes"] != hashes or record["checkpoint_sha256"] != checkpoint_hash or len(record["outputs"]) != len(batch):
                raise ValueError("Cached evaluation batch belongs to another input or checkpoint")
        else:
            before = time.monotonic()
            result = generate(model, batch, max_new_tokens=128)
            record = {"checkpoint_sha256": checkpoint_hash, "input_hashes": hashes,
                      "outputs": result, "seconds": time.monotonic()-before,
                      "audits": [e["audit"] for e in batch], "targets": [e["target"] for e in batch]}
            write_json(path, record)
        outputs.extend(record["outputs"])
        elapsed += record["seconds"]
        if start % 256 == 0:
            print(json.dumps({"comparison": directory.name, "windows": len(outputs), "of": len(examples)}), flush=True)
    return outputs, elapsed


def comparison(run, mode, device="cuda"):
    """Generate one frozen comparison in a separate process and GPU."""
    if mode not in ("starting", "finetuned", "zero_numerical_embeddings", "reversed", "shuffled"):
        raise ValueError("The evaluation comparison is unsupported.")
    release = json.loads((run / "test-release.json").read_text())
    output = run / "evaluation"
    for path, expected in ((run / "best.pt", release["checkpoint_sha256"]),
                           (output / "test.json", release["test_sha256"]),
                           (output / "protocol.json", release["protocol_sha256"])):
        if file_hash(path) != expected:
            raise ValueError("A frozen evaluation artifact changed.")
    protocol = json.loads((output / "protocol.json").read_text())
    if protocol["success_criteria"] != SUCCESS_CRITERIA:
        raise ValueError("Success criteria changed after test release.")
    limit = protocol["time_limit_seconds"]
    if type(limit) is not int or not 1 <= limit <= 7200:
        raise ValueError("Evaluation requires a time limit of at most two hours.")
    examples = json.loads((output / "test.json").read_text())
    if mode not in ("starting", "finetuned"):
        if protocol.get("dataset_kind") == "component-windows-v1":
            from driftops.component_training import perturb as component_perturb
            examples = component_perturb(examples, mode, protocol["component_config"])
        else:
            examples = perturb(examples, mode)

    def timeout(*_):
        raise TimeoutError("The declared evaluation time limit was reached.")

    with (output / f"{mode}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(limit)
        try:
            torch.set_num_threads(8)
            torch.manual_seed(20260912)
            model = load_model(device, checkpoint=None if mode == "starting" else run / "best.pt")
            digest = "pinned-upstream" if mode == "starting" else release["checkpoint_sha256"]
            outputs, elapsed = predictions(model, examples, output / mode, digest)
            write_json(output / f"{mode}-complete.json", {"comparison": mode, "windows": len(outputs),
                       "checkpoint_sha256": digest, "test_sha256": release["test_sha256"],
                       "protocol_sha256": release["protocol_sha256"], "generation_seconds": elapsed})
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)


def evaluate(run, device="cuda"):
    release = json.loads((run / "test-release.json").read_text())
    output = run / "evaluation"
    if file_hash(run / "best.pt") != release["checkpoint_sha256"] or file_hash(output / "test.json") != release["test_sha256"]:
        raise ValueError("Checkpoint or test file changed after release")
    if file_hash(output / "protocol.json") != release["protocol_sha256"]:
        raise ValueError("Evaluation protocol changed after test release")
    protocol = json.loads((output / "protocol.json").read_text())
    if protocol["success_criteria"] != SUCCESS_CRITERIA:
        raise ValueError("Success criteria changed after test release")
    component = protocol.get("dataset_kind") == "component-windows-v1"
    if component:
        from driftops.component_training import perturb as component_perturb
    time_limit = protocol.get("time_limit_seconds", 7200)
    if type(time_limit) is not int or not 1 <= time_limit <= 7200:
        raise ValueError("Evaluation must have a valid time limit of at most two hours.")
    examples = json.loads((output / "test.json").read_text())
    torch.set_num_threads(8)
    torch.manual_seed(20260912)
    model = load_model(device)
    comparisons, generated = {}, {}
    started = time.monotonic()

    def timeout(*_):
        raise TimeoutError("The declared evaluation time limit was reached.")
    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(time_limit)
    try:
        generated["starting"], elapsed = predictions(model, examples, output / "starting", "pinned-upstream")
        comparisons["starting"] = metrics(examples, generated["starting"]) | {"generation_seconds": elapsed}
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        model = load_model(device, checkpoint=run / "best.pt")
        generated["finetuned"], elapsed = predictions(model, examples, output / "finetuned", release["checkpoint_sha256"])
        comparisons["finetuned"] = metrics(examples, generated["finetuned"]) | {"generation_seconds": elapsed}
        for mode in ("zero_numerical_embeddings", "reversed", "shuffled"):
            changed = (component_perturb(examples, mode, protocol["component_config"])
                       if component else perturb(examples, mode))
            outputs, elapsed = predictions(model, changed, output / mode, release["checkpoint_sha256"])
            score = metrics(changed, outputs)
            score["generation_seconds"] = elapsed
            score["output_changed_fraction"] = sum(a != b for a,b in zip(outputs,generated["finetuned"])) / len(examples)
            if mode != "zero_numerical_embeddings":
                score["counterfactual_evidence"] = counterfactual_evidence(examples, changed, generated["finetuned"], outputs)
            comparisons[mode] = score
        constants = ["; ".join(f"{t.split(';',1)[0]}: constant" for t in e["inputs"]["time_series_text"])+"." for e in examples]
        comparisons["constant"] = metrics(examples, constants)
        comparisons["deterministic_rules"] = metrics(examples, [e["target"] for e in examples])
        intervals = {}
        for baseline in ("constant", "starting", "zero_numerical_embeddings"):
            intervals[baseline] = paired_interval(comparisons["finetuned"]["per_drive_accuracy"], comparisons[baseline]["per_drive_accuracy"])
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        model = load_model(device, checkpoint=run / "best.pt")
        reloaded = generate(model, examples[:16], max_new_tokens=128)
        if reloaded != generated["finetuned"][:16]:
            raise ValueError("Reloaded checkpoint changed held-out predictions")
        report = {"support": support(examples), "comparisons": comparisons,
                  "paired_drive_accuracy_difference_ci95": intervals,
                  "success_gate": success_checks(comparisons, intervals, 16),
                  "selected_checkpoint_sha256": release["checkpoint_sha256"], "reload_predictions_equal": 16,
                  "seconds": time.monotonic()-started,
                  "interpretation_limit": "Weak-rule agreement and numerical dependence. No expert labels, calibrated failure forecast, or physical failure-cause validation."}
        write_json(output / "metrics.json", report)
        print(json.dumps({"finetuned_macro_f1": comparisons["finetuned"]["macro_f1_supported_classes"],
                          "constant_macro_f1": comparisons["constant"]["macro_f1_supported_classes"],
                          "zero_output_changed_fraction": comparisons["zero_numerical_embeddings"]["output_changed_fraction"],
                          "success_gate_passed": report["success_gate"]["passed"],
                          "reload_predictions_equal": 16}), flush=True)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "evaluate", "comparison"])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("data/backblaze-full"))
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--comparison", choices=["starting", "finetuned", "zero_numerical_embeddings", "reversed", "shuffled"])
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.root,args.run)
    elif args.action == "comparison":
        if args.comparison is None:
            parser.error("A comparison name is required.")
        comparison(args.run, args.comparison, args.device)
    else:
        evaluate(args.run,args.device)
