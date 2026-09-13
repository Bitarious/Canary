"""Acquire the pinned public component sources with bounded, resumable transfers."""

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
from urllib.parse import urlparse

import requests


def verify_file(path, item):
    algorithm, expected = item["checksum"].split(":", 1)
    multipart = algorithm == "multipart-md5"
    pattern = r"[0-9a-f]{32}-[1-9][0-9]*" if multipart else "[0-9a-f]{" + str(32 if algorithm == "md5" else 64) + "}"
    if algorithm not in ("md5", "sha256", "multipart-md5") or not re.fullmatch(pattern, expected):
        raise ValueError("The declared source checksum is invalid.")
    if path.stat().st_size != item["bytes"]:
        raise ValueError("The source file size does not match its declaration.")
    block_size = item.get("part_size_bytes", 8 * 1024 * 1024)
    if type(block_size) is not int or not 1 <= block_size <= 64 * 1024 * 1024:
        raise ValueError("The declared checksum part size is invalid.")
    hashes = {name: hashlib.new(name) for name in ({"sha256"} if multipart else {algorithm, "sha256"})}
    combined, parts = hashlib.md5(), 0
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            for digest in hashes.values():
                digest.update(block)
            if multipart:
                combined.update(hashlib.md5(block).digest())
                parts += 1
    actual = f"{combined.hexdigest()}-{parts}" if multipart else hashes[algorithm].hexdigest()
    if actual != expected:
        raise ValueError("The source checksum does not match its declaration.")
    if item.get("sha256") and hashes["sha256"].hexdigest() != item["sha256"]:
        raise ValueError("The source SHA-256 checksum changed.")
    return hashes["sha256"].hexdigest()


def fetch(root, item, verify_only=False):
    path = root / item["name"]
    if path.is_symlink():
        raise ValueError("A source destination must not be a symbolic link.")
    if path.exists():
        digest = verify_file(path, item)
        receipt_path = root / (item["name"] + "-receipt.json")
        if not verify_only and not receipt_path.exists():
            receipt_path.write_text(json.dumps({**item, "sha256": digest, "verified": True,
                "verified_at": datetime.now(timezone.utc).isoformat(), "method": "Verified an existing complete source file."}, indent=2) + "\n")
        return {"name": item["name"], "sha256": digest, "reused": True}
    if verify_only:
        raise FileNotFoundError(path)
    partial = path.with_name(path.name + ".part")
    if partial.is_symlink():
        raise ValueError("A partial source must not be a symbolic link.")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > item["bytes"]:
        raise ValueError("The partial source exceeds the declared file size.")
    started = time.monotonic()
    if offset < item["bytes"]:
        headers = {"User-Agent": "DriftOps-component-acquisition/1.0", "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        with requests.get(item["url"], headers=headers, stream=True, timeout=(15, 30)) as response:
            response.raise_for_status()
            if offset and response.headers.get("Content-Range") != f"bytes {offset}-{item['bytes']-1}/{item['bytes']}":
                raise ValueError("The server did not return the exact requested source range.")
            if response.status_code != (206 if offset else 200):
                raise ValueError("The source server returned an unexpected status.")
            count = offset
            with partial.open("ab" if offset else "xb") as stream:
                for block in response.iter_content(8 * 1024 * 1024):
                    count += len(block)
                    if count > item["bytes"] or time.monotonic() - started > 900:
                        raise ValueError("The source transfer exceeds its size or 15-minute limit.")
                    stream.write(block)
    digest = verify_file(partial, item)
    partial.rename(path)
    receipt = {**item, "sha256": digest, "verified": True, "fetched_at": datetime.now(timezone.utc).isoformat(),
               "resumed_from_bytes": offset, "elapsed_seconds": time.monotonic() - started}
    (root / (item["name"] + "-receipt.json")).write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def acquire(manifest_path, root, verify_only=False):
    manifest = json.loads(manifest_path.read_text())
    files = manifest["files"]
    if len({item["name"] for item in files}) != len(files):
        raise ValueError("The source catalog contains duplicate destination names.")
    for item in files:
        if Path(item["name"]).name != item["name"] or item["name"] in ("", ".", ".."):
            raise ValueError("Each source destination must be a file name.")
        if urlparse(item["url"]).scheme != "https" or type(item["bytes"]) is not int or item["bytes"] < 1:
            raise ValueError("Each source requires HTTPS and a positive byte count.")
    if sum(item["bytes"] for item in files) > manifest["max_total_bytes"]:
        raise ValueError("The source catalog exceeds its declared download limit.")
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".component-download.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        needed = sum(item["bytes"] for item in files if not (root / item["name"]).exists())
        if not verify_only and shutil.disk_usage(root).free < needed + 100_000_000_000:
            raise ValueError("The source download must retain 100 GB of free storage.")
        with ThreadPoolExecutor(max_workers=3) as pool:
            for result in as_completed([pool.submit(fetch, root, item, verify_only) for item in files]):
                print(json.dumps(result.result()), flush=True)
        for name, content in manifest["metadata"].items():
            if Path(name).name != name or len(content.encode()) > 1_000_000:
                raise ValueError("A source metadata snapshot is invalid.")
            path = root / name
            if path.exists():
                if path.read_text() != content:
                    raise ValueError("An existing source metadata snapshot differs from the catalog.")
            elif verify_only:
                raise FileNotFoundError(path)
            else:
                path.write_text(content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("config/component_sources.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/component-audit/v1"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    acquire(args.manifest, args.output, args.verify_only)
