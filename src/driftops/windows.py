"""Causal windows, device/time partitions, and separate outcome labels."""

from datetime import date, timedelta
import hashlib
from pathlib import Path

import yaml


def read_yaml(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def partition_for(serial: str, config: dict) -> tuple[str, dict]:
    bucket = int(hashlib.sha256(f"driftops-split-v1:{serial}".encode()).hexdigest()[:8], 16) % 100
    matches = [(name, rule) for name, rule in config["partitions"].items()
               if rule["group_range"][0] <= bucket < rule["group_range"][1]]
    if len(matches) != 1:
        raise ValueError("Split configuration must assign every drive to exactly one partition")
    return matches[0]


def cutoff_dates(rule: dict, stride_days: int = 7):
    if stride_days < 1:
        raise ValueError("Task stride must be positive")
    cutoff = date.fromisoformat(rule["first_cutoff"])
    last = date.fromisoformat(rule["last_cutoff"])
    while cutoff <= last:
        yield cutoff
        cutoff += timedelta(days=stride_days)


def observed_window(rows: list[dict], cutoff: date, lookback_days: int = 28) -> list[dict]:
    if lookback_days < 1:
        raise ValueError("Lookback must be positive")
    start = cutoff - timedelta(days=lookback_days - 1)
    past = [row for row in rows if row["date"] <= cutoff]
    if any(row["failure"] == 1 for row in past):
        return []
    selected = [row for row in past if row["date"] >= start]
    selected.sort(key=lambda row: row["date"])
    expected = [start + timedelta(days=i) for i in range(lookback_days)]
    if [row["date"] for row in selected] != expected:
        return []
    return selected


def seven_day_label(rows: list[dict], cutoff: date, horizon_days: int = 7) -> int | None:
    """Only the evaluator/target builder should call this future-reading function.

    An observed event within the horizon is positive. Negatives require every
    follow-up day. A gap/disappearance without an event is unknown.
    """
    if any(row["failure"] == 1 and row["date"] <= cutoff for row in rows):
        return None
    future = [row for row in rows if cutoff < row["date"] <= cutoff + timedelta(days=horizon_days)]
    if any(row["failure"] == 1 for row in future):
        return 1
    expected = {cutoff + timedelta(days=i) for i in range(1, horizon_days + 1)}
    return 0 if {row["date"] for row in future} == expected else None
