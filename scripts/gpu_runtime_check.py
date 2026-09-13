#!/usr/bin/env python3
"""Run the bounded training-only CUDA check described in its advance overview."""

import argparse
import gc
import json
from pathlib import Path
import signal
import time

import torch

from driftops.acquire import write_json
from driftops.full_archive import file_hash
from driftops.full_training import compact_loss
from driftops.distributed_training import DistributedRun, local_batch, weighted_distributed_loss
from driftops.opentslm import load_model, temporal_state
from driftops.train_full import atomic_save
from driftops.windows import read_yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    run = parser.parse_args().run
    overview = json.loads((run / "overview.json").read_text())
    if (run / "started.json").exists():
        raise ValueError("This diagnostic already started. Preserve its artifacts")
    if file_hash(run / "examples.json") != overview["examples_sha256"]:
        raise ValueError("The diagnostic input checksum is incorrect")
    examples = json.loads((run / "examples.json").read_text())
    config = read_yaml("config/train_full.yaml")
    if len(examples) != overview["steps"] * config["batch_size"] * config.get("world_size", 1):
        raise ValueError("The diagnostic batch count is incorrect")
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("The GPU check reached its time limit")))
    signal.alarm(overview["time_limit_seconds"])
    torch.set_num_threads(8)
    parallel = DistributedRun()
    if parallel.world != config.get("world_size", 1):
        raise ValueError("The diagnostic GPU count differs from its configuration")
    torch.manual_seed(config["seed"])
    torch.cuda.manual_seed_all(config["seed"])
    start = time.monotonic()
    if parallel.primary:
        write_json(run / "started.json", {"unix_seconds": time.time()})
    parallel.barrier()
    model = load_model(parallel.device, lora_config=config["lora"])
    loss_module = parallel.wrap(model)
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW([
        {"params": model.encoder.parameters(), "lr": config["encoder_lr"]},
        {"params": model.projector.parameters(), "lr": config["projector_lr"]},
        {"params": model.get_lora_parameters(), "lr": config["lora_lr"]},
    ], weight_decay=config["weight_decay"])
    measurements = []
    for step in range(overview["steps"]):
        size = config["batch_size"] * parallel.world
        global_examples = examples[step * size:(step + 1) * size]
        batch, active = local_batch(global_examples, parallel.rank, config["batch_size"])
        loss_module.train()
        torch.cuda.synchronize()
        before = time.monotonic()
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            value, normalizer = loss_module(batch, None)
            loss = weighted_distributed_loss(value, normalizer, active)
        if parallel.any(not torch.isfinite(loss)):
            raise ValueError("The diagnostic loss is not finite")
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(params, config["clip_grad_norm"], error_if_nonfinite=True)
        optimizer.step()
        torch.cuda.synchronize()
        record = {"step": step + 1, "seconds": time.monotonic() - before,
                  "loss": parallel.mean(loss), "gradient_norm": norm.item()}
        measurements.append(record)
        if parallel.primary:
            write_json(run / "measurements.json", measurements)
            print(json.dumps(record), flush=True)
    del loss_module, optimizer, params
    parallel.barrier()
    if not parallel.primary:
        del model
        gc.collect()
        torch.cuda.empty_cache()
        parallel.barrier()
        parallel.close()
        return
    state = temporal_state(model)
    atomic_save(run / "diagnostic.pt", state)
    model.eval()
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        before_reload = compact_loss(model, examples[:16]).item()
    del model
    gc.collect()
    torch.cuda.empty_cache()
    restored = load_model(parallel.device, checkpoint=run / "diagnostic.pt")
    restored_state = temporal_state(restored)
    for group in ("encoder_state", "projector_state", "lora_state"):
        if state[group].keys() != restored_state[group].keys() or any(
            not torch.equal(value, restored_state[group][key]) for key, value in state[group].items()
        ):
            raise ValueError("A restored parameter differs from the saved diagnostic")
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        after_reload = compact_loss(restored, examples[:16]).item()
    if abs(before_reload - after_reload) > 1e-5:
        raise ValueError("The diagnostic reload loss differs")
    result = {"passed": True, "steps": overview["steps"], "training_examples": len(examples),
              "elapsed_seconds": time.monotonic() - start,
              "warm_step_mean_seconds": sum(x["seconds"] for x in measurements[2:]) / len(measurements[2:]),
              "peak_gpu_bytes": torch.cuda.max_memory_allocated(), "gpu": torch.cuda.get_device_name(),
              "gpu_count": parallel.world, "global_batch_size": config["batch_size"] * parallel.world,
              "torch": torch.__version__, "cuda": torch.version.cuda,
              "checkpoint_sha256": file_hash(run / "diagnostic.pt"),
              "reload_loss_before": before_reload, "reload_loss_after": after_reload,
              "use_for_full_training": False}
    write_json(run / "result.json", result)
    signal.alarm(0)
    print(json.dumps(result), flush=True)
    parallel.barrier()
    parallel.close()


if __name__ == "__main__":
    main()
