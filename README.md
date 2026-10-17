# Terraria Lite

A small deterministic Terraria-inspired simulator in C, with terminal and SDL
frontends and a versioned RL interface. **v4 corrects core Terraria geometry** while
keeping the simulation bounded and CPU-parallel.

The current milestone has Blue Slimes, Cave Bats, chests, swords, torso armor,
rope, platforms, Cloud in a Bottle, healing, Life Crystals, campfires, and four
ordinary ores. It uses original Terraria art from your local installation.
The mechanics remain intentionally simplified.

**October 17 study launched:** [v7 progression and reward/discount protocol](V7_REWARD_PROTOCOL_2026_10_17.md)
and [launch record](V7_REWARD_LAUNCH_2026_10_17.md). Twenty-five fresh16M spatial
PPO trials (419.4M main transitions) compare a matched v4 control with v7's
equal/difficulty-weighted reward × .999/1.0 discount factorial, five paired
training seeds. Evaluation stays unweighted; reserved tests stay unused.
This is an active study, not evidence of improvement or a v7/default promotion.

**October 17 LLM harness:** [usage and replay](LLM_EVALUATION.md),
[ARC/FLE/Craftax and broader benchmark research](LLM_BENCHMARK_RESEARCH_2026_10.md).
The authorized [Sol smoke](LLM_SMOKE_2026_10_17.md) scored9/32 in256 actions
for $0.282 reported cost, with exact native replay. Future development uses
**Luna high**: the [three-world batch](LLM_LUNA_2026_10_17.md) is complete and
replay-audited for **$0.896 actual reported cost**. Scores20/19 end in death;
both reach a furnace and copper smelting. The shared conservative $2 guard
stops world3 at129 actions/5 achievements: not three full-budget episodes or
a fair fixed-budget mean. All Python/SDL replays match. Luna follow-up paused;
no more paid calls. PPO continues independently. These are public development
checks, not leaderboard scores or matched-budget PPO results. Defaults unchanged.

**New user-authorized Luna comparison:** [four harness packages on two paired
worlds](LUNA_HARNESS_STUDY_2026_10_17.md), under [a frozen protocol](LUNA_HARNESS_PROTOCOL_2026_10_17.md).
Eight independent $0.35 guards allocate $2.80 of the newly authorized $3. Test
compact context/history,4-versus16 action lists and paid-illegal-action
interruption. This supersedes the previous batch's no-further-spending status
only for these8 attempts. PPO continues independently; no defaults change.

See [FOOTPRINT_LEARNING_2026_10.md](FOOTPRINT_LEARNING_2026_10.md) for the latest
completed **503.3M-transition / 30-run** paired v4/v5 learning study, and
[CREDIT_V4_2026_10.md](CREDIT_V4_2026_10.md) for the earlier completed
356.5M-transition, five-seed deadline/credit/memory/exploration study and
[CREDIT_V4_2026_10.json](CREDIT_V4_2026_10.json) for its numeric evidence.
The earlier 247.5M-transition causal/learning study remains in
[LEARNING_V4_2026_10.md](LEARNING_V4_2026_10.md) and
[LEARNING_V4_2026_10.json](LEARNING_V4_2026_10.json).
[FIDELITY_V4.md](FIDELITY_V4.md) documents current
mechanics, regression gates and the earlier 4M comparisons; numeric evidence is in
[FIDELITY_V4.json](FIDELITY_V4.json). [ITERATION_2026_10.md](ITERATION_2026_10.md)
and [ITERATION_2026_10.json](ITERATION_2026_10.json) preserve historical v3 results.
[V2.md](V2.md) documents the underlying game contract/recipes/controls and
historical evidence; its results are intentionally not relabeled as v3.

The five-seed study completed **356,515,840 main transitions across 55 runs**,
plus 294,912 calibration transitions, under [CREDIT_V4_PROTOCOL.md](CREDIT_V4_PROTOCOL.md).
PPO uses zero future value at the inherent action deadline; the correction had
positive but noisy paired effects. Generic recurrent memory made 4M mining
more reliable, but at 16M its mean was **17.95/32** versus **17.79/32** for the
finite-target control, at about **1.41× measured wall/run**. The selected memory
policy scored **18.83/32** on its one-shot test, with **no furnace in 128 worlds**.
RND and longer-credit variants did not solve crafting. No architecture or
checkpoint default was promoted; the earlier 20.79/32 policy is preserved.

A separate playable [v5 object-scale preview](OBJECT_SCALE_V5.md) corrects chest,
Life Crystal, furnace, campfire, bench and anvil footprints using original art.
Its simulator cost gate passes; the completed paired learning study finds mixed
package-dependent effects and inconclusive five-seed non-inferiority.
The main checkout and completed PPO studies remain v4.

The original [v4/v5 cohort](FOOTPRINT_LEARNING_PROTOCOL.md) was stopped at the user's
revised 7 p.m. reporting deadline. The [audited partial report](FOOTPRINT_LEARNING_PARTIAL_2026_10.md)
covers **15 full runs / 251.7M transitions** plus preserved partial checkpoints.
Plain PPO averaged **15.85/32 on v4 versus 21.56 on v5** over three paired seeds;
furnaces rose 42/384→248/384. Spatial/recurrent packages declined over two pairs.
This is not the completed planned 503M/30-run five-seed study. No-concurrent-RL
timing confirmed a paired batch ratio of 0.9884. Those interrupted attempts and
the partial report remain preserved; tests were unused at that historical stop.
On 2026-10-12 the user authorized [completing the remaining trials](FOOTPRINT_LEARNING_COMPLETION.md).
A separate frozen completion cohort retained the 15 verified full runs, restarted the
three interrupted trials from scratch, and trained the twelve untouched trials:
**251.7M additional main transitions**. It is now **complete and audited**:
[full report](FOOTPRINT_LEARNING_2026_10.md), [audit](FOOTPRINT_LEARNING_2026_10.audit.json).
Final five-seed MLP means are **13.79→17.32/32**, furnace coverage **6.6%→38.8%**;
targets **17.68→17.07**, memory **17.76→17.05**. All three predeclared learning
non-inferiority gates are inconclusive, not proven success/failure. The frozen
paired memory selection scored **18.46/32 on v4 versus 17.02 on v5** on the
one-shot reserved test. Worlds 11,000,001–11,000,128 are consumed once per
version; exact checkpoint/Python/SDL replays passed. All workers are stopped,
the follow-up is paused, and v4/default policies remain unchanged.
[All 30 final-policy crafting diagnostics](FOOTPRINT_CRAFTING_2026_10.md) show
v5 targets/memory almost never craft benches and never reach furnace
prerequisites; successful MLP seeds demonstrate workshop learning is possible.
[Joint crafting diagnostics](CRAFTING_BOTTLENECKS_2026_10.md) now identify
simultaneous wood/station shortages rather than insufficient stone; the
[design direction](DESIGN_DIRECTION_2026_10.md) prioritizes a fair, learnable
core and permits simplifying costly or unhelpful fidelity details.

## Build and verify

**Next-step work (2026-10-12):** separate [v6/v7 previews and pilots](CORE_NEXT_2026_10.md)
fix independent pickaxe ownership/ore supply and test one-action direct inventory
selection. Mechanics/original-art checks pass; the 25.2M two-seed PPO/replay pilot
is complete, as is the separate 16.8M spatial-target control (**41.9M total**). Initial
PPO means 10.11→10.48/32 remain surface-bound; replay mean 5.47 is not an
improvement. Targets mine reliably but make no benches on either preview
(15.28→15.27/32). A larger-batch MPS/CPU-evaluation calibration offers a
promising throughput path, not yet validated learning quality. The provider-neutral
offline LLM protocol was tested without API spending at that October12 milestone;
no jobs remained running then. The October17 studies above supersede that status.
Main v4/default models and all completed studies remain unchanged.

```sh
make -j4 all lib
make terraria-px                    # SDL2 required; brew install sdl2
make check                         # deterministic mechanics + exact light oracle
make check-pixel                    # original textures + UI fixtures; local Terraria required
uv sync --extra rl
uv run python -m terraria_lite.ppo_selftest
```

## Play

```sh
./terraria-px --seed 9
./terraria-lite --seed 9           # terminal, no SDL or textures needed
```

The pixel frontend needs a Terraria installation with an `ExtractedTextures`
folder. The default local Steam location is detected; `--textures DIR` selects
another folder. No Terraria textures are copied into this repository or
redistributed. `--scale N` selects integer zoom, reduced automatically to fit
the display.

Left click mines, right click places; click recipes to craft and inventory slots
to select placeables. Keyboard controls:

| Keys | Action |
| --- | --- |
| a / d, w or space | Walk / jump |
| f, t | Attack / cycle owned swords |
| z | Open nearby chest |
| c / v / b | Lesser Healing Potion / Mushroom / Life Crystal |
| j / l / ; | Climb rope up / down / drop through platform |
| e, r, q | Cycle placeable / new world / quit |
| F2 (pixel), backtick (terminal) | Pause human play |

The world advances while you stand still. Pause to stop the clock.
`./terraria-lite --help` lists all 20 mining/placement targets and 19 recipe shortcuts.
`--lockstep` makes terminal play one action per keypress.

## RL

```python
import terraria_lite
from terraria_lite import TerrariaLite, SPEC

env = TerrariaLite()
obs, info = env.reset(seed=9)
mask = env.action_mask()
obs, reward, terminated, truncated, info = env.step(0)
env.close()
```

Gymnasium registration is `TerrariaLite-v4`: `Discrete(73)` actions and a
`float32` observation of length **2961**. The observation includes an 11×9 local
terrain/light window, visible entities, inventory, equipment, cooldowns, and
achievement history. Darkness conceals terrain and mobs. Default horizon:
3000 actions; 32 distinct achievements. Reward: +1 per newly earned achievement,
−1 on death, no progress or health shaping.

Masks encode physical/epistemic legality, not strategy. Empty-air attacks and
full-health healing remain legal; dark-cell attempts do not disclose ore.
Pick upgrades improve speed, not access to ordinary ores.
Cutting a tree harvests its connected trunk above the cut, using the starter
Copper Axe; placed wood still mines one block at a time.
The avatar occupies a 2×3 grid envelope. Trees and furniture are pass-through;
workbenches/anvils have one-way tops. Six-tile jumping, 25-tile safe falls and
400-HP Life Crystal capacity replace the earlier arbitrary constants.

```sh
uv run python -m terraria_lite.ppo_agent --steps 4194304 --seed 101 --save ppo_v4.pt
uv run python -m terraria_lite.ppo_eval ppo_v4.pt --episodes 128
uv run python -m terraria_lite.watch --policy ppo_v4.pt --best-of 8 --play
uv run python -m terraria_lite.rules       # player knowledge from the simulator tables
```

The earlier unchanged-v4 study completed **247,463,936 transitions across 28
independent runs**, including matched fresh 16M/32M trials. Its validation-selected
plain PPO checkpoint (16M, seed 101) scored **20.79/32** on 128 untouched test
worlds: stone 128/128, furnace 100/128, deaths 2/128. Shared spatial target scoring
with longer GAE traces and higher entropy was more reliable at learning mining:
two-seed final means **18.39/32 at 16M** and **19.14/32 at 32M**, versus baseline
**15.87** and **10.82**. Two seeds are exploratory; the best individual policy is
not proof of a reliable algorithm. More compute alone did not guarantee progress.

The selected checkpoint and exactly verified seed-9 replay are locally preserved
under `experiments/learning-v4-20261010.GWpaf4/selected/model.pt` and
`experiments/learning-v4-20261010.GWpaf4/selected-seed9.tape`. No model default or
default checkpoint was replaced. Validation seeds 6,000,001–6,000,128 and the
now-consumed test seeds 7,000,001–7,000,128 are recorded in the report. Future
studies must reserve a new test range rather than reuse the tooling's default.

The newer five-seed study's selected checkpoint and exactly verified 20/32
seed-9 replay are under `experiments/credit-v4-20261011.naYwbC/selected/model.pt`
and `experiments/credit-v4-20261011.naYwbC/selected-seed9.tape`. Its validation
worlds were 8,000,001–8,000,128; test worlds **9,000,001–9,000,128 are consumed**.
The completion audit verified all 55 summaries, frozen sources and 75 eligible
checkpoint hashes without rerunning the test. See
[CREDIT_V4_2026_10.audit.json](CREDIT_V4_2026_10.audit.json).

Earlier v4 4M means of **10.17/32** (plain) and **10.32/32** (separate actor/critic)
were surface-bound; these are historical comparisons, not the current best.
v3's **18.55/32** plain PPO and **19.94/32** selected test score describe a different
task. Spatial/recurrent encoders and training-only RND remain experimental;
RND is disabled by default. Current baselines use legal masks, no expert cloning
and no prerequisite shaping. Crafting remains weak, and ore supply/tool ownership
need separately versioned design fixes before claiming saturation. Historical
achievement counts belong to different tasks, not a shared leaderboard.

## Preserve and replay v1

Old checkpoints and tapes are intentionally rejected by v4. Preserve the exact
historical environment, Python package, and binaries with:

```sh
sh tools/freeze_v1.sh
PYTHONPATH=experiments/v1-frozen/python .venv/bin/python -m terraria_lite.ppo_eval OLD_POLICY.pt
```

The script archives commit `0f9170bd0571e872c1e8fea666a4a2f06cdc3ad8` without
modifying your current checkout. Historical experiment documents and legacy
expert/shaping scripts describe v1, not the current baseline. The local iteration
directory also preserves original and optimized v2 for historical evaluation.
The latest local study preserves v3 at
`experiments/fidelity-v4-20261010.5spuaF/v3`: use that Python package and SDL
binary to evaluate/replay v3, rather than the current v4 executables.

## Layout

- `include/env.h`, `tiles.h`: versioned state, actions, items, recipes, achievements.
- `src/sim.c`, `worldgen.c`, `light.c`, `obs.c`: allocation-free transition core.
- `src/capi.c`: scalar and native parallel C APIs.
- `src/render.c`, `main.c`: terminal UI; `px_render.c`, `px_main.c`: original-art SDL UI.
- `python/terraria_lite/`: binding, native batching, PPO/LSTM, evaluation and replay.
- `tools/selftest_v2.c`, `px_smoke.c`: mechanics and UI fixtures, never training demonstrations.
