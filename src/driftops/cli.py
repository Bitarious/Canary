"""Portable commands for the real-data pilot. Run from the repository root."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from driftops.acquire import write_json
from driftops.windows import read_yaml


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def install_sample(sample: Path, destination: Path, config: dict) -> dict:
    manifest = json.loads(sample.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    if checksum(sample) != manifest["parquet_sha256"]:
        raise ValueError("Bundled sample checksum mismatch")
    for key in ("model", "start", "end", "max_drives"):
        if manifest[key] != config[key]:
            raise ValueError(f"Bundled sample does not match dataset configuration: {key}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if checksum(destination) != manifest["parquet_sha256"]:
            raise ValueError("Existing raw data differs; choose a separate dataset version instead of overwriting it")
    else:
        temporary = destination.with_suffix(".parquet.part")
        shutil.copyfile(sample, temporary)
        if checksum(temporary) != manifest["parquet_sha256"]:
            raise ValueError("Sample copy checksum mismatch")
        temporary.replace(destination)
    manifest_path = destination.with_suffix(".manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("Existing source manifest differs from the bundled pilot")
    else:
        write_json(manifest_path, manifest)
    return manifest


def prepare() -> None:
    from driftops.timenet_connector import BackblazeConnector, build
    connector = BackblazeConnector()
    config = connector.config
    install_sample(Path("examples/backblaze-pilot/backblaze.parquet"), Path(config["raw_path"]), config)
    version = Path(config["timef_root"]) / config["dataset_id"] / config["dataset_version"]
    print("Verifying existing TimeF version" if version.exists() else "Building the bundled pilot through TimeNet", flush=True)
    build(verify_only=version.exists())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="Install the bundled pilot, build/reuse TimeF, and verify all data")
    sub.add_parser("status", help="Show data/model capabilities without authentication or training")
    serve = sub.add_parser("demo", help="Serve the local real-data preview")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "status":
        from driftops.preview import status
        print(json.dumps(status(), indent=2))
    else:
        from driftops.preview import serve
        serve(args.port)


if __name__ == "__main__":
    main()
