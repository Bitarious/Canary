"""Fleet registry: devices grouped into sites and racks, with cached model results."""
from __future__ import annotations

import json
import re
import threading
import uuid
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
        history, overall, analysis = [], [], None
        for run in runs:
            analysis = model.analyze(run, history)
            history.append(model.history_entry(run, analysis))
            overall.append({"t": analysis["collected_at"], "health": analysis["overall"]["health"]})
        slope, accel, span = model._trajectory(overall)
        analysis["source"] = runs[-1].get("source", "agent")
        analysis["history_overall"] = overall
        analysis["overall"]["trend"] = model._trend_label(slope, span, len(overall))
        analysis["overall"]["slope_per_day"] = round(slope, 2)
        with self._lock:
            self._cache[mid] = (key, analysis)
        return analysis

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
