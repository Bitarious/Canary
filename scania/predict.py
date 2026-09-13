"""
Run a fine-tuned OpenTSLM-Flamingo checkpoint over the official validation/test split and
write predictions in the jsonl format evaluate.py expects.

Run on Nebius (same box as training). Copy out/preds_*.jsonl back to your laptop for eval.

  python predict.py --ckpt ckpt/best --data-dir data --split test --out out/tslm_test.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from scania_timenet.opentslm_dataset import CLASS_NAMES, ScaniaEvalDataset


def parse_answer(text: str) -> int:
    tail = text.rpartition("Answer:")[2].strip().lower()
    for i, c in enumerate(CLASS_NAMES):
        if c.lower() in tail:
            return i
    # fall back on the distinguishing numerals, e.g. "6 to 0"
    for i, c in enumerate(CLASS_NAMES):
        key = c.split(" time")[0].lower()
        if key in tail:
            return i
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--split", default="validation")
    ap.add_argument("--out", default="out/tslm_val.jsonl")
    ap.add_argument("--window", type=int, default=32)
    ap.add_argument("--max-new-tokens", type=int, default=300)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    from opentslm import OpenTSLM  # noqa: F401  (import path may differ; see repo)

    model = OpenTSLM.load_pretrained(a.ckpt, device="cuda")
    model.eval()

    ds = ScaniaEvalDataset(a.data_dir, split=a.split, window=a.window)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    fh = Path(a.out).open("w", encoding="utf-8")

    n = len(ds) if a.limit is None else min(a.limit, len(ds))
    for i in range(n):
        s = ds[i]
        with torch.no_grad():
            text = model.generate(
                time_series=s["time_series"],
                pre_prompt=s["pre_prompt"],
                post_prompt=s["post_prompt"],
                max_new_tokens=a.max_new_tokens,
            )
        if isinstance(text, (list, tuple)):
            text = text[0]
        fh.write(
            json.dumps(
                {
                    "sample_id": s["sample_id"],
                    "vehicle_id": s["vehicle_id"],
                    "label": s["label"],
                    "pred": parse_answer(text),
                    "text": text,
                }
            )
            + "\n"
        )
        fh.flush()
        if (i + 1) % 50 == 0:
            print(f"{i+1}/{n}", flush=True)
    fh.close()
    print("wrote", a.out)


if __name__ == "__main__":
    main()
