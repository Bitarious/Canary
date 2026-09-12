"""Versioned weak supervision, derived only from the supplied observed window."""

import numpy as np

ANNOTATION_VERSION = "window-description-v1"
QUESTION = "Describe the direction and pattern of each supplied SMART signal over this observed window."
COUNTERS = {"smart_5_raw", "smart_9_raw", "smart_187_raw", "smart_188_raw", "smart_198_raw"}


def describe_channel(channel: str, values: list[int | float]) -> dict:
    if len(values) < 2:
        raise ValueError("At least two observations are required")
    series = np.asarray(values, dtype=np.float64)
    if not np.isfinite(series).all():
        raise ValueError("Description requires finite observed values")
    changes = np.diff(series)
    span = float(np.ptp(series))
    band = max(1.0, span * 0.1)
    segment = min(7, len(series) // 2)
    change = float(np.median(series[-segment:]) - np.median(series[:segment]))
    if channel in COUNTERS and np.any(changes < 0):
        label = "counter reset or decrease"
    elif span == 0:
        label = "constant"
    elif change >= band:
        label = "rising"
    elif change <= -band:
        label = "falling"
    else:
        label = "fluctuating without a clear net trend"
    # The entire input window is the declared interval; no fabricated change time.
    return {"channel": channel, "pattern": label, "first": float(series[0]),
            "last": float(series[-1]), "minimum": float(series.min()), "maximum": float(series.max())}


def describe_window(rows: list[dict], channels: list[str]) -> tuple[str, list[dict]]:
    findings = []
    for channel in channels:
        values = [row[channel] for row in rows]
        if any(value is None for value in values):
            continue
        findings.append(describe_channel(channel, values))
    if not findings:
        raise ValueError("No complete language channels in this window")
    answer = "; ".join(f"{item['channel']}: {item['pattern']}" for item in findings) + "."
    return answer, findings
