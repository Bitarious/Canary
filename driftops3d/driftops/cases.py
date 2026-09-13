"""Fail-closed loader for the three released HDD demonstration cases.

The HTTP layer always reads the single repository-owned bundle below.  There is
no request parameter for a path and this module never runs model inference.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_PATH = REPO_ROOT / "results" / "2026-09-13" / "hdd-demo-cases.json"
EXPECTED_BUNDLE_SHA256 = "94b613c19a207b8bfcad3e9437a4fc6cedf6311592934e7fc7c5fbaf2dfde407"
CASE_IDS = ("hdd-rising", "hdd-stable", "hdd-model_mismatch")
CHANNELS = ("smart_5_raw", "smart_187_raw", "smart_194_raw", "smart_197_raw")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

MODEL = {
    "name": "Gemma 3 270M OpenTSLM-SP",
    "total_parameters": 271_029_888,
    "trainable_parameters": 2_931_072,
    "trainable_scope": "temporal encoder, projector and attention LoRA",
}
EVALUATION = {
    "channel_agreement_percent": 99.68,
    "channel_labels": 6_777,
    "unseen_drives": 2_048,
    "zero_input_percent": 86.01,
    "constant_baseline_percent": 69.43,
}
LIMITATION = "Failure probability and maintenance timing have not been validated."


class CaseBundleError(ValueError):
    """The released case bundle failed an integrity or contract check."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CaseBundleError(message)


def _normalise_raw(values: list[float]) -> list[float]:
    if len(set(values)) == 1:
        return [0.0] * len(values)
    mean = statistics.fmean(values)
    scale = statistics.stdev(values)
    return [(value - mean) / scale for value in values]


def _validate_case(case: dict) -> None:
    _require(isinstance(case, dict), "case must be an object")
    case_id = case.get("case_id")
    _require(case_id in CASE_IDS, f"unexpected case id: {case_id!r}")

    source = case.get("source") or {}
    _require(source.get("dataset") == "Backblaze Drive Stats" and source.get("split") == "released_test",
             f"{case_id}: source or split changed")
    _require(isinstance(source.get("drive_id"), str) and source["drive_id"], f"{case_id}: missing drive id")
    _require(bool(SHA256_RE.fullmatch(str(source.get("dataset_manifest_sha256") or ""))),
             f"{case_id}: invalid source manifest hash")
    window = case.get("window") or {}
    dates = window.get("dates")
    _require(isinstance(dates, list) and len(dates) == 28, f"{case_id}: expected 28 dates")
    try:
        parsed_dates = [date.fromisoformat(value) for value in dates]
    except (TypeError, ValueError) as exc:
        raise CaseBundleError(f"{case_id}: invalid window date") from exc
    _require(
        parsed_dates == [parsed_dates[0] + timedelta(days=i) for i in range(28)],
        f"{case_id}: dates are not a continuous daily window",
    )
    _require(window.get("start") == dates[0] and window.get("as_of") == dates[-1],
             f"{case_id}: start/as-of does not match the daily window")

    channels = window.get("channels")
    _require(isinstance(channels, list), f"{case_id}: channels must be a list")
    _require(all(isinstance(channel, dict) for channel in channels), f"{case_id}: invalid channel")
    _require(tuple(channel.get("name") for channel in channels) == CHANNELS,
             f"{case_id}: channel order or names changed")

    model_inputs = case.get("model_inputs") or {}
    series = model_inputs.get("time_series")
    descriptions = model_inputs.get("time_series_text")
    _require(isinstance(series, list) and len(series) == len(CHANNELS),
             f"{case_id}: expected four model-input channels")
    _require(isinstance(descriptions, list) and len(descriptions) == len(CHANNELS),
             f"{case_id}: expected four channel descriptions")

    for index, (channel, supplied, description) in enumerate(zip(channels, series, descriptions)):
        raw = channel.get("values")
        _require(channel.get("unit") == "raw_source_units", f"{case_id}: channel unit changed")
        _require(isinstance(raw, list) and len(raw) == 28, f"{case_id}: raw channel {index} is not 28 days")
        _require(isinstance(supplied, list) and len(supplied) == 28,
                 f"{case_id}: model-input channel {index} is not 28 days")
        _require(all(isinstance(value, (int, float)) and math.isfinite(value) for value in raw + supplied),
                 f"{case_id}: channel {index} contains a non-finite value")
        _require(str(description).startswith(f"{CHANNELS[index]};"),
                 f"{case_id}: channel description order changed")
        expected = _normalise_raw(raw)
        _require(all(math.isclose(left, right, rel_tol=0, abs_tol=1e-5)
                     for left, right in zip(expected, supplied)),
                 f"{case_id}: raw and model-input values no longer match")

    inference = case.get("inference") or {}
    _require(inference.get("source") == "saved_model_inference", f"{case_id}: inference source changed")
    _require(inference.get("executed_during_this_review") is False,
             f"{case_id}: review execution flag changed")
    _require(all(inference.get(field) is None for field in ("failure_probability", "failure_window", "confidence")),
             f"{case_id}: unsupported prediction fields must remain null")
    _require(isinstance(inference.get("output_text"), str) and inference["output_text"],
             f"{case_id}: saved output is missing")
    for field in ("checkpoint_sha256", "input_sha256"):
        _require(bool(SHA256_RE.fullmatch(str(inference.get(field) or ""))),
                 f"{case_id}: invalid recorded {field}")
    recomputed_input = hashlib.sha256(
        json.dumps(model_inputs, sort_keys=True).encode("utf-8")
    ).hexdigest()
    _require(recomputed_input == inference["input_sha256"], f"{case_id}: recorded input hash does not match payload")

    reference = case.get("evaluation_reference") or {}
    _require(reference.get("never_send_to_model") is True, f"{case_id}: reference boundary changed")
    _require(isinstance(reference.get("weak_rule_target"), str) and reference["weak_rule_target"],
             f"{case_id}: weak rule reference is missing")
    _require(isinstance(reference.get("exact_match"), bool), f"{case_id}: exact-match flag is invalid")
    _require(reference["exact_match"] == (inference["output_text"] == reference["weak_rule_target"]),
             f"{case_id}: mismatch flag does not match saved texts")


def load_case_bundle(path: Path = BUNDLE_PATH, expected_sha256: str = EXPECTED_BUNDLE_SHA256) -> dict:
    """Read and validate a case bundle. The server calls this with fixed defaults."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CaseBundleError("released HDD case bundle is unavailable") from exc
    digest = hashlib.sha256(raw).hexdigest()
    _require(digest == expected_sha256, "released HDD case bundle failed SHA-256 verification")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaseBundleError("released HDD case bundle is not valid JSON") from exc
    cases = payload.get("cases") if isinstance(payload, dict) else None
    _require(isinstance(cases, list) and len(cases) == len(CASE_IDS), "expected exactly three released HDD cases")
    _require(tuple(payload.get("case_order") or ()) == CASE_IDS, "released HDD case order changed")
    _require(all(isinstance(case, dict) for case in cases), "invalid case entry")
    _require(tuple(case.get("case_id") for case in cases) == CASE_IDS, "released HDD cases do not match case order")
    for case in cases:
        try:
            _validate_case(case)
        except (AttributeError, TypeError, KeyError, OverflowError) as exc:
            raise CaseBundleError("released HDD case structure is invalid") from exc
    return {
        **payload,
        "integrity": {
            "status": "verified",
            "bundle_sha256": digest,
            "contract": "28 consecutive daily observations × 4 SMART channels",
        },
        "model": MODEL,
        "evaluation": EVALUATION,
        "limitation": LIMITATION,
    }


def case_list() -> dict:
    bundle = load_case_bundle()
    return {
        key: bundle[key]
        for key in ("selection", "case_order", "integrity", "model", "evaluation", "limitation")
    } | {
        "cases": [
            {
                "case_id": case["case_id"],
                "selection_reason": case["selection_reason"],
                "drive_id": case["source"]["drive_id"],
                "start": case["window"]["start"],
                "as_of": case["window"]["as_of"],
                "exact_match": case["evaluation_reference"]["exact_match"],
            }
            for case in bundle["cases"]
        ]
    }


def case_detail(case_id: str) -> dict:
    if case_id not in CASE_IDS:
        raise KeyError(case_id)
    bundle = load_case_bundle()
    case = next((item for item in bundle["cases"] if item["case_id"] == case_id), None)
    if case is None:
        raise KeyError(case_id)
    return {
        "case": case,
        "selection": bundle["selection"],
        "integrity": bundle["integrity"],
        "model": bundle["model"],
        "evaluation": bundle["evaluation"],
        "limitation": bundle["limitation"],
    }
