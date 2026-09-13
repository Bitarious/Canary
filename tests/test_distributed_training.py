from datetime import timedelta
import json
from pathlib import Path

import pytest
import torch
import torch.distributed as dist
import torch.multiprocessing as mp

from driftops.distributed_training import local_batch, weighted_distributed_loss


def _worker(rank, rendezvous, output):
    torch.set_num_threads(1)
    dist.init_process_group("gloo", init_method="file://" + rendezvous, rank=rank,
                            world_size=2, timeout=timedelta(seconds=30))
    layer = torch.nn.Linear(2, 1, bias=False, dtype=torch.float64)
    with torch.no_grad():
        layer.weight.copy_(torch.tensor([[.3, -.7]], dtype=torch.float64))
    model = torch.nn.parallel.DistributedDataParallel(layer)
    results = []
    for count in (3, 1):
        rows = [(1., 2., .5, 1.), (2., -1., 1.5, 3.), (-2., 4., -.5, 2.)][:count]
        selected, active = local_batch(rows, rank, 2)
        data = torch.tensor(selected, dtype=torch.float64)
        model.zero_grad(set_to_none=True)
        prediction = model(data[:, :2]).squeeze(-1)
        normalizer = data[:, 3].sum()
        value = ((prediction - data[:, 2]).square() * data[:, 3]).sum() / normalizer
        weighted_distributed_loss(value, normalizer, active).backward()
        results.append(layer.weight.grad.tolist())
    Path(output + str(rank) + ".json").write_text(json.dumps(results))
    dist.destroy_process_group()


def test_weighted_ddp_matches_global_batch_including_empty_rank(tmp_path):
    rendezvous = str(tmp_path / "rendezvous")
    output = str(tmp_path / "rank")
    mp.spawn(_worker, args=(rendezvous, output), nprocs=2, join=True)
    expected = []
    for count in (3, 1):
        data = torch.tensor([(1., 2., .5, 1.), (2., -1., 1.5, 3.), (-2., 4., -.5, 2.)][:count], dtype=torch.float64)
        weight = torch.tensor([[.3, -.7]], dtype=torch.float64, requires_grad=True)
        predictions = (data[:, :2] @ weight.T).squeeze(-1)
        loss = ((predictions - data[:, 2]).square() * data[:, 3]).sum() / data[:, 3].sum()
        loss.backward()
        expected.append(weight.grad)
    for rank in range(2):
        actual = json.loads(Path(output + str(rank) + ".json").read_text())
        for a, e in zip(actual, expected):
            torch.testing.assert_close(torch.tensor(a, dtype=torch.float64), e, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("count", [1, 63, 64, 65, 511, 512])
def test_global_examples_are_assigned_once(count):
    examples = list(range(count))
    assigned = []
    for rank in range(8):
        batch, active = local_batch(examples, rank, 64)
        if active:
            assigned.extend(batch)
        else:
            assert batch == examples[:1]
    assert assigned == examples
