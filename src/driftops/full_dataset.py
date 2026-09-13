"""Build device-disjoint historical TimeF shards and compact training windows."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import date, datetime, time, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from timenet.dataset import TimeFDataset, TimeSeries
from timenet.reader import TimeFReader
from timenet.registry.version import DatasetVersion
from timenet.types import Annotation, AnswerTask, DataSource, TimeInterval, TimePoint, TimeSeriesSpec, Version
from timenet.writer import TimeFWriter

from driftops.acquire import CHANNELS, SOURCE_URL, write_json
from driftops.annotations import ANNOTATION_VERSION, COUNTERS, QUESTION
from driftops.full_archive import file_hash
from driftops.timenet_connector import BackblazeConnector, DAY_US, model_input, stable_id, verify_roundtrip
from driftops.tslm_dataset import PATTERNS
from driftops.windows import read_yaml

CONFIG = Path("config/full_history.yaml")
WINDOW_SCHEMA = pa.schema([
    ("task_id", pa.string()), ("drive_id", pa.string()), ("start", pa.date32()),
    ("cutoff", pa.date32()), ("channels", pa.list_(pa.string())),
    ("values", pa.list_(pa.list_(pa.float64(), 28))), ("target", pa.string()),
])


def drive_partition(serial, config):
    bucket = int(hashlib.sha256((config["drive_hash_salt"] + serial).encode()).hexdigest()[:8], 16) % 100
    matches = [(name, rule) for name, rule in config["partitions"].items()
               if rule["buckets"][0] <= bucket < rule["buckets"][1]]
    if len(matches) != 1:
        raise ValueError("Every serial must belong to exactly one partition")
    return matches[0]


def media_type(model):
    model = " ".join(model.split())
    if model == "00MD00":
        return "unidentified"
    if "SSD" in model or model.startswith(("MTFD", "DELLBOSS", "WDC WDS", "Micron 5300 MTFD", "Micron 5400 MTFD", "Seagate IronWolf ZA", "WD Blue SA510")):
        return "ssd"
    if re.match(r"^(ST\d|HGST |Hitachi |TOSHIBA (DT|HD|MD|MG|MQ)|WDC (WD|WUH)|WUH721816ALE6L4$|SAMSUNG HD)", model):
        return "hdd"
    return "unknown"


def connect(root, memory_gb=12):
    connection = duckdb.connect()
    connection.execute("SET threads=4")
    connection.execute("SET memory_limit=?", [f"{memory_gb}GB"])
    temporary = root / "duckdb-temp" / str(os.getpid())
    temporary.mkdir(parents=True, exist_ok=True)
    connection.execute("SET temp_directory=?", [str(temporary)])
    connection.execute("SET preserve_insertion_order=false")
    connection.execute("SET partitioned_write_max_open_files=512")
    return connection


def shard(root):
    source = root / "records-complete.json"
    if not source.is_file():
        raise ValueError("Complete and verify all source conversions before sharding")
    pin = {"source_manifest_sha256": file_hash(source), "config_sha256": file_hash(CONFIG)}
    final = root / "shards"
    if final.exists():
        saved = json.loads((final / "manifest.json").read_text())
        if any(saved[key] != value for key, value in pin.items()):
            raise ValueError("Existing shards use a different source or split configuration")
        return
    stage = root / "shards.partial"
    if stage.exists():
        raise ValueError("An incomplete source shard directory requires recovery before retry")
    with connect(root) as con:
        con.read_parquet([str(p) for p in sorted((root / "records").glob("*.parquet")) if not p.name.endswith(".quarantine.parquet")]).create_view("raw")
        models = [{"model": model, "rows": rows, "media_type": media_type(model)} for model, rows in
                  con.execute("SELECT model,count(*) FROM raw GROUP BY model ORDER BY model").fetchall()]
        write_json(root / "model-audit.json", {"models": models, "hdd_rule": "Source model family allowlist. SSD boot drives are retained in original archives and excluded from HDD training."})
        if any(row["media_type"] == "unknown" for row in models):
            raise ValueError("Review unknown drive models in model-audit.json before proceeding")
        con.register("hdd_models", pa.Table.from_pylist([{"model": row["model"]} for row in models if row["media_type"] == "hdd"]))
        stage.mkdir()
        con.execute("""COPY (SELECT raw.*, substr(sha256(serial_number),1,2) AS bucket
                    FROM raw JOIN hdd_models USING(model)) TO ?
                    (FORMAT PARQUET, PARTITION_BY(bucket), COMPRESSION ZSTD, ROW_GROUP_SIZE 131072)""", [str(stage)])
    files = {str(p.relative_to(stage)): file_hash(p) for p in sorted(stage.rglob("*.parquet"))}
    write_json(stage / "manifest.json", {**pin, "files": files,
               "hdd_rows": sum(x["rows"] for x in models if x["media_type"] == "hdd"),
               "unidentified_rows": sum(x["rows"] for x in models if x["media_type"] == "unidentified"),
               "ssd_rows": sum(x["rows"] for x in models if x["media_type"] == "ssd")})
    stage.rename(final)


def eligible_windows(rows, rule, audit):
    """Yield complete windows before the first recorded failure and within one date interval."""
    first, last = date.fromisoformat(rule["start"]), date.fromisoformat(rule["end"])
    segment = []
    failed = False
    previous = None
    for row in rows:
        if previous is not None and row["date"] <= previous:
            raise ValueError("Drive history has duplicate or unordered dates")
        previous = row["date"]
        failed = failed or row["failure"] == 1
        if failed or not first <= row["date"] <= last:
            audit["rows_outside_time_or_at_after_failure"] += 1
            continue
        if segment and (row["date"] - segment[-1]["date"]).days != 1:
            audit["rows_in_short_segments"] += len(segment)
            segment = []
        segment.append(row)
        if len(segment) == 28:
            yield segment
            segment = []
    audit["rows_in_short_segments"] += len(segment)


def patterns(values, channels):
    """Apply the existing weak-label rules to all windows of one drive in one array."""
    span = np.ptp(values, axis=-1)
    band = np.maximum(1, span * .1)
    change = np.median(values[:, :, -7:], axis=-1) - np.median(values[:, :, :7], axis=-1)
    output = np.full(span.shape, 3, dtype=np.int8)
    output[change >= band] = 1
    output[change <= -band] = 2
    output[span == 0] = 0
    for i, channel in enumerate(channels):
        if channel in COUNTERS:
            output[np.any(np.diff(values[:, i], axis=-1) < 0, axis=-1), i] = 4
    return output


def add_drive(dataset, serial, model, rows, config, source_hash, audit):
    split, rule = drive_partition(serial, config)
    record_id = stable_id("backblaze-full", serial, model)
    origin = rows[0]["date"]
    offsets = [(r["date"] - origin).days * DAY_US for r in rows]
    source = DataSource(data_source_type="backblaze-drive-stats", name="Backblaze HDD SMART", provider="Backblaze")
    series = []
    for channel in CHANNELS:
        values = [r[channel] for r in rows]
        observed = np.asarray([v for v in values if v is not None], dtype=np.float64)
        if np.any(~np.isfinite(observed) | (np.abs(observed) > 2**53)):
            raise ValueError("SMART encoding exceeds the finite exact float64 range")
        spec = TimeSeriesSpec(spec_type=channel, name=channel, unit_value="dimensionless",
                              dtype="float64", nullable=True, data_source=source)
        series.append(TimeSeries.from_irregular(values, time_offsets_us=offsets, spec=spec,
                      signal=channel, source_id=source_hash, time_series_id=stable_id(record_id, channel)))
    record = dataset.add_record(record_id=record_id, subject_ids=(f"backblaze:{serial}",),
                  start_time=datetime.combine(origin, time.min, tzinfo=timezone.utc), time_series=tuple(series))
    for key, value in {"partition": split, "hardware_model": model, "source_manifest_sha256": source_hash,
                       "annotation_method": ANNOTATION_VERSION}.items():
        record.add_annotation(Annotation(key=key, value=value, source=SOURCE_URL, id=stable_id(record_id,key)), warn_when_outside=False)
    for row, offset in zip(rows, offsets):
        if row["failure"] == 1:
            record.add_annotation(Annotation(key="recorded_failure", value=True, span=TimePoint.micros(offset),
                     source=SOURCE_URL, id=stable_id(record_id,"failure",str(offset))), warn_when_outside=False)
    channels = config["language_channels"]
    windows = list(eligible_windows(rows, rule, audit))
    audit[f"records_{split}"] += 1
    audit["source_rows"] += len(rows)
    if not windows:
        return
    arrays = np.array([[[r[c] for r in window] for c in channels] for window in windows], dtype=np.float64)
    labels = patterns(arrays, channels)
    complete = np.isfinite(arrays).all(axis=-1)
    for window, labels_row, valid in zip(windows, labels, complete):
        if valid.sum() < 2:
            audit[f"windows_missing_channels_{split}"] += 1
            continue
        selected = [c for c, ok in zip(channels, valid) if ok]
        answer = "; ".join(f"{c}: {PATTERNS[int(label)]}" for c, label, ok in zip(channels, labels_row, valid) if ok) + "."
        scope = TimeInterval.micros((window[0]["date"]-origin).days*DAY_US,
                  (window[-1]["date"]-origin).days*DAY_US+1,
                  time_series_ids=tuple(stable_id(record_id,c) for c in selected))
        dataset.add_task(record, AnswerTask(id=stable_id(record_id, window[-1]["date"].isoformat(), ANNOTATION_VERSION),
                          prompt=QUESTION, scope=scope, target=answer))
        audit[f"windows_{split}"] += 1
        for c, label, ok in zip(channels, labels_row, valid):
            if ok:
                audit[f"patterns_{split}:{PATTERNS[int(label)]}"] += 1


def build_bucket(args):
    root, bucket = args
    pa.set_cpu_count(1)
    config = read_yaml(CONFIG)
    root = Path(root)
    directory = root / "prepared" / bucket
    directory.mkdir(parents=True, exist_ok=True)
    pin = {"source_sha256": file_hash(root / "shards" / "manifest.json"), "config_sha256": file_hash(CONFIG)}
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text())
        if any(saved[k] != v for k, v in pin.items()):
            raise ValueError("Prepared shard uses a different source or configuration")
        for name, digest in saved["files"].items():
            if file_hash(directory / name) != digest:
                raise ValueError("Prepared window shard checksum changed")
        return saved
    metadata = replace(BackblazeConnector().metadata(), dataset_id="driftops/backblaze-full-" + bucket,
                       dataset_version=Version(0,2,0))
    dataset = TimeFDataset(metadata=metadata)
    audit = Counter()
    write_json(directory / "progress.json", {"phase": "source_conversion"})
    with connect(root, memory_gb=2) as con:
        con.read_parquet(str(root / "shards" / ("bucket=" + bucket) / "*.parquet")).create_view("raw")
        duplicates = con.execute("SELECT count(*) FROM (SELECT serial_number,date FROM raw GROUP BY ALL HAVING count(*)>1)").fetchone()[0]
        if duplicates:
            raise ValueError(f"Source shard has {duplicates} duplicate drive dates")
        fields = ", ".join(f"{c} := {c}" for c in ("date", "failure", *CHANNELS))
        result = con.execute(f"SELECT serial_number,model,list(struct_pack({fields}) ORDER BY date) FROM raw GROUP BY serial_number,model ORDER BY serial_number,model")
        while row := result.fetchone():
            add_drive(dataset, *row, config, pin["source_sha256"], audit)
    timef_root = root / "timef"
    version = timef_root / metadata.dataset_id / "0.2.0"
    write_json(directory / "progress.json", {"phase": "timef_write", "tasks": len(dataset.tasks)})
    if not version.exists():
        with TimeFWriter(timef_root, dataset) as writer:
            writer.write()
    restored = TimeFReader(DatasetVersion.open_local(version)).read()
    # Read each SDK stream once. Scoped checks then slice these same decoded values.
    # Range loaders would otherwise decompress the same chunks for thousands of windows.
    write_json(directory / "progress.json", {"phase": "native_verification", "tasks": len(dataset.tasks)})
    for record in restored.records:
        cached = []
        for series in record.time_series:
            values = series.to_arrow()
            offsets = series.time_offsets_loader()
            cached.append(replace(series, loader=lambda values=values: values,
                                  time_offsets_loader=lambda offsets=offsets: offsets))
        record.time_series = tuple(cached)
    verify_roundtrip(dataset, restored, 28)
    del dataset
    records = {r.record_id: r for r in restored.records}
    writers = {split: pq.ParquetWriter(directory / (split + ".parquet.part"), WINDOW_SCHEMA, compression="zstd")
               for split in config["partitions"]}
    buffers = {split: [] for split in writers}
    write_json(directory / "progress.json", {"phase": "window_export", "tasks": len(restored.tasks)})
    drives = {split: set() for split in writers}
    try:
        for task in restored.tasks:
            record = records[task.record_ids[0]]
            split = next(a.value for a in record.annotations if a.key == "partition")
            raw = model_input(record, task)
            start = datetime.fromtimestamp((record.start_time + task.scope.start_us)/1e6, timezone.utc).date()
            cutoff = datetime.fromtimestamp((record.start_time + task.scope.end_us - 1)/1e6, timezone.utc).date()
            buffers[split].append({"task_id": task.id, "drive_id": record.subject_ids[0], "start": start, "cutoff": cutoff,
                     "channels": [s.split(";",1)[0] for s in raw["time_series_text"]], "values": raw["time_series"], "target": task.target})
            drives[split].add(record.subject_ids[0])
            if len(buffers[split]) >= 4096:
                writers[split].write_table(pa.Table.from_pylist(buffers[split], schema=WINDOW_SCHEMA))
                buffers[split] = []
        for split, buffer in buffers.items():
            if buffer:
                writers[split].write_table(pa.Table.from_pylist(buffer, schema=WINDOW_SCHEMA))
    finally:
        for writer in writers.values():
            writer.close()
    files = {}
    for split in writers:
        path = directory / (split + ".parquet")
        path.with_suffix(".parquet.part").replace(path)
        files[path.name] = file_hash(path)
    manifest = {**pin, "bucket": bucket, "files": files, "audit": dict(audit),
                "drives": {s: sorted(ids) for s, ids in drives.items()},
                "timef_version": str(version), "verification": "All TimeF records, axes, values, metadata, tasks and scoped inputs passed SDK read-back checks."}
    write_json(manifest_path, manifest)
    write_json(directory / "progress.json", {"phase": "complete", "tasks": len(restored.tasks)})
    print(json.dumps({"prepared_bucket": bucket, **dict(audit)}), flush=True)
    return manifest


def build(root, workers):
    with (root / "dataset.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        shard(root)
        buckets = sorted(p.name.split("=",1)[1] for p in (root / "shards").glob("bucket=*"))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            manifests = list(pool.map(build_bucket, [(str(root), b) for b in buckets]))
        audit = Counter()
        drives = {split: set() for split in read_yaml(CONFIG)["partitions"]}
        for manifest in manifests:
            audit.update(manifest["audit"])
            for split, ids in manifest["drives"].items():
                drives[split].update(ids)
        for left in drives:
            for right in drives:
                if left != right and drives[left] & drives[right]:
                    raise ValueError("A drive appears in more than one partition")
        write_json(root / "dataset-manifest.json", {"config": read_yaml(CONFIG), "config_sha256": file_hash(CONFIG),
                   "source_sha256": file_hash(root / "records-complete.json"), "audit": dict(audit),
                   "drives": {s: sorted(ids) for s, ids in drives.items()},
                   "shards": {m["bucket"]: m["files"] for m in manifests},
                   "test_policy": "Test examples must remain unopened by the training runner until selected checkpoint hashes are frozen."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/backblaze-full"))
    parser.add_argument("--workers", type=int, choices=range(1,9), default=4)
    args = parser.parse_args()
    build(args.root, args.workers)
