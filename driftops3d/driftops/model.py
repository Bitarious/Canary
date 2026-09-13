"""DriftOps component-health model (baseline v0).

Contract
--------
analyze(run, history) -> analysis dict rendered by the 3D GUI

* ``run`` is one telemetry document (schema ``driftops.telemetry/v1``, see README).
* ``history`` is a list of earlier results for the same machine, oldest first:
  ``{"t": iso-timestamp, "health": {component_id: float}, "metrics": {component_id: {...}}}``.
  ``history_entry(run, analysis)`` builds one.

The scoring below is transparent statistics + rules, so the GUI has a working backend today.
The temporal language model replaces ``_score_component`` / ``_narrative`` and keeps the same
output contract (health, trajectory, risk, evidence, action, wait simulation).
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone

MODEL_NAME = "driftops-baseline-v0"

STAGES = [
    (90, "Healthy"),
    (80, "Slight degradation"),
    (65, "Abnormal trajectory"),
    (45, "Elevated risk"),
    (20, "Critical degradation"),
    (0, "Failure imminent"),
]

# How much a failure of each component type hurts the machine (data loss, outage, ...).
TYPE_WEIGHT = {"storage": 1.0, "power": 0.9, "memory": 0.8, "cpu": 0.8, "cooling": 0.75,
               "gpu": 0.6, "battery": 0.5}

TYPE_NOUN = {"cpu": "processor", "gpu": "graphics processor", "memory": "memory",
             "storage": "drive", "battery": "battery", "cooling": "cooling system",
             "power": "power supply"}

SIGNAL_META = {
    "temp_c": ("Temperature", "°C"),
    "bench_ops": ("Compute throughput", "ops/s"),
    "freq_mhz": ("Clock frequency", "MHz"),
    "load_pct": ("Load", "%"),
    "write_mbps": ("Sequential write", "MB/s"),
    "read_mbps": ("Sequential read", "MB/s"),
    "latency_ms": ("4K write latency", "ms"),
    "latency_p95_ms": ("4K latency p95", "ms"),
    "used_pct": ("Memory in use", "%"),
    "swap_pct": ("Swap in use", "%"),
    "bandwidth_gbps": ("Memory bandwidth", "GB/s"),
    "percent": ("Charge", "%"),
    "rpm": ("Fan speed", "RPM"),
    "util_pct": ("Utilisation", "%"),
    "power_w": ("Power draw", "W"),
    "voltage_v": ("Output voltage", "V"),
}

# Counters whose growth between runs is itself evidence of drift.
GROWTH_KEYS = {
    "reallocated_sectors": ("Reallocated sectors", 1.0),
    "pending_sectors": ("Pending sectors", 1.0),
    "media_errors": ("Media errors", 1.0),
    "uncorrectable_errors": ("Uncorrectable errors", 1.0),
    "ecc_corrected": ("Corrected ECC errors", 0.6),
    "hardware_errors": ("Hardware error events", 0.8),
    "wear_pct": ("Capacity wear", 0.5),
    "throttle_drop_pct": ("Throttling under load", 0.5),
}


# ----------------------------------------------------------------------------- statistics

def _num(xs):
    return [float(x) for x in (xs or []) if isinstance(x, (int, float)) and math.isfinite(x)]


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def rel_change(xs):
    """Relative change between the first and last third of a series."""
    if len(xs) < 4:
        return 0.0
    k = max(1, len(xs) // 3)
    a, b = _mean(xs[:k]), _mean(xs[-k:])
    return (b - a) / abs(a) if a else 0.0


def cv(xs):
    if len(xs) < 3:
        return 0.0
    m = _mean(xs)
    return statistics.pstdev(xs) / abs(m) if m else 0.0


def quantile(xs, q):
    s = sorted(xs)
    if not s:
        return 0.0
    i = (len(s) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def fleet_percentile(value, median, spread):
    """Position of ``value`` against an (illustrative) fleet reference distribution."""
    return max(1, min(99, round(100 / (1 + math.exp(-(value - median) / spread)))))


def _parse_t(t):
    try:
        d = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _log2p(x):
    return math.log2(1 + max(0, x))


# ----------------------------------------------------------------------------- findings

class _Findings:
    def __init__(self):
        self.penalty = 0.0
        self.evidence = []
        self.signals = 0
        self.metrics = {}

    def add(self, points, signal, direction, detail, series=None, fleet=None):
        self.penalty += points
        self.evidence.append({"signal": signal, "direction": direction, "detail": detail,
                              "impact": round(points, 1), "series": series,
                              "fleet_percentile": fleet})

    def note(self, signal, detail, series=None, fleet=None):
        self.add(0, signal, "flat", detail, series, fleet)


def _cpu(c, ctx):
    f, s, st = _Findings(), c.get("series", {}), c.get("static", {})
    temps, score, freq = _num(s.get("temp_c")), _num(s.get("bench_ops")), _num(s.get("freq_mhz"))
    if temps:
        f.signals += 1
        peak = max(temps)
        fp = fleet_percentile(peak, 78, 6)
        if peak >= 95:
            f.add(22, "Temperature", "up", f"Peaks at {peak:.0f} °C under load — at the thermal limit.", "temp_c", fp)
        elif peak >= 88:
            f.add(12, "Temperature", "up", f"Peaks at {peak:.0f} °C under load — little thermal headroom.", "temp_c", fp)
        elif peak >= 80:
            f.add(4, "Temperature", "up", f"Runs warm under load ({peak:.0f} °C peak).", "temp_c", fp)
        else:
            f.note("Temperature", f"Peak {peak:.0f} °C under load — within normal range.", "temp_c", fp)
        rise = rel_change(temps)
        if rise > 0.12 and peak >= 75:
            f.add(6, "Temperature drift", "up",
                  f"Temperature climbed {rise * 100:.0f}% during the sustained run without plateauing.", "temp_c")
    if score:
        f.signals += 1
        drop = -rel_change(score)
        f.metrics["throttle_drop_pct"] = round(max(0.0, drop) * 100, 1)
        if drop >= 0.08:
            f.add(min(28, drop * 130), "Sustained performance", "down",
                  f"Throughput fell {drop * 100:.0f}% from the start to the end of the stress run — "
                  "consistent with thermal throttling.", "bench_ops")
        else:
            f.note("Sustained performance", f"Throughput held steady under load ({drop * -100:+.0f}%).", "bench_ops")
        v = cv(score)
        if v > 0.10:
            f.add(min(10, v * 50), "Performance stability", "up",
                  f"Benchmark results vary strongly between rounds (CV {v * 100:.0f}%).", "bench_ops")
    if len(freq) >= 4 and rel_change(freq) < -0.10:
        f.signals += 1
        f.add(8, "Clock frequency", "down",
              f"Clock frequency dropped {-rel_change(freq) * 100:.0f}% while load stayed high.", "freq_mhz")
    errs = st.get("hardware_errors_30d")
    if errs is not None:
        f.signals += 1
        f.metrics["hardware_errors"] = errs
        if errs > 0:
            f.add(min(30, 10 + 5 * _log2p(errs)), "Hardware error events", "up",
                  f"{errs} machine-check / WHEA hardware errors logged in the last 30 days.")
    return f


def smart_from_drive_stats(row):
    """Readable counters from a Backblaze-schema row (``smart_<id>_raw``); vendor bit-packing is masked off."""
    row = row or {}

    def raw(aid, mask=None):
        v = row.get(f"smart_{aid}_raw")
        return None if not isinstance(v, (int, float)) else (int(v) & mask if mask else v)
    uncorrectable = [v for v in (raw(187), raw(198)) if v is not None]
    derived = {"reallocated_sectors": raw(5), "pending_sectors": raw(197), "crc_errors": raw(199),
               "uncorrectable_errors": max(uncorrectable) if uncorrectable else None,
               "spin_retries": raw(10), "power_on_hours": raw(9, 0xFFFFFFFF),
               "temperature_c": raw(194, 0xFF) or None}  # low byte = current °C; 0 means not reported
    return {k: v for k, v in derived.items() if v is not None}


def _storage(c, ctx):
    f, s, st = _Findings(), c.get("series", {}), c.get("static", {})
    smart = {**smart_from_drive_stats(c.get("drive_stats")), **(c.get("smart") or {})}

    def counter(key, label, base, scale, cap, detail, fleet=(0.5, 2)):
        v = smart.get(key)
        if v is None:
            return
        f.signals += 1
        f.metrics[key] = v
        if v > 0:
            f.add(min(cap, base + scale * _log2p(v)), label, "up", detail.format(v=v),
                  fleet=fleet_percentile(v, *fleet))
        else:
            f.note(label, f"No {label.lower()} recorded.")

    counter("reallocated_sectors", "Reallocated sectors", 10, 4, 38,
            "{v} sectors have been remapped to spare area — the surface is failing to hold data.")
    counter("pending_sectors", "Pending sectors", 6, 4, 25,
            "{v} unstable sectors are waiting to be remapped.")
    counter("uncorrectable_errors", "Uncorrectable errors", 12, 4, 30,
            "{v} read errors could not be corrected by ECC.")
    counter("media_errors", "Media errors", 12, 4, 30,
            "{v} NVMe media/data-integrity errors reported by the controller.")
    spin = smart.get("spin_retries")
    if spin:
        f.add(min(25, 10 + 4 * _log2p(spin)), "Spin retries", "up",
              f"The spindle needed {spin} retries to reach speed — the motor or bearings are weakening.")
    crc = smart.get("crc_errors")
    if crc:
        f.add(min(10, 3 + 2 * _log2p(crc)), "Interface CRC errors", "up",
              f"{crc} transfer CRC errors — often the cable/connector rather than the media.")
    used = smart.get("percentage_used", st.get("wear_pct"))
    if used is not None:
        f.signals += 1
        f.metrics["wear_pct"] = used
        if used >= 100:
            f.add(35, "Endurance used", "up", f"{used:.0f}% of rated write endurance consumed — past its design life.")
        elif used >= 80:
            f.add(18, "Endurance used", "up", f"{used:.0f}% of rated write endurance consumed.")
        elif used >= 50:
            f.add(6, "Endurance used", "up", f"{used:.0f}% of rated write endurance consumed.")
        else:
            f.note("Endurance used", f"{used:.0f}% of rated write endurance consumed.")
    spare = smart.get("available_spare")
    if spare is not None and spare < max(20, smart.get("available_spare_threshold", 10)):
        f.add(20, "Spare capacity", "down", f"Only {spare}% spare blocks remain.")
    temp = smart.get("temperature_c")
    if temp is not None:
        f.signals += 1
        fp = fleet_percentile(temp, 40, 5)
        if temp >= 60:
            f.add(10, "Drive temperature", "up", f"Drive at {temp:.0f} °C — above the recommended range.", fleet=fp)
        elif temp >= 50:
            f.add(4, "Drive temperature", "up", f"Drive at {temp:.0f} °C — warm.", fleet=fp)
    for key, label in (("read_errors_total", "Read errors"), ("write_errors_total", "Write errors")):
        v = smart.get(key)
        if v:
            f.add(min(20, 5 + 3 * _log2p(v)), label, "up", f"{v} {label.lower()} in the drive's reliability counters.")
    ev = st.get("event_errors_30d")
    if ev is not None:
        f.signals += 1
        if ev > 0:
            f.add(min(20, 5 + 3 * _log2p(ev)), "Disk error events", "up",
                  f"{ev} disk/storage errors in the OS event log over the last 30 days.")
    poh = smart.get("power_on_hours")
    if poh and poh > 40000:
        f.add(6, "Power-on hours", "up", f"{poh:,} power-on hours (~{poh / 8760:.1f} years).")

    write, lat, p95 = _num(s.get("write_mbps")), _num(s.get("latency_ms")), _num(s.get("latency_p95_ms"))
    if write:
        f.signals += 1
        d = rel_change(write)
        if d < -0.25:
            f.add(8, "Write throughput", "down", f"Sequential write speed fell {-d * 100:.0f}% during the run.", "write_mbps")
        else:
            f.note("Write throughput", f"Median {statistics.median(write):.0f} MB/s, stable across rounds.", "write_mbps")
    if lat:
        f.signals += 1
        med = statistics.median(lat)
        tail = quantile(p95, 0.5) if p95 else quantile(lat, 0.95)
        ratio = tail / med if med else 0
        if ratio > 6:
            f.add(min(14, ratio), "Latency variance", "up",
                  f"Tail latency is {ratio:.0f}× the median ({tail:.1f} ms vs {med:.1f} ms) — I/O retries or stalls.",
                  "latency_p95_ms" if p95 else "latency_ms", fleet_percentile(ratio, 3, 1.5))
        if rel_change(lat) > 0.35:
            f.add(8, "Latency trend", "up", f"Write latency rose {rel_change(lat) * 100:.0f}% within the run.", "latency_ms")
    return f


def _memory(c, ctx):
    f, s, st = _Findings(), c.get("series", {}), c.get("static", {})
    used, swap, bw = _num(s.get("used_pct")), _num(s.get("swap_pct")), _num(s.get("bandwidth_gbps"))
    if used:
        f.signals += 1
        m = statistics.median(used)
        if m >= 90:
            f.add(12, "Memory pressure", "up", f"{m:.0f}% of RAM in use — the system is paging.", "used_pct")
        elif m >= 80:
            f.add(5, "Memory pressure", "up", f"{m:.0f}% of RAM in use during the benchmark.", "used_pct")
        else:
            f.note("Memory pressure", f"{m:.0f}% of RAM in use.", "used_pct")
    if swap and statistics.median(swap) >= 50:
        f.add(5, "Swap usage", "up", f"{statistics.median(swap):.0f}% of swap in use.", "swap_pct")
    if bw:
        f.signals += 1
        v, d = cv(bw), rel_change(bw)
        if v > 0.15:
            f.add(6, "Bandwidth stability", "up", f"Memory copy speed is unstable across rounds (CV {v * 100:.0f}%).", "bandwidth_gbps")
        elif d < -0.15:
            f.add(6, "Memory bandwidth", "down", f"Memory copy speed fell {-d * 100:.0f}% during the run.", "bandwidth_gbps")
        else:
            f.note("Memory bandwidth", f"{statistics.median(bw):.1f} GB/s, stable.", "bandwidth_gbps")
    ce, ue = st.get("ecc_corrected"), st.get("ecc_uncorrected")
    if ce is not None:
        f.signals += 1
        f.metrics["ecc_corrected"] = ce
        if ce > 0:
            f.add(min(24, 6 + 3 * _log2p(ce)), "Corrected ECC errors", "up",
                  f"{ce} corrected memory errors — a DIMM is starting to lose bits.", fleet=fleet_percentile(ce, 1, 3))
    if ue:
        f.add(40, "Uncorrectable ECC errors", "up", f"{ue} uncorrectable memory errors.")
    return f


def _battery(c, ctx):
    f, st = _Findings(), c.get("static", {})
    design, full, cycles = st.get("design_capacity_mwh"), st.get("full_charge_capacity_mwh"), st.get("cycle_count")
    if design and full:
        f.signals += 1
        wear = max(0.0, 1 - full / design)
        f.metrics["wear_pct"] = round(wear * 100, 1)
        detail = f"Holds {full / 1000:.1f} Wh of its {design / 1000:.1f} Wh design capacity ({wear * 100:.0f}% wear)."
        fp = fleet_percentile(wear * 100, 15, 7)
        if wear >= 0.40:
            f.add(38, "Capacity wear", "down", detail, fleet=fp)
        elif wear >= 0.25:
            f.add(20, "Capacity wear", "down", detail, fleet=fp)
        elif wear >= 0.15:
            f.add(8, "Capacity wear", "down", detail, fleet=fp)
        else:
            f.note("Capacity wear", detail, fleet=fp)
    if cycles:
        f.signals += 1
        if cycles > 800:
            f.add(10, "Charge cycles", "up", f"{cycles} charge cycles — beyond typical rated life.")
        elif cycles > 500:
            f.add(5, "Charge cycles", "up", f"{cycles} charge cycles.")
        else:
            f.note("Charge cycles", f"{cycles} charge cycles.")
    return f


def _cooling(c, ctx):
    f, s, st = _Findings(), c.get("series", {}), c.get("static", {})
    rpm = _num(s.get("rpm"))
    peak = ctx.get("cpu_temp_peak")
    if rpm:
        f.signals += 1
        rc = rel_change(rpm)
        med = statistics.median(rpm)
        rated = st.get("rated_rpm")
        if rated and med < 0.75 * rated:
            f.add(min(26, (1 - med / rated) * 60), "Fan speed", "down",
                  f"Fans spin at {med:,.0f} RPM, {100 - med / rated * 100:.0f}% below their {rated:,} RPM rating — "
                  "worn bearings or obstruction.", "rpm", fleet_percentile(1 - med / rated, 0.1, 0.06))
        elif rc < -0.10:
            f.add(min(20, -rc * 80), "Fan speed", "down", f"Fan speed fell {-rc * 100:.0f}% during the run.", "rpm")
        else:
            f.note("Fan speed", f"Median {med:,.0f} RPM.", "rpm")
        if peak and peak >= 85 and rc <= 0.05:
            f.add(10, "Fan response", "flat",
                  f"CPU reached {peak:.0f} °C but fan speed did not rise — cooling is not responding to load.", "rpm")
    else:
        drop = ctx.get("cpu_throttle_drop", 0)
        if peak and peak >= 90:
            f.signals += 1
            f.add(14, "Thermal headroom", "down",
                  f"No fan telemetry exposed, but the CPU peaks at {peak:.0f} °C — consistent with dust, dried "
                  "thermal paste or blocked vents.")
        elif drop >= 0.12:
            f.signals += 1
            f.add(min(18, drop * 70), "Thermal headroom", "down",
                  f"No fan telemetry exposed, but the CPU loses {drop * 100:.0f}% throughput under sustained load, "
                  "which usually points at insufficient cooling.")
        elif peak is not None or ctx.get("cpu_has_bench"):
            f.signals += 1
            f.note("Thermal headroom", "No fan telemetry exposed; CPU thermals and sustained performance look normal.")
    return f


def _gpu(c, ctx):
    f, s, st = _Findings(), c.get("series", {}), c.get("static", {})
    temps, power = _num(s.get("temp_c")), _num(s.get("power_w"))
    if temps:
        f.signals += 1
        peak = max(temps)
        fp = fleet_percentile(peak, 72, 6)
        if peak >= 90:
            f.add(16, "GPU temperature", "up", f"GPU peaks at {peak:.0f} °C.", "temp_c", fp)
        elif peak >= 83:
            f.add(6, "GPU temperature", "up", f"GPU runs warm ({peak:.0f} °C peak).", "temp_c", fp)
        else:
            f.note("GPU temperature", f"Peak {peak:.0f} °C.", "temp_c", fp)
    thr = st.get("throttle_events")
    if thr:
        f.add(min(14, 4 + 2 * _log2p(thr)), "GPU throttling", "up", f"Driver reported thermal/power throttling in {thr} samples.")
    if len(power) >= 4 and cv(power) > 0.25 and _mean(power) > 20:
        f.add(6, "Power stability", "up", f"Power draw fluctuates strongly (CV {cv(power) * 100:.0f}%).", "power_w")
    ce = st.get("ecc_corrected")
    if ce:
        f.metrics["ecc_corrected"] = ce
        f.add(min(22, 6 + 3 * _log2p(ce)), "VRAM ECC errors", "up", f"{ce} corrected VRAM errors.")
    return f


def _power(c, ctx):
    f, s, st = _Findings(), c.get("series", {}), c.get("static", {})
    volt = _num(s.get("voltage_v"))
    if volt:
        f.signals += 1
        nominal = st.get("nominal_v", 12.0)
        dev = max(abs(v - nominal) for v in volt) / nominal
        ripple = cv(volt)
        if dev > 0.05 or ripple > 0.02:
            f.add(min(30, dev * 300 + ripple * 400), "Rail stability", "up",
                  f"12 V rail deviates up to {dev * 100:.1f}% from nominal (ripple CV {ripple * 100:.1f}%).", "voltage_v")
        else:
            f.note("Rail stability", f"Rail within {dev * 100:.1f}% of nominal.", "voltage_v")
    temps = _num(s.get("temp_c"))
    if temps:
        f.signals += 1
        if max(temps) >= 60:
            f.add(8, "PSU temperature", "up", f"PSU reaches {max(temps):.0f} °C.", "temp_c")
    return f


SCORERS = {"cpu": _cpu, "storage": _storage, "memory": _memory, "battery": _battery,
           "cooling": _cooling, "gpu": _gpu, "power": _power}


def _context(run):
    ctx = {}
    for c in run.get("components", []):
        if c.get("type") == "cpu":
            temps = _num(c.get("series", {}).get("temp_c"))
            bench = _num(c.get("series", {}).get("bench_ops"))
            if temps:
                ctx["cpu_temp_peak"] = max(ctx.get("cpu_temp_peak", 0), max(temps))
            if bench:
                ctx["cpu_has_bench"] = True
                ctx["cpu_throttle_drop"] = max(ctx.get("cpu_throttle_drop", 0), -rel_change(bench))
    return ctx


def _score_component(c, ctx):
    scorer = SCORERS.get(c.get("type"))
    return scorer(c, ctx) if scorer else _Findings()


# ----------------------------------------------------------------------------- temporal logic

def _trajectory(points):
    """Slope (health points/day), acceleration flag and span in days."""
    if len(points) < 3:
        return 0.0, False, 0.0
    t0 = _parse_t(points[0]["t"])
    xs = [(_parse_t(p["t"]) - t0).total_seconds() / 86400 for p in points]
    ys = [p["health"] for p in points]
    span = xs[-1] - xs[0]
    if span < 0.5:
        return 0.0, False, span

    def fit(x, y):
        if len(x) < 2:
            return 0.0
        mx, my = _mean(x), _mean(y)
        den = sum((a - mx) ** 2 for a in x)
        return sum((a - mx) * (b - my) for a, b in zip(x, y)) / den if den else 0.0

    recent = slice(-min(len(xs), 10), None)
    slope = fit(xs[recent], ys[recent])
    half = len(xs) // 2
    early, late = fit(xs[:half + 1], ys[:half + 1]), fit(xs[half:], ys[half:])
    accelerating = late < -1.0 and late < 1.5 * min(early, -0.3)
    return slope, accelerating, span


def _hazard(health):
    x = (100 - max(0.0, health)) / 100
    return 0.0004 + 0.35 * x ** 3  # per day


def cumulative_risk(health, slope, days):
    """P(failure within ``days``), assuming the current decline continues (improvement is ignored)."""
    decline = min(0.0, slope)
    survival, t, step = 1.0, 0.0, 0.25
    while t < days - 1e-9:
        dt = min(step, days - t)
        survival *= math.exp(-_hazard(health + decline * (t + dt / 2)) * dt)
        t += dt
    return 1 - survival


def _failure_window(health, slope):
    lo = hi = None
    decline, survival, day = min(0.0, slope), 1.0, 0.0
    while day < 365:  # one incremental pass over the survival curve
        dt = 0.5 if day < 30 else 5.0
        survival *= math.exp(-_hazard(health + decline * (day + dt / 2)) * dt)
        day += dt
        r = 1 - survival
        if lo is None and r >= 0.25:
            lo = day
        if r >= 0.75:
            hi = day
            break
    if lo is None:
        return {"low_days": None, "high_days": None, "label": "> 1 year"}

    if hi is None:
        label = f"{lo:.0f}+ days" if lo < 14 else f"{lo / 7:.0f}+ weeks"
    elif hi < 14:
        label = f"~{max(1, round(lo))}–{max(2, round(hi))} days"
    else:
        label = f"~{max(1, round(lo / 7))}–{max(2, round(hi / 7))} weeks"
    return {"low_days": lo, "high_days": hi, "label": label}


def stage_for(health):
    return next(name for thr, name in STAGES if health >= thr)


def status_for(health):
    if health >= 80:
        return "healthy"
    if health >= 65:
        return "watch"
    if health >= 45:
        return "elevated"
    return "critical"


def _trend_label(slope, span, n_points):
    if n_points < 3 or span < 0.5:
        return "baseline"
    if slope <= -2:
        return "deteriorating"
    if slope <= -0.5:
        return "slowly deteriorating"
    if slope >= 0.5:
        return "improving"
    return "stable"


def _action(c, status, evidence):
    kind, name = c.get("type"), c.get("name", "component")
    top = evidence[0]["signal"] if evidence else ""
    if status == "healthy":
        return "No action needed. Re-run the benchmark periodically to keep the trajectory up to date."
    if status == "watch":
        return "Keep monitoring: re-run the benchmark in 3–7 days to confirm whether the trend continues."
    urgent = status == "critical"
    table = {
        "storage": ("Back up now and replace this drive in the next maintenance window."
                    if urgent else "Verify backups, run an extended SMART self-test and schedule a replacement."),
        "cpu": ("Service the cooling path now (clean heatsink and fans, renew thermal paste); the CPU is "
                "throttling hard." if urgent else
                "Clean vents and fans and renew thermal paste; re-benchmark to confirm throttling is gone."),
        "cooling": ("Replace or service the fan assembly; cooling is limiting the rest of the machine."
                    if urgent else "Clean dust from fans and vents and check fan bearings for noise."),
        "memory": ("Run a full memory diagnostic and replace the failing module."
                   if "ECC" in top or urgent else "Reduce memory pressure (close workloads) or add RAM."),
        "battery": ("Replace the battery; heavy wear shortens runtime and raises the risk of swelling."
                    if urgent else "Plan a battery replacement; avoid keeping it at 100% on the charger."),
        "gpu": ("Service GPU cooling and check for driver-reported errors; reduce sustained load until fixed."
                if urgent else "Clean GPU heatsink and check thermal paste/pads."),
        "power": ("Move load to the redundant PSU and replace this unit."
                  if urgent else "Inspect the PSU and schedule a swap in the next window."),
    }
    return table.get(kind, f"Inspect {name} in the next maintenance window.")


def _narrative(c, health, stage, trend, slope, span, accelerating, evidence, associations):
    name = c.get("name") or TYPE_NOUN.get(c.get("type"), "component")
    parts = [f"{name} scores {health:.0f}/100 ({stage.lower()})."]
    if trend == "baseline":
        parts.append("There is not yet enough history (runs spread over at least a day) to establish a trajectory, "
                     "so the score reflects the current state.")
    elif trend in ("deteriorating", "slowly deteriorating"):
        parts.append(f"It has been {trend} by {abs(slope):.1f} points/day over the last {span:.0f} days"
                     + (", and the decline is accelerating." if accelerating else "."))
    else:
        parts.append(f"The trajectory over the last {span:.0f} days is {trend}.")
    drivers = [e for e in evidence if e["impact"] > 0]
    if drivers:
        names = [e["signal"].lower() for e in drivers[:2]]
        parts.append("The main driver" + (f"s are {names[0]} and {names[1]}." if len(names) > 1 else f" is {names[0]}."))
        parts.append(drivers[0]["detail"])
    else:
        parts.append("All measured signals are within normal ranges.")
    for a in associations:
        parts.append(a["text"])
    return " ".join(parts)


def _correlate(results):
    """Machine-level findings: degradation that is associated across components."""
    by_type = {}
    for r in results:
        by_type.setdefault(r["type"], []).append(r)
    findings = []

    def pen(r, *signals):
        return sum(e["impact"] for e in r["evidence"] if not signals or e["signal"] in signals)

    thermal_cpu = [r for r in by_type.get("cpu", []) + by_type.get("gpu", [])
                   if pen(r, "Temperature", "GPU temperature", "Sustained performance", "Temperature drift",
                          "GPU throttling") >= 8]
    weak_cooling = [r for r in by_type.get("cooling", []) if pen(r) >= 6]
    if thermal_cpu and weak_cooling:
        ids = [r["id"] for r in thermal_cpu + weak_cooling]
        findings.append({
            "id": "thermal", "title": "Thermal degradation", "components": ids, "severity": "elevated",
            "text": "Throttling and high temperatures are associated with degraded cooling. Servicing the "
                    "cooling path is likely to address the underlying condition; replacing the processor alone would not.",
        })
    hot = any(e["signal"] in ("Drive temperature", "Temperature") and e["impact"] > 0
              for r in results for e in r["evidence"]) or bool(weak_cooling)
    bad_disks = [r for r in by_type.get("storage", []) if r["health"] < 80]
    if bad_disks and hot:
        findings.append({
            "id": "storage-thermal", "title": "Storage degradation under thermal stress",
            "components": [r["id"] for r in bad_disks] + [r["id"] for r in weak_cooling], "severity": "elevated",
            "text": "Drive degradation is correlated with rising system temperature and weaker cooling. "
                    "Replacing the disk alone may not address the underlying condition.",
        })
    drifting = [r for r in by_type.get("storage", []) if r["trend"] in ("deteriorating", "slowly deteriorating")]
    if len(drifting) >= 2:
        findings.append({
            "id": "storage-subsystem", "title": "Storage subsystem pattern", "severity": "watch",
            "components": [r["id"] for r in drifting],
            "text": f"{len(drifting)} drives are deteriorating together — check controller, backplane and power "
                    "before replacing individual drives.",
        })
    return findings


# ----------------------------------------------------------------------------- public API

WAIT_OPTIONS = [("Now", 0.0), ("Tonight", 0.5), ("In 3 days", 3.0), ("In 7 days", 7.0), ("In 14 days", 14.0)]


def analyze(run, history=None):
    history = history or []
    machine = run.get("machine", {})
    t_now = run.get("collected_at") or datetime.now(timezone.utc).isoformat()
    ctx = _context(run)
    crit_boost = {"high": 1.3, "medium": 1.0, "low": 0.7}.get(machine.get("criticality", "medium"), 1.0)
    results = []

    for c in run.get("components", []):
        cid = c["id"]
        f = _score_component(c, ctx)

        # Growth of counters since the earliest run in the history window.
        past = [h for h in history if cid in h.get("metrics", {})]
        if past:
            first, first_t = past[max(0, len(past) - 14)]["metrics"][cid], past[max(0, len(past) - 14)]["t"]
            days = max(0.5, (_parse_t(t_now) - _parse_t(first_t)).total_seconds() / 86400)
            for key, (label, weight) in GROWTH_KEYS.items():
                if key in f.metrics and key in first:
                    delta = f.metrics[key] - first[key]
                    if delta > 0 and (delta / days > 0.5 or delta >= 5):
                        f.add(min(15, weight * (3 + 2.5 * _log2p(delta / days))), f"{label} growth", "up",
                              f"{label} grew from {first[key]:g} to {f.metrics[key]:g} in {days:.0f} days.")

        # Diminishing returns: many small issues should not add up to a dead component.
        health = round(max(1.0, 100 * math.exp(-f.penalty / 85)), 1)
        evidence = sorted(f.evidence, key=lambda e: -e["impact"])
        points = [{"t": h["t"], "health": h["health"][cid]} for h in history if cid in h.get("health", {})]
        points.append({"t": t_now, "health": health})
        slope, accel, span = _trajectory(points)
        trend = _trend_label(slope, span, len(points))
        risk7 = cumulative_risk(health, slope, 7)
        weight = TYPE_WEIGHT.get(c.get("type"), 0.5) * crit_boost
        redundancy = (c.get("static", {}).get("redundancy") or "").lower()
        if redundancy in ("hot-spare", "raid6", "n+1", "redundant"):
            weight *= 0.6
        elif redundancy in ("none", "degraded"):
            weight *= 1.3
        wait = []
        for label, d in WAIT_OPTIONS:
            r = cumulative_risk(health, slope, d)
            e = r * weight
            wait.append({"label": label, "days": d, "risk": round(r, 4),
                         "exposure": "LOW" if e < 0.04 else "MEDIUM" if e < 0.15 else "HIGH"})
        safe = [w for w in wait if w["risk"] <= 0.05]
        recommended = safe[-1]["label"] if safe else "Now"
        for w in wait:
            w["recommended"] = w["label"] == recommended
        signals = []
        for key, vals in (c.get("series") or {}).items():
            vals = _num(vals)
            if len(vals) >= 3 and key in SIGNAL_META:
                label, unit = SIGNAL_META[key]
                signals.append({"key": key, "label": label, "unit": unit, "values": [round(v, 3) for v in vals]})
        results.append({
            "id": cid, "type": c.get("type"), "name": c.get("name", cid),
            "health": health, "status": status_for(health), "stage": stage_for(health),
            "trend": trend, "slope_per_day": round(slope, 2), "accelerating": accel,
            "trajectory": points,
            "risk_7d": round(risk7, 4), "failure_window": _failure_window(health, slope),
            "confidence": None, "evidence": evidence, "signals": signals[:4],
            "priority_score": round(100 * (0.6 * risk7 + 0.4 * (100 - health) / 100) * weight, 1),
            "wait_simulation": wait, "static": c.get("static", {}), "metrics": f.metrics,
            # model-ready feature row in the Backblaze Drive Stats schema (HDDs with ATA SMART only)
            **({"drive_stats": c["drive_stats"]} if c.get("drive_stats") else {}),
            "_signals_n": f.signals, "_span": span, "_accel": accel,
        })

    findings = _correlate(results)
    for r in results:
        assoc = [fd for fd in findings if r["id"] in fd["components"]]
        r["associations"] = [{"id": a["id"], "title": a["title"], "text": a["text"],
                              "with": [x for x in a["components"] if x != r["id"]]} for a in assoc]
        n_hist = len(r["trajectory"])
        conf = 0.6 * min(1, r.pop("_signals_n") / 4) + 0.4 * min(1, (n_hist - 1) / 7)
        r["confidence"] = "high" if conf >= 0.7 else "medium" if conf >= 0.4 else "low"
        r["summary"] = _narrative(r, r["health"], r["stage"], r["trend"], r["slope_per_day"],
                                  r.pop("_span"), r.pop("_accel"), r["evidence"], assoc)
        r["action"] = _action(r, r["status"], r["evidence"])

    healths = [r["health"] for r in results] or [100]
    overall = round(0.6 * min(healths) + 0.4 * _mean(healths), 1)
    ranked = sorted(results, key=lambda r: -r["priority_score"])
    for i, r in enumerate(ranked, 1):
        r["priority_rank"] = i
    worst = min(results, key=lambda r: r["health"]) if results else None
    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("healthy", "watch", "elevated", "critical")}
    if worst and worst["status"] != "healthy":
        headline = f"{worst['name']}: {worst['stage'].lower()} — {worst['evidence'][0]['signal'].lower()}"
    else:
        headline = "All components healthy"
    return {
        "model": MODEL_NAME,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "collected_at": t_now,
        "machine": machine,
        "runs_used": len(history) + 1,
        "overall": {"health": overall, "status": status_for(overall), "stage": stage_for(overall),
                    "headline": headline, "counts": counts},
        "priority": [r["id"] for r in ranked if r["status"] != "healthy"],
        "findings": findings,
        "components": results,
    }


def history_entry(run, analysis):
    return {"t": analysis["collected_at"],
            "health": {r["id"]: r["health"] for r in analysis["components"]},
            "metrics": {r["id"]: r["metrics"] for r in analysis["components"]}}
