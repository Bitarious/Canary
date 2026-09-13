"""Prepare separate fan-module histories from pinned Marconi100 telemetry."""

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from driftops.acquire import write_json
from driftops.component_data import build, make_window, partition
from driftops.full_archive import file_hash
from driftops.prepare_components import AUDIT, time_bounds
from driftops.windows import read_yaml


CONFIG = Path("config/fan_component_v1.yaml")


def identity(name):
    if not re.fullmatch(r"[0-9]{1,4}\.parquet", name):
        raise ValueError("A fan source member lacks a valid node identity.")
    return "m100:node-" + str(int(Path(name).stem))


def cohort(config, sources):
    inventory = {}
    for item in sources["files"]:
        path = AUDIT / item["name"]
        receipt = json.loads((AUDIT / (item["name"] + "-receipt.json")).read_text())
        if file_hash(path) != receipt["sha256"]:
            raise ValueError("A fan source archive checksum changed.")
        if item["name"] == "m100-0.tar":
            continue
        with tarfile.open(path) as archive:
            for member in archive:
                if not member.isfile() or not 1 <= member.size <= 100_000_000:
                    raise ValueError("A fan source archive contains an unsupported member.")
                group = identity(member.name)
                if group in inventory:
                    raise ValueError("The fan source repeats a node across archives.")
                inventory[group] = {"archive": item["name"], "member": member.name}
    selected = {}
    for split, limit in config["host_limits"].items():
        groups = [g for g in inventory if partition(g, config) == split]
        groups.sort(key=lambda value: hashlib.sha256(("m100-fan-cohort-v1:" + value).encode()).digest())
        selected.update({g: {**inventory[g], "split": split} for g in groups[:limit]})
    return selected


def module_windows(group, module, times, values, config, audit):
    split = partition(group, config)
    first, stop = time_bounds(split, config)
    cadence = config["cadence_us"]
    valid = ((times >= first) & (times < stop) & np.isfinite(values).all(axis=1)
             & (values >= 0).all(axis=1) & (values <= 100_000).all(axis=1))
    audit["module_rows_outside_time_or_invalid"] += int((~valid).sum())
    candidates, segment = [], []
    for index in range(len(times)):
        if not valid[index]:
            segment = []
            continue
        if segment and times[index] - times[segment[-1]] != cadence:
            audit["calendar_gaps"] += 1
            segment = []
        segment.append(index)
        if len(segment) == 28:
            key = hashlib.sha256(f"m100-fan-window-v1:{group}:{module}:{times[segment[0]]}".encode()).digest()
            candidates.append((key, segment))
            segment = []
    audit[f"eligible_natural_windows_{split}"] += len(candidates)
    candidates.sort(key=lambda value: value[0])
    for _, indices in candidates[:config["windows_per_module"][split]]:
        yield make_window(f"{group}:fan-module-{module}", group, times[indices], values[indices].T,
                          list(config["channels"]), config)


def windows(selected, config, audit):
    columns = ["timestamp", *[f"fan{x}_{y}_avg" for x in range(4) for y in range(2)]]
    for archive_name in sorted({entry["archive"] for entry in selected.values()}):
        wanted = {entry["member"]: group for group, entry in selected.items() if entry["archive"] == archive_name}
        with tarfile.open(AUDIT / archive_name) as archive:
            for member in archive:
                if member.name not in wanted:
                    continue
                group = wanted[member.name]
                content = archive.extractfile(member).read()
                parquet = pq.ParquetFile(io.BytesIO(content))
                if any(name not in parquet.schema_arrow.names for name in columns):
                    audit["hosts_missing_fan_channels"] += 1
                    continue
                if parquet.schema_arrow.field("timestamp").type != pa.timestamp("us", tz="UTC"):
                    raise ValueError("The fan source clock does not match the declared UTC schema.")
                table = parquet.read(columns=columns)
                if table["timestamp"].null_count:
                    raise ValueError("A fan observation lacks its source timestamp.")
                times = table["timestamp"].cast(pa.int64()).to_numpy() + config["cadence_us"]
                order = np.argsort(times, kind="stable")
                times = times[order]
                if np.any(np.diff(times) <= 0) or np.any(times % config["cadence_us"]):
                    raise ValueError("Fan observation intervals must be unique and aligned.")
                audit["source_host_rows"] += len(times)
                for module in range(4):
                    values = np.column_stack([table[f"fan{module}_{rotor}_avg"].to_numpy() for rotor in range(2)])[order]
                    yield from module_windows(group, module, times, values, config, audit)
        print(json.dumps({"fan_archive_prepared": archive_name}), flush=True)


def prepare(output):
    config = read_yaml(CONFIG)
    manifest_path = AUDIT / "m100-fan-cohort-manifest.json"
    sources = json.loads(manifest_path.read_text())
    selected = cohort(config, sources)
    audit_path = AUDIT / "m100-fan-host-cohort.json"
    record = {"config_sha256": file_hash(CONFIG), "source_manifest_sha256": file_hash(manifest_path), "selected": selected}
    if audit_path.exists() and json.loads(audit_path.read_text()) != record:
        raise ValueError("The frozen fan host cohort changed.")
    write_json(audit_path, record)
    sources = {"source_manifest": sources, "host_cohort_sha256": file_hash(audit_path), "config_sha256": file_hash(CONFIG),
               "references": {name: json.loads((AUDIT / (name + "-receipt.json")).read_text()) for name in [
                   "m100-documentation-plugins-ipmi.md", "m100-parquet_dataset-node_aggregated_data-step1.py",
                   "m100-parquet_dataset-node_aggregated_data-step2.py"]}}
    audit = Counter()
    result = build(output, windows(selected, config, audit), config, sources)
    result["source_audit"] = dict(audit)
    write_json(output / "dataset-manifest.json", result)
    print(json.dumps({"audit": result["audit"], "groups": {s: len(v) for s, v in result["groups"].items()},
                      "manifest_sha256": file_hash(output / "dataset-manifest.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output)
