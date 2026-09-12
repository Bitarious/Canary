# DriftOps 3D

A digital twin for infrastructure health across several sites. Data centers are shown as 3D halls of racks; the HQ fleet shows three open laptops with screens, keyboards and trackpads. Devices are colored by health, and drifting devices glow.

- **Picking a device:** pick a site, then click a rack, then click a server. At HQ, click a laptop directly. That opens the 3D device view.
- **Analyzing it:** in the device view, **Analyze** makes the chassis transparent and colors every internal component by health.
- **Component details:** click a component to see its health trajectory, 7-day risk, failure window, evidence, recommended action and a "what if I wait?" simulator.

## Run

```bash
pip install psutil          # only dependency (agent); the server uses the standard library
python server.py            # http://127.0.0.1:8765  (loads the demo sites, ~15 s model warm-up)
```

### Views

| View | What you get |
|---|---|
| **Twin** (`#/site/<id>[/rack/<id>]`) | Left: site list, status counts, "drifting now", rack-level patterns (e.g. *Rack 06: thermal drift on 6 devices*). Center: the 3D racks. Right: the **copilot**. Selecting a rack asks "Status of Rack 06?" automatically. Quick chips: *Why? · What if I wait 7 days? · What should I do? · Show fleet comparison*. The copilot is rule-based over the model outputs; it does not use an LLM. |
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

- a failing disk combined with a rack-wide cooling problem in Site A Rack 06
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
| `server.py` | REST API (`/api/sites`, `/api/sites/<id>`, `/api/fleet`, `/api/incidents`, `/api/machines/<id>`, `/api/analyze`, `/api/copilot`, `/api/telemetry`, `/api/benchmark`) + serves `web/`. |
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
     "series": {"bench_ops": [ ... ], "temp_c": [ ... ]}}
  ]
}
```

Fleet percentiles are measured against illustrative reference baselines, not a real fleet. Cross-component findings describe associations, not proven causes.
