"""Convert public Ceph NVMe reports into separate, dated component windows."""

import argparse
from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from uuid import UUID
import zipfile

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from driftops.acquire import write_json
from driftops.component_data import build, make_window, partition
from driftops.full_archive import file_hash
from driftops.prepare_components import AUDIT, CONFIG, DAY_US, time_bounds
from driftops.windows import read_yaml


FIELDS = ("temperature", "media_errors", "power_on_hours", "percentage_used")
SCHEMA = pa.schema([("device", pa.string()), ("host", pa.string()), ("model", pa.string()),
                    ("timestamp_s", pa.int64()), *[(c, pa.int64()) for c in FIELDS]])


def specification(config_path=CONFIG):
    settings = read_yaml(config_path)
    rule = settings["ceph"]
    definitions = [("celsius", "NVMe composite temperature in Celsius", False),
                   ("count", "cumulative media and data integrity error count", True),
                   ("hour", "cumulative NVMe power-on hours", True),
                   ("percent", "estimated NVMe endurance used in percent", True)]
    return {"version": settings["version"], "component": "nvme", "scope": settings["scope"],
        "split_salt": rule["split_salt"], "availability": rule["availability"], "stride_days": rule["stride_days"],
        "partitions": {name: {"buckets": settings["split_buckets"][name], "start": bounds[0], "stop": bounds[1]}
                       for name, bounds in rule["time_intervals"].items()},
        "provider": "Ceph", "source_type": "ceph-nvme-telemetry", "source_url": "https://ceph.io/en/users/telemetry/device-telemetry/",
        "license": "CDLA-Sharing-1.0", "timef_license": "other", "license_url": "https://cdla.dev/sharing-1-0/",
        "citation": f"Ceph device telemetry, {rule['source_first_month']} through {rule['source_last_month']}",
        "cadence_us": DAY_US, "cadence_text": "last valid daily report available at the next UTC midnight",
        "channels": {c: {"unit": unit, "description": description, "counter": counter, "minimum_band": 1.}
                     for c, (unit, description, counter) in zip(FIELDS, definitions)}}


def report_row(row, month, audit):
    audit["source_reports"] += 1
    if row["invalid"] != "f":
        audit["invalid_collection_reports"] += 1
        return None
    if '"nvme_smart_health_information_log"' not in row["report"]:
        audit["other_device_reports"] += 1
        return None
    try:
        report = json.loads(row["report"])
        health = report["nvme_smart_health_information_log"]
        device, host = str(UUID(row["device_uuid"])), str(UUID(report["host_id"]))
        when = datetime.fromisoformat(row["ts"])
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when = when.astimezone(timezone.utc)
        if when.strftime("%Y-%m") != month:
            raise ValueError("The report timestamp is outside its source month.")
        values = [health[c] for c in FIELDS]
        if any(type(v) is not int or abs(v) > 2**53 for v in values):
            raise ValueError("A required NVMe field is not an exact, finite integer.")
        if not -100 <= values[0] <= 200 or min(values[1:]) < 0 or values[3] > 255:
            raise ValueError("An NVMe field is outside its declared encoding range.")
        if report.get("device", {}).get("protocol") != "NVMe" or not isinstance(report.get("model_name"), str):
            raise ValueError("The report lacks a verified NVMe device identity.")
    except (KeyError, ValueError, TypeError, AttributeError):
        audit["nvme_reports_with_invalid_identity_time_or_fields"] += 1
        return None
    audit["eligible_nvme_reports"] += 1
    return {"device": device, "host": host, "model": report["model_name"], "timestamp_s": int(when.timestamp()),
            **dict(zip(FIELDS, values))}


def extract_month(item):
    archive, output, digest = item
    archive, output = Path(archive), Path(output)
    if file_hash(archive) != digest:
        raise ValueError("A Ceph source checksum changed.")
    if output.exists():
        raise FileExistsError("Inspect the existing Ceph month extraction before another run.")
    month = archive.stem[-6:-2] + "-" + archive.stem[-2:]
    audit, buffer = Counter(), []
    csv.field_size_limit(32 * 1024 * 1024)
    with zipfile.ZipFile(archive) as source, pq.ParquetWriter(output, SCHEMA, compression="zstd") as writer:
        names = [n for n in source.namelist() if n.endswith(".csv")]
        if len(names) != 1:
            raise ValueError("Each Ceph monthly archive must contain one CSV file.")
        with source.open(names[0]) as stream:
            for raw in csv.DictReader(io.TextIOWrapper(stream)):
                row = report_row(raw, month, audit)
                if row is not None:
                    buffer.append(row)
                if len(buffer) == 8192:
                    writer.write_table(pa.Table.from_pylist(buffer, schema=SCHEMA))
                    buffer = []
        if buffer:
            writer.write_table(pa.Table.from_pylist(buffer, schema=SCHEMA))
    result = {"source": archive.name, "source_sha256": digest, "output_sha256": file_hash(output), "audit": dict(audit)}
    write_json(output.with_suffix(".json"), result)
    return result


def connected_groups(edges):
    """Keep every device and every host connected by a migration in one split."""
    parents = {}
    def find(node):
        parents.setdefault(node, node)
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node
    for device, host in edges:
        left, right = find("d:" + device), find("h:" + host)
        if left != right:
            parents[max(left, right)] = min(left, right)
    hosts = defaultdict(set)
    for _, host in edges:
        hosts[find("h:" + host)].add(host)
    names = {root: "ceph-host-group:" + hashlib.sha256("|".join(sorted(values)).encode()).hexdigest()
             for root, values in hosts.items()}
    return {device: names[find("d:" + device)] for device, _ in edges}


def windows(directory, config, audit):
    stride = config["stride_days"]
    with duckdb.connect() as con:
        con.execute("SET threads=4")
        con.execute("SET memory_limit='8GB'")
        con.read_parquet([str(p) for p in sorted(directory.glob("*.parquet"))]).create_view("reports")
        edges = con.execute("SELECT DISTINCT device,host FROM reports ORDER BY device,host").fetchall()
        groups = connected_groups(edges)
        write_json(directory / "device-groups.json", groups)
        conflicts = {r[0] for r in con.execute("SELECT device FROM reports GROUP BY device HAVING count(DISTINCT model)>1").fetchall()}
        fields = ", ".join(FIELDS)
        for (device,) in con.execute(f"""SELECT DISTINCT device FROM (
            SELECT device,timestamp_s FROM reports GROUP BY device,timestamp_s
            HAVING count(DISTINCT ({fields}))>1)""").fetchall():
            conflicts.add(device)
        audit["devices_with_model_or_duplicate_value_conflicts"] = len(conflicts)
        expressions = ", ".join(f"{c} := {c}" for c in FIELDS)
        grouped = con.execute(f"""SELECT device, list(struct_pack(day := day, {expressions}) ORDER BY day)
            FROM (SELECT *, timestamp_s // 86400 AS day FROM reports
                  QUALIFY row_number() OVER(PARTITION BY device,timestamp_s // 86400 ORDER BY timestamp_s DESC,host)=1)
            GROUP BY device ORDER BY device""")
        while found := grouped.fetchone():
            device, rows = found
            if device in conflicts:
                continue
            group = groups[device]
            first, stop = time_bounds(partition(group, config), config)
            segment = deque(maxlen=28)
            previous = None
            for row in rows:
                available = (row["day"] + 1) * DAY_US
                if not first <= available < stop:
                    audit["daily_rows_outside_time"] += 1
                    segment.clear()
                    continue
                if segment and row["day"] - segment[-1]["day"] != 1:
                    audit["calendar_gaps"] += 1
                    segment.clear()
                segment.append(row)
                if len(segment) == 28 and (previous is None or row["day"] - previous >= stride):
                    values = np.array([[r[c] for r in segment] for c in FIELDS], dtype=np.float64)
                    yield make_window("ceph-nvme:" + device, group, [(r["day"]+1)*DAY_US for r in segment], values, list(FIELDS), config)
                    previous = row["day"]


def prepare(output, reuse_extraction=False, config_path=CONFIG):
    config = specification(config_path)
    directory = Path("data/components/raw") / ("ceph-nvme-" + config["version"])
    if directory.exists() and not reuse_extraction:
        raise FileExistsError("Inspect the existing Ceph extraction before another run.")
    if not reuse_extraction:
        directory.mkdir(parents=True)
    manifest = json.loads((AUDIT / read_yaml(config_path)["ceph"].get("cohort_manifest", "ceph-cohort-manifest.json")).read_text())
    inputs = []
    for item in manifest["files"]:
        receipt = json.loads((AUDIT / (item["name"] + "-receipt.json")).read_text())
        inputs.append((str(AUDIT / item["name"]), str(directory / (Path(item["name"]).stem + ".parquet")), receipt["sha256"]))
    results = []
    pending = []
    if reuse_extraction:
        for _, path, digest in inputs:
            path = Path(path)
            if not path.exists() and not path.with_suffix(".json").exists():
                pending.append(next(item for item in inputs if item[1] == str(path)))
                continue
            result = json.loads(path.with_suffix(".json").read_text())
            if result["source_sha256"] != digest or result["output_sha256"] != file_hash(path):
                raise ValueError("The saved Ceph extraction does not match its source or output checksum.")
            results.append(result)
    else:
        pending = inputs
    if pending:
        with ProcessPoolExecutor(max_workers=4) as pool:
            for result in pool.map(extract_month, pending):
                results.append(result)
                print(json.dumps(result), flush=True)
    sources = {"cohort": manifest, "extractions": results, "preparation_config_sha256": file_hash(config_path),
               "unit_reference": json.loads((AUDIT / "smartmontools-nvme-receipt.json").read_text()),
               "timestamp_reference": json.loads((AUDIT / "ceph-devicehealth-receipt.json").read_text()),
               "availability": config["availability"], "failure_labels": "Not provided by Ceph"}
    audit = Counter()
    result = build(output, windows(directory, config, audit), config, sources)
    result["source_audit"] = dict(audit)
    result["device_group_manifest_sha256"] = file_hash(directory / "device-groups.json")
    write_json(output / "dataset-manifest.json", result)
    print(json.dumps({"audit": result["audit"], "groups": {s: len(v) for s, v in result["groups"].items()},
                      "manifest_sha256": file_hash(output / "dataset-manifest.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-extraction", action="store_true", help="Verify complete cached months and extract missing months")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    prepare(args.output, args.reuse_extraction, args.config)
