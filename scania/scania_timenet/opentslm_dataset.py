"""
OpenTSLM dataset adapter for the generated SCANIA CoT corpus.

Drop this file into the OpenTSLM repo under `src/opentslm/time_series_datasets/scania/`
and register it in `curriculum_learning.py` as a new stage (see RUNBOOK.md §Train).

IMPORTANT: OpenTSLM's base-class method names have moved between commits. Verify against
whatever `QADataset` looks like in the commit you cloned; the three things every subclass
must supply are (a) the split rows, (b) the text prompt around the series, and (c) the
gold completion. Those are isolated below so you only have to rename methods, not rewrite
logic.

A single sample is emitted as a LIST of univariate series (one entry per channel), which is
the shape OpenTSLM-Flamingo expects -- each series becomes its own <TS> chunk, and the
Perceiver Resampler compresses each to a fixed latent count. This is exactly why Flamingo
was the right pick here: 20 channels cost ~constant VRAM, whereas SoftPrompt would blow up.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

CLASS_NAMES = [
    "more than 48 time steps before failure",
    "48 to 24 time steps before failure",
    "24 to 12 time steps before failure",
    "12 to 6 time steps before failure",
    "6 to 0 time steps before failure",
]

PRE_PROMPT = (
    "You are a reliability engineer monitoring a fleet of heavy trucks. The following "
    "anonymised telemetry channels were recorded from one truck over its recent operating "
    "history. The manufacturer has removed all sensor names and units, so reason only about "
    "the shape of the signals -- what is accelerating, what is decaying, and how the "
    "distribution of operating conditions is shifting. Never name a physical component.\n\n"
    "Channels, in order:\n"
)

POST_PROMPT = (
    "\nQuestion: Based on this truck's monitored telemetry history, how close is it to a "
    "failure of Component X? Choose exactly one of: " + "; ".join(CLASS_NAMES) + ".\n"
    "Think step by step about the evidence, then finish with a line of the form "
    "'Answer: <choice>'.\n"
)


def zscore(x: np.ndarray) -> np.ndarray:
    m, s = float(x.mean()), float(x.std())
    return (x - m) / (s if s > 1e-8 else 1.0)


class ScaniaCoTQADataset(Dataset):
    """(signal, question, reasoning, answer) quadruples ready for LM-loss fine-tuning."""

    def __init__(
        self,
        jsonl_path: str | Path,
        split: str = "train",
        EOS_TOKEN: str = "",
        max_channels: int | None = None,
        val_fraction: float = 0.1,
        seed: int = 0,
    ):
        self.eos = EOS_TOKEN
        self.max_channels = max_channels
        rows = [json.loads(l) for l in Path(jsonl_path).open(encoding="utf-8")]

        # Split by VEHICLE, never by row -- windows from one truck must not straddle splits.
        vids = sorted({r["vehicle_id"] for r in rows})
        rng = np.random.default_rng(seed)
        rng.shuffle(vids)
        n_val = max(1, int(len(vids) * val_fraction))
        val_ids = set(vids[:n_val])
        if split == "train":
            rows = [r for r in rows if r["vehicle_id"] not in val_ids]
        elif split in ("val", "validation"):
            rows = [r for r in rows if r["vehicle_id"] in val_ids]
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    # -- the three things the OpenTSLM base class needs -----------------------

    def _get_pre_prompt(self, row: dict) -> str:
        names = row["channel_names"][: self.max_channels] if self.max_channels else row["channel_names"]
        spec = ", ".join(f"{k}={v}" for k, v in row.get("static", {}).items())
        listing = "".join(f"  {i+1}. {n}\n" for i, n in enumerate(names))
        return (
            PRE_PROMPT
            + listing
            + f"\nVehicle configuration (anonymised categories): {spec or 'unavailable'}\n"
            + f"Readouts in window: {len(row['timestamps'])}\n"
        )

    def _get_post_prompt(self, row: dict) -> str:
        return POST_PROMPT

    def _get_answer(self, row: dict) -> str:
        return f"{row['rationale'].strip()}\nAnswer: {row['answer']}{self.eos}"

    # -- series ---------------------------------------------------------------

    def _get_time_series(self, row: dict) -> list[torch.Tensor]:
        ts = np.asarray(row["time_series"], dtype=np.float32)  # (C, T)
        if self.max_channels:
            ts = ts[: self.max_channels]
        return [torch.from_numpy(zscore(c)) for c in ts]

    def __getitem__(self, i: int) -> dict:
        r = self.rows[i]
        return {
            "time_series": self._get_time_series(r),
            "time_series_text": [
                {"time_series_text": n} for n in (r["channel_names"][: self.max_channels] if self.max_channels else r["channel_names"])
            ],
            "pre_prompt": self._get_pre_prompt(r),
            "post_prompt": self._get_post_prompt(r),
            "answer": self._get_answer(r),
            "label": r["label"],
            "vehicle_id": r["vehicle_id"],
            "sample_id": r["sample_id"],
        }


class ScaniaEvalDataset(ScaniaCoTQADataset):
    """Held-out validation/test vehicles from the OFFICIAL split, with no rationale.

    Built straight from the connector so there is zero dependency on annotation having
    finished. Answers are the official class_label.
    """

    def __init__(self, data_dir: str, split: str = "validation", EOS_TOKEN: str = "", window: int = 32, max_channels: int | None = None):
        from .connector import SCANIATimeNetConnector

        self.eos = EOS_TOKEN
        self.max_channels = max_channels
        conn = SCANIATimeNetConnector(data_dir, window=window)
        self.rows = [
            {
                "sample_id": s.sample_id,
                "vehicle_id": s.vehicle_id,
                "label": s.label,
                "answer": CLASS_NAMES[s.label],
                "rationale": "",
                "time_series": s.values.tolist(),
                "channel_names": s.channel_names,
                "timestamps": s.timestamps.tolist(),
                "static": s.static,
            }
            for s in conn.iter_samples(split)
        ]

    def _get_answer(self, row: dict) -> str:
        return f"Answer: {row['answer']}{self.eos}"


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default="out/cot_train.jsonl")
    a = ap.parse_args()
    ds = ScaniaCoTQADataset(a.jsonl, split="train")
    print(f"{len(ds)} train samples")
    s = ds[0]
    print(s["pre_prompt"][:400])
    print("...")
    print(s["post_prompt"])
    print("GOLD:", s["answer"][:400])
    print("channels:", len(s["time_series"]), "len:", s["time_series"][0].shape)
