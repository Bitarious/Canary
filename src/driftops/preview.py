"""Loopback-only preview of causal TimeNet windows; no model training/inference."""

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from timenet.reader import TimeFReader
from timenet.registry.version import DatasetVersion

from driftops.annotations import describe_channel
from driftops.timenet_connector import model_input
from driftops.windows import read_yaml


def status() -> dict:
    config = read_yaml("config/dataset.yaml")
    version = Path(config["timef_root"]) / config["dataset_id"] / config["dataset_version"]
    return {"dataset": config["dataset_id"], "dataset_version": config["dataset_version"],
            "timef_ready": (version / "manifest.json").is_file(),
            "base_model": read_yaml("config/model.yaml")["base_model"]["repo_id"],
            "model_state": "not_loaded_in_preview", "training_state": "offline_runner_available",
            "capability": "Real observed windows and deterministic descriptions",
            "limitations": ["No learned predictions or calibrated failure probabilities",
                            "Generated descriptions use measured rules, not OpenTSLM inference"]}


class Preview:
    def __init__(self):
        config = read_yaml("config/dataset.yaml")
        version = Path(config["timef_root"]) / config["dataset_id"] / config["dataset_version"]
        self.dataset = TimeFReader(DatasetVersion.open_local(version)).read()
        self.records = {record.record_id: record for record in self.dataset.records}
        # Development-only preview leaves the later test set for frozen evaluation.
        self.tasks = [task for task in self.dataset.tasks if any(
            ann.key == "partition" and ann.value == "train"
            for ann in self.records[task.record_ids[0]].annotations)]
        self.tasks.sort(key=lambda task: task.id)

    def window(self, index: int) -> dict:
        if index < 0 or index >= len(self.tasks):
            raise ValueError("Window index outside the development preview")
        task = self.tasks[index]
        record = self.records[task.record_ids[0]]
        inputs = model_input(record, task)
        # TimeNet stores the origin as integer microseconds since the Unix epoch.
        start = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            microseconds=record.start_time + task.scope.start_us)
        dates = [(start + timedelta(days=i)).date().isoformat() for i in range(28)]
        channels = []
        for text, values in zip(inputs["time_series_text"], inputs["time_series"]):
            channel = text.split(";", 1)[0]
            channels.append({"name": channel, "values": values, "evidence": describe_channel(channel, values)})
        return {"index": index, "count": len(self.tasks), "window_id": task.id,
                "as_of": dates[-1], "dates": dates, "channels": channels,
                "dataset_version": str(self.dataset.metadata.dataset_version),
                "model_version": None, "description_source": "deterministic_observed_window_rules",
                "quality": "complete_28_day_window", "partition": "train",
                "provenance": "Backblaze Drive Stats / ST8000NM0055 / July-December 2024 pilot",
                "limits": status()["limitations"]}


def handler_for(preview: Preview):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request = urlparse(self.path)
            try:
                if request.path == "/":
                    body = Path(__file__).with_name("preview.html").read_bytes()
                    self.respond(200, body, "text/html; charset=utf-8")
                elif request.path == "/api/status":
                    self.respond(200, json.dumps(status()).encode(), "application/json")
                elif request.path == "/api/window":
                    index = int(parse_qs(request.query).get("index", ["0"])[0])
                    self.respond(200, json.dumps(preview.window(index)).encode(), "application/json")
                else:
                    self.respond(404, b'{"error":"Not found"}', "application/json")
            except (ValueError, IndexError):
                self.respond(400, b'{"error":"Invalid development window index"}', "application/json")

        def respond(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(port: int = 8000):
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    preview = Preview()
    with ThreadingHTTPServer(("127.0.0.1", port), handler_for(preview)) as server:
        print(f"DriftOps data preview: http://127.0.0.1:{port} ({len(preview.tasks)} development windows)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
