import json
import os
from pathlib import Path
import runpy
import subprocess

import pytest


def test_first_pass_controller_waits_for_full_coverage_and_signals_only_once(tmp_path, monkeypatch):
    module = runpy.run_path(str(Path(__file__).parents[1] / "scripts/finish_hdd_first_pass.py"))
    root = tmp_path / "run"
    group = tmp_path / "group"
    proc = tmp_path / "proc"
    root.mkdir()
    group.mkdir()
    (root / "selection.json").write_text(json.dumps({"epoch": 1, "validation_loss": .001, "examples_seen": 11315069}))
    (root / "progress.json").write_text(json.dumps({"completed_epochs": 0}))
    (group / "cgroup.procs").write_text("\n".join(str(i) for i in range(100, 108)))
    for pid in range(100, 108):
        directory = proc / str(pid)
        directory.mkdir(parents=True)
        (directory / "cmdline").write_bytes(b"python\0-u\0src/driftops/train_full.py\0train\0--run\0artifacts/tslm/full-history-rtx6000-v2\0")
    script = module["INSPECT"].replace("/opt/driftops/work-v2/artifacts/tslm/full-history-rtx6000-v2", str(root))
    script = script.replace("Path('/sys/fs/cgroup')/cgroup.lstrip('/')", "Path(" + repr(str(group)) + ")")
    script = script.replace("Path('/proc')", "Path(" + repr(str(proc)) + ")")
    calls = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append(pid))
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "/system.slice/driftops-full-history-rtx6000-v2.service\n")
    exec(compile(script, "controller-fixture", "exec"), {})
    assert calls == []
    (root / "progress.json").write_text(json.dumps({"completed_epochs": 1}))
    exec(compile(script, "controller-fixture", "exec"), {})
    assert calls == [100]
    assert json.loads((root / "first-pass-stop-request.json").read_text())["worker_pid"] == 100
    exec(compile(script, "controller-fixture", "exec"), {})
    assert calls == [100]


def test_first_pass_controller_rejects_partial_coverage(tmp_path, monkeypatch):
    module = runpy.run_path(str(Path(__file__).parents[1] / "scripts/finish_hdd_first_pass.py"))
    (tmp_path / "selection.json").write_text(json.dumps({"epoch": 1, "validation_loss": .001, "examples_seen": 100}))
    (tmp_path / "progress.json").write_text(json.dumps({"completed_epochs": 1}))
    script = module["INSPECT"].replace("/opt/driftops/work-v2/artifacts/tslm/full-history-rtx6000-v2", str(tmp_path))
    monkeypatch.setattr(os, "kill", lambda *a: pytest.fail("An incomplete pass must not trigger a worker signal."))
    with pytest.raises(ValueError, match="required full pass"):
        exec(compile(script, "controller-fixture", "exec"), {})
