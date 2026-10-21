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
