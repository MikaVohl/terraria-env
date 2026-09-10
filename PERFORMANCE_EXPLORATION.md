# Performance exploration — 2026-09-09

Exploratory prototypes only. Production simulator, PPO implementation, rewards,
and defaults were not changed in this task. Existing worktree edits were preserved.
Hardware runtime: macOS 26.4 arm64, Torch 2.13.0, MPS available.

**Follow-up correctness warning:** the subsequent long-horizon MPS run encountered
an illegal sampled action at iteration 28, yielding -infinity log probabilities
and NaN PPO ratios. The short MPS benchmarks below did not establish long-run
sampler correctness. The large-scale study uses checked CPU categorical sampling
of GPU-computed probabilities; treat its measured throughput as the relevant
replacement, not the all-MPS figures below. See `LARGE_SCALE_STUDY.md` for the
fixed contract, predeclared thresholds, and completed-run results when available.

## Bottom line

Prioritize **native parallel stepping**, then a controlled large-batch GPU learning
experiment. The lighting-cache idea works correctly but gave only modest gains in
these workloads, and almost no incremental end-to-end gain with four workers.
This revises the earlier lighting-first recommendation based on direct experiments.

Two 262,144-step confirmation runs per setup, all CPU cases using two Torch threads:

| Setup | Mean wall steps/sec | Mean training-loop steps/sec |
| --- | ---: | ---: |
| Original scalar, 16 envs | 11,655 | 11,821 |
| Original light, native batch, 4 workers, 16 envs | 16,506 | 16,830 |
| Cached light, native batch, 4 workers, 16 envs | 16,526 | 16,855 |
| Cached light, native batch, 4 workers, 256 envs, CPU | 26,216 | 27,126 |
| Cached light, native batch, 4 workers, 256 envs, MPS | 36,527 | 38,648 |

Wall timing includes model/optimizer initialization and, for the first three
CPU confirmation runs, a final checkpoint save. Training-loop timing excludes
those overheads. The GPU wall timer explicitly synchronizes; prefer that column
for cross-device comparisons. The unchanged-16-env improvement is about **1.42x**.
The 256-env GPU number is a throughput result, not a learning-quality result.

The first scalar/reference-parallel/cached-parallel confirmation checkpoints had
**bit-identical weights** after 262,144 transitions, using the same seed and two
Torch threads. CPU rollout collection fell from 13.42s to 6.86s with parallel
stepping; optimization stayed around 8.7s. Optimization becomes the larger share
after that change. Checkpoints are preserved for inspection.

## 1. Lighting cache

`tools/perf_probe.c` optionally caches terrain-only illumination. The full existing
algorithm recomputes that map when tiles change. On movement, the prototype copies
the cached map and propagates only the player's small light cone. This preserves
max-composition of attenuated light sources; it does not reduce visibility or
remove lighting rules.

At 16 environments, uniform-legal-action scalar rollouts improved from 24,949 to
28,405 transitions/sec (1.14x). With serial native batching, 27,330 became 31,672
(1.16x). Terrain changes still trigger full recomputation, so this is not a blanket
elimination of lighting cost. The benefit is workload-dependent.

This prototype intentionally uses a fixed 512-entry pointer-indexed cache and a
whole-terrain `memcmp`. It is **not production-ready**: cache ownership should live
with each environment, lifecycle cleanup must be explicit, and terrain dirtiness
should be tracked separately from player motion. Initial registration/reset is
serial; concurrent registration is not supported. The cache adds roughly 24 KiB
per slot (terrain copy plus light map). Production dirty tracking could remove the
terrain copy. These limitations are confined to the separately built probe library.

## 2. Native batching and parallel stepping

The prototype C entry point handles step, raw observation, legal mask, reward,
and terminal flags for all lanes. Python one-hot encoding is vectorized and info
dictionaries are only built for completed episodes. Reset ordering and terminal
observations remain caller-owned. This is more than just eliminating one FFI call.

Median uniform-legal rollout throughput, three repeats of 32,768 transitions:

| Configuration | 16 environments | 256 environments |
| --- | ---: | ---: |
| Original scalar wrapper | 24,949 | 24,690 |
| Original lighting, serial native batch | 27,330 | 27,419 |
| Original lighting, four native workers | 77,174 | 93,736 |
| Cached lighting, serial native batch | 31,672 | 32,890 |
| Cached lighting, four native workers | 80,075 | 108,710 |

Numbers include action sampling, observation encoding, masks, and resets, but no
neural network. They are not PPO training throughput. Workers use macOS libdispatch;
a portable production implementation needs a bounded worker pool or equivalent.
The largest gain here comes from parallelizing independent environments, not
merely replacing Python loops. Parallel speedups also argue against treating this
small workload as already saturated on shared memory bandwidth.

## 3. Network and end-to-end execution

Initial 65,536-step PPO probes, including initialization in wall time:

| Setup | Environments | Wall steps/sec |
| --- | ---: | ---: |
| Original scalar, CPU 6 threads | 16 | 10,860 |
| Original lighting, native batch, 4 workers, CPU 2 threads | 16 | 15,645 |
| Cached lighting, native batch, 4 workers, CPU 2 threads | 16 | 15,679 |
| Cached lighting, native batch, 4 workers, CPU 2 threads | 64 | 21,793 |
| Cached lighting, native batch, 4 workers, CPU 2 threads | 256 | 24,220 |
| Cached lighting, native batch, 4 workers, MPS | 16 | 5,736 |
| Cached lighting, native batch, 4 workers, MPS | 64 | 17,060 |
| Cached lighting, native batch, 4 workers, MPS | 256 | 26,801 |

CPU thread sweep (original wrapper, 16 envs): 1/2/4/6/8 threads produced
10,084 / 10,889 / 11,125 / 10,860 / 10,497 wall steps/sec. This is a broad modest
optimum, not compelling evidence for one exact thread count.

MPS is synchronized at the start and end of the outer timer. Internal PPO phase
timers are **not** used for GPU phase comparisons because device execution is
asynchronous. CPU/GPU policies can take different trajectories; these are real
pipeline probes, not fixed-work kernel comparisons.

Larger environment counts retain the 128-step rollout and four minibatches, so
they increase both rollout batch and optimizer minibatch size. At 256 environments,
65k transitions contain only two PPO iterations. Higher throughput is not proof
of better achievement-per-compute efficiency. Learning curves must be remeasured
before changing these defaults.

### Matched-data network microbenchmarks

Five warm-up calls, then 50 inference or 20 update calls, with explicit device
synchronization at timing boundaries. Identical CPU-generated input shapes and
seeded initial model weights; all tensors already reside on the target device.
Inference includes retrieving sampled actions to CPU. Updates use a PPO-shaped
clipped policy/value/entropy loss, gradient clipping, and Adam, not the complete
training loop or a learning-quality evaluation.

| Operation | Batch | CPU 2 threads, ms/call | MPS, ms/call |
| --- | ---: | ---: | ---: |
| Inference + action retrieval | 16 | 0.206 | 0.897 |
| Inference + action retrieval | 64 | 0.341 | 0.844 |
| Inference + action retrieval | 256 | 0.918 | 0.848 |
| Gradient update | 512 | 3.91 | 2.91 |
| Gradient update | 2,048 | 11.49 | 4.27 |
| Gradient update | 8,192 | 42.98 | 10.15 |

MPS inference has substantial near-fixed latency here. At batch 256 it becomes
competitive (six-thread CPU inference was slightly faster at 0.793ms), while
large gradient updates favor GPU strongly. This explains why offloading the
unchanged small-batch pipeline is counterproductive but larger batches warrant
testing. These measurements do not establish a memory-bandwidth bottleneck.

## Validation and reproduction

- Scalar versus native batch: exact observations, masks, rewards, terminal flags,
  final observations, and finished-episode info over 65,536 transitions, tested
  separately with one and four workers. Every resulting full light map was also
  compared against the original lighting algorithm.
- Lighting stress: 20,000 full-map comparisons covering movement, boundaries,
  terrain edits, opaque tiles, and emitters. Passed AddressSanitizer and UBSan.
- No learning-quality claims are made from these short performance runs.
- A brief sanitizer test overlapped part of the initial vector sweep; longer
  confirmation runs are separate. Results are workstation measurements, not
  isolated hardware certification.

From repository root:

```sh
.venv/bin/python tools/run_perf_probe.py experiments/perf-NEW
.venv/bin/python tools/network_probe.py
```

The sweep builds isolated reference/cached shared libraries and selects them only
for child processes via `TERRARIA_LITE_LIB`. It refuses to reuse its output directory.
Raw sweep data: `experiments/perf-sweep-20260909/results.jsonl`.
Longer repeats: `experiments/perf-sweep-20260909/confirmation.jsonl`.
Matched network data: `experiments/perf-sweep-20260909/network.jsonl`.
To reproduce an individual longer run, select either built library with
`TERRARIA_LITE_LIB` and run `tools/perf_probe.py --mode train --steps 262144
--threads 2`; add `--batch --workers 4` for the parallel adapter and optionally
`--envs 256 --device mps` for the GPU configuration.
Prototype sources: `tools/perf_probe.c`, `tools/perf_probe.py`,
`tools/light_probe_test.c`, `tools/network_probe.py`, `tools/run_perf_probe.py`.

## Follow-up: checked-sampling pipeline studies

Artifacts: `experiments/perf-followup-20260910/`. Production defaults and source
were not changed. This follow-up measures the actual checked CPU sampler with
MPS inference and optimization, rather than extrapolating from the earlier
unchecked-sampler or small-CPU-batch probes.

### Design and correctness

The worker/lighting study used 256 environments, 128-step rollouts, batch 32,768,
four epochs/four minibatches, two Torch CPU threads, seed 101, no shaping, and a
constant learning rate of .00015. Each child processed 524,288 transitions; the
first four updates (131,072 transitions) were warmup, leaving 393,216 measured.
Outer timing boundaries explicitly synchronized MPS. Timed children ran
sequentially, in randomized configuration order within repeat blocks.

Two workloads were tested: fresh policy initialization and weights loaded from
the completed 32M checkpoint. The latter starts fresh environments and a fresh
Adam optimizer: it represents a trained-policy workload, not an exact training
resume. Neither workload constitutes a new learning-quality comparison.

There were three timing repeats per trained-policy configuration and two per
fresh configuration. These share a seed; they are not independent learning seeds.
All 46 worker/lighting/profile runs produced bit-identical final model weights
within each workload, including instrumented runs. Separate existing scalar/batch
checks passed for 1/2/4/6/8 workers at 256 environments, each over 65,536 transitions,
comparing observations, masks, rewards, terminal information and full light maps.
Every training run checked sampled action legality and finite final parameters.

### Worker count and lighting

Median synchronized training transitions/sec, trained-policy workload:

| Native workers | Reference lighting | Cached lighting |
| ---: | ---: | ---: |
| 1 | 17,204 | 20,172 |
| 2 | 25,650 | 29,001 |
| 4 | 34,945 | 37,153 |
| 6 | 38,870 | 41,456 |
| 8 | 40,493 | 44,015 |

With caching, eight versus four workers gained 18.5% throughput. The fresh-policy
comparison was similar: 35,526 to 42,028 transitions/sec (+18.3%). Eight was the
best worker count tested, not a proven global optimum.

Lighting was not negligible in the current trained-policy pipeline: paired
cache speedups were 6.2% at four workers and 8.7% at eight. From fresh initialization
the respective gains were only 1.6% and 2.5%. This revises the earlier generalized
lighting conclusion: its importance depends on policy workload, and the earlier
near-zero result at 16 CPU environments does not describe the current MPS setup.

### Synchronized phase attribution

Profiling wraps existing trainer statements without replacing computations.
MPS barriers at phase boundaries make timings attributable but perturb execution:
instrumentation increased wall time 7.5% for trained-policy runs and 5.9% for the
fresh run. Percentages below are diagnostic shares of the instrumented pipeline,
not exact shares of uninstrumented runtime. Trained-policy values average three
runs; the fresh profile has one run. All use four workers and cached lighting.

| Phase | Trained policy | Fresh policy |
| --- | ---: | ---: |
| Environment adapter + action retrieval | 33.2% | 35.0% |
| PPO gradient updates | 23.8% | 23.1% |
| Policy inference, distribution and sampling | 20.6% | 19.9% |
| Transfers, timeout bootstrap and bookkeeping | 17.3% | 16.9% |
| Rollout-buffer writes | 4.5% | 4.3% |
| GAE and flattening | 0.6% | 0.6% |

Nested within these phases, the native step/observation/mask call accounted for
28.8% of trained-policy wall time. Checked sampling, including probability/mask
transfers, accounted for 8.6%. Neither should be added to its parent phase.
Top-level timers cover 99.9% of measured wall time.

Collection, not PPO optimization, dominates the current GPU pipeline. Even
eliminating the entire measured sampling package would have only about a 10%
idealized speedup ceiling under this diagnostic partition. A custom sampler is
therefore not the first optimization to pursue. GAE is also a low priority.

### Longer worker confirmation and CPU/MPS batching

A further 27 sequential runs processed 1,048,576 transitions each, excluding the
first 131,072 from timing. The PPO batch stayed 32,768 and minibatch stayed 8,192.
Environment counts 128/256/512 therefore used rollout lengths 256/128/64. The
trained-policy configurations had three repeats; fresh-policy MPS configurations
had two. All used cached lighting, checked sampling and two Torch CPU threads.

Median synchronized training transitions/sec, trained-policy workload:

| Environments | Rollout | Workers | CPU | MPS |
| ---: | ---: | ---: | ---: | ---: |
| 128 | 256 | 8 | 28,639 | 32,002 |
| 256 | 128 | 4 | not tested | 35,955 |
| 256 | 128 | 8 | 29,918 | 42,371 |
| 512 | 64 | 8 | 30,542 | 51,988 |

The longer four/eight-worker comparison confirms a 17.8% median paired speedup
(repeat ratios 1.149, 1.183, 1.179), again with identical final model weights.
This is a systems change without altering rollout length or optimizer batch size.

At eight workers, 512 environments were 22.7% faster than 256 on MPS; CPU gained
only 2.1%. MPS/CPU throughput ratios were 1.12x, 1.42x and 1.70x for 128, 256 and
512 environments. The fixed large optimizer batch makes MPS worthwhile even at
128 environments in this experiment; there is no universal 256-environment cutoff.
Fresh-policy MPS medians were 32,019 / 41,498 / 52,130 for 128 / 256 / 512 envs.

The fastest measured configuration is 44.6% faster than the four-worker,
256-environment control in this sweep. This is NOT evidence of 44.6% faster
learning: shortening rollouts changes GAE boundaries and trajectories despite
preserving the PPO batch. CPU/MPS numerical and sampling trajectories also differ.
Repeated runs within each device/environment/workload setting had identical final
weights, but those weights differ between settings. No policy-quality promotion
is supported by these short throughput experiments.

### Decisions

- Use eight native workers as the next training configuration on this machine:
  approximately 18% higher throughput, with the existing 256x128 training contract.
  Counts above eight remain untested; no universal hardware recommendation.
- Keep the lighting cache for experiments. It gives a real trained-policy gain;
  production adoption still requires fixing cache ownership, lifecycle and dirty
  tracking. The prototype's 512-slot limit also bounds this batching study.
- Test 512x64 MPS against 256x128 on multi-seed, wall-time learning curves before
  making it the default. It is the strongest measured additional throughput option.
- Prioritize the environment/observation/transfer path for subsequent optimization
  experiments, rather than assuming PPO updates or GAE dominate. Retain the checked
  sampler until a replacement demonstrates correctness and a measured benefit.

For scale only, dividing 31,981,568 transitions by the longer-sweep rates yields
14m49s for four workers, 12m35s for eight, and 10m15s for 512 envs/eight workers.
These are extrapolations from short fixed-LR workloads, not measured 32M runs or
equal-proficiency times.

The two sweeps contain 73 runs and 52,428,800 training transitions in total.
Results and evidence: `results.jsonl`, `batching.jsonl`, `summary.json`,
`batching-summary.json`, `correctness.json`, `manifest.json`, and `provenance.json`
under `experiments/perf-followup-20260910/`. Source snapshots, input checkpoint,
isolated libraries, generated profiling source and per-child logs are retained.
The initial instrumentation smoke caught an AST-location error; after correction,
profiled and unprofiled smoke runs produced identical model hashes. Failed smoke
logs are retained and excluded from all tables.

`study.py` and `batching.py` are the experiment drivers; `analyze.py` and
`analyze_batching.py` regenerate the summaries. To rerun the full experiments,
copy those four scripts into a fresh directory immediately under `experiments/`,
then run `study.py` followed by `batching.py` with `.venv/bin/python`. The drivers
build isolated libraries and refuse to overwrite result files. This reproduces
the protocol using current repository source; the retained source hashes identify
the precise version measured here. No concurrent benchmark children were used.
