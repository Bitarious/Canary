"""
Generate the CoT QA dataset, following the OpenTSLM annotation method (arXiv:2510.02410 §4):
give an annotator LLM the evidence plus the TRUE label, and ask for a step-by-step rationale
that never reveals the label until a final "Answer: <label>" line.

Two deliberate departures from the paper, both to fit a hackathon budget:

  1. EVIDENCE IS A NUMERIC FACT SHEET, NOT A PLOT IMAGE.
     The paper rendered matplotlib plots and used GPT-4o vision. At ~5k samples that is
     hours of rendering plus vision-rate-limited calls. A fact sheet is faster, cheaper,
     fully deterministic, and *strictly more grounded* -- the annotator cannot
     misread a pixel. Use --vision to render+send plots for a subset if you want the
     comparison for the write-up.

  2. THE ANNOTATOR MAY ONLY CITE FACTS THE MODEL CAN SEE.
     Everything in the fact sheet is computed from the exact channels fed to the TSLM.
     No fleet percentiles, no spec-cohort statistics, no absolute time. This is what stops
     the model learning to hallucinate evidence it has no access to.

Usage:
    python -m scania_timenet.gen_cot --data-dir data --out out/cot_train.jsonl \
        --n-pos 2000 --n-neg 3000 --concurrency 8
"""

from __future__ import annotations

import argparse
import json
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from .connector import (
    CLASS_NAMES,
    SCANIATimeNetConnector,
    TimeNetSample,
    fact_sheet,
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM = """You are a reliability engineer annotating training data for a predictive-maintenance model.

You analyse anonymised telemetry from heavy trucks. The sensor variables have deliberately
had their names and units removed by the manufacturer, so you must NEVER guess what a channel
physically measures and NEVER name a physical part. Reason only about the SHAPE of the signals:
what is accelerating, what is decaying, how sharply, and how the distribution of operating
conditions is shifting.

You write in the voice of an engineer explaining evidence to a fleet maintenance planner."""

USER_TEMPLATE = """A truck has been monitored for {n_readouts} readouts spanning {span} operating time steps
(mean gap {mean_gap} time steps between readouts).

Channel naming: `rate_<id>` is the per-time-step rate of change of an accumulative counter.
`hist<id>_mean_bin` is where the mass of a binned operating-condition distribution sits, scaled
to 0-1. `hist<id>_upper_mass` is the fraction of that distribution in its top quartile -- i.e.
how much of the truck's recent work happened in the most extreme bin of that condition.

Evidence extracted from the monitored window:
{facts}

Vehicle configuration (anonymised categories): {specs}

GROUND TRUTH (for your reasoning only -- do NOT state it until the final line):
This truck is in fact "{label_name}".

Write a step-by-step analysis, 4 to 6 sentences, that:
  1. Notes which channels are changing most and in which direction, quoting the ratios or
     slopes given above.
  2. Interprets whether that pattern looks like stable operation or progressive degradation.
  3. Comments on whether the shift in the condition histograms supports or weakens that read.
  4. Builds toward the correct conclusion WITHOUT announcing it early. Never write phrases like
     "we know that" or "given that the truck fails". Reason forward from the evidence only.
  5. Ends with a recommendation to the maintenance planner in one clause.

Then output the final line exactly as:
Answer: {label_name}

Do not use markdown, headers, or bullet points. Plain prose only."""

QUESTION = (
    "Based on this truck's monitored telemetry history, how close is it to a failure of "
    "Component X? Choose one of: " + "; ".join(CLASS_NAMES) + "."
)


def build_user_prompt(s: TimeNetSample) -> str:
    fs = fact_sheet(s)
    lines = []
    for f in fs.get("most_changed_channels", []):
        r = f["recent_vs_early_ratio"]
        lines.append(
            f"- {f['channel']}: normalised slope {f['normalised_slope']:+.3f}, "
            f"recent/early ratio {'n/a' if r is None else f'{r:.2f}'}, "
            f"latest value {f['last_value']:.5f}"
        )
    for f in fs.get("most_stable_channels", []):
        lines.append(f"- {f['channel']} (stable): normalised slope {f['normalised_slope']:+.3f}")
    return USER_TEMPLATE.format(
        n_readouts=fs["n_readouts"],
        span=fs["span_time_steps"],
        mean_gap=fs["mean_gap"],
        facts="\n".join(lines),
        specs=", ".join(f"{k}={v}" for k, v in list(s.static.items())[:8]) or "unavailable",
        label_name=CLASS_NAMES[s.label],
    )


# ---------------------------------------------------------------------------
# Annotator backends
# ---------------------------------------------------------------------------


def make_client(backend: str):
    if backend == "anthropic":
        from anthropic import Anthropic

        c = Anthropic()

        def call(system: str, user: str, image_png: bytes | None = None) -> str:
            content: list = [{"type": "text", "text": user}]
            if image_png is not None:
                import base64

                content.insert(
                    0,
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.b64encode(image_png).decode(),
                        },
                    },
                )
            r = c.messages.create(
                model=os.environ.get("ANNOTATOR_MODEL", "claude-sonnet-5"),
                max_tokens=600,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
            return "".join(b.text for b in r.content if b.type == "text")

        return call

    if backend in ("openai", "nebius"):
        from openai import OpenAI

        if backend == "nebius":
            # Nebius Token Factory is OpenAI-compatible and is covered by the hackathon
            # voucher -- use it as the annotator so CoT generation costs you nothing.
            #   export NEBIUS_API_KEY=...
            #   export ANNOTATOR_MODEL=meta-llama/Llama-3.3-70B-Instruct
            c = OpenAI(
                base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.com/v1/"),
                api_key=os.environ["NEBIUS_API_KEY"],
            )
        else:
            c = OpenAI()

        def call(system: str, user: str, image_png: bytes | None = None) -> str:
            content: list = [{"type": "text", "text": user}]
            if image_png is not None:
                import base64

                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,"
                            + base64.b64encode(image_png).decode()
                        },
                    }
                )
            r = c.chat.completions.create(
                model=os.environ.get("ANNOTATOR_MODEL", "gpt-4o"),
                max_tokens=600,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
            )
            return r.choices[0].message.content

        return call

    raise SystemExit(f"unknown backend {backend}")


def render_plot(s: TimeNetSample, path: Path | None = None) -> bytes:
    """Matplotlib rendering. Used for --vision and, regardless, for demo figures."""
    import io

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    V, ts = s.values, s.timestamps
    n = V.shape[0]
    fig, axes = plt.subplots(n, 1, figsize=(9, 0.55 * n), sharex=True)
    for i, ax in enumerate(np.atleast_1d(axes)):
        ax.plot(ts, V[i], lw=1.1)
        ax.set_ylabel(s.channel_names[i], rotation=0, ha="right", fontsize=6)
        ax.tick_params(labelsize=6)
        ax.margins(x=0)
    axes[-1].set_xlabel("operating time_step")
    fig.suptitle(f"vehicle {s.vehicle_id} — monitored window", fontsize=9)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=90)
    if path is not None:
        fig.savefig(path, dpi=110)
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------------------


def validate(text: str, label: int) -> tuple[bool, str]:
    """Reject annotations that leak the answer early or miss the required format."""
    if "Answer:" not in text:
        return False, "no Answer line"
    body, _, ans = text.rpartition("Answer:")
    if CLASS_NAMES[label].lower() not in ans.strip().lower():
        return False, "wrong/garbled answer line"
    lowered = body.lower()
    for leak in ("ground truth", "we know that", "given that the truck", "the true label"):
        if leak in lowered:
            return False, f"leaked: {leak}"
    if len(body.split()) < 40:
        return False, "too short"
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default="out/cot_train.jsonl")
    ap.add_argument("--split", default="train")
    ap.add_argument("--backend", default="nebius", choices=["anthropic", "openai", "nebius"])
    ap.add_argument("--n-pos", type=int, default=2000, help="samples from classes 1-4")
    ap.add_argument("--n-neg", type=int, default=3000, help="samples from class 0")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--vision", action="store_true", help="also send a rendered plot")
    ap.add_argument("--window", type=int, default=32)
    ap.add_argument("--stride", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", type=int, default=0, help="print N prompts and exit, no API calls")
    a = ap.parse_args()

    random.seed(a.seed)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # resume support -- hackathon runs get interrupted
    done: set[str] = set()
    if out.exists():
        with out.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["sample_id"])
                except Exception:
                    pass
        print(f"resuming, {len(done)} already generated")

    conn = SCANIATimeNetConnector(a.data_dir, window=a.window, stride=a.stride)

    if a.dry_run:
        for k, s in enumerate(conn.iter_samples(a.split)):
            if k >= a.dry_run:
                break
            print("=" * 78)
            print(f"sample {s.sample_id}  label={s.label} ({CLASS_NAMES[s.label]})")
            print("=" * 78)
            print("SYSTEM:\n" + SYSTEM + "\n")
            print("USER:\n" + build_user_prompt(s))
        return

    pos, neg = [], []
    for s in conn.iter_samples(a.split):
        if s.sample_id in done:
            continue
        (neg if s.label == 0 else pos).append(s)
    random.shuffle(pos)
    random.shuffle(neg)
    chosen = pos[: a.n_pos] + neg[: a.n_neg]
    random.shuffle(chosen)
    print(f"pool: {len(pos)} near-failure windows, {len(neg)} healthy windows")
    print(f"annotating {len(chosen)} samples with backend={a.backend} vision={a.vision}")

    call = make_client(a.backend)
    lock = threading.Lock()
    stats = {"ok": 0, "rejected": 0, "error": 0}
    fh = out.open("a", encoding="utf-8")

    def work(s: TimeNetSample):
        img = render_plot(s) if a.vision else None
        text = call(SYSTEM, build_user_prompt(s), img)
        ok, why = validate(text, s.label)
        body, _, _ = text.rpartition("Answer:")
        return s, text, body.strip(), ok, why

    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = [ex.submit(work, s) for s in chosen]
        for i, f in enumerate(as_completed(futs), 1):
            try:
                s, text, rationale, ok, why = f.result()
            except Exception as e:  # noqa: BLE001
                stats["error"] += 1
                continue
            if not ok:
                stats["rejected"] += 1
                continue
            rec = {
                "sample_id": s.sample_id,
                "vehicle_id": s.vehicle_id,
                "label": s.label,
                "answer": CLASS_NAMES[s.label],
                "question": QUESTION,
                "rationale": rationale,
                "time_series": s.values.tolist(),
                "channel_names": s.channel_names,
                "timestamps": s.timestamps.tolist(),
                "static": s.static,
            }
            with lock:
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                stats["ok"] += 1
            if i % 100 == 0:
                print(f"{i}/{len(chosen)} {stats}", flush=True)

    fh.close()
    print("FINAL", stats)


if __name__ == "__main__":
    main()
