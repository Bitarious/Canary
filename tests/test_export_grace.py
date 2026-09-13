from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("export_grace", Path(__file__).resolve().parents[1] / "scripts/stop_after_component_exports.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_export_grace_respects_both_absolute_deadline_and_duration_cap():
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    config = {"instance_id": module.INSTANCE, "deadline_utc": (now + timedelta(hours=2)).isoformat()}
    assert module.wait_seconds(config, now) == 900
    config["deadline_utc"] = (now + timedelta(seconds=100)).isoformat()
    assert module.wait_seconds(config, now) == 25
    assert module.wait_seconds(config, now + timedelta(seconds=101)) == 0
    config["instance_id"] = "another-instance"
    with pytest.raises(ValueError, match="guarded instance"):
        module.wait_seconds(config, now)


def test_export_wait_returns_on_receipt_or_expires_without_receipt(tmp_path):
    receipt = tmp_path / "receipt.json"
    now = [0.]
    def sleep(seconds):
        now[0] += seconds
    assert module.await_exports([receipt], 9, monotonic=lambda: now[0], sleep=sleep) is False
    assert now[0] == 9
    def publish(seconds):
        now[0] += seconds
        receipt.write_text("{}")
    assert module.await_exports([receipt], 100, monotonic=lambda: now[0], sleep=publish) is True
    assert now[0] == 14


def test_malformed_grace_state_still_calls_provider_stop(monkeypatch):
    calls = []
    monkeypatch.setattr(module.Path, "read_text", lambda _: "invalid")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(ValueError):
        module.main()
    assert calls[0][0][0] == ["/usr/bin/python3", "/opt/driftops/nebius_job_guard.py", "--stop-now"]
    assert calls[0][1]["timeout"] == 75
