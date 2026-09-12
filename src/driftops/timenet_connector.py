"""Backblaze source adapter for TimeNet 0.1.0 and isolated signal-text tasks."""

import argparse
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, time, timezone
import hashlib
import json
import os
from pathlib import Path

import duckdb
from timenet.connectors import BaseConnector
from timenet.dataset import TimeFDataset, TimeSeries
from timenet.reader import TimeFReader
from timenet.registry.version import DatasetVersion
from timenet.types import Annotation, AnswerTask, DataSource, TimeInterval, TimePoint, TimeSeriesSpec, Version
from timenet.writer import TimeFWriter

from driftops.acquire import CHANNELS, SOURCE_URL, write_json
from driftops.annotations import ANNOTATION_VERSION, QUESTION, describe_window
from driftops.windows import cutoff_dates, observed_window, partition_for, read_yaml

DAY_US = 86_400_000_000


def stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass(frozen=True)
class RawReference:
    path: Path
    manifest: dict


class BackblazeConnector(BaseConnector[RawReference]):
    """Find a verified local acquisition, then convert it without network access.

    The separate acquisition command performs filtered public data retrieval.
    Keeping download/discovery separate lets other teams convert their own
    traceable Backblaze Parquet extracts using this same connector.
    """

    CARD = Path(__file__).with_name("dataset.yaml")

    def __init__(self) -> None:
        super().__init__()
        self.config_path = Path(os.environ.get("DRIFTOPS_DATASET_CONFIG", "config/dataset.yaml"))
        self.splits_path = Path(os.environ.get("DRIFTOPS_SPLITS_CONFIG", "config/splits.yaml"))
        self.config = read_yaml(self.config_path)
        self.splits = read_yaml(self.splits_path)
        if not set(self.config["language_channels"]).issubset(self.config["channels"]):
            raise ValueError("Language channels must be included in the source channels")
        self.audit = Counter()

    def metadata(self):
        return replace(super().metadata(), dataset_version=Version.parse(self.config["dataset_version"]))

    def download(self, cache_dir: Path) -> list[RawReference]:
        # Discovery only: the acquisition command already downloaded a bounded,
        # immutable source extract. No parsing occurs in this stage.
        path = Path(self.config["raw_path"])
        manifest_path = path.with_suffix(".manifest.json")
        if not path.is_file() or not manifest_path.is_file():
            raise FileNotFoundError("Acquire the configured Backblaze cohort and manifest before building TimeNet")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != manifest["parquet_sha256"]:
            raise ValueError("Raw cohort checksum does not match its acquisition manifest")
        return [RawReference(path, manifest)]

    def convert(self, raw_refs: list[RawReference]) -> TimeFDataset:
        if len(raw_refs) != 1:
            raise ValueError("This connector expects one merged, audited cohort extract")
        reference = raw_refs[0]
        dataset = TimeFDataset(metadata=self.metadata())
        channels = tuple(self.config["channels"])
        if not channels or not set(channels).issubset(CHANNELS):
            raise ValueError("Configure a nonempty subset of the audited SMART allowlist")
        with duckdb.connect() as connection:
            connection.read_parquet(str(reference.path)).create_view("raw")
            invalid = connection.execute("""
                SELECT count(*) FROM raw WHERE date IS NULL OR serial_number IS NULL
                OR model IS NULL OR failure IS NULL OR failure NOT IN (0, 1)
            """).fetchone()[0]
            duplicates = connection.execute("""
                SELECT count(*) FROM (SELECT serial_number,date FROM raw
                GROUP BY serial_number,date HAVING count(*) > 1)
            """).fetchone()[0]
            models = connection.execute("SELECT DISTINCT model FROM raw").fetchall()
            if invalid or duplicates or models != [(self.config["model"],)]:
                raise ValueError(f"Raw identity/schema audit failed: invalid={invalid}, duplicate_days={duplicates}, models={models}")
            fields = ", ".join(f"{name} := {name}" for name in ("date", "failure", *channels))
            grouped = connection.execute(f"""
                SELECT serial_number, any_value(model), any_value(capacity_bytes),
                       list(struct_pack({fields}) ORDER BY date)
                FROM raw GROUP BY serial_number ORDER BY serial_number
            """)
            while group := grouped.fetchone():
                serial, model, capacity, rows = group
                self._add_drive(dataset, serial, model, capacity, rows, channels, reference.manifest)
        return dataset

    def _add_drive(self, dataset, serial, model, capacity, rows, channels, manifest):
        origin = rows[0]["date"]
        offsets = [(row["date"] - origin).days * DAY_US for row in rows]
        record_id = stable_id("backblaze", serial)
        source_id = manifest.get("parquet_sha256", "fixture")
        source = DataSource(data_source_type="backblaze-drive-stats", name="Backblaze HDD SMART", provider="Backblaze")
        series = []
        for channel in channels:
            # TimeNet 0.1.0 has no int64 signal dtype. Float64 represents these
            # integer encodings exactly only within this checked range.
            if any(row[channel] is not None and abs(row[channel]) > 2**53 for row in rows):
                raise ValueError(f"{channel} exceeds the exact float64 integer range")
            spec = TimeSeriesSpec(spec_type=channel, name=channel, unit_value="dimensionless",
                                  dtype="float64", nullable=True, data_source=source)
            series.append(TimeSeries.from_irregular(
                [row[channel] for row in rows], time_offsets_us=offsets,
                spec=spec, signal=channel, source_id=source_id,
                time_series_id=stable_id(record_id, channel),
            ))
        record = dataset.add_record(
            record_id=record_id, subject_ids=(f"backblaze:{serial}",),
            start_time=datetime.combine(origin, time.min, tzinfo=timezone.utc),
            time_series=tuple(series),
        )
        split, rule = partition_for(serial, self.splits)
        metadata = {"hardware_model": model, "partition": split,
                    "source_parquet_sha256": source_id,
                    "annotation_method": ANNOTATION_VERSION,
                    "value_semantics": "Source raw SMART encoding; dimensionless does not imply a verified physical count",
                    "availability_assumption": self.config["availability_assumption"]}
        if capacity is not None:
            metadata["capacity_bytes"] = capacity
        for key, value in metadata.items():
            record.add_annotation(Annotation(key=key, value=value, source=SOURCE_URL,
                                             id=stable_id(record_id, key)), warn_when_outside=False)
        for row, offset in zip(rows, offsets):
            if row["failure"] == 1:
                record.add_annotation(Annotation(
                    key="recorded_failure", value=True, span=TimePoint.micros(offset), source=SOURCE_URL,
                    description="Offline outcome annotation; never include in inference input",
                    id=stable_id(record_id, "failure", row["date"].isoformat()),
                ), warn_when_outside=False)
        self.audit[f"records_{split}"] += 1
        self.audit["source_rows"] += len(rows)
        self.audit["missing_calendar_days"] += (rows[-1]["date"] - origin).days + 1 - len(rows)
        for cutoff in cutoff_dates(rule, self.config["task_stride_days"]):
            window = observed_window(rows, cutoff, self.config["lookback_days"])
            if not window:
                self.audit[f"ineligible_windows_{split}"] += 1
                continue
            try:
                answer, findings = describe_window(window, self.config["language_channels"])
            except ValueError:
                self.audit[f"ineligible_windows_{split}"] += 1
                continue
            if len(findings) < 2:
                self.audit[f"ineligible_windows_{split}"] += 1
                continue
            selected_ids = tuple(stable_id(record_id, finding["channel"]) for finding in findings)
            scope = TimeInterval.micros(
                (window[0]["date"] - origin).days * DAY_US,
                (cutoff - origin).days * DAY_US + 1,
                time_series_ids=selected_ids,
            )
            dataset.add_task(record, AnswerTask(
                id=stable_id(record_id, cutoff.isoformat(), ANNOTATION_VERSION),
                prompt=QUESTION, scope=scope, target=answer,
            ))
            self.audit[f"tasks_{split}"] += 1
            for finding in findings:
                self.audit[f"patterns_{split}:{finding['pattern']}"] += 1


def model_input(record, task: AnswerTask, expected_days: int = 28) -> dict:
    """Construct a strict allowlist, never serialize a labeled TimeNet record.

    Result contains no target, rationale, outcome annotation, serial, split,
    absolute date, or derived description. Those stay in training/eval metadata.
    """
    if not isinstance(task.scope, TimeInterval) or not task.scope.time_series_ids:
        raise ValueError("Inference requires an explicitly scoped numerical window")
    series_values = []
    descriptions = []
    for series in record.time_series:
        if series.time_series_id not in task.scope.time_series_ids:
            continue
        start, stop = series.step_range(task.scope)
        values = series.read_steps(start, stop).to_pylist()
        if len(values) != expected_days or any(value is None for value in values):
            raise ValueError("Model input requires a complete numerical window")
        offsets = series.time_offsets_us()[start:stop]
        if any(int(b - a) != DAY_US for a, b in zip(offsets[:-1], offsets[1:])):
            raise ValueError("Model input has a calendar gap")
        series_values.append(values)
        descriptions.append(f"{series.signal}; one observation per day; raw source units")
    if len(series_values) < 2:
        raise ValueError("At least two eligible numerical channels are required")
    return {"pre_prompt": QUESTION, "time_series": series_values,
            "time_series_text": descriptions, "post_prompt": "Answer:"}


def verify_roundtrip(dataset, reloaded, expected_days: int) -> None:
    """Check every record/series and every scoped model input after serialization."""
    if len(reloaded.records) != len(dataset.records) or len(reloaded.tasks) != len(dataset.tasks):
        raise RuntimeError("TimeF read-back changed record/task counts")
    original_records = {record.record_id: record for record in dataset.records}
    loaded_records = {record.record_id: record for record in reloaded.records}
    if original_records.keys() != loaded_records.keys():
        raise RuntimeError("TimeF read-back changed record identities")
    for record_id, original in original_records.items():
        restored = loaded_records[record_id]
        if (original.subject_ids, original.start_time, original.annotations) != (
                restored.subject_ids, restored.start_time, restored.annotations):
            raise RuntimeError("TimeF read-back changed record metadata")
        if len(original.time_series) != len(restored.time_series):
            raise RuntimeError("TimeF read-back changed channel count")
        for before, after in zip(original.time_series, restored.time_series):
            if (before.time_series_id, before.signal, before.spec) != (after.time_series_id, after.signal, after.spec):
                raise RuntimeError("TimeF read-back changed a channel identity/specification")
            if not before.to_arrow().equals(after.to_arrow()):
                raise RuntimeError("TimeF read-back changed numerical values or missingness")
            if not (before.time_offsets_us() == after.time_offsets_us()).all():
                raise RuntimeError("TimeF read-back changed the observation calendar")
    originals = {task.id: task for task in dataset.tasks}
    for task in reloaded.tasks:
        before = originals.get(task.id)
        if before is None or (before.target, before.scope, before.record_ids, before.prompt) != (
                task.target, task.scope, task.record_ids, task.prompt):
            raise RuntimeError("TimeF read-back changed a task")
        if model_input(original_records[task.record_ids[0]], before, expected_days) != model_input(
                loaded_records[task.record_ids[0]], task, expected_days):
            raise RuntimeError("TimeF read-back changed a model input")


def build(verify_only: bool = False) -> None:
    connector = BackblazeConnector()
    references = connector.download(Path("data/raw"))
    dataset = connector.convert(references)
    root = Path(connector.config["timef_root"])
    if not verify_only:
        with TimeFWriter(root, dataset) as writer:
            writer.write()
    version_dir = root / dataset.metadata.dataset_id / str(dataset.metadata.dataset_version)
    reloaded = TimeFReader(DatasetVersion.open_local(version_dir)).read()
    verify_roundtrip(dataset, reloaded, connector.config["lookback_days"])
    audit = {"timef_version_dir": str(version_dir), "records": len(reloaded.records),
             "tasks": len(reloaded.tasks), "timenet_version": "0.1.0",
             "roundtrip_verification": "All records, values, calendars, annotations, tasks and model inputs",
             "dataset_config_sha256": hashlib.sha256(connector.config_path.read_bytes()).hexdigest(),
             "splits_config_sha256": hashlib.sha256(connector.splits_path.read_bytes()).hexdigest(),
             "raw_parquet_sha256": references[0].manifest["parquet_sha256"],
             **dict(connector.audit)}
    write_json(Path("data/preparation-audit.json"), audit)
    write_json(Path("data/split-manifest.json"), {
        "version": connector.splits["version"], "config": connector.splits,
        "dataset_config": connector.config,
        "records": [{"record_id": record.record_id, "subject_ids": record.subject_ids,
                     "partition": partition_for(record.subject_ids[0].removeprefix("backblaze:"), connector.splits)[0]}
                    for record in reloaded.records],
    })
    print(json.dumps(audit, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Verify the existing TimeF version against its raw source")
    build(parser.parse_args().verify_only)
