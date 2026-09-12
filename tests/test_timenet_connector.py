from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json

import pytest
from timenet.reader import TimeFReader
from timenet.registry.version import DatasetVersion
from timenet.writer import TimeFWriter
import yaml

from driftops.acquire import CHANNELS
from driftops.timenet_connector import BackblazeConnector, DAY_US, RawReference, model_input, verify_roundtrip
from driftops.windows import partition_for, read_yaml


@pytest.fixture
def fixture_cohort(tmp_path, monkeypatch):
    config = read_yaml("config/dataset.yaml")
    splits = read_yaml("config/splits.yaml")
    serial = next(f"fixture-{i}" for i in range(100) if partition_for(f"fixture-{i}", splits)[0] == "train")
    rows = []
    for i in range(36):
        row = {"date": date(2024, 7, 1) + timedelta(days=i), "serial_number": serial,
               "model": config["model"], "capacity_bytes": 8_000_000_000_000, "failure": int(i == 35)}
        row.update({channel: 0 for channel in CHANNELS})
        row.update(smart_5_raw=i, smart_194_raw=30 + i % 3, smart_188_raw=2**40)
        if i == 30:
            row["smart_194_raw"] = None
        rows.append(row)
    config_path = tmp_path / "dataset.yaml"
    config["raw_path"] = str(tmp_path / "fixture.parquet")
    config_path.write_text(yaml.safe_dump(config))
    monkeypatch.setenv("DRIFTOPS_DATASET_CONFIG", str(config_path))
    return tmp_path, rows, config


def write_fixture(tmp_path, rows):
    import pyarrow as pa
    import pyarrow.parquet as pq
    path = tmp_path / "fixture.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path)
    manifest = {"parquet_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest))
    return RawReference(path, manifest)


def test_timef_round_trip_preserves_values_time_metadata_and_targets(fixture_cohort):
    tmp_path, rows, config = fixture_cohort
    ref = write_fixture(tmp_path, rows)
    connector = BackblazeConnector()
    assert connector.download(tmp_path) == [ref]
    dataset = connector.convert([ref])
    assert len(dataset.records) == 1
    assert len(dataset.tasks) == 2
    with TimeFWriter(tmp_path / "timef", dataset) as writer:
        writer.write()
    version_dir = tmp_path / "timef" / dataset.metadata.dataset_id / str(dataset.metadata.dataset_version)
    loaded = TimeFReader(DatasetVersion.open_local(version_dir)).read()
    verify_roundtrip(dataset, loaded, config["lookback_days"])
    original, restored = dataset.records[0], loaded.records[0]
    assert restored.subject_ids == original.subject_ids
    assert restored.start_time == original.start_time
    assert restored.annotations == original.annotations
    for series in restored.time_series:
        assert series.to_arrow().to_pylist() == [row[series.signal] for row in rows]
        assert series.time_offsets_us().tolist() == [i * DAY_US for i in range(len(rows))]
    assert [(task.id, task.target, task.scope) for task in loaded.tasks] == [
        (task.id, task.target, task.scope) for task in dataset.tasks]
    assert model_input(restored, loaded.tasks[0]) == model_input(original, dataset.tasks[0])


def test_targets_annotations_and_future_values_are_excluded(fixture_cohort):
    tmp_path, rows, _ = fixture_cohort
    original = BackblazeConnector().convert([write_fixture(tmp_path, rows)])
    expected = model_input(original.records[0], original.tasks[0])
    changed_rows = deepcopy(rows)
    for row in changed_rows[28:]:
        row["smart_5_raw"] = 987654321
        row["failure"] = 0
    changed = BackblazeConnector().convert([write_fixture(tmp_path, changed_rows)])
    # The loader has a fixed neutral prompt even if task metadata is changed.
    changed.tasks[0].target = "LEAKED_TARGET_SENTINEL"
    changed.tasks[0].prompt = "LEAKED_PROMPT_SENTINEL"
    result = model_input(changed.records[0], changed.tasks[0])
    assert result == expected
    assert set(result) == {"pre_prompt", "time_series", "time_series_text", "post_prompt"}
    serialized = json.dumps(result)
    assert "SENTINEL" not in serialized
    assert rows[0]["serial_number"] not in serialized
    assert "recorded_failure" not in serialized
    assert "987654321" not in serialized


def test_duplicate_source_dates_are_rejected(fixture_cohort):
    tmp_path, rows, _ = fixture_cohort
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError, match="duplicate_days=1"):
        BackblazeConnector().convert([write_fixture(tmp_path, rows)])


def test_checksum_and_integer_precision_are_enforced(fixture_cohort):
    tmp_path, rows, _ = fixture_cohort
    ref = write_fixture(tmp_path, rows)
    ref.path.with_suffix(".manifest.json").write_text(json.dumps({"parquet_sha256": "wrong"}))
    with pytest.raises(ValueError, match="checksum"):
        BackblazeConnector().download(tmp_path)
    rows[0]["smart_188_raw"] = 2**53 + 1
    with pytest.raises(ValueError, match="exact float64"):
        BackblazeConnector().convert([write_fixture(tmp_path, rows)])
