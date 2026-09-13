"""Prepare a device-disjoint sound benchmark with an explicit unknown-date exception."""

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import wave
import zipfile

import numpy as np

from driftops.acquire import write_json
from driftops.component_data import build, make_window, partition
from driftops.full_archive import file_hash
from driftops.windows import read_yaml


CONFIG = Path("config/slider_benchmark.yaml")
AUDIT = Path("artifacts/component-audit/v1")
KIND = "slider-audio-benchmark-v1"
ARCHIVES = ("dev_data_slider.zip", "eval_data_train_slider.zip")
MEMBER = re.compile(r"slider/(train|test)/(normal|anomaly)_id_(0[0-6])_[0-9]{8}\.wav")
STUDIES = {
    KIND: ("slide_rail", "slider", "config/slider_sources.json", "docs/slider-study-design.md"),
    "valve-audio-benchmark-v1": ("valve", "valve", "config/valve_audio_sources.json", "docs/valve-audio-study-design.md"),
}


def study(config):
    selected = STUDIES.get(config.get("study"))
    if selected is None or config.get("component") != selected[0]:
        raise ValueError("The sound benchmark component must match its declared study.")
    return selected


def validate_config(config):
    _, folder, _, _ = study(config)
    expected = {"dcase-" + folder + ":" + i: s for i,s in
                (("00", "train"), ("02", "validation"), ("01", "test"),
                 ("03", "test"), ("04", "test"), ("05", "test"), ("06", "test"))}
    if (config.get("group_partitions") != expected
            or config.get("clock_semantics") != "clip-relative-offset-only"
            or config.get("chronology_verified") is not False or not config.get("chronology_exception")
            or config.get("calibration") != "absent-uncalibrated-description-benchmark"
            or config.get("cadence_us") != 32000
            or any(v != {"start": "1970-01-01T00:00:00+00:00", "stop": "1970-01-01T00:00:11+00:00"}
                   for v in config["partitions"].values())):
        raise ValueError("The sound benchmark must retain its declared devices and relative clock exception.")


def decode(content):
    with wave.open(io.BytesIO(content)) as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes(), stream.getcomptype()) != (1, 2, 16000, 160000, "NONE"):
            raise ValueError("A sound recording does not match the pinned mono PCM format.")
        pcm = stream.readframes(160000)
    if len(pcm) != 320000:
        raise ValueError("A sound recording has incomplete PCM samples.")
    return pcm


def features(pcm):
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32768.
    frames = samples[:len(samples) // 512 * 512].reshape(-1, 512)
    window = np.hanning(512)
    power = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2 / (512 * np.square(window).sum())
    power[:, 1:-1] *= 2
    frequency = np.fft.rfftfreq(512, 1 / 16000)
    return np.sqrt(np.column_stack((power[:, frequency < 2000].sum(axis=1),
                                    power[:, frequency >= 2000].sum(axis=1))))


def recording_windows(pcm, recording, group, config):
    values = features(pcm)
    for first in range(0, len(values) - 27, 28):
        # Epoch values encode offsets only. They are never acquisition dates.
        times = (np.arange(first, first + 28) + 1) * 32000
        yield make_window(recording, group, times, values[first:first+28].T, list(config["channels"]), config)


def inventory(config):
    """Hash complete PCM clips before features. Exclude all duplicate recordings."""
    seen, rows, counts = Counter(), [], Counter()
    _, source_folder, _, _ = study(config)
    archives = (f"dev_data_{source_folder}.zip", f"eval_data_train_{source_folder}.zip")
    member_pattern = re.compile(source_folder + r"/(train|test)/(normal|anomaly)_id_(0[0-6])_[0-9]{8}\.wav")
    for name in archives:
        path = AUDIT / name
        receipt = json.loads((AUDIT / (name + "-receipt.json")).read_text())
        if file_hash(path) != receipt["sha256"]:
            raise ValueError("A sound source archive checksum changed.")
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len({m.filename for m in members}) != len(members):
                raise ValueError("A sound archive repeats a member name.")
            for member in members:
                match = member_pattern.fullmatch(member.filename)
                if not match:
                    if member.filename.endswith(".wav"):
                        raise ValueError("A sound archive contains an unexpected recording identity.")
                    continue
                folder, condition, machine = match.groups()
                group = "dcase-" + source_folder + ":" + machine
                split = partition(group, config)
                if split in ("train", "validation") and (folder != "train" or condition != "normal"):
                    counts["excluded_publisher_test_development_clips"] += 1
                    continue
                if not 320000 <= member.file_size <= 400000:
                    raise ValueError("A sound archive member exceeds its PCM size bound.")
                pcm = decode(archive.read(member))
                digest = hashlib.sha256(pcm).hexdigest()
                seen[digest] += 1
                rows.append({"archive": name, "member": member.filename, "group": group, "split": split, "pcm_sha256": digest})
                counts["clips_" + split] += 1
    unique = [row for row in rows if seen[row["pcm_sha256"]] == 1]
    counts["duplicate_clips_excluded"] = len(rows) - len(unique)
    return unique, dict(counts)


def prepare(output, config_path=CONFIG):
    config = read_yaml(config_path)
    validate_config(config)
    _, folder, catalog, _ = study(config)
    archives = (f"dev_data_{folder}.zip", f"eval_data_train_{folder}.zip")
    clips, counts = inventory(config)
    sources = {"config_sha256": file_hash(config_path), "source_catalog_sha256": file_hash(Path(catalog)),
               "source_receipts": {n: json.loads((AUDIT / (n + "-receipt.json")).read_text()) for n in archives},
               "clip_inventory": clips, "inventory_audit": counts,
               "clock": "All stored epoch times are clip offsets. No acquisition chronology is known or inferred.",
               "deduplication": "Exclude every exact duplicate PCM clip before feature extraction, across all splits."}

    def rows():
        for name in archives:
            with zipfile.ZipFile(AUDIT / name) as archive:
                for clip in clips:
                    if clip["archive"] != name:
                        continue
                    pcm = decode(archive.read(clip["member"]))
                    if hashlib.sha256(pcm).hexdigest() != clip["pcm_sha256"]:
                        raise ValueError("An inventoried sound recording changed.")
                    yield from recording_windows(pcm, "clip:" + clip["pcm_sha256"], clip["group"], config)
    result = build(output, rows(), config, sources)
    print(json.dumps({"manifest_sha256": file_hash(output / "dataset-manifest.json"),
                      "windows": {s: result["audit"].get("windows_" + s, 0) for s in result["groups"]},
                      "groups": {s: len(g) for s,g in result["groups"].items()}, "inventory": counts}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    prepare(args.output, args.config)
