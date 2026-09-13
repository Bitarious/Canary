# Separate component model results

All thirteen component categories now have a separate model that passed its declared held-out checks. Every selected checkpoint and evaluation export is verified. The dated radiator-valve model failed both its original test and unchanged-weight follow-up. A separate industrial-valve sound model passed under the documented unknown-chronology exception. All results describe agreement with observed-signal rules. They do not establish failure prediction, physical root cause, or maintenance benefit.

Each component has separate weights. Every model starts from the pinned Gemma-based OpenTSLM checkpoint. Fine-tuning updates its temporal encoder, projector, and attention LoRA. Original Gemma parameters remain frozen. Dated datasets use separate device groups and ordered dates. Calibration data remains unused. Slide rail and industrial-valve sound use the explicit unknown-date exception in their [slide-rail](slider-study-design.md) and [valve](valve-audio-study-design.md) designs. Both have separate training, validation, and test machines and no calibration fit.

| Model | Held-out groups | Channel accuracy | Constant accuracy | Zero-input accuracy | Macro F1 | Frozen gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| HDD | 2,048 | 99.68% | 69.43% | 86.01% | 0.9912 | Passed |
| SSD | 159 | 95.91% | 0.31% | 24.53% | 0.9512 | Passed |
| NVMe | 256 | 97.75% | 47.66% | 57.42% | 0.9443 | Passed |
| DRAM | 256 | 94.14% | 33.59% | 78.12% | 0.9195 | Passed |
| CPU | 256 | 81.45% | 0.00% | 63.48% | 0.7597 | Passed |
| Server power | 256 | 83.01% | 0.00% | 48.24% | 0.8344 | Passed |
| Gearbox | 5 | 86.91% | 0.00% | 36.76% | 0.8716 | Passed |
| Generator bearing | 5 | 93.20% | 0.00% | 36.21% | 0.9331 | Passed |
| Gear-oil pump | 5 | 82.11% | 0.00% | 27.15% | 0.8113 | Passed |
| GPU | 256 | 92.32% | 7.42% | 80.08% | 0.9047 | Passed |
| Fan | 116 | 95.69% | 9.05% | 49.14% | 0.9651 | Passed |
| Slide rail sound | 5 | 83.22% | 0.00% | 35.60% | 0.8324 | Passed |
| Industrial valve sound | 5 | 77.08% | 0.00% | 49.34% | 0.7579 | Passed |
| Radiator valve | 5 | 95.10% | 64.51% | 93.36% | 0.8134 | Failed support |

The thirteen passing models satisfy every frozen check, including baseline gains, numerical dependence, reversal, shuffle, and sixteen exact GPU reload predictions. The dated industrial tests contain 1,280 windows but only five independent groups per model. Each sound test contains 5,120 windows across five machines. Their pass applies to the limited study, not fleet reliability. Server results describe power-supply inputs. Pump results describe gearbox oil pressure. Bearing results describe generator bearing temperatures.

The starting model's low strict score includes its difficulty with the required answer format. The deterministic rules score 100% because they generated the targets. Constant answers are weak baselines when the test contains few or no constant labels. The zero-input comparisons provide a separate numerical-dependence check. Missing DRAM error logs do not establish healthy operation. A test that lacks a pattern cannot establish performance for that pattern.

## Valve follow-up

The original valve model achieved 95.10% channel accuracy. Its baseline and numerical gains passed. Household H09 supplied only fourteen changed targets under each order test, below the required thirty-two. The original frozen gate remains failed.

The separate `valve-industrial-followup-v1` run preserves the selected epoch-six weights. Its protocol includes all 12,335 previously unused test windows and excludes all 1,280 original windows. The five households and quality thresholds remain fixed. This design follows the observed support failure. It is not an independent replication or the original predeclared test. No further fitting is allowed on either released run.

The follow-up also failed. Channel accuracy was 94.06%, compared with 91.60% for zeroed numerical inputs. H09 performed slightly better with zeroed inputs, by 0.258 percentage points. The exact paired-group sign probability was 0.0625, above the fixed 0.05 maximum. Both order-response checks passed with sufficient support in every group. All 4,641 exported JSON and checkpoint files passed hash verification.

The [industrial-valve sound design](valve-audio-study-design.md) uses separate MIMII recordings and fresh upstream weights. Training completed six epochs in 334.6 seconds and stopped for validation patience. Epoch three was selected before test release. All seven frozen checks passed on 5,120 windows from 3,204 recordings across five machines. Channel accuracy was 77.08%, macro F1 was 0.7579, and valid output rate was 100%. Zero-input accuracy was 49.34%. All 1,626 exported JSON and checkpoint files passed hash checks. GPU and CPU reload each reproduced sixteen saved answers. This sound result does not convert the failed radiator-valve telemetry result into a pass.

## Local CPU checks

Local CPU inference exactly reproduced sixteen saved GPU answers for HDD, SSD, NVMe, DRAM, fan, gearbox, bearing, pump, slide rail, and industrial-valve sound. CPU-component, GPU-component, server, and both dated valve checks each reproduced fifteen of sixteen answers. Their same-GPU reload checks reproduced all sixteen. Do not claim identical predictions across CPU and GPU for those four component categories. Cross-hardware floating-point behavior is a possible cause, not yet a verified diagnosis.

These checks removed targets and audit metadata before generation. No weights changed. Receipts, the actual differing answers, and the check script are in `artifacts/component-audit/v1/cpu-export-check-v1/`.

## Exported checkpoints

The machine-readable `artifacts/component-audit/v1/model-catalog.json` records selected checkpoint hashes, dataset pins, split counts, metrics, gate outcomes, and CPU reload counts. The catalog records fifteen evaluated runs and fourteen distinct selected checkpoints. Thirteen component categories pass. Both dated valve failures remain included.

All paths are relative to the repository root. The local run directories contain selected and terminal checkpoints, source hashes, configuration, advance overviews, selection records, test protocols, raw predictions, metrics, and export receipts. Large data and model artifacts remain in the ignored local `data/` and `artifacts/` directories. No commit, push, or remote publication has occurred.

| Model | Run directory | Selected epoch | Selected checkpoint SHA-256 |
| --- | --- | ---: | --- |
| HDD | `artifacts/tslm/full-history-rtx6000-v2` | 1 | `d941fc219865ee6cc54c62f5498f8ae180710d44c83ade1c3b145bdc57297b99` |
| SSD | `artifacts/tslm/ssd-component-v1` | 12 | `1b7fb29ef858887f63d634654a34f376f3c3ff3ed7d78593e380497f92bb5da9` |
| NVMe | `artifacts/tslm/nvme-component-v2` | 11 | `46277da8fd6fefd98d8b4a1438e4b3c4bcf5ae1bea3a62348e5e6f1a36a2303c` |
| DRAM | `artifacts/tslm/dram-component-v1` | 7 | `757ba0d7fd1af4c5e8536bed9dec48eabb205a69655be8da8faf5d649f95ed38` |
| CPU | `artifacts/tslm/cpu-component-v1` | 3 | `c1bee7c69a649ae9a8223507cdffb07dc1660e9753f6cb0aadc96c3e20a0b906` |
| Server power | `artifacts/tslm/server-component-v1` | 11 | `54b5ea4d851460a08db9a26d7cfea5e8fc45d4dd8a056beeda3ac8b9eb6d307c` |
| Gearbox | `artifacts/tslm/gearbox-industrial-v1` | 10 | `8c13d4c8f3a2d215f668d17245b2b271a2dacfee6625a516684cbef049c0e690` |
| Generator bearing | `artifacts/tslm/bearing-industrial-v1` | 11 | `cac986d97d10bb614f498e7ab25ab5103d01ac9d45e0b442152b0d4d9f873713` |
| Gear-oil pump | `artifacts/tslm/pump-industrial-v1` | 11 | `a0c12c278dd8e2440b9c7c6b749d590341cd077edc2b076f6a5ea479b2a0de65` |
| GPU | `artifacts/tslm/gpu-component-v1` | 4 | `eb42be2226a032ed5002dd2063309019f36b0850db16c69a005d161133a4c9fe` |
| Fan | `artifacts/tslm/fan-component-v1` | 7 | `7c7836b360833188d3c60c9a15d9f97890901bc677beccf0c9b80a1a02126a85` |
| Slide rail sound | `artifacts/tslm/slider-audio-v1` | 12 | `14e02c10385dc92b21e5be2c2189b8d9f8a016792f441cedcf09bd2ef10c3393` |
| Industrial valve sound | `artifacts/tslm/valve-audio-v1` | 3 | `49c0a0d01ff9f7d4c2bee6678e2cabf63ed1abd651933fd2abbe1a25bc891bfb` |
| Radiator valve | `artifacts/tslm/valve-industrial-v1` | 6 | `832849aa9e65ee86d6671ccf248a2b66f3fbe71de49b21de6f6a43e0a60a0e5e` |

Load `best.pt` with `driftops.opentslm.load_model`. It requires this repository's pinned model code and the cached Gemma base. The CPU example below performs inference on sixteen already released test inputs. It removes targets and audit metadata before generation. It does not fit weights or provision compute.

```python
import json
from pathlib import Path
import torch
from driftops.full_archive import file_hash
from driftops.opentslm import load_model, generate

run = Path("artifacts/tslm/ssd-component-v1")
selection = json.loads((run / "selection.json").read_text())
assert file_hash(run / "best.pt") == selection["sha256"]
examples = json.loads((run / "evaluation/test.json").read_text())[:16]
inputs = [{"inputs": item["inputs"]} for item in examples]
torch.set_num_threads(8)
model = load_model("cpu", checkpoint=run / "best.pt")
answers = generate(model, inputs, max_new_tokens=128)
print(answers)
```

Read [the component program](component-training-program.md) for data reproduction and training procedures. Read [the dataset audit](component-dataset-audit.md) for source terms, channels, chronology, and rejected alternatives. The [full-history report](full-history-training.md) records the complete HDD run and provider stops. Later industrial results must retain the five-group scope in [their frozen study design](industrial-study-design.md).

## Compute status

The September 13, 07:29 UTC ledger estimates $111.35 spent, leaving $488.65 under the $600 ceiling. It includes setup, failed capacity requests, training, evaluation, and owned disk storage. This is a conservative estimate, not a voucher balance or invoice.

Controller CLI authentication is restored. All three owned VMs are stopped, with no open compute interval. The last RTX stop completed at 07:28:48.868937 UTC through successful operation `computeoperation-e05y3x9vpgfwz78qjc`. The final valve phase stayed below its $28.90 cap. Its completion evidence is in `artifacts/nebius/full-history-v1/valve-audio-phase-v1/completion.json`.

Three cloud disks remain retained. Their combined quoted storage rate is about $0.03734 per hour. No GPU compute is running. The checkpoints and full verified evaluation exports are also stored locally.

All 93 tests passed in the working tree and in a fresh locked checkout. The fresh checkout rebuilt the native pilot. Entire remains enabled with its hooks and approval records present. Doctor flags the existing session's exited process, so complete session capture is not claimed. The warning and preserved history are documented in the handoff. Working tree changes remain uncommitted and unpushed.
