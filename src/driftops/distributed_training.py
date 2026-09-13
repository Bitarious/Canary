"""Exact weighted batch reduction for one-node data-parallel fine-tuning."""

from datetime import timedelta
import os

import torch
import torch.distributed as dist

from driftops.full_training import compact_loss


class AnswerLoss(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, examples, weights):
        return compact_loss(self.model, examples, weights, return_normalizer=True)


def local_batch(examples, rank, size):
    """Assign each global example once. An empty rank performs a zero-weight forward."""
    selected = examples[rank * size:(rank + 1) * size]
    return (selected, True) if selected else (examples[:1], False)


def weighted_distributed_loss(value, normalizer, active=True):
    """Compensate for DDP gradient averaging with the exact global token weight."""
    local = normalizer if active else torch.zeros_like(normalizer)
    total = local.clone()
    if dist.is_initialized():
        dist.all_reduce(total)
        world = dist.get_world_size()
    else:
        world = 1
    if total.item() <= 0:
        raise ValueError("The global batch has no target weight")
    return value * (world * local / total)


class DistributedRun:
    def __init__(self):
        self.world = int(os.environ.get("WORLD_SIZE", "1"))
        self.rank = int(os.environ.get("RANK", "0"))
        self.local_rank = int(os.environ.get("LOCAL_RANK", "0"))
        self.primary = self.rank == 0
        if not 0 <= self.rank < self.world or self.world not in (1, 8):
            raise ValueError("The GPU run must use one GPU or the approved eight-GPU node")
        torch.cuda.set_device(self.local_rank)
        self.device = f"cuda:{self.local_rank}"
        if self.world > 1:
            dist.init_process_group("nccl", timeout=timedelta(minutes=3))

    def wrap(self, model):
        loss = AnswerLoss(model)
        return torch.nn.parallel.DistributedDataParallel(loss, device_ids=[self.local_rank]) if self.world > 1 else loss

    def barrier(self):
        if self.world > 1:
            dist.barrier()

    def any(self, value):
        flag = torch.tensor(int(value), device=self.device)
        if self.world > 1:
            dist.all_reduce(flag, op=dist.ReduceOp.MAX)
        return bool(flag.item())

    def mean(self, value):
        number = value.detach().clone()
        if self.world > 1:
            dist.all_reduce(number)
            number /= self.world
        return number.item()

    def rng_states(self):
        state = torch.cuda.get_rng_state().to(self.device)
        states = [torch.empty_like(state) for _ in range(self.world)]
        if self.world > 1:
            dist.all_gather(states, state)
        else:
            states = [state]
        return [state.cpu() for state in states]

    def close(self):
        if self.world > 1:
            dist.destroy_process_group()
