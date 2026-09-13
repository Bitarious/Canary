"""Prepare separate component datasets from pinned, locally acquired sources."""

import argparse
from collections import Counter
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa

from driftops.acquire import write_json
from driftops.component_data import build, make_window, partition
from driftops.full_archive import file_hash
from driftops.windows import read_yaml


AUDIT = Path("artifacts/component-audit/v1")
CONFIG = Path("config/components.yaml")
DAY_US = 86_400_000_000


def specification(component):
    settings = read_yaml(CONFIG)
    family = "clusterwise" if component in ("cpu", "gpu", "server") else component
    rule = settings[family]
    result = {"version": settings["version"], "component": component, "scope": settings["scope"],
              "split_salt": rule["split_salt"], "availability": rule["availability"],
              "partitions": {name: {"buckets": settings["split_buckets"][name], "start": bounds[0], "stop": bounds[1]}
                             for name, bounds in rule["time_intervals"].items()}}
    def channel(unit, description, counter=False):
        return {"unit": unit, "description": description, "minimum_band": 1., "counter": counter}
    if component == "ssd":
        source = "https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data"
        result.update(provider="Backblaze", source_type="backblaze-ssd-smart", source_url=source,
                      license="other", license_url=source, citation="Backblaze Drive Stats SATA SSD observations",
                      cadence_us=DAY_US, cadence_text="daily snapshots available at the next midnight",
                      channels={"temperature": channel("celsius", "SSD temperature in Celsius"),
                                "power_on_hours": channel("hour", "SSD cumulative power-on hours", True)})
    elif family == "clusterwise":
        result.update(provider="OLCF Summit / ClusterWise", source_type="olcf-clusterwise",
                      source_url="https://huggingface.co/datasets/MachaParfait/ClusterWise/tree/93fb62c369fcfb36536252a9bb4a539dcdb2b229",
                      license="CC-BY-4.0", license_url="https://creativecommons.org/licenses/by/4.0/",
                      citation="OLCF Summit power and thermal measurements, ClusterWise pinned preparation",
                      cadence_us=10_000_000, cadence_text="ten-second mean observations available at interval end")
        if component == "cpu":
            result["channels"] = {"power": channel("watt", "processor DC power in watts"),
                                  "core_temperature": channel("celsius", "mean processor core temperature in Celsius, excluding core 13")}
        elif component == "gpu":
            result["channels"] = {"power": channel("watt", "GPU DC power in watts"),
                                  "core_temperature": channel("celsius", "GPU core temperature in Celsius"),
                                  "memory_temperature": channel("celsius", "GPU HBM temperature in Celsius")}
        else:
            result["channels"] = {"supply_0_input_power": channel("watt", "first node power supply AC input power in watts"),
                                  "supply_1_input_power": channel("watt", "second node power supply AC input power in watts")}
    else:
        raise ValueError("The component source adapter is not implemented.")
    return result


def time_bounds(split, config):
    rule = config["partitions"][split]
    return tuple(int(datetime.fromisoformat(rule[key]).timestamp() * 1e6) for key in ("start", "stop"))


def ssd_windows(config, audit):
    settings = read_yaml(CONFIG)["ssd"]
    source = Path("data/backblaze-full")
    extract = Path("data/components/raw/ssd-component-v1.parquet")
    extract.parent.mkdir(parents=True, exist_ok=True)
    if extract.exists():
        raise FileExistsError("Inspect the existing SSD extract before another preparation run.")
    with duckdb.connect() as con:
        con.execute("SET threads=8")
        con.execute("SET memory_limit='8GB'")
        con.read_parquet([str(p) for p in sorted((source / "records").glob("*.parquet"))
                          if not p.name.endswith(".quarantine.parquet")]).create_view("raw")
        con.register("allowed_models", pa.table({"model": settings["models"]}))
        con.execute("""COPY (SELECT raw.date, serial_number, model, failure, smart_9_raw, smart_194_raw
                    FROM raw JOIN allowed_models USING(model) ORDER BY serial_number,date)
                    TO ? (FORMAT PARQUET, COMPRESSION ZSTD)""", [str(extract)])
        con.read_parquet(str(extract)).create_view("ssd")
        if con.execute("SELECT count(*) FROM (SELECT serial_number,date FROM ssd GROUP BY ALL HAVING count(*)>1)").fetchone()[0]:
            raise ValueError("The SSD source has duplicate serial and date pairs.")
        if con.execute("SELECT count(*) FROM (SELECT serial_number FROM ssd GROUP BY serial_number HAVING count(DISTINCT model)>1)").fetchone()[0]:
            raise ValueError("Review SSD serials with changing hardware models.")
        grouped = con.execute("""SELECT serial_number, list(struct_pack(date := date, failure := failure,
                    temperature := smart_194_raw, power_on_hours := smart_9_raw) ORDER BY date)
                    FROM ssd GROUP BY serial_number ORDER BY serial_number""")
        while found := grouped.fetchone():
            serial, rows = found
            identity = "backblaze-ssd:" + serial
            first, stop = time_bounds(partition(identity, config), config)
            segment, failed = [], False
            for row in rows:
                audit["source_rows"] += 1
                failed = failed or row["failure"] == 1
                available = int(datetime.combine(row["date"] + timedelta(days=1), time.min, timezone.utc).timestamp() * 1e6)
                if failed or not first <= available < stop:
                    audit["rows_outside_time_or_at_after_failure"] += 1
                    segment = []
                    continue
                values = [row[c] for c in config["channels"]]
                if any(v is None or not np.isfinite(v) or abs(v) > 2**53 for v in values):
                    audit["rows_missing_or_invalid_channels"] += 1
                    segment = []
                    continue
                if segment and available - segment[-1][0] != DAY_US:
                    audit["calendar_gaps"] += 1
                    segment = []
                segment.append((available, values))
                if len(segment) == 28:
                    yield make_window(identity, identity, [r[0] for r in segment], np.asarray([r[1] for r in segment]).T,
                                      list(config["channels"]), config)
                    segment = []


def clusterwise_hosts(config):
    settings = read_yaml(CONFIG)["clusterwise"]
    path = AUDIT / "clusterwise-host-cohort.json"
    with duckdb.connect() as con:
        hosts = [r[0] for r in con.execute("SELECT DISTINCT hostname FROM read_parquet(?) ORDER BY hostname",
                                          [str(AUDIT / "clusterwise-20200101.parquet")]).fetchall()]
    result = {}
    for split, limit in settings["host_limits"].items():
        chosen = [h for h in hosts if partition("clusterwise:" + h, config) == split]
        chosen.sort(key=lambda h: hashlib.sha256((settings["cohort_hash_salt"] + h).encode()).digest())
        if len(chosen) < limit:
            raise ValueError("The fixed source inventory has too few hosts for the declared cohort.")
        result[split] = chosen[:limit]
    record = {"source_inventory": "20200101", "selection": "Fixed host hashes without target or numerical-value selection",
              "config_sha256": file_hash(CONFIG), "hosts": result}
    if path.exists() and json.loads(path.read_text()) != record:
        raise ValueError("The fixed ClusterWise host cohort changed.")
    if not path.exists():
        write_json(path, record)
    return result


def clusterwise_windows(config, audit):
    settings = read_yaml(CONFIG)["clusterwise"]
    hosts = clusterwise_hosts(config)
    component = config["component"]
    slots = range(2 if component == "cpu" else 6 if component == "gpu" else 1)
    def columns(slot):
        if component == "cpu":
            return [f"p{slot}_power", f"p{slot}_temp_mean"]
        if component == "gpu":
            return [f"p{slot//3}_gpu{slot%3}_power", f"gpu{slot}_core_temp", f"gpu{slot}_mem_temp"]
        return ["ps0_input_power", "ps1_input_power"]
    wanted_columns = list(dict.fromkeys(c for slot in slots for c in columns(slot)))
    fields = ", ".join(f"{c} := {c}" for c in wanted_columns)
    with duckdb.connect() as con:
        con.execute("SET threads=4")
        con.execute("SET memory_limit='8GB'")
        for day in settings["source_days"]:
            date = datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)
            timestamp = int(date.timestamp() * 1e6)
            splits = [s for s in hosts if time_bounds(s, config)[0] <= timestamp < time_bounds(s, config)[1]]
            eligible = [h for s in splits for h in hosts[s]]
            con.register("hosts", pa.table({"hostname": eligible}))
            path = AUDIT / ("clusterwise-" + day + ".parquet")
            receipt = json.loads(Path(str(path) + "-receipt.json").read_text())
            if file_hash(path) != receipt["sha256"]:
                raise ValueError("A ClusterWise source checksum changed.")
            con.read_parquet(str(path)).create_view("raw", replace=True)
            query = f"""SELECT hostname, list(struct_pack(observed_at := timestamp, {fields}) ORDER BY timestamp)
                       FROM raw JOIN hosts USING(hostname) GROUP BY hostname ORDER BY hostname"""
            grouped = con.execute(query)
            while found := grouped.fetchone():
                host, rows = found
                group = "clusterwise:" + host
                split = partition(group, config)
                audit["source_host_rows"] += len(rows)
                times = np.array([int(r["observed_at"].replace(tzinfo=timezone.utc).timestamp() * 1e6) + 10_000_000
                                  for r in rows], dtype=np.int64)
                if np.any(np.diff(times) <= 0):
                    raise ValueError("The ClusterWise source has duplicate or unordered host timestamps.")
                starts = list(range(0, len(rows) - 27, 28))
                starts.sort(key=lambda i: hashlib.sha256((settings["window_hash_salt"] + host + ":" + str(times[i])).encode()).digest())
                starts = sorted(starts[:settings["windows_per_host_day"][split]])
                for slot in slots:
                    values = np.array([[r[c] for r in rows] for c in columns(slot)], dtype=np.float64)
                    for start in starts:
                        window_times, window_values = times[start:start+28], values[:, start:start+28]
                        first, stop = time_bounds(split, config)
                        if not first <= window_times[0] <= window_times[-1] < stop:
                            audit["windows_outside_time"] += 1
                            continue
                        if np.any(np.diff(window_times) != config["cadence_us"]) or not np.isfinite(window_values).all():
                            audit["windows_with_gaps_or_missing_values"] += 1
                            continue
                        identity = group + f":{component}:{slot}" if component != "server" else group
                        yield make_window(identity, group, window_times, window_values, list(config["channels"]), config)


def prepare(component, output):
    config = specification(component)
    sources = {"preparation_config_sha256": file_hash(CONFIG), "source_url": config["source_url"],
               "scope": config["scope"], "availability": config["availability"]}
    if component == "ssd":
        sources.update(backblaze_records_manifest_sha256=file_hash(Path("data/backblaze-full/records-complete.json")),
                       smart_reference_sha256=file_hash(AUDIT / "barracuda120-manual.pdf"),
                       hardware_models=read_yaml(CONFIG)["ssd"]["models"])
        generator = ssd_windows
    else:
        sources.update(cohort_manifest=json.loads((AUDIT / "clusterwise-cohort-manifest.json").read_text()),
                       host_cohort=clusterwise_hosts(config),
                       channel_semantics_sha256=file_hash(AUDIT / "hpc-README.md"))
        generator = clusterwise_windows
    audit = Counter()
    result = build(output, generator(config, audit), config, sources)
    result["source_audit"] = dict(audit)
    write_json(output / "dataset-manifest.json", result)
    print(json.dumps({"component": component, "audit": result["audit"], "source_audit": dict(audit),
                      "groups": {s: len(ids) for s, ids in result["groups"].items()},
                      "manifest_sha256": file_hash(output / "dataset-manifest.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["ssd", "cpu", "gpu", "server"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.component, args.output)
