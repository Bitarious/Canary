# DriftOps 3D

A digital twin for infrastructure health across several sites. Data centers are shown as 3D halls of racks; the HQ fleet shows three open laptops using the same chassis, keyboard and screen as the device view. The laptop zoom matches the destination camera and screen position before switching views. Devices are colored by health, and drifting devices glow.

- **Picking a device:** pick a site, then click a rack, then click a server. At HQ, click a laptop directly. That opens the 3D device view.
- **Analyzing it:** in the device view, **Analyze** makes the chassis transparent and colors every internal component by health.
- **Component details:** click a component to see its health trajectory, 7-day risk, failure window, evidence, recommended action and a "what if I wait?" simulator.

## Run

```bash
pip install -r requirements.txt   # psutil for the agent; the server uses the standard library
python server.py            # http://127.0.0.1:8765  (loads the demo sites, ~15 s model warm-up)
```

### Browser check

Browser navigation regression check: with the demo running and a separate Chrome
test window started with `--remote-debugging-port=9223` and
`--user-data-dir=/tmp/driftops-navigation-chrome`, run this from the repository root
using Node 22 or newer:

```bash
node driftops3d/tests/site-navigation.mjs http://127.0.0.1:8765 http://127.0.0.1:9223
```

This clicks all three HQ laptop models, checks that their exterior geometry and
screen projection match at the view switch, checks device analysis and return
navigation, and checks a server's zoom and return transition.

### Views

| View | What you get |
|---|---|
| **Twin** (`#/site/<id>[/rack/<id>]`) | Left: site list, status counts, "drifting now", rack-level patterns (e.g. *Rack 06: thermal drift on 6 devices*). Center: the 3D racks. Right: the **copilot**. Selecting a rack asks "Status of Rack 06?" automatically. Quick chips: *Why? · What if I wait 7 days? · What should I do? · Show fleet comparison*. The copilot is rule-based over the model outputs; it does not use an LLM. |
| **Time machine** (bar under the twin) | Scrub or play (▶, space, ←/→, Shift = a week) through the **last 30 days** and a **7-day projected horizon**. Past days show the model's results using only the runs available on that day. Chains along a rack link servers degrading the same way on the shown day. Markers flag when a device first left its own baseline (◆) and each status change (●). Past NOW, the hall switches to a purple *projected* look: each component's current health slope is extended, counting declines only. That is a trend extrapolation, not a model forecast. The copilot always answers about the live state. |
| **Device** (`#/device/<id>`) | The per-device 3D analysis, with breadcrumbs back to the site and rack (Esc also goes back). |
| **Fleet** (`#/fleet`) | Searchable table of every device, filterable by site and status and sorted by priority. |
| **Incidents** (`#/incidents`) | Rack-level patterns plus every at-risk component, ranked by risk × criticality × redundancy. |

### Trained model readings

For a benchmarked (non-demo) device, **Analyze** also asks the released OpenTSLM component models to describe its signals. The health score, risk and actions still come from the rule-based baseline. The model readings appear beside them, labelled as descriptions and not failure predictions.

| Component | Model run | Window sent |
|---|---|---|
| GPU | `gpu-component-v1` | 28 averaged steps of power, core and memory temperature sampled by `nvidia-smi` during the stress run |
| CPU | `cpu-component-v1` | 28 steps of package power and core temperature. Power comes from Linux RAPL (usually root), so Windows devices report *not enough data* |
| HDD | `full-history-rtx6000-v2` | SMART 5, 187, 194 and 197 from `drive_stats`, one reading per day over 28 consecutive days |

Inputs are built with the training code (`driftops.component_data`, full-history SMART format). On this setup, the three saved HDD cases in `results/2026-09-13/hdd-demo-cases.json` reproduce their recorded input hashes and answers exactly. The benchmark windows use a different cadence and hardware than the training data (OLCF Summit ten-second means), and each reading says so. Components without enough samples show the exact shortfall.

Setup, once per machine:

1. Create the model environment: `python -m venv .venv-tslm`, install `torch==2.8.0` from the PyTorch CPU index, then `pip install -r requirements-models.txt` and `pip install -e . --no-deps` (see that file's header).
2. Download the checkpoints: `gh release download v2026.09.13 --pattern "gpu-component-v1-model.tar.gz" ...` and extract them as in [the release guide](../docs/project-release.md).
3. Log in to Hugging Face with an account that accepted the Gemma license, and cache the pinned `google/gemma-3-270m` and `OpenTSLM/gemma-3-270m-tsqa-sp` revisions from `config/model.yaml`.

The server finds `.venv-tslm` automatically (override with `DRIFTOPS_TSLM_PYTHON`). It runs the models in one worker process (`python -m driftops.benchmark_tslm`) and preloads the GPU and HDD models at startup (`DRIFTOPS_TSLM_PRELOAD=gpu,hdd`; empty disables). Each loaded model uses about 1.1 GB of RAM, and loading takes about 2 minutes on a laptop CPU. Without the environment or weights, readings show *model unavailable* and everything else works as before. Endpoints: `POST /api/model-readings {machine_id}` and `GET /api/model-status`.

### Getting devices in

- **Benchmark this device**: the server runs `agent/collect.py` on the computer hosting it, which takes about 30 s. The device lands in the **Local devices** site.
- **Other machines**: start the server with `python server.py --host 0.0.0.0`, then on each device run
  `python agent/collect.py --server http://<server-ip>:8765 --site site-a --rack r03 --slot 7`.
  Unknown site or rack ids are created automatically.
- **Offline**: run `python agent/collect.py --out run.json`, then drag the JSON onto the page.

The demo fleet has 147 devices across Site A (7 racks × 12), Site B (6 × 10) and the HQ laptop fleet (3 laptops, one each in Floor 1, Floor 2 and IT bench). It is generated in memory by `driftops/demo_data.py` and labelled `demo`. Its planted scenarios:

- a cooling fault in Site A Rack 06 that starts at U05 about 26 days ago and spreads to six neighbours, plus a failing disk in U09 during the last two weeks (each profile has an onset day in `PROFILES`)
- ECC error growth and PSU voltage drift in other Site A racks
- throttling laptops, worn batteries and a worn-out SSD in the HQ fleet

Run the agent several times over several days to build a health trajectory. The model replays all stored runs, which are kept in `data/machines/<id>/`.

## Layout

| Path | What |
|---|---|
| `agent/collect.py` | Benchmark + telemetry collector (Windows/Linux). Collects battery wear, storage reliability counters / SMART (`smartctl` if installed), `nvidia-smi`, WHEA and disk error events, and CPU temps where exposed. Windows temperature and reliability counters usually need an admin shell. |
| `driftops/model.py` | `analyze(run, history)` returns health, stage, trend, risk, failure window, evidence, correlations, action and wait simulation. This is the **baseline v0** (transparent statistics + rules). The TSLM replaces `_score_component`/`_narrative` and keeps the same output contract. |
| `driftops/demo_data.py` | Sites, racks and synthetic device histories with degradation profiles. |
| `driftops/fleet.py` | Device registry, cached model results, site/rack aggregation, rack-level pattern detection, incidents. |
| `driftops/copilot.py` | Answers status / why / wait / action / fleet-comparison questions from model outputs. |
| `driftops/tslm.py` | Builds 28-step windows from benchmark runs and talks to the trained-model worker (`src/driftops/benchmark_tslm.py`). |
| `web/js/timeline.js` | Time machine scrubber; `/api/sites/<id>/timeline` returns per-day device frames, projections, events and rack chains (`Fleet.timeline`). |
| `server.py` | REST API (`/api/sites`, `/api/sites/<id>`, `/api/sites/<id>/timeline`, `/api/fleet`, `/api/incidents`, `/api/machines/<id>`, `/api/analyze`, `/api/copilot`, `/api/telemetry`, `/api/benchmark`) + serves `web/`. |
| `web/` | `js/site-scene.js` (3D data hall), `js/scene.js` (3D device), `js/twin.js` (sidebar, copilot, fleet, incidents), `js/panel.js` (device panels), `js/main.js` (router). |

## Telemetry schema (`driftops.telemetry/v1`)

```json
{
  "schema": "driftops.telemetry/v1", "source": "agent", "collected_at": "2026-09-12T10:00:00+00:00",
  "machine": {"id": "lt-01", "hostname": "lt-01", "label": "...", "form_factor": "laptop|desktop|server",
              "criticality": "low|medium|high"},
  "components": [
    {"id": "cpu0", "type": "cpu|gpu|memory|storage|battery|cooling|power", "name": "CPU · ...",
     "static": {"hardware_errors_30d": 0},
     "smart":  {"reallocated_sectors": 0, "percentage_used": 12},
     "series": {"bench_ops": [ ... ], "temp_c": [ ... ]},
     "drive_stats": {"model": "ST1000LM035-1RK172", "capacity_bytes": 1000204886016, "serial_hash": "…",
                     "smart_5_raw": 0, "smart_5_normalized": 100, "smart_197_raw": 0, "...": "..."}}
  ]
}
```

`drive_stats` is present only on hard drives that expose ATA SMART. It uses the same columns as the
[Backblaze Drive Stats](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data)
dataset: `smart_<id>_raw` / `_normalized` for ids 1, 3, 4, 5, 7, 9, 10, 12, 187, 188, 189, 193, 194,
197, 198, 199, 240, 241 and 242. A model trained on Backblaze can therefore score a local drive
without remapping. The agent reads these from `smartctl` when it is installed; on Windows it falls
back to the built-in `MSStorageDriver_ATAPISmartData` WMI class. Both need an admin (or root) shell.
Drives behind Intel RST may only be visible to `smartctl` (as `/dev/csmi*`). The analysis passes
the row through as `components[].drive_stats`.

Fleet percentiles are measured against illustrative reference baselines, not a real fleet. Cross-component findings describe associations, not proven causes.
