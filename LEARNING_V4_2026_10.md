# v4 learning and causal study

Status: **complete**.

The production task is unchanged: a 2×3 body, pass-through trees, 73 primitive actions, 32 achievements and 3000-action episodes. All production learners use legal masks, sparse achievement rewards, no demonstrations, no prerequisite shaping and no strategic masks.

Completed main training: **247,463,936 transitions**, counted across independent learners, not one continuous agent. Two training seeds per condition; this is an exploratory comparison, not a precise population ranking.

Validation: 6,000,001–6,000,128; sampler 54321. Reserved test: 7,000,001–7,000,128. A validation-selected checkpoint is frozen before the one-shot test. Historical splits/results remain historical; do not combine different task versions into a leaderboard.

## Final checkpoint comparisons

Rows weight training seeds equally. The causal screen uses constant learning rate at 1M; method and scaling runs anneal learning rate over their own full budget. Compare within a stage/budget, not intermediate checkpoints across different schedules.

| Condition | Seed scores /32 | Mean /32 | Stone | Furnace | Death | Peak feet y | Wall/run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| causal/control | 9.74 / 9.98 | 9.86 | 0.0% | 0.0% | 18.4% | 34.9 | 1.2 min |
| causal/width1 | 8.86 / 10.03 | 9.45 | 0.0% | 0.0% | 33.6% | 35.1 | 1.2 min |
| causal/height2 | 9.84 / 9.70 | 9.77 | 2.0% | 0.0% | 41.4% | 35.2 | 1.2 min |
| causal/body1x2 | 9.09 / 16.34 | 12.71 | 50.0% | 0.4% | 46.9% | 64.2 | 1.2 min |
| causal/jump3 | 10.13 / 16.38 | 13.25 | 50.0% | 0.4% | 28.9% | 64.0 | 1.2 min |
| causal/anchored | 14.97 / 10.56 | 12.77 | 46.1% | 0.8% | 50.8% | 55.6 | 1.2 min |
| screen/baseline | 9.95 / 10.30 | 10.12 | 0.0% | 0.0% | 7.0% | 34.9 | 4.8 min |
| screen/trace | 10.03 / 9.00 | 9.52 | 0.0% | 0.0% | 2.3% | 34.8 | 4.9 min |
| screen/explore | 10.20 / 10.08 | 10.14 | 0.0% | 0.0% | 8.2% | 35.1 | 4.9 min |
| screen/targets | 10.09 / 15.34 | 12.71 | 50.0% | 0.0% | 17.2% | 61.6 | 8.4 min |
| scale/baseline/16777216 | 20.87 / 10.87 | 15.87 | 50.0% | 41.0% | 3.9% | 59.5 | 20.5 min |
| scale/targets/16777216 | 18.58 / 18.20 | 18.39 | 100.0% | 2.0% | 9.0% | 90.4 | 31.5 min |
| scale/baseline/33554432 | 10.72 / 10.93 | 10.82 | 0.0% | 0.0% | 0.8% | 34.8 | 40.5 min |
| scale/targets/33554432 | 18.55 / 19.73 | 19.14 | 99.6% | 17.6% | 18.4% | 90.8 | 66.9 min |

## Frozen selection and fresh test

Selected `scale/baseline-16777216-101` at 16,777,216 steps (20.867/32 validation). Fresh test: **20.789/32**, stone 128/128, furnace 100/128, death 1.6%. Test split is now consumed; do not tune against it.

Scaling alternative selected by the predeclared two-seed **final** 4M validation criterion: `targets`. Both this method and baseline restart from scratch at each long budget.

## What changed our understanding

At 16M, the shared-target/longer-trace/higher-entropy package averaged **18.39/32**, versus 15.87 for baseline. At 32M the respective means were **19.14** and 10.82. Both target seeds learned mining at both long budgets; only one of the four long baseline runs did. However, that baseline run remained the best individual policy. Two seeds do not establish a definitive method ranking, and the target package changes architecture, trace and entropy together relative to baseline.

More transitions alone were not sufficient: both fresh 32M baseline runs stayed surface-bound. This is evidence of a discovery/learning-stability bottleneck under these schedules, not a demonstration that additional compute cannot help. The shared-target model is a useful reliability candidate, not a replacement automatically promoted to the default.

### Remaining behavioral bottleneck

A separate diagnostic of the selected policy uses the existing validation worlds, not additional reserved-test evaluations. Furnace crafting was legal in 106/128 episodes; conditional action probability was 99.6%. Anvil crafting had opportunities in only 2 episodes. Iron/gold pickaxes, metal swords and both armor recipes had zero legal opportunities. The issue is accumulating ingredients and keeping the appropriate stations accessible, not merely increasing those recipes' logits. Legality telemetry cannot by itself separate navigation, resource retention and station placement as causes.

On the one-shot test, mean actions after the final new achievement were 1744. The fixed seed-9 replay earned 21 achievements, then spent its final 1862 actions without another. It genuinely excavated 126 original stone cells but also placed 130 stone blocks: recycling/building persists alongside progress. This one replay is illustrative, not an aggregate success estimate.

### Recommended next sequence

1. In a separately versioned game change, fix tool ownership/crafting semantics and enforce necessary material supply, retaining real recipes and primitive actions. Add regressions for crafting tools out of order and resource sufficiency. Do not erase the v4 task or reinterpret its scores.
2. On that frozen version, compare the target package with a generic recurrent spatial policy and an explicit exploration intervention, one factor at a time. Longer-horizon credit assignment, resource retention and navigation memory are hypotheses to test, not proven fixes. Keep legal masks and sparse achievements; do not introduce a mining macro, recipe controller or expert cloning.
3. Use at least five training seeds for the promising comparison, report both equal-transition and equal-wall-time results, and reserve a new test range. The 7,000,001–7,000,128 range is consumed. Scale compute after a reproducible crafting breakthrough, rather than interpreting one lucky seed as saturation.

No production gameplay or art changed during this study; model defaults and existing default checkpoint files were not replaced. All experimental changes remain available for the project owner's keep/revert decision.

## Performance

After training and diagnostics stopped, the three-repeat isolated harness measured **1,290,047 core transitions/s** and **978,961 native-batch transitions/s**. These are random legal-action simulator workloads, not policy-training throughput.

In the long runs, approximately 72–74% of wall time was PPO optimization and 24–26% collection; validation and other overhead account for the remainder. Collection includes policy inference and observation handling, not just C physics. Observed process memory was under 1 GiB per learner on a 48 GiB machine. The evidence points to neural-network training/inference throughput rather than disk I/O, RAM capacity or the raw simulator. No hardware counters were collected, so arithmetic versus memory-bandwidth limits remain unproven.

The small MPS calibration was slower end-to-end than CPU, and target scoring remains more costly despite fewer parameters. Main runs used CPU and up to three concurrent jobs. No simulator optimization speedup is claimed from timing noise.

## Finite-resource ceiling

A post-hoc census of seeds 0–255 found **131/256 worlds** cannot support all 32 achievements together even ignoring time, navigation and combat. The anvil + iron pick + iron chainmail require 40 iron bars, or 120 iron ore; the gold pick requires 40 gold ore. Iron is insufficient in 108 worlds, gold in 49, both in 26. Tile drops, initial inventory and chest loot are included.

These necessary conditions alone bound this sample's mean maximum at **31.39/32**; actual achievable scores within 3000 actions may be lower. This does not explain surface-bound policies or a large gap below that ceiling. Sufficient material is not a reachability proof. No census data enters training or model selection, and reserved test worlds were not inspected.

For the next game version, prefer a deterministic resource-supply floor after cave/chest generation, retaining Terraria recipes, over making recipes artificially cheap. Do not change the current game mid-comparison; a generator change needs a new version, new evidence and fresh training.

There is also a remaining tool-model simplification in `do_craft`/`can_craft`: pick recipes grant an irreversible upgrade tier rather than a separately owned tool. Gold-first therefore makes the Iron-pick recipe illegal and permanently misses its achievement. The mask mirrors the implemented handler, but this is not faithful independent-tool crafting. Revisit it in the next version—prefer explicit crafted tools/equipment over forcing an ore-ladder order. These rules remain unchanged throughout this study. The official wiki describes crafting availability in terms of ingredients and stations, not the player's highest tool tier: [Recipes](https://terraria.wiki.gg/wiki/Recipes). The current 10-bar pick costs match the modern recipes: [Iron Bar](https://terraria.wiki.gg/wiki/Iron_Bar), [Gold Pickaxe](https://terraria.wiki.gg/wiki/Gold_Pickaxe).

## Interpretation limits

- Width reduction alone did not restore stone collection at 1M. The old 1×2 body, a shorter jump and anchored placement each broke through in one seed, not both. This supports interacting geometry/mobility/building effects and seed-dependent exploration thresholds, not a single proven width bottleneck.
- Diagnostic variants have distinct version IDs and retain all 73 target coordinates. They are counterfactuals, not official benchmark environments or candidates for test selection. The 1×2 variant is not a complete recreation of the old v3 interface.
- Peak depth means maximum absolute feet y, not depth below local surface. Achievement-time means are conditional on reaching that achievement.
- More GAE trace persistence and entropy remain generic learning choices. Shared-target spatial scoring ties mining/placement parameters across target positions; it contains no digging controller, preferred recipe, goal order or target priority.
- Fewer model parameters do not imply faster training. Target scoring was slower in CPU pilots; factoring the repeated global projection improved it. MPS was slower end-to-end in the small calibration batch, so the main study uses CPU throughout.
- Across budgets, total steps and the learning-rate schedule change together. A breakthrough at the first 4M checkpoint of a 16M run is not evidence that it already consumed 16M steps; it retained a higher learning rate than a 4M-ending run.
- Up to three jobs ran concurrently on the active desktop. Wall times include validation and reflect contention; they are not dedicated-machine ceilings or an isolated architecture throughput comparison. Equal-transition trials are not equal-compute trials.

## Feasibility and correctness

A white-box diagnostic mined stone and crafted a furnace in all 256 generated worlds with mobs enabled and all 256 with mobs disabled. It explicitly starts with 14 wood and three torches and observes terrain identity. This establishes physical progression given prerequisites, not learned proficiency or end-to-end resource gathering. No probe actions or outputs enter the learner.

Scalar/native/worker/encoding parity, legal gradients and checkpoint reloads passed. The API-only metadata addition preserves the old frozen v4 rollout digest over 27,913 transitions. Target scorer factoring was checked against the direct expression for forward outputs and gradients at 1e-7 tolerance. Frozen production source hashes are recorded in the study protocol and checked by the runner.

## Local artifacts

Study: `/Users/mikavohl/Projects/terraria-lite/experiments/learning-v4-20261010.GWpaf4`. Each run preserves its protocol, package snapshot, checkpoints, validation episode records, phase timings and training summary. The companion JSON retains compact curves, per-achievement timings, source hashes, calibration/probe evidence and selection provenance. Old reports were not overwritten.
