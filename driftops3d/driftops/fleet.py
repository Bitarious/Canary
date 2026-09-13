"""Fleet registry: devices grouped into sites and racks, with cached model results."""
from __future__ import annotations

import bisect
import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import demo_data, model

STATUS_ORDER = {"healthy": 0, "watch": 1, "elevated": 2, "critical": 3}
PATTERN_GROUP = {"cpu": "thermal", "cooling": "thermal", "gpu": "thermal", "storage": "storage",
                 "memory": "memory", "power": "power", "battery": "battery"}
PATTERN_NOUN = {"thermal": "thermal behaviour (temperature, fan speed, throttling)", "storage": "storage health",
                "memory": "memory error rates", "power": "power delivery", "battery": "battery capacity"}
LOCAL_SITE = {"id": "local", "name": "Local devices", "region": "Benchmarked on this network", "kind": "office",
              "racks": [{"id": "bench", "name": "Bench", "row": 0, "col": 0}]}


def safe_id(s):
    return re.sub(r"[^a-zA-Z0-9_-]", "-", str(s or "unknown"))[:64] or "unknown"


def worst_status(statuses):
    return max(statuses, key=lambda s: STATUS_ORDER.get(s, 0), default="healthy")


# ----------------------------------------------------------------------------- time machine

REPLAY_DAYS = 30     # days shown before now (day 0 = now)
HORIZON_DAYS = 7     # projected days after now
DRIFTING = ("deteriorating", "slowly deteriorating")
FAINT_HEALTH = 97.5  # component health below this carries a (possibly faint) degradation signal


def _top_signal(component):
    return next((e["signal"] for e in component["evidence"] if e["impact"] > 0), None)


def _frame(analysis):
    """Compact device state for one run, as the model saw it at that time (causal: no later runs)."""
    comps = analysis["components"]
    worst = min(comps, key=lambda c: (-STATUS_ORDER[c["status"]], c["health"]))
    return {"t": analysis["collected_at"], "h": analysis["overall"]["health"], "s": worst["status"],
            "w": worst["name"], "sig": _top_signal(worst),
            # faint signals count too: any penalty at all is the first trace of a shared cause
            "g": sorted({PATTERN_GROUP.get(c["type"], c["type"]) for c in comps
                         if c["health"] < FAINT_HEALTH or c["status"] != "healthy" or c["trend"] in DRIFTING})}


def _projected_frame(analysis, days):
    """Extend each component's current health slope ``days`` ahead (declines only, like the risk model)."""
    comps = [(c, max(1.0, c["health"] + min(0.0, c["slope_per_day"]) * days)) for c in analysis["components"]]
    healths = [h for _, h in comps]
    worst, worst_h = min(comps, key=lambda x: x[1])
    return {"h": round(0.6 * min(healths) + 0.4 * sum(healths) / len(healths), 1), "s": model.status_for(worst_h),
            "w": worst["name"], "sig": _top_signal(worst), "p": True,
            "risk": round(model.cumulative_risk(worst["health"], worst["slope_per_day"], days), 4),
            "g": sorted({PATTERN_GROUP.get(c["type"], c["type"]) for c, h in comps
                         if model.status_for(h) != "healthy" or c["slope_per_day"] <= -0.5})}


class Fleet:
    def __init__(self, data_dir: Path, demo=True):
        self.data_dir = data_dir
        self.demo_runs: dict[str, list] = dict(demo_data.demo_fleet()) if demo else {}
        self.sites = {s["id"]: json.loads(json.dumps(s)) for s in (demo_data.SITES if demo else [])}
        self._cache: dict[str, tuple] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ storage

    def save_run(self, run):
        machine = run.setdefault("machine", {})
        mid = safe_id(machine.get("id") or machine.get("hostname"))
        machine["id"] = mid
        machine.setdefault("site", "local")
        machine.setdefault("rack", "bench")
        if not isinstance(run.get("components"), list) or not run["components"]:
            raise ValueError("telemetry needs a non-empty 'components' list")
        if mid in self.demo_runs:
            raise ValueError(f"'{mid}' is a demo device id")
        stamp = safe_id((run.get("collected_at") or "")[:19].replace(":", ""))
        folder = self.data_dir / mid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{stamp}-{uuid.uuid4().hex[:6]}.json").write_text(json.dumps(run), encoding="utf-8")
        return mid

    def _disk_runs(self, mid):
        folder = self.data_dir / safe_id(mid)
        runs = [json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")] if folder.exists() else []
        return sorted(runs, key=lambda r: r.get("collected_at", ""))

    def runs(self, mid):
        return self.demo_runs.get(mid) or self._disk_runs(mid)

    def device_ids(self):
        disk = [p.name for p in self.data_dir.glob("*") if p.is_dir() and any(p.glob("*.json"))] if self.data_dir.exists() else []
        return list(self.demo_runs) + [d for d in disk if d not in self.demo_runs]

    # ------------------------------------------------------------------ model

    def analyze(self, mid):
        runs = self.runs(mid)
        if not runs:
            raise KeyError(mid)
        key = (len(runs), runs[-1].get("collected_at"))
        with self._lock:
            cached = self._cache.get(mid)
            if cached and cached[0] == key:
                return cached[1]
        history, overall, frames, analysis = [], [], [], None
        for run in runs:
            analysis = model.analyze(run, history)
            history.append(model.history_entry(run, analysis))
            overall.append({"t": analysis["collected_at"], "health": analysis["overall"]["health"]})
            frames.append(_frame(analysis))   # what the model concluded with only the runs up to this one
        slope, accel, span = model._trajectory(overall)
        analysis["source"] = runs[-1].get("source", "agent")
        analysis["history_overall"] = overall
        analysis["overall"]["trend"] = model._trend_label(slope, span, len(overall))
        analysis["overall"]["slope_per_day"] = round(slope, 2)
        with self._lock:
            self._cache[mid] = (key, analysis, frames)
        return analysis

    def frames(self, mid):
        self.analyze(mid)
        return self._cache[mid][2]

    def warm(self):
        for mid in self.device_ids():
            try:
                self.analyze(mid)
            except Exception:  # a broken upload must not stop the warm-up
                pass

    # ------------------------------------------------------------------ views

    def _site_of(self, machine):
        sid = machine.get("site") or "local"
        if sid not in self.sites:
            self.sites[sid] = (json.loads(json.dumps(LOCAL_SITE)) if sid == "local" else
                               {"id": sid, "name": sid, "region": "", "kind": "office", "racks": []})
        site = self.sites[sid]
        rid = machine.get("rack") or "bench"
        if not any(r["id"] == rid for r in site["racks"]):
            n = len(site["racks"])
            site["racks"].append({"id": rid, "name": rid.replace("-", " ").title(), "row": n // 4, "col": n % 4})
        return site

    def summary(self, mid):
        a = self.analyze(mid)
        m = a["machine"]
        site = self._site_of(m)
        rack = next(r for r in site["racks"] if r["id"] == (m.get("rack") or "bench"))
        worst = min(a["components"], key=lambda c: (-STATUS_ORDER[c["status"]], c["health"]))
        top = next((c for c in sorted(a["components"], key=lambda c: -c["priority_score"])), worst)
        focus = worst if worst["status"] != "healthy" else top
        runs = self.runs(mid)
        return {
            "id": mid, "label": m.get("label") or mid, "hostname": m.get("hostname"), "form_factor": m.get("form_factor"),
            "site_id": site["id"], "site_name": site["name"], "rack_id": rack["id"], "rack_name": rack["name"],
            "slot": m.get("slot"), "source": a["source"], "runs": len(runs), "last_run": runs[-1].get("collected_at"),
            "health": a["overall"]["health"], "status": worst["status"], "trend": a["overall"]["trend"],
            "slope_per_day": a["overall"]["slope_per_day"],
            "drifting": a["overall"]["trend"] in ("deteriorating", "slowly deteriorating") or worst["status"] != "healthy",
            "priority": max(c["priority_score"] for c in a["components"]),
            "worst": {"id": focus["id"], "name": focus["name"], "type": focus["type"], "status": focus["status"],
                      "health": focus["health"], "risk_7d": focus["risk_7d"], "window": focus["failure_window"]["label"],
                      "trend": focus["trend"], "signal": next((e["signal"] for e in focus["evidence"] if e["impact"] > 0), None)},
            "health_history": [round(p["health"], 1) for p in a["history_overall"]],
        }

    def summaries(self):
        out = []
        for mid in self.device_ids():
            try:
                out.append(self.summary(mid))
            except (KeyError, ValueError):
                continue
        return out

    def rack_patterns(self, site_id):
        """Degradation of the same kind on several devices in one rack → shared cause is likely."""
        by_rack: dict[str, list] = {}
        for mid in self.device_ids():
            a = self.analyze(mid)
            if (a["machine"].get("site") or "local") == site_id:
                by_rack.setdefault(a["machine"].get("rack") or "bench", []).append(a)
        site = self.sites.get(site_id, {"racks": []})
        patterns = []
        for rid, analyses in by_rack.items():
            groups: dict[str, set] = {}
            for a in analyses:
                for c in a["components"]:
                    if c["status"] != "healthy" or c["trend"] in ("deteriorating", "slowly deteriorating"):
                        groups.setdefault(PATTERN_GROUP.get(c["type"], c["type"]), set()).add(a["machine"]["id"])
            rname = next((r["name"] for r in site["racks"] if r["id"] == rid), rid)
            for g, ids in groups.items():
                if len(ids) >= 3:
                    span = max(len(self.runs(i)) for i in ids)
                    patterns.append({
                        "id": f"{site_id}-{rid}-{g}", "site_id": site_id, "rack_id": rid, "rack_name": rname,
                        "group": g, "devices": sorted(ids), "severity": "elevated" if len(ids) >= 5 else "watch",
                        "title": f"{rname}: {g} drift on {len(ids)} devices",
                        "text": f"{len(ids)} of {len(analyses)} devices in {rname} show deteriorating {PATTERN_NOUN.get(g, g)} "
                                f"over the last {span} runs. This looks like a rack-level pattern — check shared cooling, "
                                "power and airflow before replacing parts one by one.",
                    })
        return sorted(patterns, key=lambda p: -len(p["devices"]))

    def site_list(self):
        rows = self.summaries()
        out = []
        for site in list(self.sites.values()):
            devs = [r for r in rows if r["site_id"] == site["id"]]
            if not devs:
                continue
            out.append(self._site_header(site, devs))
        return out

    def _site_header(self, site, devs):
        counts = {s: sum(1 for d in devs if d["status"] == s) for s in STATUS_ORDER}
        return {"id": site["id"], "name": site["name"], "region": site["region"], "kind": site["kind"],
                "nodes": len(devs), "racks": len({d["rack_id"] for d in devs}),
                "health": round(sum(d["health"] for d in devs) / len(devs), 1),
                "status": worst_status(d["status"] for d in devs), "counts": counts,
                "live": any(d["source"] != "demo" for d in devs)}

    def site_detail(self, site_id):
        rows = [r for r in self.summaries() if r["site_id"] == site_id]
        if site_id not in self.sites or not rows:
            raise KeyError(site_id)
        site = self.sites[site_id]
        racks = []
        for r in site["racks"]:
            devs = sorted((d for d in rows if d["rack_id"] == r["id"]), key=lambda d: (d["slot"] or 99, d["label"]))
            if not devs:
                continue
            racks.append({**r, "devices": devs, "health": round(sum(d["health"] for d in devs) / len(devs), 1),
                          "status": worst_status(d["status"] for d in devs),
                          "drifting": sum(1 for d in devs if d["drifting"])})
        drifting = sorted((d for d in rows if d["drifting"]), key=lambda d: -d["priority"])
        return {**self._site_header(site, rows), "racks": racks, "drifting": drifting[:8],
                "patterns": self.rack_patterns(site_id)}

    def timeline(self, site_id):
        """Day-by-day replay of the past REPLAY_DAYS and a trend projection HORIZON_DAYS ahead for one site.

        Past frames are the model's own results using only the runs available by that day. Future frames
        extrapolate today's per-component slopes; they are projections, not model forecasts.
        """
        rows = [r for r in self.summaries() if r["site_id"] == site_id]
        if site_id not in self.sites or not rows:
            raise KeyError(site_id)
        now = datetime.now(timezone.utc)
        days = list(range(-(REPLAY_DAYS - 1), HORIZON_DAYS + 1))
        devices, events = {}, []
        for row in rows:
            mid = row["id"]
            analysis, frames = self.analyze(mid), self.frames(mid)
            stamps = [model._parse_t(f["t"]) for f in frames]
            seq = []
            for d in days:
                if d > 0:
                    seq.append(_projected_frame(analysis, d))
                    continue
                i = bisect.bisect_right(stamps, now + timedelta(days=d)) - 1
                seq.append(None if i < 0 else {k: frames[i][k] for k in ("h", "s", "w", "sig", "g")})
            known = [f["h"] for d, f in zip(days, seq) if f and d <= 0][:5]
            devices[mid] = {"label": row["label"], "rack_id": row["rack_id"], "slot": row["slot"], "frames": seq,
                            "baseline": sorted(known)[len(known) // 2] if known else None}
            events.extend(self._events(mid, row, days, seq))
        racks = {r["id"]: r["name"] for r in self.sites[site_id]["racks"]}
        links = [self._links(devices, racks, i) for i in range(len(days))]
        return {"site_id": site_id, "now": now.isoformat(), "days": days, "now_index": days.index(0),
                "devices": devices, "events": sorted(events, key=lambda e: (e["day"], -STATUS_ORDER.get(e["status"], 0))),
                "links": links,
                "projection": "Linear extension of each component's current health slope; declines only."}

    @staticmethod
    def _events(mid, row, days, seq):
        """When a device first left its own baseline, and when it first reached each worse status."""
        out = []
        past = [(d, f) for d, f in zip(days, seq) if f and d <= 0]
        if len(past) < 4:
            return out
        base = sorted(f["h"] for _, f in past[:5])[len(past[:5]) // 2]
        first = STATUS_ORDER[past[0][1]["s"]]
        onset = next(((d, f) for d, f in past
                      if f["sig"] and (f["h"] <= base - 4 or STATUS_ORDER[f["s"]] > first)), None)
        if onset:
            out.append({"day": onset[0], "device_id": mid, "label": row["label"], "rack_id": row["rack_id"],
                        "kind": "onset", "status": onset[1]["s"], "signal": onset[1]["sig"], "component": onset[1]["w"],
                        "text": f"{row['label']} drifts from its baseline ({base:.0f} → {onset[1]['h']:.0f})"})
        reached = STATUS_ORDER[past[0][1]["s"]]
        for d, f in ((d, f) for d, f in zip(days, seq) if f):
            level = STATUS_ORDER[f["s"]]
            if level > reached:
                reached = level
                out.append({"day": d, "device_id": mid, "label": row["label"], "rack_id": row["rack_id"],
                            "kind": "projected" if f.get("p") else "status", "status": f["s"], "signal": f["sig"],
                            "component": f["w"],
                            "text": f"{row['label']} {'would reach' if f.get('p') else 'reaches'} {f['s']}"})
        return out

    @staticmethod
    def _links(devices, racks, i):
        """Devices in one rack degrading in the same way on this day: the chains the twin draws."""
        groups: dict[tuple, list] = {}
        for mid, dev in devices.items():
            f = dev["frames"][i]
            # a constant quirk (e.g. two remapped sectors since day one) is not drift: require a move off baseline
            if not f or (f["s"] == "healthy" and not f.get("p") and f["h"] > (dev["baseline"] or 100) - 2):
                continue
            for g in f["g"]:
                groups.setdefault((dev["rack_id"], g), []).append(mid)
        out = []
        for (rid, g), ids in groups.items():
            if len(ids) < 2:
                continue
            ids.sort(key=lambda m: devices[m]["slot"] or 99)
            status = worst_status(devices[m]["frames"][i]["s"] for m in ids)
            out.append({"rack_id": rid, "rack_name": racks.get(rid, rid), "group": g, "devices": ids,
                        "status": status if status != "healthy" else "watch"})
        return out

    def incidents(self):
        items = []
        for mid in self.device_ids():
            a = self.analyze(mid)
            s = self.summary(mid)
            for c in a["components"]:
                if c["status"] == "healthy":
                    continue
                items.append({"device_id": mid, "device_label": s["label"], "site_id": s["site_id"], "site_name": s["site_name"],
                              "rack_id": s["rack_id"], "rack_name": s["rack_name"], "source": s["source"],
                              "component": {k: c[k] for k in ("id", "name", "type", "status", "health", "risk_7d", "trend",
                                                               "action", "priority_score", "failure_window")},
                              "evidence": next((e for e in c["evidence"] if e["impact"] > 0), None),
                              "associations": [x["title"] for x in c["associations"]]})
        items.sort(key=lambda i: -i["component"]["priority_score"])
        patterns = [p for sid in list(self.sites) for p in self.rack_patterns(sid)]
        return {"items": items, "patterns": patterns}
