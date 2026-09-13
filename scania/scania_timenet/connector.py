"""
SCANIATimeNetConnector — maps the SCANIA Component X dataset into TimeNet-schema samples.

Design decisions (all deliberate, see RUNBOOK.md §Decisions):
  * 105 raw columns -> 20 derived channels. Counters are ACCUMULATIVE (raw they encode
    odometer, not health) so we differentiate and divide by the time_step gap. Histograms
    are cumulative counts per bin, so we differentiate then renormalise to a distribution
    and summarise each histogram by (mean bin index, upper-quartile mass).
  * Labels follow the OFFICIAL validation/test class definition so results are directly
    comparable to the IDA-2024 leaderboard:
        0: >48   1: 48-24   2: 24-12   3: 12-6   4: 6-0   time_steps before failure
  * Right-censoring is handled correctly: a vehicle with in_study_repair==0 tells us
    nothing about what happens after its last readout, so we only emit class-0 windows
    where (L - t) > 48. Nearer windows are DROPPED, not labelled healthy.
  * Fleet-relative statistics are deliberately NOT model inputs. Everything the CoT
    annotator is allowed to cite must be recoverable from the series the model sees.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Dataset constants (verified against the published files, arXiv:2401.15199)
# ---------------------------------------------------------------------------

HISTOGRAMS: dict[str, int] = {
    "167": 10,
    "272": 10,
    "291": 11,
    "158": 10,
    "459": 20,
    "397": 36,
}
COUNTERS: list[str] = [
    "171_0", "666_0", "427_0", "837_0", "309_0", "835_0", "370_0", "100_0",
]

# Official class boundaries, in time_steps before failure. Upper bound is exclusive.
CLASS_EDGES: list[tuple[float, float]] = [
    (48.0, np.inf),  # 0
    (24.0, 48.0),    # 1
    (12.0, 24.0),    # 2
    (6.0, 12.0),     # 3
    (0.0, 6.0),      # 4
]
CLASS_NAMES: list[str] = [
    "more than 48 time steps before failure",
    "48 to 24 time steps before failure",
    "24 to 12 time steps before failure",
    "12 to 6 time steps before failure",
    "6 to 0 time steps before failure",
]

# Scania's expert cost matrix. COST[actual][predicted].
COST = np.array(
    [
        [0, 7, 8, 9, 10],
        [200, 0, 7, 8, 9],
        [300, 200, 0, 7, 8],
        [400, 300, 200, 0, 7],
        [500, 400, 300, 200, 0],
    ],
    dtype=np.float64,
)

SPEC_COLS = [f"Spec_{i}" for i in range(8)]

SPLIT_FILES = {
    "train": ("train_operational_readouts.csv", "train_specifications.csv", "train_tte.csv"),
    "validation": ("validation_operational_readouts.csv", "validation_specifications.csv", "validation_labels.csv"),
    "test": ("test_operational_readouts.csv", "test_specifications.csv", "test_labels.csv"),
}


def hist_cols(var: str) -> list[str]:
    return [f"{var}_{i}" for i in range(HISTOGRAMS[var])]


def channel_names() -> list[str]:
    names = [f"rate_{c}" for c in COUNTERS]
    for var in HISTOGRAMS:
        names.append(f"hist{var}_mean_bin")
        names.append(f"hist{var}_upper_mass")
    return names


N_CHANNELS = len(channel_names())  # 8 + 12 = 20


def ttf_to_class(ttf: float) -> int:
    """time-to-failure (in time_steps) -> official class 0..4."""
    if ttf > 48.0:
        return 0
    if ttf > 24.0:
        return 1
    if ttf > 12.0:
        return 2
    if ttf > 6.0:
        return 3
    return 4


# ---------------------------------------------------------------------------


@dataclass
class TimeNetSample:
    """One TimeNet-schema sample: channels + annotations + tasks."""

    sample_id: str
    vehicle_id: int
    split: str
    timestamps: np.ndarray            # (T,) irregular, unit = operating time_step
    values: np.ndarray                # (C, T) float32
    channel_names: list[str]
    static: dict[str, str]            # Spec_0..Spec_7
    label: int | None                 # 0..4
    horizon_ttf: float | None         # true time-to-failure at window end (train only)
    tasks: list[dict] = field(default_factory=list)

    def to_timenet(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "source": "scania_component_x",
            "subject_id": str(self.vehicle_id),
            "channels": [
                {
                    "name": name,
                    "values": self.values[i].tolist(),
                    "sampling": {
                        "kind": "irregular",
                        "unit": "operating_time_step",
                        "timestamps": self.timestamps.tolist(),
                    },
                }
                for i, name in enumerate(self.channel_names)
            ],
            "annotations": (
                [
                    {"type": "static", "name": k, "value": v}
                    for k, v in self.static.items()
                ]
                + [{"type": "static", "name": "n_readouts", "value": int(len(self.timestamps))}]
            ),
            "tasks": self.tasks
            or [
                {
                    "type": "classification",
                    "name": "failure_window",
                    "label": self.label,
                    "label_names": CLASS_NAMES,
                }
            ],
        }


class SCANIATimeNetConnector:
    def __init__(
        self,
        data_dir: str | Path,
        window: int = 32,
        stride: int = 4,
        min_readouts: int = 6,
        censor_margin: float = 48.0,
    ):
        self.data_dir = Path(data_dir)
        self.window = window
        self.stride = stride
        self.min_readouts = min_readouts
        self.censor_margin = censor_margin

    # -- loading -----------------------------------------------------------

    def _read_readouts(self, fname: str) -> pd.DataFrame:
        usecols = ["vehicle_id", "time_step"] + COUNTERS
        for var in HISTOGRAMS:
            usecols += hist_cols(var)
        dtypes = {c: np.float32 for c in usecols if c != "vehicle_id"}
        dtypes["vehicle_id"] = np.int32
        df = pd.read_csv(self.data_dir / fname, usecols=usecols, dtype=dtypes)
        df = df.sort_values(["vehicle_id", "time_step"], kind="mergesort").reset_index(drop=True)
        # <1% missingness; forward-fill within vehicle then zero-fill the head.
        df[usecols[2:]] = df.groupby("vehicle_id")[usecols[2:]].ffill()
        df = df.fillna(0.0)
        return df

    # -- channel derivation ------------------------------------------------

    def derive_channels(self, df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
        """Returns (index frame with vehicle_id/time_step, channel matrix (N, C))."""
        g = df.groupby("vehicle_id", sort=False)
        dt = g["time_step"].diff().to_numpy(dtype=np.float32)
        # first readout of each vehicle: no rate defined -> use the elapsed time itself
        first = np.isnan(dt)
        dt = np.where(first | (dt <= 0), np.nan, dt)

        chans: list[np.ndarray] = []

        # 1. counter rates
        for c in COUNTERS:
            d = g[c].diff().to_numpy(dtype=np.float32)
            # ECU software updates can reset counters -> negative diffs. Treat as missing.
            d = np.where(d < 0, np.nan, d)
            chans.append(np.nan_to_num(d / dt, nan=0.0, posinf=0.0, neginf=0.0))

        # 2. histogram shape summaries, computed on the DELTA distribution
        for var, nbins in HISTOGRAMS.items():
            cols = hist_cols(var)
            deltas = np.column_stack(
                [np.where((v := g[c].diff().to_numpy(dtype=np.float32)) < 0, np.nan, v) for c in cols]
            )
            deltas = np.nan_to_num(deltas, nan=0.0)
            total = deltas.sum(axis=1, keepdims=True)
            p = np.divide(deltas, total, out=np.zeros_like(deltas), where=total > 0)
            idx = np.arange(nbins, dtype=np.float32)
            mean_bin = (p * idx).sum(axis=1) / max(nbins - 1, 1)     # scaled to [0,1]
            upper = p[:, int(np.ceil(nbins * 0.75)):].sum(axis=1)    # upper-quartile mass
            chans.append(mean_bin.astype(np.float32))
            chans.append(upper.astype(np.float32))

        X = np.column_stack(chans).astype(np.float32)
        X[first] = 0.0  # first readout of a vehicle carries no rate information
        return df[["vehicle_id", "time_step"]], X

    # -- label construction ------------------------------------------------

    def _train_labels(self) -> pd.DataFrame:
        tte = pd.read_csv(self.data_dir / "train_tte.csv")
        return tte.set_index("vehicle_id")

    # -- sample emission ---------------------------------------------------

    def iter_samples(self, split: str, max_vehicles: int | None = None) -> Iterator[TimeNetSample]:
        ro_f, spec_f, lab_f = SPLIT_FILES[split]
        df = self._read_readouts(ro_f)
        specs = pd.read_csv(self.data_dir / spec_f).set_index("vehicle_id")
        idx, X = self.derive_channels(df)

        if split == "train":
            labels = self._train_labels()
        else:
            labels = pd.read_csv(self.data_dir / lab_f).set_index("vehicle_id")

        vids = idx["vehicle_id"].to_numpy()
        bounds = np.flatnonzero(np.r_[True, vids[1:] != vids[:-1], True])
        names = channel_names()

        seen = 0
        for a, b in zip(bounds[:-1], bounds[1:]):
            vid = int(vids[a])
            if max_vehicles is not None and seen >= max_vehicles:
                return
            n = b - a
            # min_readouts gates TRAIN window construction only. Every val/test vehicle must
            # receive a prediction or the official split is no longer comparable -- a skipped
            # vehicle is silently a class-0 prediction, which is the expensive error.
            if split == "train" and n < self.min_readouts:
                continue
            ts_all = idx["time_step"].to_numpy()[a:b]
            X_all = X[a:b]
            static = {c: str(specs.at[vid, c]) for c in SPEC_COLS} if vid in specs.index else {}

            if split == "train":
                if vid not in labels.index:
                    continue
                L = float(labels.at[vid, "length_of_study_time_step"])
                repaired = int(labels.at[vid, "in_study_repair"]) == 1
                ends = range(self.min_readouts - 1, n, self.stride)
                if repaired and (n - 1) not in ends:
                    ends = list(ends) + [n - 1]  # always keep the terminal window
                for e in ends:
                    ttf = L - float(ts_all[e])
                    if ttf < 0:
                        continue
                    if repaired:
                        y = ttf_to_class(ttf)
                    else:
                        if ttf <= self.censor_margin:
                            continue  # right-censored: outcome genuinely unknown
                        y = 0
                    s = max(0, e + 1 - self.window)
                    yield TimeNetSample(
                        sample_id=f"{split}-{vid}-{e}",
                        vehicle_id=vid,
                        split=split,
                        timestamps=ts_all[s : e + 1],
                        values=X_all[s : e + 1].T.copy(),
                        channel_names=names,
                        static=static,
                        label=y,
                        horizon_ttf=ttf,
                    )
                seen += 1
            else:
                # val/test: histories are already truncated at the evaluation point.
                if vid not in labels.index:
                    continue
                e = n - 1
                s = max(0, e + 1 - self.window)
                yield TimeNetSample(
                    sample_id=f"{split}-{vid}",
                    vehicle_id=vid,
                    split=split,
                    timestamps=ts_all[s : e + 1],
                    values=X_all[s : e + 1].T.copy(),
                    channel_names=names,
                    static=static,
                    label=int(labels.at[vid, "class_label"]),
                    horizon_ttf=None,
                )
                seen += 1


# ---------------------------------------------------------------------------
# Fact sheet: the ONLY thing the CoT annotator is allowed to see.
# Every statement here is recoverable from the channels the model receives.
# ---------------------------------------------------------------------------


def fact_sheet(s: TimeNetSample, top_k: int = 5) -> dict:
    V, ts = s.values, s.timestamps
    T = V.shape[1]
    if T < 4:
        return {"n_readouts": T, "note": "very short history"}
    head = slice(0, max(2, T // 2))
    tail = slice(max(2, T // 2), T)

    facts = []
    for i, name in enumerate(s.channel_names):
        a, b = float(np.mean(V[i, head])), float(np.mean(V[i, tail]))
        if abs(a) < 1e-9:
            ratio = None
        else:
            ratio = b / a
        # linear trend over the window, normalised by the channel's own scale
        scale = float(np.std(V[i]) + 1e-9)
        slope = float(np.polyfit(np.arange(T), V[i], 1)[0]) / scale
        facts.append(
            {
                "channel": name,
                "recent_vs_early_ratio": None if ratio is None else round(ratio, 3),
                "normalised_slope": round(slope, 3),
                "last_value": round(float(V[i, -1]), 5),
            }
        )
    facts.sort(key=lambda f: -abs(f["normalised_slope"]))
    return {
        "n_readouts": T,
        "span_time_steps": round(float(ts[-1] - ts[0]), 1),
        "mean_gap": round(float(np.mean(np.diff(ts))) if T > 1 else 0.0, 2),
        "specs": s.static,
        "most_changed_channels": facts[:top_k],
        "most_stable_channels": facts[-2:],
    }


def total_cost(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    return float(COST[y_true, y_pred].sum())


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--split", default="validation")
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()

    conn = SCANIATimeNetConnector(a.data_dir)
    for k, s in enumerate(conn.iter_samples(a.split, max_vehicles=a.n)):
        print(json.dumps({"sample": s.sample_id, "label": s.label, "facts": fact_sheet(s)}, indent=2)[:2000])
        if k + 1 >= a.n:
            break
