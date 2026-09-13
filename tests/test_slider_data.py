from copy import deepcopy
import io
import wave

import numpy as np
import pytest

from driftops.component_data import build
from driftops.evaluate_industrial import CRITERIA, audio_criteria
from driftops.slider_data import decode, features, recording_windows, validate_config
from driftops.windows import read_yaml


def test_audio_bands_preserve_energy_and_frame_causality():
    t = np.arange(160000) / 16000
    values = (.5 * np.sin(2 * np.pi * 500 * t) * 32767).astype('<i2')
    pcm = values.tobytes()
    result = features(pcm)
    assert result.shape == (312, 2)
    assert np.allclose(result[:, 0], .5 / np.sqrt(2), atol=1e-4)
    assert result[:, 1].max() < 1e-4
    values[512 * 28:] = 0
    assert np.array_equal(features(values.tobytes())[:28], result[:28])
    config = read_yaml('config/slider_benchmark.yaml')
    rows = list(recording_windows(pcm, 'clip:a', 'dcase-slider:00', config))
    assert len(rows) == 11
    assert rows[0]['times_us'] == ((np.arange(28) + 1) * 32000).tolist()
    assert rows[-1]['cutoff'].timestamp() == pytest.approx(9.856)
    assert rows[0]['group_id'] == 'dcase-slider:00'


def test_audio_format_and_split_exception_are_explicit():
    config = read_yaml('config/slider_benchmark.yaml')
    validate_config(config)
    bad = deepcopy(config)
    bad['group_partitions']['dcase-slider:02'] = 'train'
    with pytest.raises(ValueError, match='declared devices'):
        validate_config(bad)
    bad = deepcopy(config)
    bad['chronology_verified'] = True
    with pytest.raises(ValueError, match='relative clock'):
        validate_config(bad)
    out = io.BytesIO()
    with wave.open(out, 'wb') as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(bytes(640000))
    with pytest.raises(ValueError, match='mono PCM'):
        decode(out.getvalue())
    assert {k:v for k,v in audio_criteria().items() if k not in ('scope', 'windows_per_group')} == {
        k:v for k,v in CRITERIA.items() if k not in ('scope', 'windows_per_group')}


@pytest.mark.parametrize('config_path', ['config/slider_benchmark.yaml', 'config/valve_audio_benchmark.yaml'])
def test_audio_native_roundtrip_retains_relative_clock_and_disjoint_machines(tmp_path, config_path):
    config = read_yaml(config_path)
    pcm = (np.arange(160000) % 1000).astype('<i2').tobytes()
    rows = [next(recording_windows(pcm, 'clip:' + group, group, config)) for group in config['group_partitions']]
    result = build(tmp_path / 'audio', rows, config, {'fixture': True})
    assert result['groups']['calibration'] == []
    assert len(result['groups']['test']) == 5
    assert result['audit']['windows_train'] == 1
    assert result['config']['clock_semantics'] == 'clip-relative-offset-only'


def test_valve_sound_study_rejects_component_mix_and_preserves_quality_thresholds():
    config = read_yaml('config/valve_audio_benchmark.yaml')
    validate_config(config)
    bad = deepcopy(config)
    bad['component'] = 'slide_rail'
    with pytest.raises(ValueError, match='component must match'):
        validate_config(bad)
    bad = deepcopy(config)
    bad['group_partitions']['dcase-valve:02'] = 'train'
    with pytest.raises(ValueError, match='declared devices'):
        validate_config(bad)
    assert {k:v for k,v in audio_criteria('valve').items() if k != 'scope'} == {
        k:v for k,v in audio_criteria().items() if k != 'scope'}
    with pytest.raises(ValueError, match='unsupported'):
        audio_criteria('pump')
