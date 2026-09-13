"""Retrieve dated temperature tables from public bearing ZIPs with bounded ranges."""

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import zipfile

import requests


class RangeReader(io.RawIOBase):
    def __init__(self, url, size, limit=32 * 1024 * 1024):
        if urlparse(url).scheme != "https" or type(size) is not int or size < 1:
            raise ValueError("A ZIP source requires HTTPS and a positive size.")
        self.url, self.size, self.limit = url, size, limit
        self.position, self.transferred = 0, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence not in (0, 1, 2):
            raise ValueError("The ZIP seek origin is invalid.")
        target = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if not 0 <= target <= self.size:
            raise ValueError("The ZIP seek exceeds the source bounds.")
        self.position = target
        return target

    def read(self, size=-1):
        count = self.size - self.position if size < 0 else min(size, self.size - self.position)
        if count > 16 * 1024 * 1024 or self.transferred + count > self.limit:
            raise ValueError("The ZIP probe exceeds its transfer limit.")
        if count == 0:
            return b""
        end = self.position + count - 1
        expected = f"bytes {self.position}-{end}/{self.size}"
        with requests.get(self.url, headers={"Range": f"bytes={self.position}-{end}",
                          "Accept-Encoding": "identity"}, timeout=(15, 30), stream=True) as response:
            response.raise_for_status()
            if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("The ZIP server did not return the exact requested range.")
            content = response.raw.read(count + 1)
        if len(content) != count:
            raise ValueError("The ZIP range length does not match its declaration.")
        self.position += count
        self.transferred += count
        return content


def acquire(root):
    metadata = json.loads((root / "paderborn-bearing.json").read_text())
    sources = sorted([f for f in metadata["files"] if re.fullmatch(r"B[0-9]{2}(?:_part1)?\.zip", f["key"])],
                     key=lambda item: item["key"])
    if len(sources) != 17:
        raise ValueError("The publisher inventory must contain 17 first experiment archives.")
    destination = root / "paderborn-temperature-audit"
    destination.mkdir(exist_ok=True)
    for source in sources:
        experiment = source["key"][:3]
        receipt_path = destination / f"{experiment}-receipt.json"
        output = destination / f"{experiment}_meanTemperatures.csv"
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if hashlib.sha256(output.read_bytes()).hexdigest() != receipt["sha256"]:
                raise ValueError("A saved bearing temperature table changed.")
            print(json.dumps({"experiment": experiment, "reused": True}), flush=True)
            continue
        if output.exists():
            raise FileExistsError("Inspect the incomplete bearing probe before another attempt.")
        reader = RangeReader(source["links"]["self"], source["size"])
        with zipfile.ZipFile(reader) as archive:
            candidates = [f for f in archive.infolist() if f.filename.endswith(f"{experiment}_meanTemperatures.csv")]
            if len(candidates) != 1 or candidates[0].file_size > 8 * 1024 * 1024:
                raise ValueError("The experiment must contain one bounded temperature table.")
            member = candidates[0]
            content = archive.read(member)
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        times = [datetime.strptime(row["Time"], "%d-%b-%Y %H:%M:%S") for row in rows]
        if not times or times != sorted(set(times)):
            raise ValueError("Bearing temperature observations require unique ordered source times.")
        receipt = {"experiment": experiment, "source_url": source["links"]["self"], "archive_bytes": source["size"],
                   "publisher_archive_checksum": source["checksum"], "archive_checksum_verified": False,
                   "member": member.filename, "member_crc32": f"{member.CRC:08x}", "member_crc32_verified": True,
                   "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                   "transferred_bytes": reader.transferred, "rows": len(rows), "columns": list(rows[0]),
                   "first_source_time": times[0].isoformat(), "last_source_time": times[-1].isoformat(),
                   "timezone": "Unspecified by the source CSV. Preserve the source clock without claiming UTC.",
                   "fetched_at": datetime.now(timezone.utc).isoformat()}
        output.write_bytes(content)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    acquire(Path("artifacts/component-audit/v1"))
