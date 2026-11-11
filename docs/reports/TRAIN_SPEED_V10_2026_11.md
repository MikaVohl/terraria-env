# Training speed on v10 (2026-11-10, branch `train-speed`)

Goal: shorten wall-clock time to a given score for PPO on Terraria-Lite v10. Work order:

1. Measure where a production-like run spends its time.
2. Speed up both the simulator and the learner.
3. Accept changes only if they are exact. Algorithm changes count only after a learning check.

## Setup

- **Machine and placement**
  - eg18, **GPU 4 only** (MI350X).
  - torch 2.13.0+rocm7.1 from `~/Projects/RL/.venv`.
  - Checkout `~/Projects/RL-trainspeed`.
  - CPUs pinned with `taskset`: **136-159** for a single run. The second run of a pair, and the CPU-only parity jobs, used **160-183**. All of these cores are on NUMA node 1, the same node as GPU 4.
  - GPUs 0-3 and 5-7 ran other agents' jobs during the measurements.
- **Game**: `variants/v10` at `4ef5afa`, built with `make -C perf/v7 V7=$PWD/variants/v10 BUILD=build-v10 VARIANT="-DINV_LOG=1"`.
- **Arm**: the production `v10_shaped_g9999` arm with the `gpu` layout, as `tools/explore_screen.py` builds it (argv from `perf/v10/arm_argv.py`):
  - 1,024 envs × 128 steps, so 131,072 steps per PPO iteration.
  - 4 epochs × 16 minibatches.
  - targets net; `--compile --bf16 --fused-adam --compile-all --async-evaluation`.
  - frontier potential 3, novelty .01, unimix .01, γ .9999.
  - Collection and learning on the GPU, `--sim-workers 12 --threads 4`.
  - 128 validation episodes, evaluated on the CPU in a spawned process.
- **Baseline**: the `4ef5afa` Python tree and library, kept on eg18 under `perf/v10/base*`.

## 1. Where the time goes (baseline)

Method:
- `perf/profile_train.py` runs `tools/iterate_ppo.py` unchanged, with timers around every phase.
- The table shows ms per PPO iteration, steady state, 127 iterations, seed 901 (`perf/v10/logs/profile_base_nosync.json`).
- `--sync` (a GPU sync after every phase) gives the same split within 5%. The phases are therefore host-bound and not waiting on queued GPU work.

| Phase | ms / iteration | share |
|---|---:|---:|
| C simulator step (`VecTerraria.step`: 128 batch steps, 12 pool threads, autoreset) | 60.8 | 12% |
| Recipe potential (`RecipePotential.step`, NumPy) | 93.9 | 19% |
| Novelty (`CellNovelty.step`, C tables) | 16.8 | 3% |
| Rest of collection: compiled sampling graph, multinomial, action fetch, 3 H2D uploads, buffer writes, telemetry | 104.7 | 21% |
| GAE | 6.2 | 1% |
| PPO update (64 minibatches: eager bf16 loss around the compiled trunk and actor, backward, clip, fused Adam) | 211.5 | 43% |
| Checkpoint save | 0.04 | 0% |
| **Total** | **494** | **265k steps/s** |

**Validation.** It runs asynchronously while training continues. Only the **final** evaluation sits on the critical path:
- ~38 s in a 64M-step run (`e2e` below).
- ~48 s of the 914 s production run `combo-ab2/v10_shaped_nc_192M-4104`.
- That production run used 201M steps with 2 runs on GPU 7: 232k steps/s, 460 s collection, 406 s optimisation.

**GPU vs host** (`perf/profile_train.py --trace 20`, torch profiler over one iteration, `perf/v10/logs/`):

| Phase | wall (with profiler) | GPU busy | kernels | copies |
|---|---:|---:|---:|---:|
| collection | 372 ms | 54 ms (14.5%) | 7,447 (58 per step) | 256 |
| update | 402 ms | 139 ms (34.5%) | 18,603 (291 per minibatch) | 6 |

**Utilisation.**
- GPU: idle 65-85% of every phase.
- CPU (`/proc` sampling of the process tree, `perf/v10/util_sample.py`, traces in `perf/v10/logs/util_*.jsonl`): ~1.8 busy cores while training alone, ~6 while the async evaluation worker overlaps training, ~4 for the final evaluation alone.
- `amd-smi metric -u` reports 0% `gfx_activity` throughout on this machine, so it cannot be used to measure utilisation.

**Verdict on DECISIONS B3 ("training is network-bound").**
- It is right that the learner is the largest single phase, at 43%.
- It is **not** GPU compute: the network keeps the GPU busy only about 1/3 of the update.
- The run is **host-latency-bound**: kernel launches and Python in the update and in sampling, plus NumPy shaping and the C step, all serialised on one thread. This is also why two runs per GPU nearly double the aggregate throughput.
- The simulator is only 12% of the iteration.

### C profile of the simulator

Taken on the Mac with `sample` (eg18 has `perf_event_paranoid=4`, so `perf` cannot be used there).
- Workload: `tools/sim_throughput` load, 64 lanes, 1 thread, uniform legal actions.
- Build: `-fno-inline`, so that time is attributed to functions. Numbers are inclusive.

| Function | share |
|---|---:|
| `fid_tick` (15 game ticks per action) | 59.7% |
| ↳ `player_tick` (ported player physics) | 21.8% |
| ↳ `mobs_game_tick` → `mob_update` (NPC AI and movement; `fighter_ai` 2.9, `bat_ai` 5.7, `flyer_steer` 1.8) | 22.8% |
| ↳ ↳ `fid_tile_collision` (player and NPCs) | 18.0% |
| ↳ swing / contact (`swing_tick`, `mobs_swing`, `mobs_contact`, `fid_can_hit`) | ~14% |
| `env_obs` (observation encoding; `logf` of INV_LOG 1.6%) | 12.6% |
| `env_action_mask` (`can_place`, `can_mine`, `station_near`) | 12.0% |
| lighting (`light_recompute`, `light_tile_changed`, `light_reference`) | ~5% |
| `env_reset` / worldgen | 2.4% |
| event messages (`SAY` → `snprintf`) | 1.5% |

In the inlined production build the top self-time entries are:
- `env_step` 24% (the inlined player physics, mining and tick loop)
- `mobs_game_tick` 16%
- `env_obs` 11%
- `env_action_mask` 7%
- `mobs_contact` 4%

Batch shape on eg18 (`perf/v10/sim_bench.c`: 1,024 lanes, 12 workers, trainer-shaped autoreset):
- A batch step costs 0.212 ms without resets and **0.585 ms when any lane resets**: one `env_reset` world generation (0.30 ms) runs serially while the other workers wait.
- About a quarter of the batch steps under a random policy contain a reset.

## 2. Changes (all exact)

| # | Change | Files | Exactness evidence | Effect |
|---|---|---|---|---|
| S1 | **Reset prefetch.** `env_reset` keeps only `max_steps` and rebuilds everything else from the seed, so a reset state is a function of `(seed, max_steps)` alone. After each `tl_batch_step_autoreset` call, one background thread generates the next 8 autoreset seeds. A later reset of such a seed becomes an 85 KB `memcpy`. Misses (other seeds, other episode limits, not ready yet) reset in place. `TL_RESET_PREFETCH=0` disables it. | `src/capi.c` | `perf/v10/sim_bench.c`, lockstep parity with the `4ef5afa` library: every obs row, mask, reward, end code, terminal row, info row and reset lane compared byte for byte at every step. **1,024 lanes × 100,000 steps** (23k resets) and **512 lanes × 100,000 steps at 1,500-step episodes** (41.7k resets): identical (`perf/v10/logs/sim_parity.txt`). The same property holds for every variant using `capi.c` (v4/v8/v8fid/v9/v10 `env_reset` are identical in this respect); `tools/v10_noport_parity.py` (v9 vs v10-noport, 400k steps) still passes. | Trainer-shaped sim, eg18, 12 workers: 0.282 → **0.212 ms per batch step** (**3.63M → 4.82M steps/s, 1.33×**). Steps with a reset: 0.585 → 0.226 ms. In training: sim phase 60.8 → ~52 ms/iteration. |
| S2 | `env_obs`: skip `logf` for empty inventory slots. `logf(1)/logf(1000)` is +0 (C99 F.9.3.7), already written by the `memset`. | `variants/v10/src/obs.c` | Same parity runs; v10 selftest 193/193 (incl. the scripted EoC gate), `fid_test` 102/102, `check_v10.py` pass | Raw single-thread throughput (`sim_throughput`, Mac): 0.604M → 0.617M steps/s (+2%) |
| L1 | Recipe potential: widen only the 3 status columns the boss goals read, not the whole 1,090-float status row of every lane | `python/terraria_lite/potential.py` | `perf/check_shaping.py` (dense reference, all three modes, live compact and flat, 512 × 1,500 steps): OK | Potential 0.78 → 0.53 ms per step (Mac) |
| L2 | Recipe potential: two-level memo. The rows × recipes × items term depends only on the capped inventory and visible stations. It is cached per lane and recomputed only when those change. A lane that moved (y feeds the altar goal) or changed achievements recomputes only the cheap goal tail. Measured: 205 stale rows per step, 196 of them y-only. | `potential.py` | Same `check_shaping.py` run; values bit-identical | Potential 0.53 → 0.26 ms per step (Mac). In training: 93.9 → 61 ms/iteration |
| L3 | Rollout loop: a step's shaping runs **after the next step's sampling forward is launched**, so the host computes it while the GPU samples. The potential's numerics (`RecipePotential.finish`, after a `prepare` decode stage that copies what it needs) run on one worker thread during the next C step, which releases the GIL. The reward is assembled with the same additions in the same order before GAE. Archive restarts and SIL keep the old in-order path. | `python/terraria_lite/ppo_agent.py`, `potential.py` | `perf/bench_trainer.py` SHA on the deterministic exact path with the arm's shaping (`perf/v10/fingerprint.sh`: frontier potential 3, novelty .01, unimix .01, γ .9999, 1,024 envs, 6 iterations): **`10e562162c02ceda` for base, for every intermediate state, and for the final tree, with both libraries** | Potential on the critical path: 61 → 14.5 ms/iteration (the 59 ms `finish` overlaps the simulator) |

**Collection after all changes** (`perf/v10/logs/profile_new2_nosync.json`), ms per iteration, before → after:

| Phase | before | after |
|---|---:|---:|
| sim | 60.8 | 52.3 |
| potential (critical path) | 93.9 | 14.5 |
| novelty | 16.8 | 17.3 |
| rest | 104.7 | 100.9 |
| **collection total** | **276** | **185** |

The update is unchanged at 216 ms. Steady state: **265k → 322k steps/s (1.21×)**, solo, first iteration and evaluation excluded.

**End to end** (`perf/v10/e2e.sh`): 64M steps, evaluations at 32M and 64M (async), seed 901.

| Configuration | base `4ef5afa` | this branch | factor |
|---|---:|---:|---:|
| solo, wall incl. final evaluation | 294.5 s | 249.4 s | **1.18×** (steps/s 1.22×) |
| solo, training steps/s (`summary.json` `sps`) | 263k | 320k | |
| 2 runs sharing GPU 4 (production packing), mean wall | 302.5 s (300.6, 304.4) | 247.6 s (248.8, 246.4) | **1.22×** (steps/s 1.26×) |
| 2 runs sharing GPU 4, mean training steps/s | 255k (256k, 254k) | 322k (321k, 322k) | |

Each run of a pair is as fast as a run alone, so the GPU is not the shared bottleneck at 2 runs per GPU (each run has its own 24 cores here).

All changes are bit-exact, so the score at matched steps is unchanged by construction. The max config itself is not run-to-run deterministic on ROCm (perf/REPORT.md §7.2), so score differences between the base and branch e2e runs are noise.

## 3. Tried and rejected

| Idea | Result |
|---|---|
| Dynamic lane scheduling in the C pool (workers claim 4-lane chunks from an atomic counter instead of a static interleave) | Parity-exact, but on eg18 the steps without resets went 0.213 → 0.239-0.245 ms (**12% slower**). A static interleave keeps each lane's 85 KB `Env` in the same core's cache. On the Mac it was 8% faster. Reverted. |
| **HIP graph capture of the whole minibatch step** (loss, backward, clip, fused Adam; `perf/v10/update_probe.py`) | (1) Capturable fused Adam needs a tensor lr (float32 only) and is **not bit-identical** to the production optimizer after 3 steps. (2) Capture fails under hipBLASLt: `operation not permitted when stream is capturing`, then the process hangs. (3) With `TORCH_BLAS_PREFER_HIPBLASLT=0` the capture succeeds, but replay aborts with `HSA_STATUS_ERROR_INVALID_PACKET_FORMAT`, the same failure perf/REPORT.md §1 saw for sampling. Not usable on torch 2.13 / ROCm 7.1. |
| Compiling the bf16 minibatch loss as one graph (would cut the 291 kernels per minibatch) | Excluded on purpose: this is the GPU-sharing gradient-corruption trigger (`docs/reports/GPU_SHARING_CORRUPTION_2026_10.md`) |
| **`--minibatches 8`** (16,384-row minibatches; changes the algorithm) | Learning check at matched steps (134M, seeds 901/902, paired on GPU 4): **23.5 / 25.1% vs control 28.0 / 27.7%**. Also behind at matched wall-clock (394 s vs 477 s per run, but at 371 s the control already had 25.2%). **Rejected.** |

## 4. Learning check of `--envs 2048 --rollout 64`

This changes the algorithm. The batch (131,072) and minibatch (8,192) sizes stay the same.

Setup (`perf/v10/learning_check.sh`):
- 134M steps, seeds 901 and 902.
- The arm and a second control run side by side on GPU 4.
- Evaluations every 33.5M steps on validation worlds 23000001..+127.

| Steps | ctl (pair with mb8) 901 / 902 | ctl2 (pair with e2048) 901 / 902 | **e2048** 901 / 902 |
|---|---|---|---|
| 33.5M | 17.9 / 16.9 | 16.2 / 16.2 | 17.7 / 17.3 |
| 67.1M | 20.6 / 21.8 | 18.4 / 18.6 | 25.1 / 22.9 |
| 100.7M | 25.2 / 26.5 | 22.7 / 24.3 | 25.0 / 24.2 |
| 134.2M | 28.0 / 27.7 | 26.1 / 25.9 | 27.6 / 26.6 |
| wall per run (paired) | 477 / 469 s | 464 / 465 s | **426 / 416 s** |

Findings:
- **No score loss at matched steps**: within the control-to-control spread of ~2 points, and ahead at 67M.
- About **1.10× faster**: fewer, wider sampling calls, and the C step parallelises better at 2,048 lanes.
- This is a **recommendation, not adopted**. Two seeds at 134M are weak evidence. Confirm with ≥3 seeds at the 1B standard budget before switching arms; new arms must not be compared bit-for-bit with old ones.

## 5. Further ideas, ranked by estimated gain

| # | Idea | Estimated gain | Kind |
|---|---|---|---|
| 1 | **Fewer update launches**: a fused hand-written fp32 tail (masked log-softmax with unimix, log-prob/entropy, PPO objective) as one eager kernel or a Triton kernel with a hand-written backward. 291 → ~60 kernels per minibatch, while avoiding Inductor's compiled bf16 backward (the corruption trigger). | update 216 → ~150 ms, **~1.15×** | equivalent math, different rounding; needs a learning check and a sharing soak like the corruption report's |
| 2 | **Graph capture** once ROCm fixes `INVALID_PACKET_FORMAT` and hipBLASLt capture | update → ~140 ms (GPU-busy bound), sampling 0.8 → ~0.4 ms per step: **1.3-1.4×** | equivalent |
| 3 | Final evaluation off the critical path: let the queue start the next job while the last async evaluation finishes on its own cores (`tools/gpu_queue.py`) | −40-50 s per run (~5% of a 200M run) | exact |
| 4 | `--envs 2048 --rollout 64` (§4) | ~1.10× | algorithmic, recommended for a proper study |
| 5 | Move novelty into the prepare/finish split as well (decode on the main thread, C table update on the worker) | ~10 ms/iteration (2-3%) | exact |
| 6 | Simulator micro-work, each exact but small: lazy `SAY` formatting (1.5% of the sim, if `tl_message` formats on demand), a span-based `fid_tile_collision` without per-tile bounds checks, action-mask caching of `station_near` | ≤10% of the sim = ≤1.3% end to end | exact |
| 7 | `FID_TICKS` < 15 or a coarser physics port | the sim scales almost linearly with ticks per action | **game rule change: out of scope**, listed only for completeness |

Two runs per GPU remain the right packing: each run is host-latency-bound, at ~1.8 busy cores and a GPU idle most of the time.

## Reproduce (eg18, checkout root)

```sh
make -C perf/v7 V7=$PWD/variants/v10 BUILD=build-v10 VARIANT="-DINV_LOG=1"
gcc -O2 perf/v10/sim_bench.c -o /tmp/sim_bench -ldl
taskset -c 136-159 /tmp/sim_bench -n 1024 -w 12 -s 2000 perf/v7/build-v10/libterraria.so          # sim speed
taskset -c 160-183 /tmp/sim_bench -n 1024 -w 16 -s 100000 OLD/libterraria.so perf/v7/build-v10/libterraria.so   # parity
sh perf/v10/profile_run.sh NAME [--sync | --trace 20] -- [extra flags]      # phase profile, util trace
sh perf/v10/fingerprint.sh base=OLD_TREE/python new=python                 # trainer SHA (exact path)
PYTHONPATH=python TERRARIA_LITE_LIB=... python perf/check_shaping.py --envs 512 --steps 1500
sh perf/v10/learning_check.sh ctl "" e2048 "--envs 2048 --rollout 64"
sh perf/v10/e2e.sh
```

Logs: `perf/v10/logs/` (profiles, traces, parity, fingerprints, learning-check and e2e lines).
