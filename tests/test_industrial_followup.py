from copy import deepcopy

import pytest

from driftops.evaluate_industrial import CRITERIA
from driftops.industrial_followup import followup_criteria, require_support_failure, verify_selection


def test_followup_keeps_quality_thresholds_and_requires_support_only_failure():
    changed = {k for k,v in followup_criteria().items() if v != CRITERIA[k]}
    assert changed == {"windows_per_group"}
    checks = dict.fromkeys(["valid_outputs", "checkpoint_reload", "starting", "constant", "zero_numerical_embeddings"], True)
    checks.update(reversed_target_response=False, shuffled_target_response=False)
    support = {"groups": 5, "accuracy_gain_ci95": [.1,.3],
               "one_sided_exact_group_sign_probability": 1/32, "support_sufficient": False}
    report = {"success_gate": {"passed": False, "checks": checks},
              "comparisons": {mode: {"counterfactual_evidence": deepcopy(support)} for mode in ("reversed", "shuffled")}}
    require_support_failure(report)
    for damage in ("numerical", "nonpositive", "sufficient", "missing"):
        bad = deepcopy(report)
        if damage == "numerical":
            bad["success_gate"]["checks"]["zero_numerical_embeddings"] = False
        elif damage == "nonpositive":
            bad["comparisons"]["reversed"]["counterfactual_evidence"]["accuracy_gain_ci95"][0] = -.01
        elif damage == "sufficient":
            bad["comparisons"]["reversed"]["counterfactual_evidence"]["support_sufficient"] = True
        else:
            bad["success_gate"]["checks"].pop("constant")
        with pytest.raises(ValueError):
            require_support_failure(bad)


def test_followup_excludes_opened_windows_and_requires_every_remaining_window():
    examples = [{"audit": {"task_id": f"new-{g}", "group_id": str(g)}} for g in range(5)]
    verify_selection(examples, ["old"], 6)
    with pytest.raises(ValueError, match="reuses"):
        verify_selection(examples, ["new-0"], 6)
    with pytest.raises(ValueError, match="every unused"):
        verify_selection(examples, ["old"], 7)
    with pytest.raises(ValueError, match="more than once"):
        verify_selection(examples + [examples[0]], ["old"], 7)
    with pytest.raises(ValueError, match="five"):
        verify_selection(examples[:4], ["old"], 5)
