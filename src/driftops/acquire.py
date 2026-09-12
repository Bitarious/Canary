"""Acquire a bounded cohort from Backblaze's official read-only Iceberg table.

The credentials below are explicitly published by Backblaze for public read-only
dataset access, not user credentials. No private account credentials are used.
Source: https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data
"""

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import boto3
from botocore.config import Config
import duckdb

SOURCE_URL = "https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data"
BUCKET = "drivestats-iceberg"
ENDPOINT = "https://s3.us-west-004.backblazeb2.com"
PUBLIC_KEY_ID = "0045f0571db506a0000000017"
PUBLIC_READ_KEY = "K004Fs/bgmTk5dgo6GAVm2Waj3Ka+TE"
CHANNELS = ("smart_5_raw", "smart_9_raw", "smart_187_raw", "smart_188_raw",
            "smart_194_raw", "smart_197_raw", "smart_198_raw")
COLUMNS = ("date", "serial_number", "model", "capacity_bytes", "failure", *CHANNELS)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def discover_snapshot(output: Path) -> dict:
    """Pin a concrete metadata object instead of querying a moving 'latest'."""
    if output.exists():
        return json.loads(output.read_text(encoding="utf-8"))
    client = boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name="us-west-004",
        aws_access_key_id=PUBLIC_KEY_ID, aws_secret_access_key=PUBLIC_READ_KEY,
        config=Config(connect_timeout=15, read_timeout=30, retries={"max_attempts": 2}),
    )
    candidates = []
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="drivestats/metadata/")
    for page in pages:
        candidates.extend(item for item in page.get("Contents", []) if item["Key"].endswith(".metadata.json"))
    if not candidates:
        raise RuntimeError("No official Iceberg metadata objects found")
    latest = max(candidates, key=lambda item: (item["LastModified"], item["Key"]))
    body = client.get_object(Bucket=BUCKET, Key=latest["Key"])["Body"].read()
    metadata = json.loads(body)
    snapshot = {
        "source_url": SOURCE_URL,
        "metadata_uri": f"s3://{BUCKET}/{latest['Key']}",
        "metadata_sha256": hashlib.sha256(body).hexdigest(),
        "current_snapshot_id": metadata["current-snapshot-id"],
        "source_updated_at_ms": metadata["last-updated-ms"],
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(output, snapshot)
    return snapshot


def connect(root: Path) -> duckdb.DuckDBPyConnection:
    extension_dir = root / ".tools/duckdb-extensions"
    extension_dir.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(config={"extension_directory": str(extension_dir), "memory_limit": "2GB", "threads": 4})
    connection.execute("INSTALL httpfs; LOAD httpfs; INSTALL iceberg; LOAD iceberg;")
    connection.execute(
        f"CREATE SECRET public_backblaze (TYPE s3, KEY_ID {sql_literal(PUBLIC_KEY_ID)}, "
        f"SECRET {sql_literal(PUBLIC_READ_KEY)}, REGION 'us-west-004', "
        "ENDPOINT 's3.us-west-004.backblazeb2.com')"
    )
    return connection


def source_table(snapshot: dict) -> str:
    # Relocate manifest/data paths relative to the table root, not the metadata
    # filename. Use an exact metadata version with no latest-version guessing.
    metadata_uri = snapshot["metadata_uri"]
    table_root, filename = metadata_uri.rsplit("/metadata/", 1)
    version = filename.removesuffix(".metadata.json")
    return (f"iceberg_scan({sql_literal(table_root)}, version={sql_literal(version)}, "
            "version_name_format='%s%s.metadata.json', allow_moved_paths=true)")


def inspect_development(connection, table: str, start: date, end: date) -> list[dict]:
    query = f"""
        SELECT model, count(*) AS drive_days, count(DISTINCT serial_number) AS drives,
               sum(failure) AS events,
               count(smart_5_raw)::DOUBLE / count(*) AS smart_5_coverage,
               count(smart_197_raw)::DOUBLE / count(*) AS smart_197_coverage
        FROM {table} WHERE date BETWEEN ? AND ?
        GROUP BY model HAVING count(DISTINCT serial_number) >= 1000
        ORDER BY events DESC, drive_days DESC LIMIT 20
    """
    result = connection.execute(query, [start, end])
    names = [item[0] for item in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def fetch_cohort(connection, table: str, snapshot: dict, *, model: str, start: date,
                 end: date, max_drives: int, output: Path) -> dict:
    if max_drives < 1 or max_drives > 10000:
        raise ValueError("Choose between 1 and 10,000 baseline-date drives")
    if (end - start).days < 28 or (end - start).days > 366:
        raise ValueError("Choose a bounded history between 29 and 367 calendar dates")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing cohort: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Choose identifiers at the first observation date, before consulting later
    # outcomes. Retain all subsequent rows for those drives, including removals.
    connection.execute(f"""
        CREATE TEMP TABLE cohort AS
        SELECT DISTINCT serial_number FROM {table}
        WHERE date = ? AND model = ?
        ORDER BY md5(serial_number || 'driftops-cohort-v1'), serial_number LIMIT ?
    """, [start, model, max_drives])
    drive_count = connection.execute("SELECT count(*) FROM cohort").fetchone()[0]
    if drive_count == 0:
        raise ValueError("No drives match the selected model and baseline date")
    query = f"""
        SELECT {', '.join('source.' + name for name in COLUMNS)}
        FROM {table} AS source INNER JOIN cohort USING (serial_number)
        WHERE date BETWEEN {sql_literal(start.isoformat())}::DATE AND {sql_literal(end.isoformat())}::DATE
        ORDER BY serial_number, date
    """
    temporary = output.with_suffix(".parquet.part")
    connection.execute(f"COPY ({query}) TO {sql_literal(str(temporary))} (FORMAT PARQUET, COMPRESSION ZSTD)")
    temporary.replace(output)
    stats = connection.execute("""
        SELECT count(*), count(DISTINCT serial_number), sum(failure), min(date), max(date)
        FROM read_parquet(?)
    """, [str(output)]).fetchone()
    with output.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {
        **snapshot, "acquired_at": datetime.now(timezone.utc).isoformat(),
        "model": model, "start": start.isoformat(), "end": end.isoformat(),
        "selection": "Baseline-date identifiers ordered by md5(serial + driftops-cohort-v1); later outcomes unused",
        "max_drives": max_drives, "cohort_drives": drive_count,
        "rows": stats[0], "distinct_drives": stats[1], "recorded_events": stats[2],
        "observed_min_date": stats[3], "observed_max_date": stats[4],
        "columns": COLUMNS, "parquet_sha256": checksum,
        "duckdb_version": duckdb.__version__, "file_bytes": output.stat().st_size,
        "endpoint": "Recorded failure/removal under Backblaze's operating policy",
        "sampling_limitations": "Baseline-date cohort excludes later fleet entrants; event counts do not establish prediction performance",
    }
    write_json(output.with_suffix(".manifest.json"), manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "fetch"])
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 7, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2024, 7, 31))
    parser.add_argument("--model")
    parser.add_argument("--max-drives", type=int, default=3000)
    parser.add_argument("--output", type=Path, default=Path("data/raw/backblaze.parquet"))
    parser.add_argument("--snapshot", type=Path, default=Path("config/source-snapshot.json"))
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("start must not follow end")
    root = Path.cwd()
    snapshot = discover_snapshot(args.snapshot)
    print(json.dumps({"snapshot": snapshot}, default=str), flush=True)
    with connect(root) as connection:
        table = source_table(snapshot)
        if args.action == "inspect":
            result = inspect_development(connection, table, args.start, args.end)
            write_json(root / "data/development-model-audit.json", {"start": args.start, "end": args.end, "models": result})
        else:
            if not args.model:
                parser.error("fetch requires --model")
            result = fetch_cohort(connection, table, snapshot, model=args.model, start=args.start,
                                  end=args.end, max_drives=args.max_drives, output=args.output)
    print(json.dumps(result, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
