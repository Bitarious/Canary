"""Validate an explicit repository-local configuration for a new training run."""

import math
from pathlib import Path

from driftops.windows import read_yaml


def read_training_config(path=Path('config/train_full.yaml')):
    path = Path(path)
    if path.resolve().parent != (Path.cwd() / 'config').resolve() or path.suffix != '.yaml':
        raise ValueError('Training configuration must be a YAML file in the repository config directory')
    config = read_yaml(path)
    for key in ('world_size', 'batch_size', 'epochs', 'validation_drives', 'test_drives',
                'checkpoint_every_steps', 'validation_every_steps'):
        value = config.get(key)
        if type(value) is not int or value <= 0:
            raise ValueError(f'Training setting {key} must be a positive integer')
    for key in ('max_train_hours', 'max_vm_hours', 'gpu_memory_gb', 'budget_usd',
                'encoder_lr', 'projector_lr', 'lora_lr', 'clip_grad_norm'):
        value = config.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'Training setting {key} must be finite and positive')
    for key in ('vm_hourly_usd', 'disk_hourly_usd', 'weight_decay'):
        value = config.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f'Training setting {key} must be finite and nonnegative')
    if config['max_train_hours'] > config['max_vm_hours']:
        raise ValueError('Training time cannot exceed the reserved machine time')
    quoted = config['max_vm_hours'] * (config['vm_hourly_usd'] + config['disk_hourly_usd'])
    if quoted > config['budget_usd']:
        raise ValueError('The maximum quoted machine cost exceeds the run budget')
    if not isinstance(config.get('gpu_name'), str) or not config['gpu_name'].strip():
        raise ValueError('Training configuration must identify the GPU')
    return config


def read_compute_ledger(path, now):
    import json
    from datetime import datetime

    ledger = json.loads(Path(path).read_text())
    stamp = datetime.fromisoformat(ledger['as_of'])
    remaining = ledger.get('remaining_under_ceiling_usd')
    if stamp.tzinfo is None:
        raise ValueError('The compute ledger timestamp must include a time zone')
    if type(remaining) not in (int, float) or not math.isfinite(remaining) or remaining < 0:
        raise ValueError('The compute ledger balance must be finite and nonnegative')
    age = (now - stamp).total_seconds()
    if not 0 <= age <= 300 or remaining < 50.45:
        raise ValueError('Refresh the shared compute ledger and reserve the bounded component phase before training.')
    return ledger
