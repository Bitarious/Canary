"""TimeF windows with separate model inputs, targets, and audit metadata."""

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from timenet.reader import TimeFReader
from timenet.registry.version import DatasetVersion

from driftops.timenet_connector import model_input
from driftops.windows import read_yaml

PATTERNS = ("constant", "rising", "falling", "fluctuating without a clear net trend",
            "counter reset or decrease")
PREPROCESSING_VERSION = "window-zscore-f64-ddof1-v1"
PROMPT_VERSION = "smart-description-v1"


def prepare_input(inputs: dict) -> dict:
    """Normalize only the observed window. Keep targets out of this function."""
    series = np.asarray(inputs["time_series"], dtype=np.float64)
    if series.ndim != 2 or series.shape[1] != 28 or series.shape[0] < 2:
        raise ValueError("Expected at least two complete 28-day channels")
    if not np.isfinite(series).all():
        raise ValueError("Model input contains nonfinite values")
    channels = [text.split(";", 1)[0] for text in inputs["time_series_text"]]
    allowed = read_yaml("config/dataset.yaml")["language_channels"]
    if len(channels) != len(series) or len(set(channels)) != len(channels) or any(
        channel not in allowed for channel in channels
    ):
        raise ValueError("Model input channels do not match the allowed channels")
    centered = series - series.mean(axis=1, keepdims=True)
    std = series.std(axis=1, ddof=1, keepdims=True)
    normalized = centered / np.where(std > 1e-8, std, 1.0)
    return {
        "pre_prompt": "Describe each SMART signal over the entire observed 28-day window. "
                      "Use only these patterns: " + "; ".join(PATTERNS) + ".",
        "time_series_text": [f"{name}; daily observations:" for name in channels],
        "time_series": normalized.astype(np.float32).tolist(),
        "post_prompt": "Answer with one 'channel: pattern' entry per supplied channel, separated by semicolons. Answer:",
    }


def input_hash(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, allow_nan=False).encode()).hexdigest()


def load_examples(partition: str, limit: int) -> list[dict]:
    """Select one window per drive by hash, without inspecting its target."""
    if partition not in {"train", "validation", "test"} or limit < 1:
        raise ValueError("Select a supported partition and a positive sample count")
    config = read_yaml("config/dataset.yaml")
    version = Path(config["timef_root"]) / config["dataset_id"] / config["dataset_version"]
    dataset = TimeFReader(DatasetVersion.open_local(version)).read()
    records = {record.record_id: record for record in dataset.records}
    tasks = sorted(dataset.tasks, key=lambda task: hashlib.sha256(
        ("concept-v1:" + task.id).encode()).hexdigest())
    selected = []
    seen = set()
    for task in tasks:
        record = records[task.record_ids[0]]
        if record.record_id in seen or not any(
            ann.key == "partition" and ann.value == partition for ann in record.annotations
        ):
            continue
        raw = model_input(record, task)
        inputs = prepare_input(raw)
        start = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            microseconds=record.start_time + task.scope.start_us)
        selected.append({"inputs": inputs, "target": task.target,
                         "audit": {"task_id": task.id, "drive_id": record.record_id,
                                   "partition": partition, "input_hash": input_hash(inputs),
                                   "start": start.date().isoformat(),
                                   "cutoff": (start + timedelta(days=27)).date().isoformat()}})
        seen.add(record.record_id)
        if len(selected) == limit:
            break
    if len(selected) != limit:
        raise ValueError(f"Only {len(selected)} distinct eligible drives in {partition}")
    return selected


def support(examples: list[dict]) -> dict:
    counts = Counter()
    for example in examples:
        for item in example["target"].rstrip(".").split("; "):
            counts[item.split(": ", 1)[1]] += 1
    return {"windows": len(examples), "drives": len({x["audit"]["drive_id"] for x in examples}),
            "patterns": dict(counts), "cutoff_min": min(x["audit"]["cutoff"] for x in examples),
            "cutoff_max": max(x["audit"]["cutoff"] for x in examples)}
