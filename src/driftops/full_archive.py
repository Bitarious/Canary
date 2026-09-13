"""Download every published Backblaze archive with bounded, resumable transfers."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import zipfile

import requests

from driftops.acquire import SOURCE_URL, write_json

ARCHIVE_NAME = re.compile(r"data_(?:20\d{2}|Q[1-4]_20\d{2})\.zip")
ROOT_URL = "https://f001.backblazeb2.com/file/Backblaze-Hard-Drive-Data/"


def archive_name(url):
    name = url.removeprefix(ROOT_URL)
    if not url.startswith(ROOT_URL) or not ARCHIVE_NAME.fullmatch(name):
        raise ValueError("Archive URL is outside the official Backblaze allowlist")
    return name


def inventory(root):
    response = requests.get(SOURCE_URL, timeout=(15, 60))
    response.raise_for_status()
    urls = sorted(set(re.findall(r'https://[^\s"<>]+\.zip', response.text)))
    urls = [url for url in urls if url.startswith(ROOT_URL)]
    if not urls:
        raise ValueError("No official archive links found")

    def inspect(url):
        name = archive_name(url)
        response = requests.head(url, timeout=(15, 60))
        response.raise_for_status()
        size = int(response.headers["Content-Length"])
        if not 0 < size < 50 * 1024**3:
            raise ValueError("Unexpected archive size")
        return {"name": name, "url": url, "bytes": size,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified")}

    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(inspect, url) for url in urls]):
            records.append(future.result())
            print(json.dumps({"inventory_files": len(records), "of": len(urls)}), flush=True)
    records.sort(key=lambda row: row["name"])
    result = {"source_url": SOURCE_URL, "discovered_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Every ZIP archive linked on the official Drive Stats page. No model or drive sampling.",
              "archives": records, "total_bytes": sum(row["bytes"] for row in records)}
    write_json(root / "inventory.json", result)
    print(json.dumps({"archives": len(records), "total_gib": result["total_bytes"] / 1024**3}), flush=True)


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_one(record, directory):
    name = archive_name(record["url"])
    target = directory / name
    manifest = target.with_suffix(".manifest.json")
    if target.exists():
        if not manifest.exists():
            raise ValueError(f"Archive exists without its verification record: {name}")
        saved = json.loads(manifest.read_text())
        if target.stat().st_size != record["bytes"] or file_hash(target) != saved["sha256"]:
            raise ValueError(f"Existing archive failed verification: {name}")
        return saved
    partial = target.with_suffix(".zip.part")
    identity = target.with_suffix(".download.json")
    if identity.exists():
        if json.loads(identity.read_text()) != record:
            raise ValueError(f"Remote archive changed since the partial download: {name}")
    else:
        write_json(identity, record)
    for attempt in range(3):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > record["bytes"]:
                raise ValueError("Partial archive exceeds its declared size")
            if offset == record["bytes"]:
                break
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            if record["etag"]:
                headers["If-Match"] = record["etag"]
            with requests.get(record["url"], headers=headers, stream=True, timeout=(15, 60)) as response:
                response.raise_for_status()
                if response.headers.get("ETag") != record["etag"]:
                    raise ValueError("Remote archive identity changed during transfer")
                if offset and response.status_code == 206:
                    if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise ValueError("Server returned an inconsistent resume range")
                    mode = "ab"
                elif response.status_code == 200:
                    mode = "wb"
                else:
                    raise ValueError("Unexpected download response status")
                with partial.open(mode) as output:
                    for chunk in response.iter_content(8 * 1024**2):
                        if shutil.disk_usage(directory).free < 80 * 1024**3:
                            raise OSError("Stop download to retain 80 GiB of free controller storage")
                        output.write(chunk)
                        if output.tell() > record["bytes"]:
                            raise ValueError("Archive transfer exceeds the declared size")
            if partial.stat().st_size != record["bytes"]:
                raise requests.ConnectionError("Incomplete archive transfer")
            break
        except (requests.RequestException, OSError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    with zipfile.ZipFile(partial) as archive:
        entries = [info for info in archive.infolist() if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.csv", Path(info.filename).name)
                   and not info.filename.startswith("__MACOSX/")]
        if not entries:
            raise ValueError("Archive contains no dated CSV data")
    digest = file_hash(partial)
    saved = {**record, "sha256": digest, "daily_files": len(entries),
             "uncompressed_daily_bytes": sum(info.file_size for info in entries),
             "verified_at": datetime.now(timezone.utc).isoformat(),
             "verification": "HTTP size/ETag, SHA-256, and ZIP central directory. CSV CRC checked during conversion."}
    write_json(manifest, saved)
    partial.replace(target)
    print(json.dumps({"downloaded": name, "bytes": saved["bytes"], "daily_files": len(entries)}), flush=True)
    return saved


def download(root, workers):
    source = json.loads((root / "inventory.json").read_text())
    if source["total_bytes"] > 150 * 1024**3:
        raise ValueError("Archive exceeds the 150 GiB acquisition limit. Review storage before proceeding")
    directory = root / "archives"
    directory.mkdir(parents=True, exist_ok=True)
    with (root / "download.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(download_one, row, directory) for row in source["archives"]]):
                results.append(future.result())
        write_json(root / "download-complete.json", {"archives": sorted(results, key=lambda row: row["name"]),
                                                     "total_bytes": sum(row["bytes"] for row in results)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inventory", "download"])
    parser.add_argument("--root", type=Path, default=Path("data/backblaze-full"))
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    if args.action == "inventory":
        inventory(args.root)
    else:
        download(args.root, args.workers)
