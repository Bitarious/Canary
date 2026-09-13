# Industrial-valve sound benchmark

This design is fixed before training and test release. It applies only to `valve-audio-v1`.

The dated radiator-valve model failed its original test and its unchanged-weight follow-up. Preserve both failures. This new model describes industrial-valve sound. It does not establish that the radiator-valve telemetry model works.

The user authorized MIMII with documented shortcomings when no suitable dated replacement exists. The September 13 review found no accessible replacement with verified dates and enough independent groups for this design. HOMESENSE already supplied the dated trial. RICO and the UCI hydraulic rig lack enough independent installations. The DAMADICS benchmark has three actuators at one plant. The recent [refinery study](https://arxiv.org/abs/2601.12362) describes historian exports for a flow-control valve and limited cross-valve validation. It does not supply an identified public archive with five independent test groups. The [SACAC resource page](https://sacac.org.za/resources/) was unavailable during this check, so raw access and chronology remain unverified. These findings do not establish that no other valve dataset exists.

## Sources and limits

Use only `dev_data_valve.zip` from [DCASE record 3678171](https://zenodo.org/records/3678171) and `eval_data_train_valve.zip` from [record 3727685](https://zenodo.org/records/3727685). Preserve their CC-BY-NC-SA-4.0 license. The source catalog records publisher checksums and metadata. Both archive downloads passed publisher checksum and SHA-256 verification before preparation.

The [DCASE protocol](https://dcase.community/challenge2020/task-unsupervised-detection-of-anomalous-sounds) defines machine IDs as individual physical machines. These mono recordings derive from the first microphone and include environmental noise. This experiment describes numerical sound-energy patterns. It does not reproduce the DCASE anomaly task or measure fault detection.

Acquisition dates are unknown. File numbers, ZIP dates, and release dates do not establish chronology. Stored epoch coordinates represent elapsed clip time only. Native TimeF records carry this clock annotation. No calendar-generalization claim is permitted.

## Fixed split

| Partition | Physical machine IDs | Eligible recordings |
| --- | --- | --- |
| Training | 00 | Publisher training folder, normal recordings only |
| Validation | 02 | Publisher training folder, normal recordings only |
| Test | 01, 03, 04, 05, 06 | All supplied recordings for these machines |

Exclude every exact PCM duplicate across the retained inventory before feature extraction. Do not join recordings or include alternate microphone or noise versions. Device identity, file name, source condition, and target text never enter model inputs.

This uncalibrated description benchmark has no calibration partition. One training machine and one validation machine limit development diversity. Test windows and recordings from one machine are not independent groups. Shared noise and recording sessions can add dependence.

## Signals and training

Decode signed 16-bit mono PCM at 16 kHz. Use nonoverlapping 512-sample Hann frames. Normalize one-sided spectral energy by `512 * sum(window**2)` and double interior FFT-bin power. Sum bins below 2 kHz and from 2 through 8 kHz separately. Take their square roots for two RMS channels in normalized digital units. These values are not calibrated sound pressure.

Each example contains 28 consecutive frames, or 0.896 seconds. Frame-end time defines availability. Each ten-second clip supplies eleven complete windows. Discard the remaining frames. The existing numerical pattern rules supply weak targets with minimum band 0.000001. Source anomaly labels are not targets.

Initialize independently from the pinned Gemma OpenTSLM checkpoint. Update the temporal encoder, projector, and rank-8 attention LoRA. Freeze original Gemma parameters. Use all eligible training windows in the first epoch. Later epochs mix half natural windows, one-quarter reversal, and one-quarter shuffle. Select the lowest completed-epoch loss on 256 fixed-hash validation windows and equal reversed and shuffled views.

Use one RTX PRO 6000 GPU for training in the existing eight-GPU Nebius VM. Independent evaluation comparisons can use other GPUs after checkpoint and test freezing. Train at most twelve epochs or thirty minutes. Stop after three nonimproving completed epochs, after at least three epochs. Stop on nonfinite values, cancellation, or the provider guard.

This is a new bounded phase after the previous VM stop. Reserve at most two VM hours, including setup and export, for $28.90 with storage. The shared total ceiling remains $600. Freeze the exact start allowance and UTC deadline in the phase budget before restarting. Install the controller deadline before restart. Verify the guest deadline before training. Stop through the provider after verified exports or at the absolute deadline.

## Frozen evaluation

Export and hash selected weights before releasing test values. Select up to 1,024 windows per test machine by fixed task hashes. Do not select on targets. Preserve the slide-rail and industrial numerical quality thresholds.

Require at least 95% valid outputs and higher supported-class macro F1 than each baseline. Require positive lower 95% group-bootstrap accuracy gains and exact one-sided paired-group sign probability at most 0.05. Compare the starting checkpoint, constant answers, and zeroed numerical inputs.

Reversal and shuffle must each change at least 32 targets in every test machine. Model responses must beat unchanged original answers under the same group checks. Require sixteen identical predictions after GPU checkpoint reload. Record CPU portability separately because hardware can change borderline greedy answers.

Save source hashes, split and clip manifests, native TimeF proof, training records, checkpoints, raw generations, metrics, reload evidence, export hashes, and compute costs. Preserve every failed result. No further fitting is allowed after this run's test release.
