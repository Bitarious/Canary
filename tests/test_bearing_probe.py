import io
from pathlib import Path
import runpy
import zipfile

import pytest


def test_range_probe_reads_zip_members_and_rejects_full_body_response(monkeypatch):
    reader_class = runpy.run_path(str(Path(__file__).parents[1] / "scripts/probe_bearing_temperatures.py"))["RangeReader"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("temperature.csv", "Time,value\n2021-01-01,23.5\n")
    payload = buffer.getvalue()
    def response(url, headers, **kwargs):
        start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        class Reply:
            status_code = 206
            def __init__(self):
                self.headers = {"Content-Range": f"bytes {start}-{end}/{len(payload)}"}
                self.raw = io.BytesIO(payload[start:end+1])
            def raise_for_status(self):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return Reply()
    monkeypatch.setattr("requests.get", response)
    reader = reader_class("https://publisher.example/fixture.zip", len(payload))
    with zipfile.ZipFile(reader) as archive:
        assert archive.read("temperature.csv") == b"Time,value\n2021-01-01,23.5\n"
    assert 0 < reader.transferred <= reader.limit
    def ignored_range(*a, **k):
        result = response(*a, **k)
        result.status_code = 200
        return result
    monkeypatch.setattr("requests.get", ignored_range)
    with pytest.raises(ValueError, match="exact requested range"):
        reader_class("https://publisher.example/fixture.zip", len(payload)).read(10)
    with pytest.raises(ValueError, match="transfer limit"):
        reader_class("https://publisher.example/fixture.zip", len(payload), limit=1).read(10)
