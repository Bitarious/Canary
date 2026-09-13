"""Stream the complete official ZIP archive into typed SMART Parquet files."""

import argparse
from datetime import date
import fcntl
import json
from pathlib import Path
import re
import time
import zipfile

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as csv
import pyarrow.parquet as pq

from driftops.acquire import CHANNELS, COLUMNS, write_json
from driftops.full_archive import archive_name, file_hash

SCHEMA = pa.schema([("date", pa.date32()), ("serial_number", pa.string()), ("model", pa.string()),
                    ("capacity_bytes", pa.int64()), ("failure", pa.int8()),
                    *[(name, pa.float64()) for name in CHANNELS]])


def parse_dates(values):
    """Accept the ISO and US date formats present in the source archives."""
    parsed = pc.coalesce(*[pc.strptime(values, format=fmt, unit="s", error_is_null=True)
                           for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y")])
    if parsed.null_count:
        raise ValueError("Source contains a missing or unsupported date")
    return pc.cast(parsed, pa.date32())


def daily_members(archive):
    entries = [info for info in archive.infolist() if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.csv", Path(info.filename).name)
               and not info.filename.startswith("__MACOSX/")]
    names = [Path(info.filename).name for info in entries]
    if len(names) != len(set(names)):
        raise ValueError("Archive repeats a dated CSV filename")
    return sorted(entries, key=lambda info: Path(info.filename).name)


def convert_archive(source, destination):
    source_manifest = json.loads(source.with_suffix(".manifest.json").read_text())
    manifest_path = destination.with_suffix(".manifest.json")
    if destination.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["source_sha256"] != source_manifest["sha256"] or file_hash(destination) != manifest["parquet_sha256"]:
            raise ValueError("Existing converted archive failed verification")
        return manifest
    temporary = destination.with_suffix(".parquet.part")
    row_count = 0
    rejected_count = 0
    days = []
    quarantine = destination.with_suffix(".quarantine.parquet")
    with zipfile.ZipFile(source) as archive, pq.ParquetWriter(temporary, SCHEMA, compression="zstd") as writer, pq.ParquetWriter(quarantine, SCHEMA, compression="zstd") as rejected:
        for member in daily_members(archive):
            expected = date.fromisoformat(Path(member.filename).stem)
            daily_count = 0
            if member.file_size > 512 * 1024**2:
                raise ValueError("A daily CSV exceeds the 512 MiB conversion buffer limit")
            # An Arrow buffer avoids Python ZIP callbacks from native I/O threads.
            with pa.BufferReader(archive.read(member)) as stream:
                with csv.open_csv(stream, read_options=csv.ReadOptions(block_size=8 * 1024**2, use_threads=False),
                                      convert_options=csv.ConvertOptions(column_types={**{field.name: field.type for field in SCHEMA}, "date": pa.string(), "capacity_bytes": pa.float64()},
                                          include_columns=list(COLUMNS), include_missing_columns=True,
                                          null_values=["", "NA", "N/A", "null"], strings_can_be_null=True)) as reader:
                    for batch in reader:
                        table = pa.Table.from_batches([batch])
                        table = table.set_column(0, SCHEMA.field("date"), parse_dates(table["date"]))
                        table = table.set_column(3, SCHEMA.field("capacity_bytes"), pc.cast(table["capacity_bytes"], pa.int64(), safe=True))
                        missing_identity = pc.or_(pc.is_null(table["serial_number"]), pc.is_null(table["model"]))
                        wrong_date = pc.not_equal(table["date"], pa.scalar(expected, pa.date32()))
                        invalid_failure = pc.invert(pc.is_in(table["failure"], value_set=pa.array([0, 1], type=pa.int8())))
                        invalid_mask = pc.or_(missing_identity, pc.or_(wrong_date, invalid_failure))
                        invalid = table.filter(invalid_mask)
                        if len(invalid):
                            rejected.write_table(invalid)
                            rejected_count += len(invalid)
                            table = table.filter(pc.invert(invalid_mask))
                        writer.write_table(table)
                        daily_count += len(table)
            row_count += daily_count
            days.append({"date": expected.isoformat(), "rows": daily_count})
    manifest = {"source_archive": source.name, "source_sha256": source_manifest["sha256"],
                "rows": row_count, "days": days, "columns": list(COLUMNS),
                "quarantined_rows": rejected_count, "quarantine_reason": "Missing serial/model, CSV date inconsistent with source day, or failure outside 0/1. Excluded from training and evaluation.",
                "quarantine_sha256": file_hash(quarantine),
                "parquet_sha256": file_hash(temporary), "file_bytes": temporary.stat().st_size,
                "verification": "All dated CSV streams decoded to EOF with ZIP CRC checks. Required identity/date/failure fields validated. No row sampling."}
    write_json(manifest_path, manifest)
    temporary.replace(destination)
    print(json.dumps({"converted": source.name, "rows": row_count, "days": len(days),
                      "parquet_mib": destination.stat().st_size / 1024**2}), flush=True)
    return manifest


def convert_all(root, follow=False):
    inventory = json.loads((root / "inventory.json").read_text())
    output = root / "records"
    output.mkdir(exist_ok=True)
    with (root / "convert.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        complete = {}
        deadline = time.monotonic() + 6 * 3600
        while len(complete) < len(inventory["archives"]):
            progress = False
            for record in inventory["archives"]:
                name = archive_name(record["url"])
                source = root / "archives" / name
                if name in complete or not source.is_file() or not source.with_suffix(".manifest.json").is_file():
                    continue
                complete[name] = convert_archive(source, output / (source.stem + ".parquet"))
                progress = True
            if not progress:
                if not follow or time.monotonic() >= deadline:
                    raise RuntimeError("The full archive download is not complete")
                time.sleep(15)
        all_days = [day["date"] for item in complete.values() for day in item["days"]]
        if len(all_days) != len(set(all_days)):
            raise ValueError("Source archives contain overlapping daily snapshots")
        write_json(root / "records-complete.json", {"archives": len(complete),
                    "rows": sum(item["rows"] for item in complete.values()),
                    "quarantined_rows": sum(item.get("quarantined_rows", 0) for item in complete.values()),
                    "start": min(all_days), "end": max(all_days), "days": len(all_days),
                    "files": {name: item["parquet_sha256"] for name, item in sorted(complete.items())}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/backblaze-full"))
    parser.add_argument("--follow", action="store_true")
    args = parser.parse_args()
    convert_all(args.root, args.follow)
