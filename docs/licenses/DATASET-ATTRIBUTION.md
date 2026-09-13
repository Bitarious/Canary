# Dataset attribution and preparation changes

DriftOps trained separate component models using the sources below.
The source authors do not endorse DriftOps or its measured results.
The dataset licenses and source versions remain attached to their records and prepared examples.
See [the license matrix](../model-licenses.md) for the conditions that apply to each source.

## Backblaze Drive Stats

Source and credit: [Backblaze Drive Stats](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data).
The HDD study covers the historical archives through the first quarter of 2026.
The SSD study uses the eligible SATA SSD observations from the same archive collection.
DriftOps selected channels, filtered invalid observations, built consecutive daily windows, and assigned disjoint devices to ordered partitions.
Backblaze remains the source of the measurements. The generated pattern targets and model outputs are DriftOps additions.

## Ceph device telemetry

Source and credit: [Ceph device telemetry](https://ceph.io/en/users/telemetry/device-telemetry/), January 2020 through September 2022.
The source data uses [CDLA-Sharing-1.0](https://cdla.dev/sharing-1-0/).
DriftOps selected NVMe channels, normalized field representations, grouped hosts, and built ordered windows.
Prepared telemetry examples are modified data and retain the source agreement.
The license matrix does not impose model-use restrictions on the independently licensed telemetry data.

## SmartMem

Huawei Technologies, Min Zhou, Hongyi Xie, Qiao Yu, Jialiang Yu, and Zhenli Sheng.
[Smartmem Dataset, Zenodo 15516113](https://zenodo.org/records/15516113).
License: [CC-BY-NC-4.0](https://creativecommons.org/licenses/by-nc/4.0/).
DriftOps aggregated memory-error observations into numerical channels and separated devices and time partitions.
The generated targets describe observed numerical patterns. They are not original fault annotations from the authors.

## OLCF Summit and ClusterWise

Source and credit: OLCF Summit telemetry and the MachaParfait ClusterWise preparation.
[ClusterWise revision 93fb62c369fcfb36536252a9bb4a539dcdb2b229](https://huggingface.co/datasets/MachaParfait/ClusterWise/tree/93fb62c369fcfb36536252a9bb4a539dcdb2b229).
License recorded in the pinned source and run manifests: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
DriftOps selected distinct CPU, GPU, and server-power channels from the prepared Summit measurements.
Each component has separate training, model selection, and test results.

## M100 ExaData

Andrea Borghesi, Carmine Di Santi, Martin Molan, Mohsen Seyedkazemi Ardebili, Alessio Mauri, Massimiliano Guarrasi, and Daniela Galetti.
Also credited: Mirko Cestari, Francesco Barchi, Luca Benini, Francesco Beneventi, and Andrea Bartolini.
[M100 dataset: time-aggregated data for anomaly detection, Zenodo 7541722](https://zenodo.org/records/7541722).
License: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
DriftOps selected observed fan-module speed channels from the node-aggregated IPMI records.
Preparation separates hosts, preserves ordered time partitions, and generates numerical pattern targets.

## Kelmarsh and Penmanshiel

Charlie Plumley and Cubico Sustainable Investments Ltd.
[Kelmarsh wind farm data, Zenodo 8252025](https://zenodo.org/records/8252025).
[Penmanshiel wind farm data, Zenodo 8253010](https://zenodo.org/records/8253010).
License: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
DriftOps selected observed 2018–2020 SCADA channels and used the authors' signal mappings.
The component studies describe gearbox temperatures, generator-bearing temperatures, and gear-oil-pump pressures.
Preparation builds separate component windows and assigns disjoint turbines to ordered partitions.

## HOMESENSE

Yu Sheng, Ali Deger Ozbakir, Deniz Iren, Clara Maathuis, and Stefano Bromuri, Open University of the Netherlands.
[A multisensor dataset of energy use and activity in Dutch social housing, Zenodo 21687970](https://zenodo.org/records/21687970), version 1.0.0.
License: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
DriftOps selected observed radiator-valve motor position, temperature, and setpoint fields.
Preparation excludes interpolated observations and separates households and ordered time partitions.
The released study and unchanged-weight follow-up failed their declared checks. They do not support a passing radiator-valve model claim.

## DCASE 2020 Task 2 and MIMII sound data

NTT Corporation, Hitachi, Ltd., and the dataset authors:
Yuma Koizumi, Yohei Kawaguchi, Keisuke Imoto, Toshiki Nakamura, Yuki Nikaido, and Ryo Tanabe.
Also credited: Harsh Purohit, Kaori Suefusa, Takashi Endo, Masahito Yasuda, and Noboru Harada.

Sources: [development dataset, Zenodo 3678171](https://zenodo.org/records/3678171), version 1.0, and
[additional training dataset, Zenodo 3727685](https://zenodo.org/records/3727685), version 1.0.
License: [CC-BY-NC-SA-4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

DriftOps used the slide-rail and industrial-valve recordings in separate studies.
Preparation converts the first microphone's 16 kHz recordings into two spectral-energy bands and 28-frame numerical windows.
It adds numerical pattern targets and assigns separate machines to training, validation, and test.
Shared prepared audio features retain the source attribution and CC-BY-NC-SA-4.0 license.
Acquisition dates are unverified. Clip offsets are not calendar timestamps.

The dataset providers request these citations:

- Yuma Koizumi and colleagues. [ToyADMOS: A Dataset of Miniature-Machine Operating Sounds for Anomalous Sound Detection](https://ieeexplore.ieee.org/document/8937164), WASPAA, 2019.
- Harsh Purohit and colleagues. [MIMII Dataset: Sound Dataset for Malfunctioning Industrial Machine Investigation and Inspection](https://dcase.community/documents/workshop2019/proceedings/DCASE2019Workshop_Purohit_21.pdf), DCASE, 2019.
- Yuma Koizumi and colleagues. [Description and Discussion on DCASE2020 Challenge Task2: Unsupervised Anomalous Sound Detection for Machine Condition Monitoring](https://arxiv.org/abs/2006.05822), 2020.

## OpenTSLM citation

Patrick Langer and colleagues. [OpenTSLM: Time-Series Language Models for Reasoning over Multivariate Medical Text- and Time-Series Data](https://arxiv.org/abs/2510.02410), 2025.
The [upstream contributors](OpenTSLM-CONTRIBUTORS.md) and [MIT notice](OpenTSLM-MIT.txt) accompany the model release.
