"""Prepare dated component signals for explicitly bounded industrial studies."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv

from driftops.acquire import write_json
from driftops.component_data import build, make_window, partition
from driftops.full_archive import file_hash
from driftops.prepare_components import AUDIT, time_bounds
from driftops.windows import read_yaml


CONFIG = Path("config/industrial_studies.yaml")


def windows(device, group, times, values, config, audit, observed=None):
    split = partition(group, config)
    first, stop = time_bounds(split, config)
    if len(times) != len(values) or np.any(np.diff(times) <= 0):
        raise ValueError("Industrial source timestamps must be unique and ordered.")
    valid = np.isfinite(values).all(axis=1) & (times >= first) & (times < stop)
    if observed is not None:
        valid &= observed
    audit["excluded_rows"] += int((~valid).sum())
    segment = []
    for index in range(len(times)):
        if not valid[index]:
            segment = []
            continue
        if segment and times[index] - times[segment[-1]] != config["cadence_us"]:
            segment = []
            audit["calendar_gaps"] += 1
        segment.append(index)
        if len(segment) == 28:
            yield make_window(device, group, times[segment], values[segment].T, list(config["channels"]), config)
            segment = []


def csv_header(stream):
    comments = []
    for _ in range(30):
        line = stream.readline(64_001)
        if len(line) > 64_000:
            raise ValueError("An industrial CSV header exceeds its size bound.")
        if line.startswith(b"# Date and time,"):
            if b"# Time zone: UTC" not in comments:
                raise ValueError("The turbine CSV does not declare UTC.")
            return line
        comments.append(line.strip())
    raise ValueError("The turbine CSV lacks its declared header.")


def turbine_windows(config, audit, source_manifest):
    fields = [spec["source_column"] for spec in config["channels"].values()]
    pattern = re.compile(r"Turbine_Data_(Kelmarsh|Penmanshiel)_([0-9]{1,2})_(20[0-9]{2})-01-01_-_20[0-9]{2}-01-01_[0-9]+\.csv")
    for item in source_manifest["files"]:
        if not item["name"].endswith(".zip"):
            continue
        path = AUDIT / item["name"]
        receipt = json.loads((AUDIT / (item["name"] + "-receipt.json")).read_text())
        if file_hash(path) != receipt["sha256"]:
            raise ValueError("An industrial source archive checksum changed.")
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                match = pattern.fullmatch(member.filename)
                if not match:
                    continue
                site, number, year = match.groups()
                group = f"cubico:{site}:{int(number)}"
                split = partition(group, config)
                required_year = {"train": "2018", "validation": "2019", "calibration": "2019", "test": "2020"}[split]
                if year != required_year:
                    continue
                if not 0 < member.file_size <= 512_000_000:
                    raise ValueError("A turbine source member exceeds its size bound.")
                with archive.open(member) as stream:
                    header = csv_header(stream)
                    names = next(csv.reader([header.decode("utf-8")]))
                    if any(field not in names for field in fields):
                        audit["units_missing_channels"] += 1
                        continue
                    table = pacsv.read_csv(io.BytesIO(header + stream.read()), convert_options=pacsv.ConvertOptions(
                        include_columns=["# Date and time", *fields],
                        column_types={"# Date and time": pa.timestamp("us"), **{f: pa.float64() for f in fields}},
                        null_values=["NaN", "nan", "", "NA"]))
                if table["# Date and time"].null_count:
                    raise ValueError("A turbine observation lacks its timestamp.")
                times = table["# Date and time"].cast(pa.int64()).to_numpy() + config["cadence_us"]
                values = np.column_stack([table[field].to_numpy() for field in fields])
                order = np.argsort(times, kind="stable")
                audit["source_rows"] += len(times)
                yield from windows(group + ":" + config["component"], group, times[order], values[order], config, audit)
        print(json.dumps({"industrial_archive_prepared": item["name"], "component": config["component"]}), flush=True)


def valve_windows(config, audit):
    variables = [spec["source_variable"] for spec in config["channels"].values()]
    for group in config["group_partitions"]:
        path = AUDIT / ("homesense-" + group.split(":")[1] + ".csv")
        receipt = json.loads((AUDIT / (path.name + "-receipt.json")).read_text())
        if file_hash(path) != receipt["sha256"]:
            raise ValueError("A valve source checksum changed.")
        with path.open() as stream:
            header = next(csv.reader(stream))
        prefixes = sorted({name.removesuffix("__motorposition") for name in header if name.endswith("__vicki__motorposition")})
        columns = ["timestamp_nl", *[prefix + "__" + variable + suffix
                    for prefix in prefixes for variable in variables for suffix in ("", "__qc")]]
        if any(name not in header for name in columns):
            raise ValueError("The valve source lacks a required channel or quality flag.")
        table = pacsv.read_csv(path, convert_options=pacsv.ConvertOptions(include_columns=columns,
            column_types={name: pa.string() if name == "timestamp_nl" or name.endswith("__qc") else pa.float64() for name in columns}))
        times = []
        for value in table["timestamp_nl"].to_pylist():
            stamp = datetime.fromisoformat(value)
            if stamp.utcoffset() is None:
                raise ValueError("A valve timestamp lacks its UTC offset.")
            times.append(int(stamp.astimezone(timezone.utc).timestamp() * 1e6) + config["cadence_us"])
        times = np.asarray(times, dtype=np.int64)
        for prefix in prefixes:
            values = np.column_stack([table[prefix + "__" + v].to_numpy() for v in variables])
            observed = np.column_stack([np.asarray(table[prefix + "__" + v + "__qc"].to_pylist()) == "observed" for v in variables]).all(axis=1)
            observed &= (values[:, 0] >= 0) & (values[:, 0] <= 800)
            audit["source_device_rows"] += len(times)
            yield from windows(group + ":" + prefix, group, times, values, config, audit, observed)
        print(json.dumps({"valve_household_prepared": group, "valves": len(prefixes)}), flush=True)


def prepare(component, output):
    config = read_yaml(CONFIG)["components"][component]
    source_manifest = json.loads((AUDIT / "industrial-source-manifest.json").read_text())
    audit = Counter()
    producer = valve_windows(config, audit) if component == "valve" else turbine_windows(config, audit, source_manifest)
    sources = {"study_config_sha256": file_hash(CONFIG), "source_manifest": source_manifest if component != "valve" else
               json.loads((AUDIT / "industrial-observed-telemetry-audit-v2.json").read_text())}
    result = build(output, producer, config, sources)
    result["source_audit"] = dict(audit)
    write_json(output / "dataset-manifest.json", result)
    print(json.dumps({"component": component, "audit": result["audit"], "groups": {s: len(v) for s,v in result["groups"].items()},
                      "manifest_sha256": file_hash(output / "dataset-manifest.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["gearbox", "bearing", "pump", "valve"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.component, args.output)
