# v10 generic PPO headroom study, 2026-11-11

Provisionally selected A; last paired comparisons A-3001 +4.23pp at 268,435,456 steps, A-3002 +3.50pp at 1,073,741,824 steps. This is not a definitive ranking.

## Frozen protocol

- Engine `4ede178`; library SHA256 `f6413078a1684d54b65e5f70f028e59a5ee1e95670d093a03fdee68d1e30e971`; immutable input manifest `17e1607359934a03efe0adba326b8e37d05ef22eb8f9134428f2a91334d26686`.
- 93 actions, 40 weighted achievements, max145, 11×9 view, 10,000-step episodes; no engine/interface/observation/mask/evaluation-reward changes.
- Cached generic controls3001/3002 reused with exact trainer/package hashes. No fresh control job, BC, task-specific shaping, curriculum, or reserved test-world evaluation.
- Targets h128/depth2/cell32,487896 parameters; γ.9999, LR.0003 linearly annealed over1,073,741,824 steps, novelty.01, unimix.01,4epochs×16minibatches, batch131072/minibatch8192.
- A: entropy.01 (baseline.03). B: λ.995,512envs×256rollout (baselineλ.99,1024×128); entropy.03. Every other baseline knob is unchanged.
- GPU collect/train; CPU async validation128worlds23000001–23000128, sampler54321, every134,217,728steps; native-autoreset/compact/compile/bf16/fusedAdam/compile-all safe eager bf16 backward,4threads/12simworkers.
- Actual worker runtime: amd-unified/gpt-6.1-sol/high, no fallback, as observed by parent session metadata.

## Ownership and budget

- Common GPU-work window began `2026-11-11T20:34:39.151198+00:00`; immutable hard deadline `2026-11-11T22:04:39.151198+00:00`. Detached watchdog enforces only owned process groups, starting termination10s early.
- HIP6 → PCI0000:e8:00.0 / amd-smiGPU6; HIP7 → PCI0000:98:00.0 / amd-smiGPU5. Trainers use CPUs300–323 and324–347 on NUMA1.
- Remote durable evidence: `/home/mvohl/Projects/RL-headroom-20261111`. Commands, PID/PGID/start-ticks and logs are in the JSON/remote evidence.
- Startup supervision failure preserved: `NameError("name 'j' is not defined")`. Initial process attempts terminated before any evaluated checkpoint; training steps are unknown, not assumed zero. Both attempts and shutdown times are retained in JSON.
- Recovery authorization: Main explicitly authorized one operational retry each for logical A3001/B3001; max3 counts logical trial identities, failed process attempts retained; original deadline unchanged; original deadline unchanged.
- Screen supervisor exception preserved: `TypeError("dict() got multiple values for keyword argument 'time'")`. A duplicated `time` keyword in event logging invoked ownership-scoped shutdown after the screen decision was written. The final source fixes this collision; the running confirmation path did not invoke that screen event.
- Parent promotion amendment: Main authorized planned third logical trial A3002 on HIP6 now; original common deadline, no restart A3001/B3001, incomplete checkpoints valid evidence. A3001 remains screen-only; no weights-only reconstruction of its Adam/RNG/LR state was attempted.
- The original 1.2×fresh-confirmation completion guard was too conservative (A missed it by about12s despite ~67min remaining). It was not evidence of learning failure or hard budget impossibility. Parent approved only the planned A3002 confirmation; original selection/shutdown evidence remains archived.
- Logical candidate jobs=3; actual process attempts=5 including the two explicitly authorized initialization retries. No additional condition or seed.
- Screen decision: Parent promotion amendment: positive A screen; collect planned A3002 confirmation within original deadline, no A3001 restart; winner=A; live-state continuation=False, checkpoint restart=False.
- A-3001 at the last jointly observed available-time comparison (872s): +4.23pp versus paired control. Observed score-per-time advantage; not a robust efficiency ranking.
- B-3001 at the last jointly observed available-time comparison (1066s): -3.20pp versus paired control. No observed advantage at this snapshot; not a robust efficiency ranking.
- A-3002 at the last jointly observed available-time comparison (3279s): +4.79pp versus paired control. Observed score-per-time advantage; not a robust efficiency ranking.
- GPU shutdown: `2026-11-11T21:54:28.679480+00:00`; deadline respected=True; candidate occupied-job-hours upper bound=1.5163971951935027; zero fresh controls/reserved test worlds.

## Per-seed results

| Trial | Status / stop reason | Last evaluated steps | Score % | Paired control % | Difference pp | Checkpoint / available seconds |
|---|---|---:|---:|---:|---:|---:|
| A-3001 | stopped: common budget or supervisor shutdown | 268,435,456 | 33.79 | 29.55 | +4.23 | 832.7 / 871.1 |
| B-3001 | stopped: common budget or supervisor shutdown | 268,435,456 | 26.35 | 29.55 | -3.20 | 1030.3 / 1065.0 |
| A-3002 | finished: normal full-budget completion | 1,073,741,824 | 36.71 | 33.21 | +3.50 | 3240.5 / 3278.0 |

Full1B means an observed1,073,741,824-step evaluation only. Partial/stopped runs are not extrapolated.

Only A3002 can have a full1B result; A3001 was stopped at the screen. There is no two-seed full1B mean/ranking. Compare both A seeds at256Mi, and A3002 against its paired cached control at later observed checkpoints.

A at matched256Mi: A-3001 33.79% vs 29.55% (+4.23pp), A-3002 32.03% vs 21.62% (+10.41pp); mean paired difference +7.32pp. This is early-budget evidence, not a full1B average.

## Matched-step and matched-time evidence

| Trial | Steps | Candidate / control % | Difference pp | Checkpoint seconds candidate / control |
|---|---:|---:|---:|---:|
| A-3001 | 134,217,728 | 29.75 / 23.91 | +5.85 | 427.1 / 412.5 |
| A-3001 | 268,435,456 | 33.79 / 29.55 | +4.23 | 832.7 / 822.8 |
| B-3001 | 134,217,728 | 18.75 / 23.91 | -5.16 | 522.9 / 412.5 |
| B-3001 | 268,435,456 | 26.35 / 29.55 | -3.20 | 1030.3 / 822.8 |
| A-3002 | 134,217,728 | 29.98 / 18.81 | +11.17 | 398.7 / 403.2 |
| A-3002 | 268,435,456 | 32.03 / 21.62 | +10.41 | 801.8 / 807.9 |
| A-3002 | 402,653,184 | 34.13 / 30.47 | +3.66 | 1200.9 / 1203.7 |
| A-3002 | 536,870,912 | 33.41 / 29.83 | +3.58 | 1609.7 / 1621.5 |
| A-3002 | 671,088,640 | 34.30 / 33.36 | +0.95 | 2016.9 / 2034.1 |
| A-3002 | 805,306,368 | 35.23 / 32.61 | +2.62 | 2415.7 / 2447.5 |
| A-3002 | 939,524,096 | 34.84 / 31.92 | +2.92 | 2826.6 / 2858.1 |
| A-3002 | 1,073,741,824 | 36.71 / 33.21 | +3.50 | 3240.5 / 3276.2 |

| Trial | Available-time limit s | Latest observed steps candidate / control | Score candidate / control % | Difference pp |
|---|---:|---:|---:|---:|
| A-3001 | 470 | 134,217,728 / 134,217,728 | 29.75 / 23.91 | +5.85 |
| A-3001 | 600 | 134,217,728 / 134,217,728 | 29.75 / 23.91 | +5.85 |
| A-3001 | 872 | 268,435,456 / 268,435,456 | 33.79 / 29.55 | +4.23 |
| B-3001 | 566 | 134,217,728 / 134,217,728 | 18.75 / 23.91 | -5.16 |
| B-3001 | 600 | 134,217,728 / 134,217,728 | 18.75 / 23.91 | -5.16 |
| B-3001 | 1066 | 268,435,456 / 268,435,456 | 26.35 / 29.55 | -3.20 |
| A-3002 | 600 | 134,217,728 / 134,217,728 | 29.98 / 18.81 | +11.17 |
| A-3002 | 840 | 268,435,456 / 134,217,728 | 32.03 / 18.81 | +13.22 |
| A-3002 | 1200 | 268,435,456 / 268,435,456 | 32.03 / 21.62 | +10.41 |
| A-3002 | 1239 | 402,653,184 / 268,435,456 | 34.13 / 21.62 | +12.51 |
| A-3002 | 1648 | 536,870,912 / 402,653,184 | 33.41 / 30.47 | +2.94 |
| A-3002 | 1800 | 536,870,912 / 536,870,912 | 33.41 / 29.83 | +3.58 |
| A-3002 | 2055 | 671,088,640 / 536,870,912 | 34.30 / 29.83 | +4.47 |
| A-3002 | 2400 | 671,088,640 / 671,088,640 | 34.30 / 33.36 | +0.95 |
| A-3002 | 2454 | 805,306,368 / 671,088,640 | 35.23 / 33.36 | +1.87 |
| A-3002 | 2865 | 939,524,096 / 805,306,368 | 34.84 / 32.61 | +2.23 |
| A-3002 | 3000 | 939,524,096 / 939,524,096 | 34.84 / 31.92 | +2.92 |
| A-3002 | 3279 | 1,073,741,824 / 939,524,096 | 36.71 / 31.92 | +4.79 |

JSON also includes checkpoint-write-time comparisons. Cached controls shared HIP7; wall-time comparisons include that limitation.

## Behavior and stability

- A-3001: death=0.477, peak-depth=117.2, tail-after-last-achievement=3397.4; entropy=2.968, KL=0.00453, clip=0.02671, EV=0.99820.
  Late-achievement hits/128: craft iron pickaxe=0, craft gold pickaxe=0, craft iron chainmail=0, return to surface=0, defeat Demon Eye=0, collect lens=0, hold 6 lenses=0, craft Suspicious Looking Eye=0, defeat the Eye of Cthulhu=0.
  Matched-step control: death=0.523, peak-depth=111.3, tail-after-last-achievement=2193.7; craft iron pickaxe=0, craft gold pickaxe=0, craft iron chainmail=0, return to surface=0, defeat Demon Eye=0, collect lens=0, hold 6 lenses=0, craft Suspicious Looking Eye=0, defeat the Eye of Cthulhu=0.
  Mid-progression hits candidate/control: craft anvil=39/22, craft metal sword=24/10, craft wood breastplate=119/107, smelt silver=84/65, smelt gold=59/40, survive a night=107/111.
  CPU final/checkpoint diagnostic: night-deaths=20, attack-share=12.109%, place-share=10.079%, place-outcomes={'placed': 71390, 'failed': 22776, 'unknown': 0}; diagnostic score=33.79%. All action counts/probabilities, inventory peaks and layer fractions are in JSON.
- B-3001: death=0.438, peak-depth=108.2, tail-after-last-achievement=1833.8; entropy=3.258, KL=0.00444, clip=0.01624, EV=0.99181.
  Late-achievement hits/128: craft iron pickaxe=0, craft gold pickaxe=0, craft iron chainmail=0, return to surface=0, defeat Demon Eye=0, collect lens=0, hold 6 lenses=0, craft Suspicious Looking Eye=0, defeat the Eye of Cthulhu=0.
  Matched-step control: death=0.523, peak-depth=111.3, tail-after-last-achievement=2193.7; craft iron pickaxe=0, craft gold pickaxe=0, craft iron chainmail=0, return to surface=0, defeat Demon Eye=0, collect lens=0, hold 6 lenses=0, craft Suspicious Looking Eye=0, defeat the Eye of Cthulhu=0.
  Mid-progression hits candidate/control: craft anvil=5/22, craft metal sword=0/10, craft wood breastplate=91/107, smelt silver=36/65, smelt gold=22/40, survive a night=119/111.
  CPU final/checkpoint diagnostic: night-deaths=24, attack-share=13.105%, place-share=15.988%, place-outcomes={'placed': 111241, 'failed': 51916, 'unknown': 0}; diagnostic score=26.35%. All action counts/probabilities, inventory peaks and layer fractions are in JSON.
- A-3002: death=0.609, peak-depth=122.4, tail-after-last-achievement=2834.9; entropy=2.931, KL=0.00004, clip=0.00000, EV=0.99722.
  Late-achievement hits/128: craft iron pickaxe=0, craft gold pickaxe=0, craft iron chainmail=0, return to surface=0, defeat Demon Eye=0, collect lens=0, hold 6 lenses=0, craft Suspicious Looking Eye=0, defeat the Eye of Cthulhu=0.
  Matched-step control: death=0.547, peak-depth=115.7, tail-after-last-achievement=2596.8; craft iron pickaxe=0, craft gold pickaxe=0, craft iron chainmail=0, return to surface=0, defeat Demon Eye=0, collect lens=0, hold 6 lenses=0, craft Suspicious Looking Eye=0, defeat the Eye of Cthulhu=0.
  Mid-progression hits candidate/control: craft anvil=71/48, craft metal sword=42/22, craft wood breastplate=126/116, smelt silver=101/81, smelt gold=82/58, survive a night=100/114.
  CPU final/checkpoint diagnostic: night-deaths=40, attack-share=11.754%, place-share=9.160%, place-outcomes={'placed': 58926, 'failed': 17267, 'unknown': 0}; diagnostic score=36.71%. All action counts/probabilities, inventory peaks and layer fractions are in JSON.
  Matched1B control night-deaths=20; candidate death-rate change=+0.062. Higher score is not a survival win; the late-frontier hit counts above distinguish mid-tier gains from new endgame progression.

A3002 observed full1B completion: 3278.4s versus cached control 3314.3s. This small timing difference is not an isolated throughput claim; the score gain is evaluated at matched steps and the tables show matched-time evidence.

## Limits

- Selection uses validation worlds, not reserved test worlds.
- One screen seed and at most two selected seeds cannot establish a definitive ranking or robust CI.
- Cached control timing used two trainers on HIP7; candidates use one trainer per GPU. Timings are not exact compute parity.
- Asynchronous checkpoint-write time and score-availability time are distinguished; no interpolation or extrapolated 1B score.
- Longer-credit changes are a package, not an isolated lambda or rollout effect.

- Prior width/memory/longer-budget studies were negative; no capacity or algorithm grid was launched. Release Gate1 remains open; no defaults/checkpoints promoted into the project.
- No builds, lint, offline tests or formatters. Exercised checks were provenance/runtime protocol parity, actual process/GPU inspection, scheduled validation and bounded CPU diagnostics.

Compact evidence: `RL_HEADROOM_V10_2026_11.json`. Reproduction/supervision: `tools/headroom_study.py`; evidence exporter: `tools/headroom_report.py`.
