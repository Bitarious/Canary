"""Prepare and train one independent component OpenTSLM after the HDD gate."""

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from driftops.acquire import write_json
from driftops.component_data import example, target
from driftops.full_archive import file_hash
from driftops.full_training import raw_batches, window_files
from driftops.tslm_dataset import PATTERNS, input_hash
from driftops.windows import read_yaml


def perturb(examples, mode, config, seed=612):
    changed = deepcopy(examples)
    rng = np.random.default_rng(seed)
    for item in changed:
        values = np.asarray(item["inputs"]["time_series"])
        if mode == "zero_numerical_embeddings":
            item["inputs"]["time_series"] = np.zeros_like(values).tolist()
        elif mode in ("reversed", "shuffled"):
            order = np.arange(27, -1, -1) if mode == "reversed" else rng.permutation(28)
            raw = np.asarray(item["raw_values"])[:, order]
            item["inputs"]["time_series"] = values[:, order].tolist()
            item["raw_values"] = raw.tolist()
            channels = [text.split(";", 1)[0] for text in item["inputs"]["time_series_text"]]
            item["target"] = target(raw, channels, config)
        else:
            raise ValueError("The component perturbation is unsupported.")
        item["audit"]["numerical_transform"] = mode
        item["audit"]["input_hash"] = input_hash(item["inputs"])
    return changed


def training_example(row, config, epoch, seed):
    item = example(row, config)
    if epoch == 0:
        return item
    digest = hashlib.sha256(f"component-augmentation-v1:{seed}:{epoch}:{row['task_id']}".encode()).digest()
    if digest[0] < 128:
        return item
    mode = "reversed" if digest[0] < 192 else "shuffled"
    return perturb([item], mode, config, int.from_bytes(digest[1:9], "big"))[0]


def heldout(root, manifest, split, limit):
    """Choose one physical device window per independent split group by fixed hashes."""
    groups = sorted(manifest["groups"][split], key=lambda value: hashlib.sha256(("component-heldout-v1:" + value).encode()).digest())[:limit]
    wanted, chosen = set(groups), {}
    for path in window_files(root, split, manifest):
        for batch in pq.ParquetFile(path).iter_batches(batch_size=4096):
            for row in batch.to_pylist():
                group = row["group_id"]
                if group not in wanted:
                    continue
                key = hashlib.sha256(("component-heldout-window-v1:" + row["task_id"]).encode()).digest()
                if group not in chosen or key < chosen[group][0]:
                    chosen[group] = key, row
    if len(chosen) != len(groups):
        raise ValueError("The component held-out group inventory does not match its windows.")
    return [example(chosen[group][1], manifest["config"]) for group in groups]


def prepare(root, run, hdd_report, *, industrial_study=False, audio_benchmark=False):
    gate = json.loads(hdd_report.read_text())
    if not gate["success_gate"]["passed"] or gate["reload_predictions_equal"] != 16:
        raise ValueError("The HDD model must pass its frozen held-out gate before component training.")
    ledger_path = Path("artifacts/nebius/full-history-v1/cost-ledger.json")
    ledger = json.loads(ledger_path.read_text())
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(ledger["as_of"])).total_seconds()
    if not 0 <= age <= 300 or ledger["remaining_under_ceiling_usd"] < 50.45:
        raise ValueError("Refresh the shared compute ledger and reserve the bounded component phase before training.")
    manifest_path = root / "dataset-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != "component-windows-v1":
        raise ValueError("The dataset is not a verified component dataset.")
    if industrial_study and audio_benchmark:
        raise ValueError("Select only one component study design.")
    if audio_benchmark:
        from driftops.slider_data import validate_config
        validate_config(manifest["config"])
        if ({s: len(g) for s,g in manifest["groups"].items()} != {"train": 1, "validation": 1, "calibration": 0, "test": 5}
                or manifest["audit"]["windows_train"] < 1024):
            raise ValueError("The sound cohort does not meet its separate benchmark design.")
    elif industrial_study:
        if (manifest["config"].get("study") != "small-industrial-v1"
                or len(manifest["groups"]["train"]) < 3 or len(manifest["groups"]["validation"]) < 2
                or len(manifest["groups"]["test"]) != 5 or manifest["audit"]["windows_train"] < 1024):
            raise ValueError("The industrial cohort does not meet its separate study design.")
    elif min(len(manifest["groups"][s]) for s in ("train", "validation", "test")) < 64:
        raise ValueError("The component needs at least 64 independent groups in each main split.")
    for split in ("train", "validation"):
        for path in window_files(root, split, manifest):
            if file_hash(path) != manifest["shards"][path.parent.name][path.name]:
                raise ValueError("A component training or validation source checksum changed.")
    if industrial_study or audio_benchmark:
        from driftops.evaluate_industrial import heldout_many
        validation = heldout_many(root, manifest, "validation", 256 if audio_benchmark else 64)
    else:
        validation = heldout(root, manifest, "validation", 256)
    selection = [*validation, *perturb(validation, "reversed", manifest["config"]),
                 *perturb(validation, "shuffled", manifest["config"])]
    counts = Counter()
    sample_count = 0
    for rows, _ in raw_batches(root, manifest, 64, 20260913):
        items = [example(row, manifest["config"]) for row in rows]
        # Expected post-warmup mix: 1/2 original, 1/4 reversal, 1/4 shuffle.
        for weight, samples in ((2, items), (1, perturb(items, "reversed", manifest["config"])),
                                (1, perturb(items, "shuffled", manifest["config"]))):
            for item in samples:
                for entry in item["target"].rstrip(".").split("; "):
                    counts[entry.split(": ", 1)[1]] += weight
        sample_count += len(rows)
        if sample_count >= 8192:
            break
    total = sum(counts.values())
    weights = {p: float(np.clip(total/(len(PATTERNS)*max(counts[p], 1)), .1, 30)) for p in PATTERNS}
    config = {**read_yaml("config/train_full.yaml"), "version": run.name, "seed": 20260913,
              "world_size": 1, "epochs": 12, "max_train_hours": 2, "max_vm_hours": 3.5,
              "checkpoint_every_steps": 500, "validation_every_steps": 2000,
              "validation_drives": len(validation), "test_drives": min(256, len(manifest["groups"]["test"])),
              "early_stopping_patience": 3, "minimum_epochs": 3,
              "objective": "Class-weighted answer-token loss on component-only observed windows and declared order perturbations.",
              "coverage": "First epoch visits every observed training window. Later epochs use deterministic 50% original, 25% reversed, 25% shuffled views.",
              "selection": "Lowest combined loss on equal-size natural, reversed, and shuffled validation views at completed epochs."}
    if industrial_study:
        config.update(evaluation_kind="small-industrial-v1", test_drives=5, test_windows_per_group=256, max_train_hours=.75)
    if audio_benchmark:
        config.update(evaluation_kind=manifest["config"]["study"], test_drives=5, test_windows_per_group=1024, max_train_hours=.5)
    run.mkdir(parents=True)
    write_json(run / "config.json", config)
    write_json(run / "dataset-manifest.json", manifest)
    write_json(run / "validation-natural.json", validation)
    write_json(run / "validation.json", selection)
    write_json(run / "class-weights.json", weights)
    write_json(run / "weight-support.json", {"training_sample_windows": sample_count, "weighted_pattern_counts": dict(counts)})
    write_json(run / "hdd-gate.json", {"report_sha256": file_hash(hdd_report), "success_gate": gate["success_gate"],
                                      "selected_checkpoint_sha256": gate["selected_checkpoint_sha256"], "reload_predictions_equal": 16})
    write_json(run / "budget-at-preparation.json", ledger)
    overview = {
        "objective": f"Test an independent OpenTSLM for {manifest['config']['component']} observed signal descriptions.",
        "necessity": "The HDD model passed its held-out gate. This component has different signals and requires separate weights and evidence.",
        "data": {"dataset_manifest_sha256": file_hash(manifest_path), "scope": manifest["config"]["scope"],
                 "training_windows": manifest["audit"]["windows_train"], "independent_groups": {s: len(v) for s,v in manifest["groups"].items()},
                 "split_rules": manifest["config"]["partitions"], "test_numeric_data_transferred": False},
        "updated_parameters": "Temporal encoder, projector, and rank-8 Gemma attention LoRA, initialized independently from pinned upstream OpenTSLM weights.",
        "frozen_parameters": "All original Gemma language-model parameters. No other component's fitted weights or training examples are used.",
        "augmentation": config["coverage"] + " These order perturbations are labeled numerical counterfactuals, not additional physical histories or failure events.",
        "selection": config["selection"],
        "hardware_cost": "One assigned RTX PRO 6000 GPU inside the existing eight-GPU Nebius VM. The whole VM costs $14.40/hour plus its disk. A shared 3.5-hour component phase costs at most $50.45 and must remain inside the shared $600 ceiling and absolute VM deadline.",
        "stopping": "At most 12 epochs or two training hours. Stop after three completed epochs without validation improvement, after at least three epochs. Stop on nonfinite values, cancellation, or the independent VM guard.",
        "evaluation": "Freeze selected checkpoint before test release. Use one window per held-out group. Compare upstream, constant, fitted, zero numerical values, reversal, and shuffle. Require valid output, baseline gains, numerical dependence, target response, and 16 exact reload predictions.",
        "outputs": "Source and split pins, independent model and optimizer checkpoints, validation records, raw test generations, metrics and paired-group intervals, reload proof, and compute ledger.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if industrial_study:
        from driftops.evaluate_industrial import CRITERIA
        overview["study_scope"] = "Separate small-cohort experiment. It does not inherit the large-cohort success label."
        overview["hardware_cost"] = "Four independent small-study processes share the unused eighth RTX PRO 6000 GPU on the already-running eight-GPU VM. The existing total VM phase cap remains $50.45. No additional VM is allocated. The parent component phase owns provider stopping and may interrupt these jobs when it completes. Preserve checkpoints and inspect any interruption before a bounded resume."
        overview["stopping"] = "At most 12 epochs or 45 training minutes per model. Stop after three nonimproving completed epochs, with at least three epochs. The shared industrial service has a 90-minute limit. The parent VM's existing completion stop and absolute deadline remain controlling."
        overview["evaluation"] = "Freeze the selected checkpoint, then select up to 256 windows per held-out group. Average accuracy within groups before uncertainty calculations. Require five groups, positive paired group gains, exact one-sided group sign-randomization probability at most 0.05, valid outputs, correct numerical perturbation responses, and 16 exact reload predictions."
        overview["success_criteria"] = CRITERIA
        overview["study_design_sha256"] = file_hash(Path("docs/industrial-study-design.md"))
    if audio_benchmark:
        from driftops.evaluate_industrial import audio_criteria
        overview["study_scope"] = "Unknown-date sound benchmark. One training machine, one validation machine, five test machines. No calibration fitting or calendar-generalization claim."
        overview["hardware_cost"] = "One free RTX PRO 6000 GPU in the existing eight-GPU Nebius VM. The whole VM costs $14.40/hour plus disk. This run shares the existing $50.45 phase reservation and absolute deadline. The parent completion stop can interrupt this supplementary job."
        overview["stopping"] = "At most 12 epochs or 30 training minutes. Stop after three nonimproving completed epochs after at least three epochs. Stop on nonfinite values or the parent provider stop. Export completed checkpoints before any bounded resume."
        overview["evaluation"] = "Freeze selected weights before releasing up to 1024 fixed-hash windows per held-out machine. Apply five-group industrial numerical-response and baseline-gain checks, unchanged quality thresholds, and 16 exact GPU reload predictions."
        from driftops.slider_data import study
        overview["success_criteria"] = audio_criteria(manifest["config"]["component"])
        overview["study_design_sha256"] = file_hash(Path(study(manifest["config"])[3]))
    write_json(run / "overview.json", overview)
    sources = [*Path("src/driftops").rglob("*.py"), *Path("config").glob("*.yaml"), Path("pyproject.toml"), Path("uv.lock")]
    write_json(run / "source-hashes.json", {str(p): file_hash(p) for p in sorted(sources)})
    print(json.dumps(overview, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "train"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--hdd-report", type=Path)
    parser.add_argument("--industrial-study", action="store_true")
    parser.add_argument("--audio-benchmark", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare":
        if args.hdd_report is None:
            parser.error("Preparation requires the completed HDD report.")
        prepare(args.root, args.run, args.hdd_report, industrial_study=args.industrial_study, audio_benchmark=args.audio_benchmark)
    else:
        from driftops.train_full import train
        train(args.root, args.run)
