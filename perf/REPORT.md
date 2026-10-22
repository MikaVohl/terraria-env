# Trainer performance work (branch `perf`)

All measurements are on eg18 using **GPU 7 only** (MI350X; torch 2.13.0+rocm7.1 from `~/Projects/RL/.venv`) and at most 16 CPU threads (`taskset -c 368-383`, the SMT siblings of cores 176-191). Live experiments were running on GPUs 0-6 at the same time.

Unless stated otherwise, "realistic settings" means the real trainer (`ppo_agent.train`) configured like `tools/explore_screen.py`'s `pot_e1024`/`pot_e4096` arms:
- targets model, potential shaping 3
- γ .999, GAE .99, entropy .03
- rollout 128, 4 epochs, 16 minibatches
- collection and learning both on the GPU

Throughput is the steady-state rate with the first iteration excluded (`perf/bench_trainer.py`). Every exact change is backed by a SHA-256 over the final parameters plus episode telemetry.

The GPU-simulator feasibility study that preceded this work is in `perf/gpusim/REPORT.md`.

## Summary

| Configuration (v4) | 1024 envs | 4096 envs | Exact? |
|---|---:|---:|---|
| main (before) | 109k steps/s | 105k steps/s | — |
| perf, all flags off (light window + potential memo) | 203k | 269k | **bit-identical** to main |
| + `--native-autoreset --compact-obs` (**exact config**) | **244k** (2.2×) | **415k** (4.0×) | **bit-identical** to main |
| + `--compile --bf16 --fused-adam` (**max config**) | **311k** (2.9×) | **592k** (5.6×) | different rounding; learning check passed |

The same holds on the v7 game: the live v7 library gives 103k / 93k, the exact config 235k / 386k, and the exact config with the light-window v7 library 241k / 406k. All v7 rows are SHA-identical to the live v7 runs.

For fleets, run **2 runs per GPU**. With the max config at 2048 envs that gives about **781k steps/s per GPU** in aggregate. A third and fourth run on the same GPU lowers the aggregate. A run needs only 2-4 CPU cores.

**Round 2 (§7, v7 with frontier potential and novelty shaping).**
- Exact changes: C cell decode and C novelty tables, fewer host syncs, and `--async-evaluation`. They take the shaping arms from 254k to 324k steady steps/s and cut a 32M-step run with 4 evaluations from 192 s to 117 s.
- Opt-in `--compile-all`: reaches 440-476k. Its learning check passed.

## 1. Changes, exactness and measured effect

Columns are steps/s at 1024 / 4096 envs, realistic settings. The "Before" column shows the row the change is applied on top of. Logs are in `perf/logs/`.

| # | Change (commit) | Flag | Exactness | Before | After | Notes |
|---|---|---|---|---|---|---|
| P0 | Light window: `light_recompute` refreshes only the 11×10 observation/glow box; `light_full()` serves renderers/oracles (6871cde) | always on | Obs, mask, reward and end identical to main. CPU 40.96M lane-steps / 65,684 resets; GPU 81.9M lane-steps; 1M worlds; all 0 diffs | main 109k / 105k | default 203k / 269k (P0 + potential together) | CPU sim alone: 16 threads × 4096 envs 3.95M → 9.12M steps/s; 1 thread +11% |
| — | Potential shaping memoised per lane; `stations_visible` without gather (d97c10a) | always on | Bit-identical: `perf/check_potential.py`, 1.9M nonzero shaping rewards. Trainer SHA = main | (see row above) | | Was the largest collection cost: 2.1 ms (1024 envs) and 13.6 ms (4096 envs) per step, now 0.4 / 1.4 ms |
| b | Native C autoreset (`tl_batch_step_autoreset`; parallel resets, lane-ordered seeds, final obs and infos in C) (36c0160) | `native_autoreset` / `--native-autoreset` | Bit-identical: `perf/check_vec.py` 1024×6000 steps, 9,837 resets; trainer SHA = main | 203k / 269k | 211k / 285k | |
| a | Compact observations: uint8 rows through the C step, H2D and the rollout buffer; exact one-hot rebuilt on the GPU (36c0160) | `compact_obs` / `--compact-obs` | Bit-identical, same evidence as (b); torch expansion checked bitwise | 203k / 269k | 238k / 380k (a alone); **244k / 415k** with b | The C step at 4096 envs falls from 4.7 to 1.0 ms (no 48 MB float encode); H2D 1.26 → 0.6 ms; rollout memory ÷5.5 |
| c | `torch.compile` of encoder + actor, in place (fbf8ee8) | `compile` / `--compile` | Different rounding | 244k / 409k | 291k / 494k | Learner 0.30 → 0.23 s/iteration at 1024 envs; collection barely changes |
| d | bf16 autocast in the update (heads, log-probs, values in fp32) (fbf8ee8) | `bf16` / `--bf16` | Different rounding | 244k / 409k | 259k / 460k | |
| d | Fused Adam (fbf8ee8) | `fused_adam` / `--fused-adam` | Different rounding | 244k / 409k | 246k / 407k | No gain alone; part of max |
| c+d | compile + bf16 + fused (max config) | | Different rounding | 244k / 409k | **311k / 592k** | |
| f | GPU simulator backend (HIP build of src/, pool resets on device) (4ae91b1) | `sim_backend='gpu'` / `--sim-backend gpu` | Bit-identical: `perf/check_gpusim.py` 1024×4000 steps; trainer SHA = CPU path at 1024/2048/4096/16384 envs | CPU exact 245k / 343k / 409k / 482k (at 1024 / 2048 / 4096 / 16384) | 183k / 275k / 364k / 470k | Slower at every tested size: GPU latency is ~1.6 ms per batch step below ~16k envs. It does not save CPU either (1.7-2.1 cores busy vs 1.2-1.7). Kept as an option only |
| g | epochs 2 / epochs 1 / 4 minibatches | existing `--epochs`, `--minibatches` | **Changes the algorithm** | exact 244k / 409k | 337k / 585k; 417k / 742k; 303k / 451k | epochs 2 loses sample efficiency (§2); not recommended at a fixed sample budget |
| e | Overlapped collection (double-buffered env halves, C step in a thread) | not added | — | collection 1.59 / 3.41 ms per step | 2.70 / 4.00 ms per step (**0.59× / 0.85×**) | `perf/overlap_probe.py`. Inference is launch-bound, so two half-batch calls cost more than the hidden C step; rejected |
| 5 | Tile-embedding lookup instead of one-hot × Linear in the targets encoder | not added | Same function, max \|Δlogp\| 1e-6 | update 3.03 / 5.36 ms (minibatch 8192 / 16384) | 7.45 / 13.75 ms (**2.5× slower**) | `perf/embed_probe.py`; the embedding backward (scatter-add) is slow on ROCm; rejected |
| 5 | HIP/CUDA graph capture of collection sampling (Gumbel-max) | removed | Changes the random stream | — | **aborts**: `HSA_STATUS_ERROR_INVALID_PACKET_FORMAT` on ROCm 7.1 / torch 2.13 (float32 input; once also with compile) | Not reliable here; revisit with a newer ROCm |
| 5 | Pinned host buffers for H2D | not added | Exact | 0.893 ms (46 MB, 4096 envs) | 0.876 ms | `perf/gpusim/logs/eval1/sweep.log`; no gain, and compact obs already shrank the copy |

The sources of the before/after collection time come from the per-phase profile (`perf/profile_collect.py`, ms per step):

| 1024 envs | act | C step | potential | H2D | total |
|---|---:|---:|---:|---:|---:|
| main | 1.33 | 0.78 | 2.12 | 0.45 | 4.77 |
| exact config | 0.76 | 0.31 | 0.40 | 0.26 | 1.80 |

At 4096 envs the total falls from 22.1 to 3.76 ms per step. In the exact config the remaining collection cost is mostly launch-bound policy inference.

## 2. Learning checks (changes that alter the math)

Setup (`perf/learning_check.sh`):
- 32M steps at 1024 envs, `pot_e1024` settings
- seeds 901-904
- validation on seeds 23000001.. (128 episodes, evaluated on CPU) via `tools/iterate_ppo.py`
- The control is the exact config, which is bit-identical to the unchanged trainer.

Final validation achievements out of 32 (`perf/logs/learning_checks.txt`; curves in `perf/logs/learning/`):

| Arm | Mean ± sd | Per seed | Verdict |
|---|---|---|---|
| control (unchanged math) | 17.48 ± 4.41 | 19.66, 10.90, 20.24, 19.13 | — |
| compile | 19.09 ± 1.16 | 20.09, 17.96, 20.08, 18.23 | no regression |
| bf16 + fused Adam | 19.07 ± 1.06 | 19.63, 17.48, 19.54, 19.62 | no regression |
| compile + bf16 + fused (max) | 19.73 ± 0.34 | 19.74, 19.25, 19.95, 19.99 | no regression |
| epochs 2 | 16.47 ± 3.81 | 18.26, 10.75, 18.50, 18.35 | **worse per sample**: below control on every seed that broke through |

Outcomes are bimodal: a seed either breaks through to stone/furnace by 32M steps or stays near 11. Four seeds therefore only rule out gross regressions; they cannot detect differences of a few tenths. The max config should get more seeds in a real study before anyone claims it learns *better*.

## 3. Concurrency on one GPU (planning for 7-GPU fleets)

Measured with `perf/bench_concurrency.py`. The 16 CPU threads are split evenly between runs, with `sim_workers` equal to the threads each run gets. All values are steady steps/s.

| Config | Envs | 1 run | 2 runs (aggregate / per run) | 4 runs (aggregate / per run) |
|---|---:|---:|---:|---:|
| exact | 1024 | 244k | **433k** / 217k | 345k / 86k |
| exact | 2048 | 343k | **530k** / 265k | 497k / 124k |
| max | 1024 | 302k | **594k** / 297k | 441k / 110k |
| max | 2048 | 489k | **781k** / 390k | 735k / 184k |
| gpu backend | 1024 | 184k | 320k / 160k | 303k / 76k |
| gpu backend | 2048 | 276k | 442k / 221k | 449k / 112k |
| gpu backend + max | 2048 | 346k | 606k / 303k | 638k / 159k |

How much CPU a run actually uses (single run, 1024 envs, `perf/logs/cpu_scaling_1024.txt`):

| Cores (= sim_workers) | exact | max |
|---:|---:|---:|
| 2 | 227k | 284k |
| 4 | 250k | 298k |
| 8 | 252k | 305k |

Average busy cores per run were 1.2-2.1, as computed by `bench_concurrency` from rusage.

What this means for fleets:
- **The GPU is the shared resource, not the CPU.** Two runs per GPU nearly double the aggregate.
- Four runs per GPU lose to two, because processes time-slicing one GPU interfere.
- Give each run 2-4 cores (`--sim-workers 2..4 --threads 1`).
- **Estimate:** at 2 runs × 2048 envs per GPU with the max config, 7 GPUs would sustain about 7 × 0.78M ≈ 5.5M steps/s using about 14 × 2-4 cores. This assumes other GPUs' runs do not contend for the CPU, which was not measured.

## 4. Recommended production configs

- **(a) Exact.** Results are bit-identical to main.
  - Flags: `--native-autoreset --compact-obs`, using this branch's library (`make lib`).
  - For v7: `make -C perf/v7 LIGHT_WINDOW=1` and `TERRARIA_LITE_LIB=$PWD/perf/v7/build-lw/libterraria.so`.
  - Supported extras: potential and novelty shaping. Rejected with an error: memory features, SIL, RND, progress/difficulty rewards, archive restarts, aux.
  - Without `--compact-obs`, every extra still works with `--native-autoreset`, except the archive.
- **(b) Max.** Config (a) plus `--compile --bf16 --fused-adam`. The first iteration pays about 10-20 s of compile time.
- Do **not** use `--epochs 2` to buy speed without a dedicated sample-efficiency study.
- Keep `--sim-backend gpu` as a research option only; it is slower at 1024-16k envs.

## 5. Merge checklist (for Main)

1. Merge `perf` into `main` with `--no-ff`, between experiment waves only. Never rebuild `python/terraria_lite/libterraria.so` in a worktree while live runs have it mapped.
2. Conflict surface: `tools/iterate_ppo.py` only (append-only flags). `perf` also changes or adds:
   - `src/light.c`, `src/capi.c`, `include/env.h`
   - `src/render.c`, `src/px_render.c`
   - `tools/selftest_v2.c`, `tools/light_incremental_test.c`, `tools/fidelity_test.c`, `tools/light_probe_test.c`
   - `python/terraria_lite/{batch,cells,potential,ppo_agent}.py`
   - new: `python/terraria_lite/{compact,gpusim}.py`, `perf/**`
3. After merging, in the main worktree:
   - `make lib selftest light-selftest fidelity-selftest && make check`
   - `HIP_VISIBLE_DEVICES=<gpu> PYTHONPATH=python python -m terraria_lite.v2_checks`
   - `python perf/check_vec.py`
   - `python perf/check_potential.py`
   - `python perf/bench_trainer.py --envs 1024 --iters 6`: the SHA must equal the pre-merge default (`70f455d891915357` for seed 901, 6 iterations at 1024 envs).
4. Behaviour notes:
   - `Env.light` is exact only inside the observation window, and renderers call `light_full`.
   - Whole-state blobs differ from older builds outside that window, so do not byte-compare blobs across builds.
   - Flagged options default to off.
5. v7: the live runs use `builds/v7/python/terraria_lite/libterraria.so`. To get the exact speed-ups there, build `perf/v7` (CPU) and point `TERRARIA_LITE_LIB` at `perf/v7/build-lw/libterraria.so`. Alternatively, rebuild `builds/v7` with the new `capi.c` and the `light_window_v7.patch`. Parity logs are in `perf/v7/logs/`.
6. The GPU backend is optional and needs hipcc: `make -C perf/gpusim libgpusim.so`, or `make -C perf/v7 gpu` for v7.
7. Add the new flags to `explore_screen.py` arms as needed: `--native-autoreset --compact-obs [--compile --bf16 --fused-adam]`.

## 6. Reproduce (eg18, `~/Projects/RL-perf`)

```sh
export HIP_VISIBLE_DEVICES=7 PYTHONDONTWRITEBYTECODE=1
PY=~/Projects/RL/.venv/bin/python
make lib && make -C perf/gpusim libgpusim.so && make -C perf/v7 && make -C perf/v7 LIGHT_WINDOW=1 && make -C perf/v7 gpu
PYTHONPATH=python $PY perf/check_vec.py --envs 1024 --steps 6000 --workers 16 --torch-device cuda
PYTHONPATH=python $PY perf/check_potential.py --envs 1024 --steps 3000
PYTHONPATH=python $PY perf/check_gpusim.py --envs 1024 --steps 4000
sh perf/bench_exact.sh        # main vs branch, exact options      -> perf/logs/bench_exact.log
sh perf/bench_math.sh         # compile / bf16 / fused / epochs    -> perf/logs/bench_math.log
sh perf/bench_backend_v7.sh   # GPU backend sizes; v7 rows         -> perf/logs/bench_backend_v7.log
sh perf/bench_concurrency.sh  # 1/2/4 runs per GPU                 -> perf/logs/bench_concurrency.log
sh perf/learning_check.sh control compile bf16 fast epochs2   # SEEDS="901 902" default
python3 perf/summarize_learning.py perf/runs
sh perf/v7/parity.sh          # v7 CPU/GPU parity vs the live v7 library
PYTHONPATH=python $PY perf/overlap_probe.py --envs 4096; PYTHONPATH=python $PY perf/embed_probe.py
```

Caveats:
- The CPU threads are SMT siblings shared with other jobs.
- GPU 7 was otherwise idle, but GPUs 0-6 ran live experiments.
- Learning checks use 4 seeds at 32M steps; see §2 for their power.

## 7. Round 2: v7 max path with frontier potential and novelty (eg18 GPU 0)

Setup:
- eg18, **GPU 0 only**, CPUs 72-95 (24 threads), torch 2.13.0+rocm7.1.
- Live experiments ran on GPUs 1-4 (later also 5-6) at the same time, so absolute numbers carry a few % of noise.
- Game: v7 light-window library (`perf/v7/build-lw`).
- Arm: the production `pot_e1024_max` arm from `tools/explore_screen.py` (gpu layout, `--native-autoreset --compact-obs --compile --bf16 --fused-adam`) plus `--potential-mode frontier --novelty .01` (`wall_frontier_nov01`), unless stated otherwise.
- Compact logs are in `perf/logs/round2/`.

### 7.1 Where the time went (main d397bda)

`perf/profile_train.py` runs `tools/iterate_ppo.py` unchanged, with timers around each phase. Values are ms per PPO iteration (131,072 steps). There is no GPU sync between phases; `--sync` gives the same picture within ±10%. The first iteration is excluded.

| Phase | frontier + nov .01 | ctl (mean potential 3) |
|---|---:|---:|
| policy forward + sampling (collection) | 91 | 81 |
| C simulator step (`VecTerraria.step`) | 31 | 29 |
| potential shaping (`RecipePotential.step`) | 64 | 61 |
| novelty (`CellNovelty.step`) | **89** | — |
| compact-obs expansion (collection) | 11 | 10 |
| H2D, buffer writes, telemetry | 33 | 30 |
| GAE | 6 | 5 |
| PPO update (4 epochs × 16 minibatches) | **190** | **192** |
| **steady steps/s, evaluation excluded** | **254k** | **320k** |

- **Shaping (potential + novelty) was 30% of training time** on the shaping arms. This matches the live curves: `wall_frontier_nov01` ran at ~165k train steps/s vs ~240k for `wall_ctl`.
- **Evaluation:** 128 validation episodes on CPU took ~10 s early in training and ~13 s late (live runs: 294 s elapsed vs 281 s training per 67M interval). That is ~5% of wall time at the 64M interval, more at shorter intervals. Checkpoint saving: <10 ms.
- **Two runs on one GPU barely interfere:** 248k + 242k vs 254k alone. The GPU is not saturated. Each run is bound by per-step latency on the host (Python, numpy, kernel launches).
- **The update is launch-bound:** the torch profiler shows ~70% GPU busy during the update, with ~560 kernel launches and ops per minibatch.

### 7.2 Changes (branch `perf`)

Speeds are steady steps/s at 1024 envs (bench_trainer, 16 iterations), unless the row says otherwise. Every exact row keeps the trainer fingerprint, using `perf/bench_trainer.py --envs 1024 --iters 6` on the v7 light-window library (`perf/logs/round2/fingerprints.txt`):
- exact config + frontier + nov .01: `9b00de160bd6436b`
- exact config + frontier_surface + nov .1: `edc62c5e1595e4a4`
- no perf flags: `a18970ad67930ebb`

| # | Change (commit) | Flag | Exactness | Effect |
|---|---|---|---|---|
| R1 | Shaping in C (687975b): `tl_cells_decode` decodes compact rows (inventory, stations, achievements, row, cell key) on the simulator's worker pool; `tl_novelty_*` hold the visit counts and per-episode cell sets in C hash tables; the `RecipePotential` memo key ignores counts above an item's largest need and the row while the climb goal is closed | always on | Bit-identical: `perf/check_shaping.py` compares decode, every potential mode and novelty (bonuses and stats) against the main implementations (dense phi, dict-and-set loop) on live compact and flat rollouts and on trained-policy traces (1024 lanes × 1000 steps, 1.0M nonzero shaping rewards, 109k novelty bonuses); `check_potential.py` OK; fingerprints unchanged | Trained-policy trace, ms/step: novelty 0.54-0.65 → **0.10**, potential frontier 0.71 → **0.39**, frontier_surface 0.94 → **0.54**, mean 0.63 → 0.36. Real run: shaping 153 → 67 ms/iteration |
| R2 | `--async-evaluation` (db2b33e): the checkpoint copy is evaluated by one spawned worker process (same `evaluate(load_agent(...))`, same torch thread count) while training continues; rows are recorded in checkpoint order | opt-in; needs `--evaluation-device` ≠ `--device` (true for the gpu layout) | Validation results and checkpoint files byte-identical to in-process evaluation (exact config, 2 evaluations) | 32M-step run with 4 evaluations: 150.6 → **117.3 s**. Saves one evaluation's time per interval except the last |
| R3 | `Categorical(validate_args=False)` in `act` and the bf16 scorer (f14eef7) | always on | The argument checks can only raise. Outputs and the sampling stream are unchanged (fingerprints) | Removes two host syncs per call. Max config 318k → **338k** (learner 0.20 → 0.18 s/iteration) |
| R4 | Pinned host buffers and non-blocking rollout uploads (ecc272c): `VecTerraria(pin_memory=True)`; obs, mask, reward and done are copied into persistent device tensors | always on when collecting on a GPU | Bit copies, stream-ordered; the per-step action fetch synchronises before the simulator rewrites the buffers. Fingerprints unchanged | Collection 0.219 → 0.211 s/iteration (3 A/B pairs) |
| R5 | Gather each batch tensor once per epoch; minibatches become slices (d2fbc23) | always on | Same rows, values and layouts; fingerprints unchanged | Learner ~0.196 → 0.185 s/iteration (3 A/B pairs; small, near the noise) |
| R6 | `--compile-all` (98bc7bf): one `torch.compile` graph for the sampling forward (expansion through log-softmax and value; multinomial sampling stays eager) and one for the whole minibatch loss (expansion, heads, losses, backward) | opt-in | **Changes rounding.** Learning check below | Max config 324k → **457k** (collection 0.208 → 0.166, learner 0.196 → 0.119 s/iteration). With 1 run per GPU on 24 cores: 476k |

Learning check for R6 (`GPU=0 CPUS=72-95 JOBS=4 SEEDS="901 902 903 904" sh perf/learning_check.sh fn_fast fn_fast_all`):
- 32M steps, v7 light-window library, frontier + nov .01, max config with and without `--compile-all`, validation on 23000001..+127.
- Results: `perf/logs/learning_checks_v7_compile_all.txt`.

| Arm | Final validation (mean ± sd) | Per seed 901-904 |
|---|---|---|
| fn_fast (control) | 16.45 ± 3.67 | 18.08, 17.92, 10.98, 18.81 |
| fn_fast_all (`--compile-all`) | 17.72 ± 2.25 | 18.71, 19.18, 14.38, 18.63 |

There is no regression. As in §2, outcomes are bimodal and four seeds cannot resolve small differences.

**Note: the max config is not deterministic run to run on ROCm.** Two identical runs give different fingerprints (`0266f975…` vs `ee3d688f…`), probably from atomics in compiled backward kernels. So exactness of every change is proven on the exact config, which is deterministic; the max config can only be learning-checked.

### 7.3 After: profile and end to end

Profile, ms per iteration, frontier + nov .01:
- `prof_new`: max config with R1-R5.
- `prof_new_all`: also with `--compile-all`. Under `--compile-all` the forward and expansion run inside the compiled graph, so they are counted in "H2D, buffers, telemetry".

| Phase | main | R1-R5 | + `--compile-all` |
|---|---:|---:|---:|
| policy forward + sampling | 91 | 85 | (in next row) |
| H2D, buffers, telemetry | 33 | 19 | 75 (incl. forward + sampling) |
| C simulator step | 31 | 29 | 26 |
| potential | 64 | 51 | 52 |
| novelty | 89 | 17 | 14 |
| expansion | 11 | 11 | (in graph) |
| GAE | 6 | 6 | 5 |
| PPO update | 190 | 186 | 124 |
| **steady steps/s, eval excluded** | **254k** | **324k** (1.28×) | **440k** (1.73×) |

End to end, `tools/iterate_ppo.py`:
- 32M steps, 4 evaluations at 8M intervals, seed 901, solo on GPU 0.
- This includes startup (compile, a few seconds) and evaluations, so it overweights fixed costs compared with a 512M production run.
- Log: `perf/logs/round2/e2e.txt`.

| Code / flags | Wall | Collection | Optimisation | Final validation |
|---|---:|---:|---:|---:|
| main d397bda, max arm | 191.8 s | 93.3 s | 55.0 s | 18.88 |
| perf, max arm | 150.6 s | 56.4 s | 55.2 s | 19.01 |
| perf, + `--async-evaluation` | 117.3 s | 53.0 s | 51.3 s | 17.92 |
| perf, + `--async-evaluation --compile-all` | **88.4 s** (2.2×) | 43.0 s | 33.8 s | 19.16 |

The final-validation scores differ between rows because the max config is nondeterministic (above), not because the changes alter evaluation.

Runs per GPU (`perf/bench_concurrency.py --gpu 0 --cpus 72-95 --iters 40 --set potential_mode=frontier novelty_coef=.01`):
- The 24 CPU threads are split evenly between runs.
- In the 3-run rows, one run's timing window partly ran alone (startup stagger), so read their aggregate as ~0.93M (max-all) and ~0.67M (max).
- Results: `perf/logs/round2/concurrency.txt`.

| Config | 1 run | 2 runs (aggregate / per run) | 3 runs | 4 runs |
|---|---:|---:|---:|---:|
| max + R1-R5 | 342k | 612k / 306k | 767k* / 222-322k | 729k / 182k |
| max + R1-R5 + `--compile-all` | 476k | **835k** / 418k | 1.03M* / 308-414k | 1.01M / 252k |

Two runs per GPU remain the best trade-off for the latency of a single run. Three or four runs add ~10-20% aggregate throughput at a 25-40% slower per-run speed. They are worth it only when there are more queued runs than GPU slots.

### 7.4 Tried and rejected (or not worth keeping)

| Idea | Result |
|---|---|
| Skip the unused entropy in collection | 338.8k vs 337.6k (noise); not kept |
| Defer the per-minibatch `isfinite(loss)` host sync to the end of the iteration | 330k vs 338k (noise, no gain); not kept, because it would also weaken the crash guarantee |
| Vectorised NumPy novelty (dict touched only for lanes whose cell changed) | 0.65 → 0.50 ms/step; superseded by the C tables (0.10) |
| Single-thread `tl_cells_decode` | 0.30 ms per 1024 cold rows (0.12 hot): the 64-bit multiply chain of the hash plus DRAM. 8 pool threads bring it to 0.08 ms; kept that way |
| Global (cross-lane) phi memo for the potential | Only 52% (frontier) / 46% (frontier_surface) of recomputed rows hit, while the dict grows by 80-138k keys per 1000 steps. At most ~0.07 ms/step; rejected |
| Recomputing phi over only the needed items, or phi in C | NumPy's pairwise summation order over the 33-item axis would have to be replicated, which depends on NumPy internals; rejected as not provably exact |
| 3-4 runs per GPU | See §7.3: +10-20% aggregate, much slower per run |
| Earlier rejections still hold (§1) | Overlapped half-batches, CUDA/HIP graph capture, embedding lookup, pinned memory for its own sake |

### 7.5 Recommended configuration

- **Exact** (bit-identical training to main): `pot_e1024_max` flags as today, plus `--async-evaluation`.
  - R1, R3, R4 and R5 are always on and exact.
  - They need the rebuilt library (checklist below).
  - On the max path this alone is 254k → 324k steady steps/s for the shaping arms, and one evaluation less on the critical path per interval.
- **Max:** additionally `--compile-all`. Steady steps/s are 440-476k solo and ~835k per GPU with 2 runs.
  - Learning check passed (§7.2).
  - Start new studies with it rather than switching arms mid-study, because it changes rounding.
- Packing: keep **2 runs per GPU**, each with ~12 CPU threads (`--sim-workers 12 --threads 4` is fine).

### 7.6 Merge checklist (round 2)

1. Merge `perf` into `main` with `--no-ff`. Conflict surface:
   - `python/terraria_lite/{ppo_agent,cells,potential,count_novelty,ppo_eval}.py`
   - `tools/iterate_ppo.py` (append-only flags)
   - `src/capi.c` (append-only)
   - `perf/**`
2. **The Python package now needs the new C symbols** (`tl_cells_decode`, `tl_novelty_*`). `cells.py` and `count_novelty.py` bind them at import, so an old library fails loudly at the first shaping run.
   - Rebuild before launching new runs: `make -C perf/v7 LIGHT_WINDOW=1 BUILD=build-lw2`, or any fresh `BUILD` directory.
   - Point `TERRARIA_LITE_LIB` at the new build. Building into a fresh directory never touches a library that live runs have mapped.
   - Run `make lib` (the package's own library, used by v4 runs) only between waves.
   - Live runs are unaffected by the merge. Every module round 2 changes is imported when training starts, and live runs do not use `--async-evaluation`, whose worker would import the package afresh.
3. Checks after merging, in the main worktree with the new library:
   - `PYTHONPATH=python python perf/check_shaping.py --envs 1024 --steps 300` (add `--trace <npz>` from `perf/shaping_trace.py --policy <late checkpoint>` for trained-policy states)
   - `python perf/check_potential.py --envs 1024 --steps 1000`
   - `python perf/check_vec.py --envs 1024 --steps 6000 --workers 16 --torch-device cuda`
   - `python perf/bench_trainer.py --envs 1024 --iters 6 --set native_autoreset=1 compact_obs=1 potential_mode=frontier novelty_coef=.01` must print `9b00de160bd6436b`. This is on the v7 light-window library, seed 901. Without `--set`, it must print `a18970ad67930ebb`.
4. `tools/explore_screen.py`: add `--async-evaluation` (and `--compile-all` for a max study) to new arms, for example a `pot_e1024_max2` arm = `pot_e1024_max` + both flags.
5. Reproduce round 2 on eg18 (`~/Projects/RL-perf`, `HIP_VISIBLE_DEVICES=0`, `TERRARIA_LITE_LIB=$PWD/perf/v7/build-lw/libterraria.so`):
   - `perf/profile_train.py -- <iterate_ppo args>` (§7.1/7.3)
   - `perf/shaping_trace.py` + `perf/check_shaping.py --trace` (R1)
   - `perf/bench_trainer.py` A/B with `PYTHONPATH` set to a `git archive` export of the older commit (R3-R6)
   - `perf/bench_concurrency.py --gpu 0 --cpus 72-95 --config max-all --set potential_mode=frontier novelty_coef=.01`
   - `GPU=0 CPUS=72-95 JOBS=4 SEEDS="901 902 903 904" sh perf/learning_check.sh fn_fast fn_fast_all`
