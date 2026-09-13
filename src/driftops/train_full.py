"""Prepare and run bounded OpenTSLM fine-tuning on the full historical HDD training split."""

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import fcntl
import json
import math
from pathlib import Path
import random
import signal
import time

import numpy as np
import torch

from driftops.acquire import write_json
from driftops.full_archive import file_hash
from driftops.distributed_training import DistributedRun, local_batch, weighted_distributed_loss
from driftops.full_training import class_weights, compact_loss, example, heldout, raw_batches, window_files
from driftops.opentslm import generate, load_model, temporal_state
from driftops.training_config import read_training_config


def atomic_save(path, state):
    temporary = path.with_suffix(path.suffix + ".part")
    torch.save(state, temporary)
    temporary.replace(path)


def prepare(root, run, config_path=Path("config/train_full.yaml")):
    if run.exists():
        raise ValueError("Choose a new run directory. Existing run artifacts must remain intact")
    manifest_path = root / "dataset-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    config = read_training_config(config_path)
    for split in ("train", "validation"):
        for path in window_files(root, split, manifest):
            if file_hash(path) != manifest["shards"][path.parent.name][path.name]:
                raise ValueError("Prepared dataset checksum mismatch")
    validation = heldout(root, manifest, "validation", config["validation_drives"])
    if len(validation) < config["validation_drives"]:
        raise ValueError("Not enough independent validation drives")
    run.mkdir(parents=True)
    write_json(run / "config.json", config)
    write_json(run / "dataset-manifest.json", manifest)
    write_json(run / "validation.json", validation)
    weights = class_weights(manifest)
    write_json(run / "class-weights.json", weights)
    overview = {
        "objective": "Test whether native OpenTSLM numerical inputs support HDD signal descriptions across the complete historical archive.",
        "necessity": "The 256-drive CPU pilot repeated one answer and ignored numerical ablations. This run expands device/date coverage and adds a small language LoRA adapter with class-weighted supervision.",
        "source": {"archives": 44, "dataset_manifest_sha256": file_hash(manifest_path), "config": manifest["config"]},
        "data_splits": {"train_windows": manifest["audit"]["windows_train"],
                         "validation_selection_drives": len(validation), "test_evaluation_drives": config["test_drives"],
                         "rule": "Disjoint serials and ordered dates. All numeric windows pass native TimeF read-back. Test files stay on the controller until selection is frozen."},
        "updated_parameters": {"temporal_encoder": True, "projector": True, "gemma_attention_lora": config["lora"]},
        "frozen_parameters": "All original Gemma parameters. Start from the pinned upstream TSQA adapter, not the prior pilot checkpoint.",
        "supervision": "Existing window-description-v1 deterministic labels. These are weak targets, not technician reports or failure predictions.",
        "normalization": "Observed-window z-score. Channel text includes the same window's raw standard deviation. No identity, dates, failure flags, labels, or future observations enter prompts.",
        "hardware_cost": {"provider": "Nebius", "preferred_gpu": f"{config.get('world_size', 1)} {config['gpu_name']} GPUs, {config['gpu_memory_gb']} GB each", "vm_rate_usd_hour": config["vm_hourly_usd"],
                          "disk_128_gib_rate_usd_hour": config["disk_hourly_usd"], "training_hours_limit": config["max_train_hours"],
                          "vm_hours_limit": config["max_vm_hours"], "quoted_vm_limit_usd": (config["vm_hourly_usd"] + config["disk_hourly_usd"]) * config["max_vm_hours"],
                          "run_budget_usd": config["budget_usd"], "budget_note": "Configured limit, not a measured account balance. Verify current funds and a provider stop guard before launch."},
        "stopping_conditions": f"At most {config['epochs']} complete epochs, {config['max_train_hours']} training hours, nonfinite loss/gradients, signal cancellation, or the independent absolute provider API stop guard. A partial first epoch is not a full-data success.",
        "evaluation": "Unweighted validation answer loss selects only completed-epoch checkpoints. Freeze checkpoint hash before test. Compare the upstream model, fitted model, all-constant baseline, and zero/reversed/shuffled numerical inputs. Report syntax validity, channel accuracy, macro F1, drive bootstrap intervals, and raw outputs.",
        "outputs": "Pinned data/split/source manifests, optimizer and cursor checkpoints, selected temporal/LoRA weights, progress and costs, test predictions/metrics, ablations, and verified reload results.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(run / "overview.json", overview)
    sources = [*Path("src/driftops").rglob("*.py"), *Path("config").glob("*.yaml"), Path("pyproject.toml"), Path("uv.lock")]
    write_json(run / "source-hashes.json", {str(p): file_hash(p) for p in sorted(sources)})
    print(json.dumps(overview, indent=2), flush=True)


@torch.inference_mode()
def validation_loss(model, examples, batch_size):
    model.eval()
    total, count = 0., 0
    for start in range(0, len(examples), batch_size):
        batch = examples[start:start+batch_size]
        with torch.autocast("cuda", dtype=torch.bfloat16):
            value = compact_loss(model, batch)
        if not torch.isfinite(value):
            raise ValueError("Validation loss is not finite")
        total += value.item() * len(batch)
        count += len(batch)
    return total / count


def train(root, run, diagnostic_steps=0):
    if (run / "test-release.json").exists():
        raise ValueError("Test data was released for this run. Do not train it again")
    if not torch.cuda.is_available():
        raise ValueError("This training run requires a CUDA GPU")
    if not (run / "overview.json").is_file():
        raise ValueError("Prepare and explain the run before training")
    if diagnostic_steps:
        overview = json.loads((run / "diagnostic-overview.json").read_text())
        if overview["steps"] != diagnostic_steps:
            raise ValueError("The diagnostic step limit differs from its advance overview")
    for name, digest in json.loads((run / "source-hashes.json").read_text()).items():
        if file_hash(Path(name)) != digest:
            raise ValueError("Source changed after the training overview was frozen")
    config = json.loads((run / "config.json").read_text())
    manifest = json.loads((run / "dataset-manifest.json").read_text())
    component = manifest.get("format") == "component-windows-v1"
    if component:
        from driftops.component_training import training_example
        gate = json.loads((run / "hdd-gate.json").read_text())
        if not gate["success_gate"]["passed"] or gate["reload_predictions_equal"] != 16:
            raise ValueError("The HDD held-out gate must pass before component training.")
    validation = json.loads((run / "validation.json").read_text())
    weights = json.loads((run / "class-weights.json").read_text())
    hours_limit = min(config["max_train_hours"], 1) if diagnostic_steps else config["max_train_hours"]
    parallel = DistributedRun()
    if parallel.world != config.get("world_size", 1):
        raise ValueError("The launched GPU count differs from the frozen run configuration")
    with (run / "train.lock").open("a") as lock:
        if parallel.primary:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        parallel.barrier()
        torch.set_num_threads(8)
        random.seed(config["seed"])
        np.random.seed(config["seed"])
        torch.manual_seed(config["seed"])
        torch.cuda.manual_seed_all(config["seed"])
        model = load_model(parallel.device, lora_config=config["lora"])
        parameters = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.AdamW([
            {"params": model.encoder.parameters(), "lr": config["encoder_lr"]},
            {"params": model.projector.parameters(), "lr": config["projector_lr"]},
            {"params": model.get_lora_parameters(), "lr": config["lora_lr"]},
        ], weight_decay=config["weight_decay"])
        runtime = {"epoch": 0, "completed_epochs": 0, "cursor": None, "steps": 0, "examples_seen": 0,
                   "elapsed_seconds": 0., "best_validation_loss": None}
        if (run / "last.pt").is_file():
            state = torch.load(run / "last.pt", weights_only=True, map_location=parallel.device)
            if state.get("world_size", 1) != parallel.world:
                raise ValueError("Resume requires the original GPU count")
            model = load_model(parallel.device, checkpoint=run / "last.pt")
            parameters = [p for p in model.parameters() if p.requires_grad]
            optimizer = torch.optim.AdamW([
                {"params": model.encoder.parameters(), "lr": config["encoder_lr"]},
                {"params": model.projector.parameters(), "lr": config["projector_lr"]},
                {"params": model.get_lora_parameters(), "lr": config["lora_lr"]},
            ], weight_decay=config["weight_decay"])
            optimizer.load_state_dict(state["optimizer"])
            runtime = state["runtime"]
            torch.set_rng_state(state["torch_rng"].cpu())
            torch.cuda.set_rng_state(state["cuda_rng"][parallel.rank].cpu())
        else:
            torch.cuda.manual_seed(config["seed"] + parallel.rank)
        loss_module = parallel.wrap(model)
        start = time.monotonic()
        prior_elapsed = runtime["elapsed_seconds"]
        stop = {"requested": False}
        previous_handlers = {sig: signal.signal(sig, lambda *_: stop.update(requested=True)) for sig in (signal.SIGTERM, signal.SIGINT)}
        hardware = {"torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(),
                    "gpu_bytes": torch.cuda.get_device_properties(0).total_memory,
                    "gpu_count": parallel.world, "global_batch_size": config["batch_size"] * parallel.world,
                    "trainable_parameters": sum(p.numel() for p in parameters),
                    "frozen_parameters": sum(p.numel() for p in model.parameters() if not p.requires_grad)}
        if parallel.primary:
            write_json(run / "hardware.json", hardware)

        def save():
            runtime["elapsed_seconds"] = prior_elapsed + time.monotonic() - start
            rng = parallel.rng_states()
            if parallel.primary:
                atomic_save(run / "last.pt", {**temporal_state(model), "optimizer": optimizer.state_dict(),
                            "runtime": runtime.copy(), "torch_rng": torch.get_rng_state(), "cuda_rng": rng,
                            "world_size": parallel.world})
                write_json(run / "progress.json", {**runtime,
                           "peak_gpu_bytes": torch.cuda.max_memory_allocated(), "hardware": hardware})
            parallel.barrier()

        def validate():
            score = validation_loss(model, validation, config["batch_size"]) if parallel.primary else 0.
            value = torch.tensor(score, device=parallel.device, dtype=torch.float64)
            if parallel.world > 1:
                torch.distributed.broadcast(value, src=0)
            return value.item()

        reason = "completed"
        try:
            if runtime["steps"] == 0:
                baseline_loss = validate()
                if parallel.primary:
                    write_json(run / "initial-validation.json", {"loss": baseline_loss})
            for epoch in range(runtime["epoch"], config["epochs"]):
                runtime["epoch"] = epoch
                for global_rows, cursor in raw_batches(root, manifest, config["batch_size"] * parallel.world, config["seed"] + epoch, runtime["cursor"]):
                    if parallel.any(stop["requested"] or prior_elapsed + time.monotonic() - start >= hours_limit * 3600):
                        reason = "signal" if stop["requested"] else "training_time_limit"
                        break
                    local_rows, active = local_batch(global_rows, parallel.rank, config["batch_size"])
                    examples = [(training_example(row, manifest["config"], epoch, config["seed"])
                                 if component else example(row)) for row in local_rows]
                    loss_module.train()
                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast("cuda", dtype=torch.bfloat16):
                        local_value, normalizer = loss_module(examples, weights)
                        value = weighted_distributed_loss(local_value, normalizer, active)
                    if parallel.any(not torch.isfinite(value)):
                        raise ValueError("Training loss is not finite")
                    value.backward()
                    norm = torch.nn.utils.clip_grad_norm_(parameters, config["clip_grad_norm"], error_if_nonfinite=True)
                    optimizer.step()
                    runtime["cursor"] = cursor
                    runtime["steps"] += 1
                    runtime["examples_seen"] += len(global_rows)
                    if runtime["steps"] % 10 == 0:
                        event = {"step": runtime["steps"], "epoch": epoch, "loss": parallel.mean(value), "gradient_norm": norm.item(),
                                 "examples_seen": runtime["examples_seen"], "elapsed_seconds": prior_elapsed + time.monotonic() - start}
                        if parallel.primary:
                            with (run / "metrics.jsonl").open("a") as stream:
                                stream.write(json.dumps(event) + "\n")
                            print(json.dumps(event), flush=True)
                    if runtime["steps"] % config["checkpoint_every_steps"] == 0:
                        save()
                    if diagnostic_steps and runtime["steps"] >= diagnostic_steps:
                        reason = "diagnostic_step_limit"
                        break
                    if runtime["steps"] % config["validation_every_steps"] == 0:
                        score = validate()
                        if parallel.primary:
                            with (run / "validation-metrics.jsonl").open("a") as stream:
                                stream.write(json.dumps({"step": runtime["steps"], "epoch": epoch, "loss": score, "selection_eligible": False}) + "\n")
                else:
                    if runtime["examples_seen"] != (epoch + 1) * manifest["audit"]["windows_train"]:
                        raise ValueError("Completed epoch did not visit the full training row count")
                    runtime["completed_epochs"] = epoch + 1
                    runtime["epoch"] = epoch + 1
                    runtime["cursor"] = None
                    score = validate()
                    if runtime["best_validation_loss"] is None or score < runtime["best_validation_loss"]:
                        runtime["best_validation_loss"] = score
                        if config.get("early_stopping_patience"):
                            runtime["validation_no_improvement"] = 0
                        if parallel.primary:
                            atomic_save(run / "best.pt", temporal_state(model))
                            write_json(run / "selection.json", {"sha256": file_hash(run / "best.pt"), "epoch": epoch + 1,
                                "examples_seen": runtime["examples_seen"], "validation_loss": score,
                                "validation_sha256": file_hash(run / "validation.json"), "test_opened": False})
                    elif config.get("early_stopping_patience"):
                        runtime["validation_no_improvement"] = runtime.get("validation_no_improvement", 0) + 1
                    save()
                    if (config.get("early_stopping_patience") and epoch + 1 >= config.get("minimum_epochs", 1)
                            and runtime.get("validation_no_improvement", 0) >= config["early_stopping_patience"]):
                        reason = "validation_patience"
                        break
                    continue
                break
            save()
            if parallel.primary:
                write_json(run / "training-result.json", {**runtime, "stop_reason": reason,
                             "full_data_training_complete": runtime["completed_epochs"] >= 1,
                             "selected_checkpoint": "best.pt" if (run / "best.pt").exists() else None})
        except BaseException as error:
            # A failed rank cannot enter a checkpoint collective. Resume the last durable cursor.
            write_json(run / f"training-error-rank-{parallel.rank}.json", {"type": type(error).__name__, "message": str(error)[:2000]})
            raise
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
            parallel.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "train"])
    parser.add_argument("--root", type=Path, default=Path("data/backblaze-full"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--diagnostic-steps", type=int, default=0)
    parser.add_argument("--config", type=Path, default=Path("config/train_full.yaml"), help="Repository config YAML for preparation only")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.root, args.run, args.config)
    else:
        train(args.root, args.run, args.diagnostic_steps)
