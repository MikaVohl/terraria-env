# Scaling feed-forward PPO policies on terraria-lite v7 (October 2026)

Branch `scale-ff`. Question: does a bigger feed-forward policy move v7 past PPO's ~25/32 plateau, at equal environment steps or at equal wall-clock, and where does it saturate? General capacity only: game, rewards, observations, masks, shaping (recipe potential 3, mean) and the evaluation protocol are unchanged.

## Answer

**No.** Over an 83x range of parameters (134k to 11.1M) the 512M-step score is flat within about 0.5 points, and the default network (hidden 128, 473k parameters) is the best point: 24.96/32 (seeds 24.92, 25.00) against 24.45 to 24.57 for every other width. Bigger networks are also 10-15% slower per step, so at equal wall-clock they lose by the same margin or more. At 2B steps the largest network still does not beat the control (25.54 for the control vs 24.98 for hidden 2048 at lr 1e-4, and the control is ahead at all 16 checkpoints). Very small networks hurt only slightly: hidden 32 (134k parameters) reaches 24.57.

Capacity is not what limits the policy:
- The value function already explains 99.3-99.8% of return variance at every size from 128M steps on, so a bigger critic has nothing left to fit.
- Bigger policies get more deterministic (entropy 2.5-2.6 vs 2.7-2.8) and take bigger update steps (approx KL and clip fraction up to 2x), but play the same game. Achievement rates, death rate, idle tail and inventory are the same within seed noise.
- Stockpiling does not change with size. The median iron-bar peak is 4-5 at every size, only 0-4 of 128 episodes per run ever hold 10 iron bars, wood peaks at 13-15 (max 27), and **no run at any size ever had a legal iron pickaxe, gold pickaxe, iron chainmail or wood breastplate craft**. Return to surface stays at 0-0.4%.

So the plateau is not a representational limit of a 0.5M-parameter reactive policy. Per the problem statement, the missing crafts need long-horizon accumulation (finding nearly all 120 iron ore with an 11x9 window and no memory). Adding feed-forward width or depth does not supply that. Memory (the MemoryArch study) or a different learning signal is the remaining lever.

Larger networks need a lower learning rate. At the default 3e-4, hidden 2048 never builds a furnace (19.4/32 at 512M, both seeds) and hidden 1024 trails (23.6). At 1e-4 both match the small networks.

## Protocol

- Fast path = arm `pot_e1024_max2` (tools/explore_screen.py): `--potential 3 --envs 1024 --minibatches 16 --rollout 128 --gamma .999 --gae-lambda .99 --entropy .03`, native autoreset, compact obs, `--compile --bf16 --fused-adam --compile-all --async-evaluation`, architecture `targets`. Validation: 128 fresh worlds 23000001-23000128, every 32M steps (128M for the 2B runs). Reserved test worlds are unused. Arms `ff_t{hidden}c{cell}d{depth}[_lr1e4]` and `ff_m{hidden}d{depth}[_lr1e4]` are defined in tools/explore_screen.py.
- Size knobs (this branch): Config/CLI `hidden` (0 = architecture default), `depth` (global trunk layers, `targets` and `mlp`) and `cell_width` (per-cell MLP width, `targets`). They are threaded through `spatial_agent.build_agent(architecture, hidden, extra, depth=, cell_width=)` and `TargetActorCritic(hidden, extra, depth, cell_width)`. Checkpoint sizes are inferred from the state dict (`spatial_agent.agent_size`), so `ppo_eval.load_agent`, async evaluation and `watch` load any size. protocol.json records `parameters`; summary.json records hidden/depth/cell_width/parameters. From cb73159 on, every checkpoint profile records `approx_kl`, `clip_fraction` and `explained_variance`, alongside the existing `policy_entropy`.
- Defaults are bit-identical: on eg15 HIP 2/3 with this checkout's v7 build-lw2 library, `perf/bench_trainer.py --envs 1024 --iters 6` prints `a18970ad67930ebb` (required a18970ad67930ebb), and with `--set native_autoreset=1 compact_obs=1 potential_mode=frontier novelty_coef=.01` it prints `9b00de160bd6436b` (required 9b00de160bd6436b). The default `targets`, `mlp`, `cnn`, `tokens` and `separate` networks were also checked tensor-equal to main's at the same seed.
- Machine: eg15 (8x MI350X), ROCm 7.2.4, amdgpu 6.16.13, torch 2.13.0+rocm7.1; HIP GPUs 2 and 3 (7 for the solo trace). Seeds 1801/1802. Diagnostics: `tools/policy_diagnostics.py <final checkpoint> --episodes 128 --seed-start 23000001` for every finished run (`diag.json`).
- **Runs sharing a GPU are not trustworthy on eg15** (see "GPU sharing corrupts training" below). The main results are therefore one run per GPU ("alone"). The first sweep at two runs per GPU is reported separately and flagged.

## Throughput (steps/s by model size)

Steady-state `perf/bench_trainer.py --iters 12` on the max2 flags. The environment simulation, not the GPU, is the bottleneck: an 11M-parameter policy costs only ~13% of throughput alone. Real 512M runs alone took 21-23 min including asynchronous evaluation.

| config | params | alone steps/s | each of 2 on one GPU |
|---|---:|---:|---:|
| targets h128 (control) | 472,718 | 422,630 | 412,142, 403,024 |
| targets h256 | 953,230 | 442,862 | 392,383, 410,324 |
| targets h512 | 2,012,558 | 431,225 | 379,059, 388,774 |
| targets h1024 | 4,524,430 | 378,512 | 364,090, 369,702 |
| targets h2048 | 11,121,038 | 369,133 | 313,094, 302,399 |
| targets h512, cell 64 | 3,657,070 | 370,022 | 312,157, 310,242 |
| targets h512, cell 128 | 6,952,238 | 329,066 | 247,401, 236,396 |
| targets h512, depth 3 | 2,275,214 | 399,093 | 371,144, 382,090 |
| targets h512, depth 4 | 2,537,870 | 383,047 | 354,129, 355,198 |
| targets h2048, cell 128, depth 4 | 39,051,566 | 209,207 | 143,770, 143,603 |
| mlp h512 | 1,823,316 | 539,972 | 562,621, 558,116 |
| mlp h1024 | 4,170,836 | 540,255 | 515,554, 528,260 |
| mlp h2048 | 10,438,740 | 526,017 | 459,261, 478,834 |

## Results at 512M steps (alone, 1 run per GPU, 2 seeds each)

Mean validation score /32 at matched environment steps and at matched wall-clock (last checkpoint written within 600 s and 1200 s of the start).

| model | params | 128M | 256M | 512M final (seeds 1801, 1802) | at 600 s | at 1200 s | s per 1B steps (wall, incl. eval) |
|---|---:|---:|---:|---|---:|---:|---:|
| targets h32 | 133,838 | 22.51 | 23.93 | **24.57** (24.41, 24.73) | 23.52 | 24.27 | 2570 |
| targets h64 | 244,750 | 22.89 | 23.93 | **24.55** (24.55, 24.55) | 23.71 | 24.73 | 2529 |
| targets h128 | 472,718 | 23.29 | 24.52 | **24.96** (24.92, 25.00) | 24.06 | 24.73 | 2432 |
| targets h1024 lr 1e-4 | 4,524,430 | 21.62 | 23.44 | **24.53** (24.30, 24.75) | 23.36 | 24.05 | 2495 |
| targets h2048 lr 1e-4 | 11,121,038 | 22.69 | 23.74 | **24.45** (24.54, 24.36) | 23.68 | 24.59 | 2679 |

Equal steps: the control is ahead at every checkpoint (128M, 256M, 512M). Equal wall-clock: the control is ahead or tied (hidden 64 ties at 1200 s), and wider networks fall further behind because they are slower per step.

### Learner telemetry at matched steps

Approx KL is from the last minibatch, clip fraction is the iteration mean, and value EV is computed on the rollout. Each value is the mean of 2 seeds at that checkpoint. At 480M the LR has annealed to ~5%, so KL and clip fraction are omitted there.

| model | entropy 128M / 256M / 480M | approx KL 128M / 256M | clip frac 128M / 256M | value EV 128M / 256M / 480M |
|---|---|---|---|---|
| targets h32 | 2.82 / 2.81 / 2.83 | 0.0021 / 0.0023 | 0.008 / 0.007 | 0.9948 / 0.9960 / 0.9975 |
| targets h64 | 2.80 / 2.76 / 2.78 | 0.0039 / 0.0031 | 0.012 / 0.008 | 0.9934 / 0.9955 / 0.9976 |
| targets h128 | 2.71 / 2.73 / 2.78 | 0.0036 / 0.0042 | 0.018 / 0.016 | 0.9926 / 0.9965 / 0.9977 |
| targets h1024 lr 1e-4 | 2.50 / 2.60 / 2.61 | 0.0043 / 0.0040 | 0.027 / 0.017 | 0.9918 / 0.9954 / 0.9962 |
| targets h2048 lr 1e-4 | 2.63 / 2.55 / 2.62 | 0.0049 / 0.0043 | 0.035 / 0.025 | 0.9933 / 0.9939 / 0.9968 |

Every size fits the value function about equally well (EV >0.99). Wider networks move the policy more per update and end more deterministic, without scoring higher. In short, a bigger network fits no better here, and it doesn't play better either.

### Achievements and stockpiling diagnostics (final 512M checkpoints, 256 validation episodes per size)

| model | anvil | metal sword | iron / gold pickaxe | chainmail | breastplate | return to surface | death | idle tail (steps) | iron bar peak median (max) | episodes with >=10 iron bars | wood peak median (max) | gold bar peak median (max) | legal opportunities: anvil / iron pickaxe / gold pickaxe / chainmail / breastplate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| targets h32 | 37% | 5% | 0% / 0% | 0% | 0% | 0.0% | 9% | 1426 | 4.5 (15) | 7/256 | 13.0 (21) | 1.0 (7) | 94 / 0 / 0 / 0 / 0 (of 256) |
| targets h64 | 34% | 5% | 0% / 0% | 0% | 0% | 0.4% | 9% | 1416 | 4.5 (11) | 3/256 | 13.0 (17) | 1.0 (6) | 86 / 0 / 0 / 0 / 0 (of 256) |
| targets h128 | 41% | 7% | 0% / 0% | 0% | 0% | 0.0% | 8% | 1373 | 5.0 (12) | 4/256 | 14.5 (27) | 1.5 (7) | 104 / 0 / 0 / 0 / 0 (of 256) |
| targets h1024 lr 1e-4 | 36% | 6% | 0% / 0% | 0% | 0% | 0.0% | 9% | 1467 | 4.2 (14) | 4/256 | 15.2 (26) | 1.5 (7) | 91 / 0 / 0 / 0 / 0 (of 256) |
| targets h2048 lr 1e-4 | 34% | 4% | 0% / 0% | 0% | 0% | 0.0% | 13% | 1501 | 4.5 (11) | 5/256 | 14.5 (25) | 1.0 (8) | 86 / 0 / 0 / 0 / 0 (of 256) |

### Single-seed extras: cell width, depth, flat MLP (alone, 512M)

These ran in the last free slots, seed 1801 only. Read them as consistency checks, not rankings: the seed-to-seed spread of the control is about 0.1-0.4.

| model (seed 1801 only) | params | 128M | 256M | 512M final | at 600 s | at 1200 s | entropy / KL / EV at 256M | anvil / metal sword | iron bar peak median (max) | big-craft opportunities |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| targets h128, cell width 64 | 900,718 | 23.42 | 24.30 | **24.84** | 23.89 | 24.88 | 2.71 / 0.0035 / 0.9951 | 39% / 7% | 5.0 (10) | 0 |
| targets h128, depth 4 | 505,742 | 21.95 | 23.28 | **24.51** | 23.02 | 24.45 | 2.68 / 0.0027 / 0.9949 | 27% / 2% | 4.0 (15) | 0 |
| flat mlp h1024 (lr 3e-4) | 4,170,836 | 22.34 | 24.01 | **24.88** | 23.94 | 24.88 | 2.64 / 0.0089 / 0.9948 | 37% / 6% | 5.0 (14) | 0 |

None beats the default. Doubling the cell width is neutral (24.84), depth 4 is slower to learn (24.51), and a flat 4.2M-parameter MLP at the default LR (24.88) matches the targets control within seed noise despite having no spatial action sharing. Capacity in any of these directions doesn't move the score.

## 2B steps (alone, seed 1801)

Best large size (hidden 2048, lr 1e-4) vs the matched control (hidden 128, lr 3e-4). Same path, one run per GPU, validation every 128M.

| model (seed 1801, alone) | params | 512M | 1B | 1.5B | 2B final | wall-clock to 2B | death | idle tail | anvil / metal sword | iron bar peak median (max), episodes >=10 | big-craft legal opportunities |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| targets h128 (control) | 472,718 | 24.88 | 25.03 | 25.21 | **25.54** | 89 min | 5% | 1506 | 62% / 17% | 5.0 (9), 0/128 | 0/0/0/0 |
| targets h2048 lr 1e-4 | 11,121,038 | 24.14 | 24.67 | 24.98 | **24.98** | 96 min | 16% | 1519 | 48% / 11% | 5.0 (13), 3/128 | 0/0/0/0 |

Both curves are still rising slowly at 2B. The control's 25.54 matches the earlier best v7 policy (25.67 at 2B, different machine). Hidden 2048 peaks at 25.18 (1.66B) and ends at 24.98. Its entropy runs lower (2.30-2.52 vs 2.69-2.80) and its clip fraction higher (0.048-0.050 vs 0.012-0.023) throughout, with the same value EV (0.994-0.998). Neither 2B policy ever had a legal iron pickaxe, gold pickaxe, chainmail or breastplate craft, and return to surface stayed at 0/128. At equal wall-clock the gap is the same: the control reached 25.16 at 1 h and 25.54 at 89 min, hidden 2048 reached 24.53 at 1 h and 24.98 at 96 min.

## First sweep at two runs per GPU (flagged: shared, spike-prone)

These ran before the GPU-sharing problem was found and were stopped at 18:26 UTC. They point the same way, and they are the only data for hidden 512 and for the learning-rate effect at 3e-4. Three were cut short by non-finite losses or stopped mid-run.

| model (2 runs per GPU) | params | lr | per seed: status, last eval | 128M | 512M final mean |
|---|---:|---:|---|---:|---:|
| targets h32 | 133,838 | 3e-04 | 1801: finished, 24.34 @512M; 1802: stopped, 19.73 @224M | 21.26 | 24.34 |
| targets h128 | 472,718 | 3e-04 | 1801: finished, 24.94 @512M; 1802: finished, 24.98 @512M | 22.66 | 24.96 |
| targets h512 | 2,012,558 | 3e-04 | 1801: non-finite loss, 21.34 @128M; 1802: finished, 24.62 @512M | 22.06 | 24.62 |
| targets h1024 | 4,524,430 | 3e-04 | 1801: finished, 24.24 @512M; 1802: finished, 22.98 @512M | 20.50 | 23.61 |
| targets h1024 | 4,524,430 | 1e-04 | 1801: finished, 24.72 @512M; 1802: finished, 24.64 @512M | 23.04 | 24.68 |
| targets h2048 | 11,121,038 | 3e-04 | 1801: finished, 19.23 @512M; 1802: finished, 19.61 @512M | 18.23 | 19.42 |
| targets h2048 | 11,121,038 | 1e-04 | 1801: finished, 24.73 @512M; 1802: finished, 24.45 @512M | 22.16 | 24.59 |
| targets h256 | 953,230 | 3e-04 | 1801: non-finite loss, 23.92 @160M; 1802: stopped, 19.24 @32M | 23.44 | – |
| targets h64 | 244,750 | 3e-04 | 1801: stopped, 24.30 @224M; 1802: stopped, 23.89 @192M | 23.34 | – |

## GPU sharing corrupts training on eg15

Two `pot_e1024_max2` processes on one MI350X (eg15, ROCm 7.2.4) produce silent, isolated gradient explosions. Sometimes they end in "Non-finite PPO loss" (here: h256 at 160M, h512 at ~140M; MemoryArch lost 4 runs the same way, including a default-size control). The same command alone on a GPU is clean. This is the t512, lr 3e-4, seed 1801 run, with `clip_grad_norm_` total norm traced at every update (2048 env steps per update; tools/scale_ff/nan_repro.py):

- Shared, two traces covering 82M and 123M steps: norms >1e3 in every 10M window from 10M on (1-7 per window), >1e4 1-5 per window, peaks 3.7e10 and 4.5e13. The original shared run died at ~140M.
- Alone (HIP 7), 346M steps: 0 norms >1e3, max 10.4, no non-finite values. Score 24.21 at 436M, where it was stopped to free the GPU.
- Ruled out: the sampler (no draw with p<1e-8 in the shared trace; MemoryArch found 1.08e9 offline multinomial draws calibrated) and bf16 logit drift (|logit| <=47, bf16 log-prob error <=0.29 on checkpoints; tools/scale_ff/logits_probe.py). MemoryArch also found bf16 update numerics (hipBLASLt) to be run-to-run nondeterministic on eg15 when sharing, while fp32 stays deterministic. GpuShareBug is investigating the root cause.
- Consequence: all conclusions above come from one-run-per-GPU runs. Shared runs are reported only as flagged secondary data.

## Not run

Two seeds per cell-width/depth/MLP variant, cell width 128, depth 3, MLP h512/h2048 and lower-LR controls (h128 at 1e-4). Arms and throughput numbers exist for all of them. Width was flat across 83x with the default on top, and the single-seed extras above are flat too. After the switch to one run per GPU, the two GPUs went to the requested width points, seed repeats and the 2B pair.

## Reproduce

- Code: branch `scale-ff`. Knobs in python/terraria_lite/{ppo_agent,target_agent,spatial_agent,ppo_eval,watch}.py, CLI in tools/iterate_ppo.py and ppo_agent.py, arms in tools/explore_screen.py.
- eg15 drivers: tools/scale_ff/queue_driver.py (job queue, `SFF_PER_GPU=1`), diag.sh, status.sh, throughput.sh, nan_repro.py/alone.sh/repro.sh (gradient tracing), spikes.py, logits_probe.py. Run directories on eg15: `~/sff/a512/runs`, `~/sff/a2b/runs` (alone) and `~/sff/s512/runs` (shared).
- Compact results: docs/reports/SCALE_FF_2026_10.json (per run: curves with checkpoint wall-clock, learner telemetry, final rates, diagnostics; per arm: matched-step and matched-wall-clock aggregates; throughput, fingerprints and gradient-spike counts), produced by `tools/scale_ff_report.py ~/sff/a512/runs ~/sff/s512/runs ~/sff/a2b/runs --extra ~/sff/extra.json --wallclock 300 600 900 1200`.
