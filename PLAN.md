Inspiration: [Craftax](https://craftaxenv.github.io/)

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

### Layout
- `include/` — frozen contract: `tiles.h` (taxonomy + property tables), `env.h` (state
  struct, actions, achievements, recipes), `rng.h` (per-env PCG32).
- `src/worldgen.c` `src/light.c` `src/sim.c` — the environment core. No globals, no
  allocation in `env_step`, no `rand()`. Verified with `nm`.
- `src/render.c` `src/main.c` — terminal frontend. Reads state, never mutates it.
- `tools/selftest.c` — invariants + scripted expert. `tools/play.py`, `tools/vtdump.py`
  drive and reconstruct the TUI headlessly.

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
