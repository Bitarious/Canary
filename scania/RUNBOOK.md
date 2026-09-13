# SCANIA × OpenTSLM — 12-hour runbook

## Hard constraints found in your environment

| | |
|---|---|
| Local GPU | GTX 1060 Mobile, 6GB, **Pascal — no bf16**, and your torch is `2.12.0+cpu` |
| Verdict | **Cannot train OpenTSLM-Flamingo locally.** Not a tuning problem, an architecture-generation problem. |
| Plan | Local = data prep, CoT generation, evaluation. **Nebius = training only.** |
| Annotator | No `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` set. Use Nebius Token Factory (OpenAI-compatible, covered by the voucher). |

Rent **one L40S or A100-40GB**. At ~$1.5–2.5/hr that is under $20 for the whole hackathon
against a $1000 voucher. Do not rent an 8-GPU node; you will spend an hour on distributed
setup you do not need for a 1B backbone with a frozen trunk.

---

## Decisions already made for you

**1. Task = the official 5-class problem.** Classes 0–4 (>48, 48–24, 24–12, 12–6, 6–0 time
steps before failure). This is what `validation_labels.csv` / `test_labels.csv` contain and what
Scania's cost matrix scores. **Binary "fails soon" is derived from the same predictions at eval
time**, which is how you compare to the MH-LSTM paper without a second training run.
(A macro-F1 ≈ 0.879 attributed to an IDA-2024 entry is floating around; treat it as UNVERIFIED
and probably a different framing — see the caveat under the measured results below.)

**2. 105 raw columns → 20 channels.** 8 counter *rates* + per-histogram (mean bin index, upper-quartile mass).
Counters are accumulative: fed raw they encode odometer, not health. This is the single most
important preprocessing step and the one most teams will get wrong.

**3. Right-censoring is handled properly.** A vehicle with `in_study_repair == 0` tells you
nothing about what happens after its last readout, so windows within 48 time steps of the study
end are **dropped**, not labelled healthy. Free rigour point for the jury; two lines of code.

**4. CoT evidence is a numeric fact sheet, not a plot image.** See `gen_cot.py` docstring.
Faster, cheaper, and strictly more grounded than vision. `--vision` exists for a subset if you
want the comparison in the write-up.

**5. The annotator may only cite facts the model can see.** No fleet percentiles, no cohort
statistics. Everything in the fact sheet is computed from the exact 20 channels fed to the TSLM.
This is what stops the model learning to hallucinate evidence it has no access to — and it is
the answer to the sharpest question the jury can ask about synthetic CoT.

---

## Timeline

### H0–H1 · Data + connector  ✅ *already done for you*
```bash
# all 9 CSVs are downloading/downloaded into ../data
python -m scania_timenet.connector --data-dir ../data --split validation --n 2   # smoke test (passes)
```

### H1–H2 · Start CoT generation, then walk away
It is API-bound, so launch it **first** and do everything else while it runs.
```bash
export NEBIUS_API_KEY=...
export ANNOTATOR_MODEL=meta-llama/Llama-3.3-70B-Instruct
python -m scania_timenet.gen_cot --data-dir ../data --out out/cot_train.jsonl \
    --backend nebius --n-pos 2000 --n-neg 3000 --concurrency 12
```
It appends and **resumes** — safe to kill and restart. Target ≥3,000 accepted samples; it
self-validates and rejects annotations that leak the label or miss the `Answer:` line.

Sanity-check 10 generated rationales by eye before letting it run to completion. If the prose
is generic ("the signals show some variation"), tighten `USER_TEMPLATE` once, early — not at H8.

### H2–H4 · Nebius box in parallel
```bash
git clone https://github.com/StanfordBDHG/OpenTSLM && cd OpenTSLM && pip install -e .
python curriculum_learning.py --help        # ← DO THIS AT H4, NOT H8
```
**The flag names in `train_flamingo.sh` are a best guess.** `curriculum_learning.py`'s argparse
has drifted between commits. Reconcile it while you still have slack. Then register
`ScaniaCoTQADataset` as a stage named `scania_cot`.

Prove the loop runs on 50 samples for 20 steps before you trust it with the real corpus.

### H4–H7 · Train
```bash
bash train_flamingo.sh      # Llama-3.2-1B backbone, bs4 × grad-accum 8, 3 epochs, lr 1e-4
```
3 epochs over ~4k samples on one L40S is roughly 1.5–2.5 hours. **Checkpoint every epoch.**
An epoch-1 checkpoint that exists beats an epoch-3 checkpoint that is still training at H11.

### H7–H8 · Baselines (run locally, no GPU needed)
```bash
python -m scania_timenet.evaluate --data-dir ../data --split validation
```
Gives you always-0, always-4, and two gradient-boosting baselines with cost + macro-F1 + binary F1.
**This is your safety net: even if training fails completely, you have a real results table
on the official split with the real cost function.**

### H8–H10 · Predict + evaluate
```bash
python predict.py --ckpt ckpt/best --data-dir data --split validation --out out/tslm_val.jsonl
# copy back, then:
python -m scania_timenet.evaluate --data-dir ../data --split validation --preds out/tslm_val.jsonl
```
Only touch `--split test` **once**, at the end. Tuning against test is the one thing that would
actually disqualify your rigour claim.

### H10–H12 · Demo + slides
Render 3–4 example figures (`render_plot` in `gen_cot.py` writes PNGs), pick one truck the model
got right with good reasoning and one it got wrong, and build the results table around
**cost saved vs the check-nothing policy**.

---

## Corners to cut, in the order you should cut them

1. **Drop `--vision` entirely.** Already the default. Saves 2+ hours.
2. **Cut the corpus to 2,000 samples** if generation is slow. 2k CoT samples fine-tune fine.
3. **Evaluate on a 1,000-vehicle subsample of validation** during iteration (`--limit` in
   `predict.py`). Full val is 5,046 generations. Run the full split once, for the final number.
4. **One epoch is acceptable.** Say so on the slide; nobody expects convergence in 12 hours.
5. **If the OpenTSLM repo fights you past H6 — stop.** Fall back to: freeze a small LLM, train
   *only* a linear head on pooled channel embeddings, and present the CoT corpus + connector +
   cost-aware evaluation as the contribution. The connector and the evaluation design are
   genuinely the novel parts; the fine-tune is the replaceable part.
6. **Never cut:** the cost-matrix evaluation, the censoring logic, or the vehicle-level split.
   Those three are what make the result defensible, and they are already written.

---

## What will bite you

- **`length_of_study_time_step` is a float** (e.g. `281.8`), not an integer. Handled.
- **ECU resets** make counter diffs negative. Treated as missing, not as huge negative rates. Handled.
- **Class imbalance is brutal**: validation is 4,910 / 16 / 14 / 30 / 76. Accuracy is meaningless
  (predict-all-0 scores 97%) and macro-F1 is noisy at n=14. **Lead with total cost.** Say this
  before a judge says it.
- **Free-generation parsing.** If the model rambles without `Answer:`, `predict.py` defaults to
  class 0, which is the *expensive* error. Check the parse rate before trusting any number —
  a 20% unparsed rate will silently look like a bad model.
- **Don't let the model name parts.** The system prompt forbids it. If a demo output says
  "turbo actuator seal", that is the one failure that sinks the pitch.

---

## Files

| File | What it does |
|---|---|
| `scania_timenet/connector.py` | `SCANIATimeNetConnector` — CSVs → TimeNet samples, channels/annotations/tasks, censoring-aware labels, cost matrix, fact sheet |
| `scania_timenet/gen_cot.py` | CoT corpus generation: prompt, validation, concurrency, resume, optional plots |
| `scania_timenet/opentslm_dataset.py` | `ScaniaCoTQADataset` / `ScaniaEvalDataset` for OpenTSLM |
| `train_flamingo.sh` | Nebius fine-tuning launcher |
| `predict.py` | Checkpoint → predictions jsonl |
| `scania_timenet/evaluate.py` | Cost + macro-F1 + binary F1 vs 4 baselines |

---

## Baseline results — MEASURED, official validation split (5,046 vehicles)

Class counts `[4910, 16, 14, 30, 76]` — exact match to the published figures.
Train corpus after censoring: 210,954 windows, `[202847, 3126, 1606, 939, 2436]`.

| system | total cost | cost/vehicle | macro-F1 | binary-F1 | accuracy |
|---|---|---|---|---|---|
| **gbm_window_costweighted** | **39,278** | **7.78** | 0.1740 | 0.0893 | 0.6829 |
| gbm_window | 49,437 | 9.80 | 0.2039 | 0.0860 | 0.8585 |
| always_4 (check everything) | 49,566 | 9.82 | 0.0059 | 0.0525 | 0.0151 |
| always_0 (check nothing) | 57,400 | 11.38 | 0.1973 | 0.0000 | 0.9730 |

**The bar your TSLM must clear: 39,278.**

### The headline finding — build the pitch on this

Cost-weighting drops accuracy from 97.3% to 68.3% and cuts cost by 31.6%. The two metrics move
in *opposite* directions. The model that looks worst under the metric everyone reaches for is
the one that saves a third of the money. That is a quantified argument for putting the expert
cost function inside the training loop, not just in the report.

Secondary: check-everything (49,566) beats check-nothing (57,400). The fleet's default policy is
the worst option on the board.

### Caveat you must not paper over

Macro-F1 is 0.17-0.20 for every baseline, and always-predict-0 scores 0.1973 — so the GBM at
0.2039 is barely above a system that discriminates nothing. Binary F1 is ~0.09.

1. **Do NOT claim you are beating a published macro-F1 of ~0.879.** That figure came from a search
   result and is unverified; with 14-16 vehicles in some classes it is implausible for this exact
   task and is probably a different framing. Verify its provenance before citing it, or drop it.
2. **Lead with cost, always.** The defensible claim is "cost reduction on a genuinely hard, badly
   imbalanced task", not "state of the art".
3. The 20 derived channels may be under-powered for classical models. The TSLM sees the full
   sequence rather than summary statistics, which is exactly where it should win — that is the
   hypothesis your run is testing.
