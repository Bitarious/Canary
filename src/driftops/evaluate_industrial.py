"""Evaluate small industrial studies with independent-group uncertainty."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import heapq
from itertools import product
import json
from pathlib import Path
import signal
import time

import numpy as np
import pyarrow.parquet as pq
import torch

from driftops.acquire import write_json
from driftops.component_data import example
from driftops.component_training import perturb
from driftops.evaluate_full import predictions, paired_interval
from driftops.evaluate_tslm import metrics
from driftops.full_archive import file_hash
from driftops.full_training import window_files
from driftops.opentslm import load_model, generate


CRITERIA = {
    "scope": "Small-cohort signal interpretation. No large-cohort reliability or failure-prediction claim.",
    "minimum_valid_output_rate": .95,
    "test_groups": 5,
    "windows_per_group": 256,
    "minimum_changed_windows_per_group": 32,
    "baseline_requirement": "Higher supported-class macro F1, positive lower 95% group-bootstrap accuracy gain, and one-sided exact paired group sign-randomization probability at most 0.05.",
    "baselines": ["starting", "constant", "zero_numerical_embeddings"],
    "counterfactual_requirement": "Reversal and shuffle must each change at least 32 targets in every held-out group. Require positive lower group-bootstrap gain and exact paired sign-randomization probability at most 0.05 over unchanged original answers.",
    "reload_equal_predictions": 16,
}


def audio_criteria(component="slide_rail"):
    if component not in ("slide_rail", "valve"):
        raise ValueError("The sound evaluation component is unsupported.")
    label = "Slide-rail" if component == "slide_rail" else "Industrial-valve"
    return {**CRITERIA, "windows_per_group": 1024,
            "scope": label + " sound description benchmark with unknown acquisition dates, one training machine, one validation machine, and five test machines. No calendar generalization or fault-detection claim."}


def heldout_many(root, manifest, split, limit):
    selected = {group: [] for group in manifest["groups"][split]}
    for path in window_files(root, split, manifest):
        for batch in pq.ParquetFile(path).iter_batches(batch_size=2048):
            for row in batch.to_pylist():
                key = int.from_bytes(hashlib.sha256(("industrial-heldout-v1:" + row["task_id"]).encode()).digest(), "big")
                heap = selected[row["group_id"]]
                heapq.heappush(heap, (-key, row["task_id"], row))
                if len(heap) > limit:
                    heapq.heappop(heap)
    return [example(row, manifest["config"]) for group in sorted(selected)
            for _, _, row in sorted(selected[group], reverse=True)]


def group_values(examples, scores):
    if len(examples) != len(scores):
        raise ValueError("Industrial scores must match their input windows.")
    values = defaultdict(list)
    for item, score in zip(examples, scores):
        if not np.isfinite(score):
            raise ValueError("An industrial accuracy value is not finite.")
        values[item["audit"]["group_id"]].append(float(score))
    return {g: float(np.mean(v)) for g,v in sorted(values.items())}


def evidence(examples, fitted, baseline):
    a, b = group_values(examples, fitted), group_values(examples, baseline)
    if not 1 <= len(a) <= 12:
        raise ValueError("Exact small-study inference requires one to twelve groups.")
    delta = np.asarray([a[g] - b[g] for g in a])
    observed = float(delta.mean())
    probability = sum(float(np.mean(delta * signs)) >= observed - 1e-12
                      for signs in product((-1, 1), repeat=len(delta))) / (2 ** len(delta))
    interval = paired_interval(list(a.values()), list(b.values()))
    return {"groups": len(a), "group_accuracy_gain": dict(zip(a, delta.tolist())),
            "accuracy_gain_ci95": interval, "one_sided_exact_group_sign_probability": probability,
            "passed": len(a) == 5 and interval[0] > 0 and probability <= .05}


def freeze(root, run, *, audio_benchmark=False):
    selection = json.loads((run / "selection.json").read_text())
    terminal = json.loads((run / "training-result.json").read_text())
    if not terminal["full_data_training_complete"] or selection["epoch"] < 1 or file_hash(run / "best.pt") != selection["sha256"]:
        raise ValueError("The industrial study lacks a verified completed-epoch checkpoint.")
    output = run / "evaluation"
    output.mkdir(exist_ok=True)
    if (run / "test-release.json").exists():
        release = json.loads((run / "test-release.json").read_text())
        if (release["checkpoint_sha256"] != selection["sha256"] or file_hash(output / "test.json") != release["test_sha256"]
                or file_hash(output / "protocol.json") != release["protocol_sha256"]):
            raise ValueError("The frozen industrial study changed.")
        return
    manifest = json.loads((run / "dataset-manifest.json").read_text())
    kind = manifest["config"].get("study") if audio_benchmark else "small-industrial-v1"
    criteria = audio_criteria(manifest["config"]["component"]) if audio_benchmark else CRITERIA
    limit = criteria["windows_per_group"]
    if audio_benchmark:
        from driftops.slider_data import validate_config
        validate_config(manifest["config"])
    if manifest["config"].get("study") != kind or len(manifest["groups"]["test"]) != 5:
        raise ValueError("The industrial study must preserve five held-out groups.")
    write_json(output / "protocol.json", {"dataset_kind": kind, "component_config": manifest["config"],
        "dataset_manifest_sha256": file_hash(run / "dataset-manifest.json"), "checkpoint_sha256": selection["sha256"],
        "selected_completed_epoch": selection["epoch"], "success_criteria": criteria,
        "selection": f"Up to {limit} fixed-hash windows per independent test group, without target-based selection.",
        "generation": {"do_sample": False, "max_new_tokens": 128, "batch_size": 16}, "time_limit_seconds": 3600,
        "uncertainty": "First average accuracy within each group. Use 2000 paired group bootstrap samples, seed42, and all32 paired group sign assignments. Windows and nearby devices are not independent groups."})
    for path in window_files(root, "test", manifest):
        if file_hash(path) != manifest["shards"][path.parent.name][path.name]:
            raise ValueError("An industrial test shard changed.")
    examples = heldout_many(root, manifest, "test", limit)
    groups = {item["audit"]["group_id"] for item in examples}
    devices = {item["audit"]["drive_id"] for item in examples}
    if len(groups) != 5:
        raise ValueError("The industrial study lacks all five test groups.")
    for split in ("train", "validation", "calibration"):
        if groups.intersection(manifest["groups"][split]) or devices.intersection(manifest["drives"][split]):
            raise ValueError("Industrial test identities overlap development data.")
    write_json(output / "test.json", examples)
    write_json(run / "test-release.json", {"checkpoint_sha256": selection["sha256"], "test_sha256": file_hash(output / "test.json"),
        "protocol_sha256": file_hash(output / "protocol.json"), "released_at": datetime.now(timezone.utc).isoformat(),
        "further_training_allowed": False})


def evaluate(run, device="cuda", *, followup=False, audio_benchmark=False):
    output = run / "evaluation"
    release = json.loads((run / "test-release.json").read_text())
    for path, digest in [(run / "best.pt", release["checkpoint_sha256"]), (output / "test.json", release["test_sha256"]),
                         (output / "protocol.json", release["protocol_sha256"])]:
        if file_hash(path) != digest:
            raise ValueError("A frozen industrial evaluation artifact changed.")
    protocol = json.loads((output / "protocol.json").read_text())
    criteria = audio_criteria(protocol["component_config"]["component"]) if audio_benchmark else CRITERIA
    if audio_benchmark:
        from driftops.slider_data import validate_config
        validate_config(protocol["component_config"])
        if followup or protocol["dataset_kind"] != protocol["component_config"]["study"]:
            raise ValueError("The sound evaluation must match its frozen benchmark protocol.")
    if followup:
        from driftops.industrial_followup import followup_criteria, verify_followup
        criteria = followup_criteria()
        verify_followup(run)
    if protocol["success_criteria"] != criteria:
        raise ValueError("Industrial study criteria changed after test release.")
    examples = json.loads((output / "test.json").read_text())
    scores, outputs = {}, {}
    torch.set_num_threads(8)
    torch.manual_seed(20260912)
    started = time.monotonic()

    def cancel(*_):
        raise TimeoutError("The industrial evaluation reached its time limit.")

    previous = signal.signal(signal.SIGALRM, cancel)
    signal.alarm(3600)
    try:
        model = load_model(device)
        outputs["starting"], seconds = predictions(model, examples, output / "starting", "pinned-upstream")
        scores["starting"] = metrics(examples, outputs["starting"]) | {"generation_seconds": seconds}
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        model = load_model(device, checkpoint=run / "best.pt")
        for mode in ("finetuned", "zero_numerical_embeddings", "reversed", "shuffled"):
            changed = examples if mode == "finetuned" else perturb(examples, mode, protocol["component_config"])
            outputs[mode], seconds = predictions(model, changed, output / mode, release["checkpoint_sha256"])
            scores[mode] = metrics(changed, outputs[mode]) | {"generation_seconds": seconds}
            if mode in ("reversed", "shuffled"):
                indices = [i for i,(a,b) in enumerate(zip(examples, changed)) if a["target"] != b["target"]]
                subset = [changed[i] for i in indices]
                actual = metrics(subset, [outputs[mode][i] for i in indices])["per_drive_accuracy"]
                unchanged = metrics(subset, [outputs["finetuned"][i] for i in indices])["per_drive_accuracy"]
                counts = defaultdict(int)
                for item in subset:
                    counts[item["audit"]["group_id"]] += 1
                support_ok = len(counts) == 5 and min(counts.values()) >= 32
                ev = evidence(subset, actual, unchanged) if subset else {"passed": False}
                scores[mode]["counterfactual_evidence"] = {**ev, "changed_windows_by_group": dict(counts), "support_sufficient": support_ok,
                                                          "passed": support_ok and ev["passed"]}
        constants = ["; ".join(f"{t.split(';',1)[0]}: constant" for t in item["inputs"]["time_series_text"]) + "." for item in examples]
        scores["constant"] = metrics(examples, constants)
        comparisons = {mode: evidence(examples, scores["finetuned"]["per_drive_accuracy"], scores[mode]["per_drive_accuracy"])
                       for mode in CRITERIA["baselines"]}
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        model = load_model(device, checkpoint=run / "best.pt")
        if generate(model, examples[:16], max_new_tokens=128) != outputs["finetuned"][:16]:
            raise ValueError("The industrial checkpoint changed predictions after reload.")
        checks = {"valid_outputs": scores["finetuned"]["valid_output_rate"] >= .95, "checkpoint_reload": True,
                  **{mode: value["passed"] and scores["finetuned"]["macro_f1_supported_classes"] > scores[mode]["macro_f1_supported_classes"]
                     for mode,value in comparisons.items()},
                  **{mode + "_target_response": scores[mode]["counterfactual_evidence"]["passed"] for mode in ("reversed", "shuffled")}}
        for score in scores.values():
            score["per_window_accuracy"] = score.pop("per_drive_accuracy")
        report = {"support": {"windows": len(examples), "groups": len({e["audit"]["group_id"] for e in examples}),
                              "devices": len({e["audit"]["drive_id"] for e in examples})},
                  "comparisons": scores, "group_evidence": comparisons,
                  "success_gate": {"passed": all(checks.values()), "checks": checks, "criteria": criteria},
                  "selected_checkpoint_sha256": release["checkpoint_sha256"], "reload_predictions_equal": 16,
                  "seconds": time.monotonic() - started, "large_cohort_result": False,
                  "interpretation_limit": criteria["scope"] + " Only five held-out groups. Exact sign inference assumes exchangeable paired differences under the null."}
        if audio_benchmark:
            report["support"]["recordings"] = report["support"].pop("devices")
            report["chronology_verified"] = False
            report["clock_semantics"] = "clip-relative-offset-only"
        if followup:
            report["followup"] = {"original_gate_unchanged": True, "original_gate_result": False,
                "original_metrics_sha256": protocol["original_metrics_sha256"],
                "weights_changed": False, "new_independent_groups": False,
                "scope": "Follow-up on all unused test windows after an insufficient-support result. This is not an independent replication or the original predeclared test."}
        write_json(output / "metrics.json", report)
        print(json.dumps({"small_cohort_gate_passed": report["success_gate"]["passed"], "checks": checks}), flush=True)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "evaluate"])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--audio-benchmark", action="store_true")
    args = parser.parse_args()
    if args.action == "freeze":
        if args.root is None:
            parser.error("Test release requires the prepared industrial dataset root.")
        freeze(args.root, args.run, audio_benchmark=args.audio_benchmark)
    else:
        evaluate(args.run, args.device, audio_benchmark=args.audio_benchmark)
