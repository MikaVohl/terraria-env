# October 2026 iteration — faster simulation, coherent harvesting, stronger PPO

Historical v3 iteration; current fidelity work is in [FIDELITY_V4.md](FIDELITY_V4.md).
This report's game: **v3**, `TerrariaLite-v3`. Same fixed universe as v2: 31 inventory
types, 19 recipes, 53 actions, 32 achievements, 2961 observation values, and a
3000-action budget. Geography and loot vary by world seed. The previous
[v2 report](V2.md) and its JSON evidence remain historical, not rewritten.

**68,222,976 completed training transitions** in this iteration, excluding
interrupted/failed pilots. The validation-selected policy scores **19.94/32**
on 128 reserved test worlds. Detailed numeric evidence, all achievement rates,
curves, source hashes and asset provenance: [ITERATION_2026_10.json](ITERATION_2026_10.json).

This iteration separates three questions: can we simulate the **same** game
faster, does a Terraria-like harvesting rule improve the **game**, and which
general-purpose learning changes improve **PPO**? Cross-version achievement
counts are not an apples-to-apples algorithm leaderboard.

## Simulator: exact optimization before game changes

Terrain edits previously invalidated a full-world lighting cache. Mining is
common, so expensive full-map propagation kept returning during rollouts.
The new implementation updates the edited cell, affected sunlight column, and
neighboring light field until it reaches the same fixed point as the reference
propagator. Both source removal and opacity changes are covered. Reset and
bulk fixture edits still use the full reference computation. No simulation
events are skipped and no lighting/visibility rules are approximated.

The native batch API now optionally encodes one-hot terrain, light and status
directly into the caller's float32 observation buffer. This removes Python-side
strided extraction/encoding. The raw native API is retained and tested.

Measured on the M5 Pro MacBook, with an active desktop and concurrent training:
262,144 transitions per repeat, three repeats, 64 worlds, uniform legal actions,
and subsequent episode resets included. Initial world construction is excluded.
Both comparisons below use **unchanged v2 rules**; the C and Python harnesses
use different samplers, so compare within a row, not across harnesses.

| Harness | Original v2 | Optimized v2 | Speedup |
| --- | ---: | ---: | ---: |
| Single-thread C: mask, step, observe, reset | 48,777 steps/s | 1,060,127 steps/s | 21.73× |
| Native Python batch, 4 workers, encoded observations | 135,020 steps/s | 843,494 steps/s | 6.25× |

Incremental lighting alone reached 623,507 batched steps/s; direct native
encoding produced the remaining gain. Env state grew from 38,576 to 38,704
bytes, only 128 bytes per world for sunlight cutoffs. The local queue uses
bounded stack storage, not per-step heap allocations.

Independent correctness evidence:

- **24,000 arbitrary tile/source edits** exactly match full-map reference light.
- **64,000 scalar/native transitions** agree on observations, masks, rewards,
  endings and info, across 1/2/4/8 workers, including resets.
- Raw NumPy encoding and direct C encoding agree bit for bit.
- Original and optimized v2 produced the same digest for **30,032 transitions**:
  `dc56bc86ba953de9b110b2b40c31c0c42c7b2bb0202bc351175a18a17b19bb03`.
- A matched 1,048,576-step PPO run produced **bit-identical learned weights**
  to the earlier v2 seed-101 checkpoint.
- AddressSanitizer and UndefinedBehaviorSanitizer pass mechanics/invariants and
  the independent light-edit suite.

Current v3 probes reached 1.10M core steps/s and 1.01M native batched steps/s;
state is 38,712 bytes. These are a different game workload and are **not** the
basis for the same-task speedup claim. Neither probe includes neural training.

## Game design: tree felling, not a gathering reward

The four-million-step v2 policy's mean peak wood was only **1.27**, maximum 4.
Workbench crafting was never legal in its 128 validation worlds. A policy
cannot learn a recipe action it never gets to attempt.

In [Terraria](https://terraria.wiki.gg/wiki/Tree), cutting a trunk removes the
tree above the cut. v2 instead required a separate action for each trunk block.
v3 applies the connected-tree rule: cutting the base harvests the connected
trunk and clears its decorative crown. Cutting higher leaves a lower stump.
Each removed trunk cell yields exactly one wood. Placed wood remains ordinary
one-cell mining. Generated trees retain their existing 4–6-trunk-cell sizes.

The real starter [Copper Axe](https://terraria.wiki.gg/wiki/Copper_Axe), original
item ID 3506, is implicit starting equipment like the pickaxe. Directional
mining uses the axe on a tree, with a three-action cooldown unaffected by pick
upgrades. This adds neither strategic masks nor an automatic goal planner.
Recipes, world generation, reward weights and achievement definitions did not
change. Because transition behavior changed, the environment version increased
to **3** even though action/observation dimensions stayed the same.

Three fresh plain-PPO seeds at 4,194,304 steps reached **18.55/32** final mean
achievements (sample standard deviation across training seeds **0.99**).
Workbench hits were 128/128, 128/128 and 126/128. The matched v2 seed-101 run
reached 17.31 with no workbench or furnace. This indicates improved early
progression under the new rules, not an algorithm improvement across versions.

The v3 seed-202 final policy's mean peak wood was **11.97**, median 12, max 15;
workbench crafting was legally available in all 128 worlds. Wood gathering is
no longer the only progression barrier. Furnaces, station placement and later
crafting remain unreliable. Trees are still simplified grid objects, not a
faithful implementation of Terraria collision, growth or drop quantities.

## Original textures and human play

Two incorrect asset uses were corrected:

- Forest trunks now use **Tiles_5**, not Tiles_191 (Living Wood). Three original
  20×20 bark frames are fit to the simulator's 16px grid; canopy uses Tree_Tops_0.
- NPC_1 is a grayscale source sheet. Blue Slimes were gray because their real
  color passes were missing. The local installed Terraria.exe's SetDefaults,
  GetAlpha, GetColor and DrawNPCDirect IL were inspected. The daylight base pass
  is RGBA `(80,80,80,80)` and the blue overlay `(0,80,255,100)`; both now use the
  original NPC pixels. Bat art remains original NPC_49, five 44×32 frames.

The SDL frontend displays the original Copper Axe while chopping, in the swing
and HUD; terminal status also identifies the axe. Harvest messages report wood
yield. Equipment, all 31 inventory icons, 19 recipe hit targets, three armor
variants and tree before/after states are exercised by pixel fixtures. Their
screenshots were visually inspected, not merely checked for file existence.

`tools/asset_audit.py` records SHA256 and PNG dimensions for **72 original asset
files**, the renderer source and local Terraria assembly. No textures were
copied into the repository or redistributed. Original source pixels do not
make this a pixel-identical Terraria renderer: crops, scaling, player palette,
grid physics, SDL blending and lighting remain deliberate simplifications.

## PPO experiments

All studies below start from scratch, with **legal masks and no demonstrations,
behavior cloning, expert planner or prerequisite shaping**. Base training:
64 environments × 128 steps, four PPO epochs/four minibatches, gamma .999,
GAE lambda .95, entropy .01, LR .0003 linearly annealed, CPU with six Torch
threads. Evaluation uses 128 fixed validation worlds (2,000,001–2,000,128),
3000 actions, stochastic legal policies with sampler seed 54321.

Alternative general architectures are now trainable/evaluable/replayable:

- `cnn`: shared spatial convolutions plus global-state MLP.
- `tokens`: shared per-cell dense features plus a global-state MLP; no recipe
  features or selected-item emphasis.
- `separate`: independent actor and critic MLP trunks instead of shared features.

Optional [Random Network Distillation](https://arxiv.org/abs/1810.12894) supplies
observation-prediction novelty during training. It considers all observed
fields, never selects objectives, and never changes evaluation reward. Its
coefficient decays to zero during the first half of training. This is an
**intrinsic training reward**, not an unshaped run; it remains off by default.
The balanced variant rescales whole observation modalities by dimensionality.

### Unchanged v2 learning controls

Final validation scores; 4,194,304 steps unless explicitly stated:

| Run | Achievements / 32 | Death rate | Furnace worlds / 128 |
| --- | ---: | ---: | ---: |
| Plain MLP, seed 101 | 17.31 | 14.1% | 0 |
| MLP, lambda .99 / entropy .03 | 14.98 | 20.3% | 0 |
| Shared-cell model, .99 / .03 | 13.16 | 25.0% | 0 |
| MLP + RND .05, .99 / .03 | 12.88 | 29.7% | 0 |
| MLP + balanced RND .01, .95 / .01 | 14.20 | 13.3% | 0 |
| CNN on MPS, 256 envs, .99 / .03 | 14.19 | 25.8% | 0 |
| Plain MLP, **16,777,216 steps** | 18.71 | 8.6% | 25 |

The sixteen-million-step run took **1053.6 seconds (17.6 minutes)** including
four validations, while other experiments were running. Its twelve-million
checkpoint scored 18.88, with workbench 127/128 and furnace 37/128. Thus the old
harvesting rule is not an absolute learnability barrier: longer training learns
crafting, but more transitions do not guarantee monotonic retained proficiency.

The CNN trial also changes batch size and device, so it does not isolate the
effect of architecture. CPU convolution pilots were interrupted after profiling
very slow backward kernels; an earlier balanced-RND trial failed on a NameError
and was fixed/rerun in a fresh directory. Neither is silently counted as a
completed learning experiment. MPS categorical sampling uses CPU sampling to
avoid the observed device multinomial/legal-support issue.

### Matched v3 experiments

| 4,194,304-step run | Final achievements / 32 | Death rate | Furnace worlds / 128 |
| --- | ---: | ---: | ---: |
| Plain MLP, seed 101 | 19.16 | 13.3% | 40 |
| Plain MLP, seed 202 | 19.08 | 7.8% | 21 |
| Plain MLP, seed 303 | 17.41 | 14.1% | 4 |
| Shared-cell model, seed 101 | 19.09 | 18.0% | 33 |
| Independent actor/critic, seed 101 | 20.27 | 18.0% | 72 |
| Independent actor/critic, seed 202 | 19.62 | 10.2% | 19 |

Independent trunks improve both matched training seeds: **+1.11** and **+0.54**
achievements. Their two-seed mean is **19.94**, versus **19.12** for plain MLP
on those same two seeds. Both independent-trunk policies have slightly higher
death rates. The gain costs more parameters and wall time; it is not evidence
of a win at equal compute. With only two seeds and this compute/survival tradeoff,
`--architecture separate` is a promising option, not a replacement default.
Plain MLP remains the baseline for comparisons.

Curves matter: plain seed 202 peaked at 19.52 at two million steps, then finished
at 19.08. Selection must use declared validation criteria, not training-tail
scores or the test set. Uniform legal random scores **5.34/32**, death **95.3%**,
on the same v3 validation worlds.

### Frozen selection and reserved test

Selection considered 24 checkpoints from the three plain MLP seeds, shared-cell
seed 101, and independent-trunk seeds 101/202. Criterion: highest validation
mean; ties prefer lower death rate, fewer steps, then run name. All candidate
checkpoint hashes and the selected policy were saved **before** test evaluation.

Selected: independent actor/critic seed 101 at **4,194,304 steps**, validation
**20.27/32**. One evaluation on reserved worlds **3,000,001–3,000,128**, sampler
54321, gave **19.94/32**, median 20, max 25, mean return 19.73, death **20.3%**.
Workbench and chest opening each occurred in all 128 worlds; furnaces 68/128,
anvil 1/128. No metal sword, armor or upgraded-pick achievement was reached.
The model has learned broad early-game play, not near-saturation.

This split is now consumed. Do not tune against it or repeatedly pick a different
model after inspecting its outcome. Selection uses several models/checkpoints,
so validation-best is selection-biased; the separately reported test is important.
The independent-trunk advantage has two training-seed checks, not a definitive
large-sample algorithm ranking. No comparative test sweep was performed.

Ready-to-watch local policy and a deterministic replay:

```sh
PYTHONPATH=experiments/fidelity-v4-20261010.5spuaF/v3/python .venv/bin/python -m terraria_lite.watch --policy experiments/iteration-20261010/v3-selected/model.pt --seed 9 --play
./experiments/fidelity-v4-20261010.5spuaF/v3/terraria-px --watch experiments/iteration-20261010/selected-demo.tape
```

The selected seed-9 demonstration reaches 20 achievements in 3000 actions and
was verified in the C frontend. Watch defaults to one Torch thread for
single-world inference and exposes a separate reproducible policy sampling seed.

## Current bottlenecks and next decisions

Simulation is no longer the dominant measured training phase. For v3 plain
seed 202, collection took 80.3 seconds, optimization 211.0 seconds, plus
validation/reporting; optimization was **72.4%** of the two training phases.
Collection includes policy inference, sampling, transfers and reset logic, not
just C stepping. I/O does not occur per simulated step. In CPU runs, dense
matrix/backward work and small-batch inference are the next throughput targets.
Do not infer an equal end-to-end training speedup from the 6.25× simulator gain.

64 simulator states use about 2.36 MiB; the default float32 rollout observation
buffer uses about 92.5 MiB. The 48GB machine is not limited by these buffers.
CNN on MPS can be much faster than the observed CPU convolution path, but its
batch/device/learning behavior needs separate calibration. An MI350X experiment
should begin with a measured larger-batch learner/inference pilot, not assume
that porting the tiny CPU rollout call to a GPU eliminates the new bottleneck.
Native worker parallelism currently uses macOS dispatch; other platforms retain
the correct serial fallback. A Linux cluster port must explicitly add/calibrate
its rollout worker pool rather than assume this API already runs parallel there.

The remaining capability barriers are station-dependent chains, survival versus
resource collection, and retention of rare crafting behavior. Selected-policy
diagnostics on validation worlds show furnace crafting legal for only **117
action opportunities in 72 worlds**, and selected **114** times: recognizing
an available furnace recipe is not its main problem. Reaching the combined
resource/station prerequisites is. Anvil crafting becomes legal in only one
world; metal equipment/upgraded-pick recipes never become legal. Peak wood
averages 13.45 and reaches at most 21, below the breastplate's 30-wood cost.

The same policy crafts **372 workbenches** over 128 worlds. Repeated stations
consume wood without repeating the achievement reward. Keep that action legal:
this is a learned resource-allocation problem, not a reason for a strategic mask
that forbids an unhelpful recipe. Opportunity counts do not isolate every cause
of missing prerequisites; targeted station/resource diagnostics are the next
analysis step, not a justification for scripted gathering behavior.

Keep v3's world,
recipes and achievements fixed for the next algorithm study. Test larger
budgets, independent actor/critic features and general memory before adding
strategic masks, demonstrations or scripted subgoals. More early-game content
can follow a stable benchmark revision; it need not require abandoning bounded
entities or native parallel simulation. The LLM API benchmark remains future
work: its player-knowledge export is present, the runner is not implemented.

## Regression thresholds and reproduction

Hard gates for accepting simulator changes: zero mismatches against scalar/full
lighting oracles; deterministic resets/replay; physical-only masks; finite
policy gradients; correct truncation bootstrapping; incompatible versions
rejected; sanitizers clean. Required original assets must load without substitute
art. Test fixtures are not training demonstrations.

Performance gate: use the **same frozen version**, hardware, sampler, cohort,
worker count and three-repeat timing protocol. A median regression over 10%
requires an explanation and an isolated rerun; desktop contention invalidates
a strict absolute steps/s CI threshold. Preserve raw timings. A different game
version cannot pass this gate merely by becoming easier or skipping behavior.

Learning gate: fixed-budget/final and validation-best scores are both reported,
with per-achievement rates and deaths. A single best seed is exploratory, not a
robust algorithm win. Defaults require matched multiple-seed evidence, and
equal-step results must not be called equal-compute results. The reserved test
is evaluated once **after** validation selection; no tuning against that score.

```sh
make -j4 all lib terraria-px
make check
make check-pixel                   # local original Terraria textures required
uv run python -m terraria_lite.ppo_selftest
uv run python tools/iterate_ppo.py --out experiments/NEW_RUN --seed 101 --steps 4194304
uv run python tools/iterate_ppo.py --out experiments/NEW_SEPARATE --seed 101 --architecture separate
uv run python tools/v2_benchmark.py --steps 262144 --envs 64 --workers 4
```

Local artifacts are in `experiments/iteration-20261010/`: protocols recorded
before training, package/library hashes, source snapshots, checkpoints, full
curves, individual episodes, diagnostics and original-asset audit. The exact
starting v2 is preserved in `baseline/`; optimized unchanged v2 is preserved in
`v2-optimized/`, with matching Python packages and native libraries. For example:

```sh
PYTHONPATH=experiments/iteration-20261010/v2-optimized/python .venv/bin/python -m terraria_lite.ppo_eval experiments/iteration-20261010/mlp16m-101/step-16777216.pt
```

v3 rejects old checkpoints and tapes even if their tensor dimensions match.
Current representative Python→SDL replay was verified exactly for 3000 actions,
21 achievements, return 21 and final health 47. Earlier documents and the user's
existing experiment notes are preserved; changes remain uncommitted for review.
