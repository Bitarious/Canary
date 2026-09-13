from datetime import date
from types import SimpleNamespace

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytest.importorskip("torch")

from driftops.full_dataset import WINDOW_SCHEMA
from driftops.full_training import batches, compact_loss, example, raw_batches
from driftops.distributed_training import local_batch


def row(index):
    return {"task_id": f"task-{index}", "drive_id": f"drive-{index}",
            "start": date(2024,1,1), "cutoff": date(2024,1,28),
            "channels": ["smart_5_raw", "smart_194_raw"], "values": [[0.] * 28, list(range(28))],
            "target": "smart_5_raw: constant; smart_194_raw: rising."}


def test_training_iteration_covers_every_row_and_resumes_without_repetition(tmp_path):
    manifest = {"shards": {"a": {}, "b": {}}}
    for shard, start in [("a", 0), ("b", 11)]:
        path = tmp_path / "prepared" / shard
        path.mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist([row(i) for i in range(start,start+11)], schema=WINDOW_SCHEMA),
                       path / "train.parquet", row_group_size=5)
    complete = list(batches(tmp_path, manifest, 3, 123))
    seen = [e["audit"]["task_id"] for batch, _ in complete for e in batch]
    assert len(seen) == len(set(seen)) == 22
    cursor = complete[3][1]
    resumed = list(batches(tmp_path, manifest, 3, 123, cursor))
    assert resumed == complete[4:]
    assert list(batches(tmp_path, manifest, 3, 123)) == complete


def test_full_input_ignores_audit_targets_and_future_fields():
    original = row(1)
    expected = example(original)["inputs"]
    original.update(target="future failure", drive_id="other", failure=1, future_values=[999], partition="test")
    assert example(original)["inputs"] == expected
    changed = row(1)
    changed["values"][1].reverse()
    assert example(changed)["inputs"]["time_series_text"] == expected["time_series_text"]
    assert example(changed)["inputs"]["time_series"] != expected["time_series"]


def test_rank_preparation_preserves_inputs_empty_ranks_and_resume(tmp_path):
    path = tmp_path / "prepared" / "a"
    path.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist([row(i) for i in range(23)], schema=WINDOW_SCHEMA), path / "train.parquet", row_group_size=11)
    manifest = {"shards": {"a": {}}}
    full = list(batches(tmp_path, manifest, 8, 42))
    raw = list(raw_batches(tmp_path, manifest, 8, 42))
    saw_empty = False
    for (expected, position), (rows, raw_position) in zip(full, raw, strict=True):
        assert position == raw_position
        combined = []
        for rank in range(8):
            local, active = local_batch(rows, rank, 1)
            prepared = [example(item) for item in local]
            if active:
                combined.extend(prepared)
            else:
                saw_empty = True
                assert prepared == expected[:1]
        assert combined == expected
    assert saw_empty
    assert list(raw_batches(tmp_path, manifest, 8, 42, raw[1][1])) == raw[2:]


def test_chunked_answer_loss_and_gradients_match_full_logits(monkeypatch):
    torch = pytest.importorskip("torch")
    from driftops import full_training
    torch.manual_seed(1)
    inputs = torch.randn(2,8,6,requires_grad=True)
    labels = torch.tensor([[-100,-100,-100,2,1,5,3,0],[-100,-100,1,2,0,-100,-100,-100]])
    head = torch.nn.Linear(6,7,bias=False)
    model = SimpleNamespace(lora_enabled=False, llm=SimpleNamespace(
        model=lambda **kw: SimpleNamespace(last_hidden_state=kw["inputs_embeds"] * 1.7),
        lm_head=head, config=SimpleNamespace(final_logit_softcapping=3.)))
    monkeypatch.setattr(full_training,"training_tensors",lambda *_: (inputs,torch.ones(2,8),labels))
    computed = compact_loss(model, [], chunk_tokens=2)
    actual_grad = torch.autograd.grad(computed,(inputs,head.weight),retain_graph=True)
    logits = torch.tanh(head(inputs*1.7)/3.)*3.
    reference = torch.nn.functional.cross_entropy(logits[:,:-1].reshape(-1,7),labels[:,1:].reshape(-1))
    expected_grad = torch.autograd.grad(reference,(inputs,head.weight))
    torch.testing.assert_close(computed, reference)
    for actual, expected in zip(actual_grad, expected_grad):
        torch.testing.assert_close(actual,expected)
