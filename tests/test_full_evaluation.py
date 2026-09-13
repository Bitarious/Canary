from datetime import date
from copy import deepcopy
import json

import pytest

pytest.importorskip("torch")

from driftops.evaluate_full import SUCCESS_CRITERIA, comparison, counterfactual_evidence, freeze, paired_interval, perturb, success_checks
from driftops.full_archive import file_hash
from driftops.full_training import example
from driftops.train_full import train


def test_test_release_requires_a_completed_epoch(tmp_path):
    (tmp_path / "selection.json").write_text(json.dumps({"epoch": 0, "sha256": "unused"}))
    (tmp_path / "training-result.json").write_text(json.dumps({"full_data_training_complete": False}))
    with pytest.raises(ValueError, match="complete training epoch"):
        freeze(tmp_path / "unopened-dataset", tmp_path)
    assert not (tmp_path / "evaluation").exists()


def test_training_refuses_a_run_after_test_release(tmp_path):
    (tmp_path / "test-release.json").write_text("{}")
    with pytest.raises(ValueError, match="Test data was released"):
        train(tmp_path / "unopened-dataset", tmp_path)


def test_counterfactual_targets_change_without_changing_text_statistics():
    item = example({"task_id": "fixture", "drive_id": "fixture", "start": date(2025,10,1), "cutoff": date(2025,10,28),
                    "channels": ["smart_5_raw", "smart_194_raw"], "values": [list(range(28)), list(range(28))],
                    "target": "smart_5_raw: rising; smart_194_raw: rising."})
    reversed_item = perturb([item], "reversed")[0]
    assert reversed_item["inputs"]["time_series_text"] == item["inputs"]["time_series_text"]
    assert reversed_item["target"] == "smart_5_raw: counter reset or decrease; smart_194_raw: falling."
    zero = perturb([item], "zero_numerical_embeddings")[0]
    assert zero["inputs"]["time_series_text"] == item["inputs"]["time_series_text"]
    assert zero["target"] == item["target"]
    assert zero["inputs"]["time_series"] == [[0.] * 28] * 2


def test_counterfactual_check_rejects_unchanged_answers_and_measures_correct_response():
    item = example({"task_id": "fixture", "drive_id": "fixture", "start": date(2025, 10, 1), "cutoff": date(2025, 10, 28),
                    "channels": ["smart_5_raw", "smart_194_raw"], "values": [list(range(28)), list(range(28))],
                    "target": "smart_5_raw: rising; smart_194_raw: rising."})
    originals = [deepcopy(item) for _ in range(32)]
    for index, original in enumerate(originals):
        original["audit"]["drive_id"] = f"fixture-{index}"
    changed = perturb(originals, "reversed")
    repeated = [item["target"]] * 32
    unchanged = counterfactual_evidence(originals, changed, repeated, repeated)
    assert unchanged["changed_target_drives"] == 32
    assert unchanged["accuracy_gain_over_unchanged_output_ci95"] == [0., 0.]
    correct = counterfactual_evidence(originals, changed, repeated, [x["target"] for x in changed])
    assert correct["accuracy_gain_over_unchanged_output_ci95"] == [1., 1.]
    empty = counterfactual_evidence(originals, originals, repeated, repeated)
    assert empty["changed_target_drives"] == 0
    assert empty["accuracy_gain_over_unchanged_output_ci95"] is None


def test_success_requires_numerical_benefit_and_counterfactual_support():
    comparisons = {
        "finetuned": {"valid_output_rate": 1., "macro_f1_supported_classes": .8},
        "starting": {"macro_f1_supported_classes": .1},
        "constant": {"macro_f1_supported_classes": .2},
        "reversed": {"counterfactual_evidence": {"changed_target_drives": 32, "accuracy_gain_over_unchanged_output_ci95": [.1, .2]}},
        "shuffled": {"counterfactual_evidence": {"changed_target_drives": 32, "accuracy_gain_over_unchanged_output_ci95": [.1, .2]}},
    }
    intervals = {name: [.1, .2] for name in ("starting", "constant", "zero_numerical_embeddings")}
    assert success_checks(comparisons, intervals, 16)["passed"]
    intervals["zero_numerical_embeddings"] = [0., 0.]
    result = success_checks(comparisons, intervals, 16)
    assert not result["passed"]
    assert not result["checks"]["numerical_input_benefit"]
    intervals["zero_numerical_embeddings"] = [.1, .2]
    comparisons["reversed"]["counterfactual_evidence"]["changed_target_drives"] = 31
    assert not success_checks(comparisons, intervals, 16)["passed"]
    assert not success_checks(comparisons, intervals, 0)["checks"]["checkpoint_reload"]


def test_paired_interval_rejects_unpaired_scores():
    with pytest.raises(ValueError, match="equal lengths"):
        paired_interval([1.], [])
    assert paired_interval([], []) is None


def test_separate_comparison_keeps_frozen_inputs_and_rejects_changed_protocol(tmp_path, monkeypatch):
    import driftops.evaluate_full as evaluation

    item = example({"task_id": "fixture", "drive_id": "fixture", "start": date(2025, 10, 1), "cutoff": date(2025, 10, 28),
                    "channels": ["smart_5_raw", "smart_194_raw"], "values": [list(range(28)), list(range(28))],
                    "target": "smart_5_raw: rising; smart_194_raw: rising."})
    output = tmp_path / "evaluation"
    output.mkdir()
    (tmp_path / "best.pt").write_bytes(b"test fixture, not model weights")
    (output / "test.json").write_text(json.dumps([item]))
    (output / "protocol.json").write_text(json.dumps({"success_criteria": SUCCESS_CRITERIA, "time_limit_seconds": 30}))
    release = {"checkpoint_sha256": file_hash(tmp_path / "best.pt"), "test_sha256": file_hash(output / "test.json"),
               "protocol_sha256": file_hash(output / "protocol.json")}
    (tmp_path / "test-release.json").write_text(json.dumps(release))
    calls = []
    monkeypatch.setattr(evaluation, "load_model", lambda *a, **k: object())
    def fake_generation(model, batch, **kwargs):
        calls.extend(batch)
        return [x["target"] for x in batch]
    monkeypatch.setattr(evaluation, "generate", fake_generation)
    comparison(tmp_path, "reversed", "cpu")
    cached = json.loads((output / "reversed" / "batch-000000.json").read_text())
    assert cached["outputs"] == ["smart_5_raw: counter reset or decrease; smart_194_raw: falling."]
    assert calls[0]["inputs"]["time_series_text"] == item["inputs"]["time_series_text"]
    assert file_hash(output / "test.json") == release["test_sha256"]
    comparison(tmp_path, "reversed", "cpu")
    assert len(calls) == 1
    (output / "protocol.json").write_text("{}")
    with pytest.raises(ValueError, match="frozen evaluation artifact changed"):
        comparison(tmp_path, "finetuned", "cpu")
    assert not (output / "finetuned").exists()
