"""DriftOps agent: benchmark this machine and send its telemetry to a DriftOps server.

    python agent/collect.py --server http://127.0.0.1:8765          # ~1 minute
    python agent/collect.py --rounds 6 --no-stress --out run.json  # quick, offline

Runs a sustained stress benchmark in rounds (CPU, memory, disk) while sampling sensors, then
reads long-lived health counters (battery wear, SMART / storage reliability, GPU, error logs).
Every probe is best-effort: missing sensors simply leave a signal out. Only needs ``psutil``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

try:
    import psutil
except ImportError:  # pragma: no cover
    sys.exit("psutil is required: pip install psutil")

WINDOWS = os.name == "nt"


def log(msg):
    print(msg, flush=True)


def run(cmd, timeout=20):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def ps_json(script, timeout=25):
    """Run PowerShell and parse ``ConvertTo-Json`` output into a list of dicts."""
    if not WINDOWS:
        return []
    out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
               f"$ErrorActionPreference='SilentlyContinue'; {script} | ConvertTo-Json -Depth 3"], timeout)
    try:
        data = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else [data]


# ----------------------------------------------------------------------------- static probes

def machine_info():
    info = {"hostname": socket.gethostname(), "os": f"{platform.system()} {platform.release()}",
            "cpu_model": platform.processor(), "vendor": "", "model": ""}
    if WINDOWS:
        cs = ps_json("Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model")
        cpu = ps_json("Get-CimInstance Win32_Processor | Select-Object Name")
        if cs:
            info["vendor"], info["model"] = (cs[0].get("Manufacturer") or "").strip(), (cs[0].get("Model") or "").strip()
        if cpu:
            info["cpu_model"] = (cpu[0].get("Name") or "").strip()
    elif sys.platform.startswith("linux"):
        for key, path in (("vendor", "/sys/class/dmi/id/sys_vendor"), ("model", "/sys/class/dmi/id/product_name")):
            try:
                info[key] = open(path).read().strip()
            except OSError:
                pass
        try:
            for line in open("/proc/cpuinfo"):
                if line.startswith("model name"):
                    info["cpu_model"] = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
    return info


def battery_static():
    st = {}
    if WINDOWS:
        for cls, key, field in (("BatteryStaticData", "design_capacity_mwh", "DesignedCapacity"),
                                ("BatteryFullChargedCapacity", "full_charge_capacity_mwh", "FullChargedCapacity"),
                                ("BatteryCycleCount", "cycle_count", "CycleCount")):
            rows = ps_json(f"Get-CimInstance -Namespace root\\wmi -ClassName {cls} | Select-Object {field}")
            if rows and rows[0].get(field):
                st[key] = int(rows[0][field])
        if "design_capacity_mwh" not in st:  # fallback without admin rights
            st.update(_battery_report())
    elif sys.platform.startswith("linux"):
        base = "/sys/class/power_supply/BAT0/"

        def read(name):
            try:
                return int(open(base + name).read().strip())
            except (OSError, ValueError):
                return None
        design, full = read("energy_full_design"), read("energy_full")
        if design and full:
            st["design_capacity_mwh"], st["full_charge_capacity_mwh"] = design // 1000, full // 1000
        if read("cycle_count"):
            st["cycle_count"] = read("cycle_count")
    return st


def _battery_report():
    """Parse ``powercfg /batteryreport`` (works without admin)."""
    import re
    path = os.path.join(tempfile.gettempdir(), "driftops_battery.xml")
    run(["powercfg", "/batteryreport", "/xml", "/output", path], timeout=30)
    try:
        xml = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return {}
    st = {}
    for key, tag in (("design_capacity_mwh", "DesignCapacity"), ("full_charge_capacity_mwh", "FullChargeCapacity"),
                     ("cycle_count", "CycleCount")):
        m = re.search(rf"<{tag}>(\d+)</{tag}>", xml)
        if m and int(m.group(1)) > 0:
            st[key] = int(m.group(1))
    return st


def event_counts():
    """Hardware (WHEA) and disk error events over the last 30 days."""
    if not WINDOWS:
        return {}
    script = ("$s=(Get-Date).AddDays(-30); "
              "$w=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-WHEA-Logger';StartTime=$s;Level=2,3} -MaxEvents 500).Count; "
              "$d=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='disk','stornvme','storahci';StartTime=$s;Level=1,2,3} -MaxEvents 500).Count; "
              "[pscustomobject]@{whea=$w;disk=$d}")
    rows = ps_json(script, timeout=40)
    return {"hardware_errors_30d": int(rows[0].get("whea") or 0), "disk_errors_30d": int(rows[0].get("disk") or 0)} if rows else {}


# SMART attributes kept in the Backblaze Drive Stats schema (smart_<id>_raw / smart_<id>_normalized),
# so a model trained on https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data can
# score a local drive with the same feature columns. Raw values are the full 48-bit counters, exactly
# as smartctl reports them (Backblaze collects with smartctl), including vendor bit-packing.
DRIVE_STATS_ATTRS = (1, 3, 4, 5, 7, 9, 10, 12, 187, 188, 189, 193, 194, 197, 198, 199, 240, 241, 242)


def drive_stats_row(model, serial, capacity_bytes, attrs):
    """One Backblaze-schema feature row from ``{attribute_id: (normalized, raw)}``."""
    row = {"model": (model or "").strip(), "capacity_bytes": capacity_bytes,
           # the serial identifies the drive across runs without sending it off the machine
           "serial_hash": hashlib.sha256((serial or "").strip().encode()).hexdigest()[:16] if serial else None}
    for aid in DRIVE_STATS_ATTRS:
        if aid in attrs:
            norm, raw = attrs[aid]
            row[f"smart_{aid}_normalized"], row[f"smart_{aid}_raw"] = norm, raw
    return row


def parse_ata_smart_table(data):
    """Attributes from the raw 362-byte ATA SMART data block (as exposed by Windows WMI)."""
    attrs = {}
    for off in range(2, min(len(data), 362) - 11, 12):  # 30 entries: id, flags(2), value, worst, raw(6), reserved
        aid = data[off]
        if aid:
            attrs[aid] = (data[off + 3], int.from_bytes(data[off + 5:off + 11], "little"))
    return attrs


def _wmi_drive_stats():
    """Backblaze rows keyed by disk number, from the in-box ATA SMART WMI class (admin, no smartctl)."""
    rows = ps_json(
        "$dd=@(Get-CimInstance Win32_DiskDrive); "
        "Get-CimInstance -Namespace root\\wmi -ClassName MSStorageDriver_ATAPISmartData | ForEach-Object { "
        "$inst=$_.InstanceName -replace '_\\d+$',''; $d=$dd | Where-Object { $_.PNPDeviceID -eq $inst } | Select-Object -First 1; "
        "[pscustomobject]@{Index=$d.Index; Model=$d.Model; Serial=$d.SerialNumber; Size=$d.Size; "
        "Data=[BitConverter]::ToString($_.VendorSpecific)} }", timeout=40)
    out = {}
    for r in rows:
        if r.get("Index") is None or not r.get("Data"):
            continue
        try:
            attrs = parse_ata_smart_table(bytes.fromhex(r["Data"].replace("-", "")))
        except ValueError:
            continue
        out[str(r["Index"])] = (r.get("Serial"), drive_stats_row(r.get("Model"), r.get("Serial"), r.get("Size"), attrs))
    return out


def _same_serial(a, b):
    return bool(a and b) and a.strip().lower() == b.strip().lower()


def disks_static():
    """Physical disks with whatever health counters the OS or smartctl exposes."""
    disks = []
    if WINDOWS:
        rows = ps_json(
            "$sys=(Get-Partition -DriveLetter $env:SystemDrive[0] | Get-Disk).Number; "
            "Get-PhysicalDisk | ForEach-Object { $r = $_ | Get-StorageReliabilityCounter; "
            "[pscustomobject]@{Id=$_.DeviceId; Name=$_.FriendlyName; Media=[string]$_.MediaType; Bus=[string]$_.BusType; "
            "Serial=$_.SerialNumber; SizeGB=[math]::Round($_.Size/1GB); Health=[string]$_.HealthStatus; System=([string]$_.DeviceId -eq [string]$sys); "
            "Temp=$r.Temperature; Wear=$r.Wear; ReadErr=$r.ReadErrorsTotal; WriteErr=$r.WriteErrorsTotal; POH=$r.PowerOnHours} }",
            timeout=40)
        wmi = _wmi_drive_stats()
        for r in rows:
            smart = {k: v for k, v in (("temperature_c", r.get("Temp")), ("percentage_used", r.get("Wear")),
                                       ("read_errors_total", r.get("ReadErr")), ("write_errors_total", r.get("WriteErr")),
                                       ("power_on_hours", r.get("POH"))) if isinstance(v, (int, float)) and not (k == "temperature_c" and v == 0)}
            disk = {"key": str(r.get("Id")), "name": f"{r.get('Name', 'Disk').strip()} · {r.get('SizeGB')} GB",
                    "media": (r.get("Media") or "").lower(), "bus": r.get("Bus"), "serial": r.get("Serial"),
                    "system": bool(r.get("System")), "smart": smart}
            if str(r.get("Id")) in wmi and disk["media"] != "ssd":
                disk["drive_stats"] = wmi[str(r.get("Id"))][1]
            disks.append(disk)
    if shutil.which("smartctl"):
        scan = run(["smartctl", "--scan", "-j"])
        try:
            devices = json.loads(scan).get("devices", []) if scan else []
        except json.JSONDecodeError:
            devices = []
        for i, dev in enumerate(devices):
            try:
                data = json.loads(run(["smartctl", "-a", "-j", "-d", dev.get("type", "auto"), dev["name"]], timeout=30) or "{}")
            except json.JSONDecodeError:
                continue
            smart = {}
            table = data.get("ata_smart_attributes", {}).get("table", [])
            attrs = {a["id"]: a.get("raw", {}).get("value") for a in table}
            for key, aid in (("reallocated_sectors", 5), ("pending_sectors", 197), ("uncorrectable_errors", 198),
                             ("crc_errors", 199)):
                if aid in attrs:
                    smart[key] = attrs[aid]
            if 9 in attrs:
                smart["power_on_hours"] = attrs[9] & 0xFFFFFFFF  # some vendors pack minutes above bit 32
            nv = data.get("nvme_smart_health_information_log") or {}
            for key, src in (("percentage_used", "percentage_used"), ("media_errors", "media_errors"),
                             ("available_spare", "available_spare"), ("available_spare_threshold", "available_spare_threshold"),
                             ("power_on_hours", "power_on_hours")):
                if src in nv:
                    smart[key] = nv[src]
            if data.get("temperature", {}).get("current"):
                smart["temperature_c"] = data["temperature"]["current"]
            name = data.get("model_name", dev["name"])
            serial = data.get("serial_number")
            media = "hdd" if data.get("rotation_rate") else "ssd"
            stats = None
            if table and media == "hdd":
                stats = drive_stats_row(name, serial, data.get("user_capacity", {}).get("bytes"),
                                        {a["id"]: (a.get("value"), a.get("raw", {}).get("value")) for a in table})
            # enrich the OS view rather than duplicating it: match by serial, else by scan order
            match = next((d for d in disks if _same_serial(d.get("serial"), serial)), None)
            if match is None and not serial and i < len(disks):
                match = disks[i]
            if match is not None:
                match["smart"].update(smart)
                if stats:
                    match["drive_stats"] = stats  # smartctl is the reference source; it wins over WMI
            else:
                disks.append({"key": dev["name"], "name": name, "media": media, "system": not disks and i == 0,
                              "smart": smart, **({"drive_stats": stats} if stats else {})})
    if not disks:
        disks.append({"key": "sys", "name": "System drive", "media": "", "system": True, "smart": {}})
    if not any(d["system"] for d in disks):
        disks[0]["system"] = True
    return disks


# ----------------------------------------------------------------------------- live sampling

def cpu_temp():
    try:
        temps = psutil.sensors_temperatures()  # Linux / BSD
    except AttributeError:
        temps = {}
    for key in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"):
        if temps.get(key):
            return max(t.current for t in temps[key])
    return None


def win_thermal_zone():
    rows = ps_json("Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature | Select-Object CurrentTemperature", 15)
    vals = [r["CurrentTemperature"] / 10 - 273.15 for r in rows if r.get("CurrentTemperature")]
    vals = [v for v in vals if 5 < v < 125]
    return max(vals) if vals else None


def fan_rpm():
    try:
        fans = psutil.sensors_fans()
    except AttributeError:
        return None
    vals = [f.current for group in fans.values() for f in group if f.current]
    return statistics.mean(vals) if vals else None


def gpu_sample():
    if not shutil.which("nvidia-smi"):
        return None
    out = run(["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,power.draw,clocks_throttle_reasons.active",
               "--format=csv,noheader,nounits"], timeout=10)
    if not out.strip():
        return None
    parts = [p.strip() for p in out.splitlines()[0].split(",")]

    def num(x):
        try:
            return float(x)
        except ValueError:
            return None
    throttle = parts[4] if len(parts) > 4 else "0x0"
    # bits: 0x20 sw thermal, 0x40 hw slowdown, 0x80 hw thermal (0x4 power cap is normal at idle on Max-Q)
    try:
        throttled = int(throttle, 16) & (0x20 | 0x40 | 0x80) != 0
    except ValueError:
        throttled = False
    return {"name": parts[0], "temp_c": num(parts[1]), "util_pct": num(parts[2]),
            "power_w": num(parts[3]) if len(parts) > 3 else None, "throttled": throttled}


def _burn(stop):
    x = 0
    while not stop.is_set():
        for _ in range(20000):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF


def cpu_bench(seconds=1.0):
    payload, n, end = os.urandom(512), 0, time.perf_counter() + seconds
    h = hashlib.sha256
    while time.perf_counter() < end:
        for _ in range(200):
            payload = h(payload).digest() * 16
        n += 200
    return n / seconds


def mem_bench(src, dst):
    t = time.perf_counter()
    for _ in range(3):
        dst[:] = src
    dt = time.perf_counter() - t
    return 3 * len(src) / dt / 1e9


def disk_bench(path, mb=48, small=24):
    block = os.urandom(1 << 20)
    t = time.perf_counter()
    with open(path, "wb", buffering=0) as f:
        for _ in range(mb):
            f.write(block)
        os.fsync(f.fileno())
    write = mb / (time.perf_counter() - t)
    t = time.perf_counter()
    with open(path, "rb", buffering=0) as f:
        while f.read(1 << 20):
            pass
    read = mb / (time.perf_counter() - t)
    lat, four_k = [], os.urandom(4096)
    with open(path, "r+b", buffering=0) as f:
        for i in range(small):
            t = time.perf_counter()
            f.seek((i * 7919) % (mb - 1) << 20)
            f.write(four_k)
            os.fsync(f.fileno())
            lat.append((time.perf_counter() - t) * 1000)
    lat.sort()
    return write, read, statistics.median(lat), lat[int(len(lat) * 0.95) - 1]


# ----------------------------------------------------------------------------- main

def collect(rounds=12, stress=True, disk_mb=48):
    log("PHASE static: reading machine inventory and health counters")
    battery = psutil.sensors_battery()
    form = "laptop" if battery is not None else "desktop"
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {"info": pool.submit(machine_info), "events": pool.submit(event_counts), "disks": pool.submit(disks_static),
                "battery": pool.submit(battery_static if battery is not None else dict),
                "wmi_temp": pool.submit(lambda: WINDOWS and cpu_temp() is None and win_thermal_zone() is not None),
                "gpu": pool.submit(lambda: gpu_sample() is not None)}
        info, events, disks = jobs["info"].result(), jobs["events"].result(), jobs["disks"].result()
        bat_static, use_wmi_temp, has_gpu = jobs["battery"].result(), jobs["wmi_temp"].result(), jobs["gpu"].result()

    series = {k: [] for k in ("cpu_ops", "cpu_temp", "cpu_freq", "cpu_load", "mem_used", "swap", "mem_bw",
                              "write", "read", "lat", "lat95", "fan", "gpu_temp", "gpu_util", "gpu_power", "bat")}
    gpu = {"name": None, "throttle": 0}
    stop, workers = mp.Event(), []
    if stress:
        physical = psutil.cpu_count(logical=False) or os.cpu_count() or 2
        for _ in range(max(1, physical - 1)):
            p = mp.Process(target=_burn, args=(stop,), daemon=True)
            p.start()
            workers.append(p)
        time.sleep(1.0)  # let the load processes spin up before the first round

    def sampler():
        """Slow probes (external tools, WMI) run beside the benchmark instead of inside each round."""
        while not stop.is_set():
            t = win_thermal_zone() if use_wmi_temp else None
            if t is not None:
                series["cpu_temp"].append(t)
            g = gpu_sample() if has_gpu else None
            if g:
                gpu["name"] = g["name"]
                gpu["throttle"] += int(g["throttled"])
                for key, src_key in (("gpu_temp", "temp_c"), ("gpu_util", "util_pct"), ("gpu_power", "power_w")):
                    if g[src_key] is not None:
                        series[key].append(g[src_key])
            stop.wait(1.5)

    probe = threading.Thread(target=sampler, daemon=True)
    probe.start()
    src = bytearray(os.urandom(64 << 20))
    dst = bytearray(len(src))
    tmp = os.path.join(tempfile.gettempdir(), f"driftops_bench_{os.getpid()}.bin")
    psutil.cpu_percent(None)
    try:
        for i in range(rounds):
            log(f"PROGRESS {i + 1}/{rounds} cpu+memory+disk")
            series["cpu_ops"].append(cpu_bench(1.0))
            series["cpu_load"].append(psutil.cpu_percent(None))
            freq = psutil.cpu_freq()
            if freq and freq.current:
                series["cpu_freq"].append(freq.current)
            t = cpu_temp()
            if t is not None:
                series["cpu_temp"].append(t)
            vm = psutil.virtual_memory()
            series["mem_used"].append(vm.percent)
            series["swap"].append(psutil.swap_memory().percent)
            series["mem_bw"].append(mem_bench(src, dst))
            try:
                w, r, lat, lat95 = disk_bench(tmp, disk_mb)
                series["write"].append(w)
                series["read"].append(r)
                series["lat"].append(lat)
                series["lat95"].append(lat95)
            except OSError as e:
                log(f"disk benchmark skipped: {e}")
            rpm = fan_rpm()
            if rpm:
                series["fan"].append(rpm)
            b = psutil.sensors_battery()
            if b:
                series["bat"].append(b.percent)
    finally:
        stop.set()
        probe.join(timeout=5)
        for p in workers:
            p.join(timeout=3)
        try:
            os.remove(tmp)
        except OSError:
            pass

    def rnd(xs, d=2):
        return [round(x, d) for x in xs]

    comps = [{
        "id": "cpu0", "type": "cpu", "name": f"CPU · {info['cpu_model'] or platform.machine()}",
        "static": {"cores": os.cpu_count(), **({"hardware_errors_30d": events["hardware_errors_30d"]} if events else {})},
        "series": {"bench_ops": rnd(series["cpu_ops"], 0), "load_pct": rnd(series["cpu_load"], 1),
                   **({"temp_c": rnd(series["cpu_temp"], 1)} if series["cpu_temp"] else {}),
                   **({"freq_mhz": rnd(series["cpu_freq"], 0)} if len(set(series["cpu_freq"])) > 1 else {})},
    }]
    if gpu["name"]:
        comps.append({"id": "gpu0", "type": "gpu", "name": f"GPU · {gpu['name']}",
                      "static": {"throttle_events": gpu["throttle"]},
                      "series": {"temp_c": series["gpu_temp"], "util_pct": series["gpu_util"], "power_w": series["gpu_power"]}})
    comps.append({"id": "memory", "type": "memory",
                  "name": f"Memory · {psutil.virtual_memory().total / 2 ** 30:.0f} GB",
                  "static": {}, "series": {"used_pct": rnd(series["mem_used"], 1), "swap_pct": rnd(series["swap"], 1),
                                           "bandwidth_gbps": rnd(series["mem_bw"])}})
    for i, d in enumerate(disks):
        c = {"id": f"disk{i}", "type": "storage", "name": d["name"],
             "static": {"media": d["media"], "system": d["system"]}, "smart": d["smart"], "series": {}}
        if d.get("drive_stats"):
            c["drive_stats"] = d["drive_stats"]
        if d["system"]:
            if events:
                c["static"]["event_errors_30d"] = events["disk_errors_30d"]
            c["series"] = {"write_mbps": rnd(series["write"], 1), "read_mbps": rnd(series["read"], 1),
                           "latency_ms": rnd(series["lat"], 3), "latency_p95_ms": rnd(series["lat95"], 3)}
        comps.append(c)
    if battery is not None:
        comps.append({"id": "battery", "type": "battery", "name": "Battery", "static": bat_static,
                      "series": {"percent": series["bat"]}})
    comps.append({"id": "cooling", "type": "cooling", "name": "Cooling · fans & heatsink", "static": {},
                  "series": {"rpm": rnd(series["fan"], 0)} if series["fan"] else {}})

    machine_id = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in info["hostname"].lower())
    return {
        "schema": "driftops.telemetry/v1", "source": "agent",
        "collected_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "machine": {"id": machine_id, "hostname": info["hostname"],
                    "label": f"{info['hostname']} · {info['vendor']} {info['model']}".strip(" ·"),
                    "form_factor": form, "vendor": info["vendor"], "model": info["model"], "os": info["os"],
                    "cpu_model": info["cpu_model"], "role": "benchmarked device", "criticality": "medium"},
        "benchmark": {"rounds": rounds, "stress": stress, "disk_mb": disk_mb},
        "components": comps,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", help="DriftOps server URL, e.g. http://127.0.0.1:8765")
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--no-stress", action="store_true", help="do not load the other CPU cores")
    ap.add_argument("--disk-mb", type=int, default=48)
    ap.add_argument("--out", help="also write the telemetry JSON to this file")
    ap.add_argument("--site", default="local", help="site id this device belongs to (default: local)")
    ap.add_argument("--rack", default="bench", help="rack / group id inside the site (default: bench)")
    ap.add_argument("--slot", type=int, help="position in the rack, used for ordering in the digital twin")
    args = ap.parse_args()

    telemetry = collect(args.rounds, not args.no_stress, args.disk_mb)
    telemetry["machine"].update({"site": args.site, "rack": args.rack, **({"slot": args.slot} if args.slot else {})})
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(telemetry, f, indent=1)
        log(f"wrote {args.out}")
    if args.server:
        req = urllib.request.Request(args.server.rstrip("/") + "/api/telemetry", data=json.dumps(telemetry).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            log(f"RESULT {resp.read().decode()}")
    if not args.out and not args.server:
        print(json.dumps(telemetry, indent=1))


if __name__ == "__main__":
    mp.freeze_support()
    main()
