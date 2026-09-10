# Large-scale unshaped PPO study

## Fixed contract

Two fresh runs, requested budgets 16M and 32M transitions, seed 101 for both.
Neither resumes another checkpoint. Legal affordance masks only; original +1
achievement/death reward; zero progression shaping; no cloning, demonstrations,
expert trajectories, strategic masks, curriculum, or persistent map. Existing
local observations, recipes, achievements, timeout bootstrapping, and world
generation remain unchanged.

Configuration: 256 environments, 128-step rollouts, four native simulator workers,
cached exact lighting, MPS policy/optimization, two Torch CPU threads. Original
512x512 MLP; four epochs/four minibatches, gamma .999, lambda .95, entropy .01,
LR .0003 annealed independently over each run. Batch 32,768; minibatch 8,192.
Action probabilities are computed on MPS, but categorical sampling uses checked
CPU multinomial; neural inference and optimization remain on MPS. This workaround
was added after the first attempt's iteration 28 contained one illegal sampled
action with old/new log-probability -infinity, causing NaN PPO ratios. Diagnostic
observations were finite. The failed attempt is retained in
`experiments/scaling-20260909/`; it produced no qualifying checkpoint. The checked
sampling run restarts from scratch and may have different throughput/RNG trajectories
than the earlier all-MPS performance probes. No masking rule was weakened.
Whole-batch rounding produces 15,990,784 and 31,981,568 actual transitions.
This deliberately changes the PPO batch from the original baseline; speed does
not imply preserved sample efficiency. One seed per budget is exploratory, not
a robust multi-seed algorithm comparison.

Checkpoint thresholds: 1M, 4M, 8M, 16M, 24M where applicable, plus the final batch.
Each checkpoint is evaluated on the same 128 validation worlds (1000001–1000128),
sampled actions with sampling seed 54321, batch 64, CPU and original lighting.
No best-of-world selection. Evaluation happens in separate processes after each
training run. Final test seeds remain unused. Inference checkpoints do not contain
optimizer/RNG state and are not exact training-resume checkpoints.

## Benchmarks and decision thresholds

The measured benchmark reference is PERFORMANCE_EXPLORATION.md, not a promised
speed: 11.7k scalar CPU, 16.5k parallel CPU (16 envs), 26.2k parallel CPU and
36.5k parallel MPS (256 envs), synchronized wall steps/sec in 262k-step probes.
GPU beats CPU at the tested 256-env pipeline, but loses at 16 and 64 environments.
Only 16/64/256 were tested; the precise crossover is unknown. CPU thread counts
2–6 were close. Serial lighting caching gained 14–16%; with four workers its
incremental training benefit was negligible.

Predeclared decision criteria (engineering choices, not statistical guarantees):

- Correctness gate: exact scalar/batch transitions and full lighting comparisons;
  prior 262k CPU training yielded bit-identical weights across adapters. Abort on
  nonfinite checkpoint parameters or process failure; never silently fall back.
- Throughput target: at least 25k synchronized training transitions/sec over a
  full run. Below this, profile before promoting this configuration. Not an early
  stopping rule: policy workload can change as proficiency improves.
- Proficiency reference: original 4M runs averaged 9.04/24 (range 8.11–10.18).
  Score above 10.18 is encouraging, not proof of superiority with only one seed.
- Progression milestone: at least 10% validation success on copper-pick crafting
  (13 of 128 worlds), previously 0%; report every achievement, not just this one.
- Scaling signal: 32M final mean at least 1 achievement above 16M final mean.
  If less, investigate efficiency/plateaus; do not claim saturation automatically.
- Promotion requires follow-up multi-seed learning curves, not just these two runs.

## Reproduce

```sh
make lib check
.venv/bin/python -m terraria_lite.ppo_selftest
.venv/bin/python tools/scaling_study.py --out experiments/scaling-NEW
```

Separate probe libraries avoid changing production defaults. Cached registration
is serial before stepping; each training process owns 256 persistent environments.
Each evaluation uses a fresh reference-library process, avoiding the experimental
cache's fixed-slot lifecycle limitation. Source snapshots/hashes, configurations,
per-world evaluations, checkpoints, and synchronized total timing are retained.

## Results

Both qualifying runs completed from fresh initialization. The 16M run processed
15,990,784 transitions in 450.38 synchronized seconds (35,538 steps/sec); the
32M run processed 31,981,568 transitions in 897.33 seconds (35,660 steps/sec).
Both clear the predeclared 25k steps/sec target. The checked CPU sampler therefore
retained the practical throughput of the large MPS configuration while avoiding
the illegal-action failure from the discarded attempt.

Validation results:

| Schedule | Checkpoint | Mean achievements | Mean return | Death rate |
|---|---:|---:|---:|---:|
| 16M | 1,015,808 | 4.523 | 4.266 | 25.8% |
| 16M | 4,030,464 | 4.945 | 4.914 | 3.1% |
| 16M | 8,028,160 | 6.617 | 6.617 | 0.0% |
| 16M | 15,990,784 | 11.945 | 11.703 | 24.2% |
| 32M | 1,015,808 | 4.750 | 4.594 | 15.6% |
| 32M | 4,030,464 | 6.031 | 6.000 | 3.1% |
| 32M | 8,028,160 | 11.984 | 11.703 | 28.1% |
| 32M | 16,023,552 | 13.727 | 13.625 | 10.2% |
| 32M | 24,018,944 | 13.953 | 13.891 | 6.2% |
| 32M | 31,981,568 | 13.945 | 13.930 | 1.6% |

The 16M final exceeds the prior 4M-run maximum of 10.18. The 32M final improves
on the 16M final by exactly 2.000 mean achievements, clearing the predeclared
one-achievement scaling signal. Most of that gain arrived by the 16.0M checkpoint
of the longer schedule; its mean then remained effectively flat through 24M and
32M. Because each budget has only one seed and a different independently annealed
schedule, differences at matched transition counts are not controlled estimates
of schedule quality.

The progression milestone did not pass. No validation episode at any checkpoint
crafted a copper pick (required threshold: 13 of 128). At the 32M final, all 128
worlds collected copper, 127 smelted copper, 125 crafted and placed a torch, and
all 128 descended deep, but none advanced beyond the first 14 achievements. The
policy therefore learned the full pre-copper-pick routine reliably and then
plateaued at that boundary. The 24M checkpoint was marginally higher than the
final checkpoint (13.953 versus 13.945), which is consistent with this plateau
rather than continued progression.

Conclusion: promote the 256-environment checked-sampling pipeline as the current
throughput configuration, but do not promote this policy as a solved or robust
learning result. The next algorithm study should target the copper-pick boundary
and use multiple seeds; simply extending this exact schedule beyond 32M is not
supported by the observed 16M–32M curve.

## 100M fresh run with eight native workers

Completed in `experiments/ppo-100m-20260910/`. This is a fresh seed-101 run,
not a continuation of the 32M checkpoint. It retains the 256-environment,
128-step-rollout contract (batch 32,768, minibatch 8,192), original 512x512 MLP,
unshaped reward, legal masks, four epochs/four minibatches, gamma .999, lambda .95,
entropy .01, and .0003 learning rate annealed over the full run. The only selected
performance change from the previous long runs is eight rather than four native
workers. Cached lighting, MPS inference/optimization and checked CPU sampling remain
enabled, with two Torch CPU threads. The faster 512x64 configuration was deliberately
not adopted because its learning-quality effect has not been established.

The requested 100,000,000 transitions were rounded upward to **100,007,936**
(3,052 complete PPO updates), rather than stopping short. Synchronized training
took **2,238.39 seconds (37m18s)** at **44,679 transitions/sec**, including checkpoint
writes and excluding validation. The process and all evaluations exited successfully;
the connection interruption did not restart or interrupt training. All ten checkpoints
were evaluated afterward in separate CPU/reference-lighting processes on the same
128 validation worlds, sampling seed 54321 and evaluation batch 64. Test worlds
remain unused.

### Validation learning curve

| Actual transitions | Mean achievements /24 | Mean return | Death rate | Copper-pick successes |
| ---: | ---: | ---: | ---: | ---: |
| 1,015,808 | 4.352 | 3.859 | 49.2% | 0/128 |
| 4,030,464 | 7.688 | 7.664 | 2.3% | 0/128 |
| 8,028,160 | 11.195 | 11.141 | 5.5% | 0/128 |
| 16,023,552 | 13.141 | 13.109 | 3.1% | 0/128 |
| 24,018,944 | 13.586 | 13.523 | 6.2% | 0/128 |
| 32,014,336 | 13.188 | 13.109 | 7.8% | 0/128 |
| 48,005,120 | 13.695 | 13.578 | 11.7% | 0/128 |
| 64,028,672 | 13.805 | 13.750 | 5.5% | 0/128 |
| 80,019,456 | 13.766 | 13.766 | 0.0% | 0/128 |
| 100,007,936 | 13.828 | 13.797 | 3.1% | 0/128 |

The final checkpoint has the best mean achievement score within this run, but
its **13.828/24** is **0.117 below** the previous independent 32M final's 13.945.
Its median, p90 and maximum are all 14 achievements. Mean episode length is
2,947.98 actions. No saved checkpoint's validation reached the copper pick,
iron progression or lantern. More compute did not break the observed progression
boundary. This does not establish universal saturation: there is only one seed
per schedule, and the LR annealing horizon differs. It does not justify another
blind budget increase for this configuration.

### Final per-achievement validation counts

| Achievement | Worlds /128 |
| --- | ---: |
| collect wood | 128 |
| collect dirt | 128 |
| collect stone | 128 |
| place block | 128 |
| craft workbench | 128 |
| place workbench | 128 |
| craft stone pick | 128 |
| craft furnace | 128 |
| place furnace | 128 |
| collect copper | 125 |
| smelt copper | 123 |
| craft torch | 121 |
| place torch | 121 |
| craft copper pick | 0 |
| collect iron | 0 |
| smelt iron | 0 |
| craft anvil | 0 |
| place anvil | 0 |
| craft iron pick | 0 |
| collect gold | 0 |
| smelt gold | 0 |
| craft lantern | 0 |
| place lantern | 0 |
| descend deep | 128 |

### Artifacts and verification

Final weights remain local at
`experiments/ppo-100m-20260910/training/step-100007936.pt` and are ignored by
Git. All ten compact per-world evaluations, configuration, synchronized timing,
checkpoint hashes and the plotted learning curve are committed under the study
directory. `manifest.json` records the frozen protocol and source/library hashes;
`summary.json` contains the full learning curve, achievement counts and prior-run
comparison.

`run.py --smoke` first completed an isolated 262,144-transition training/checkpoint/
128-world evaluation workflow. During the full run, every checkpoint's parameters
were checked finite before it was written. `analyze.py` verifies the retained 128
expected world records at every checkpoint and recomputes aggregate means and all
24 achievement counts. Checkpoints contain inference weights only, not optimizer,
RNG or environment state for exact resumption. No production defaults were changed.
The committed manifest and summaries preserve the result; rerunning `run.py`
requires creating a new output directory because the original frozen source and
libraries are intentionally local experiment payloads rather than repository code.
