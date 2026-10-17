## Active study — October 17, 2026

The [v7 reward/discount protocol](V7_REWARD_PROTOCOL_2026_10_17.md) is launched:
25 fresh16M runs, five paired seeds, 419,430,400 main transitions. Compare v4
equal/.999 with v7 equal/difficulty × discount.999/1.0 using the same spatial
target package and unweighted evaluation. Frozen snapshots, preflight evidence,
PIDs and report locations are in the [launch record](V7_REWARD_LAUNCH_2026_10_17.md).
No reserved evaluation, automatic promotion, extra algorithms or gameplay edits.
Next: audit all25 final runs and paired factorial effects, inspect crafting
diagnostics, then decide whether incentives or discounting warrant adoption.
Do not treat unfinished curves or checkpoints as independent seeds.

## Historical plan and completed evidence

Historical v1 plan. The combat/exploration contract is in [V2.md](V2.md);
the v3 iteration is in [ITERATION_2026_10.md](ITERATION_2026_10.md).
Current v4 fidelity changes and remeasurements are in [FIDELITY_V4.md](FIDELITY_V4.md).
The earlier completed credit sequence is in [CREDIT_V4_2026_10.md](CREDIT_V4_2026_10.md):
356,515,840 main transitions across 55 runs with five paired training seeds.
Memory stabilized early mining but did not materially separate from the target
control at 16M (17.95 versus 17.79/32), and the selected policy's fresh test was
18.83/32 with zero furnaces. RND and longer-credit conditions did not solve
progression. The finite-deadline objective correction is retained; no default
architecture/checkpoint is promoted. Test worlds 9,000,001–9,000,128 are consumed.
The earlier 247.5M sequence and its 20.79/32 policy remain preserved in
[LEARNING_V4_2026_10.md](LEARNING_V4_2026_10.md).

Joint resource/station diagnostics and no-concurrent-RL footprint timings are
now completed in [CRAFTING_BOTTLENECKS_2026_10.md](CRAFTING_BOTTLENECKS_2026_10.md).
The newer policy lacks both wood and a nearby bench on 96.1% of its
stone-sufficient pre-furnace actions. The footprint simulator gate passes again.
The original v4/v5 cohort was **stopped at the user deadline**, under
[FOOTPRINT_LEARNING_PROTOCOL.md](FOOTPRINT_LEARNING_PROTOCOL.md): 30 runs,
503.3M planned main transitions, three packages, five paired seeds each.
The user shortened completion to 7 p.m.; workers stopped at 6:52 p.m. Edmonton
on 2026-10-11. [Audited partial results](FOOTPRINT_LEARNING_PARTIAL_2026_10.md)
cover 15 complete runs, three interrupted and twelve unstarted. Plain PPO rose
15.85→21.56/32 over three pairs; spatial/recurrent scores declined over two.
Do not interpret the time-limited subset as the completed 30-run protocol or
consume reserved tests for it. Frozen sources and trial order are unchanged.
At that stop the five-seed protocol was unfinished; this partial history remains
unchanged. The [v5 preview](OBJECT_SCALE_V5.md) is still not promoted.

**2026-10-12 update:** the user authorized running the remaining trials.
[Completion is audited](FOOTPRINT_LEARNING_COMPLETION.md) in a separate frozen
cohort: 15 completed results retained without retraining, three interrupted
trials restarted from scratch, twelve unstarted trials trained under the same
settings. No optimizer-state resume or warm start; old partial evidence stays
preserved. The earlier time cutoff is superseded. Final selection/test/diagnostic
stages executed after all 30 complete results were available. The
[completed 503.3M report](FOOTPRINT_LEARNING_2026_10.md) finds MLP 13.79→17.32/32
and furnace 6.6%→38.8%, targets 17.68→17.07, memory 17.76→17.05. None supports
the exploratory five-seed non-inferiority gate; all are inconclusive. The
validation-selected paired memory seed scored 18.46 versus 17.02 on one-shot
tests. Test worlds 11,000,001–11,000,128 are now consumed once per version.
All 30 final-policy diagnostics and exact checkpoint/Python/SDL replays passed
the [artifact audit](FOOTPRINT_LEARNING_2026_10.audit.json). No workers or new
experiments run; follow-up paused and main v4/model defaults unchanged.

[DESIGN_DIRECTION_2026_10.md](DESIGN_DIRECTION_2026_10.md) sets the working
priority: a fair learnable core, meaningful strategic diversity, learning
efficiency, then detail-level fidelity. Neutral direct inventory selection is
a proposed independent interface experiment; tool ownership and necessary
resource-supply fixes remain separate versioned changes. Generic replay or
predictive learning is a proposed next agent track, not part of the completed
footprint comparison. Do not pool future game changes with frozen studies.

Inspiration: [Craftax](https://craftaxenv.github.io/)

**Authorized next steps, 2026-10-12:** [CORE_NEXT_2026_10.md](CORE_NEXT_2026_10.md)
records separate v6/v7 implementations, regression tests, simulator/CPU/MPS
measurements, a completed 25.2M exploratory pilot and completed 16.8M follow-on
spatial-target control (41.9M total). Initial MLP policies remain surface-bound; replay is
not a demonstrated improvement. V6 fixes tool ownership and
necessary ore supply atop v5; v7 independently adds direct selection. Generic
uniform n-step Double DQN is a replay reference, not a world-model port or a
causal replay ablation. No LLM calls: the initial JSON-lines harness is offline.
Do not promote game/method defaults from two-seed pilots, reuse reserved tests,
or change the frozen pilot sources. Targets mine but craft no benches; direct
selection alone is insufficient. Large scaling runs need a fresh schedule and
a better prerequisite-learning mechanism. Bigger-batch MPS training with CPU
checkpoint evaluation is calibrated, not learning-quality validated. All workers
stopped; reserved tests unused.

Plan:
1. Write terraria-lite in C
2. Train PPO on the game
3. Iteratively optimize to run faster and fix exploits
4. Connect an LLM as a benchmark performance
	1. See https://terrariabench.com/

Scope of game:
- **World:** 128 wide × 96 deep, single biome. Surface around y=30, dirt layer, stone layer, ores by depth. Agent sees a local window (Craftax uses 9×7). Vertical layering gives you a depth-gated tech tree for free.
- **Tiles (~12):** air, dirt, grass, stone, tree/wood, copper ore, iron ore, torch, workbench, furnace, placed block, bedrock.
- **Actions (~15):** move L/R, jump, mine in 4 directions, place in 4 directions, and a handful of craft actions. Craftax has 17, so this is comparable.
- **Crafting (~6 recipes):** wood→workbench, stone→furnace, wood+stone→stone pickaxe, copper ore+furnace→copper bar, copper bar+wood→copper pickaxe, copper bar+wood→torch. Tool tier gates what you can mine — hand gets dirt and wood, stone pick gets stone and copper, copper pick gets iron. That gating _is_ the RL structure.
- **Physics, simplified hard:** grid-snapped horizontal movement, gravity as "fall one tile per tick until supported," fall damage past a threshold. No continuous position, no sub-tile AABB. This is the single biggest complexity cut and it costs you real Terraria fidelity.
- **Keep lighting, cut liquids.** If you keep exactly one propagation system, make it lighting — darkness underground is what makes torches meaningful and creates the exploration gradient, and it's a bounded Jacobi relaxation rather than an ordering nightmare.
- **Cut:** mobs, biomes, day/night, hunger, walls, wiring, all liquids. Health exists only for fall damage.

Notes:
- There should be a beautiful terraria-clone for textures when a human is observing the environment

---

## Checkpoint 1 — playable terminal game (done)

`make && ./terraria-lite --seed 9`. Keys: `wasd` move/jump, `ikjl` mine, `tgfh` place,
`e` cycle placeable, `1`-`6` craft, `r` reset, `q` quit.
`make check` runs the invariant suite and the scripted expert.

### Real-time frontend (frontend only; the engine never changed)
The core is still lockstep — one `env_step` per tick, one action per tick, every
state transition an agent decision point. That is the MDP and it stays. What
changed is who supplies the clock:

- Default: the frontend ticks every `--tick-ms` (80ms → 12.5 tiles/s walk speed,
  which is roughly Terraria's run speed under one-tile-per-tick physics). An
  empty frame steps `ACT_NOOP`, so jump arcs and falls resolve on their own
  instead of freezing until the next keystroke.
- `--lockstep` restores one tick per keypress, for stepping through physics by
  hand and for replaying a `selftest --record` tape without a wall clock.
- Terminals have no key-up event, so a held key arrives as an OS repeat burst
  faster than the tick. Input is queued (cap 4) with a repeat of the queue tail
  dropped: sustained holds run at exactly one action per tick with no banked
  movement firing after release, while two *different* keys inside one frame
  both survive.
- Idle frames are elided. When nothing is queued and the player is grounded and
  not mid-jump, the world is a fixed point — a `NOOP` tick would move only the
  step counter, and 3000 of them at 80ms is four minutes of standing still into
  a truncation. The loop blocks on input instead, without resetting the tick
  deadline, so the rate cap still holds.

Measured: 80ms/tick and 200ms/tick honoured with zero input; one `w` keypress
plays a full 3-up-3-down jump arc unaided (lockstep freezes one tile up); a held
`k` digs 16 tiles in 16 ticks over 1.27s and stops within the fall; the seed-9
expert tape still replays through the TUI to 16/16 in 228 steps under
`--lockstep`.

## Checkpoint 1.5 — depth over fidelity

Three changes, chosen because they close *incoherences* rather than add fidelity.
The rule: fix what has a hole in the grammar, ignore what is merely less rich
than Terraria. Depth is table entries; fidelity is systems.

**The player is two tiles tall.** `(px, py)` is the FEET cell, head at
`(px, py-1)`. Movement needs both cells clear, step-up needs clearance in both
columns, jump clearance is measured above the head. `body_fits()` and
`is_body()` in `env.h` are the only places that know the height, so a taller
body stays a one-constant change.

**Mine and place address ten targets**, the Moore neighbourhood of the body
minus the two cells it fills (`REACH_DX`/`REACH_DY`). 19 actions became 36.
This was not about fidelity: bridging was *incoherent*. The game had
bridge-down (2 actions/tile, losing 1 tile of altitude each) and stair-up
(4 actions/tile, gaining 2) and no way to cross level at all. With a
down-diagonal target, `place-down-right` then `walk-right` spans 10 tiles in
20 actions at unchanged altitude. Measured, not asserted.

**The iron dead-end is closed.** `ITEM_IRON_ORE` had a tier gate, an
achievement, and no recipe consuming it — the top rung of the tech tree was a
stub. Now iron smelts to bars, bars build an anvil, the anvil makes an iron
pickaxe, which gates a new gold band (rows 78-93, ~57 tiles/world against
iron's 132), and gold smelts into the lantern. Ore→bar→tool is now the grammar
on every rung. `Recipe.need_workbench`/`need_furnace` became `Recipe.station`.

**Log and plank are two tiles.** `TILE_LOG` is grown by worldgen; `TILE_WOOD` is
what you place. Both drop `ITEM_WOOD`, exactly as `TILE_GRASS` and `TILE_DIRT`
both drop `ITEM_DIRT` — the pattern already existed. This is not decoration: a
frontend can draw bark against planks, and the scripted expert can no longer
mistake the scaffold it just placed for a tree worth chopping, which was a real
hover-loop pathology. Worldgen grows 62 logs/world and zero planks.

Counts: 16 tiles, 14 items, 4 tool tiers, 36 actions, **24 achievements**
(Craftax-Classic has 22), 11 recipes.

### The Makefile had no header dependencies
Inserting `TILE_LOG` broke lighting in a way that looked like a physics bug and
was not. `%.o: %.c` listed no header prerequisites, so `include/tiles.h`
changing rebuilt nothing whose `.c` was untouched. `TILE_INFO` is a `static
const` table in that header, so every stale object keeps a private outdated
copy: fresh `sim.o` wrote the new `TILE_TORCH` id 10, stale `light.o` looked it
up in its old 15-entry table where 10 was the lantern, and the torch emitted 15.
The lantern hit the old workbench row and emitted 0.

Fixed with `-MMD -MP` and `-include $(DEPS)`. Verified: touching
`include/tiles.h` now rebuilds all six translation units. Any project with
tables in headers needs this before the second contributor, not after.

### Fall damage was optional (exploit, fixed)
`physics()` resolved falling and landing in mutually exclusive branches of one
tick, so touching down was detected a tick late. That left the player standing
on solid ground for a whole action with `fall_dist` still owed — and `do_mine`
on reach slot 8 zeroes `fall_dist` as a controlled descent. So:

> fall 39 tiles while spamming mine-down → **arrive at full health**.

Fall damage, the only real risk in the game and the thing that makes depth cost
something, was opt-out. A policy would have found this immediately; it is
exactly the phase-3 exploit class, found early.

Fix: a fall settles on the tick the feet arrive, from either branch. One `if`.
The `fall_dist` window an action could reach into no longer exists.

Everything else held: `FALL_SAFE` threshold unchanged (4 tiles free, 5 costs
2 hp), digging straight down is still free for 25+ rows, arresting your own
fall with a placed block still costs you. Calibration barely moved — expert
mean 446 steps and **0 deaths over 120 seeds**, so the bot was never leaning on
the exploit, which is a good sign about the movement design.

Locked with a regression test that was verified to fail against the pre-fix
`sim.c` on all three symptoms (damage lagged, `fall_dist` still owed, digging
erased the debt).

### The procedural texture path is gone
The pixel frontend used to carry a second, fully generated texture set as a
per-texture fallback, so it ran without Terraria. It has been deleted: ~450
lines of `gen_*` tile generators, item icons and the hand-drawn player sprite,
plus the `bmp_*` scaffolding underneath them. A Terraria install is now
required.

Why it was worth deleting rather than keeping: it was a second code path the
owner would never see, it had to be kept visually in step with the real art on
every change, and because `px_init` built it first and then overwrote it, a
partially-procedural state existed during startup and after any single sheet
failed to load. One path cannot disagree with itself.

The one genuine casualty was the lantern: `ITEM_ID[ITEM_LANTERN]` is -1, so it
has no Terraria *item* sheet and was the only thing still drawn by hand. It now
borrows its own tile texture, already cropped from `Tiles_42` — the right object
and no new asset. Shared, so `item_owned[]` stays false and `px_shutdown` frees
it exactly once; verified under ASan.

Loading is all-or-nothing now, so the failure has to be good: the directory is
checked before `SDL_Init`, so a bad `--textures` never creates a window, and the
message names the first missing file and the directory searched rather than
listing fifteen failures.

### Calibration after
20/20 seeds full-clear all 24 achievements including the lantern, 0 deaths,
copper pickaxe in 331-446-727 steps. The 228-step full clear that made the old
game an 18-second exercise is gone.

### Pixel frontend
`make terraria-px` — SDL2, links the core directly, no FFI. 60fps render over
the 80ms sim tick with the player and camera interpolated between ticks; the
engine stays strictly one `env_step` per tick and idle frames are still elided.
Mouse drives the ten-target reach, which is the interaction the terminal cannot
express well. Loads real Terraria tile and item art from a local install at
runtime — **never vendored, never committed** — and falls back per texture to
procedural generation.

One real bug worth remembering: the cursor was accumulated from
`SDL_MOUSEMOTION` events, so any gap in that stream (pointer moved while the
window was unfocused) left it stale for good — measured 277 points, ~8 tiles,
between the real pointer and the game's belief. The coordinate math was
correct the whole time. Polling `SDL_GetMouseState` each frame is the fix;
never accumulate pointer state from events.

### Deduplication pass
A complexity audit found the keyboard bindings transcribed in **four** places:
`main.c` owned the tables, `render.c` kept its own copy of the craft row to
label the HUD (with a comment saying "mirroring `key_to_action()` in main.c"),
`px_main.c` re-spelled the reach keys as a switch over SDL keycodes, and
`selftest.c` hand-aligned a 36-entry action→key array for its replay tapes. A
fifth spelling turned up as an inline expression in the pixel frontend's usage
text. Nothing made them agree.

They now live in `src/keymap.h`, both directions, with `_Static_assert` tying
the table lengths to `REACH_COUNT` and `RECIPE_COUNT`. SDL keycodes equal their
ASCII character for printable keys, so the pixel frontend shares the tables
verbatim and reads shift as a modifier instead of as a shifted character.

`src/frontend.h` holds the three things both frontends need and neither owns:
`parse_u64`, `at_rest`, and the achievement diff. **The input queue and the
frame loop were deliberately left duplicated** — SDL has real key-up events and
a terminal has only OS key repeat, so the pixel queue has no use for the
repeat-collapsing the terminal one depends on. Folding them together would
trade a real difference for a fake abstraction.

`tools/play.py` and `tools/vtdump.py` (143 lines: a PTY driver plus a
hand-written VT100 screen reconstructor) existed largely to notice the bindings
drifting apart. One shared table plus a 16-line `test_keymap` round-trip is a
stronger guarantee, so they are gone. The harness had also already cost more
than it saved — the "parity regression" chased earlier was its fixed-duration
drain truncating the capture, not a game bug.

Verified the new test actually fails: duplicating one key in `KB_PLACE` and
rebuilding produces `key 'y' maps to mine up-left, not place down-right` and
`mine up-left and place down-right both answer to 'y'`.

## Checkpoint 2 — the observation, and a way in

### `env_obs` (src/obs.c)
An 11×9 window centred on the **feet**, plus a 54-value status vector. Pure,
allocation-free, `const Env *`.

**Darkness is real for the agent.** A cell lit below `DARK_THRESHOLD` reads as
`OBS_UNKNOWN`, not as its tile. Before this, `DARK_THRESHOLD` was referenced
only by the two renderers — lighting was a display effect, and for a policy
torches would have been decorative and the depth gate would not have existed.
Measured through the binding: 79/99 cells visible in daylight, **20/99 forty
tiles down with no torch**. This is the single decision that makes the lighting
system part of the game.

Out-of-world cells are *visible bedrock*, never `OBS_UNKNOWN`, so the map edge
is never confused with an unlit cave.

**Achievements are in the observation** because `award()` fires once per
achievement — two states with identical worlds but different unlock masks pay
differently for the same action. Omitting the mask would break the Markov
property for no reason. `steps/max_steps` is in for the same reason: the
horizon is finite.

**Tiles are emitted as ids, not one-hot.** The C side stays compact and stable;
the consumer picks the encoding. Adding a tile is then an embedding resize
rather than an observation-layout change. The Python binding does the one-hot,
so swapping it for an embedding never touches C.

### Action representation
Flat `Discrete(36)` for now, chosen deliberately over `MultiDiscrete`. The
factored version is still the right answer if the action space keeps growing —
revisit before it does, because it invalidates checkpoints.

### Binding (src/capi.c, python/)
Flat C ABI: scalars and caller-owned buffers only, no struct layout to agree
on. `-fvisibility=hidden` so only the 23 `tl_*` symbols escape. Layout
constants are *queried* from the library rather than restated in Python — a
binding that hardcodes 11×9 is one that lies the day the window changes.

`python/terraria_lite.py` needs only numpy; Gymnasium is optional and adds
`TerrariaLite-v0`. Not vectorised — batching belongs here when a trainer is
actually starved, and nothing forecloses it.

### Baselines
| | achievements | notes |
|---|---|---|
| random | **3.8 / 24** | stalls at `craft workbench`, 80% die to falls |
| scripted expert | 24 / 24 | 446 steps, 0 deaths |

Random scores within ~12 steps in 100% of episodes, so there is an immediate
gradient, then a hard exploration cliff at the workbench (needs 8 wood; random
never holds more than 1). Dense first rungs, sharp wall — the Crafter/Craftax
shape, and where a learner will sit.

FFI overhead is real but not yet interesting: 88k steps/s native, ~58k through
ctypes one env at a time.

`test_obs` in the selftest covers geometry, the darkness rule, self-visibility,
the world edge, status ranges, purity and buffer initialisation. It was
validated against **14 deliberately injected mutants of `obs.c`** — all caught.

### Layout
- `include/` — frozen contract: `tiles.h` (taxonomy + property tables), `env.h` (state
  struct, actions, achievements, recipes), `rng.h` (per-env PCG32).
- `src/worldgen.c` `src/light.c` `src/sim.c` `src/obs.c` — the environment core.
  No globals, no allocation in `env_step`, no `rand()`. Verified with `nm`.
- `src/render.c` `src/main.c` — terminal frontend. Reads state, never mutates it.
- `src/px_render.c` `src/px_main.c` — SDL2 pixel frontend. Same rule: reads state
  only. `third_party/stb_image.h` decodes the Terraria PNGs.
- `src/keymap.h` `src/frontend.h` — the only things both frontends share.
- `tools/selftest.c` — invariants + scripted expert; `--record` emits a key tape.
- `src/capi.c` — flat C ABI, built only into the shared library (`make lib`).
- `python/terraria_lite.py` — ctypes binding, Gymnasium optional.
  `python/random_agent.py` — random baseline and binding smoke test.

### Decisions settled
- **Autoreset:** same-step, with a `final_obs` buffer. Not yet built; no episode
  boundary crosses the C ABI until Checkpoint 2.
- **Death is real.** Fall damage past 4 tiles, 2 hp/tile, 10 hp. Dying sets
  `terminated`; the step limit sets `truncated`. Kept separate from day one so the
  value bootstrap is correct later.
- **Episode limit:** runtime parameter, default 3000. See calibration below.
- **Worldgen:** fresh procedural world per episode from a per-episode seed, splitmix
  avalanched so sequential seeds do not correlate.
- **Falls are controllable.** The agent acts every tick while airborne, per the
  original "one tile per tick" wording. Mid-fall movement and pillar-jumping both work.

### Deviations from the plan above
- **Stone is hand-mineable.** As specified the tech tree deadlocked: stone needed a
  stone pickaxe, whose recipe costs 5 stone. Rather than add a wood-pickaxe rung, the
  gate moved: tools gate *ores* (stone pick → copper, copper pick → iron) and darkness
  gates *depth*. Lighting is now the thing standing between you and the deep layers,
  which is what the plan wanted from it anyway.
- **Tiles:** `leaves` replaces `placed block`; placing a material places that material.
- **Placement needs no supporting neighbour**, which makes pillar-jumping and bridging
  work. Known exploit surface for phase 3.
- **Furnaces emit no light**, deliberately — a 12-stone furnace would otherwise be a
  permanent lamp and defeat the torch gate.
- **Mining the tile directly beneath you resets fall distance.** Without this,
  continuous digging never produces a grounded tick and a 30-tile shaft is fatal.
  Lowering yourself a tile at a time is a controlled descent; breaking into a cavern
  still hurts.

### Calibration (120 seeds, scripted expert with omniscient ore search)
- 109/120 reach a copper pickaxe, 107/120 clear all 16 achievements, 7 deaths.
- Steps to copper pickaxe: min 178, mean 452, max 4739.
- An expert full-clears in ~450 steps, so 3000 leaves an RL agent roughly 6x the
  optimal budget. Revisit once a policy is actually learning.

### Next
Checkpoint 2 is small: `env_obs` writing a flat egocentric window + status vector,
a batched `env_step_many`, and a Gymnasium shim. The observation *layout* is the one
decision worth care — changing it later invalidates every checkpoint and benchmark
number.
