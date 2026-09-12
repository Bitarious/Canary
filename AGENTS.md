# DriftOps project instructions

Read `docs/handoff.md` and `docs/implementation-plan.md` before continuing work.

- Keep Entire enabled, with agent hooks and the normal Git push hook active.
  The user explicitly requires its session logs for hackathon eligibility.
  Never disable, bypass, discard, or suppress Entire recording or checkpoint pushes.
- Work alone, without sub-agents. Start ready work without fixed implementation times.
- Initial demo scope: the bundled Backblaze HDD pilot and Gemma-based OpenTSLM.
- Before every model-training run, including diagnostics and baseline fitting,
  explain the objective, necessity, data/splits, updated/frozen parameters,
  hardware/cost limit, stopping conditions, evaluation, and outputs. Write the
  same overview into the run artifacts before launching. The user's instruction
  requires advance explanation, not a new permission question for each run.
- Nebius is the intended GPU provider; the user's Linux Ryzen AI Max+ 395 server
  with 128 GB unified RAM is the development/controller machine. The team voucher
  is $600, subject to remaining balance. Do not assume extra credits or a GPU
  reservation. Obtain current rates/balance and enforce a bounded run before spending.
- Exclude secrets from command output, model prompts, commits, and logs. Keep
  Entire history intact; use normal local browser/CLI authentication for accounts.
- Retain causal input boundaries, disjoint devices and ordered time partitions.
  Do not relabel rule descriptions as model inference or report unmeasured metrics.
- Validate changes with the relevant tests and a clean-checkout smoke test before
  claiming portability. Keep `docs/handoff.md` accurate when capabilities change.
