from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
import yaml

from driftops.training_config import read_training_config


def test_explicit_training_config_preserves_settings_and_rejects_invalid_limits(tmp_path, monkeypatch):
    config = read_training_config()
    (tmp_path / 'config').mkdir()
    path = tmp_path / 'config/custom.yaml'
    monkeypatch.chdir(tmp_path)
    path.write_text(yaml.safe_dump(config))
    assert read_training_config(path) == config
    for key, value in [('world_size', 0), ('batch_size', True), ('max_train_hours', float('inf')),
                       ('max_train_hours', 999), ('vm_hourly_usd', -1), ('budget_usd', 1)]:
        path.write_text(yaml.safe_dump({**config, key: value}))
        with pytest.raises(ValueError):
            read_training_config(path)
    with pytest.raises(ValueError, match='repository config'):
        read_training_config(tmp_path / 'external.yaml')


def test_component_custom_ledger_retains_freshness_and_existing_run_guards(tmp_path):
    from driftops.component_training import prepare
    report = tmp_path / 'hdd.json'
    report.write_text(json.dumps({'success_gate': {'passed': True}, 'reload_predictions_equal': 16}))
    ledger = tmp_path / 'budget.json'
    ledger.write_text(json.dumps({'as_of': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                                  'remaining_under_ceiling_usd': 100}))
    with pytest.raises(ValueError, match='Refresh the shared compute ledger'):
        prepare(tmp_path / 'data', tmp_path / 'new-run', report, ledger_path=ledger)
    run = tmp_path / 'existing-run'
    run.mkdir()
    with pytest.raises(ValueError, match='Existing run artifacts'):
        prepare(tmp_path / 'data', run, report, ledger_path=ledger)


def test_compute_ledger_accepts_current_funds_and_rejects_invalid_or_future_values(tmp_path):
    from driftops.training_config import read_compute_ledger
    now = datetime.now(timezone.utc)
    valid = {'as_of': now.isoformat(), 'remaining_under_ceiling_usd': 100}
    path = tmp_path / 'ledger.json'
    path.write_text(json.dumps(valid))
    assert read_compute_ledger(path, now) == valid
    for changed in ({'as_of': (now + timedelta(minutes=1)).isoformat()},
                    {'as_of': now.replace(tzinfo=None).isoformat()},
                    {'remaining_under_ceiling_usd': float('nan')},
                    {'remaining_under_ceiling_usd': -1},
                    {'remaining_under_ceiling_usd': True},
                    {'remaining_under_ceiling_usd': 50}):
        path.write_text(json.dumps({**valid, **changed}))
        with pytest.raises(ValueError):
            read_compute_ledger(path, now)


def test_hdd_preparation_freezes_the_selected_config_without_loading_a_model(tmp_path, monkeypatch):
    from driftops import train_full
    from driftops.full_archive import file_hash
    config = read_training_config()
    config.update(world_size=2, batch_size=16, validation_drives=2,
                  gpu_name='reproduction GPU', vm_hourly_usd=1.5)
    (tmp_path / 'config').mkdir()
    custom = tmp_path / 'config/reproduction.yaml'
    custom.write_text(yaml.safe_dump(config))
    for name in ('pyproject.toml', 'uv.lock'):
        (tmp_path / name).write_bytes(Path(name).read_bytes())
    root = tmp_path / 'data'
    root.mkdir()
    (root / 'dataset-manifest.json').write_text(json.dumps({'config': {}, 'audit': {'windows_train': 10}}))
    monkeypatch.setattr(train_full, 'window_files', lambda *_: [])
    monkeypatch.setattr(train_full, 'heldout', lambda *_: [{}, {}])
    monkeypatch.setattr(train_full, 'class_weights', lambda *_: {})
    monkeypatch.setattr(train_full, 'load_model', lambda *_: pytest.fail('Preparation must not load a model'))
    monkeypatch.chdir(tmp_path)
    run = tmp_path / 'run'
    train_full.prepare(root, run, custom)
    assert json.loads((run / 'config.json').read_text()) == config
    overview = json.loads((run / 'overview.json').read_text())
    assert overview['hardware_cost']['vm_rate_usd_hour'] == 1.5
    assert 'balance_user_reported_usd' not in overview['hardware_cost']
    hashes = json.loads((run / 'source-hashes.json').read_text())
    assert hashes['config/reproduction.yaml'] == file_hash(custom)
    with pytest.raises(ValueError, match='Existing run artifacts'):
        train_full.prepare(root, run, custom)
