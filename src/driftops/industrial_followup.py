"""Evaluate unchanged industrial weights on all previously unused test windows."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import pyarrow.parquet as pq

from driftops.acquire import write_json
from driftops.component_data import example
from driftops.evaluate_industrial import CRITERIA, evaluate
from driftops.full_archive import file_hash
from driftops.full_training import window_files


def followup_criteria():
    return {**CRITERIA, "windows_per_group": "All previously unused eligible test windows, without target-based sampling."}


def require_support_failure(report):
    checks = report["success_gate"]["checks"]
    failed = {name for name, value in checks.items() if value is not True}
    allowed = {"reversed_target_response", "shuffled_target_response"}
    expected = allowed | {"valid_outputs", "checkpoint_reload", "starting", "constant", "zero_numerical_embeddings"}
    if set(checks) != expected:
        raise ValueError("The original report lacks its complete frozen checks.")
    if report["success_gate"]["passed"] is not False or not failed or not failed <= allowed:
        raise ValueError("The follow-up requires an original failure limited to counterfactual support.")
    for mode in ("reversed", "shuffled"):
        result = report["comparisons"][mode]["counterfactual_evidence"]
        if (result["groups"] != 5 or result["accuracy_gain_ci95"][0] <= 0
                or result["one_sided_exact_group_sign_probability"] > .05):
            raise ValueError("The original comparison lacks positive group-level evidence.")
        if mode + "_target_response" in failed and result["support_sufficient"] is not False:
            raise ValueError("The original failed comparison has sufficient support.")


def verify_selection(examples, previous_ids, expected_total):
    ids = [item["audit"]["task_id"] for item in examples]
    if len(previous_ids) != len(set(previous_ids)) or len(ids) != len(set(ids)):
        raise ValueError("An industrial test window appears more than once.")
    if set(ids).intersection(previous_ids):
        raise ValueError("The follow-up reuses an opened test window.")
    if len(ids) + len(previous_ids) != expected_total:
        raise ValueError("The follow-up must contain every unused test window.")
    if len({item["audit"]["group_id"] for item in examples}) != 5:
        raise ValueError("The follow-up must retain all five held-out groups.")


def freeze(root, parent, run, overview):
    prior = json.loads((parent / "evaluation/metrics.json").read_text())
    require_support_failure(prior)
    release = json.loads((parent / "test-release.json").read_text())
    selection = json.loads((parent / "selection.json").read_text())
    for path, digest in [(parent / "best.pt", release["checkpoint_sha256"]),
                         (parent / "evaluation/test.json", release["test_sha256"]),
                         (parent / "evaluation/protocol.json", release["protocol_sha256"])]:
        if file_hash(path) != digest:
            raise ValueError("An original frozen study artifact changed.")
    if prior["selected_checkpoint_sha256"] != selection["sha256"] or selection["sha256"] != release["checkpoint_sha256"]:
        raise ValueError("The follow-up checkpoint differs from the original selected model.")
    previous = json.loads((parent / "evaluation/test.json").read_text())
    previous_ids = sorted(item["audit"]["task_id"] for item in previous)
    manifest = json.loads((parent / "dataset-manifest.json").read_text())
    if not 1 <= manifest["audit"]["windows_test"] <= 20_000:
        raise ValueError("The follow-up exceeds its test-size bound.")
    if run.exists():
        raise FileExistsError("Inspect the existing follow-up before another attempt.")
    (run / "evaluation").mkdir(parents=True)
    (run / "original").mkdir()
    for name in ("best.pt", "selection.json", "training-result.json", "config.json", "dataset-manifest.json"):
        shutil.copy2(parent / name, run / name)
    shutil.copy2(parent / "evaluation/metrics.json", run / "original/metrics.json")
    shutil.copy2(parent / "test-release.json", run / "original/test-release.json")
    write_json(run / "original/test-task-ids.json", previous_ids)
    write_json(run / "overview.json", overview)
    protocol = {"dataset_kind": "industrial-unused-test-followup-v1", "component_config": manifest["config"],
        "dataset_manifest_sha256": file_hash(run / "dataset-manifest.json"),
        "checkpoint_sha256": selection["sha256"], "selected_completed_epoch": selection["epoch"],
        "original_metrics_sha256": file_hash(run / "original/metrics.json"),
        "original_test_task_ids_sha256": file_hash(run / "original/test-task-ids.json"),
        "success_criteria": followup_criteria(), "selection": followup_criteria()["windows_per_group"],
        "original_gate_result": False, "weights_changed": False, "new_independent_groups": False,
        "generation": {"do_sample": False, "max_new_tokens": 128, "batch_size": 16},
        "time_limit_seconds": 3600,
        "scope": "Follow-up after insufficient counterfactual support. Same five groups, all unused windows, unchanged weights and quality thresholds. Preserve the original failed gate."}
    # Fix the protocol before reading any remaining numerical test inputs.
    write_json(run / "evaluation/protocol.json", protocol)
    examples, seen = [], set()
    exclude = set(previous_ids)
    for path in window_files(root, "test", manifest):
        if file_hash(path) != manifest["shards"][path.parent.name][path.name]:
            raise ValueError("A follow-up test shard changed.")
        for batch in pq.ParquetFile(path).iter_batches(batch_size=2048):
            for row in batch.to_pylist():
                if row["task_id"] in seen:
                    raise ValueError("The prepared test contains a duplicate window.")
                seen.add(row["task_id"])
                if row["task_id"] not in exclude:
                    examples.append(example(row, manifest["config"]))
    if not exclude <= seen:
        raise ValueError("The original test does not belong to this prepared dataset.")
    examples.sort(key=lambda item: (item["audit"]["group_id"], item["audit"]["task_id"]))
    verify_selection(examples, previous_ids, manifest["audit"]["windows_test"])
    write_json(run / "evaluation/test.json", examples)
    write_json(run / "test-release.json", {"checkpoint_sha256": selection["sha256"],
        "test_sha256": file_hash(run / "evaluation/test.json"),
        "protocol_sha256": file_hash(run / "evaluation/protocol.json"),
        "released_at": datetime.now(timezone.utc).isoformat(), "further_training_allowed": False})
    verify_followup(run)


def verify_followup(run):
    protocol = json.loads((run / "evaluation/protocol.json").read_text())
    for path, digest in [(run / "original/metrics.json", protocol["original_metrics_sha256"]),
                         (run / "original/test-task-ids.json", protocol["original_test_task_ids_sha256"]),
                         (run / "dataset-manifest.json", protocol["dataset_manifest_sha256"])]:
        if file_hash(path) != digest:
            raise ValueError("An original follow-up record changed.")
    prior = json.loads((run / "original/metrics.json").read_text())
    require_support_failure(prior)
    if prior["selected_checkpoint_sha256"] != protocol["checkpoint_sha256"]:
        raise ValueError("The follow-up changed the original checkpoint.")
    examples = json.loads((run / "evaluation/test.json").read_text())
    previous_ids = json.loads((run / "original/test-task-ids.json").read_text())
    manifest = json.loads((run / "dataset-manifest.json").read_text())
    verify_selection(examples, previous_ids, manifest["audit"]["windows_test"])
    groups = {item["audit"]["group_id"] for item in examples}
    devices = {item["audit"]["drive_id"] for item in examples}
    if groups != set(manifest["groups"]["test"]):
        raise ValueError("The follow-up changes the original held-out groups.")
    for split in ("train", "validation", "calibration"):
        if groups.intersection(manifest["groups"][split]) or devices.intersection(manifest["drives"][split]):
            raise ValueError("The follow-up overlaps development identities.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    args = parser.parse_args()
    evaluate(args.run, args.device, followup=True)
