# Canary five-minute presentation

## The argument

The audience knows hardware teams have charts and alerts. They may doubt that another AI description helps an operator.

They should consider a proposed paid pilot with a storage operations team. The pilot must test whether linked descriptions improve inspection speed without reducing correctness.

The gap is measured customer value. The benchmark supports numerical signal descriptions, but it does not establish savings, failure prediction, or buyer demand.

Four of eight slides cover industry impact, the British Airways case, proposed operator value, and the commercial next step. Three slides show model evidence, inference architecture, and training architecture. The demo connects saved answers to measurements.

## Delivery plan

The [eight-slide deck](../PresentationDraftDeck.html) has a planned 300-second schedule, including a 35-second demo. Actual timing requires rehearsal.

| Slide | Planned time | Duration | Takeaway |
| --- | --- | ---: | --- |
| 1 | 0:00 to 0:35 | 35 seconds | An outage can cost over $1 million. |
| 2 | 0:35 to 1:05 | 30 seconds | A data-center outage disrupted British Airways. |
| 3 | 1:05 to 1:35 | 30 seconds | Give operators a checkable starting point. |
| 4 | 1:35 to 2:10 | 35 seconds | The HDD model reads signal patterns. |
| 5 | 2:10 to 2:45 | 35 seconds | Small trained modules turn measurements into words. |
| 6 | 2:45 to 3:25 | 40 seconds | Training updates only selected model weights. |
| 7 | 3:25 to 4:25 | 60 seconds | Check the answer. Keep the mistakes visible. |
| 8 | 4:25 to 5:00 | 35 seconds | Help us find our first pilot partner. |

Open the evidence route before presenting. The demo runs from 3:40 to 4:15. Keep the slide tab available. Slide 7 retains both examples if the route is unavailable.

## Speaker script

The native notes contain the same script. It contains 518 spoken words, excluding headings, timing cues, sources, and demo actions.

### Slide 1, 0:00 to 0:35

Hardware problems can become expensive incidents. In Uptime Institute's 2025 survey, one in five respondents reporting a significant outage said it cost more than one million dollars.

That is industry context, not savings Canary claims to deliver. Our proposed first customer is a storage operations team.

An alert starts their investigation. Someone must still inspect the history. Canary puts short descriptions beside the measurements so that person has a checkable starting point.

### Slide 2, 0:35 to 1:05

British Airways shows how widely an outage can spread. In May 2017, disruption continued across three days. The airline canceled 672 flights in the first two days.

DCD reported about 75,000 passenger cancellations and estimated claims of 58 million pounds. That was an estimate, not a settlement amount. BA cited power, but the exact cause remained disputed.

### Slide 3, 1:05 to 1:35

Our proposed workflow is simple. Select a device, check its explanation, then decide what to inspect.

Today, the evidence view places real measurements beside saved model answers. The surrounding fleet uses synthetic data and rules.

The buyer hypothesis is less time interpreting charts without more mistakes. A pilot must test that benefit. Operators keep the decision.

### Slide 4, 1:35 to 2:10

The HDD model matched 99.68 percent of weak signal labels across 6,777 answers from 2,048 unseen drives.

An always-constant answer scored 69.43 percent. With numerical inputs zeroed, the model scored 86.01 percent. The numbers affect its answers.

Fixed rules generated these labels. Those rules score one hundred percent by construction. This measures signal descriptions, not superiority over the rules, failure prediction, or customer savings.

### Slide 5, 2:10 to 2:45

We normalize twenty-eight samples, encode their pattern, and project it into Gemma 3 270M to generate a description.

We trained the encoder, projector, and attention adapters. The original Gemma base stayed frozen. Only 1.08 percent of parameters were trained.

We fitted thirteen independent component models, each with its own data and checks. HDD training covered 11.32 million windows. These results do not form one universal model or combined accuracy score.

### Slide 6, 2:45 to 3:25

We turn dated hardware histories into TimeF records, with separate devices and periods for training, validation, and testing. Each input contains twenty-eight observations, normalized within that window.

During training, weighted cross-entropy compares answer tokens with separate rule-generated targets. Those targets never enter the inference prompt.

Backpropagation calculates gradients. AdamW updates the encoder, projector, and attention adapters, with weight decay. The original Gemma weights stay frozen. Validation selects the checkpoint before we open the test set.

### Slide 7, 3:25 to 4:25

Let us check a real saved answer. I will open the rising case, show its measurements and cutoff, then show a mismatch.

**Demo actions, 3:40 to 4:15. Open the saved-output demo. Show the rising case and December 23, 2025 cutoff. Select the model-mismatch case. Show SMART 194, saved answer falling, and weak reference fluctuating. Return to slide 7. Do not read this cue aloud.**

The model says falling while the weak reference says fluctuating. Both remain visible. This is saved inference, with no new model call in the browser. Operators must be able to challenge the answer.

### Slide 8, 4:25 to 5:00

We are looking for our first storage operations pilot partner.

Our proposed commercial path is a paid pilot, then a fleet subscription if results justify it. Pricing and buyer demand still need testing.

Measure inspection time and correct findings against raw charts. Ask experts to review explanations independently of our labels.

The next proof is customer value. Introduce us to a storage operations lead who can help test it.

## Additional architecture evidence

The attachment supplied the architecture topics. Repository code controls the technical claims. TimeNet writes and verifies TimeF records with values, times, metadata, and separate targets. The HDD preparation assigns disjoint drives and ordered periods before it creates gap-free 28-day windows. See [data preparation](../src/driftops/full_dataset.py) and [normalization](../src/driftops/tslm_dataset.py).

The base is `google/gemma-3-270m`. The pretrained time-series model is `OpenTSLM/gemma-3-270m-tsqa-sp`. The loader uses upstream encoder and projector states, then adds attention LoRA. The original Gemma parameters stay frozen. See [model configuration](../config/model.yaml).

Weighted cross-entropy applies training-frequency weights to answer-entry tokens. Prompt and padding tokens are masked. The loss divides summed weighted token losses by the sum of token weights. These are token weights, not example or sampling weights. See [loss implementation](../src/driftops/full_training.py).

Backpropagation computes gradients. After norm clipping at 1.0, AdamW updates only the encoder, projector, and LoRA weights, with weight decay 0.01. Encoder and projector learning rates are 0.0001. LoRA uses 0.00005. See [training loop](../src/driftops/train_full.py) and [recorded optimizer settings](../results/2026-09-13/runs/full-history-rtx6000-v2/config.json).

HDD training covers 2013 through 2024. Validation covers January through September 2025. The unused calibration reserve has separate drives over the same dates. Test covers October 2025 through March 2026. Unweighted validation answer loss selects a completed checkpoint before test release. See [split configuration](../config/full_history.yaml). These dated HDD boundaries do not establish chronology for the separate sound datasets.

## British Airways case limits

 DCD, February 11, 2019, reports an estimated £58 million in passenger compensation claims and about 75,000 passenger cancellations. The estimate is not a final bill or settlement amount. BA and CBRE settled with no admission of liability; payment and exact cause were not established in that report. BA attributed the outage to a power supply issue. DCD reports problems from Saturday to Monday morning, May 27 to 29, 2017. This is three calendar days, not 72 hours of complete shutdown. IAG reported 479 canceled flights on May 27 and 193 on May 28, totaling 672 over two days. BA had resumed most flights by May 29. BA interim accounts separately record a £56 million provision for compensation fees and baggage claims. That accounting provision differs from the £58 million press estimate displayed on this slide. None of these figures establishes Canary preventability, savings, or a customer relationship. Sources  DCD settlement report, February 11, 2019  IAG traffic statement, June 6, 2017  BA interim accounts 2017, page 15  

Sources: [DCD settlement report](https://www.datacenterdynamics.com/en/news/ba-and-cbre-settle-dispute-over-2017-data-center-outage/), [IAG traffic statement](https://www.cnmv.es/webservices/verdocumento/ver?e=SXm4iA7ape7KuPe%2Ftg89%2BqfqoTZheLsWaW8eg8EG1exQSRh0dt1K2vXNhAR3mLSV), [BA interim accounts](https://www.iairgroup.com/media/344neah0/interim-management-report-for-six-months-to-june-30-2017.pdf).

## Commercial assumptions

The first proposed buyer is a storage operations team. A paid pilot would compare correct findings and inspection time against raw charts. The proposed next contract is a fleet subscription, conditional on useful pilot results. No price, customer, revenue, signed pilot, demand, or savings has been established. These are hypotheses to test with a buyer.

## Evidence and scope

- [Uptime Institute Global Data Center Survey 2025](https://datacenter.uptimeinstitute.com/rs/711-RIA-145/images/2025.Annual.Survey.Report.pdf?version=0#page=19) supplies the opening industry-impact statistic. July 2025, Figure 11, page 19, cost responses n=94. One in five respondents reported a significant outage cost above $1 million. Costs are self-reported totals through recovery, including direct, opportunity, and reputation costs. The [May 11, 2026 outage analysis](https://intelligence.uptimeinstitute.com/index.php/resource/annual-outage-analysis-2026) repeats this result from the 2025 survey. This does not estimate Canary savings or imply that hardware inspection prevents every outage.
- [Measured metrics](../results/2026-09-13/measured-metrics.json) supplies the model scores, parameter audit, and generation timing. All fifteen exported metric files matched their recorded hashes in the September 13 review.
- [HDD frozen results](../results/2026-09-13/runs/full-history-rtx6000-v2/evaluation/metrics.json) records 6,755 correct channel labels out of 6,777. Accuracy is 99.6753726%. Zero-input accuracy is 86.0115095%. Constant accuracy is 69.4259997%. The raw channel-accuracy difference is 13.6638631 percentage points. The zero-input control retains the same text, including scale metadata.
- [HDD training report](full-history-training.md) records 11,315,069 eligible training windows across 260,618 training drives. Training dates end December 31, 2024. The test reserve covers October 1, 2025 through March 31, 2026. The displayed test uses one window each from 2,048 disjoint held-out drives.
- [Saved HDD cases](../results/2026-09-13/hdd-demo-cases.json) supplies the exact raw traces and model text. The rising case ends December 23, 2025. SMART 197 contains eight zero samples followed by twenty samples at eight. The mismatch is SMART 194 on a different drive, October 1 through October 28, 2025. Its model answer is `falling`. Its weak reference is `fluctuating without a clear net trend`.
- [Component results](component-model-results.md) documents all thirteen passing component categories and both failed dated radiator-valve evaluations. These are independent fitted models, not a universal multi-component model. Five industrial groups per test limit the supported population. Slide rail and industrial valve sound lack verified acquisition dates.
- [Presentation evidence review](reviews/2026-09-13/presentation-plan.md) documents the parameter audit. The model has 2,931,072 trainable and 268,098,816 frozen parameters, 271,029,888 in total. The encoder has 2,110,976 trainable parameters. The projector has 82,816. Rank-8 attention LoRA has 737,280, with alpha 16 and q/k/v/o projection targets.
- The temporal encoder uses four-sample patches, six transformer layers, and width 128. The projector maps to Gemma's 640-dimensional embeddings. The upstream model is [OpenTSLM/gemma-3-270m-tsqa-sp](https://huggingface.co/OpenTSLM/gemma-3-270m-tsqa-sp). The correct [OpenTSLM paper](https://arxiv.org/abs/2510.02410) is 2510.02410.

The labels describe observed signal patterns. The rules that generated them score 100% by construction. No slide claims validated failure probability, warning time, avoided downtime, physical causes, or maintenance savings. No slide uses batch-generation timing as browser-request latency. The demo displays saved inference, and the surrounding fleet remains illustrative.

## Presenter controls

1. Open the deck and select **Fullscreen** when the browser supports it.
2. Use the visible Previous and Next buttons or the left and right arrow keys.
3. Select **Notes** to read the current script, timing cues, and sources.
4. Start the optional five-minute timer from the notes panel.
5. Use **Home** for the first slide and **End** for the last slide.
6. Press **N** to open notes or **F** to request fullscreen.
7. Swipe left or right to change slides on a touch screen.
8. Use the browser's print command to export all eight slides.

The desktop stage uses 16:9 framing. Narrow screens use a readable single-column slide layout. The deck uses system fonts and no external JavaScript library. The deck uses the supplied gold-bird artwork without modifying it. Its asset hook resolves the hosted image and a repository fallback. The colors follow the gold-and-black artwork.
