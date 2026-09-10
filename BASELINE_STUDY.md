# Unshaped baseline study

This study follows the project's agreed direction: fixed mechanics and achievements,
randomized worlds, local observations, legal masks, original achievement/death
rewards, no demonstrations, and no progression shaping. PPO is the first baseline,
not an architectural requirement for future agents.

## Completed results — 2026-09-05

Three runs completed 3,999,744 transitions each (11,999,232 total). Twelve
checkpoints were evaluated for 1,536 episodes total, reusing the same 128
validation worlds at each checkpoint. No demonstrations or progress shaping.

| Training steps | Seed 101 | Seed 202 | Seed 303 | Mean ± seed SD | Mean training seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| 251,904 | 4.40 | 3.91 | 4.75 | 4.35 ± 0.42 | 21.9 |
| 1,001,472 | 4.71 | 4.73 | 5.98 | 5.14 ± 0.73 | 86.1 |
| 2,000,896 | 7.55 | 4.73 | 6.42 | 6.23 ± 1.42 | 173.4 |
| 3,999,744 | 10.18 | 8.11 | 8.84 | 9.04 ± 1.05 | 344.3 |

Scores are mean achievements out of 24. SD is the sample standard deviation of
the three run means, not a confidence interval or episode-level deviation.
Training seconds sum collection and optimization timers. Aggregate throughput
was 11,616 transitions/second, with 63.0% collection and 37.0% optimization.

The final policies' pooled death rate was 6.77%, versus 80.47% for uniform legal
actions. Each final policy reached at most 14 achievements in any validation
episode. Selected achievement success rates across 384 final-policy episodes:

| Achievement | Success rate |
| --- | ---: |
| Craft/place workbench | 99.2% |
| Craft/place furnace | 77.9% |
| Craft stone pick | 31.0% |
| Collect copper | 21.9% |
| Smelt copper | 18.0% |
| Craft/place torch | 6.5% |
| Craft copper pick | 0% |
| Descend deep | 67.2% |

### Interpretation and next experiment

- **Unshaped learning works, but is far from saturation.** All three runs learn
  crafting and improve between 2M and 4M. This does not establish a plateau.
  A 16M-step-from-scratch schedule is a useful next scaling control; simply
  resuming these weights would also require deciding how to restart the learning
  rate and optimizer, which are not included in the plain inference checkpoints.
- **The progression gap begins before copper tools.** Stone-pick success varies
  from 3.1% to 48.4% by training seed; smelting varies from 1.6% to 31.3%.
  Rare successful transitions and long-horizon credit assignment are plausible
  issues, but these aggregate results do not distinguish exploration, memory,
  resource management, or policy capacity as the cause. Log action availability,
  resource trajectories, and time-to-achievement before choosing an intervention.
- **Lighting is the clearest measured speed target.** Optimize with bit-exact
  observation/transition comparisons against the existing implementation, then
  remeasure end-to-end throughput. Faster rollout collection is relevant to any
  learning algorithm; a cluster alone does not remove this serial simulator work.
- **Do not infer a BC/shaping winner from this study.** Earlier shaped results
  used different validation worlds and training seeds. A fair comparison needs
  matched budgets and evaluation; this study instead establishes the preferred
  no-demonstration baseline. CNNs, memory, intrinsic rewards, and alternative RL
  algorithms remain hypotheses for controlled follow-ups.

Raw records, configurations, source hashes/snapshots, and twelve checkpoints are
in `experiments/unshaped-20260905/`. `results.jsonl` contains every per-world
outcome; `training-*.json` contains training summaries. No final test set was used.

## Reproduction

```sh
make lib check
uv run python -m terraria_lite.ppo_selftest
uv run python -m terraria_lite.baseline_study --out experiments/unshaped-NEW
```

The runner refuses to overwrite an existing output directory. It records source
snapshots and hashes, configuration, platform and Torch version, checkpoint timing,
and per-world evaluation records. Checkpoints remain ignored by Git's existing
`*.pt` rule. Source snapshots are provenance artifacts, not maintained code.

## Protocol

- Three independent initializations: 101, 202, 303.
- Four million requested training transitions per seed; actual counts are rounded
  down to whole 2,048-transition batches and recorded explicitly.
- Checkpoints near 250k, 1M, 2M, and 4M transitions.
- Existing 512-by-512 MLP, 16 environments, 128-step rollout, gamma 0.999,
  lambda 0.95, and a learning rate annealed over the full 4M-step run.
- These are intermediate points on one training schedule, not independent
  optimally annealed runs for each smaller budget.
- Validation: 128 worlds, seeds 1000001 through 1000128, sampled actions,
  sampling seed 54321, batch size 64. Evaluation happens after training so it
  cannot perturb training random-number state.
- Test worlds remain unused. Validation is for development and comparison,
  not a final benchmark claim.
- Evaluation stops at death or the existing 3,000-action episode limit.
- Each world contributes one score; no best-of selection.

## Reference policy

The matched uniform legal-action policy scores 4.1484/24 across these 128 validation
worlds, with 80.47% deaths and 1,038.8 actions per episode. It reaches no crafting
achievements. This uses the same evaluator, sampling seed, and batch size as PPO.

## Timing interpretation

Collection timing includes network action sampling, Python/ctypes calls, simulation,
observation construction, resets, and timeout bootstrapping. Optimization timing
includes GAE and gradient updates. Checkpoint writes and evaluation are excluded
from these two component timers. These measurements use the CPU; asynchronous
accelerator work would require synchronized timing before comparing devices.

An initial legal-action microprofile spent 1.165 of 1.476 seconds directly in the
Python `step` method (including its C call); observation encoding took 0.079 seconds
inclusive and info generation 0.032 seconds. This does not isolate lighting or other
C components. It supports a subsequent native profile rather than assuming all
collection cost is Python overhead. The microprofile ran alongside training and
is indicative, not an isolated hardware throughput benchmark.

A five-second native stack sample during seed 303 found `light_recompute` in
169 of 398 main-thread samples (42.5%); 74 samples were at the full-map light
histogram loop and 35 at seed-list construction. This is direct evidence that
lighting is a substantial hotspot in that training window. It is not a precise
whole-run CPU fraction or a guaranteed speedup. The sampling report is preserved
as `experiments/unshaped-20260905/native-sample.txt`; seed 303's timing includes
this brief profiler attachment. A small callback correctness test also ran
concurrently, so these are practical workstation timings, not isolated benchmarks.

## Correctness and benchmark boundaries

The native selftests and PPO boundary selftest pass. A separate 4,096-step
fixed-seed comparison produced bit-identical learned weights with and without
checkpoint saves in the callback, and callbacks saw the expected step counts.
The study runner also passed a short end-to-end checkpoint/evaluation smoke test.

This establishes the existing training baseline, not a frozen benchmark release.
Two contracts still deserve explicit decisions before publishing a leaderboard:

- The existing trainer bootstraps value at the 3,000-action truncation, while
  evaluation scores only those 3,000 actions and observations include elapsed
  time. Continuing-task truncation and a genuinely finite-horizon objective are
  different; compare these semantics explicitly rather than silently changing
  them inside a performance experiment.
- Legal masks are part of the agent's information: they consult true local tile
  and station state, including state obscured by darkness. The LLM interface
  should receive the same affordance information if it shares this track.

No game mechanics, observation rules, reward weights, or action masks were
changed for this study. The runner remains PPO-specific; the evaluation protocol
is intended to apply to other algorithms too.
