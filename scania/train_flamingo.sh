#!/usr/bin/env bash
# Fine-tune OpenTSLM-Flamingo on the SCANIA CoT corpus. RUN THIS ON NEBIUS, NOT LOCALLY.
#
# Your GTX 1060 (6GB, Pascal, no bf16) cannot train this. Rent one L40S or A100-40GB.
# At ~$1.5-2.5/hr that is a few dollars of your $1000 voucher for the whole hackathon.
#
#   ssh nebius-box
#   git clone https://github.com/StanfordBDHG/OpenTSLM && cd OpenTSLM
#   pip install -e .
#   # copy scania_timenet/ + out/cot_train.jsonl across, then:
#   bash train_flamingo.sh
set -euo pipefail

REPO=${REPO:-$HOME/OpenTSLM}
COT=${COT:-$HOME/scania/out/cot_train.jsonl}
OUTDIR=${OUTDIR:-$HOME/scania/ckpt}

# Llama-3.2-1B is OpenTSLM's default backbone and the right call for a hackathon:
# it fits comfortably, trains fast, and only the encoder + gated cross-attention layers
# are trainable anyway, so backbone size buys less than you would think.
LLM_ID=${LLM_ID:-meta-llama/Llama-3.2-1B}

mkdir -p "$OUTDIR"
cd "$REPO"

python curriculum_learning.py \
  --model OpenTSLMFlamingo \
  --llm_id "$LLM_ID" \
  --stages scania_cot \
  --device cuda \
  --batch_size 4 \
  --gradient_accumulation_steps 8 \
  --epochs 3 \
  --lr 1e-4 \
  --weight_decay 0.01 \
  --warmup_ratio 0.1 \
  --max_grad_norm 1.0 \
  --output_dir "$OUTDIR" \
  2>&1 | tee "$OUTDIR/train.log"

# NOTE ON FLAG NAMES: curriculum_learning.py's argparse has drifted between commits.
# Run `python curriculum_learning.py --help` FIRST and fix any mismatches. Do not burn
# 40 minutes debugging a flag name at hour 8 -- check at hour 4.
