# Model licenses and release notices

The selected DriftOps checkpoints contain Gemma-derived tensors. The Gemma terms apply to every checkpoint, including private release copies.
The upstream OpenTSLM MIT license also applies to the OpenTSLM material. It does not replace the Gemma terms.
The [model artifact terms](licenses/MODEL-TERMS.txt) incorporate the required use restrictions.

The selected binary files remain unchanged. Their original SHA-256 checksums identify the evaluated models.
The [modification notice](licenses/best.pt.NOTICE) accompanies each `best.pt` file.
Each package must also identify its run and selected checkpoint checksum.

## Model dependencies

| Material | Pinned reference | Terms and attribution |
|---|---|---|
| Gemma base | `google/gemma-3-270m`, revision `9b0cfec892e2bc2afd938c98eabe4e4a7b1e0ca1` | [Gemma terms](https://ai.google.dev/gemma/terms), [local agreement](licenses/gemma-terms.html), [required Notice](licenses/Notice) |
| OpenTSLM temporal checkpoint | `OpenTSLM/gemma-3-270m-tsqa-sp`, revision `c97bd36131e07d53a7af9cd307eb3db628f9712f` | The [model card](https://huggingface.co/OpenTSLM/gemma-3-270m-tsqa-sp) identifies MIT. Retain the [MIT notice](licenses/OpenTSLM-MIT.txt). |
| OpenTSLM implementation | Revision `2968f4b891baab4307f7e9d0043e87677b593a30` | [Pinned upstream license](https://github.com/OpenTSLM/OpenTSLM/blob/2968f4b891baab4307f7e9d0043e87677b593a30/LICENSE.md) and [contributors](licenses/OpenTSLM-CONTRIBUTORS.md) |

The saved Gemma agreement was last modified on April 1, 2026.
Its appendix includes Gemma 3. The incorporated prohibited-use policy was last modified on February 21, 2024.
The [source receipt](licenses/sources.json) records download dates, URLs, transformations, sizes, and checksums.
The HTML copies contain the official agreement articles without paraphrase. The wrapper omits website navigation.

Gemma redistribution requires the agreement, use restrictions, a modification notice, and the prescribed Notice.
The accompanying [policy copy](licenses/gemma-prohibited-use-policy.html) preserves the incorporated restrictions.
Read Section 3 of the agreement before further distribution.

## Dataset license matrix

This matrix records the training sources. Dataset licenses remain distinct from model and source-code licenses.
The [dataset attribution](licenses/DATASET-ATTRIBUTION.md) gives author credits, source versions, and preparation changes.
Each run's dataset manifest provides the exact source hashes and split configuration.

| Model or study | Dataset source | Dataset license | Release limit |
|---|---|---|---|
| HDD and SSD | [Backblaze Drive Stats](https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data) | Backblaze source terms | Credit Backblaze. The data itself must not be sold. Backblaze permits sale of derivative works. |
| NVMe | [Ceph device telemetry](https://ceph.io/en/users/telemetry/device-telemetry/) | [CDLA-Sharing-1.0](https://cdla.dev/sharing-1-0/) | Preserve source attribution. Redistributed data and enhanced data retain CDLA-Sharing-1.0. |
| DRAM | [SmartMem, record 15516113](https://zenodo.org/records/15516113) | [CC-BY-NC-4.0](https://creativecommons.org/licenses/by-nc/4.0/) | Noncommercial source data. The checkpoint is released for noncommercial research and evaluation only. |
| CPU, GPU, server power | [OLCF Summit / ClusterWise, pinned revision](https://huggingface.co/datasets/MachaParfait/ClusterWise/tree/93fb62c369fcfb36536252a9bb4a539dcdb2b229) | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Preserve attribution and identify data preparation changes. |
| Fan | [M100 ExaData, record 7541722](https://zenodo.org/records/7541722) | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Preserve attribution and identify data preparation changes. |
| Gearbox, generator bearing, gear-oil pump | [Kelmarsh 8252025](https://zenodo.org/records/8252025) and [Penmanshiel 8253010](https://zenodo.org/records/8253010) | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Credit Charlie Plumley and Cubico Sustainable Investments. Identify data preparation changes. |
| Dated radiator-valve study and follow-up | [HOMESENSE, record 21687970](https://zenodo.org/records/21687970) | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Preserve attribution. Both studies failed their declared model checks. |
| Slide-rail sound and industrial-valve sound | DCASE 2020 Task 2 [development 3678171](https://zenodo.org/records/3678171) and [additional training 3727685](https://zenodo.org/records/3727685) | [CC-BY-NC-SA-4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) | Noncommercial source data. Shared adapted data retains the source license. The checkpoints are released for noncommercial research and evaluation only. |

The noncommercial checkpoint limit is an explicit condition of this release.
It does not claim that every dataset license automatically becomes the license for trained weights.
Commercial clearance for the DRAM and sound checkpoints has not been established.
The other rows are not a certification of suitability for a commercial deployment.

Ceph's agreement distinguishes data from computational results. Section 3.5 does not restrict publication of results as defined in that agreement.
This distinction does not remove the source license from redistributed telemetry windows.
Private repository access does not revoke recipients' rights under the dataset licenses.

Audio acquisition dates remain unverified. The sound benchmarks use separate machines and have no calibration partition.
The source license does not validate calendar generalization or fault-detection claims.

## Files in each model asset

Keep the following paths in every model archive. Place the two model notices beside `best.pt`.

```text
artifacts/tslm/<run>/best.pt
artifacts/tslm/<run>/best.pt.NOTICE      # copy of docs/licenses/best.pt.NOTICE
artifacts/tslm/<run>/Notice              # copy of docs/licenses/Notice
artifacts/tslm/<run>/selection.json      # original selected checksum and epoch
artifacts/tslm/<run>/config.json
artifacts/tslm/<run>/overview.json
artifacts/tslm/<run>/dataset-manifest.json
artifacts/tslm/<run>/training-result.json
docs/model-licenses.md
docs/licenses/MODEL-TERMS.txt
docs/licenses/gemma-terms.html
docs/licenses/gemma-prohibited-use-policy.html
docs/licenses/Notice
docs/licenses/best.pt.NOTICE
docs/licenses/OpenTSLM-MIT.txt
docs/licenses/OpenTSLM-CONTRIBUTORS.md
docs/licenses/DATASET-ATTRIBUTION.md
docs/licenses/sources.json
```

The archive manifest must name the run and verify `best.pt` against `selection.json`.
Do not modify the model binary to add license text. Retain the separate, prominent modification notice.
Include this attribution set with evaluation archives that redistribute prepared dataset windows.
The dataset links provide their license texts. Full dataset license copies are not required by this packaging plan.
