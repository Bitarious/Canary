import importlib.util
import json
from pathlib import Path
import sys

import pytest


spec = importlib.util.spec_from_file_location("component_phase", Path(__file__).parents[1] / "scripts/run_component_phase.py")
phase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase)


def fixture_job(tmp_path, name="fan-run", gpu=0):
    run = tmp_path / "artifacts/tslm" / name
    run.mkdir(parents=True)
    root = tmp_path / (name + "-data")
    root.mkdir()
    for filename, value in {
        "overview.json": {}, "config.json": {"world_size": 1, "max_train_hours": 2},
        "hdd-gate.json": {"success_gate": {"passed": True}, "reload_predictions_equal": 16},
        "dataset-manifest.json": {}, "source-hashes.json": {},
    }.items():
        (run / filename).write_text(json.dumps(value))
    return {"name": name, "gpu": gpu, "run": str(run), "data_root": str(root)}


def test_component_phase_requires_separate_gpus_and_passing_hdd(tmp_path):
    jobs = [fixture_job(tmp_path), fixture_job(tmp_path, "ssd-run", 1)]
    assert phase.validate({"jobs": jobs}, tmp_path) == jobs
    jobs[1]["gpu"] = 0
    with pytest.raises(ValueError, match="separate"):
        phase.validate({"jobs": jobs}, tmp_path)
    jobs[1]["gpu"] = 1
    (Path(jobs[0]["run"]) / "hdd-gate.json").write_text(json.dumps({"success_gate": {"passed": False}, "reload_predictions_equal": 16}))
    with pytest.raises(ValueError, match="passing HDD"):
        phase.validate({"jobs": jobs}, tmp_path)


def test_component_phase_rejects_changed_source_and_started_run(tmp_path):
    job = fixture_job(tmp_path)
    run = Path(job["run"])
    source = tmp_path / "source.py"
    source.write_text("changed")
    (run / "source-hashes.json").write_text(json.dumps({"source.py": "0" * 64}))
    with pytest.raises(ValueError, match="checksum"):
        phase.validate({"jobs": [job]}, tmp_path)
    (run / "source-hashes.json").write_text("{}")
    (run / "hardware.json").write_text("{}")
    with pytest.raises(ValueError, match="already started"):
        phase.validate({"jobs": [job]}, tmp_path)


def test_gpu_sharing_requires_explicit_industrial_studies(tmp_path):
    jobs = [fixture_job(tmp_path, "gearbox-study", 7), fixture_job(tmp_path, "bearing-study", 7)]
    with pytest.raises(ValueError, match="restricted"):
        phase.validate({"jobs": jobs, "shared_gpu": 7}, tmp_path)
    for job in jobs:
        p = Path(job["run"]) / "config.json"
        value = json.loads(p.read_text())
        value["evaluation_kind"] = "small-industrial-v1"
        p.write_text(json.dumps(value))
    assert phase.validate({"jobs": jobs, "shared_gpu": 7}, tmp_path) == jobs
    jobs[1]["gpu"] = 6
    with pytest.raises(ValueError, match="unused eighth"):
        phase.validate({"jobs": jobs, "shared_gpu": 7}, tmp_path)


def test_component_phase_runs_independent_stages_and_preserves_failed_job(tmp_path):
    jobs = [fixture_job(tmp_path), fixture_job(tmp_path, "ssd-run", 1)]

    def commands(job, stage):
        if job["name"] == "ssd-run":
            return [sys.executable, "-c", "raise SystemExit(3)"]
        script = "from pathlib import Path; import json; p=Path(" + repr(job["run"]) + "); "
        if stage == "training":
            script += "(p/'training-result.json').write_text(json.dumps({'full_data_training_complete':True})); (p/'selection.json').write_text('{}'); (p/'test-release.json').write_text('{}')"
        else:
            script += "(p/'evaluation').mkdir(); (p/'evaluation/metrics.json').write_text(json.dumps({'success_gate':{'passed':True},'reload_predictions_equal':16}))"
        return [sys.executable, "-c", script]

    states = phase.supervise(jobs, tmp_path, commands, interval=.01, phase_seconds=10)
    assert states["fan-run"] == {"stage": "complete", "gate_passed": True, "reload_predictions_equal": 16}
    assert states["ssd-run"] == {"stage": "failed", "reason": "training_exit", "exit_code": 3}
    assert (Path(jobs[0]["run"]) / "training-ready.json").is_file()
    assert json.loads((tmp_path / "result.json").read_text())["jobs"] == states


def test_component_phase_test_release_timeout(tmp_path):
    job = fixture_job(tmp_path)
    run = Path(job["run"])
    (run / "training-result.json").write_text(json.dumps({"full_data_training_complete": True}))
    (run / "selection.json").write_text("{}")
    states = phase.supervise([job], tmp_path, lambda *_: [sys.executable, "-c", "pass"],
                             interval=.01, phase_seconds=10, release_seconds=.03)
    assert states["fan-run"] == {"stage": "failed", "reason": "test_release_timeout"}


def test_component_export_rejects_corrupt_checkpoint_before_test_release(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    export_spec = importlib.util.spec_from_file_location("component_export", Path(__file__).parents[1] / "scripts/export_component_phase.py")
    exporter = importlib.util.module_from_spec(export_spec)
    export_spec.loader.exec_module(exporter)
    job = fixture_job(tmp_path)
    job["run"] = "/opt/driftops/components-v1/artifacts/tslm/fan-run"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"jobs": [job]}))
    (tmp_path / "budget.json").write_text(json.dumps({"deadline_utc": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}))
    (tmp_path / "artifacts/tslm/fan-run/best.pt").write_bytes(b"wrong checkpoint")
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    monkeypatch.setattr(exporter, "inspect", lambda *_: {"fan-run": {"training-ready.json": {"selection": {"sha256": "0" * 64}}, "component-terminal.json": None}})
    monkeypatch.setattr(exporter, "transfer", lambda *_: None)
    monkeypatch.setattr(exporter, "freeze", lambda *_: pytest.fail("Corrupt weights must not release the test."))
    with pytest.raises(ValueError, match="differs from its selection"):
        exporter.main(manifest)
