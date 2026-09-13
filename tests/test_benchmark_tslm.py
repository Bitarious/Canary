import json
from pathlib import Path

import pytest

from driftops.benchmark_tslm import build, parse

CASES = Path("results/2026-09-13/hdd-demo-cases.json")


@pytest.mark.parametrize("case", json.loads(CASES.read_text(encoding="utf-8"))["cases"], ids=lambda c: c["case_id"])
def test_hdd_inputs_match_the_released_inference_inputs(case):
    channels = [c["name"] for c in case["window"]["channels"]]
    values = [c["values"] for c in case["window"]["channels"]]
    inputs, reference = build("hdd", channels, values)
    from driftops.tslm_dataset import input_hash
    assert input_hash(inputs) == case["inference"]["input_sha256"]
    assert inputs == case["model_inputs"]
    # The rule reference is returned separately and never enters the prompt.
    assert reference == case["evaluation_reference"]["weak_rule_target"]
    assert reference not in json.dumps(inputs)


def test_parse_keeps_only_supplied_channels_and_known_patterns():
    answer = "power: rising; core_temperature: sort of warm; constant: fluctuating without a clear net trend."
    assert parse(answer, ["power", "core_temperature"]) == {"power": "rising"}


def test_build_rejects_incomplete_windows():
    with pytest.raises(ValueError):
        build("hdd", ["smart_5_raw", "smart_197_raw"], [[0.0] * 27, [0.0] * 27])
