# DriftOps implementation plan

**Execution:** Codex performs the work alone, with no team split or sub-agents. Start each step as soon as its prerequisites are satisfied. There are no fixed implementation slots or per-step durations. Downloads and training processes may run while Codex continues independent work.

**Status, 12 September 2026:** the dependency order below remains the implementation plan. A real Backblaze pilot cohort is bundled and converted by the implemented TimeNet connector: 3,000 drives of one model over July–December 2024, 547,812 source rows, and 13,616 signal-description tasks. A local browser preview displays actual development windows and deterministic descriptions; the complete operator application remains unfinished. The 3,000-drive cap is a local pipeline pilot, not the size of Backblaze's archive. See [data preparation](data-preparation.md) and the [Linux handoff](handoff.md). Nebius access and GPU quota are verified. Hugging Face is connected; Gemma 3 270M and its matching OpenTSLM-SP checkpoint are selected, with both weight endpoints accessible. Llama review remains pending independently. Model loading, remaining credit balance, and GPU capacity are unverified. No trained baseline, fine-tuned TSLM, or model evaluation exists yet; no paid compute has started.

The [architecture](architecture.md) defines analytical contracts and safeguards. This plan defines the required submission and the prerequisites for building it.

**Dataset scope confirmed:** the first working demo uses Backblaze HDD data only, starting with one supported model. Additional HDD sources, SSD/NVMe, RAM, GPUs, servers, and industrial hardware remain in the [future dataset backlog](dataset-backlog.md).

**Session evidence:** the user requires Entire for submission eligibility. Preserve its recording, trusted agent hooks, and checkpoint push workflow on both machines. Never bypass these to make a commit, push, or unattended run proceed. Development runs on the user's Linux Ryzen AI Max+ 395 server with 128 GB unified RAM; Nebius is the intended training compute.

**Compute and communication:** the user corrected the team's voucher to **$600**. Use this as the maximum available budget, subject to the console's actual remaining balance. Additional credits can be requested if needed, but are not available or authorized by default. Before every model-training run, including baseline fitting and tiny training diagnostics, give the user an overview of the data/splits, learning objective, parameters to update/freeze, why the run is necessary, hardware, expected cost, stopping conditions, evaluation, and saved outputs. This is a requirement to explain the run in advance; it does not itself add a separate approval step.

## Host requirements

Reviewed the supplied `Aionic_Temporal_AI_Hackathon.pdf`, especially PDF pages 14, 16, 17, 19, and 22, alongside the host introduction. Page references count from the first PDF page, rather than using the slides' printed numbers. The source is at `C:\Users\mariu\Downloads\Aionic_Temporal_AI_Hackathon.pdf` on this machine.

| Host requirement | DriftOps implementation | Evidence to retain |
|---|---|---|
| Problem + open data | Help a storage operator inspect degrading drives and choose a maintenance window using real Backblaze SMART histories | User, decision, provenance, cohort and endpoint definition |
| Connect using TimeNet | Use or build a reusable connector for signals, metadata, annotations, and learning targets | Connector, dataset card, TimeF version, successful read-back |
| Train or fine-tune a TSLM | Adapt OpenTSLM to describe relevant changes in real SMART windows | Training config, logs, checkpoint or learned adapter, reload verification |
| Evaluate against a baseline | Compare trained OpenTSLM with its starting checkpoint and a deterministic interpretation baseline on held-out windows; evaluate risk separately | Predictions, metrics, split manifest, sample counts, failures and limitations |
| Demonstrate usefulness | Real replay, model findings, measured evidence, maintenance draft, and explicit outcome reveal | Working demo and reproducible case bundle |
| Submit artifacts | Demo, code + training config, checkpoint or adapter, dataset documentation, short evaluation | Completed submission checklist below |

The PDF permits generated text annotations (page 16). Backblaze needs that layer because it does not provide maintenance narratives. Reusable connectors and automated dataset assessment are bonus opportunities after the required path works. The hosts describe OpenTSLM as a reference; we retain it as DriftOps' selected TSLM under the existing project decision.

TimeNet prepares and loads data; it does not train or serve models. OpenTSLM supplies the native numerical-series model path. **Actual TSLM training and a reloadable learned artifact are required.** An API wrapper named `OpenTSLMAdapter` is integration code, not the trained adapter requested for submission. [TimeNet scope](https://docs.timenet.ai/), [OpenTSLM paper](https://arxiv.org/abs/2510.02410).

## Required scope

One locally runnable operator journey:

1. Open a fleet ordered by concern and supplied operational context.
2. Inspect a drive's health history, actual SMART changes, and same-model peers where supported.
3. Advance through a real held-out history with inputs restricted to the current cutoff.
4. Ask the fine-tuned OpenTSLM to interpret numerical sequences and compare its findings with measured evidence.
5. Compare supported maintenance options and save a local draft with explicit assumptions.
6. Reveal the historical outcome and present TSLM evaluation alongside the separate warning/risk results.

| Required | Conditional on evidence and completed prerequisites | Deferred |
|---|---|---|
| Real histories, controls, provenance, dataset documentation | Calibrated seven-day event probability | Precise remaining-life intervals |
| TimeNet connector, valid TimeF output, training loader | Validated daily hazard curve | SMD/server anomaly implementation |
| Signal-text examples with annotation provenance | Outcome-prediction task added to the TSLM | Historical nearest-neighbor retrieval |
| OpenTSLM fine-tuning, config, reloadable learned artifact | Additional replay cases and cost sensitivity | Rack root-cause and cross-company transfer claims |
| Held-out TSLM comparisons against baselines | Automated dataset discovery/assessment beyond the connector | Large-scale pretraining or full-parameter training |
| SMART rule, drift/evidence, temporal risk baseline where labels support fitting | Hosted deployment and upstream connector contribution | Production scheduling and autonomous actions |
| Isolated replay, maintenance draft, verified UI journey | Small illustrative rack navigation | General telemetry platform infrastructure |

If calibrated risk lacks support, show a labeled score or drift index and leave probability fields unavailable. This does not waive TimeNet preparation, TSLM training, or held-out evaluation. Missing real data or a learned TSLM artifact leaves the submission incomplete.

## Work order and readiness checks

The order expresses dependencies. Begin any ready task; there is no reserved later slot for model access or training. While a download or GPU run is active, continue independent API, UI, documentation, or verification work.

| Step | Start when | Work | Complete when |
|---|---|---|---|
| 1. Freeze task and check resources | Now | Define user/task; inspect data, compatible runtimes, TimeNet revision, weight access, Nebius voucher/quota and candidate GPU | Task/config drafts, acquisition route, separate data/model/compute dependency states |
| 2. Prepare data through TimeNet | Source format and a real sample are available | Audit SMART semantics; use/build connector; preserve metadata and annotations; write/read TimeF | Real histories round-trip with provenance, quality counts, and dataset card |
| 3. Freeze splits and language targets | Cohort coverage is known | Assign drive/date partitions; build causal windows; generate/audit signal-text targets; implement OpenTSLM training bridge | Input-only batches, separate targets, split manifest, leakage checks pass |
| 4. Establish baselines | Development partitions and task rubric are frozen | Implement rule descriptions, pretrained OpenTSLM inference, SMART alerts, features, and supported XGBoost baseline | Versioned baseline artifacts and validation results; test untouched |
| 5. Train OpenTSLM | Batches, weights, compute, and baseline smoke run are ready | Check gradients and tiny training run; fine-tune; select on validation; export learned artifact | Weights reload in a fresh process and generate from real numerical windows |
| 6. Build snapshot API and replay | Cutoff-scoped records and contracts are available | Implement snapshots, evidence, policy, isolated reveal, bounded history | Fleet/detail/replay agree on cutoff and versions; future-data checks pass |
| 7. Build operator journey | Snapshot contract is stable | Build fleet, detail, charts, evidence, replay, maintenance options, local draft | Complete journey with explicit capability states |
| 8. Connect trained model | Training artifact reload passes | Serve that artifact, validate findings, record attribution, cache actual inference if needed | Demo responses trace to submitted weights and exact inputs |
| 9. Evaluate and verify | Models, transforms, prompts, parsers, thresholds are frozen | Held-out comparisons, temporal tests, browser flow, failure cases, artifact checks | Metrics with denominators, saved predictions, limitations, passing workflow checks |
| 10. Package and rehearse | Required artifacts and verification are complete | Write tested launch/train/eval commands, cards, artifact manifest, jury walkthrough | Every submission item is present and reproducible |

Record concrete missing dependencies and continue ready work. Labeled synthetic fixtures can support pipeline/API/UI development, but cannot supply training evidence, real evaluation, or the historical outcome payoff.

## Data and TimeNet connector

Start with one well-supported Backblaze hardware model and a short metric allowlist. Prefer a traceable extract with complete histories and normal controls; otherwise acquire a bounded official archive selection. Choose the cohort using development data, independently of future test outcomes, and retain enough history/follow-up for the splits. Record source URLs, checksums, schema changes, inclusion rules, missingness, duplicates, usage terms, and the recorded failure/removal definition.

The existing 3,000-drive, six-month extract proves pipeline operation and supplies initial signal-language examples. Backblaze publishes a much larger archive beginning in 2013, with Q1 2026 downloadable on the reviewed source page. Before substantive failure-prediction fitting/evaluation, audit usable events and follow-up separately in each development partition and expand the same-model drive/date coverage if support is inadequate. There are only 33 recorded failure flags in the complete pilot; that does not establish enough independent events for calibrated risk. Preserve normal controls, record the expanded inclusion rule, and freeze a new dataset/split version before fitting. Broadening to all years and models requires an additional SMART/schema audit; it is not necessary for the first signal-language integration check.

Check the TimeNet catalog and pinned connector source before implementing a new connector. The reviewed catalog does not list Backblaze, so plan a Backblaze connector unless a suitable implementation is available when building. TimeNet is evolving: pin tested SDK/producer revisions rather than mixing examples from different versions. [TimeNet catalog](https://docs.timenet.ai/catalog/datasets.html), [repository](https://github.com/OpenTSLM/TimeNet).

The documented producer contract separates cached acquisition in `download(cache_dir)` from offline conversion in `convert(raw_refs)` into `TimeFDataset`. Use the SDK writer/reader to create and reload TimeF and provide a dataset card; custom Parquet alone does not prove TimeNet integration. Keep source settings configurable and package offline conversion checks with a small fixture. A local build suffices; public registry publication is optional. [Connector contract](https://docs.timenet.ai/connectors.html).

| Source concept | Logical mapping, implemented against the pinned version |
|---|---|
| Drive history | Stable source/serial group and model metadata; identifiers retained for splitting, excluded from prompts/features |
| SMART channel | Numerical series with source name, verified semantics/unit where available, daily calendar alignment, missingness, transform provenance |
| Observation date | Actual date and documented availability convention; missing dates remain visible |
| Failure/removal flag | Outcome annotation for label construction/evaluation, excluded from inference inputs |
| Window | Input clipped at `as_of`, with lookback, coverage, source-row references, split membership |
| Language target | Question/answer about the observed window, annotation method/version, supporting signal interval |
| Optional seven-day target | Separate classification target; unknown when follow-up is inadequate |

TimeNet distinguishes text-answer/classification targets and annotations supplied as context versus targets. Preserve this separation in the training bridge. Never serialize a whole labeled record into a model prompt or public replay response. [TimeNet tasks](https://docs.timenet.ai/data-model/tasks.html).

Round-trip checks preserve values, channel order, time axes, metadata, annotations, and tasks. The model loader separately proves it materializes only the allowed numerical window and neutral metadata. Future outcomes may exist in offline target storage without becoming model inputs.

## Language task and annotation design

**Required TSLM task:** given a short multivariate SMART history and neutral question, identify relevant changing channels and describe their direction/pattern and observed interval. This helps an operator review why a drive deserves attention. It does not establish physical root cause, remaining lifetime, or maintenance effects.

Begin with two to four verified channels and complete daily windows, using the architecture's provisional 28-observation input only if compatible with the checkpoint. Freeze eligibility, gap/reset handling, scaling, output vocabulary, and interval rubric. Match training and inference preprocessing. Include constant channels, normal controls, and ambiguous patterns; do not label every pre-failure window as degraded.

Backblaze has no prose explanations. Generate concise descriptions from auditable, cutoff-scoped measurements and fixed trend/change rules; mark them as derived or weak supervision. If an LLM rewrites them, retain the evidence, generator/model/prompt revision, and validation result, discarding unsupported additions. The generator must not receive future observations, failure dates, test labels, or post-event knowledge. Do not invent technician notes or maintenance-effect labels.

Freeze annotation rules on development data and inspect a diverse sample for direction, channel, interval, and reset errors. Reserve a separately reviewed held-out subset for a fixed faithfulness rubric. Agreement with rule-generated targets measures rule agreement, not independent expert reasoning. Record the reviewer/method and subset size.

**Conditional extension:** add a seven-day recorded-event question only if development-period event/control counts support it; freeze that decision before test evaluation. Use the architecture's censored `y7` label exclusively on the target side. A generated class is not a calibrated probability. Signal interpretation remains the required task if failure prediction is unsupported.

Split drive identities and ordered periods before fitting or generating learned annotations. Fit transforms/peer references on training data, purge target horizons across boundaries, and separate tuning, calibration, and test. Keep related windows and question variants within their drive's partition. Held-out targets belong only to evaluation.

## OpenTSLM training and Nebius readiness

Use `google/gemma-3-270m` with `OpenTSLM/gemma-3-270m-tsqa-sp`, pinned in [model.yaml](../config/model.yaml). Both weight endpoints are accessible through the connected account; model loading and storage-task performance are still unverified. The earlier Llama candidate remains an optional alternative pending access. Check licenses, revisions, batch schema, and actual trainable modules. Begin with the supported SP configuration: freeze the base language model and adapt the numerical encoder/projector, subject to the runtime parameter audit. An inference endpoint alone cannot satisfy training. [Official OpenTSLM setup](https://github.com/OpenTSLM/OpenTSLM), [model readiness](model-setup.md).

Build a small TimeNet-to-OpenTSLM dataset/collator bridge: numerical channels through `time_series`, channel descriptions and neutral questions through text, answers only as training targets. Match patching, normalization, and padding. Verify prompt/padding loss masking and gradients in the intended temporal adaptation parameters. The upstream dataset and batch helpers are references, not a ready-made TimeNet integration. [TSQA dataset](https://raw.githubusercontent.com/OpenTSLM/OpenTSLM/main/src/opentslm/time_series_datasets/TSQADataset.py), [batch helpers](https://raw.githubusercontent.com/OpenTSLM/OpenTSLM/main/src/opentslm/time_series_datasets/util.py).

Prefer a small adaptation using supported temporal encoder/projector or other adapter modules, freezing the base language model where practical. Verify which parameters update; do not assume arbitrary LoRA attachment works. First complete a forward/backward step and tiny-batch overfit diagnostic. Then run the declared training configuration, select on validation, and export all learned components needed for reload. The overfit diagnostic is not final evaluation.

Record dataset/split/annotation versions, checkpoint revisions, trainable/frozen modules, preprocessing, prompts, seed, optimizer, learning rate, effective batch size, precision, steps/epochs, validation cadence, selection rule, and stopping criteria. Training-step counts are reproducibility settings, not implementation deadlines. Save losses, validation metrics, hardware, peak VRAM, runtime, cost, and artifact hashes.

The host PDF announces a $1,000 voucher (page 19), but the user confirmed the team's actual voucher is **$600**; the team's amount controls this plan. CLI access and tenant GPU quotas are verified, while actual remaining balance, instance availability, and training readiness need checking. Select hardware from a memory smoke test, explain each proposed training run before starting it, and set its spend limit within the remaining $600 budget with an evaluation/reload reserve. Record actual rates and consumption; stop idle compute after exporting artifacts. Seek additional credits only after discussing the need with the user.

Use Nebius for training when ready. The local 6 GB GPU is a possible inference/smoke-test resource with unverified fit. Prepare compatible runtimes and lockfiles during setup. A missing partner endpoint need not block self-hosted work when weights and compute are available. Missing weights or compute leave training pending while independent data, UI, contracts, and CPU baselines proceed.

## Baselines and held-out evaluation

Evaluate the **trained TSLM itself**, alongside the separate risk model:

| Comparison | Shared task/input | Report |
|---|---|---|
| Starting vs fine-tuned OpenTSLM | Identical numerical windows, neutral prompts, parser, interpretation rubric | Direction/pattern macro-F1, channel precision/recall, interval correctness under fixed rubric, valid-output rate, unsupported claims, latency, counts |
| Deterministic descriptions vs fine-tuned OpenTSLM | Same observed histories and interpretation task | Same applicable metrics; disclose overlap between rule-based targets and baseline |
| Numerical-input ablation | Hold neutral text fixed; reorder or remove/mismatch series under a predeclared probe | Temporal-input dependence and failures; integration evidence, not prediction accuracy |
| SMART rule vs temporal XGBoost where fitting is supported | Same partitions, seven-day labels, eligibility, alert policy | Average precision, event recall, false-alert episodes per 1,000 eligible drive-days, lead times, coverage; Brier score only for supported probabilities |
| Optional TSLM event task vs outcome baselines | Same known-outcome windows and target | Class precision/recall/F1; ranking metrics only with a reproducible class score |

Freeze prompts, annotation rules, parsers, selection, and thresholds before test. Report denominators, distinct drives, class support, invalid outputs, and censoring exclusions. Do not discard invalid answers to improve results. Report the separately reviewed faithfulness subset alongside automated scores.

Keep test histories representative of the eligible cohort. Estimate uncertainty by resampling drives, not correlated daily rows. Changes motivated by test results need a new untouched holdout for a fresh generalization claim. Report lack of improvement honestly. Selected replay cases and synthetic modality probes do not replace held-out comparison.

## Serving, replay, and maintenance

Load the **submitted fine-tuned artifact** for the final demo. Record checkpoint hash, cutoff, input hash, raw output, parsed finding, validation, and latency. Validate channel references and numerical claims against server-owned evidence. Preserve disagreements rather than silently correcting and attributing them to OpenTSLM.

If caching is needed, precompute actual outputs from that artifact and label them cached. Cache keys cover dataset, sequence, cutoff, model, preprocessing, prompt, question, and context versions. New questions need inference or an unavailable response. Starting-checkpoint outputs may appear as a baseline, not as the trained submission model.

Use one immutable snapshot across fleet/detail/replay. Hide outcomes from ordinary API responses, client assets, serving exports, and copilot inputs. Rewinding invalidates later explanations and revealed outcomes. Topology, workload, redundancy, and cost context remain explicitly supplied or illustrative.

Show only validated probability horizons. A seven-day classifier cannot supply other durations' percentages; score-only mode compares timing qualitatively using evidence and assumptions. Daily telemetry supports a next feasible daily window, not learned hourly risks. Add a hazard curve only after the required journey works and held-out cumulative-risk checks justify it.

Saving creates a local maintenance draft with window, evidence, action, and assumptions. Costs and maintenance effects remain illustrative unless separately measured.

## Proposed repository layout

```text
README.md
docs/
  architecture.md
  implementation-plan.md
  nebius-setup.md
  dataset-card.md
  model-card.md
  evaluation.md
  demo-script.md
connectors/backblaze/           # register using the pinned producer's discovery mechanism
  connector.py
  dataset.yaml
  requirements.txt
apps/web/
services/api/
  main.py
  contracts.py
  snapshot_service.py
  opentslm_adapter.py           # serving wrapper, not a learned adapter
  maintenance.py
src/driftops/
  timenet_build.py
  windows.py
  annotations.py
  tslm_dataset.py
  train_tslm.py
  features.py
  labels.py
  train_baseline.py
  evaluate.py
  replay.py
config/
  dataset.yaml
  splits.yaml
  train_tslm.yaml
  train_baseline.yaml
  evaluation.yaml
  policy.yaml
  replay_cases.yaml
data/                          # excluded from version control
  timef/
  processed/
  outcomes/                    # evaluator/reveal only
artifacts/                     # excluded from Git; exported for submission
  tslm/                        # learned weights + manifest
  baselines/
  snapshots/
  opentslm_responses/
  evaluation/
  training_logs/
tests/
  fixtures/
  test_timenet_connector.py
  test_tslm_data_boundary.py
  test_temporal_integrity.py
  test_risk_and_policy.py
  test_replay_boundary.py
  test_opentslm_adapter.py
```

This is a target layout. Keep the application small; no event broker, vector database, Kubernetes, or general feature store is required.

## Acceptance checks

| Check | Passing behavior |
|---|---|
| TimeNet integration | Rebuild and SDK read-back preserve real values, axes, metadata, annotations, and tasks |
| Training boundary | Targets, failure flags, future records, and target-derived text absent from inference input; training targets separate |
| Actual training | Logs and changed weights prove optimization; exported artifact reloads and generates in a fresh process |
| Split isolation | Drive/time partitions match manifest; related windows stay together; target horizons purged |
| Future mutation | Post-cutoff changes leave that cutoff's features, peers, model input, and predictions unchanged |
| Censoring/data quality | Unknown follow-up, missing channels, resets, gaps, constants handled explicitly without NaNs |
| TSLM evaluation | Starting/fine-tuned models and deterministic baseline have comparable held-out results, counts, invalid outputs, limitations |
| Shared snapshot | Fleet/detail/simulator/copilot agree on cutoff and dataset/model/context versions |
| Risk and priority | Supported probabilities bounded and cumulative risk monotone; unknown risk null; priority obeys documented context policy |
| Model provenance | Captured native numerical invocation traces to submitted weights; cached, baseline, and fixture states distinct |
| Hidden outcome/reset | Outcomes absent before reveal; rewind clears future reveal and stale explanations |
| Complete UI journey | Select drive -> inspect evidence -> interpret sequence -> compare timing -> save draft -> reveal outcome |
| Dependency failure | Missing model/timeout does not block fleet/replay; templates never masquerade as trained inference |
| Reproduction | Data build, training, evaluation, reload, and launch commands exercised and documented |

Use tests for consequential analytical/workflow behavior. Routine styling needs visual verification rather than tests mirroring markup.

## Submission and jury walkthrough

- [ ] Working demo with real inputs and attributed trained-model outputs.
- [ ] Code, environment lockfiles, and actual training configuration.
- [ ] Checkpoint or learned adapter, all required trained components, base-model reference, hashes, access/license notes, and tested reload instructions. Large artifacts excluded from Git still need a submission artifact location.
- [ ] Dataset documentation: source/terms, cohort, schema, TimeNet build, annotations, splits, missingness, censoring, limitations, regeneration commands.
- [ ] Short evaluation with TSLM baseline comparisons, supported risk results, held-out predictions, denominators, and limitations.
- [ ] Demo walkthrough and artifact manifest linking data, connector, model, config, evaluation, and replay versions.

Present without fixed segment timings: introduce the operator and source data; show TimeNet preparation and annotations; explain what was trained; replay a held-out drive; compare the model finding with evidence; save a maintenance draft; reveal the outcome; present aggregate results, failure cases, and learnings. Include a normal control and missed/false-positive case where present. Select cases after models/thresholds are frozen and disclose that selection.

At handoff, distinguish implemented, conditional/unvalidated, and incomplete capabilities. Report tested commands, revisions, actual training/evaluation results, compute consumption, and remaining dependencies. UI progress alone is not a completed challenge submission.

The immediate implementation priority is **a real TimeNet-prepared SMART window with an isolated, auditable language target**, followed by a training-and-reload proof and the operator journey around the trained model.

## Sources

- Host PDF: `Aionic_Temporal_AI_Hackathon.pdf`, PDF pages 14 and 16 (mission, workflow, annotations), 17 (resources, judging, submission), 19 (voucher), 22 (resources/support).
- Host introduction supplied in this conversation: mission, four steps, deliverables, judging, and compute.
- [TimeNet documentation](https://docs.timenet.ai/) and [source](https://github.com/OpenTSLM/TimeNet): pin and verify contracts during implementation.
- [OpenTSLM paper](https://arxiv.org/abs/2510.02410) and [source](https://github.com/OpenTSLM/OpenTSLM): model/training reference, not evidence of DriftOps performance.
- [Hackathon Discord support](https://discord.com/invite/qXsAt4BHV), linked on PDF page 22, for unresolved host-specific access or training questions.
