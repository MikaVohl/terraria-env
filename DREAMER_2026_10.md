# DreamerV3-style world-model agent for terraria-lite v7 (October 2026)

Branch `dreamer`. Status: **stopped early.** Two 16.8M-step short runs finished.
The planned ~10 h long run was stopped by the parent at 23.8M env steps. Another
user needed eg18 GPU 6 for benchmarks. Its only validation point is 16.8M. **No
run reached PPO's plateau regime. This report cannot answer whether Dreamer
passes 25/32.**

## Headline

- Best Dreamer validation: **17.98/32** (ratio 32, 14.7M env steps, 69 min on a
  shared GPU). PPO with the same potential-3 shaping scores **18.09** at the same
  step count (64 envs, 12 seeds). At equal wall-clock, wall_ctl PPO is at about
  24.8 after 69 min.
- Per env step, Dreamer is roughly level with low-budget PPO, at best. Per hour,
  Dreamer is far behind: it trains at about 8-11k env steps/s, while PPO's max
  path runs at about 235k.
- Stockpiling: the best checkpoint never holds 10 iron bars or 30 wood (iron-bar
  peak median 0, max 2; wood median 11, max 19). The pickaxe, chainmail and
  breastplate crafts are never legal. The anvil is never legal, and the furnace is
  legal in only 7/128 episodes. At this budget the bottleneck is the furnace, the
  same wall that low-budget PPO hits.
- One positive signal: the long run's 16.8M checkpoint earned **return to
  surface in 14/128** worlds. PPO earned it in 0.3/128 at 537M (1 of 384
  episodes); the 12 low-budget PPO seeds at 16.8M earned it in 0. The short runs
  earned it at 2-3/128 in three of their 16 evaluations (r8 @16.8M; r32 @10.5M and
  @16.8M). This is one evaluation of one seed, so it is suggestive, not established.

Question: does a model-based learner that trains its policy in imagination get past
the PPO v7 plateau (~25/32 at 512M steps), in particular the never-earned
stockpiling crafts (wood breastplate, iron chainmail, iron/gold pickaxe) and
"return to surface"? Game, extrinsic rewards, observations, masks and the
evaluation protocol are unchanged; PPO code paths are untouched (new files only).

## Design

Code: `python/terraria_lite/dreamer/` (`nets.py`, `replay.py`, `agent.py`,
`evaluate.py`) and `tools/train_dreamer.py`; Mac smoke test `tools/dreamer_selftest.py`.

### Data
- Collection: `VecTerraria(native_autoreset=True, compact=True)` from `ppo_agent`
  (one `tl_batch_step_autoreset` C call per step for all lanes), compact uint8 rows
  (2,152 B) expanded on the GPU by `compact.Expander` into exactly PPO's flat input.
- Replay (on the GPU): one ring per env lane. Row `t` = `(obs_t, mask_t,
  prev_action_t, reward_t, first_t, cont_t)`. At an episode end the lane writes
  two rows: the true terminal observation (`cont=0`, reward of the last action) and
  the reset observation (`first=1`, no previous action). Death and the 3,000-step
  deadline both get `cont=0`: the deadline is inherent and observed (status
  `time`), matching PPO's zero future value at the deadline. Sequences of length
  64 are sampled uniformly over each lane's ring; `first` resets the RSSM state
  inside a sequence; sequences start from a zero state.
- Optional training-only reward: the same potential shaping as the PPO
  baseline (`potential.RecipePotential`, `--potential C --potential-mode`) added to
  the stored reward, so the reward head learns shaped reward. Evaluation is
  always extrinsic. Disclosed per run in `protocol.json`.

### World model (RSSM)
- Encoder: flat obs (tile one-hot 99x24, light/15, status 488; status symlog) ->
  MLP (LayerNorm + SiLU) -> embedding.
- Deterministic GRU state (DreamerV3 LayerNorm GRU, update bias -1), stochastic
  latent 32 categoricals x 32 classes, 1% unimix, straight-through sampling.
- Heads on `feat = [h, z]`: decoder (tile categorical per cell, light
  categorical per cell (16 levels), status symlog MSE where inventory targets are
  `symlog(count)` instead of the encoded sqrt(count/999) so 9 vs 10 bars are well
  separated), reward (two-hot symlog, 255 bins), continue (Bernoulli), and an
  **action-mask head** (83 Bernoulli, terminal rows excluded).
- Loss: prediction + 0.5 dyn KL + 0.1 rep KL, free bits 1.0 (KL balancing).

### Actor-critic in imagination
- Starts: every posterior state of the replayed batch (B x 64), horizon 15,
  gamma 0.997, lambda 0.95. Imagined trajectories are rolled out without
  gradient (discrete actions use REINFORCE, as in DreamerV3), then actor and
  critic are trained on the stored features.
- Critic: two-hot symlog (255 bins), returns from a slow EMA critic (0.02/update),
  plus a regulariser toward the slow critic's prediction.
- Actor: REINFORCE with advantage `(R_lambda - V) / max(1, S)`, S = EMA(0.99) of
  the 95th-5th return percentile range; entropy 3e-4; 1% unimix over the legal set;
  steps weighted by the predicted continuation product.
- **Action mask in imagination: predicted.** Step 0 uses the real mask stored
  with the replayed state (exact). Later steps use the mask head
  (`p > 0.5`; if empty, `noop` is legal). Justification: illegal actions are forbidden
  in the real env, so the world model has never seen their consequences; a fixed
  start-state mask becomes wrong as soon as the imagined agent moves (mining
  targets, crafting after ingredients change), which would let imagination exploit
  unlearned transitions (e.g. "craft iron pickaxe" with 5 bars) or forbid newly legal
  crafts. Masks are a deterministic function of the state (inventory, stations in
  view, tiles in reach), so they are learnable from the latent, and the head also
  forces the latent to encode exact craft thresholds. Real acting always uses the
  real mask.

### Training loop
- N env lanes collect with the current actor (sampled, posterior filtered);
  updates are interleaved so that replayed steps / env steps = `train_ratio`
  (`--train-ratio`). bf16 autocast for the networks; losses, distributions and
  returns in float32. Adam (world model 1e-4, actor/critic 3e-5, eps 1e-8/1e-5,
  grad-norm clip 1000/100).

### Evaluation (comparable to PPO)
- `dreamer/evaluate.py` mirrors `ppo_eval.evaluate`: validation worlds
  23,000,001-23,000,128, cohorts of 64, `torch.manual_seed(54321)`, categorical
  sampling from the masked policy, `NativeBatch.step` flat observations, same result
  keys (mean achievements /32, per-achievement hits, death rate, peak depth, ...).
- Inventory diagnostic mirrors `tools/policy_diagnostics.py` (`diagnose`): peak
  inventories, legal-step counts, chosen actions.
- PPO comparison: `experiments/eg18/eg18-wall-v7-20261021/runs/wall_ctl-150{1,2,3}`
  (potential 3, 512M) at equal env steps and equal wall-clock.

## Hyperparameters (all runs)

| | value |
|---|---|
| world model | MLP encoder 3x640 (LayerNorm+SiLU), GRU deter 1024, stoch 32x32, unimix 1%, decoder 3x640, mask/reward/cont/shaping heads 2x640 |
| world model loss | tile CE + light CE + status symlog MSE + mask BCE + reward two-hot + shaping two-hot + cont BCE + 0.5 dyn + 0.1 rep (free bits 1.0) |
| actor / critic | 3x640, two-hot critic (255 bins), slow critic EMA 0.02/update, slow reg 1.0 |
| imagination | horizon 15, gamma 0.997, lambda 0.95, entropy 3e-4, return norm EMA 0.99 (5-95 pct) |
| optimisation | Adam: world model 1e-4 (eps 1e-8, clip 1000), actor/critic 3e-5 (eps 1e-5, clip 100) |
| batch | 256 sequences x 64 steps = 16,384 replayed steps per update |
| precision | bf16 autocast for the networks; losses and returns in float32; `torch.compile` per RSSM step (long run: whole 64-step filter) |
| training reward | extrinsic + potential shaping 3, mode mean, gamma .997 (same coefficient and mode as wall_ctl) |
| parameters | 30.6M: world model 23.8M, actor + critic + slow critic 6.8M (checkpoint 122 MB fp32) |

Runs (seeds give training worlds `seed*10^7+`, disjoint from validation):

| run | train ratio | envs | replay rows | GPU | env steps | wall |
|---|---|---|---|---|---|---|
| short_r8 (seed 1601) | 8 | 512 | 8M | GPU 6, shared with short_r32 | 16.8M | 26 min |
| short_r32 (seed 1601) | 32 | 512 | 8M | GPU 6, shared with short_r8 | 16.8M | 78 min |
| long_r16 (seed 1602) | 16 | 1024 | 10M | GPU 6, alone after 10 min | 23.8M (stopped) | 48 min |

## Throughput (eg18, one MI350X, ROCm 7.1, torch 2.13)

Update cost (B=256, T=64, alone on the GPU): eager fp32 242 ms, bf16 162 ms,
bf16 + per-step compile 101 ms (161k replayed steps/s). At B=1024 the same
configuration reaches 203k replayed steps/s. The cost is dominated by the
sequential 64-step filter and the 15-step imagination, which are launch-bound at
B=256. Compiling the whole filter gave a further ~17% (measured while a second run
shared the GPU).

In training, collection and updates alternate synchronously. Measured rates:
- Alone: about 132k replayed steps/s, so 8.3k env steps/s at ratio 16.
- Two runs sharing the GPU: about 88k replayed/s each, so 11k env steps/s at ratio 8 and 2.9k at ratio 32.

For comparison, the PPO max path collects about 235k env steps/s.

An option to capture the whole update in one CUDA graph was tried and removed.
Capture failed with hipBLASLt, and with rocBLAS the graph replay crashed with
`HSA_STATUS_ERROR_INVALID_PACKET_FORMAT`.

## Results (validation worlds 23,000,001-23,000,128, sampled, seed 54321)

Mean achievements /32. PPO columns interpolate linearly within each PPO run's
evaluated range: equal env steps (`@steps`) and equal elapsed seconds (`@wall`).
- rep64 = `eg18-rep-v7` potential (64 envs, 12 seeds, evals every 4.2M).
- e1024 = `eg18-long-v7` pot_e1024 (1 seed, first eval at 33.6M).
- wall_ctl = `eg18-wall-v7` (3 seeds, max path, first eval at 67M).

Elapsed time includes validation, and PPO ran 2 runs per GPU.
Source: `results/dreamer-2026-10/comparison.json`, made by `tools/dreamer_compare.py`.

| run | env steps | min | Dreamer | death | PPO rep64 @steps | PPO e1024 @wall | PPO wall_ctl @wall |
|---|---|---|---|---|---|---|---|
| short_r8 | 2.1M | 3 | 9.98 | 13% | - | - | - |
| short_r8 | 4.2M | 6 | 12.05 | 100% | 15.56 | 19.52 | 22.07 |
| short_r8 | 8.4M | 13 | 10.17 | 33% | 17.62 | 21.13 | 23.37 |
| short_r8 | 12.6M | 20 | 16.41 | 95% | 17.96 | 23.24 | 24.32 |
| short_r8 | 16.8M | 26 | 16.94 | 47% | 18.23 | 23.78 | 24.70 |
| short_r32 | 2.1M | 12 | 12.98 | 31% | - | 20.76 | 23.26 |
| short_r32 | 4.2M | 25 | 16.27 | 40% | 15.56 | 23.70 | 24.68 |
| short_r32 | 8.4M | 42 | 16.43 | 35% | 17.62 | 24.19 | 24.88 |
| short_r32 | 10.5M | 51 | 17.36 | 52% | 17.79 | 24.76 | - |
| short_r32 | 12.6M | 60 | 10.82 | 78% | 17.96 | 24.71 | - |
| short_r32 | 14.7M | 69 | **17.98** | 63% | 18.09 | 24.84 | - |
| short_r32 | 16.8M | 78 | 17.27 | 72% | 18.23 | 25.04 | - |
| long_r16 | 16.8M | 34 | 15.01 | 38% | 18.23 | 24.35 | 24.94 |

The full per-row data, including the 6.3M points and the `long64` PPO reference
(explore-v7-long, 2 seeds), is in the JSON.

Per-achievement hits out of 128 (`results/dreamer-2026-10/dreamer_runs.json`):

| achievement | Dreamer r32 @14.7M | Dreamer long @16.8M | PPO rep64 @16.8M (mean of 12) | PPO wall_ctl @537M (mean of 3) |
|---|---|---|---|---|
| collect wood | 128 | 128 | 128.0 | 128.0 |
| collect stone | 127 | 104 | 128.0 | 128.0 |
| place block | 128 | 128 | 128.0 | 128.0 |
| craft workbench | 128 | 128 | 127.4 | 128.0 |
| craft furnace | 6 | 1 | 8.5 | 127.3 |
| craft anvil | 0 | 0 | 0.2 | 56.7 |
| place torch | 126 | 128 | 127.9 | 128.0 |
| place platform | 128 | 128 | 125.9 | 127.7 |
| collect copper | 104 | 74 | 109.9 | 125.3 |
| collect iron | 114 | 71 | 119.8 | 127.3 |
| collect silver | 101 | 63 | 110.1 | 127.3 |
| collect gold | 77 | 46 | 88.9 | 124.3 |
| smelt copper | 5 | 1 | 7.1 | 115.7 |
| smelt iron | 2 | 0 | 5.2 | 125.0 |
| smelt silver | 0 | 0 | 3.8 | 117.0 |
| smelt gold | 0 | 0 | 1.8 | 105.7 |
| defeat Blue Slime | 113 | 128 | 115.2 | 127.3 |
| defeat Cave Bat | 106 | 68 | 117.4 | 126.7 |
| open chest | 127 | 105 | 127.2 | 128.0 |
| craft wooden sword | 103 | 62 | 64.8 | 125.0 |
| craft metal sword | 0 | 0 | 0.1 | 10.0 |
| craft wood breastplate | 0 | 0 | 0 | 0 |
| craft iron chainmail | 0 | 0 | 0 | 0 |
| heal with food or potion | 128 | 128 | 126.7 | 128.0 |
| use life crystal | 89 | 50 | 90.8 | 126.7 |
| double jump | 88 | 54 | 87.2 | 127.3 |
| descend deep | 119 | 79 | 127.9 | 128.0 |
| **return to surface** | 0 | **14** | 0 | 0.3 |
| explore 30 columns | 128 | 128 | 127.9 | 128.0 |
| climb rope | 127 | 105 | 127.2 | 128.0 |
| craft iron pickaxe | 0 | 0 | 0 | 0 |
| craft gold pickaxe | 0 | 0 | 0 | 0 |
| **mean /32** | **17.98** | **15.01** | **18.23** | **25.02** |

### Inventory diagnostic (best checkpoint)

`python -m terraria_lite.dreamer.evaluate CKPT --diagnose` mirrors
`tools/policy_diagnostics.py`. It ran on short_r32 step 14.7M, on the validation
worlds with seed 54321, on CPU. The episode mean was 17.88/32, against 17.98 on the
GPU evaluation. The difference is CPU vs GPU rounding in the sampled
trajectories. Summary: `results/dreamer-2026-10/diagnostic_best.json`.

| item | mean peak | median | max |
|---|---|---|---|
| wood | 11.9 | 11 | 19 |
| stone | 120.6 | 124.5 | 306 |
| iron ore | 8.3 | 7 | 28 |
| iron bar | 0.03 | 0 | 2 |
| gold ore | 3.8 | 2 | 23 |
| gold bar | 0.01 | 0 | 1 |
| copper bar | 0.16 | 0 | 11 |

- Never 10 iron bars, never 30 wood: in 0/128 episodes.
- Iron pickaxe, gold pickaxe, iron chainmail, wood breastplate and anvil: 0 legal steps.
- Furnace: legal in 7 episodes, 116 steps; chosen 5 times (p = 0.10 when legal).
- Smelt iron: legal in 3 episodes, chosen 4 times.

At this budget the gate is the furnace, not the late stockpiling crafts. The
policy holds plenty of stone but too little wood at the right time. This matches
low-budget PPO (rep64: furnace 8.5/128 at 16.8M).

### World-model and imagination telemetry

Mask head on replay (fraction of terminal-excluded rows):

| | false-legal | false-illegal |
|---|---|---|
| short_r8 at 2.1M | 17% | 26% |
| short_r32 at 2.1M | 4.7% | 5.5% |
| short runs at 16.8M | 1.1-1.5% | 1.2-1.5% |
| long_r16 at 16.8M | 1.35% | 1.36% |

An imagined action is always legal under the mask in force (selftest), so a
false-legal mask is the only way imagination can use an illegal action. That
happens in ~1-2% of predicted masks late in training.

Imagined rewards per step, averaged over the update (long run):

| | extrinsic head | shaping head |
|---|---|---|
| at 16.8M | 0.0037 | -0.0015 |

Imagined λ-returns are about 2.0. The value comes from the extrinsic head;
the potential term is slightly negative on average, from the γΦ' − Φ
discount on held ingredients.

### What failed or limits the result

- **Budget.** The long run was stopped after 48 min, at 23.8M env steps, 3% of
  the planned budget. Every conclusion here is at ≤ 17M steps, where PPO itself is
  only at about 18. The central question (does it pass 25 and earn the stockpiling
  crafts?) is unanswered.
- **Validation instability.** Scores swing by up to 7 points between consecutive
  evaluations, for example 17.36 → 10.82 → 17.98. The low points are policies that stay
  near the surface (peak row 35) and die. Death rates are high (35-100%) against
  PPO's ~8% at convergence. Policies dive to the world bottom (row ~93) and die
  around steps 1,300-1,800.
- **Wall-clock.** Dreamer pays ~16k replayed steps per update. Even at a train ratio
  of 8 it is about 20x slower per env step than PPO's max path. Dreamer is only
  competitive per env step, and only at the low end.
- **No hyperparameter search.** These are DreamerV3 defaults (size about "M") plus three
  train ratios. Each configuration ran with 1 seed.

## Reproduce

```sh
# Mac smoke test (about 5 s): shapes, losses, masks in imagination, checkpoint round trip, evaluation
TERRARIA_LITE_LIB=<v7 lib> PYTHONPATH=python python tools/dreamer_selftest.py
# eg18 (build: make -C perf/v7 LIGHT_WINDOW=1), long-run configuration:
HIP_VISIBLE_DEVICES=<gpu> TERRARIA_LITE_LIB=$PWD/perf/v7/build-lw/libterraria.so PYTHONPATH=python \
  python tools/train_dreamer.py --out RUN --device cuda --steps 536870912 --interval 16777216 \
  --envs 1024 --sim-workers 12 --threads 4 --capacity 10000000 --batch 256 --seq-len 64 \
  --train-ratio 16 --bf16 --compile --compile-observe --potential 3 --seed 1602
python -m terraria_lite.dreamer.evaluate RUN/step-N.pt [--diagnose] --out eval.json
```

PPO paths are untouched. `git diff 409d3a0 HEAD` only adds new files
(`python/terraria_lite/dreamer/*`, `tools/*dreamer*`, this report, `results/dreamer-2026-10/`),
so default PPO training is byte-for-byte the same code. Only GPU 6 was used, with
at most 24 cores (`taskset`). `~/Projects/RL` was only read: the venv and
`builds/v7` sources. Checkpoints and raw curves stay out of git; they are under
`experiments/dreamer-v7/` on the Mac and in `~/Projects/RL-dreamer/experiments/dreamer-v7/` on eg18.
