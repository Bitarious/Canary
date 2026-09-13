"""Prepare, run, and resume bounded temporal-module adaptation."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import shutil
import signal
import time

import torch

from driftops.cli import checksum
from driftops.opentslm import generate, load_model, loss, temporal_state
from driftops.tslm_dataset import load_examples, support, PREPROCESSING_VERSION, PROMPT_VERSION
from driftops.windows import read_yaml


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def save_checkpoint(path, value):
    temporary = path.with_suffix(".part")
    torch.save(value, temporary)
    temporary.replace(path)


def parameter_hash(module):
    digest = hashlib.sha256()
    for name, value in module.state_dict().items():
        digest.update(name.encode())
        digest.update(value.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def prepare(run, diagnostic, steps=None):
    config = read_yaml("config/train_tslm.yaml")
    if diagnostic:
        config.update(train_windows=4, validation_windows=4, steps=30,
                      validation_every=10, max_seconds=600, patience=4)
    if steps is not None:
        if steps < 1:
            raise ValueError("The step limit must be positive")
        config["steps"] = steps
    train = load_examples("train", config["train_windows"])
    validation = load_examples("validation", config["validation_windows"])
    overview = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "diagnostic" if diagnostic else "concept-finetune",
        "objective": "Reduce answer-token cross entropy for descriptions of four observed SMART channels.",
        "necessity": "Prove numerical-module optimization and reload before the held-out concept test." if diagnostic else
                     "Test whether adapting OpenTSLM improves rule agreement on unseen drives and later dates.",
        "data": {"train": support(train), "validation": support(validation),
                 "selection": "One window per drive, ordered by a fixed task-ID hash. Targets do not select samples.",
                 "split_config": read_yaml("config/splits.yaml"),
                 "source_sha256": checksum(Path("examples/backblaze-pilot/backblaze.parquet")),
                 "annotation": "window-description-v1, deterministic weak supervision"},
        "updated_parameters": ["encoder, 2110976 parameters", "projector, 82816 parameters"],
        "frozen_parameters": "All Gemma language-model parameters. No LoRA.",
        "hardware_and_cost": "Local Ryzen AI Max+ 395 CPU, 8 threads, bfloat16 Gemma, float32 temporal modules. No cloud charge. Electricity unmeasured.",
        "stopping": "Stop at configured steps, runtime cap, nonfinite loss/gradients, or validation patience. Save every 10 steps.",
        "evaluation": "Diagnostic train loss, gradients, input ablation, unchanged Gemma, changed temporal weights, and fresh-process reload." if diagnostic else
                      "Select by validation answer loss. Compare starting and selected models on 64 held-out drives, then zero-series ablation. No test-based tuning.",
        "outputs": ["overview.json", "train.json", "validation.json", "progress.jsonl", "best.pt", "last.pt", "result.json"],
        "config": config, "model": read_yaml("config/model.yaml"),
        "preprocessing": PREPROCESSING_VERSION, "prompt": PROMPT_VERSION,
    }
    run.mkdir(parents=True, exist_ok=False)
    write_json(run / "overview.json", overview)
    write_json(run / "train.json", train)
    write_json(run / "validation.json", validation)
    source_files = [Path("pyproject.toml"), Path("uv.lock"), *Path("config").glob("*.yaml"),
                    *Path("src/driftops").rglob("*.py")]
    source_hashes = {}
    for path in source_files:
        destination = run / "source" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        source_hashes[str(path)] = checksum(path)
    write_json(run / "source-hashes.json", source_hashes)
    print(json.dumps(overview, indent=2), flush=True)


@torch.no_grad()
def evaluate_loss(model, examples, batch_size):
    model.eval()
    weighted = []
    for start in range(0, len(examples), batch_size):
        batch = examples[start:start + batch_size]
        weighted.append((float(loss(model, batch)), len(batch)))
    return sum(value * count for value, count in weighted) / sum(count for _, count in weighted)


def run_training(run, resume=False):
    overview = json.loads((run / "overview.json").read_text())
    config = overview["config"]
    if not resume and (run / "progress.jsonl").exists():
        raise ValueError("This run already started. Use --resume or prepare a new run directory")
    torch.set_num_threads(config["threads"])
    torch.manual_seed(config["seed"])
    random.seed(config["seed"])
    train = json.loads((run / "train.json").read_text())
    validation = json.loads((run / "validation.json").read_text())
    model = load_model(config["device"])
    initial_hashes = {name: parameter_hash(getattr(model, name)) for name in ("llm", "encoder", "projector")}
    optimizer = torch.optim.AdamW([
        {"params": model.encoder.parameters(), "lr": config["learning_rate_encoder"]},
        {"params": model.projector.parameters(), "lr": config["learning_rate_projector"]},
    ], weight_decay=config["weight_decay"])
    generator = torch.Generator().manual_seed(config["seed"])
    step, consumed, stale = 0, 0.0, 0
    best = float("inf")
    initial_train_loss = evaluate_loss(model, train[:min(16, len(train))], config["batch_size"])
    if resume:
        checkpoint = torch.load(run / "last.pt", weights_only=True, map_location="cpu")
        if checkpoint["overview_sha256"] != checksum(run / "overview.json"):
            raise ValueError("The run overview changed since the checkpoint")
        model.encoder.load_state_dict(checkpoint["encoder_state"])
        model.projector.load_state_dict(checkpoint["projector_state"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        torch.set_rng_state(checkpoint["rng"])
        generator.set_state(checkpoint["sampler_rng"])
        step, consumed, stale, best = (checkpoint[k] for k in ("step", "elapsed_seconds", "stale", "best"))
    started = time.monotonic()
    remaining = config["max_seconds"] - consumed
    if remaining <= 0:
        raise ValueError("The run has exhausted its runtime budget")
    stop_reason = "step_limit"

    def alarm_handler(signum, frame):
        raise TimeoutError("Training runtime limit reached")

    old_handler = signal.signal(signal.SIGALRM, alarm_handler)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    gradients = {}
    try:
        with (run / "progress.jsonl").open("a", buffering=1) as log:
            while step < config["steps"]:
                indices = torch.randint(len(train), (config["batch_size"],), generator=generator).tolist()
                batch = [train[index] for index in indices]
                model.train()
                model.llm.eval()
                optimizer.zero_grad(set_to_none=True)
                value = loss(model, batch)
                if not torch.isfinite(value):
                    raise FloatingPointError("Nonfinite training loss")
                value.backward()
                for name in ("encoder", "projector"):
                    gradients[name] = sum(float(p.grad.detach().float().norm()) for p in getattr(model, name).parameters() if p.grad is not None)
                    if not gradients[name] > 0:
                        raise RuntimeError(f"No gradient reached {name}")
                if any(p.grad is not None or p.requires_grad for p in model.llm.parameters()):
                    raise RuntimeError("Gemma must remain frozen")
                torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],
                                               config["gradient_clip"], error_if_nonfinite=True)
                optimizer.step()
                step += 1
                entry = {"step": step, "train_loss": float(value.detach()),
                         "elapsed_seconds": consumed + time.monotonic() - started}
                if step % config["validation_every"] == 0 or step == config["steps"]:
                    validation_loss = evaluate_loss(model, validation, config["batch_size"])
                    entry["validation_loss"] = validation_loss
                    # The tiny overfit diagnostic selects on its training batch.
                    selection = evaluate_loss(model, train, config["batch_size"]) if overview["mode"] == "diagnostic" else validation_loss
                    if selection < best:
                        best, stale = selection, 0
                        save_checkpoint(run / "best.pt", temporal_state(model))
                    else:
                        stale += 1
                    print(json.dumps(entry), flush=True)
                log.write(json.dumps(entry, allow_nan=False) + "\n")
                if step % 10 == 0 or step == config["steps"]:
                    checkpoint = temporal_state(model)
                    checkpoint.update(optimizer=optimizer.state_dict(), rng=torch.get_rng_state(),
                                      sampler_rng=generator.get_state(), step=step, stale=stale, best=best,
                                      elapsed_seconds=consumed + time.monotonic() - started,
                                      overview_sha256=checksum(run / "overview.json"))
                    save_checkpoint(run / "last.pt", checkpoint)
                if stale >= config["patience"]:
                    stop_reason = "validation_patience"
                    break
    except TimeoutError:
        stop_reason = "runtime_limit"
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
    final_hashes = {name: parameter_hash(getattr(model, name)) for name in initial_hashes}
    if initial_hashes["llm"] != final_hashes["llm"]:
        raise RuntimeError("Frozen Gemma weights changed")
    result = {"steps": step, "stop_reason": stop_reason,
              "elapsed_seconds": consumed + time.monotonic() - started,
              "initial_train_probe_loss": initial_train_loss,
              "final_train_probe_loss": evaluate_loss(model, train[:min(16, len(train))], config["batch_size"]),
              "best_selection_loss": best if best != float("inf") else None,
              "initial_hashes": initial_hashes, "final_hashes": final_hashes,
              "gradient_norm_sums": gradients,
              "selected_checkpoint_sha256": checksum(run / "best.pt") if (run / "best.pt").exists() else None,
              "peak_process_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
              "cloud_spend_usd": 0}
    write_json(run / "result.json", result)
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "train", "reload"])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--steps", type=int, help="Record an explicit step limit when preparing a run")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.run, args.diagnostic, args.steps)
    elif args.action == "train":
        run_training(args.run, args.resume)
    else:
        overview = json.loads((args.run / "overview.json").read_text())
        torch.set_num_threads(overview["config"]["threads"])
        torch.manual_seed(overview["config"]["seed"])
        model = load_model(checkpoint=args.run / "best.pt")
        examples = json.loads((args.run / "train.json").read_text())[:4]
        result = {"checkpoint_sha256": checksum(args.run / "best.pt"),
                  "loss": evaluate_loss(model, examples, 4),
                  "predictions": generate(model, examples), "targets": [x["target"] for x in examples]}
        write_json(args.run / "reload.json", result)
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
