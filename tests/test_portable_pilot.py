from copy import deepcopy
import json
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from driftops.cli import checksum, install_sample
from driftops.preview import Preview, handler_for
from driftops.windows import read_yaml


def test_bundled_pilot_installs_repeatably_and_refuses_modified_data(tmp_path):
    source = Path("examples/backblaze-pilot/backblaze.parquet")
    config = read_yaml("config/dataset.yaml")
    destination = tmp_path / "raw" / "backblaze.parquet"
    manifest = install_sample(source, destination, config)
    assert checksum(destination) == manifest["parquet_sha256"]
    assert install_sample(source, destination, config) == manifest
    destination.write_bytes(b"different source")
    with pytest.raises(ValueError, match="Existing raw data differs"):
        install_sample(source, destination, config)


def test_sample_configuration_mismatch_cannot_be_silently_accepted(tmp_path):
    config = read_yaml("config/dataset.yaml")
    config["model"] = "DIFFERENT_MODEL"
    with pytest.raises(ValueError, match="does not match"):
        install_sample(Path("examples/backblaze-pilot/backblaze.parquet"), tmp_path / "raw.parquet", config)


def test_preview_http_contract_and_errors():
    class FixturePreview:
        def window(self, index):
            if index != 0:
                raise ValueError("out of range")
            return {"index": 0, "as_of": "2024-07-28", "model_version": None}

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(FixturePreview()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(address + "/") as response:
            assert "Data preview" in response.read().decode()
        with urlopen(address + "/api/window?index=0") as response:
            assert json.load(response)["as_of"] == "2024-07-28"
        for path, code in [("/api/window?index=-1", 400), ("/api/window?index=nan", 400),
                           ("/api/window?index=999999", 400), ("/config/model.yaml", 404)]:
            with pytest.raises(HTTPError) as error:
                urlopen(address + path)
            assert error.value.code == code
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_preview_excludes_targets_outcomes_and_future_values():
    config = read_yaml("config/dataset.yaml")
    version = Path(config["timef_root"]) / config["dataset_id"] / config["dataset_version"]
    if not (version / "manifest.json").exists():
        pytest.skip("Run driftops prepare first for the real TimeNet integration check")
    preview = Preview()
    output = preview.window(0)
    assert len(preview.tasks) == 7151
    assert len(output["dates"]) == 28
    assert output["dates"][-1] == output["as_of"]
    assert output["partition"] == "train"
    serialized = json.dumps(output)
    assert "recorded_failure" not in serialized and "target" not in output
    expected = deepcopy(output)
    preview.tasks[0].target = "FUTURE_TARGET_SHOULD_NOT_LEAK"
    preview.tasks[0].prompt = "FUTURE_PROMPT_SHOULD_NOT_LEAK"
    assert preview.window(0) == expected
