from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq

from driftops.component_data import partition
from driftops.memory_data import count_device, initialize_worker, specification, windows
from driftops.full_archive import file_hash
from driftops import prepare_components
from driftops.nvme_data import connected_groups, report_row


def test_memory_log_counts_exclude_ticket_and_unknown_error_types(tmp_path):
    path = tmp_path / "memory.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("type_A/sn_1.csv", "LogTime,error_type_full_name\n1704067203,CE.READ\n1704067201,CE.SCRUB\n1704067202,OTHER\n1704067204,CE.READ\n")
    initialize_worker(path)
    result = count_device(("type_A/sn_1.csv", 1704067204))
    assert result["days"] == [[19723, 1, 1]]
    assert result["first_log"] == 1704067201
    assert result["audit"]["rows_at_after_failure_ticket"] == 1
    assert result["audit"]["rows_other_error_types"] == 1


def test_memory_window_uses_closed_days_and_no_future_logs(tmp_path):
    config = specification()
    name = next(f"type_A/sn_{i}.csv" for i in range(100) if partition(f"type_A/sn_{i}.csv", config) == "train")
    origin = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    first_day = origin // 86400
    records = [{"name": name, "alarm": None, "first_log": origin, "day": first_day + day,
                "read_error_logs": day + 1, "scrub_error_logs": 1} for day in (0, 27, 34)]
    path = tmp_path / "counts.parquet"
    pq.write_table(pa.Table.from_pylist(records), path)
    before = list(windows(path, config, Counter()))
    assert len(before) == 2
    assert before[0]["values"][0] == [1] + [0] * 26 + [28]
    assert before[0]["cutoff"].isoformat() == "2024-01-29T00:00:00+00:00"
    records[-1]["read_error_logs"] = 90000
    pq.write_table(pa.Table.from_pylist(records), path)
    after = list(windows(path, config, Counter()))
    assert before[0] == after[0]


def test_clusterwise_gpu_slot_mapping_and_availability(tmp_path, monkeypatch):
    cfg = prepare_components.specification("gpu")
    host = next(str(i) for i in range(100) if partition("clusterwise:" + str(i), cfg) == "train")
    rows = []
    for i in range(28):
        row = {"hostname": host, "timestamp": datetime(2020, 1, 1) + timedelta(seconds=10*i)}
        for slot in range(6):
            row.update({f"p{slot//3}_gpu{slot%3}_power": 100*slot+i,
                        f"gpu{slot}_core_temp": 30+slot+i, f"gpu{slot}_mem_temp": 40+slot+i})
        rows.append(row)
    path = tmp_path / "clusterwise-20200101.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path)
    path.with_name(path.name + "-receipt.json").write_text(json.dumps({"sha256": file_hash(path)}))
    settings = prepare_components.read_yaml(prepare_components.CONFIG)["clusterwise"]
    settings["source_days"] = ["20200101"]
    monkeypatch.setattr(prepare_components, "AUDIT", tmp_path)
    monkeypatch.setattr(prepare_components, "read_yaml", lambda _: {"clusterwise": settings})
    monkeypatch.setattr(prepare_components, "clusterwise_hosts", lambda _: {"train": [host]})
    result = list(prepare_components.clusterwise_windows(cfg, Counter()))
    assert len(result) == 6
    assert result[3]["values"][0][0] == 300
    assert result[3]["values"][1][0] == 33
    assert result[3]["start"].isoformat() == "2020-01-01T00:00:10+00:00"
    assert result[3]["cutoff"].isoformat() == "2020-01-01T00:04:40+00:00"


def test_nvme_migration_keeps_devices_and_hosts_together():
    edges = [("a", "host1"), ("b", "host1"), ("b", "host2"), ("c", "host2"), ("d", "host3")]
    groups = connected_groups(edges)
    assert groups["a"] == groups["b"] == groups["c"]
    assert groups["d"] != groups["a"]
    assert groups == connected_groups(list(reversed(edges)))


def test_nvme_invalid_collection_is_not_a_failure_label():
    raw = {"invalid": "f", "ts": "2021-01-01 01:02:03", "device_uuid": "00000000-0000-0000-0000-000000000001",
           "report": json.dumps({"device": {"protocol": "NVMe"}, "model_name": "test NVMe", "host_id": "00000000-0000-0000-0000-000000000002",
                       "nvme_smart_health_information_log": {"temperature": 30, "media_errors": 0, "power_on_hours": 100, "percentage_used": 2}})}
    audit = Counter()
    valid = report_row(raw, "2021-01", audit)
    assert valid["temperature"] == 30
    assert "failure" not in valid
    assert report_row(raw, "2021-02", audit) is None
    raw["invalid"] = "t"
    assert report_row(raw, "2021-01", audit) is None
    assert audit["invalid_collection_reports"] == 1


def test_fan_modules_keep_host_groups_and_use_interval_end(tmp_path, monkeypatch):
    import io
    import tarfile
    from driftops import fan_data
    from driftops.windows import read_yaml

    config = read_yaml(fan_data.CONFIG)
    number = next(i for i in range(20, 200) if partition(f"m100:node-{i}", config) == "train")
    group = f"m100:node-{number}"
    rows = []
    for i in range(28):
        row = {"timestamp": datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15*i), "value": 999}
        row.update({f"fan{module}_{rotor}_avg": 1000 + 100*module + rotor + i for module in range(4) for rotor in range(2)})
        rows.append(row)
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buffer)
    with tarfile.open(tmp_path / "fixture.tar", "w") as archive:
        member = tarfile.TarInfo(f"{number}.parquet")
        member.size = len(buffer.getvalue())
        archive.addfile(member, io.BytesIO(buffer.getvalue()))
    monkeypatch.setattr(fan_data, "AUDIT", tmp_path)
    selected = {group: {"archive": "fixture.tar", "member": f"{number}.parquet", "split": "train"}}
    result = list(fan_data.windows(selected, config, Counter()))
    assert len(result) == 4
    assert {r["group_id"] for r in result} == {group}
    assert result[3]["values"][0][0] == 1300
    assert result[3]["start"].isoformat() == "2021-01-01T00:15:00+00:00"
    assert result[3]["cutoff"].isoformat() == "2021-01-01T07:00:00+00:00"
    assert all(r["channels"] == ["rotor_0_speed", "rotor_1_speed"] for r in result)


def test_fan_windows_reject_missing_intervals_and_cross_split_windows():
    import numpy as np
    from driftops.fan_data import CONFIG, module_windows
    from driftops.windows import read_yaml

    config = read_yaml(CONFIG)
    group = next(f"m100:node-{i}" for i in range(20, 200) if partition(f"m100:node-{i}", config) == "train")
    start = int(datetime(2021, 12, 31, 21, tzinfo=timezone.utc).timestamp() * 1e6)
    times = start + np.arange(28) * config["cadence_us"]
    values = np.ones((28, 2)) * 4000
    assert list(module_windows(group, 0, times, values, config, Counter())) == []
    start = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp() * 1e6)
    times = start + np.arange(28) * config["cadence_us"]
    times[14:] += config["cadence_us"]
    assert list(module_windows(group, 0, times, values, config, Counter())) == []
