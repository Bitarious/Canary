"""DriftOps copilot: answers operator questions from model outputs (rule-based, no LLM).

Every answer is assembled from the analysis of real devices in the fleet, so it can be traced
back to the evidence shown in the 3D views. An LLM can later rephrase these grounded facts.
"""
from __future__ import annotations

import re

from . import model
from .fleet import STATUS_ORDER

STATUS_WORD = {"healthy": "No drift detected.", "watch": "Early drift detected.",
               "elevated": "Elevated drift detected.", "critical": "Critical drift detected."}
TYPE_NOUN = {"cpu": "a processor", "gpu": "the GPU", "memory": "memory", "storage": "a storage unit",
             "battery": "the battery", "cooling": "the cooling system", "power": "a power supply"}

HELP = ["Status of this rack?", "Why?", "What if I wait 7 days?", "What should I do?", "Show fleet comparison"]


def _pct(x):
    return f"{x * 100:.1f}%" if 0 < x < 0.01 else f"{x * 100:.0f}%"


def _find_device(fleet, q, site_id):
    m = re.search(r"(server|laptop)\s*([a-z0-9-]+)", q)
    if not m:
        return None
    needle = f"{m.group(1)} {m.group(2)}".lower()
    rows = fleet.summaries()
    for r in sorted(rows, key=lambda r: r["site_id"] != site_id):
        if r["label"].lower() == needle:
            return r["id"]
    return None


def _find_rack(fleet, q, site_id):
    m = re.search(r"(rack|floor)\s*0*(\d+)", q)
    if not m or site_id not in fleet.sites:
        return None
    for r in fleet.sites[site_id]["racks"]:
        if re.fullmatch(rf"(rack|floor)\s*0*{m.group(2)}", r["name"].lower()):
            return r["id"]
    return None


def _focus_component(analysis):
    return max(analysis["components"], key=lambda c: (STATUS_ORDER[c["status"]], c["priority_score"]))


def _card(fleet, device_id, comp=None):
    a = fleet.analyze(device_id)
    s = fleet.summary(device_id)
    c = comp or _focus_component(a)
    hist = s["health_history"]
    return {"device_id": device_id, "device_label": s["label"], "rack_name": s["rack_name"], "site_name": s["site_name"],
            "component": c["name"].split("·")[0].strip(), "component_type": c["type"], "status": c["status"],
            "health": round(c["health"]), "window": c["failure_window"]["label"],
            "trajectory": [round(p["health"], 1) for p in c["trajectory"]],
            "trajectory_label": f"{c['name'].split('·')[0].strip()} health · {len(hist)} runs · "
                                f"{round(c['trajectory'][0]['health'])} → {round(c['health'])}"}


def answer(fleet, question, ctx):
    q = (question or "").strip().lower()
    site_id = ctx.get("site_id") or next(iter(fleet.sites), None)
    rack_id = _find_rack(fleet, q, site_id) or ctx.get("rack_id")
    device_id = _find_device(fleet, q, site_id) or ctx.get("device_id")
    if _find_rack(fleet, q, site_id) and not _find_device(fleet, q, site_id):
        device_id = None  # an explicit rack question overrides the previous device focus

    rows = [r for r in fleet.summaries() if r["site_id"] == site_id]
    scope = [r for r in rows if r["rack_id"] == rack_id] if rack_id else rows
    if not device_id and scope:
        device_id = max(scope, key=lambda r: (STATUS_ORDER[r["status"]], r["priority"]))["id"]
    scope_name = scope[0]["rack_name"] if rack_id and scope else (fleet.sites.get(site_id, {}).get("name") or "this site")
    focus = {"site_id": site_id, "rack_id": rack_id, "device_id": device_id}
    if not device_id:
        return {"text": "There are no devices in this scope yet.", "focus": focus, "suggestions": HELP}

    a = fleet.analyze(device_id)
    s = fleet.summary(device_id)
    comp = _focus_component(a)
    comp_short = comp["name"].split("·")[0].strip()
    where = f"{s['rack_name']} → {s['label']}"

    if "why" in q:
        drivers = [e for e in comp["evidence"] if e["impact"] > 0][:3]
        text = comp["summary"]
        lst = [{"label": e["signal"], "meta": e["detail"], "status": comp["status"]} for e in drivers]
        return {"text": text, "tone": comp["status"], "list": lst, "card": _card(fleet, device_id, comp), "focus": focus,
                "suggestions": ["What if I wait 7 days?", "What should I do?", "Show fleet comparison"]}

    if "wait" in q or "delay" in q or "postpone" in q:
        m = re.search(r"(\d+)\s*(day|d\b|week|w\b)", q)
        days = int(m.group(1)) * (7 if m and m.group(2).startswith("w") else 1) if m else 7
        risk = model.cumulative_risk(comp["health"], comp["slope_per_day"], days)
        weight = comp["priority_score"] / max(1e-6, 100 * (0.6 * comp["risk_7d"] + 0.4 * (100 - comp["health"]) / 100))
        exposure = "LOW" if risk * weight < 0.04 else "MEDIUM" if risk * weight < 0.15 else "HIGH"
        rec = next((w for w in comp["wait_simulation"] if w["recommended"]), None)
        text = (f"If {comp_short} on {s['label']} is left for {days} days, the model estimates a **{_pct(risk)}** chance it "
                f"fails before maintenance (exposure **{exposure}**). "
                + (f"Latest low-risk window: **{rec['label'].lower()}**." if rec and rec["days"] < 14 else
                   "No maintenance is needed in the next two weeks."))
        lst = [{"label": w["label"], "meta": f"{_pct(w['risk'])} risk · {w['exposure']} exposure",
                "status": {"LOW": "healthy", "MEDIUM": "watch", "HIGH": "critical"}[w["exposure"]]} for w in comp["wait_simulation"]]
        return {"text": text, "tone": "critical" if exposure == "HIGH" else comp["status"], "list": lst,
                "card": _card(fleet, device_id, comp), "focus": focus,
                "suggestions": ["What should I do?", "Why?", "Show fleet comparison"]}

    if any(w in q for w in ("what should", "do first", "fix", "action", "priorit", "recommend")):
        ranked = sorted((r for r in scope if r["status"] != "healthy"), key=lambda r: -r["priority"])[:4]
        if not ranked:
            return {"text": f"Nothing in {scope_name} needs attention right now. Keep the benchmark schedule running.",
                    "tone": "healthy", "focus": focus, "suggestions": HELP}
        lst = []
        for r in ranked:
            c = _focus_component(fleet.analyze(r["id"]))
            lst.append({"label": f"{r['label']} · {c['name'].split('·')[0].strip()}", "meta": c["action"],
                        "status": c["status"], "device_id": r["id"]})
        patterns = [p for p in fleet.rack_patterns(site_id) if not rack_id or p["rack_id"] == rack_id]
        text = f"In {scope_name}, fix these first (ranked by risk × criticality × redundancy):"
        if patterns:
            text += f" Note the rack-level pattern — {patterns[0]['title'].lower()}; check shared cooling/power first."
        return {"text": text, "tone": ranked[0]["status"], "list": lst, "focus": focus,
                "suggestions": ["Why?", "What if I wait 7 days?"]}

    if any(w in q for w in ("fleet", "compar", "baseline", "peer")):
        peers = []
        for mid in fleet.device_ids():
            pa = fleet.analyze(mid)
            if pa["machine"].get("model") != a["machine"].get("model") or mid == device_id:
                continue
            pc = next((c for c in pa["components"] if c["id"] == comp["id"]), None)
            if pc:
                peers.append(pc["health"])
        if not peers:
            return {"text": "No comparable devices of the same model in the fleet yet.", "focus": focus, "suggestions": HELP}
        peers.sort()
        below = sum(1 for h in peers if h > comp["health"])
        median = peers[len(peers) // 2]
        worse = sum(1 for h in peers if h < 80)
        text = (f"{comp_short} on {s['label']} scores **{comp['health']:.0f}** against a fleet median of **{median:.0f}** "
                f"across {len(peers)} same-model devices — worse than **{below / len(peers) * 100:.0f}%** of its peers. "
                f"{worse} peer{'s' if worse != 1 else ''} show a similar issue.")
        fleet_ev = next((e for e in comp["evidence"] if e["fleet_percentile"] is not None and e["impact"] > 0), None)
        if fleet_ev:
            text += f" Its {fleet_ev['signal'].lower()} sits at the {fleet_ev['fleet_percentile']}th percentile of the reference baseline."
        return {"text": text, "tone": comp["status"], "card": _card(fleet, device_id, comp), "focus": focus,
                "suggestions": ["Why?", "What should I do?"]}

    if any(w in q for w in ("incident", "critical", "alert")):
        crit = sorted((r for r in scope if STATUS_ORDER[r["status"]] >= 2), key=lambda r: -r["priority"])
        text = f"{len(crit)} device{'s' if len(crit) != 1 else ''} in {scope_name} are elevated or critical."
        lst = [{"label": r["label"], "meta": f"{r['worst']['name']} · {r['worst']['window']}", "status": r["status"],
                "device_id": r["id"]} for r in crit[:6]]
        return {"text": text, "tone": crit[0]["status"] if crit else "healthy", "list": lst, "focus": focus, "suggestions": HELP}

    # Default: status of the rack / device / site in focus — but only for questions that are about status.
    about_status = any(w in q for w in ("status", "how ", "health", "doing", "state", "overview", "summar", "okay", "ok?"))
    if q and not about_status and not _find_rack(fleet, q, site_id) and not _find_device(fleet, q, site_id):
        return {"text": "I can only answer questions about the health of this infrastructure, grounded in the model's results: "
                        "the **status** of a site, rack or server, **why** something is flagged, **what happens if you wait** "
                        "N days, **what to fix first**, and **fleet comparisons**. Try one of the suggestions below.",
                "tone": "watch", "focus": {"site_id": site_id, "rack_id": ctx.get("rack_id"), "device_id": ctx.get("device_id")},
                "suggestions": HELP}
    drifting = [r for r in scope if r["drifting"]]
    if s["status"] == "healthy" and not drifting:
        text = f"{STATUS_WORD['healthy']} All {len(scope)} devices in {scope_name} are within normal ranges."
    else:
        verb = "failing" if s["status"] == "critical" else "trending down" if "deteriorating" in s["trend"] else "drifting"
        text = (f"**{STATUS_WORD[s['status']]}** {where} is {verb}; {TYPE_NOUN.get(comp['type'], comp['type'])} is the "
                f"strongest contributor")
        fleet_ev = next((e for e in comp["evidence"] if e["fleet_percentile"] and e["fleet_percentile"] >= 80), None)
        text += " and is diverging from the fleet baseline." if fleet_ev else "."
        pats = [p for p in fleet.rack_patterns(site_id) if p["rack_id"] == s["rack_id"]]
        if pats:
            text += f" {pats[0]['text']}"
        elif len(drifting) > 1:
            text += f" {len(drifting)} devices in {scope_name} are drifting."
    return {"text": text, "tone": s["status"], "card": _card(fleet, device_id, comp), "focus": focus,
            "suggestions": ["Why?", "What if I wait 7 days?", "What should I do?", "Show fleet comparison"]}
