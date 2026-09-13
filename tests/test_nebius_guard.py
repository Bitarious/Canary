from datetime import datetime, timezone
import importlib.util
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("nebius_guard", Path("scripts/nebius_job_guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_absolute_deadline_survives_restart():
    config = {"deadline_utc": "2026-09-13T00:00:00+00:00"}
    assert not guard.should_stop(config, datetime(2026,9,12,23,59,tzinfo=timezone.utc))
    assert guard.should_stop(config, datetime(2026,9,13,tzinfo=timezone.utc))
    assert guard.should_stop(config, datetime(2026,9,14,tzinfo=timezone.utc))


def test_only_owned_instance_can_be_stopped_with_bounded_api_call():
    config = {"instance_id": "computeinstance-abc123"}
    calls = []
    def run(args, **kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(returncode=0)
    guard.stop_vm(config, "computeinstance-abc123", run)
    assert calls[0][0][-3:] == ["computeinstance-abc123", "--format", "json"]
    assert calls[0][1]["timeout"] == 70
    for other in ("computeinstance-other", "computeinstance-abc123;command"):
        with pytest.raises(ValueError):
            guard.stop_vm(config, other, run)
    assert len(calls) == 1
    with pytest.raises(RuntimeError, match="stop command failed"):
        guard.stop_vm(config, "computeinstance-abc123", lambda *a, **k: SimpleNamespace(returncode=1))


def test_new_image_metadata_uses_bounded_identity_only_http_request(tmp_path):
    calls = []
    def open_metadata(request, timeout):
        calls.append((request, timeout))
        return BytesIO(b"computeinstance-new123\n")
    assert guard.get_instance_id(tmp_path / "absent-legacy-file", open_metadata) == "computeinstance-new123"
    assert calls[0][0].full_url == "http://metadata.nebius.internal/v1/instance-data/id"
    assert calls[0][0].get_header("Metadata") == "true"
    assert calls[0][1] == 5
    with pytest.raises(ValueError, match="metadata instance identifier"):
        guard.get_instance_id(tmp_path / "absent", lambda *a, **k: BytesIO(b"not-an-instance"))


def test_existing_image_keeps_legacy_identity_without_http(tmp_path):
    path = tmp_path / "instance-id"
    path.write_text("computeinstance-old123\n")
    def unexpected_request(*args, **kwargs):
        pytest.fail("The existing metadata file must not require an HTTP request")
    assert guard.get_instance_id(path, unexpected_request) == "computeinstance-old123"
