"""Causal component windows with native TimeF round-trip verification."""

from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from timenet.dataset import TimeFDataset, TimeSeries
from timenet.reader import TimeFReader
from timenet.registry.version import DatasetVersion
from timenet.types import Annotation, AnswerTask, DataSource, TimeInterval, TimeSeriesSpec, Version
from timenet.writer import TimeFWriter

from driftops.acquire import write_json
from driftops.full_archive import file_hash
from driftops.timenet_connector import BackblazeConnector, stable_id
from driftops.tslm_dataset import PATTERNS, input_hash


SPLITS = ("train", "validation", "calibration", "test")
SCHEMA = pa.schema([
    ("task_id", pa.string()), ("drive_id", pa.string()), ("group_id", pa.string()),
    ("split", pa.string()), ("start", pa.timestamp("us", tz="UTC")),
    ("cutoff", pa.timestamp("us", tz="UTC")), ("times_us", pa.list_(pa.int64(), 28)),
    ("channels", pa.list_(pa.string())), ("values", pa.list_(pa.list_(pa.float64(), 28))),
    ("target", pa.string()),
])


def partition(identity, config):
    if "group_partitions" in config:
        split = config["group_partitions"].get(identity)
        if split not in SPLITS:
            raise ValueError("The component identity lacks a declared study partition.")
        return split
    bucket = int(hashlib.sha256((config["split_salt"] + identity).encode()).hexdigest()[:8], 16) % 100
    found = [name for name, rule in config["partitions"].items()
             if rule["buckets"][0] <= bucket < rule["buckets"][1]]
    if len(found) != 1:
        raise ValueError("Each component identity must have exactly one split.")
    return found[0]


def target(values, channels, config):
    values = np.asarray(values, dtype=np.float64)
    if values.shape != (len(channels), 28) or not np.isfinite(values).all():
        raise ValueError("Each component channel must contain 28 finite observations.")
    output = []
    for channel, row in zip(channels, values):
        spec = config["channels"][channel]
        span = np.ptp(row)
        change = np.median(row[-7:]) - np.median(row[:7])
        band = max(spec["minimum_band"], span * .1)
        label = (4 if spec.get("counter") and np.any(np.diff(row) < 0) else
                 0 if span == 0 else 1 if change >= band else 2 if change <= -band else 3)
        output.append(f"{channel}: {PATTERNS[label]}")
    return "; ".join(output) + "."


def make_window(device, group, times_us, values, channels, config):
    times = np.asarray(times_us, dtype=np.int64)
    if times.shape != (28,) or np.any(np.diff(times) <= 0):
        raise ValueError("Component observation times must increase across 28 samples.")
    if config.get("cadence_us") and np.any(np.diff(times) != config["cadence_us"]):
        raise ValueError("A component window contains a calendar gap.")
    if len(channels) < 2 or len(set(channels)) != len(channels) or any(c not in config["channels"] for c in channels):
        raise ValueError("Component channels must match the declared allowlist.")
    split = partition(group, config)
    rule = config["partitions"][split]
    start, cutoff = [datetime.fromtimestamp(int(v) / 1e6, tz=timezone.utc) for v in (times[0], times[-1])]
    first, stop = datetime.fromisoformat(rule["start"]), datetime.fromisoformat(rule["stop"])
    if not first <= start <= cutoff < stop:
        raise ValueError("A component window crosses its split time boundary.")
    values = np.asarray(values, dtype=np.float64)
    answer = target(values, channels, config)
    return {"task_id": stable_id(config["version"], config["component"], device, str(times[0]), str(times[-1])),
            "drive_id": device, "group_id": group, "split": split, "start": start, "cutoff": cutoff,
            "times_us": times.tolist(), "channels": list(channels), "values": values.tolist(), "target": answer}


def example(row, config):
    """Expose observed values and channel semantics, with no identity or outcome fields."""
    values = np.asarray(row["values"], dtype=np.float64)
    # Recompute the weak target only to reject corrupt prepared data. It is never an input.
    if target(values, row["channels"], config) != row["target"]:
        raise ValueError("The prepared component target does not match its observations.")
    std = values.std(axis=1, ddof=1, keepdims=True)
    normalized = (values - values.mean(axis=1, keepdims=True)) / np.where(std > 1e-8, std, 1.)
    inputs = {
        "pre_prompt": f"Describe each {config['component']} signal over the entire observed 28-sample window. "
                      "Use only these patterns: " + "; ".join(PATTERNS) + ".",
        "time_series_text": [f"{c}; {config['channels'][c]['description']}; {config['cadence_text']}; "
                             f"original standard deviation: {s:.8g}." for c, s in zip(row["channels"], std[:, 0])],
        "time_series": normalized.astype(np.float32).tolist(),
        "post_prompt": "Answer with one 'channel: pattern' entry per supplied channel, separated by semicolons. Answer:",
    }
    def iso(value):
        return value.isoformat() if hasattr(value, "isoformat") else value
    return {"inputs": inputs, "target": row["target"], "raw_values": values.tolist(),
            "audit": {"task_id": row["task_id"], "drive_id": row["drive_id"], "group_id": row["group_id"],
                      "start": iso(row["start"]), "cutoff": iso(row["cutoff"]), "input_hash": input_hash(inputs)}}


def write_shard(root, index, rows, config, source_hash):
    """Serialize each selected observed window and verify every native scoped input."""
    name = f"{index:04d}"
    metadata = replace(BackblazeConnector().metadata(),
        dataset_id=f"driftops/{config['component']}-{config['version']}-{name}", dataset_version=Version(0, 1, 0),
        name=f"DriftOps {config['component']} observed windows", description=config["scope"],
        license=config.get("timef_license", config["license"]), license_url=config["license_url"], source_url=config["source_url"],
        citation=config["citation"], tags=(config["component"], "time-series", "weak-supervision"))
    dataset = TimeFDataset(metadata=metadata)
    source = DataSource(data_source_type=config["source_type"], name=config["citation"], provider=config["provider"])
    original = {}
    for row in rows:
        record_id = row["task_id"]
        offsets = np.asarray(row["times_us"], dtype=np.int64) - row["times_us"][0]
        series = []
        for channel, values in zip(row["channels"], row["values"]):
            spec = TimeSeriesSpec(spec_type=channel, name=channel, unit_value=config["channels"][channel]["unit"],
                                  dtype="float64", nullable=False, data_source=source)
            series.append(TimeSeries.from_irregular(values, time_offsets_us=offsets.tolist(), spec=spec,
                signal=channel, source_id=source_hash, time_series_id=stable_id(record_id, channel)))
        record = dataset.add_record(record_id=record_id, subject_ids=(row["drive_id"], row["group_id"]),
                                    start_time=row["start"], time_series=tuple(series))
        annotations = {"partition": row["split"], "source_manifest_sha256": source_hash,
                       "annotation_method": "component-window-description-v1"}
        if "clock_semantics" in config:
            annotations["clock_semantics"] = config["clock_semantics"]
        for key, value in annotations.items():
            record.add_annotation(Annotation(key=key, value=value, source=config["source_url"],
                                  id=stable_id(record_id, key)), warn_when_outside=False)
        scope = TimeInterval.micros(0, int(offsets[-1]) + 1,
                                   time_series_ids=tuple(s.time_series_id for s in series))
        dataset.add_task(record, AnswerTask(id=record_id, prompt=example(row, config)["inputs"]["pre_prompt"],
                                          scope=scope, target=row["target"]))
        original[record_id] = record
    with TimeFWriter(root / "timef", dataset) as writer:
        writer.write()
    version = root / "timef" / metadata.dataset_id / "0.1.0"
    restored = TimeFReader(DatasetVersion.open_local(version)).read()
    if len(restored.records) != len(rows) or len(restored.tasks) != len(rows):
        raise ValueError("Native TimeF changed the component record or task count.")
    records = {record.record_id: record for record in restored.records}
    tasks = {task.id: task for task in restored.tasks}
    originals = {task.id: task for task in dataset.tasks}
    for row in rows:
        before, after = original[row["task_id"]], records[row["task_id"]]
        if (before.subject_ids, before.start_time, before.annotations) != (after.subject_ids, after.start_time, after.annotations):
            raise ValueError("Native TimeF changed component identity or annotations.")
        task, old_task = tasks[row["task_id"]], originals[row["task_id"]]
        if (task.target, task.scope, task.record_ids, task.prompt) != (old_task.target, old_task.scope, old_task.record_ids, old_task.prompt):
            raise ValueError("Native TimeF changed a component task.")
        if len(before.time_series) != len(after.time_series):
            raise ValueError("Native TimeF changed the component channel count.")
        for a, b, values in zip(before.time_series, after.time_series, row["values"]):
            left, right = b.step_range(task.scope)
            if (a.signal, a.spec, a.time_series_id) != (b.signal, b.spec, b.time_series_id):
                raise ValueError("Native TimeF changed a component channel specification.")
            if not a.to_arrow().equals(b.to_arrow()) or not np.array_equal(a.time_offsets_us(), b.time_offsets_us()):
                raise ValueError("Native TimeF changed component values or observation times.")
            if b.read_steps(left, right).to_pylist() != values:
                raise ValueError("Native TimeF changed a scoped component input.")
    directory = root / "prepared" / name
    directory.mkdir(parents=True)
    result = {}
    for split in SPLITS:
        path = directory / (split + ".parquet")
        pq.write_table(pa.Table.from_pylist([r for r in rows if r["split"] == split], schema=SCHEMA), path,
                       compression="zstd", row_group_size=1024)
        result[path.name] = file_hash(path)
    result["native_manifest_sha256"] = file_hash(version / "manifest.json")
    return name, result


def build(root, windows, config, sources, audit=None):
    """Publish a manifest only after complete split and native serialization checks."""
    root = Path(root)
    if root.exists():
        raise FileExistsError("The component output already exists. Use a new version or inspect the partial build.")
    root.mkdir(parents=True)
    write_json(root / "source-manifest.json", sources)
    source_hash = file_hash(root / "source-manifest.json")
    write_json(root / "config.json", config)
    counts = Counter(audit or {})
    drives, groups, shards, buffer = ({s: set() for s in SPLITS}, {s: set() for s in SPLITS}, {}, [])
    seen = set()
    for row in windows:
        checked = make_window(row["drive_id"], row["group_id"], row["times_us"], row["values"], row["channels"], config)
        if checked != row or row["task_id"] in seen:
            raise ValueError("A component window changed or has a duplicate identity.")
        seen.add(row["task_id"])
        split = row["split"]
        drives[split].add(row["drive_id"])
        groups[split].add(row["group_id"])
        for other in SPLITS:
            if other != split and (row["drive_id"] in drives[other] or row["group_id"] in groups[other]):
                raise ValueError("Component devices or groups overlap dataset splits.")
        counts["windows_" + split] += 1
        for entry in row["target"].rstrip(".").split("; "):
            counts[f"patterns_{split}:" + entry.split(": ", 1)[1]] += 1
        buffer.append(row)
        if len(buffer) == 2048:
            name, checksums = write_shard(root, len(shards), buffer, config, source_hash)
            shards[name] = checksums
            buffer = []
            write_json(root / "progress.json", {"shards": len(shards), "audit": dict(counts)})
    if buffer:
        name, checksums = write_shard(root, len(shards), buffer, config, source_hash)
        shards[name] = checksums
    required = SPLITS
    if config.get("study") in ("slider-audio-benchmark-v1", "valve-audio-benchmark-v1"):
        from driftops.slider_data import validate_config
        validate_config(config)
        required = ("train", "validation", "test")
        if counts["windows_calibration"] or groups["calibration"]:
            raise ValueError("The sound benchmark has no calibration partition.")
    if not all(counts["windows_" + s] > 0 for s in required):
        raise ValueError("A required component data split has no eligible windows.")
    result = {"format": "component-windows-v1", "config": config, "source_manifest_sha256": source_hash,
              "audit": dict(counts), "drives": {s: sorted(v) for s, v in drives.items()},
              "groups": {s: sorted(v) for s, v in groups.items()}, "shards": shards,
              "verification": "Every native record, value, timestamp, annotation, task, and scoped input matched."}
    write_json(root / "dataset-manifest.json", result)
    return result
