from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pyarrow.parquet as pq
import pytest

from driftops.component_data import build, example, make_window, partition, target
from driftops.component_training import heldout, perturb, training_example


def config():
    return {"component": "fixture", "version": "test-v1", "split_salt": "test:",
        "channels": {"temperature": {"unit": "celsius", "description": "temperature in Celsius", "minimum_band": 1},
                     "events": {"unit": "count", "description": "cumulative events", "minimum_band": 1, "counter": True}},
        "cadence_us": 10_000_000, "cadence_text": "observations every ten seconds",
        "partitions": {name: {"buckets": bounds, "start": f"2020-0{i+1}-01T00:00:00+00:00",
                              "stop": f"2020-0{i+2}-01T00:00:00+00:00"}
                       for i, (name, bounds) in enumerate(zip(("train", "validation", "calibration", "test"),
                                                            ((0, 60), (60, 75), (75, 85), (85, 100))))},
        "scope": "Test observed signals", "source_type": "test", "source_url": "https://example.com/data",
        "license": "CC-BY-4.0", "license_url": "https://example.com/license", "citation": "Test fixture", "provider": "Test"}


def rows(cfg):
    for split, rule in cfg["partitions"].items():
        group = next(str(i) for i in range(1000) if partition(str(i), cfg) == split)
        origin = int(datetime.fromisoformat(rule["start"]).timestamp() * 1e6)
        times = origin + np.arange(28) * cfg["cadence_us"]
        yield make_window("device:" + group, "" + group, times, [np.arange(28), np.arange(28)],
                          ["temperature", "events"], cfg)


def test_native_component_roundtrip_and_input_boundary(tmp_path):
    cfg = config()
    cfg.update(license="CDLA-Sharing-1.0", timef_license="other", license_url="https://cdla.dev/sharing-1-0/")
    samples = list(rows(cfg))
    result = build(tmp_path / "data", iter(samples), cfg, {"fixture": "deterministic"})
    assert all(len(ids) == 1 for ids in result["groups"].values())
    restored = pq.read_table(tmp_path / "data/prepared/0000/train.parquet").to_pylist()[0]
    assert example(restored, cfg) == example(samples[0], cfg)
    original = example(restored, cfg)["inputs"]
    changed = deepcopy(restored)
    changed.update(drive_id="secret-device", group_id="secret-host", split="test")
    assert example(changed, cfg)["inputs"] == original
    assert "secret" not in str(original)
    selected = heldout(tmp_path / "data", result, "validation", 1)
    assert selected[0]["audit"]["group_id"] == samples[1]["group_id"]


def test_component_time_boundary_gap_and_counter_response():
    cfg = config()
    row = next(rows(cfg))
    args = [row["drive_id"], row["group_id"], row["times_us"], row["values"], row["channels"], cfg]
    gap = deepcopy(args)
    gap[2][-1] += cfg["cadence_us"]
    with pytest.raises(ValueError, match="calendar gap"):
        make_window(*gap)
    outside = deepcopy(args)
    outside[2] = [x + 100 * 86400 * 1_000_000 for x in args[2]]
    with pytest.raises(ValueError, match="split time"):
        make_window(*outside)
    reverse = target(np.asarray(row["values"])[:, ::-1], row["channels"], cfg)
    assert reverse == "temperature: falling; events: counter reset or decrease."
    bad = deepcopy(row)
    bad["target"] = "temperature: constant; events: constant."
    with pytest.raises(ValueError, match="target"):
        example(bad, cfg)


def test_component_augmentation_preserves_text_and_recomputes_targets():
    cfg = config()
    row = next(rows(cfg))
    original = example(row, cfg)
    assert training_example(row, cfg, 0, 5) == original
    reverse = perturb([original], "reversed", cfg)[0]
    assert reverse["target"] == "temperature: falling; events: counter reset or decrease."
    assert reverse["inputs"]["time_series_text"] == original["inputs"]["time_series_text"]
    assert reverse["audit"]["input_hash"] != original["audit"]["input_hash"]
    assert original["raw_values"][0][0] == 0
    zero = perturb([original], "zero_numerical_embeddings", cfg)[0]
    assert zero["target"] == original["target"]
    assert np.count_nonzero(zero["inputs"]["time_series"]) == 0
    assert training_example(row, cfg, 3, 5) == training_example(row, cfg, 3, 5)
