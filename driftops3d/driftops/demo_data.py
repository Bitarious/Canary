"""Synthetic multi-site demo fleet (every run is labelled source="demo").

Most devices are healthy with realistic noise; a handful carry a degradation profile
(failing disk, rack-wide thermal drift, ECC growth, PSU drift, worn batteries, throttling laptops)
so the digital twin has something to find.
"""
from __future__ import annotations

import random
import zlib
from datetime import datetime, timedelta, timezone

N = 10  # samples per benchmark series

SITES = [
    {"id": "site-a", "name": "Site A", "region": "EU-CENTRAL · Zurich", "kind": "datacenter",
     "racks": [{"id": f"r0{i + 1}", "name": f"Rack 0{i + 1}", "row": 0 if i < 4 else 1, "col": i if i < 4 else i - 4}
               for i in range(7)]},
    {"id": "site-b", "name": "Site B", "region": "US-EAST · Ashburn", "kind": "datacenter",
     "racks": [{"id": f"r0{i + 1}", "name": f"Rack 0{i + 1}", "row": i // 3, "col": i % 3} for i in range(6)]},
    {"id": "hq", "name": "HQ laptop fleet", "region": "EU-CENTRAL · Zurich HQ", "kind": "office",
     "racks": [{"id": "f1", "name": "Floor 1", "row": 0, "col": 0}, {"id": "f2", "name": "Floor 2", "row": 0, "col": 1},
               {"id": "it", "name": "IT bench", "row": 0, "col": 2}]},
]

# (site, rack, slot) -> degradation profile. Everything else is healthy.
PROFILES = {
    # Site A, Rack 06: shared cooling problem across the rack, one drive about to fail on top of it.
    **{("site-a", "r06", s): {"thermal": v} for s, v in ((2, 0.55), (3, 0.75), (5, 0.9), (6, 0.6), (8, 0.45), (11, 0.5))},
    ("site-a", "r06", 9): {"thermal": 0.8, "disk": 1.0},
    ("site-a", "r04", 5): {"memory": 1.0},
    ("site-a", "r03", 4): {"disk": 0.06},
    ("site-a", "r02", 7): {"psu": 0.8},
    ("site-a", "r01", 10): {"memory": 0.3},
    ("site-b", "r02", 8): {"thermal": 0.85},
    ("site-b", "r05", 3): {"disk": 0.3},
    ("hq", "f1", 3): {"thermal": 1.0},
    ("hq", "f1", 7): {"ssd": 1.0},
    ("hq", "f2", 5): {"battery": 1.0},
    ("hq", "it", 2): {"thermal": 0.8, "battery": 1.0},
}

SERVERS_PER_RACK = {"site-a": 12, "site-b": 10}
LAPTOPS_PER_GROUP = 8


def _seed(*parts):
    return zlib.crc32("|".join(map(str, parts)).encode())


def _series(rng, start, end, noise=0.02):
    return [round((start + (end - start) * i / (N - 1)) * (1 + rng.gauss(0, noise)), 3) for i in range(N)]


def _lerp(a, b, k):
    return a + (b - a) * k


def _server_run(ident, p, day, days, t):
    base = random.Random(_seed(ident["id"]))          # stable per-device characteristics
    rng = random.Random(_seed(ident["id"], day))        # per-run noise
    k = day / (days - 1)
    thermal = p.get("thermal", 0) * k ** 1.4
    disk = p.get("disk", 0) * k ** 2.2
    mem = p.get("memory", 0) * k ** 1.8
    psu = p.get("psu", 0) * k ** 1.6
    fan_rpm = base.uniform(9300, 10200) * (1 - 0.38 * thermal)
    cpu_peak = base.uniform(62, 72) + 18 * thermal
    quirk_disk = base.randrange(4) if base.random() < 0.06 else None

    comps = []
    for i in range(2):
        comps.append({"id": f"cpu{i}", "type": "cpu", "name": f"CPU {i} · Xeon Gold 6338",
                      "static": {"hardware_errors_30d": 0},
                      "series": {"temp_c": _series(rng, cpu_peak - 12, cpu_peak - i * 2, 0.015),
                                 "bench_ops": _series(rng, 1.0e6, 1.0e6 * (1 - 0.12 * thermal), 0.01),
                                 "load_pct": _series(rng, 70, 80, 0.03)}})
    comps.append({"id": "memory", "type": "memory", "name": "Memory · 12× 32 GB DDR4 ECC",
                  "static": {"ecc_corrected": round(380 * mem), "ecc_uncorrected": 0},
                  "series": {"used_pct": _series(rng, 58, 62), "bandwidth_gbps": _series(rng, 14, 14, 0.03)}})
    failing = 3
    for d in range(4):
        f = disk if d == failing else 0
        realloc = round(90 * f) + (2 if d == quirk_disk else 0)
        smart = {"reallocated_sectors": realloc, "pending_sectors": round(15 * f),
                 "uncorrectable_errors": round(4 * f), "crc_errors": 0,
                 "power_on_hours": base.randrange(12000, 36000) + day * 24,
                 "temperature_c": round(_lerp(36, 42, rng.random() * 0.3) + 10 * f + 9 * thermal, 1)}
        lat = 6 + 5 * f
        comps.append({
            "id": f"disk{d}", "type": "storage", "name": f"Disk {d} · 8 TB HDD (bay {d})",
            "static": {"media": "hdd", "redundancy": "none" if f else "raid6"}, "smart": smart,
            "series": {"write_mbps": _series(rng, 210, 210 * (1 - 0.3 * f), 0.04),
                       "latency_ms": _series(rng, 6, lat, 0.08),
                       "latency_p95_ms": _series(rng, lat * (2.4 + 7 * f), lat * (2.5 + 8 * f), 0.1)}})
    comps.append({"id": "fans", "type": "cooling", "name": "Fan wall · 6× 60 mm", "static": {"rated_rpm": 10000},
                  "series": {"rpm": _series(rng, fan_rpm, fan_rpm * 0.99, 0.01)}})
    for i in range(2):
        v = 12.05 - (0.9 * psu if i == 0 else 0)
        comps.append({"id": f"psu{i}", "type": "power", "name": f"PSU {i} · 1100 W",
                      "static": {"nominal_v": 12.0, "redundancy": "n+1"},
                      "series": {"voltage_v": _series(rng, v, v - 0.02, 0.002 + (0.012 * psu if i == 0 else 0)),
                                 "temp_c": _series(rng, 40 + 8 * thermal, 43 + 10 * thermal)}})
    return comps


def _laptop_run(ident, p, day, days, t):
    base = random.Random(_seed(ident["id"]))
    rng = random.Random(_seed(ident["id"], day))
    k = day / max(1, days - 1)
    thermal = p.get("thermal", 0) * k ** 1.3
    wear = base.uniform(0.03, 0.14) + p.get("battery", 0) * _lerp(0.25, 0.33, k)
    peak = base.uniform(70, 80) + 20 * thermal
    drop = 0.02 + 0.24 * thermal
    ssd_used = round(base.uniform(3, 30) if not p.get("ssd") else _lerp(84, 97, k))
    mem = base.uniform(45, 78)
    return [
        {"id": "cpu0", "type": "cpu", "name": "CPU · 8-core mobile", "static": {"hardware_errors_30d": 0},
         "series": {"temp_c": _series(rng, peak - 20, peak, 0.015),
                    "bench_ops": _series(rng, 5.2e5, 5.2e5 * (1 - drop), 0.015),
                    "freq_mhz": _series(rng, 4200, 4200 * (1 - drop * 0.8), 0.01)}},
        {"id": "gpu0", "type": "gpu", "name": "GPU · integrated", "static": {},
         "series": {"temp_c": _series(rng, peak - 22, peak - 8, 0.02)}},
        {"id": "memory", "type": "memory", "name": "Memory · 16 GB LPDDR5", "static": {},
         "series": {"used_pct": _series(rng, mem - 2, mem + 2), "bandwidth_gbps": _series(rng, 9.5, 9.4)}},
        {"id": "ssd0", "type": "storage", "name": "SSD · 512 GB NVMe", "static": {"media": "ssd", "event_errors_30d": 0},
         "smart": {"percentage_used": ssd_used, "media_errors": 0, "available_spare": 100, "temperature_c": round(38 + 8 * thermal)},
         "series": {"write_mbps": _series(rng, 820, 800, 0.05), "latency_ms": _series(rng, 0.9, 1.0, 0.1),
                    "latency_p95_ms": _series(rng, 2.4, 2.6, 0.1)}},
        {"id": "battery", "type": "battery", "name": "Battery · 57 Wh Li-ion",
         "static": {"design_capacity_mwh": 57000, "full_charge_capacity_mwh": round(57000 * (1 - wear)),
                    "cycle_count": base.randrange(40, 420) + (220 if p.get("battery") else 0) + day * 3},
         "series": {"percent": _series(rng, 96, 88)}},
        {"id": "cooling", "type": "cooling", "name": "Cooling · dual fan + heat pipes", "static": {}, "series": {}},
    ]


def _runs(ident, profile, builder, days, step_days, now):
    for d in range(days):
        t = now - timedelta(days=step_days * (days - 1 - d), hours=2)
        yield {"schema": "driftops.telemetry/v1", "source": "demo", "collected_at": t.isoformat(),
               "machine": ident, "components": builder(ident, profile, d, days, t)}


def demo_fleet():
    """Yield (machine_id, [runs oldest first]) for every demo device."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for site in SITES:
        for rack in site["racks"]:
            if site["kind"] == "datacenter":
                rack_no = rack["id"][1:]
                for slot in range(1, SERVERS_PER_RACK[site["id"]] + 1):
                    num = f"{int(rack_no)}{slot:02d}"
                    mid = f"{site['id']}-{num}"
                    ident = {"id": mid, "hostname": f"{site['id']}-{rack['id']}-u{slot:02d}", "label": f"Server {num}",
                             "form_factor": "server", "vendor": "Demo", "model": "2U storage node", "os": "Ubuntu 22.04",
                             "role": "database" if slot <= 4 else "compute", "criticality": "high" if slot <= 4 else "medium",
                             "site": site["id"], "rack": rack["id"], "slot": slot}
                    profile = PROFILES.get((site["id"], rack["id"], slot), {})
                    yield mid, list(_runs(ident, profile, _server_run, 14, 1, now))
            else:
                for slot in range(1, LAPTOPS_PER_GROUP + 1):
                    mid = f"hq-{rack['id']}-{slot:02d}"
                    ident = {"id": mid, "hostname": mid, "label": f"Laptop {rack['id'].upper()}-{slot:02d}",
                             "form_factor": "laptop", "vendor": "Demo", "model": "14\" business laptop", "os": "Windows 11",
                             "role": "employee laptop", "criticality": "medium",
                             "site": site["id"], "rack": rack["id"], "slot": slot}
                    profile = PROFILES.get((site["id"], rack["id"], slot), {})
                    yield mid, list(_runs(ident, profile, _laptop_run, 7, 4, now))
