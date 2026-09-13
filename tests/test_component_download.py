import hashlib
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("component_download", Path(__file__).parents[1] / "scripts/download_component_sources.py")
download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download)


def test_source_integrity_handles_multipart_etags_and_rejects_corruption(tmp_path):
    payload = b"a known public source payload"
    path = tmp_path / "source.zip"
    path.write_bytes(payload)
    parts = [payload[i:i+8] for i in range(0, len(payload), 8)]
    checksum = hashlib.md5(b"".join(hashlib.md5(part).digest() for part in parts)).hexdigest() + f"-{len(parts)}"
    item = {"bytes": len(payload), "checksum": "multipart-md5:" + checksum, "part_size_bytes": 8}
    assert download.verify_file(path, item) == hashlib.sha256(payload).hexdigest()
    path.write_bytes(b"x" + payload[1:])
    with pytest.raises(ValueError, match="checksum"):
        download.verify_file(path, item)
    path.write_bytes(payload[:-1])
    with pytest.raises(ValueError, match="size"):
        download.verify_file(path, item)
