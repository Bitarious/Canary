# Hardware dataset backlog

**Current scope:** complete the historical Backblaze HDD TSLM first. The user has authorized research and separate TSLMs for the other hardware components below if the HDD model passes its evaluation. All runs share the $600 compute ceiling. See the [component training program](component-training-program.md). The listed candidates still require a source audit before use.

These references were supplied by the user on 12 September 2026. Tracking parameters have been removed. The [component dataset audit](component-dataset-audit.md) records the sources checked on September 13 and the remaining data checks. Repeated sources can contain the same physical devices. They are not independent datasets.

## HDD

| Candidate | Role |
|---|---|
| [Backblaze Drive Stats / Hard Drive Test Data](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data) | Selected source for the first HDD demo |
| [Alibaba HDD Dataset - DCBrain diskdata](https://github.com/alibaba-edu/dcbrain/tree/master/diskdata) | Future HDD source |
| [SMART-Z HDD Dataset](https://osf.io/search?q=SMART-Z) | Discovery link; resolve the actual dataset record before use |
| [Baidu HDD SMART Dataset](https://www.kaggle.com/datasets/drtycoon/hdds-dataset-baidu-inc) | Future HDD source; verify upstream provenance |

## SSD

| Candidate | User-provided note to verify |
|---|---|
| [Alibaba SSD Open Data](https://github.com/alibaba-edu/dcbrain/tree/master/ssd_open_data) | Publisher describes nearly 1 million SSDs, but releases only one day of SMART values plus location and failure records |
| [Alibaba SSD SMART Logs](https://github.com/alibaba-edu/dcbrain/tree/master/ssd_smart_logs) | Separate daily histories for 2018–2019, with overlapping devices from SSD Open Data. Download uses Tianchi 95044 |
| [Backblaze Drive Stats](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data) | SSD coverage; choose a separate cohort and semantic mapping |

## NVMe

- [Alibaba NVMe SSD Open Dataset](https://tianchi.aliyun.com/dataset/128972). The previous link, 132973, is the DRAM dataset.
- [SNIA NVMe source README](https://iotta.snia.org/traces/reliability/36779/download?type=readme). Snapshot SMART tables and separate latency histories require different tasks.
- [SNIA Perseus fail-slow README](https://iotta.snia.org/traces/reliability/36782/download?type=readme). Mixed HDD/SSD telemetry requires component identification.
- [Ceph Device Health Telemetry](https://ceph.io/en/users/telemetry/device-telemetry/)
- [Alibaba DCBrain Storage Datasets](https://github.com/alibaba-edu/dcbrain)

## RAM / DRAM

- [Alibaba DRAM Failure Dataset - DCBrain dramdata](https://github.com/alibaba-edu/dcbrain/tree/master/dramdata)
- [Alibaba DRAM Analysis Dataset / Failure Tickets / MCE Logs](https://github.com/zncheng/dramanalysis)
- [SmartMem - Memory Failure Prediction Dataset](https://doi.org/10.5281/zenodo.15516113)
- [SmartMem Raw Competition Dataset](https://www.codabench.org/competitions/3586/)
- [SmartMem Precomputed Features](https://www.kaggle.com/datasets/smartmem/smartmem-features)

## GPU

- [ORNL Summit GPU Double-Bit Error Dataset](https://impact.ornl.gov/en/datasets/olcf-summit-supercomputer-gpu-snapshots-during-double-bit-errors-/)
- [ClusterWise - Summit GPU/System Reliability Dataset](https://huggingface.co/datasets/MachaParfait/ClusterWise)
- [Alibaba GPU Cluster Trace 2020](https://github.com/alibaba/clusterdata/tree/master/cluster-trace-gpu-v2020) - user-provided size: 6,500+ GPUs, to verify.

## CPU / processor / general hardware failures

- [Los Alamos National Laboratory HPC Failure Data](https://usrc.lanl.gov/data%20sources/failure-data.php)
- [USENIX CFDR hardware and event logs](https://www.usenix.org/cfdr-data). The checked page lists Blue Gene/L. The previous Blue Gene/P Intrepid claim remains unverified.

## Whole server / datacenter

- [Server Machine Dataset (SMD)](https://github.com/NetManAIOps/OmniAnomaly/tree/master/ServerMachineDataset)
- [Alibaba Cluster Trace 2018](https://github.com/alibaba/clusterdata/tree/master/cluster-trace-v2018) - user-provided size: approximately 4,000 machines, to verify.
- [Alibaba Cluster Data Repository](https://github.com/alibaba/clusterdata)
- [ClusterWise](https://huggingface.co/datasets/MachaParfait/ClusterWise) - candidate for CPU/GPU temperature, power, failures, and rack layout; verify fields and joins.
- [LANL HPC Component Failure Data](https://usrc.lanl.gov/data%20sources/failure-data.php)

## Mixed HDD / SSD / NVMe telemetry

- [Ceph Device Telemetry Dataset](https://ceph.io/en/users/telemetry/device-telemetry/)
- [Alibaba DCBrain Hardware Reliability Datasets](https://github.com/alibaba-edu/dcbrain)

## Fans / pumps / industrial hardware

- [MIMII - Malfunctioning Industrial Machine Dataset](https://zenodo.org/records/3384388)
- [MIMII DUE - Domain-Shift Machine Failure Dataset](https://zenodo.org/records/4740355)
- [MIMII DG - Fans, Gearboxes, Bearings, Slide Rails & Valves](https://zenodo.org/records/6529888)
- [NASA IMS bearing experiments](https://data.nasa.gov/dataset/ims-bearings)

The MIMII releases require further physical-device and capture-chronology checks. MIMII DG also has conflicting license fields. See the audit before using these sources.

## Before adding a source

For each future addition, verify access and terms, actual hardware coverage, signal modality and semantics, timestamps/cadence, device identities, outcome definitions, censoring, text annotations, and leakage-safe splits. Distinguish anomaly detection, fail-slow behavior, workload traces, and recorded failures. Reuse or build a TimeNet connector and evaluate the source-specific task before combining its results with the HDD demo.

Cross-source joins and transfer claims require evidence. Sources listed under several categories are not independent datasets, and precomputed features need a provenance and leakage audit before training.
