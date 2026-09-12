Continue building DriftOps for the Temporal AI Challenge using the current
repository. Read AGENTS.md, docs/handoff.md, docs/implementation-plan.md,
docs/model-setup.md, and docs/data-preparation.md first. Inspect the actual code
and current artifact state before assuming a capability is complete.

The user wants development on a Linux Ryzen AI Max+ 395 server with 128 GB RAM
and bounded training on Nebius. Keep working through ready tasks autonomously.
Work alone without sub-agents. Keep Entire and every required recording/push
hook active; this is a submission eligibility requirement. Do not bypass
permissions, authentication, or spending limits to keep the run going.

The bundled Backblaze pilot, TimeNet conversion, tested input isolation, and
local data preview exist. A complete trained-model demo does not yet exist.
Build the missing model loader/bridge, actual training and evaluation runner,
and operator journey in dependency order. Use the pinned Gemma 3 270M base with
its matching OpenTSLM-SP checkpoint. Verify runtime compatibility and numerical
sequence use before treating this path as operational. Preserve upstream
licenses/attribution if adapting code. Keep all preprocessing causal and use
separate answer targets. Keep the base language model frozen initially and
adapt the numerical encoder/projector if the loaded parameter audit supports it.

Before EVERY model-training run, including tiny diagnostics and risk-baseline
fitting, explain what it does and why, data/splits, updated/frozen parameters,
hardware/rate/cost cap, stop conditions, evaluation, and saved outputs. Write
this overview to the run artifact directory before starting. The user's request
is advance explanation, not a new approval question for an already authorized
run. If an actual missing dependency requires user action, report it clearly and
continue independent work. No credentials belong in outputs or session logs.

Use the existing Nebius account only after verifying remaining credits, current
rates/capacity, and a bounded initial run. The team voucher is $600; no additional
credits are assumed. Prefer a small single-GPU diagnostic before any larger run.
Do not create idle billable resources while writing code. Each remote job needs
an immutable checkout, unbuffered logs, periodic atomic resumable checkpoints,
optimizer/RNG/data position state, finite runtime/spend limits, and an explicit
artifact-export/compute-release procedure. Test interruption and resume before
claiming unattended training works. Run training independently of the coding
agent's lifetime so a conversation pause does not kill a valid job.

Keep validation and test honest: use disjoint drives and ordered dates; do not
tune on test; compare the trained model with its starting checkpoint and stated
baselines. Generated SMART descriptions are weak labels, not expert truth. Do
not claim calibrated failure risk from the small pilot without outcome support.
Do not replace missing model inference with invented model responses.

Run relevant tests and the full local workflow after implementation. Update
docs/handoff.md with completed capabilities, exact commands, artifact locations,
measured results, remaining limitations, and any blockers. Preserve the team's
Git changes. At a coherent verified milestone, commit project changes normally
with Entire active; use the existing authorized project push workflow and verify
both source and checkpoint synchronization. End with a concise result and clear
remaining work. Do not loop idle or retry permanent failures indefinitely.
