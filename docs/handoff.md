# Linux server handoff

## What this revision can run

The real Backblaze pilot is bundled under `examples/backblaze-pilot/` with its
source manifest and checksum. `driftops prepare` builds and verifies the complete
TimeNet/TimeF dataset, and `driftops demo` serves a browser preview of development
windows with charts and deterministic signal descriptions. Repeated preparation
reuses the committed TimeF version and checks it against the source.

This is a working data preview. OpenTSLM inference, a training runner, learned
artifacts, risk fitting, full operator workflow, and model evaluation remain to
be implemented. `config/model.yaml` pins the selected Gemma/OpenTSLM pair; it is
not a runnable training configuration. No GPU instance or paid compute has been
started. These are the next development tasks, not hidden completed capabilities.

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

The continuation task includes implementing and verifying the training path.
Until that is complete, there is no training command to launch. Do not mistake
the data preview or a successful source download for a verified model runtime.

1. Authenticate Hugging Face on the Linux server with `uv run --no-sync hf auth login`.
   Verify the two pinned Gemma/OpenTSLM artifacts from [model setup](model-setup.md).
2. Install/authenticate the Nebius CLI on the controller and select the team's
   `driftops` profile/project. Use `bash scripts/nebius.sh ...` for native Linux;
   `nebius.ps1` is the original Windows/WSL launcher.
3. Check actual remaining credits and current GPU capacity/rates. The user
   confirmed a $600 voucher, but remaining console balance has not been verified.
4. Implement the pinned model loader and training bridge; prove numerical inputs
   are used, targets remain isolated, a small update works, and saved weights
   reload. Explain every training diagnostic in advance.
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
