# Component dataset audit

This review started on September 13, 2026. The historical HDD model has passed its held-out gate. All thirteen component categories have passed their declared tests and verified exports, including the separate industrial-valve sound model. Both dated valve failures remain recorded. Source descriptions below are verified against publisher records. A candidate is not ready for training until its downloaded data passes the device, time, channel, and split checks.

Public metadata snapshots and checksum receipts are in `artifacts/component-audit/v1/`. The DCBrain review pins revision `07314287ca0858b9a7d8dba951c96394487e2be2`. The ClusterWise review pins dataset revision `93fb62c369fcfb36536252a9bb4a539dcdb2b229` and preparation code revision `265302720c020e97256718973232aeb0b3fa2641`. These records support a source audit, not a trained-model claim.

## Separate model candidates

| Component | Preferred source under review | Supported task and remaining checks |
| --- | --- | --- |
| HDD | Complete Backblaze archive | Full training pass and all frozen held-out checks passed, including numerical dependence and exact reload. |
| SSD | SSD records in the acquired Backblaze archive | Native dataset ready for two BarraCuda 120 capacities. Separate temperature and power-on-hour descriptions. |
| NVMe | Ceph device telemetry | Expanded native dataset ready from all 33 months. No verified failure outcomes. |
| RAM / DRAM | SmartMem raw data | Native dataset ready. Describe recorded read-error and scrub-error log counts. Missing logs do not establish healthy operation. |
| GPU | ClusterWise / OLCF Summit | Native dataset ready. Separate GPU power, core temperature, and memory temperature. Splits group all adjacent devices by host. |
| CPU | ClusterWise / OLCF Summit | Native dataset ready. Separate processor power and mean core temperature. No GPU error labels enter this model. |
| Whole server | ClusterWise / OLCF Summit | Native dataset ready. Describe the two node power-supply input signals. Separate weights from CPU and GPU models. |
| Fan | Marconi100 ExaData | All 49 rack archives verified. Native preparation uses dated fan-module RPM signals, separate hosts, and ordered time partitions. |
| Pump | Cubico wind-turbine SCADA | Gear-oil-pump pressure model passed its five-group industrial study. |
| Valve | HOMESENSE | Radiator-valve model failed both frozen and follow-up gates. A separate MIMII industrial-valve sound model passed under the authorized unknown-date exception. |
| Gearbox | Cubico wind-turbine SCADA | Gearbox oil-temperature model passed its five-group industrial study. |
| Bearing | Cubico wind-turbine SCADA | Generator-bearing temperature model passed its five-group industrial study. |
| Slide rail | MIMII-derived DCASE 2020 | Sound-description benchmark passed. File indices do not establish recording dates. |

## Storage sources

The local Backblaze source audit found 5,788,269 SSD rows. The largest named model has 2,021,382 rows across 1,166 serials. Temperature and power-on fields have broad coverage for several SATA SSD models. `DELLBOSS VD` has almost no usable SMART values. Exclude it from the proposed signal model. See `backblaze-ssd-coverage.json` for measured counts and date ranges.

The prepared SSD cohort contains `Seagate BarraCuda 120 SSD ZA250CM10003` and `ZA500CM10003`. The manufacturer identifies SMART 09h as power-on hours and C2h as temperature. Local observed values support the decoded temperature field. The preparation uses the raw fields for these verified meanings. It treats a snapshot as available at the next midnight and excludes recorded failure dates and later rows. [Manufacturer manual](https://www.seagate.com/content/dam/seagate/migrated-assets/www-content/support-content/internal-products/barracuda/barracuda-ssd/_shared/masters/100858062_A.pdf)

Alibaba's `ssd_open_data` release contains one day's SMART readings, plus location and failure information. It cannot supply a multiday SMART sequence by itself. Its separate `ssd_smart_logs` release supplies daily records for 2018 and 2019. The two releases overlap in device identities. They are not independent cohorts. The latter download uses Tianchi dataset 95044. Source access and SMART meanings still need a data audit. [SSD source descriptions](https://github.com/alibaba-edu/dcbrain/tree/07314287ca0858b9a7d8dba951c96394487e2be2/ssd_smart_logs)

The backlog's former NVMe link, Tianchi 132973, actually identifies Alibaba's DRAM dataset. The ATC 2022 NVMe source is Tianchi 128972. SNIA IOTTA also lists it as trace 36779. Its SMART tables describe snapshots. Its latency archive contains timestamped drive columns, node metadata, missing values, and restricted daily observation hours. Use only the SSD subset for an NVMe model. A retrieved sample confirms `ts` and 12 drive columns. [NVMe dataset](https://tianchi.aliyun.com/dataset/128972), [publisher README](https://iotta.snia.org/traces/reliability/36779/download?type=readme)

The separate Perseus release, SNIA trace 36782, contains mixed HDD and SSD latency/throughput records. Its README describes 15 consecutive observation days per cluster. A slow-drive list does not give an exact failure onset for every observation. Component identity needs verification before selecting an NVMe subset. Both SNIA full-download paths request downloader identity and organization. No registration form was submitted. [Perseus README](https://iotta.snia.org/traces/reliability/36782/download?type=readme)

Ceph publishes monthly reports with timestamps, device UUIDs, an invalid-report flag, and SMART/NVMe JSON. Its publisher explicitly states that drive-failure labels are absent. Invalid telemetry is a collection error, not a failed disk. A downloaded January 2020 probe has 1,102 records across 89 UUIDs, including 33 NVMe reports. It exposes temperature, spare capacity, media errors, and wear indicators. These observations establish schema availability, not enough independent devices for training. The published data terms are CDLA Sharing 1.0. [Ceph source](https://ceph.io/en/users/telemetry/device-telemetry/)

The complete January 2021 probe has 548,832 reports, including 19,776 NVMe reports from 812 devices on 342 hosts. The first prepared cohort uses all 18 months through June 2021. It joins connected host and device identities into split groups, including device migrations. It requires 28 consecutive reporting days. It produced 2,106 training windows across 146 groups, but only 63 validation groups. This is below the unchanged 64-group telemetry readiness requirement. No model used this cohort. A new version expands through September 2022 and reserves July–September 2022 for test.

All 33 expanded archives passed size and checksum verification. They total 58,506,221,424 bytes. The September 2022 file uses a 708-part composite MD5 checksum with 8 MiB parts. The complete downloaded file matched that checksum and has SHA-256 `ad025fa72a8b967b4635c6fc4b905f2238c994abfed3b69c31f909612ff3249d`. Expanded native preparation passed. Its manifest SHA-256 is `9b2dd451cd214f2039866399bd2a3d76bc758f7f0db087282418fab0e52c5cf5`.

The NVMe fields are composite temperature, media errors, power-on hours, and percentage used. Smartctl converts NVMe temperature to Celsius before writing JSON. Its source also defines the counter fields. The audit pins smartmontools revision `9f83095a631ff71df44f8065c7a4a00134d3d404`. Ceph's version-16 device-health code uses a UTC scrape clock. TimeNet 0.1.0 lacks a CDLA enum entry, so native metadata uses `other` with the exact license URL. The component config retains `CDLA-Sharing-1.0`. [JSON field definitions](https://github.com/smartmontools/smartmontools/blob/9f83095a631ff71df44f8065c7a4a00134d3d404/smartmontools/nvmeprint.cpp), [Ceph scrape clock](https://github.com/ceph/ceph/blob/v16.2.0/src/pybind/mgr/devicehealth/module.py)

## Memory and compute sources

SmartMem publishes DIMM-indexed error histories and separate failure tickets. Its documented schema includes error timestamps and memory location fields. The public Zenodo archive is 5,621,070,729 bytes and declares CC BY-NC 4.0. The audit uses raw data before considering precomputed features. Do not interpret absent error rows as verified healthy observation time without evidence. Do not treat CPU identifier fields as CPU telemetry. [Schema](https://hwcloud-ras.github.io/SmartMem.github.io/dataset), [archive](https://zenodo.org/records/15516113)

The verified archive contains 64,794 type-A DIMM files and 7,175 type-B files. Its layout differs from the website's generic train/test description. The preparation selected 13,000 DIMMs by fixed hashes before reading their logs or tickets. It streamed 202,637,802 records without extracting the roughly 200 GB full archive. It sorted the source timestamps and counted `CE.READ` and `CE.SCRUB` logs by closed UTC day. A zero means no recorded logs. It is not a health label. Each window ends on a day with a recorded log and remains before a known failure-ticket boundary.

Alibaba DRAM is an alternative with timestamped error logs, server inventory, and server failure tickets. Its date origin is deliberately anonymized to year 0001. Preserve that ordered source clock without inventing real calendar dates. DIMM slots and physical replacement identities need separate checks. [DRAM source](https://github.com/alibaba-edu/dcbrain/tree/07314287ca0858b9a7d8dba951c96394487e2be2/dramdata)

ClusterWise provides CPU/GPU temperatures, component power, node identity, and timestamps. The pinned file listing totals 221,012,378,627 bytes, including small repository files. Its five recording months permit ordered train, validation, and test periods. It declares CC BY 4.0. The proposed models use separate channel groups and checkpoints, with common host assignments to prevent overlap across splits. [Dataset](https://huggingface.co/datasets/MachaParfait/ClusterWise/tree/93fb62c369fcfb36536252a9bb4a539dcdb2b229), [original OLCF measurements](https://doi.ccs.ornl.gov/dataset/086578e9-8a9f-56b1-a657-0ed8b7393deb)

The pinned preparation code joins error labels to the nearest report within 60 seconds. It also includes eventual job end times. Exclude `label`, `xid`, and job completion metadata from causal numerical inputs. Verify the availability time of each ten-second mean before choosing window cutoffs. The CPU reduction averages simultaneous core values and omits core 13. Preserve that source definition. [Preparation code](https://github.com/YiyangLu/hpc_dataset/blob/265302720c020e97256718973232aeb0b3fa2641/src/generate_olcf.py), [CPU reduction](https://github.com/YiyangLu/hpc_dataset/blob/265302720c020e97256718973232aeb0b3fa2641/src/generate_olcf_mini.py)

Seven pinned daily files, totaling 11,715,626,783 bytes, are downloaded and checksum-verified. January 2020 supplies training days, August 2020 supplies validation and calibration days, and February 2021 supplies test days. Fixed hashes select 600 training hosts, 200 validation hosts, 128 calibration hosts, and 256 test hosts. CPU and GPU missingness excludes two validation hosts. Windows contain 28 ten-second means. The preparation conservatively delays availability by ten seconds. The first source day has 39,968,634 rows across 4,626 hosts. [Published channel meanings](https://github.com/YiyangLu/hpc_dataset/blob/265302720c020e97256718973232aeb0b3fa2641/README.md)

Alibaba's GPU 2020 trace includes over 6,500 GPUs, but its sensor table averages each job instance's lifetime. This is not a regular causal sensor sequence. It is unsuitable as a direct replacement for the proposed telemetry windows. [Publisher schema](https://github.com/alibaba/clusterdata/tree/master/cluster-trace-gpu-v2020)

SMD contains 28 machines with 38 unnamed numerical dimensions. Its published train/test halves reuse the same machines. The proposed program requires disjoint devices, named channel semantics, and ordered time partitions. The standard SMD split does not establish these properties. Prefer OLCF for the current whole-server model. [SMD documentation](https://github.com/NetManAIOps/OmniAnomaly)

LANL and USENIX provide valuable outage and component-failure records. They do not by themselves establish continuous CPU sensor coverage or healthy exposure intervals. The reviewed USENIX page lists Blue Gene/L event logs. It does not verify the backlog's specific Blue Gene/P Intrepid claim. [LANL catalog](https://usrc.lanl.gov/data%20sources/failure-data.php), [USENIX catalog](https://www.usenix.org/cfdr-data)

## Industrial sources

Marconi100 ExaData provides node-aggregated IPMI observations under CC BY 4.0. All 49 rack archives from record 7541722 passed publisher MD5 and local SHA-256 checks. They total 24,781,639,680 bytes. The source has UTC timestamps and eight fan-rotor channels per host. The pinned IPMI documentation defines these values in RPM. [Dataset](https://zenodo.org/records/7541722), [IPMI channel definitions](https://gitlab.com/ecs-lab/exadata/-/blob/db994a39cb256da3d623fbfe28257a4531db075f/documentation/plugins/ipmi.md)

The source code averages each left-labeled fifteen-minute interval. Preparation delays model availability until the interval ends. Each example contains two rotors from one fan module. All four modules share their host's split. The schema-probe rack is excluded from the formal study. Fixed hashes select hosts and eligible, nonoverlapping seven-hour windows before model fitting. Training uses March 2020 through December 2021. Validation, calibration, and test use successive quarters of 2022. Nagios labels and other component signals are excluded. [Aggregation code](https://gitlab.com/ecs-lab/exadata/-/blob/db994a39cb256da3d623fbfe28257a4531db075f/parquet_dataset/node_aggregated_data/step1.py)

The fan task describes observed speed patterns. It does not infer physical fan failures from the node's Nagios status. Native preparation verified 203,264 training windows from 397 hosts, 127 validation hosts, 64 calibration hosts, and 116 test hosts. Its manifest SHA-256 is `ae02e2692a9ae8065a2de9c35bf874048d735e272c445c96c9477ef0f8d62e9e`. The adapter and component controllers pass 77 tests in the working checkout and a fresh locked environment. `config/m100_fan_sources.json` retains the reproducible source catalog and required schema snapshots.

MIMII contains normal and deliberately abnormal machine sounds. The original public record covers fan, pump, valve, and slide rail models under CC BY-SA 4.0. Its public 1.0 note specifies four model IDs. Noise variants reuse underlying machine recordings, so they cannot become independent split examples. Capture chronology still needs evidence. [Original dataset](https://zenodo.org/records/3384388), [recording method](https://arxiv.org/abs/1909.09347)

MIMII DUE adds gearbox data and domain shifts under CC BY-NC-SA 4.0. It duplicates parts of the DCASE 2021 datasets. MIMII DG covers fan, gearbox, bearing, slide rail, and valve sounds. Its metadata says CC BY 4.0, while its conditions-of-use text says CC BY-NC-SA 4.0. Record this conflict and use the more restrictive stated conditions pending clarification. [DUE](https://zenodo.org/records/4740355), [DG](https://zenodo.org/records/6529888)

DCASE 2022 defines sections by domain shift. They do not universally identify separate physical machines. Filenames expose condition labels and operating attributes. Exclude these labels from numerical inputs. Published section numbers and clip indices do not prove ordered acquisition dates. This remains a blocker for the project's current split contract. [DCASE definitions](https://dcase.community/challenge2022/task-unsupervised-anomalous-sound-detection-for-machine-condition-monitoring)

NASA lists the IMS bearing archive as public experimental data from the University of Cincinnati. Audit its archive metadata, bearing identities, and recorded timestamps before declaring it suitable. [NASA record](https://data.nasa.gov/dataset/ims-bearings)

Paderborn's newer bearing release contains 17 separate experiments with dated temperature and operating-condition tables. A bounded ZIP-range probe retrieved the B01 temperature CSV and verified its ZIP CRC. Its 377 observations have explicit October 19, 2021 timestamps. The CSV SHA-256 is `00f7ebee199faae866bcfbffec22a8a4201914461411f99d35f3d9e6078323f2`. This probe transferred 42,460 bytes. It did not download or verify the complete 965.9 MB ZIP. This is a promising chronological alternative, but 17 experiments require an explicit small-laboratory evaluation design. [Paderborn dataset](https://zenodo.org/records/10868257)

The later bounded probe retrieved all 17 temperature tables. Each passed its ZIP CRC check. The tables contain 95,660 observations from October 19, 2021 through November 5, 2022. The transfer totaled 5,106,572 bytes. Receipts preserve each member's SHA-256, source range, dates, and archive checksum limitation. The CSVs do not declare a time zone. Preserve their source clock without claiming UTC. `scripts/probe_bearing_temperatures.py` reproduces the bounded acquisition.

Other reviewed bearing and gearbox sources have few physical units. DLR's needle-bearing release has eight tests with two bearings per test. Lenze-GD has three gearmotor degradation experiments. Their observation clocks and independent validation support need inspection before fitting. [DLR dataset](https://zenodo.org/records/20742913), [Lenze-GD](https://zenodo.org/records/11162448)

FAN-COIL-I records one fan-coil motor, despite its many high-rate observations. RepOD's exhaust-fan release has dated vibration and temperature readings, but only two physical fans. Individual sensors cannot become independent machines. These sources may support a combined fan-specific study after a compatible channel and split audit. [FAN-COIL-I paper](https://arxiv.org/abs/2408.14448), [RepOD exhaust fans](https://doi.org/10.18150/4BIBFA)

RICO is another source of pump, fan, and valve-related operating signals. It comes from a dedicated test building. The reviewed description does not establish independent component populations for all required splits. It is not yet a substitute for the industrial models. [Publisher record](https://www.sintef.no/en/publications/publication/2391974/)

NIST's rail-degradation experiment has dated archives from April and May 2017. It repeatedly measures one intentionally degraded rail across 15 stages. Runs, speeds, and degradation stages are not independent rails. This source alone cannot meet disjoint-device train, validation, and test requirements. [NIST record](https://data.nist.gov/pdr/lps/6EF435207EF17114E0532457068155831934)

CIRA publishes dated measurements from three industrial centrifugal pumps. The pinned Zenodo record has nine pump-day CSV files and a README. The related paper describes eight files, so use the actual versioned inventory. Pump contact temperature, vibration, and pressure have source definitions. Three machines remain insufficient for the current telemetry study. [Dataset](https://zenodo.org/records/15301820), [source paper](https://www.mdpi.com/2306-5729/10/6/91)

The nine CSVs and README now pass publisher checksums. The README says the October pump-C file is absent, but the archive includes it. Its pressure and temperature suffixes also differ from the actual headers. Preserve these conflicts and use verified column meanings before preparation. The dataset alone still cannot provide four disjoint device partitions.

Cubico publishes dated ten-minute SCADA histories from six Kelmarsh turbines and fourteen Penmanshiel turbines under CC BY 4.0. These are candidates for gearbox and bearing temperature descriptions. Native channel coverage and component replacement identities still need verification. Combining these two sources would combine data within each component category, with separate gearbox and bearing weights. [Kelmarsh](https://zenodo.org/records/8252025), [Penmanshiel](https://zenodo.org/records/8253010)

The selected 2018–2020 SCADA archives, site inventories, and channel dictionaries are downloaded and checksum-verified. Real CSV headers declare UTC. They name gear-oil and generator-bearing temperatures in Celsius, and gear-oil-pump and oil-inlet pressures in bar. Separate native gearbox, bearing, and pump datasets passed read-back checks. The combined Cubico and CIRA acquisition contains 23 files totaling 3,465,915,597 bytes. CIRA data does not enter these models.

HOMESENSE supplies eleven pseudonymized households with explicit timezone offsets and ten-minute valve observations. The adapter uses motor position, device temperature, and temperature setpoint. It requires all three quality flags to be `observed`. It excludes interpolation, imputation, unrelated household signals, and values outside the documented motor-position range. All valves from one household share a partition. These are radiator valves, so the result cannot establish industrial process-valve performance. [HOMESENSE release and source preprocessing](https://zenodo.org/records/21687970)

The four industrial studies use the frozen [small-study design](industrial-study-design.md). Their five test groups are fewer than the large telemetry cohorts require. Exact group-level tests and paired group intervals support only this limited population. Window counts do not increase the number of independent machines. `config/industrial_sources.json` pins 25 required files, 4,225,595,495 bytes, and the original metadata snapshots. Every file passed publisher checksum and SHA-256 verification.

The slide-rail audit read the original MIMII ZIP directory and eight WAV samples through bounded HTTP ranges. The directory contains only four device IDs. Sampled WAV files contain `fmt`, `fact`, and `data` chunks, with no acquisition-date fields. ZIP modification times do not establish recording chronology. The audit transferred 14,649,316 bytes and verified each sampled member's CRC. It did not verify or download the full archive. Receipts are `mimii-slider-central-directory.json` and `mimii-slider-wav-metadata-audit.json`. Slide rail remains unready under the current chronology and independent-device requirements. [Publisher dataset](https://zenodo.org/records/3384388), [DCASE machine-ID definitions](https://dcase.community/challenge2020/task-unsupervised-detection-of-anomalous-sounds)

CARE to Compare contains 95 selected histories from 36 turbines. These are not 95 independent machines. Some features and power values are anonymized, and the publisher lists quality problems in minimum, maximum, and standard-deviation fields. Its EDP portion overlaps the earlier EDP release. Do not count these as independent sources or infer physical units from anonymous names. [Pinned current record](https://zenodo.org/records/15846963)

## Other slide-rail candidates

NIST's rail-degradation experiment records fifteen damage stages on one intentionally degraded rail. Repeated motions and damage stages do not establish new physical units. Its separate IMS run-to-failure record follows one linear axis and emphasizes ball-screw backlash. Both provide useful dated experiments, but neither alone supplies separate development and test machines. [Rail experiment](https://catalog.data.gov/dataset/linear-axis-testbed-rail-degradation-experiment-01), [IMS experiment](https://catalog.data.gov/dataset/linear-axis-testbed-at-ims-center-run-to-failure-experiment-01)

The 2026 Stuttgart release contains measured position, torque, and velocity for controller experiments on one five-axis milling machine. Axes and repeated controller settings cannot be counted as independent machines. No files were acquired for model training. [Stuttgart data](https://doi.org/10.18419/DARUS-6114)

A recent linear-guide dynamics study offers data only on request. Another guide-design study keeps its data and code private. These papers do not provide downloadable chronological cohorts for this program. No contact forms or requests were sent. [Longitudinal dynamics](https://doi.org/10.1007/s11340-026-01349-4), [Guide design](https://ms.copernicus.org/articles/17/141/2026/)

## Training readiness

Seven independent component models started training after the HDD gate passed. Their shared phase uses one GPU per model and a bounded provider stop. Counts below refer to selected eligible windows, not every observation in their original archives.

| Component | Training windows | Training groups | Validation groups | Calibration groups | Test groups |
| --- | ---: | ---: | ---: | ---: | ---: |
| SSD | 31,269 | 703 | 166 | 112 | 159 |
| DRAM | 34,089 | 3,553 | 925 | 428 | 1,027 |
| CPU | 114,840 | 600 | 198 | 128 | 256 |
| GPU | 344,520 | 600 | 198 | 128 | 256 |
| Server | 57,420 | 600 | 200 | 128 | 256 |
| NVMe first cohort | 2,106 | 146 | 63 | 40 | 105 |
| NVMe expanded cohort | 51,105 | 1,085 | 268 | 199 | 337 |
| Fan | 203,264 | 397 | 127 | 64 | 116 |

CPU/GPU/server groups are hosts. SSD and DRAM groups are separate physical device identities. NVMe groups connect all observed host/device migrations. Every prepared native record, numerical value, time axis, annotation, task, and scoped model input passed read-back checks.

Before each run, save an explicit task, channel dictionary, source hashes, device/time split manifest, baseline, acceptance criteria, and bounded compute overview. A source with missing identity or chronology stays unready until those facts are established. More compute cannot repair missing provenance.

Preserve preparation failures as evidence. The first ClusterWise query used a reserved SQL field name and emitted no windows. A regression-tested field rename fixed it. The initial Ceph preparation lacked a standard receipt for the earlier January 2020 probe. The existing file then passed publisher size/checksum verification. A later native write rejected the unsupported CDLA enum value. The documented `other` mapping retained the exact source terms. No failure required weakening a data or test check.

## Selected slide-rail fallback, September 13

The user authorized MIMII when no suitable dated replacement exists, with its shortcomings documented. Use the DCASE 2020 mono slide-rail releases from [record 3678171](https://zenodo.org/records/3678171) and [record 3727685](https://zenodo.org/records/3727685). Both archives passed publisher and SHA-256 checks. Together they contain 1,580,514,507 compressed bytes. `config/slider_sources.json` records their source metadata and download recipe.

The [publisher protocol](https://dcase.community/challenge2020/task-unsupervised-detection-of-anomalous-sounds) defines machine IDs as individual physical machines. Seven IDs permit one training machine, one validation machine, and five test machines. This is a narrow development cohort. The adapter excludes publisher test recordings from development, excludes exact PCM duplicates across the retained inventory, and never joins separate clips. It found zero exact duplicates. The final data contains 10,648 training, 10,648 validation, and 40,755 test windows. There is no calibration fit.

The selected release uses CC-BY-NC-SA-4.0. TimeF stores `other` with the full license URL because its enum lacks this exact license. Channel units are dimensionless digital amplitude. They are not calibrated sound pressure. Acquisition chronology remains unknown. Stored epoch coordinates encode clip-relative offsets only, and native record annotations say so. The [fixed study design](slider-study-design.md) records source choices, exclusions, weak targets, test selection, and quality checks. The native adapter passes all 88 repository tests in both working and fresh locked environments.

## Industrial-valve sound fallback, September 13

The HOMESENSE radiator-valve model failed its original support gate and its unchanged-weight follow-up numerical-dependence gate. The latter reused five households and preserved the original failure. See [the result report](component-model-results.md).

The additional dated-data review did not identify an accessible replacement with verified chronology and enough independent groups. The [refinery study](https://arxiv.org/abs/2601.12362) uses plant historian exports, with limited cross-valve evidence and no identified public raw archive. DAMADICS offers only three actuators at one factory. RICO and the UCI hydraulic experiment have inadequate independent installation counts. SACAC resource access timed out, so dates and group identities remain unverified.

Use the separate DCASE/MIMII valve recordings under the user's explicit chronology exception. The two verified archives total 1,629,571,053 bytes. They retain CC-BY-NC-SA-4.0 terms. Machine 00 supplies 891 training recordings and 9,801 windows. Machine 02 supplies 608 validation recordings and 6,688 windows. Five other machines supply 4,763 test recordings and 52,393 windows. Exclude 439 publisher test clips from development machines. No retained exact PCM duplicates were found.

The adapter uses the same causal sound frames and native TimeF checks as slide rail. Acquisition dates remain unknown. No calibration fit or failure-detection claim is permitted. The source manifest is `b0bfccc9ba5e1b5353537874b83e9c2b4bd1b916a0eb4acd0d7bbf77cd6ca66d`. Read [the fixed design](valve-audio-study-design.md) before reproducing this separate model.

The industrial-valve sound model passed its frozen five-machine test. This result supports weak sound-energy descriptions only. It does not replace either failed radiator-valve telemetry result or establish acquisition chronology. Final metrics and source limits are in [component results](component-model-results.md).
