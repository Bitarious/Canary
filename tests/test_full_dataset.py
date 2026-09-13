from collections import Counter
from datetime import date, timedelta
import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from driftops.acquire import CHANNELS
from driftops.annotations import describe_channel
from driftops.full_dataset import CONFIG, build_bucket, drive_partition, eligible_windows, media_type, patterns
from driftops.full_prepare import SCHEMA
from driftops.tslm_dataset import PATTERNS
from driftops.windows import partition_for, read_yaml


def test_full_splits_preserve_device_assignment_and_ordered_dates():
    full, pilot = read_yaml(CONFIG), read_yaml("config/splits.yaml")
    for i in range(1000):
        serial = f"fixture-{i}"
        assert drive_partition(serial, full)[0] == partition_for(serial, pilot)[0]
    partitions = full["partitions"]
    assert partitions["train"]["end"] < partitions["validation"]["start"]
    assert partitions["validation"]["end"] < partitions["test"]["start"]


def test_calendar_gaps_failure_and_time_boundaries():
    rule = {"start": "2024-01-01", "end": "2024-02-29"}
    rows = [{"date": date(2024, 1, 1)+timedelta(days=i), "failure": int(i==58)} for i in range(90)]
    windows = list(eligible_windows(rows, rule, Counter()))
    assert len(windows) == 2
    assert windows[-1][-1]["date"] == date(2024, 2, 25)
    rows.pop(5)
    windows = list(eligible_windows(rows, rule, Counter()))
    assert len(windows) == 1
    assert windows[0][0]["date"] == date(2024, 1, 7)
    with pytest.raises(ValueError, match="duplicate"):
        list(eligible_windows([rows[0], rows[0]], rule, Counter()))


def test_vectorized_labels_match_existing_rules():
    rng = np.random.default_rng(61)
    channels = read_yaml(CONFIG)["language_channels"]
    values = rng.integers(0, 8, (80, len(channels), 28)).astype(float)
    values[:3] = 0
    values[3:6] = np.arange(28)
    values[6:9] = -np.arange(28)
    result = patterns(values, channels)
    for i, sample in enumerate(values):
        for j, channel in enumerate(channels):
            assert PATTERNS[int(result[i,j])] == describe_channel(channel, sample[j])["pattern"]


def test_native_full_history_shard_roundtrip_and_restart(tmp_path):
    config = read_yaml(CONFIG)
    serials = {}
    for i in range(1000):
        serial = f"fixture-{i}"
        split, rule = drive_partition(serial, config)
        serials.setdefault(split, (serial, rule))
    rows = []
    for serial, rule in serials.values():
        for i in range(56):
            rows.append({"serial_number": serial, "model": "ST8000NM0055", "capacity_bytes": 8000000000000,
                         "date": date.fromisoformat(rule["start"])+timedelta(days=i), "failure": 0,
                         **{c: float(i % 9) if c == "smart_194_raw" else 0. for c in CHANNELS}})
    source = tmp_path / "shards" / "bucket=00"
    source.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), source / "fixture.parquet")
    (source.parent / "manifest.json").write_text(json.dumps({"fixture": True}))
    manifest = build_bucket((str(tmp_path), "00"))
    for split, (serial, rule) in serials.items():
        table = pq.read_table(tmp_path / "prepared" / "00" / (split+".parquet"))
        assert len(table) == 2
        assert table["drive_id"].to_pylist() == ["backblaze:" + serial] * 2
        assert min(table["start"].to_pylist()) >= date.fromisoformat(rule["start"])
        assert max(table["cutoff"].to_pylist()) <= date.fromisoformat(rule["end"])
    assert build_bucket((str(tmp_path), "00")) == manifest


def test_ssd_and_unknown_models_are_not_hdd():
    assert media_type("WDC  WUH721816ALE6L4") == "hdd"
    assert media_type("DELLBOSS VD") == "ssd"
    assert media_type("WDC  WDS250G2B0A") == "ssd"
    assert media_type("unidentified") == "unknown"
