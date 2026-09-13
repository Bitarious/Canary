# Canary demo

Canary combines a saved real HDD evidence view with a separate synthetic 3D infrastructure demo. Data centers are shown as 3D halls of racks; the HQ fleet shows three open laptops using the same chassis, keyboard and screen as the device view. The laptop zoom matches the destination camera and screen position before switching views. Devices are colored by health, and drifting devices glow.

- **Picking a device:** pick a site, then click a rack, then click a server. At HQ, click a laptop directly. That opens the 3D device view.
- **Analyzing it:** in the device view, **Analyze** makes the chassis transparent and colors every internal component by health.
- **Component details:** click a component to see its health trajectory, illustrative 7-day risk, rule window, evidence, illustrative action and a "what if I wait?" simulator.

## Run

```bash
pip install -r requirements.txt   # psutil for the agent; the server uses the standard library
python server.py            # http://127.0.0.1:8765  (loads the demo sites, ~15 s illustrative-rule warm-up)
```


## Saved real HDD evidence

Open `#/evidence/hdd-rising`, or select **Inspect saved HDD result** in the synthetic twin banner.
Use **Stable control** and **Model mismatch** to inspect the other two cases.
The view shows four raw 28-day SMART charts, the input cutoff, and the exact saved model answer.
Source hashes, exact normalized model input, and recorded checkpoint provenance are under a details disclosure.

The server reads only `../results/2026-09-13/hdd-demo-cases.json` relative to this directory.
`GET /api/cases` lists the cases. `GET /api/cases/<id>` returns one case.
It verifies the fixed bundle SHA-256, all three input hashes, and the daily-window contract before serving data.
Corrupt or missing evidence returns HTTP 503. Unknown IDs return HTTP 404.
The checkpoint hash is recorded provenance. This server does not rehash model weights or run inference.

The selected HDD model is Gemma 3 270M OpenTSLM-SP, with 271,029,888 total parameters and 2,931,072 trained parameters.
Training updated the temporal encoder, projector, and attention LoRA.
The frozen HDD test measured 99.68% channel agreement with 6,777 weak labels across 2,048 unseen drives.
Zeroed inputs scored 86.01%. The constant baseline scored 69.43%.
These post-evaluation examples illustrate results. They are not a representative sample for estimating aggregate performance.
Failure probability, failure window, and confidence remain null in the real case records.
Failure prediction and maintenance timing have not been validated.

The synthetic Twin, Fleet, Incidents, and component drawers keep their illustrative rule outputs.
**More** contains site navigation and the optional hardware benchmark.
The supplied Canary logo remains unchanged in `web/assets/canary-logo.png`. CSS frames it in the header.

### Evidence and replay checks

For the complete automated browser workflow from the repository root:

```bash
npm ci
npx playwright install chromium
npm run test:browser
```

The harness starts a local server with temporary device storage, checks four viewports, and checks 3D laptop/server navigation. It stops its own processes afterward. Node 22 or newer is required.

From the repository root:

```bash
python3 -m unittest discover -s driftops3d/tests -p 'test_*.py' -v
node --check driftops3d/web/js/main.js
node --check driftops3d/web/js/evidence.js
node driftops3d/tests/evidence-ui.mjs http://127.0.0.1:8765
```

The browser check requires Playwright and a supported browser.
`PLAYWRIGHT_MODULE` can select an installed Playwright module. `CHROME_PATH` can select Chrome.
`SCREENSHOT_DIR` can name an existing absolute folder for review screenshots.
The check covers four viewports: 390×844, 768×1024, 1440×900, and 2560×1440.
It checks the real cases, mismatch, Analyze bounds, historical/projected copilot controls, reduced motion, and mobile drawer focus.
It also checks submitted mobile copilot answers, readable chart labels, case/rack focus, inert modal backgrounds, and simulator-tab focus.
The mobile Twin scrolls vertically and reserves at least 220 pixels for the copilot answer area.
Run the separate navigation regression below to check the existing 3D geometry, picking, and camera transitions.

### Browser check

Browser navigation regression check: with the demo running and a separate Chrome
test window started with `--remote-debugging-port=9223` and
`--user-data-dir=/tmp/canary-navigation-chrome`, run this from the repository root
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
| **Evidence** (`#/evidence/<id>`) | Saved real HDD cases, raw charts, exact model output, separate weak reference, and provenance. |
| **Twin** (`#/site/<id>[/rack/<id>]`) | Left: site list, status counts, "drifting now", rack-level patterns (e.g. *Rack 06: thermal drift on 6 devices*). Center: the 3D racks. Right: the **copilot**. Selecting a rack asks "Status of Rack 06?" automatically. Quick chips: *Why? · What if I wait 7 days? · What should I do? · Show fleet comparison*. The copilot uses illustrative rule outputs; it does not use an LLM. |
| **Time machine** (bar under the twin) | Scrub or play (▶, or space and ←/→ while the timeline has focus; Shift = a week) through the **last 30 days** and a **7-day projected horizon**. Past days show illustrative rule results using only the runs available on that day. Chains along a rack link servers degrading the same way on the shown day. Markers flag when a device first left its own baseline (◆) and each status change (●). Past NOW, the hall switches to a purple *projected* look: each component's current health slope is extended, counting declines only. That is a trend extrapolation, not a model forecast. Historical and projected dates disable the copilot. Return to Now to ask a question. The server rejects non-current cutoffs before reading fleet data. Current answers display their response date and illustrative origin. |
| **Device** (`#/device/<id>`) | The per-device 3D analysis, with breadcrumbs back to the site and rack (Esc also goes back). |
| **Fleet** (`#/fleet`) | Searchable table of every device, filterable by site and status and sorted by priority. |
| **Incidents** (`#/incidents`) | Rack-level patterns plus every at-risk component, ranked by risk × criticality × redundancy. |

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

Run the agent several times over several days to build a health trajectory. The illustrative rules replay all stored runs, which are kept in `data/machines/<id>/`.

## Layout

| Path | What |
|---|---|
| `agent/collect.py` | Benchmark + telemetry collector (Windows/Linux). Collects battery wear, storage reliability counters / SMART (`smartctl` if installed), `nvidia-smi`, WHEA and disk error events, and CPU temps where exposed. Windows temperature and reliability counters usually need an admin shell. |
| `driftops/model.py` | `analyze(run, history)` returns health, stage, trend, risk, failure window, evidence, correlations, action and wait simulation. This is the **baseline v0** (transparent statistics + rules). The trained HDD output has its own saved-evidence contract. It does not replace this rule analysis. |
| `driftops/demo_data.py` | Sites, racks and synthetic device histories with degradation profiles. |
| `driftops/fleet.py` | Device registry, cached model results, site/rack aggregation, rack-level pattern detection, incidents. |
| `driftops/copilot.py` | Answers status / why / wait / action / fleet-comparison questions from model outputs. |
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
197, 198, 199, 240, 241 and 242. These column names support future input mapping. This demo does not run the trained HDD model on local drives. The agent reads these from `smartctl` when it is installed; on Windows it falls
back to the built-in `MSStorageDriver_ATAPISmartData` WMI class. Both need an admin (or root) shell.
Drives behind Intel RST may only be visible to `smartctl` (as `/dev/csmi*`). The analysis passes
the row through as `components[].drive_stats`.

Fleet percentiles are measured against illustrative reference baselines, not a real fleet. Cross-component findings describe associations, not proven causes.
