"""Prepare dated SmartMem log-count windows without assuming healthy exposure."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.csv as pcsv
import pyarrow.parquet as pq

from driftops.acquire import write_json
from driftops.component_data import build, make_window, partition
from driftops.full_archive import file_hash
from driftops.prepare_components import AUDIT, CONFIG, DAY_US, time_bounds
from driftops.windows import read_yaml


def specification():
    settings = read_yaml(CONFIG)
    rule = settings["smartmem"]
    return {"version": settings["version"], "component": "dram", "scope": settings["scope"],
        "split_salt": rule["split_salt"], "availability": rule["availability"],
        "partitions": {name: {"buckets": settings["split_buckets"][name], "start": bounds[0], "stop": bounds[1]}
                       for name, bounds in rule["time_intervals"].items()},
        "provider": "SmartMem", "source_type": "smartmem-recorded-memory-errors",
        "source_url": "https://zenodo.org/records/15516113", "license": "CC-BY-NC-4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc/4.0/", "citation": "SmartMem WWW 2025 memory error logs",
        "cadence_us": DAY_US, "cadence_text": "recorded error counts per closed UTC day; zero does not establish healthy operation",
        "channels": {
            "read_error_logs": {"unit": "count", "description": "recorded CE.READ error log count", "minimum_band": 1},
            "scrub_error_logs": {"unit": "count", "description": "recorded CE.SCRUB error log count", "minimum_band": 1}}}


def initialize_worker(archive):
    global ZIP
    ZIP = zipfile.ZipFile(archive)
    pa.set_cpu_count(1)


def count_device(item):
    name, alarm = item
    counts, audit = Counter(), Counter()
    first = None
    with ZIP.open(name) as stream:
        reader = pcsv.open_csv(stream, read_options=pcsv.ReadOptions(block_size=4*1024*1024, use_threads=False),
            convert_options=pcsv.ConvertOptions(include_columns=["LogTime", "error_type_full_name"],
                                               column_types={"LogTime": pa.int64(), "error_type_full_name": pa.string()}))
        for batch in reader:
            audit["source_rows"] += len(batch)
            if batch.column(0).null_count or batch.column(1).null_count:
                raise ValueError("A SmartMem log row lacks a timestamp or error type.")
            times = batch.column(0).to_numpy()
            if np.any((times < 1_600_000_000) | (times > 1_800_000_000)):
                raise ValueError("A SmartMem timestamp is outside the documented era.")
            kinds = np.asarray(batch.column(1).to_pylist())
            valid = times < alarm if alarm is not None else np.ones(len(times), dtype=bool)
            audit["rows_at_after_failure_ticket"] += int((~valid).sum())
            if valid.any():
                first = min(first if first is not None else int(times[valid].min()), int(times[valid].min()))
            for index, kind in enumerate(("CE.READ", "CE.SCRUB")):
                selected = valid & (kinds == kind)
                days, frequencies = np.unique(times[selected] // 86400, return_counts=True)
                for day, count in zip(days, frequencies):
                    counts[(int(day), index)] += int(count)
            audit["rows_other_error_types"] += int((valid & ~np.isin(kinds, ("CE.READ", "CE.SCRUB"))).sum())
    days = sorted({key[0] for key in counts})
    return {"name": name, "alarm": alarm, "first_log": first, "audit": dict(audit),
            "days": [[day, counts[(day, 0)], counts[(day, 1)]] for day in days]}


def extract(config):
    archive = AUDIT / "smartmem.zip"
    receipt = json.loads((AUDIT / "smartmem.zip-receipt.json").read_text())
    if file_hash(archive) != receipt["sha256"]:
        raise ValueError("The SmartMem source checksum changed.")
    settings = read_yaml(CONFIG)["smartmem"]
    directory = Path("data/components/raw/smartmem-component-v1")
    if directory.exists():
        raise FileExistsError("Inspect the existing SmartMem extraction before another run.")
    directory.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        entries = [item for item in source.infolist() if item.filename.endswith(".csv") and "/sn_" in item.filename]
        if len({x.filename for x in entries}) != len(entries):
            raise ValueError("The SmartMem archive has duplicate member identities.")
        selected = []
        for split, limit in settings["device_limits"].items():
            candidates = [x for x in entries if partition(x.filename, config) == split]
            candidates.sort(key=lambda x: hashlib.sha256((settings["cohort_hash_salt"] + x.filename).encode()).digest())
            if len(candidates) < limit:
                raise ValueError("SmartMem has too few source devices for the declared cohort.")
            selected.extend(candidates[:limit])
        declared_bytes = sum(x.file_size for x in selected)
        if declared_bytes > 60_000_000_000:
            raise ValueError("The SmartMem cohort exceeds its 60 GB streaming read limit.")
        write_json(directory / "cohort.json", {"config_sha256": file_hash(CONFIG), "archive_sha256": receipt["sha256"],
                   "selection": "Fixed DIMM filename hashes within disjoint device buckets, before reading log values or tickets",
                   "members": [x.filename for x in selected], "uncompressed_bytes": declared_bytes})
        with source.open("failure_ticket.csv") as stream:
            tickets = pcsv.read_csv(stream).to_pylist()
        alarms = {}
        for row in tickets:
            name = f"type_{row['sn_type']}/{row['sn_name']}.csv"
            when = int(row["alarm_time"])
            alarms[name] = min(when, alarms.get(name, when))
    schema = pa.schema([("name", pa.string()), ("alarm", pa.int64()), ("first_log", pa.int64()),
                        ("day", pa.int64()), ("read_error_logs", pa.int64()), ("scrub_error_logs", pa.int64())])
    audit = Counter()
    output = directory / "daily-log-counts.parquet"
    with pq.ParquetWriter(output, schema, compression="zstd") as writer, ProcessPoolExecutor(
            max_workers=4, initializer=initialize_worker, initargs=(str(archive),)) as pool:
        for i, result in enumerate(pool.map(count_device, [(x.filename, alarms.get(x.filename)) for x in selected], chunksize=8)):
            audit.update(result["audit"])
            audit["source_devices"] += 1
            records = [{"name": result["name"], "alarm": result["alarm"], "first_log": result["first_log"],
                        "day": day, "read_error_logs": read, "scrub_error_logs": scrub} for day, read, scrub in result["days"]]
            if records:
                writer.write_table(pa.Table.from_pylist(records, schema=schema))
            if (i + 1) % 500 == 0:
                write_json(directory / "progress.json", dict(audit))
                print(json.dumps({"phase": "log_count_extraction", **dict(audit)}), flush=True)
    write_json(directory / "manifest.json", {"cohort_sha256": file_hash(directory / "cohort.json"),
               "daily_counts_sha256": file_hash(output), "audit": dict(audit)})
    return output


def windows(path, config, audit):
    settings = read_yaml(CONFIG)["smartmem"]
    with duckdb.connect() as con:
        con.execute("SET threads=4")
        grouped = con.execute("""SELECT name, any_value(alarm), min(first_log),
                 list(struct_pack(day := day, read_error_logs := read_error_logs, scrub_error_logs := scrub_error_logs) ORDER BY day)
                 FROM read_parquet(?) GROUP BY name ORDER BY name""", [str(path)])
        while found := grouped.fetchone():
            name, alarm, first_log, records = found
            split = partition(name, config)
            start, stop = time_bounds(split, config)
            counts = {row["day"]: [row["read_error_logs"], row["scrub_error_logs"]] for row in records}
            previous = None
            for day in sorted(counts):
                cutoff = (day + 1) * DAY_US
                origin = (day - 26) * DAY_US
                if not start <= origin <= cutoff < stop or origin < first_log * 1_000_000:
                    audit["cutoffs_outside_time_or_before_history"] += 1
                    continue
                if alarm is not None and cutoff >= alarm * 1_000_000:
                    audit["cutoffs_at_after_failure_ticket"] += 1
                    continue
                if previous is not None and day - previous < settings["stride_days"]:
                    continue
                days = range(day-27, day+1)
                times = [(d+1)*DAY_US for d in days]
                values = np.asarray([counts.get(d, [0, 0]) for d in days], dtype=np.float64).T
                yield make_window("smartmem:" + name, name, times, values, list(config["channels"]), config)
                previous = day


def prepare(output):
    config = specification()
    path = extract(config)
    sources = {"archive_receipt": json.loads((AUDIT / "smartmem.zip-receipt.json").read_text()),
               "extraction_manifest": json.loads((path.parent / "manifest.json").read_text()),
               "cohort": json.loads((path.parent / "cohort.json").read_text()),
               "availability": config["availability"], "scope": config["scope"]}
    audit = Counter()
    result = build(output, windows(path, config, audit), config, sources)
    result["source_audit"] = dict(audit)
    write_json(output / "dataset-manifest.json", result)
    print(json.dumps({"audit": result["audit"], "groups": {s: len(v) for s, v in result["groups"].items()},
                      "manifest_sha256": file_hash(output / "dataset-manifest.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output)
