# Slide-rail sound benchmark

This design is fixed before training and test release. It applies only to `slider-audio-v1`.

The user authorized MIMII with documented shortcomings when no suitable dated replacement exists on September 13, 2026. The dated alternatives reviewed in the dataset audit have too few independent machines, inaccessible raw data, or inadequate signals. Fan, pump, valve, gearbox, and bearing retain their dated sensor datasets.

## Sources and limits

Use only the slide-rail archives from [DCASE development record 3678171](https://zenodo.org/records/3678171) and [additional training record 3727685](https://zenodo.org/records/3727685). Preserve their CC-BY-NC-SA-4.0 license. The source catalog records publisher checksums and source metadata.

The [DCASE protocol](https://dcase.community/challenge2020/task-unsupervised-detection-of-anomalous-sounds) defines each machine ID as an individual machine. These mono recordings contain environmental noise and derive from the first microphone. This experiment describes numerical sound-energy patterns. It does not reproduce the DCASE anomaly task or measure fault detection.

Acquisition dates are unknown. ZIP modification dates, file numbers, and release dates do not establish chronology. No chronological test claim is permitted. The stored Unix epoch coordinate represents elapsed time within each clip. It is not an acquisition date. Native TimeF records carry this clock annotation.

## Fixed split

| Partition | Physical machine IDs | Eligible recordings |
| --- | --- | --- |
| Training | 00 | Publisher training folder, normal recordings only |
| Validation | 02 | Publisher training folder, normal recordings only |
| Test | 01, 03, 04, 05, 06 | All supplied recordings for these machines |

Exclude all exact PCM duplicates across the inventory before extracting signals. Do not include alternative microphone or noise versions of the same source. Do not join separate recordings. Device identity, file name, source condition, and target text never enter model inputs.

This uncalibrated description benchmark has no calibration partition. Five test machines permit a limited exact paired-group check. One training machine and one validation machine severely limit development diversity. Windows and recordings from the same machine are not independent test groups. Shared environmental noise and recording sessions may introduce additional dependence.

## Signals and training

Decode signed 16-bit mono PCM at 16 kHz. Use 512-sample frames with no overlap. Apply a Hann window and calculate one-sided spectral energy, normalized by `512 * sum(window**2)`. Double interior FFT-bin power. Sum bins below 2 kHz and bins from 2 through 8 kHz separately. Take each square root to obtain two RMS channels in normalized digital units. These units are not calibrated sound pressure.

Each example contains 28 consecutive frames, or 0.896 seconds. Availability is the end of each frame. A ten-second clip supplies eleven complete windows. Discard the remaining frames. Targets use the existing weak numerical pattern rules with a minimum band of 0.000001. These targets are signal descriptions, not source anomaly labels.

Initialize this model independently from the pinned Gemma OpenTSLM checkpoint. Update the temporal encoder, projector, and rank-8 attention LoRA. Freeze original Gemma weights. Use all eligible training windows in the first epoch. Later epochs mix half natural windows, one-quarter reversal, and one-quarter shuffle. Select the lowest completed-epoch loss on 256 fixed-hash validation windows and equal reversed and shuffled views.

Use one free RTX PRO 6000 GPU in the existing Nebius VM. The shared phase reservation remains $50.45 within the total $600 ceiling. Train at most twelve epochs or thirty minutes. Stop after three nonimproving completed epochs, after at least three epochs. Nonfinite values, the parent completion stop, and the absolute provider deadline also stop work. Export any complete checkpoint before considering a bounded resume.

## Frozen evaluation

Export and hash the selected checkpoint before releasing test values. Select up to 1,024 windows per test machine by fixed task hashes, without target-based selection. Preserve the industrial study's numerical quality thresholds. Require at least 95% valid outputs, higher supported-class macro F1 than each baseline, and positive paired-group accuracy gains. Require positive lower 95% group-bootstrap bounds and one-sided exact paired-group sign probability at most 0.05. Baselines are the starting checkpoint, constant answers, and zeroed numerical inputs.

Reversal and shuffle must each change at least 32 targets in every test machine. The model must respond more accurately than unchanged original answers under the same group checks. Require sixteen identical predictions after GPU checkpoint reload. Record CPU portability separately because floating-point kernels can change borderline greedy answers across devices.

Save source hashes, clip and split manifests, native TimeF proof, training configuration, overview, checkpoints, validation records, raw generations, metrics, reload evidence, export hashes, and compute costs. Any failure remains a failure in the original report.
