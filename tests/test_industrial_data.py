from collections import Counter
import io

import numpy as np
import pytest

from driftops.component_data import partition
from driftops.industrial_data import csv_header, windows
from driftops.prepare_components import time_bounds
from driftops.windows import read_yaml


def test_explicit_industrial_groups_are_complete_and_separate():
    configs = read_yaml("config/industrial_studies.yaml")["components"]
    for component, config in configs.items():
        assignments = config["group_partitions"]
        assert Counter(assignments.values())["test"] == 5
        for group, split in assignments.items():
            assert partition(group, config) == split
        with pytest.raises(ValueError, match="lacks a declared"):
            partition("unknown-unit", config)
    assert configs["bearing"]["group_partitions"] == configs["gearbox"]["group_partitions"] == configs["pump"]["group_partitions"]


def test_industrial_windows_reject_imputed_values_gaps_and_future_rows():
    config = read_yaml("config/industrial_studies.yaml")["components"]["valve"]
    group = next(g for g,s in config["group_partitions"].items() if s == "train")
    first, stop = time_bounds("train", config)
    times = first + np.arange(28) * config["cadence_us"]
    values = np.column_stack([np.arange(28), np.full(28, 20.), np.full(28, 21.)])
    assert len(list(windows("valve1", group, times, values, config, Counter()))) == 1
    observed = np.ones(28, dtype=bool)
    observed[13] = False
    assert list(windows("valve1", group, times, values, config, Counter(), observed)) == []
    times[14:] += config["cadence_us"]
    assert list(windows("valve1", group, times, values, config, Counter())) == []
    times = stop - np.arange(27, -1, -1) * config["cadence_us"]
    assert list(windows("valve1", group, times, values, config, Counter())) == []


def test_turbine_header_requires_explicit_utc_and_bounded_lines():
    assert csv_header(io.BytesIO(b"# Time zone: UTC\n# Date and time,a\n")) == b"# Date and time,a\n"
    with pytest.raises(ValueError, match="declare UTC"):
        csv_header(io.BytesIO(b"# Date and time,a\n"))
    with pytest.raises(ValueError, match="size bound"):
        csv_header(io.BytesIO(b"x" * 64001))


def test_industrial_evidence_uses_groups_and_exact_small_sample_probability():
    import json
    from driftops.evaluate_industrial import evidence
    examples = [{"audit": {"group_id": str(group)}} for group in range(5) for _ in range(100)]
    result = evidence(examples, [.9] * 500, [.5] * 500)
    assert result["groups"] == 5
    assert result["one_sided_exact_group_sign_probability"] == 1 / 32
    assert result["passed"] is True
    json.dumps(result)
    fewer = evidence(examples[:400], [.9] * 400, [.5] * 400)
    assert fewer["one_sided_exact_group_sign_probability"] == 1 / 16
    assert fewer["passed"] is False
    inconsistent = evidence(examples, [.9] * 400 + [.49] * 100, [.5] * 500)
    assert inconsistent["passed"] is False


def test_industrial_window_selection_is_fixed_and_bounded_per_group(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from driftops.component_data import make_window, SCHEMA
    from driftops.evaluate_industrial import heldout_many
    config = read_yaml("config/industrial_studies.yaml")["components"]["valve"]
    groups = [g for g,s in config["group_partitions"].items() if s == "test"][:2]
    first, _ = time_bounds("test", config)
    rows = []
    for group in groups:
        for index in range(5):
            times = first + (np.arange(28) + index * 28) * config["cadence_us"]
            rows.append(make_window(group + ":valve", group, times, np.tile(np.arange(28), (3,1)), list(config["channels"]), config))
    directory = tmp_path / "prepared/0000"
    directory.mkdir(parents=True)
    manifest = {"groups": {"test": groups}, "shards": {"0000": {}}, "config": config}
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), directory / "test.parquet")
    first_result = heldout_many(tmp_path, manifest, "test", 2)
    pq.write_table(pa.Table.from_pylist(list(reversed(rows)), schema=SCHEMA), directory / "test.parquet")
    assert heldout_many(tmp_path, manifest, "test", 2) == first_result
    assert Counter(e["audit"]["group_id"] for e in first_result) == dict.fromkeys(groups, 2)
