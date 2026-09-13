from datetime import date
import json
from pathlib import Path
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from driftops.full_archive import ROOT_URL, archive_name, file_hash
from driftops.full_prepare import convert_archive, daily_members, parse_dates


def source_zip(tmp_path, rows, filename="2018-02-25.csv"):
    source = tmp_path / "data_Q1_2018.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(filename, "date,serial_number,model,capacity_bytes,failure,smart_5_raw\n" + rows)
    source.with_suffix(".manifest.json").write_text(json.dumps({"sha256": file_hash(source)}))
    return source


def test_historical_csv_formats_missing_channels_and_restart(tmp_path):
    source = source_zip(tmp_path, "2/25/18,drive,HDD,4.00079E+12,0,1\n2018-02-25,other,HDD,4000790000000,1,2\n")
    destination = tmp_path / "converted.parquet"
    manifest = convert_archive(source, destination)
    table = pq.read_table(destination)
    assert table["date"].to_pylist() == [date(2018, 2, 25)] * 2
    assert table["capacity_bytes"].to_pylist() == [4000790000000] * 2
    assert table["smart_187_raw"].null_count == 2
    assert manifest["rows"] == 2
    assert convert_archive(source, destination) == manifest
    destination.write_bytes(b"changed")
    with pytest.raises(ValueError, match="verification"):
        convert_archive(source, destination)


@pytest.mark.parametrize("rows", [
    "2018-02-26,drive,HDD,10,0,1\n",
    "2018-02-25,drive,HDD,10,2,1\n",
])
def test_invalid_dates_and_failure_flags_are_not_training_rows(tmp_path, rows):
    source = source_zip(tmp_path, rows)
    destination = tmp_path / "converted.parquet"
    manifest = convert_archive(source, destination)
    assert manifest["quarantined_rows"] == 1
    assert len(pq.read_table(destination)) == 0
    assert len(pq.read_table(destination.with_suffix(".quarantine.parquet"))) == 1


def test_missing_serial_is_retained_outside_training_rows(tmp_path):
    source = source_zip(tmp_path, "2018-02-25,,HDD,10,0,1\n2018-02-25,valid,HDD,10,0,1\n")
    destination = tmp_path / "converted.parquet"
    manifest = convert_archive(source, destination)
    assert manifest["rows"] == 1
    assert manifest["quarantined_rows"] == 1
    assert pq.read_table(destination)["serial_number"].to_pylist() == ["valid"]
    assert pq.read_table(destination.with_suffix(".quarantine.parquet"))["serial_number"].to_pylist() == [None]


def test_strict_archive_urls_and_dates():
    assert archive_name(ROOT_URL + "data_2013.zip") == "data_2013.zip"
    for bad in (ROOT_URL + "../data_2013.zip", "https://example.com/data_2013.zip"):
        with pytest.raises(ValueError, match="allowlist"):
            archive_name(bad)
    with pytest.raises(ValueError, match="unsupported date"):
        parse_dates(pa.array(["bad"]))
