"""Freeze and evaluate one separately trained component model."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from driftops.acquire import write_json
from driftops.component_training import heldout
from driftops.evaluate_full import SUCCESS_CRITERIA, evaluate
from driftops.full_archive import file_hash
from driftops.full_training import window_files


def freeze(root, run):
    selection = json.loads((run / "selection.json").read_text())
    training = json.loads((run / "training-result.json").read_text())
    if not training["full_data_training_complete"] or selection["epoch"] < 1:
        raise ValueError("A component needs a complete observed-data epoch before test release.")
    if file_hash(run / "best.pt") != selection["sha256"]:
        raise ValueError("The selected component checkpoint changed.")
    output = run / "evaluation"
    output.mkdir(exist_ok=True)
    if (run / "test-release.json").exists():
        release = json.loads((run / "test-release.json").read_text())
        if (release["checkpoint_sha256"] != selection["sha256"] or file_hash(output / "test.json") != release["test_sha256"]
                or file_hash(output / "protocol.json") != release["protocol_sha256"]):
            raise ValueError("The frozen component test release changed.")
        return
    manifest = json.loads((run / "dataset-manifest.json").read_text())
    config = json.loads((run / "config.json").read_text())
    # Publish the protocol before materializing numerical test inputs for the model.
    write_json(output / "protocol.json", {
        "dataset_kind": "component-windows-v1", "component_config": manifest["config"],
        "dataset_manifest_sha256": file_hash(run / "dataset-manifest.json"),
        "checkpoint_sha256": selection["sha256"], "selected_completed_epoch": selection["epoch"],
        "test_groups": config["test_drives"],
        "selection": "Fixed hashes choose one device window per independent held-out group. No target-based selection.",
        "comparisons": ["starting", "finetuned", "constant", "deterministic_rules", "zero_numerical_embeddings", "reversed", "shuffled"],
        "primary": "Strict free-text channel accuracy, exact-window accuracy, supported-class macro F1, and invalid output rate.",
        "ablations": "Keep all text and raw scale statistics fixed. Zero numerical values, reverse time order, or shuffle order. Recompute component-specific weak targets for the order changes.",
        "uncertainty": "2000 paired independent-group bootstrap samples, seed 42. One window per group. Counterfactual gains use groups with changed targets and compare against unchanged original predictions.",
        "success_criteria": SUCCESS_CRITERIA,
        "concept_scope": manifest["config"]["scope"],
        "generation": {"do_sample": False, "max_new_tokens": 128, "batch_size": 16},
        "time_limit_seconds": 3600,
    })
    for path in window_files(root, "test", manifest):
        if file_hash(path) != manifest["shards"][path.parent.name][path.name]:
            raise ValueError("A component test source checksum changed.")
    examples = heldout(root, manifest, "test", config["test_drives"])
    if len(examples) != config["test_drives"]:
        raise ValueError("The component lacks the declared number of independent test groups.")
    groups = {item["audit"]["group_id"] for item in examples}
    devices = {item["audit"]["drive_id"] for item in examples}
    if len(groups) != len(examples) or len(devices) != len(examples):
        raise ValueError("Component evaluation must use one device window per independent group.")
    for split in ("train", "validation", "calibration"):
        if groups.intersection(manifest["groups"][split]) or devices.intersection(manifest["drives"][split]):
            raise ValueError("Component test identities overlap a development split.")
    write_json(output / "test.json", examples)
    write_json(run / "test-release.json", {"checkpoint_sha256": selection["sha256"],
        "test_sha256": file_hash(output / "test.json"), "protocol_sha256": file_hash(output / "protocol.json"),
        "released_at": datetime.now(timezone.utc).isoformat(), "further_training_allowed": False})
    print(json.dumps({"component": manifest["config"]["component"], "test_groups": len(groups),
                      "checkpoint_sha256": selection["sha256"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "evaluate"])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    args = parser.parse_args()
    if args.action == "freeze":
        if args.root is None:
            parser.error("Test release requires the prepared component dataset root.")
        freeze(args.root, args.run)
    else:
        evaluate(args.run, args.device)
