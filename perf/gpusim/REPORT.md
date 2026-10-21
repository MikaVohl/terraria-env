# GPU-native terraria-lite simulator: feasibility, measurements, recommendation

Date: 2026-10-21. Machine: eg18. Every number below was measured on **GPU 7 only** (MI350X, gfx950, ROCm 7.2.2 hipcc; torch 2.13.0+rocm7.1 from `~/Projects/RL/.venv`) with ≤16 CPU threads (`taskset -c 368-383`; these are the SMT siblings of cores 176-191). The CPU library is the repo's v4 `libterraria.so` (commit 717773c), loaded read-only. The main repo and its venv were not modified (`git status` is clean). All code and logs are in `~/Projects/RL-gpusim` (471 MB, mostly the torch inductor cache).

> **Branch note (perf).** This is the original evaluation, done in a scratch directory
> against commit 717773c. In this branch the light-window patch is part of `src/light.c`
> (commit 6871cde), and this directory builds against the repo's own `src/` and `include/`.
> So `gs_main` here is the "patched" build; the "verbatim" columns below are historical.
> The original logs are in `logs/eval1/`; the branch's parity logs are `logs/p0_*.log`. See §7 for
> the commands that apply to this branch.

## TL;DR

* **The simulator ports to the GPU with no source changes, and the port is bit-exact.** All of `sim.c`, `worldgen.c`, `light.c` and `obs.c` compile unmodified as HIP `__host__ __device__` code, run one env per GPU thread, and keep `Env` resident in device memory. Three wrapper-level details make this work: `#pragma clang force_cuda_host_device`, `snprintf` (the messages) compiled out of the device pass only, and a device port of glibc's `sinf`/`cosf`. Observations, masks, rewards, end flags and the full `Env` state matched the CPU library exactly: 0 mismatches over 204.8M lane-steps and 384,541 episode resets, 1,048,576 generated worlds, and a policy-driven PPO rollout whose actions, rewards and dones hash identically.
* **Simulator-only throughput** (random legal actions): 1.2M / 4.4M / 15.2M / 22.3M env-steps/s at 4k / 16k / 64k / 256k envs with the verbatim code. A 20-line change to `light.c` (refresh only the observation window, plus a leaner queue init) raises this to **2.6M / 9.2M / 30.0M / 54.4M**. The same patch makes the **CPU library 2.3× faster** at 16 threads (3.95M → 9.12M steps/s).
* **End-to-end PPO does not get a dramatic step change, because the learner is the wall.** On one MI350X the measured lean-PPO numbers (4 epochs, minibatch 32768, no KL early stop) are:
  * CPU sim with 16 threads: 347k steps/s. The repo's own `train()` with the same settings gives 312k.
  * GPU sim: **483k at 4096 envs, 619k at 16k, 667k at 64k**, then **985k at 64k with `torch.compile`**.
  * The learner alone caps out at **≈0.81M steps/s eager** and **≈1.18M compiled** for 4 PPO epochs. With 1 epoch the measured end-to-end rate is 2.07M steps/s, but that is a hyperparameter change that has to be validated for sample efficiency.
* **Recommendation:** do not rewrite the simulator. Instead:
  1. Land the light-window patch (CPU win today, about 1 day).
  2. Adopt the **verbatim-core HIP backend** (`GpuVec`) as an optional collection device (about 1–1.5 engineer-weeks to productionise), with a CPU/GPU parity job in CI.
  3. Spend the next effort on the learner: `torch.compile`/bf16, epochs × minibatch tuning, and async collection.

  A tensorised JAX/torch rewrite (3–6 weeks, two simulators to keep in sync) would buy simulator throughput that the learner cannot use.

## 1. Portability analysis of the C core

| Aspect | Finding | Consequence on GPU |
|---|---|---|
| State | `Env` = 38,712 B, POD, no pointers (`tl_state_bytes`). The C11 struct layout is identical under hipcc C++ (checked: `sizeof(Env)`, `sizeof(Obs)` and field-wise compares). | 64k envs = 2.5 GB, 256k = 10.1 GB, 1M = 38.7 GB of 252 GB. Memory is not a constraint. Snapshot transfer is a plain 38.7 KB copy. |
| Language | C11 compiles as HIP C++ without edits. The only non-portable items are `snprintf` (messages) and libm trig. Clang implicitly promotes the `static const` tables to device constants. | Wrapper `gpusim_core.h` `#include`s the `.c` files unchanged. |
| Control flow | Per-env scalar code, branching on the action (72 actions: mine/place/craft/combat), mobs, physics. | Wave divergence is real but tolerable on the step path (`env_step` 1.1 ms for 64k envs after the light patch). |
| Lighting | `light_recompute` memcpys the full 12 KB `terrain_light → light` on every move, then runs a radius-3 BFS. `light_tile_changed` zero-initialises a 26 KB `LightQueue` on every opacity-changing edit (the aggregate initialiser zeroes the whole ring). | This was the largest GPU cost: 3.75 ms of 9.1 ms `env_step` at 256k envs. It is also a large CPU cost (see §3). Fix: refresh only the 11×10 window that is ever read. |
| Stack | Function-local arrays: `light_reference` 74 KB, `LightQueue` 26 KB → kernel scratch 74–100 KB/lane, 120 VGPRs, occupancy 4 waves/SIMD. | Works on MI350X. A future core change that adds big stack arrays would hurt. |
| Worldgen / reset | ~95 µs/world on one CPU core (about 100 step-equivalents). On GPU one call has ~40 ms latency; batched throughput is ~0.6M worlds/s. | In-kernel autoreset is **5–7× slower** (wave stalls on the slowest lane), measured below. Resets must come from a **pre-generated pool** (a coalesced 38.7 KB copy per finished lane). |
| RNG | Per-env PCG32 stored in `Env`, integer-only. | Bit-exact for free. |
| Floating point | The obs status uses `/` and `sqrtf`. Worldgen uses `sinf`/`cosf`. | Needs `-ffp-contract=off` and correctly rounded div/sqrt (both default-safe flags here). **ROCm's ocml `sinf`/`cosf` differ from glibc on 1.1–1.5% of inputs → 198 of 1,048,576 worlds (0.019%) differed.** A device port of glibc 2.39's FMA-variant `sinf`/`cosf` (`glibc_sincosf.h`) is bit-identical on all 2.25e9 floats with \|x\|<128 → 0 differing worlds. |
| Mobs / chests | Fixed arrays (8 mobs, 10 chests), bounded loops. | No issue. |

**Blockers found:** none hard. Two soft ones:
* Trig determinism, solved as above.
* Reset divergence, solved with the pool.

The libm dependence also affects the CPU library itself. macOS libm `sinf` differs from glibc's on 506,452 of the 2.25e9 inputs (`cosf`: 100,842), so Mac-built and Linux-built worlds are probably not identical for a small fraction of seeds. That is an [INFERENCE] from the trig-level measurement; worlds were not compared on the Mac.

## 2. Prototype: verbatim core as HIP device code

Files (originally under `~/Projects/RL-gpusim`; now `perf/gpusim/` in branch perf):

| File | Purpose |
|---|---|
| `gpusim_core.h` | The wrapper (pragma, device-only `snprintf`/trig remap). |
| `gpusim_kernels.h` | Kernels: step, step+mark, reset, pool reset, encode, sampler. |
| `gs_main.hip` | Standalone parity/benchmark driver; loads the repo's `libterraria.so` with `dlopen` as the oracle. |
| `gs_lib.hip` | ctypes launcher used from PyTorch. It shares torch's HIP runtime: same `libamdhip64.so.7` SONAME, buffers are torch tensors, launches go on torch's stream. |
| `pipeline.py` | Transfer, inference and learner benchmarks, plus an end-to-end lean PPO loop with a `GpuVec` backend. |
| (light-window patch) | Now `src/light.c` in this branch (commit 6871cde). |

`GpuVec` reproduces `VecTerraria`'s seed contract:
* Lane i starts with seed `s+i`.
* The k-th finished lane (lane order within a step, steps in order) gets seed `s+n+k`.
* World k lives in pool slot `k % pool_n`; slot indices come from `cursor + cumsum(ends) - 1` with no host sync.
* The pool is refilled by batched device worldgen.

### 2.1 Parity evidence (all bit-exact, random actions: uniform over legal plus x% uniform over all 72)

| Test | Scale | Result |
|---|---|---|
| Step path, CPU worldgen + 38.7 KB blob upload (hybrid) | 4096 envs × 20,000 steps = 81.9M lane-steps, 131,941 resets, 10% illegal | obs/mask/reward/end mismatches **0**; full `Env` state (all fields except `msg`) **0/90,112** |
| Same, 50% illegal actions | 40.96M lane-steps, 120,659 resets | **0** / state 0/49,152 |
| Full GPU (device worldgen for resets) | 81.9M lane-steps, 131,941 resets | **0** / state 0/90,112 |
| Full GPU + light-window patch vs **unmodified** CPU lib | 81.9M lane-steps, 131,941 resets (plus 40.96M at 50% illegal via blob) | **0** (the `light` array outside the view window is intentionally not compared) |
| Worldgen only, seeds 10,000,000–11,048,575 | 1,048,576 worlds | exact trig: **0** differing; ROCm ocml trig: 198 worlds (0.019%), 18,975 tiles |
| Trig, exhaustive \|x\|<128 | 2,248,146,944 floats | glibc-port (FMA) sin 0 / cos 0; non-FMA port 12/22; ocml 25.6M/34.0M |
| End-to-end: PPO rollout (TargetActorCritic sampling), 1024 envs × 1536 steps, 2,612 resets | SHA-256 of actions/rewards/dones | GPU sim = CPU sim: `2cadb52caf5eef48` |
| End-to-end: 4 PPO iterations (3 learner updates in between), 4096 envs | episodes / reward sum | CPU sim 2972 / 28020.0 = GPU sim 2972 / 28020.0 |

An earlier run with ocml trig (`logs/parity_4096x20000.log`) shows how a single differing world propagates: obs diffs appear after the affected lane's next reset. That is why the trig port is required, not cosmetic.

### 2.2 Simulator throughput on GPU 7 (`gs_main bench N S pool 256`; random legal actions via a device sampler; pool resets; outputs are raw `Obs` + masks + rewards in device memory)

| Envs | Verbatim core (steps/s) | + light-window patch | µs per batch step (patched) |
|---:|---:|---:|---:|
| 4,096 | 1.17M | **2.56M** | 1,598 |
| 16,384 | 4.39M | **9.19M** | 1,784 |
| 65,536 | 15.2M | **30.0M** | 2,183 |
| 262,144 | 22.3M | **54.4M** | 4,818 |

Adding the float32 one-hot encode kernel (the binding's 2963-float layout, coalesced): 25.4M steps/s at 64k envs and 39.7M at 256k (patched build).

Reset strategy matters a lot. Verbatim build at 16,384 envs:

| Strategy | Steps/s |
|---|---:|
| No resets | 5.58M |
| **Pool copy** | **5.18M** |
| In-kernel autoreset | 1.08M |
| Separate compacted worldgen kernel per step | 0.68M |

Patched build at 65,536 envs: in-kernel autoreset 4.23M vs pool 30.0M.

Per-phase profile in ms per batch step at 65,536 / 262,144 envs:

| Build | `env_step` | `env_obs` | `env_action_mask` | `light_recompute` alone |
|---|---:|---:|---:|---:|
| Verbatim | 3.14 / 9.09 | 0.39 / 1.99 | 0.35 / 1.33 | 1.18 / 3.75 |
| Patched | 1.11 / 1.76 | 0.39 / 1.98 | 0.35 / 1.32 | 0.25 / 0.58 |

At 256k envs, obs and mask writes now dominate. These are scattered per-lane 2144/72-byte records. An LDS-staged coalesced write-back was tried (`k_step_mark_coop`) and was **slower**: 20M steps/s at 64k, and occupancy collapsed at 256k. It is kept only as a documented negative result.

The **GPU sim is latency-bound below ~16k envs.** One batch step takes ≥1.6 ms however few lanes there are, because a GPU lane executes one env step ~2000× slower than a CPU core. At the project's current 4096 envs/run it is 2.6M steps/s, which is fast enough to stop being the bottleneck but well short of 1B/s-class numbers.

## 3. Step-ups on the current CPU-sim pipeline (measured on GPU 7)

### (0) Light-window patch, CPU side

Measured with `cpu_bench` on the training entry point `tl_batch_step_flat`, random legal actions:

| Configuration | Before | After |
|---|---:|---:|
| 1 thread, 256 envs | 0.957M steps/s | 1.062M (+11%) |
| 16 threads, 4096 envs | 3.95M steps/s | **9.12M (2.3×)** |

The 12 KB-per-step memcpy over a 158 MB working set is cache-bound with many threads. This is the cheapest win in the whole report. The renderers (`render.c`, `px_render.c`) read the full light map, so they must recompute it on demand.

### (a) Compact observations

H2D transfer per batch step (pageable `torch.as_tensor(np).to(dev)`, as `ppo_agent` does):

| Envs | float32 one-hot | Compact (uint8 tiles + light + f32 status, 2142 B/env) | Compact → float32 expand on GPU |
|---:|---:|---:|---:|
| 4096 | 46.3 MB, 0.89 ms | 8.4 MB, 0.17 ms | 0.14 ms |
| 8192 | 92.5 MB, 1.76 ms | 16.7 MB, 0.33 ms | 0.25 ms |

Pinned memory made no difference. This saves ~0.6 ms of the ~6.1 ms per-step CPU-pipeline collection, roughly +5% end-to-end. Storing the rollout compactly also cuts rollout memory 5.5× (16k envs: 30.4 → 11.5 GB peak), which is what makes 64k+ envs fit.

### (a′) Where the CPU pipeline's collection time actually goes

Lean loop, 4096 envs, 16 sim threads, 6.1 ms per batch step:
* `VecTerraria.step`: 2.8–3.1 ms. The native batch step is ~1.0 ms (`cpu_bench`); the rest is serial Python per-lane `reset` + `action_mask` + `_info`, and ~95 µs C worldgen per finished lane.
* H2D of obs, mask and reward: 1.1–1.2 ms.
* Inference ≈ 0.8 ms.

Moving autoreset into C and parallelising it (a worldgen pool on the C side) is worth ~1.5–2 ms per step [estimate from those components].

### (b) Overlapping simulation with inference

Not built. Estimate from the breakdown above: with two env halves, CPU stepping of half A overlaps H2D + inference of half B, hiding about min(2.9, 2.0) ms ≈ 2 ms of 6.1 ms → collection −30%, end-to-end about +15% at a 52% collection share [estimate]. With the GPU sim this is moot: collection is already only 10–33% of the time.

### (c) HIP graphs and `torch.compile`

| Workload | Eager | HIP graph | `torch.compile` |
|---|---:|---:|---:|
| Policy act, 4096 envs | 0.775 ms | 0.494 ms | 0.265 ms |
| Policy act, 16k envs | 1.62 ms | 1.55 ms | 0.83 ms |
| Policy act, 64k envs | 6.41 ms | 6.30 ms | 3.55 ms |
| PPO minibatch update, 32768 samples (fwd+bwd+clip+Adam) | 10.08 ms | — | 6.94 ms (bf16 autocast: 7.70 ms) |

Graphs only help at 4096 envs; `torch.compile` fusion gives about 2× on inference and 1.45× on the learner. With 4 epochs the learner ceiling is ≈0.81M env-steps/s eager and ≈1.18M compiled. In end-to-end runs (below) compile gives +43% at 16k envs and +48% at 64k envs. Trajectories then differ from eager in the last bits (reward sum 118,101 vs 117,415), as expected.

### (d) Async actor-learner (APPO / V-trace)

Not built. Upper bound = 1/(1 − collect share):
* CPU-sim pipeline (52% collection): up to ~2.1× (≈700k) if collection fully overlaps the update.
* GPU-sim pipeline (10–33% collection): at most 1.1–1.5×.

The cost is policy lag, which needs V-trace/IS correction and re-validation of learning curves [estimate]. It pays off mainly if the CPU sim is kept.

## 4. End-to-end throughput on one MI350X (measured)

Setup: `pipeline.py e2e`. Same TargetActorCritic(128), losses, Adam, GAE(λ=.99, γ=.999) as `ppo_agent.train`; 4 epochs, minibatch 32768, rollout 128; no KL early stop (worst case for the learner); first iteration excluded.

Calibration: the repo's own `train()` on GPU 7 with 4096 envs and 16 sim workers gave 312k steps/s (50% collection). The project's phase-1 baselines are 377k (4096 envs) and 429k (8192 envs), using 64–96 CPU threads.

| Configuration | Collection steps/s | End-to-end steps/s | Collect share | Peak GPU mem | Bottleneck |
|---|---:|---:|---:|---:|---|
| CPU sim (repo lib), 4096 envs, 16 threads | 670k | **347k** | 0.52 | 9.8 GB | Python resets + H2D + learner |
| GPU sim (patched), 4096 envs | 1.46M | **483k** (+39%) | 0.33 | 12.3 GB | Learner |
| GPU sim, 8192 envs | 2.51M | **565k** | 0.23 | 18.4 GB | Learner |
| GPU sim, 16,384 envs | 3.99M | **619k** | 0.15 | 30.4 GB | Learner |
| GPU sim (verbatim, unpatched), 16,384 | 2.78M | 576k | 0.21 | 30.4 GB | Learner |
| GPU sim, 16,384, compact rollout | 4.06M | 619k | 0.15 | 11.5 GB | Learner |
| GPU sim, 65,536, compact rollout | 7.01M | **667k** | 0.10 | 27.1 GB | Learner (11.4 s/iteration) |
| GPU sim, 16,384, `torch.compile` | 4.64M | **884k** | 0.19 | 30.1 GB | Learner |
| GPU sim, 65,536, compact, `torch.compile` | 8.80M | **985k** (2.6× phase-1 4096 baseline) | 0.11 | 26.8 GB | Learner |
| GPU sim, 65,536, compact, **1 epoch** (hyperparameter change) | 6.98M | **2.07M** | 0.30 | 27.1 GB | Learner + inference |

Projection: with the GPU sim and the learner unchanged, end-to-end saturates at ~0.65–0.70M (eager) or ~1.0–1.1M (compiled) steps/s per GPU. That is 1.6–2.6× the 377–429k baseline. In every GPU-sim row the new bottleneck is the PPO update: 4 passes over 2963-wide float inputs at ≈3.2M samples/s eager.

Going further needs learner-side changes:
* fewer epochs or larger minibatches (needs sample-efficiency validation);
* bf16;
* a cheaper input path (tile embedding lookup instead of one-hot × Linear) [estimate].

A second structural gain is CPU freedom: the GPU sim needs ~1 core per run instead of 64–96 threads. Eight concurrent runs (one per GPU) would no longer compete for the CPU, which capped the phase-1 multi-run aggregate at 602k [INFERENCE; multi-GPU not measured, by constraint].

## 5. Findings table

| Approach | Measured sim steps/s (GPU 7) | Parity | End-to-end (measured / projected) | Effort (eng-days) | Risks |
|---|---|---|---|---|---|
| **A. Verbatim C core as HIP, one env/thread, pool resets** (prototype done) | 1.2M / 4.4M / 15.2M / 22.3M (4k/16k/64k/256k) | Bit-exact (§2.1) | 576k at 16k envs | 5–8 to productionise (package `GpuVec` with the `VecTerraria` contract incl. `final_obs`/infos via a small info kernel, build/CI parity job, port the numpy-side extras: shapers, novelty, archive restart via blob copy) | Needs ROCm/hipcc at build time. Core changes must stay device-safe: no new host-only libc calls, no big stack arrays, no pointers in `Env`. CI parity guards drift; single source means no second simulator. |
| **A + light-window patch** | **2.6M / 9.2M / 30.0M / 54.4M** | Bit-exact for obs/mask/reward/end vs the unmodified lib | **483k (4k) – 667k (64k)**; with compile 884k–985k | +1 (patch, renderer full-map recompute, selftest) | `Env.light` outside the view becomes a cache; anything reading it must call a full recompute. Also speeds the CPU lib 2.3× at 16 threads. |
| B. Hybrid: GPU step, CPU worldgen + blob upload | Same step path as A. CPU worldgen 95 µs/world/core → ~10k worlds/s/core (a 600-step random policy needs ~1 core per 6M steps/s). | Bit-exact (81.9M + 41M steps) | ≈ A | 4–6 | Avoids the trig-port dependency; costs CPU cores and H2D of 38.7 KB per reset. |
| C. Tensorised rewrite (JAX/torch, SoA) | Not built. Plausibly 10–100× A's simulator throughput [estimate] | Must be re-established from scratch | Capped by the learner (~1.2M compiled, 4 epochs): ≤ +20% over A+compile | 15–30 | Second simulator to maintain; fidelity drift; lighting BFS, trees and worldgen are awkward to vectorise. Not justified now. |
| D. CPU pipeline: light patch + C-side autoreset + compact obs (+ overlap) | CPU sim 9.1M steps/s at 16 threads (patched) | Unchanged (CPU) | [estimate] collection 6.1 → ~3 ms/step at 4096 → ~470–520k end-to-end | 3–5 | Low; Python API changes for the C autoreset. |
| E. `torch.compile` (inference + learner) | — | Bitwise drift vs eager (expected) | +43–48% end-to-end measured with the GPU sim | 1–2 | Recompiles on shape changes; validate numerics. |
| F. APPO / V-trace async | — | — | ≤1.1–1.5× with the GPU sim; ≤2× with the CPU sim [estimate] | 5–10 | Policy lag; learning dynamics change. |
| G. Fewer PPO epochs / bigger minibatch | — | — | 2.07M with 1 epoch at 64k envs (measured speed only) | 1 + experiments | Sample efficiency: must be validated by learning curves. |

## 6. Recommendation and staged plan

The simulator is no longer the dominant cost once it moves off the CPU, and a straightforward verbatim port already moves it off. Do not invest in a tensorised rewrite; invest in the learner.

1. **Week 0 (≤1 day): land the light-window patch in the core.** This is a CPU win independent of any GPU work (2.3× at 16 threads). Include the renderer full-map recompute and parity tests against the old lib (obs/mask/reward identity, as done here).
2. **Week 1: productionise backend A** as `terraria_lite.gpu` (optional extra, built with hipcc):
   * a `GpuVec` matching `VecTerraria`: seeds, `final_obs`, infos;
   * the device trig port, plus making the core itself call the same deterministic `sinf`/`cosf` on CPU so Mac, Linux and GPU agree;
   * a CI parity job (`gs_main parity …`, `worldparity …`) on a GPU runner.

   Default to compact rollout storage.
3. **Week 2: learner.** Turn on `torch.compile` for the encoder/actor and the update (measured 1.45–2×), try bf16 autocast, then run a sample-efficiency study over epochs × minibatch × envs (e.g. 16k–64k envs, 1–2 epochs). The speed side is measured above: 1 epoch gives 2.07M steps/s.
4. **Only if learning-curve studies favour very large batches:** revisit async collection (APPO) or a tensorised simulator. Neither is worth it while the update costs ≥1.2 µs/sample/epoch.

Throughput claims in this report are for a near-uniform random policy, with ~600-step episodes. A trained policy (longer episodes, more mining/crafting) changes the reset rate and the divergence pattern, which is [INFERENCE] likely a modest effect on the pool-based design.

## 7. Reproduce (eg18, branch perf, from perf/gpusim)

```sh
cd ~/Projects/RL-perf && taskset -c 368-383 make lib     # this branch's CPU library
cd perf/gpusim && taskset -c 368-383 make all             # gs_main, gs_main_ocml, trigtest, libgpusim.so, cpu_bench
export HIP_VISIBLE_DEVICES=7
MAIN=$HOME/Projects/RL/python/terraria_lite/libterraria.so   # unmodified main-branch library
MINE=../../python/terraria_lite/libterraria.so
sh logs/run_p0_parity.sh      # all of the following, writing logs/p0_*.log:
#  ./gs_main cpuparity $MINE $MAIN 4096 10000 10 1000       branch CPU lib vs main lib
#  ./gs_main parity $MAIN 4096 20000 10 1000 1              GPU (device worldgen) vs main lib
#  ./gs_main parity $MAIN 4096 10000 50 1000 0              GPU, CPU-blob resets, 50% illegal actions
#  ./gs_main parity $MINE 4096 10000 10 1000 1              GPU vs branch lib
#  ./gs_main worldparity $MAIN 10000000 1048576             1M worlds
./gs_main_ocml worldparity $MAIN 10000000 1048576          # ROCm ocml trig: ~0.02% of worlds differ
./trigtest 128                                             # exhaustive sinf/cosf comparison
sh sweep.sh > logs/sweep.log 2>&1                          # simulator + pipeline microbenchmarks
# GPU-sim end-to-end lean PPO loop (section 4), and the CPU-vs-GPU rollout digest:
PY=~/Projects/RL/.venv/bin/python
for s in gpu cpu; do taskset -c 368-383 $PY pipeline.py e2e --sim $s --envs 1024 --rollout 1536 --minibatch 65536 --epochs 1 --iters 1 --digest --pool 4096; done
taskset -c 368-383 $PY pipeline.py e2e --sim gpu --envs 65536 --store compact --iters 4
```

Parity compares Env.light only inside the observation window, the only part the simulator
keeps exact after the light-window patch. Caveats on the measurements:
* CPU numbers use the SMT siblings 368-383 while other jobs ran on the machine.
* `bench` throughput uses a device-side uniform-legal sampler, not a policy network.
* The end-to-end loop omits `ppo_agent`'s optional extras (shapers, novelty, archive, telemetry).
