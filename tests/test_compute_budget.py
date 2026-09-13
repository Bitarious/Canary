from datetime import datetime, timedelta, timezone
import json

import pytest

from driftops.compute_budget import instance_cost
import driftops.compute_budget as budget_module


START = datetime(2026, 9, 12, tzinfo=timezone.utc)


def event(name, minute, finish=None, code=0):
    result = {"description": name, "created_at": (START + timedelta(minutes=minute)).isoformat(), "status": {"code": code}}
    if finish is not None:
        result["finished_at"] = (START + timedelta(minutes=finish)).isoformat()
    return result


def test_aborted_stop_and_overlapping_start_do_not_end_or_double_count():
    events = [event("Start Instance", 0, 1), event("Stop Instance", 20, 21, 10),
              event("Start Instance", 21, 22), event("Stop Instance", 40, 45)]
    result = instance_cost(events, START + timedelta(hours=1), 4., 1., START)
    assert result["compute_seconds_upper"] == 2700
    assert result["total_usd_upper"] == 4.
    assert not result["open_compute_interval"]


def test_failed_scheduling_and_active_compute_are_conservatively_counted():
    events = [event("Start Instance", 0, 5, 8), event("Start Instance", 10)]
    result = instance_cost(events, START + timedelta(minutes=30), 12., 0., START)
    assert result["compute_seconds_upper"] == 1500
    assert result["total_usd_upper"] == 5.
    assert result["open_compute_interval"]


def test_successful_deletion_ends_compute_and_storage():
    events = [event("Start Instance", 0, 1), event("Delete Instance", 25, 30)]
    result = instance_cost(events, START + timedelta(hours=1), 2., 2., START)
    assert result["total_usd_upper"] == 2.


def test_incomplete_stop_does_not_mark_compute_stopped():
    events = [event("Start Instance", 0, 1), event("Stop Instance", 20)]
    result = instance_cost(events, START + timedelta(minutes=30), 2., 0., START)
    assert result["compute_seconds_upper"] == 1800
    assert result["open_compute_interval"]


def test_future_operation_is_rejected():
    with pytest.raises(ValueError, match="future"):
        instance_cost([event("Start Instance", 1)], START, 1., 1., START)


def test_report_includes_fallback_and_its_regional_disk_rate(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return START + timedelta(hours=1)

    monkeypatch.setattr(budget_module, "datetime", Clock)
    for index, name in enumerate(("", "parallel", "rtx6000")):
        directory = tmp_path / name
        directory.mkdir(exist_ok=True)
        instance = f"computeinstance-fixture{index}"
        events = [event("Start Instance", 20)] if name == "rtx6000" else [event("Start Instance", 0, 1), event("Stop Instance", 9, 10)]
        for operation in events:
            operation["resource_id"] = instance
        (directory / "operations.json").write_text(json.dumps({"operations": events}))
        (directory / "resources.json").write_text(json.dumps({"instance_id": instance}))
        config = {"created_at": START.isoformat(), "updated_at": START.isoformat(), "disk_hourly_usd": (index + 1) / 10}
        path = tmp_path / "eight-gpu-budget.json" if name == "parallel" else directory / "vm-budget.json"
        path.write_text(json.dumps(config))
    result = budget_module.report(tmp_path)
    assert len(result["instances"]) == 3
    assert result["estimated_spend_upper_usd"] == pytest.approx(16.95)
    assert result["instances"][2]["total_usd_upper"] == pytest.approx(9.9)
    assert result["instances"][2]["open_compute_interval"]
    (tmp_path / "rtx6000" / "resources.json").write_text(json.dumps({"instance_id": "different-vm"}))
    with pytest.raises(ValueError, match="different VM"):
        budget_module.report(tmp_path)
