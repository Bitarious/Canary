# Linux server handoff

The full-history HDD model passed every frozen success check on 2,048 unseen drives. It completed all 11,315,069 training windows on eight Nebius RTX PRO 6000 GPUs. Channel accuracy is 99.68%, compared with 69.43% for the constant baseline and 86.01% with numerical inputs zeroed. Reversal, shuffle, and sixteen exact reload predictions also pass. All checkpoints and 648 evaluation JSON files are exported with verified hashes. The evaluation VM stopped successfully at 04:20:37 UTC on September 13. Read [full-history training](full-history-training.md) for evidence and limits. This result supports signal descriptions, not failure prediction.

The user also authorized a [separate component TSLM program](component-training-program.md) if the HDD model passes. Research the remaining hardware categories and train separate models within the same total $600 ceiling. Keep source and evidence in this GitHub repository. The user authorized the full project upload on September 13, 2026.

All thirteen component categories now have separate models that pass their declared signal-description checks: HDD, SSD, NVMe, DRAM, CPU, GPU, server power, fan, gearbox, generator bearing, gear-oil pump, slide-rail sound, and industrial-valve sound. All selected weights and evaluation artifacts are exported with verified hashes. Same-GPU reload checks pass for every model. Local CPU checks reproduce sixteen saved answers for ten categories. CPU-component, GPU-component, server, and the failed dated valve model reproduce fifteen. Read [component results](component-model-results.md) for metrics, checkpoints, and limits.

The dated radiator-valve model failed twice. Its original gate lacked changed-window support in H09. The unchanged-weight follow-up covered all 12,335 unused test windows, but H09 performed slightly better with zeroed numerical inputs. Its paired-group sign probability of 0.0625 failed the unchanged 0.05 limit. Preserve both failures. Do not fit either released run again.

The separate industrial-valve sound model uses MIMII recordings and fresh upstream initialization. The user authorized this unknown-date exception when reviewed dated alternatives are inadequate. Its fixed design reserves one training machine, one validation machine, and five test machines. The prepared dataset contains 9,801 training, 6,688 validation, and 52,393 test windows. Training completed six epochs in 334.6 seconds and selected epoch three on validation. The frozen test used 5,120 windows from 3,204 recordings. It passed with 77.08% channel accuracy, 0.7579 macro F1, and 100% valid outputs. Zero-input accuracy was 49.34%. GPU and CPU reload each matched sixteen saved answers. All 1,626 exported JSON and checkpoint files passed hash verification. This sound result does not establish that radiator-valve telemetry works.

All 93 tests passed in the working tree and in a fresh locked checkout. The latter rebuilt the native pilot. Evidence is in `artifacts/component-audit/v1/isolated-verification-v10/`. The model catalog records fifteen evaluated runs and fourteen distinct selected checkpoints. Thirteen categories pass. No model uses another component's fitted weights or training examples. Sound models retain unknown chronology and no calibration fitting. Dated datasets retain disjoint groups and ordered partitions.

Controller CLI authentication is restored. At 07:29 UTC, all three owned VMs were verified stopped. The final RTX stop completed at 07:28:48.868937 UTC through operation `computeoperation-e05y3x9vpgfwz78qjc`. The final ledger estimates $111.35 spent and $488.65 remaining under the $600 ceiling. This is a conservative cost estimate, not the current voucher balance. Three retained cloud disks cost about $0.03734 per hour together. No GPU compute remains active. After provider verification, the completed job's controller deadline timer was stopped at 07:33 UTC. The guest guard remains on the stopped VM. Its retirement receipt is in the final phase directory.

The last valve phase stayed within its $28.90 cap and 08:59:46 UTC deadline. Its complete model export was verified before the completion guard requested provider stop. A later attempt to copy secondary phase logs missed SSH shutdown. Immutable preflight/start evidence, the complete model export, its terminal record, and provider stop proof remain available. See `artifacts/nebius/full-history-v1/valve-audio-phase-v1/completion.json`. Do not restart these job-owned VMs without a fresh budget and valid guest deadline.

The requested component training program is complete within the stated benchmark scope. The operator application and failure-risk modeling remain separate work in the implementation plan. The user has now authorized commits and the GitHub upload. See [the release guide](project-release.md).

## September 13 publication and private demo

The user authorized the complete GitHub upload and parallel agents for publication and private demo access. The training work and teammates' main branch were merged without conflicts. The [release guide](project-release.md) describes source, selected models, evaluation records, and dataset reproduction.

The private demo route is `https://projects.home.doodlebeast.com/driftops/#/site/site-a`. It requires the existing WireGuard access and either an administrator grant or a DriftOps resource grant. The user approved a DriftOps-only grant for the registered laptop after its request reached the gateway but returned403. The laptop remains a non-administrator. The gateway route, browser navigation, fleet data, and analysis requests passed local verification. The app still uses synthetic telemetry and rules.

The gateway and its access configuration belong to the private hosting project, not this source repository. The demo backend binds to loopback. No public app port was opened. The laptop received only the approved DriftOps grant.

## What this revision can run

The real Backblaze pilot is bundled under `examples/backblaze-pilot/` with its
source manifest and checksum. `driftops prepare` builds and verifies the complete
TimeNet/TimeF dataset, and `driftops demo` serves a browser preview of development
windows with charts and deterministic signal descriptions. Repeated preparation
reuses the committed TimeF version and checks it against the source.

The repository now also has a pinned OpenTSLM-SP loader, a TimeNet training bridge,
bounded temporal-module training, checkpoint reload, and held-out evaluation.
`config/train_tslm.yaml` supplies training settings. See [training commands](training.md)
and the [concept evaluation](evaluation.md). The selected local checkpoint is
`artifacts/tslm/concept-v2/best.pt`. It needs the pinned Gemma base and this code.

The concept experiment failed the useful-input-dependence check. All 64 test windows
receive the same answer, including when numerical inputs are zeroed. Channel accuracy
is 77.7%, but the all-constant baseline scores 73.4%. Do not present this checkpoint
as useful signal interpretation or failure prediction. The browser still shows
deterministic descriptions. Risk fitting and the operator workflow remain unfinished.
The CPU pilot used no paid compute. The subsequent full-history job uses a bounded Nebius GPU setup described in the full-history report.

The development/controller machine is the user's Linux server with a Ryzen AI
Max+ 395 and 128 GB unified RAM. Nebius supplies the intended NVIDIA GPU training
compute. No local CUDA setup is required for the data preview.

The separate `driftops3d/` illustrative UI uses synthetic telemetry and rule-based
health analysis. Its HQ scene contains exactly three open laptop models, one per
office group, with direct navigation to device analysis. The zoom transition
uses the same laptop exterior as the device view and matches its camera projection
at the switch; the navigation regression checks model geometry and screen alignment
as well as clicks and return navigation. The check is documented in the 3D README.
Site A and Site B retain
their server racks. Run it with `python3 driftops3d/server.py` and open port 8765;
see [its README](../driftops3d/README.md). This is separate from the real Backblaze
preview described above.

## First setup on the server

Install Git, `uv`, Entire, and `tmux` using the server's usual package/setup
workflow. Official installation instructions:
[uv](https://docs.astral.sh/uv/getting-started/installation/),
[Entire](https://docs.entire.io/installation),
[Codex CLI](https://developers.openai.com/codex/cli/),
[Nebius CLI](https://docs.nebius.com/cli/install).

```bash
git clone https://github.com/M-10001/EHL_Zurich_hackathon_team_piloty.git
cd EHL_Zurich_hackathon_team_piloty
bash scripts/bootstrap.sh
uv run --no-sync driftops demo
```

The bootstrap configures Entire for Codex on this machine, installs the locked
Python 3.12 environment, prepares the bundled data, and runs the tests. It does
not log into cloud accounts, fit models, or start billable resources.

Open `http://127.0.0.1:8000` on the server, or create a tunnel from the computer
whose browser you use:

```bash
ssh -L 8000:127.0.0.1:8000 YOUR_LINUX_SERVER
```

Then visit `http://127.0.0.1:8000` in that computer's browser. The preview binds
only to loopback. It supports previous/next windows and a numbered-window jump.

For an existing checkout:

```bash
git pull --ff-only
bash scripts/bootstrap.sh
```

Run from the repository root. `uv` installs the package, so no manual
`PYTHONPATH` is needed. Downloaded TimeF data, caches, and model artifacts remain
local. To acquire a different cohort from the public source, use the explicit
commands in [data preparation](data-preparation.md) with a new dataset version.

## Entire must remain active

The user requires Entire history for hackathon submission. **Never disable its
agent hooks or Git push hook, never skip session pushes, and never use ephemeral
Codex runs.** The committed hook configuration targets Linux. The originating
Windows machine keeps its own trusted Windows commands as a local configuration
change; that change is not part of this handoff.

Before leaving development unattended, run:

```bash
entire version
entire status
entire doctor
```

In Codex, review `/hooks` on this new machine and trust the expected Entire
commands. Entire's `doctor` reports missing hook approval records. Git does not
clone `.git/hooks`; the bootstrap's `entire enable --agent codex --local` step
installs them. Normal `git push` then includes Entire's checkpoint sync. Keep
that hook active even if a push needs troubleshooting. Credentials should never
be printed into a recorded session.

The September 13 read-only doctor check found the existing metadata branches, Git hooks, Codex hooks, and approval records intact. It also reported a stale active session whose process had exited. Session `01a09767-a6e8-7fa0-86e6-5144390eb82c` retains two checkpoints on its shadow branch. No forced repair, condensation, history deletion, commit, or push was attempted. Do not report current session capture as verified from this check alone. The 07:21 UTC check again found this same active session with exited process 421692. Entire remained enabled. Metadata branches, Git hooks, Codex hooks, and approval records passed their checks. The filtered evidence is in `artifacts/component-audit/v1/entire-check-20260913-final.json`.

## Development overnight

Sign into Codex locally and complete the Entire hook review while present.
Check the environment's required network/command permissions before leaving it;
the launcher preserves the normal sandbox, approval rules, configuration, and
session logging. It does not bypass controls to force progress.

```bash
tmux new -s driftops-dev
bash scripts/overnight-development.sh
```

Detach with `Ctrl-b`, then `d`. Reconnect with `tmux attach -t driftops-dev`.
The task is stored in [overnight-task.md](overnight-task.md). Outputs are under
`artifacts/development/` with timestamped event, stderr, and final-summary files;
Entire records the session separately. The launcher runs one substantive task,
not an infinite retry loop. For a stopped Codex session, use its printed session
ID with `codex exec resume SESSION_ID` after addressing the reason for the stop.
See [official non-interactive mode documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

`tmux` keeps processes alive across SSH disconnects. It does not survive a server
reboot or guarantee progress through expired authentication, usage limits,
missing permissions, or unavailable cloud capacity. The server must stay powered
on and awake. Git/Entire history travels with the push; private account logins
and this machine's installed tools do not.

## Training readiness before leaving it overnight

The local CPU training path is implemented and verified. Its first concept result
is negative, as described above. Nebius provisioning and provider-stop guards now
exist. All three job-owned VMs passed provider stop checks before the valve phase. Full-history HDD and twelve-category component exports have passed verification.
The valve sound trial also passed and exported its artifacts.

1. Authenticate Hugging Face on the Linux server with `uv run --no-sync hf auth login`.
   Verify the two pinned Gemma/OpenTSLM artifacts from [model setup](model-setup.md).
2. Install/authenticate the Nebius CLI on the controller and select the team's
   `driftops` profile/project. Use `bash scripts/nebius.sh ...` for native Linux;
   `nebius.ps1` is the original Windows/WSL launcher.
3. Recheck remaining credits and current GPU capacity/rates before spending. The user
   reported $605 on September 12. The project ceiling remains $600. The CPU pilot spent
   $0. The later Nebius setup has paid runtime recorded in the full-history cost ledger.
4. Use the verified local model loader and training bridge as the starting point.
   The original CPU checkpoint repeats one answer. The subsequent cloud models have
   separate measured results. Explain every training diagnostic in advance.
5. Before a paid run, present and save its overview: task, data/splits,
   trainable/frozen parameters, necessity, GPU, rate, expected duration/cost,
   spend/runtime cap, stopping criteria, evaluation, and saved outputs. Start
   small; $600 is the total ceiling, not the initial-run target.
6. Run the job on the Nebius machine under its own `tmux` session or service,
   with unbuffered logs, atomic periodic checkpoints, optimizer/RNG/data-position
   state, resumable progress, and a tested time limit. The job must remain
   independent of the coding-agent conversation and controller SSH connection.
7. Export artifacts and release billable compute when done. A Python process
   exiting does not by itself stop VM billing. Verify cleanup and preserve any
   output storage needed for the submission; never delete the only checkpoint.

Keep development work on the Linux controller and launch training from an
immutable checkout on Nebius so concurrent edits cannot change a running job.
The initial language task can use this pilot; strong failure-prediction claims
require a separate event-support audit and potentially a larger cohort.

The completed component phase used a bounded export grace period. It waited at most fifteen minutes for slide-rail and valve follow-up export receipts. It then invoked the unchanged provider guard and stopped successfully at 06:38:09 UTC. Its 07:51:32 UTC deadline has been superseded by the separately budgeted valve phase. This stays within the original $50.45 phase reservation. `scripts/stop_after_component_exports.py` and its unit override are recorded in `artifacts/nebius/full-history-v1/export-grace-v1/`. All 91 tests pass in working and isolated locked environments. The fresh checkout also rebuilt the native pilot. Evidence is in `artifacts/component-audit/v1/isolated-verification-v9/`.
