# v10: Terraria-Lite with real-Terraria behaviour ports

v10 = v9 (`docs/ENV_V9_DESIGN.md`) + the five behaviour ports proven in `variants/v8fid`
(D22, each a compile-time knob, all on by default) at **15 game ticks per action**
(D23) + two tier-4 stepping-stone achievements (D24). Implementation notes:
`docs/ENV_V9_DESIGN.md` section 14. Started as a copy of `variants/v9`; v4/v7/v8/v8fid/v9
sources are untouched. `ENV_VERSION` is 10, so v10 checkpoints never load on other versions.

| File | Contents |
|---|---|
| `include/env.h` | knobs (v9's + `FID_*`), actions, 40 achievements with tiers, observation layout, recipes, `Env` |
| `include/fid.h` | fixed-point tile collision (`Collision.TileCollision`, `SolidCollision`, `CanHit`), from v8fid |
| `include/tiles.h` | tiles and items (v9's) |
| `src/sim.c` | actions, player physics (`FID_PHYSICS`), mining (`FID_MINING`), melee (`FID_COMBAT`), tick loop, crafting, day/night |
| `src/mobs.c` | spawning (v9 rule), NPC AI ports per kind (`FID_MOBS`), contact damage, melee hits, drops |
| `src/boss.c` | Eye of Cthulhu (v9 module) + `FID_COMBAT` hit/contact rules |
| `src/worldgen.c` | v9 world; `FID_TREES` tree heights; wood floor in wood, not trunk tiles |
| `src/light.c`, `src/obs.c` | v9 lighting; observation with the port scalars |
| `tests/selftest.c` | C gates: determinism, save/load, light parity, v9 mechanics with the ports, D24, scripted boss fight, worldgen supply |
| `tests/fid_test.c` | port fixtures against the real constants on v10's five mobs and the boss |
| `tests/check_v10.py` | Python gates: SPEC contract, scalar = native autoreset, scoring (max 145), potential goals, evaluation |

## Ports (D22)

All five are on by default; each is a knob (`VARIANT="-DFID_X=0"`) for ablations. Every
port cites the decompiled Terraria 1.4.4 method it follows (tModLoader 2026.08, decompiled
on `omarchy:~/tml-bench/decomp`; no game code is in this repository). Details and
constants of the v8fid ports: `variants/v8fid/README.md`.

| Knob | Default | Replaces |
|---|---|---|
| `FID_MOBS` | 1 | v9's grid AI of all five regular mobs: Blue Slime `AI_001_Slimes`, Cave Bat aiStyle 14, **Zombie and Skeleton `AI_003_Fighters`** (new), **Demon Eye `AI_002_FloatingEye`** (new), on sub-tile fixed-point bodies with real stats |
| `FID_COMBAT` | 1 | fixed attack/damage/hurt cooldown: damage variance, defense, crits, 40-tick i-frames, NPC hit immunity, knockback, sword swing / shortsword stab hitboxes, also against the boss |
| `FID_PHYSICS` | 1 | the one-cell grid player: 20x42 px fixed-point body, run, held jumps, gravity, step up/down, rope pulley |
| `FID_MINING` | 1 | fixed mining cooldown: pick power vs tile, `HitTile` counters, tool use time (axe on trees) |
| `FID_TREES` | 1 | 8-12-tile trunks with one wood each: `GrowTree` heights 5-16 and per-tile wood with branches, roots and bonus wood |
| `FID_TICKS` | 15 | 60 Hz game ticks per agent action (v8fid default 4) |

New mob ports (from the decompiled methods; `src/mobs.c`):

- **Zombie / Skeleton** (`AI_003_Fighters`, types 3 / 21): walk at +-0.07 px/tick² up to
  1.0 / 1.5 px/tick (x0.8 when above that on the ground); the `ai[3]` stuck counter (60
  ticks -> about 540 bored ticks without targeting, reset by a hit or touching the player);
  wander instead of targeting by day on or above the surface (turn after 2 still grounded
  ticks); their own step-up onto 1-tile ledges; wall jumps of vy -6 / -7 / -8 for 2 / 3 /
  4-tile walls, a gap jump (-8, vx x1.5) toward a player level or above, the first-stuck-tick
  hop (-5); drop through platforms only when the player is below the feet. Stats 45/14/6 and
  60/20/8 (life/damage/defense), 18x40 px, knockBackResist 0.5.
- **Demon Eye** (`AI_002_FloatingEye`, type 2): no gravity, bounce at half speed off tiles
  (minimum 2 / 1 px/tick), re-target every tick, accelerate 0.1 / 0.04 px/tick² up to 4 / 1.5
  px/tick, always through platforms. 60/18/2, 30x32 px, knockBackResist 0.8. Its daytime
  branch (fly up and leave) is not reached because v9's dawn rule removes Demon Eyes.
- Knockback follows `StrikeNPC` exactly: weapon kb x knockBackResist (x1.4 on crits); light
  hits apply knockBackResist a second time (vanilla; v8fid applied it once in each branch).

Kept from v9: mob spawning by layer and time, the despawn radius (28 columns / 24 rows),
the dawn rule, the Eye of Cthulhu's AI (per action, grid cells). The boss now takes ported
hits (48x48 px body, once per swing, no line-of-sight test since it has `noTileCollide`,
damage variance, `EOC_DEF`, crits, no knockback) and deals contact damage every tick
through `Player.Hurt`.

## Time scale at 15 ticks per action (D23)

One action is 1/4 s of game time, about one copper-pickaxe swing (useTime 15). The v9
constants are counted in actions; each was kept as an action count (a design pacing
choice) or replaced by a ported tick-based rule:

| Constant | v9 | v10 | Game time at 15 ticks | Real Terraria |
|---|---|---|---|---|
| Episode | 10,000 steps | kept | 2,500 s (41.7 min) | — |
| Day / night | 1,800 / 1,200 steps | kept (D8: 3.3 cycles per episode) | 7.5 / 5 min | 15 / 9 min (would be 3,600 / 2,160 steps, 1.7 cycles) |
| Spawn attempts | every 120 steps, 60 at night on the surface | kept | 30 s / 15 s | spawn-rate system, not ported |
| Heal cooldown | 60 steps | kept | 15 s | potion sickness 60 s |
| Natural regen | after 40 safe steps, +1 HP / 16 steps (8 at a campfire) | kept | 10 s, then 1 HP / 4 s | — |
| Hurt cooldown | 8 steps | `immuneTime` 40 ticks (20 for 1 damage) | 0.67 s (2.7 steps) | same |
| Attack cooldown | 3 steps | `itemAnimation` 13-21 ticks | swords: one swing per 2 steps; shortsword one per step | same |
| Mining cooldown | 4 - tool tier steps | tool `useTime` 15 / 13 / 17 ticks, axe 21 | stone: 3 steps (copper), tree: 17 steps | same |
| Jump | 6 tiles in 6 steps | `JumpMovement` | one held step rises 5.8 tiles, two 6.1 | same |
| Lens drop | 33% per Demon Eye | kept (per kill) | ~10 eye spawns per night at most, so 6 lenses take about 2 nights of kills | 1/3 |
| Despawn radius | 28 / 24 tiles | kept | — | screen-based `timeLeft` |
| EoC hover / dash / pause | 30 / 8 / 6 steps (phase 2: 15 / 6 / 3) | kept (v9 module) | 7.5 / 2 / 1.5 s | — |
| EoC contact damage | 12 / 18, hover 8 rows | **8 / 12, hover 5 rows** with `FID_COMBAT` | — | 15 / 23 |

The EoC retune: v9's damage was balanced against the 8-step (120-tick) hurt cooldown; the
40-tick i-frames let contact land three times as often, and the hovering boss was out of
reach of the 32x32-frame overhead swing. With the retune the scripted iron-gear fight wins
193/200 again (v9: 194/200); with v9's values it won 1/200.

## Achievements (D24)

40 achievements, tiers 13 / 12 / 8 / 7, weights 1 / 3 / 5 / 8, **max 145** (v9: 38, max 129).
Tier 4 order: craft gold pickaxe, collect lens, **find a Demon Altar**, **hold 6 lenses**,
craft Suspicious Looking Eye, summon the Eye of Cthulhu, defeat the Eye of Cthulhu
(the last three moved two indices against v9).

- **find a Demon Altar**: at the end of a step, a Demon Altar tile lies within the
  crafting-station square of the body (`station_near`: columns px-3 .. px+4, rows
  py-5 .. py+3), i.e. where the Suspicious Looking Eye recipe works. No light condition.
- **hold 6 lenses**: at the end of a step the inventory holds at least `EYE_LENSES` (6)
  lenses. The recipe is unchanged (6 lenses at a Demon Altar).

Training reward stays +1 per first unlock and -1 on death; the tiers are evaluation only.

## Build

The v7 fast-path Makefile builds v10 (it compiles `mobs.c`/`boss.c` and copies `fid.h`).
Do **not** pass `LIGHT_WINDOW=1` (`light.c` already has the window refresh).

    # default game (all ports, 15 ticks); INV_LOG=1 as in the v8/v9 training builds
    make -C perf/v7 V7=$PWD/variants/v10 BUILD=build-v10 VARIANT="-DINV_LOG=1"
    # control: all ports and tile rules off = v9's rules plus the D24 achievements
    make -C perf/v7 V7=$PWD/variants/v10 BUILD=build-v10-noport \
        VARIANT="-DINV_LOG=1 -DFID_MOBS=0 -DFID_COMBAT=0 -DFID_PHYSICS=0 -DFID_MINING=0 -DFID_TREES=0 -DTREE_LEAF_VISUAL=0 -DSUPPORT_RULES=0 -DEXPLICIT_TOOLS=0 -DTOOL_DAMAGE=0 -DBG_WALLS=0"

    TERRARIA_LITE_LIB=$PWD/perf/v7/build-v10/libterraria.so PYTHONPATH=python ...

`build-v10-noport` plays exactly like `build-v9` (`tools/v10_noport_parity.py`): same
worlds, views, masks, status outside the achievement block, rewards net of the D24
unlocks. Arms: `v10_gen_g9999` / `v10_shaped_g9999` in `tools/explore_screen.py`
(library `build-v10` or `build-v10-noport`; with `tools/gpu_queue.py` set `"lib"`).
`MINIMAP` is carried over from v9 (default 0, not a v10 default). The GPU simulator
backend (`--sim-backend gpu`) is v7-only.

## Play

`terraria-px-v10` is the SDL pixel frontend (`src/px_*.c`, built against this core with
the default knobs plus `ENV_FX=1`; Terraria textures from the local Steam install, as
`terraria-px`):

    make terraria-px-v10 && ./terraria-px-v10            # seed 23000001 (first validation world)
    ./terraria-px-v10 42                                  # or --seed 42; --tick-ms 250 is real time
    make check-pixel-v10                                  # headless smoke, screenshots in /tmp

F1 shows the controls (also at start). Beyond `terraria-px`'s scheme: Enter uses the
Suspicious Looking Eye, a click on a potion / mushroom / life crystal / the Eye uses it,
a hotbar click selects the slot directly, `'` and `` ` `` craft gold chainmail and the Eye,
and j / l can be held on a rope. The HUD adds the clock and night, the layer, the tiered
achievement panel with the weighted score, and the boss bar.

Combat feedback comes from `Env.fx` (hits, swing start, every body per game tick; never
read by the game): broadswords swing the useStyle 1 overhead arc from the original item
sprite over `itemAnimationMax` ticks, the copper shortsword thrusts its stab, pickaxe and
axe swing per use time; damage numbers pop over the struck body (orange, crits larger, red
on the player); mobs, the boss and the player flash red on a hit, the player blinks through
its i-frames; the player and mobs follow their per-tick path, so knockback shows its real
jolt. Trees draw `Tree_Tops` crowns and `Tree_Branches` leaves (`TREE_LEAF_VISUAL`).

## Tests

    V=variants/v10
    cc -std=c11 -O2 -I$V/include $V/src/{sim,worldgen,light,obs,mobs,boss}.c src/capi.c $V/tests/selftest.c \
       -o /tmp/v10-selftest -lm && /tmp/v10-selftest 512
    cc -std=c11 -O2 -I$V/include -I$V/src $V/tests/fid_test.c $V/src/{worldgen,light,obs}.c \
       -o /tmp/v10-fid -lm && /tmp/v10-fid
    TERRARIA_LITE_LIB=$PWD/perf/v7/build-v10/libterraria.so PYTHONPATH=python .venv/bin/python $V/tests/check_v10.py
    PYTHONPATH=python .venv/bin/python tools/v10_noport_parity.py \
       perf/v7/build-v9/libterraria.so perf/v7/build-v10-noport/libterraria.so 16 25000
    cc -O2 tools/sim_throughput.c -o /tmp/sim_throughput && /tmp/sim_throughput -n 64 -s 20000 -r 3 \
       perf/v7/build-v8-o3t2-inv/libterraria.so perf/v7/build-v9/libterraria.so \
       perf/v7/build-v10-noport/libterraria.so perf/v7/build-v10/libterraria.so

Add `-DENV_FX=1` to the first `cc` line for the side-channel fixture (`test_fx`). Add the
noport flags (including `-DTREE_LEAF_VISUAL=0 -DSUPPORT_RULES=0 -DEXPLICIT_TOOLS=0 -DTOOL_DAMAGE=0 -DBG_WALLS=0`) to the two `cc` lines to
test the control build. The scripted boss fight is gated (>= 90%) for the two shipped rule
sets (combat and physics both on, or both off); mixed ablation builds only report it.

## Knobs

All compile-time (`VARIANT="-DNAME=value"`). v9's knobs keep their meaning
(`variants/v9/README.md`); new or changed defaults:

| Knob | Default | Meaning |
|---|---|---|
| `FID_MOBS`, `FID_COMBAT`, `FID_PHYSICS`, `FID_MINING`, `FID_TREES` | 1 | behaviour ports (above) |
| `FID_TICKS` | 15 | game ticks per action (D23) |
| `TREE_LEAF_VISUAL` | 1 | canopies and branch leaves are tree sprites (frontend), no `TILE_LEAVES` cells (below) |
| `SUPPORT_RULES` | 1 | tile anchors for placement and breaking (below) |
| `ENV_FX` | 0 | observational side channel `Env.fx` for the pixel frontend (built with 1); never read by the game |
| `EXPLICIT_TOOLS` | 1 | pickaxes/axe are items, starter set, Auto Select, `held` item observed, 9,999 stacks (below) |
| `TOOL_DAMAGE` | `FID_COMBAT && FID_MINING` | pickaxe/axe uses swing a real melee hitbox (below) |
| `BG_WALLS` | 1 | background walls from worldgen; Terraria's neighbour-or-wall block placement (below) |
| `SLIME_HP/DMG/DEF` | 25 / 7 / 2 | Blue Slime |
| `BAT_HP/DMG/DEF` | 16 / 13 / 2 | Cave Bat (v9 damage 12 without mob/combat ports) |
| `ZOMBIE_HP/DMG/DEF` | 45 / 14 / 6 | Zombie (v9: 30 / 10) |
| `DEMON_EYE_HP/DMG/DEF` | 60 / 18 / 2 | Demon Eye (v9: 30 / 12) |
| `SKELETON_HP/DMG/DEF` | 60 / 20 / 8 | Skeleton (v9: 50 / 16) |
| `EOC_DMG1`, `EOC_DMG2` | 8, 12 | EoC contact damage with `FID_COMBAT` (v9: 12, 18) |
| `EOC_HOVER_HEIGHT` | 5 | EoC hover rows above the feet with `FID_COMBAT` (v9: 8) |
| `EOC_DEF` | 0 | EoC defense in the ported damage formula (real 12; v9's 240 HP assumed none) |
| `MINIMAP` | 0 | v9 prototype option, not used by v10 |

Mob stats default to the real `NPC.SetDefaults` values whenever `FID_MOBS` or `FID_COMBAT`
is on, otherwise to v9's; defense acts only through `FID_COMBAT`.

## Tile rules (after the first v10 runs)

Rule changes found in play, each a knob (default on); with both 0 a v10 build plays as
before them, and `build-v10-noport` sets both 0 to stay v9.

- **`TREE_LEAF_VISUAL`**: as in Terraria, the canopy (`Tree_Tops`) and the branch leaves
  (`Tree_Branches`) belong to the tree sprite. Worldgen still reserves the canopy cells
  (every other cell equals the `TREE_LEAF_VISUAL=0` world) and clears them before
  returning: no `TILE_LEAVES` (id and observation channel kept, always empty); felling
  clears none. `terraria-px-v10` draws crowns on trunk tops and leafy branches along
  trunks, chosen from the trunk cell; trunks under 5 tiles are stumps.
- **`SUPPORT_RULES`** (no walls exist, so blocks are the anchors):
  - torch: a solid tile left, right or below; rope: a solid tile or rope above; platform: a
    solid tile or platform left/right, or a solid tile below;
  - workbench, furnace, anvil, campfire: a solid tile under every bottom cell (workbench:
    or a platform). Blocks need nothing (pillars and bridges stay legal);
  - when a cell is removed its neighbours are re-checked: torches, rope (the whole chain
    below), mushrooms, stations, life crystals and looted chests without an anchor break
    and drop their item into the inventory (a looted chest drops nothing), recursively,
    with exact incremental light and `object_part`; placed platforms stay;
  - the block under an unopened chest cannot be mined;
  - the placement and mining masks follow; a dark anchor cell counts as present (no
    hidden-terrain leak).

## Tools and walls (2026-11-10)

Three more ports, each a knob (default on); `build-v10-noport` sets them 0 and still equals v9
(`tools/v10_noport_parity.py`, 400,000 steps, 16 lanes).

- **`EXPLICIT_TOOLS`**: Copper Pickaxe (3509) and Copper Axe (3506) are items; episodes start
  with Terraria's starter set (Copper Shortsword, Copper Pickaxe, Copper Axe). No hidden tool
  tier: mining power is the best pickaxe owned. A mine action auto-selects
  (`Player.SmartSelect_GetToolStrategy`: axe for trunks, pickaxe otherwise; Terraria takes the
  first such item in slot order, here the best pickaxe). `Env.held` (Player.HeldItem): the tool
  while mining, the weapon on attack / weapon cycling, the placeable on place / select.
  Stacks hold 9,999 (1.4.4 `maxStack`); the inventory observation still saturates at 999.
- **`TOOL_DAMAGE`**: each tool use starts `itemAnimation = useAnimation` and swings the
  useStyle 1 hitbox of the sword path (`ItemCheck_GetMeleeHitbox`, `ItemCheck_MeleeHitNPCs`:
  immunity per swing, `Main.DamageVar`, defense, 4% crits, `StrikeNPC` knockback; boss too).
  `Item.SetDefaults`: Copper Pickaxe damage 4 / useAnimation 23 / useTime 15 / kb 2 / pick 35;
  Iron Pickaxe 5 / 20 / 13 / 2 / 40; Gold Pickaxe 6 / 20 / 17 / 2 / 55; Copper Axe 3 / 30 / 21 /
  4.5 / axe 7. Tools autoReuse and useTurn; mining hits need the tool's use running (a sword
  swing still running delays them), and a tool use running blocks `attack` (one item in hand).
  Hits go to `Env.fx`; the player draws the tool sprite's swing and the damage numbers.
- **`BG_WALLS`**: `Env.wall` per cell from `WorldGen` passes "Dirt Wall Backgrounds" (dirt wall
  from one row below the surface to the dirt band's bottom + a 0-9 row jitter walk, none in the
  sky) and "Cave Walls" (`maxTilesX*0.04` = 5 enclosed cave regions of 10-1499 open cells
  between (worldSurface+rockLayer)/2 and the bottom, `countTiles`/`Spread.Wall`, walls 59 / 61 /
  170 / 171), plus Planked Wall 27 in the underground chest cabins; deeper caves stay wall-less
  as in Terraria. Own RNG stream: tiles are identical to `BG_WALLS=0`. Mining never removes a
  wall. Placement (`Player.PlaceThing_Tiles_BlockPlacementForAssortedThings`): a block needs a
  solid tile, platform or rope right/left/below/above, or a wall on such a neighbour or behind
  the target (no floating blocks in the sky; pillars and bridges stay legal); torches
  (`wall > 0` first) and platforms may also hang on the wall behind them. Walls do not change
  lighting (not ported). The observation adds a 9th per-cell channel (1 = lit cell with a
  wall); `llm_text` draws `,` for open cells in front of a wall; `terraria-px-v10` draws the
  `Wall_N` textures (cells without a wall show the rock backdrop darkened).

Observation (INV_LOG=1, all knobs): status 1090 (was 948): +2 items x 2 (inventory, log), +39
held one-hot (`tl_status_held0`), +99 wall channel (`tl_wall_channel`, entity channels 9).

## Contract summary

- **Actions (86):** v9's, unchanged. With `FID_PHYSICS`, `left`/`right` are always legal
  and hold the direction for the action's 15 ticks; `jump` holds Jump (a held jump
  continues through `left`/`right`); `climb`/`drop` hold Up/Down. With `FID_MINING` a mine
  action holds the tool on its target (one hit every `useTime` ticks). With `FID_COMBAT`
  `attack` starts a swing, legal again when the swing ends.
- **Achievements (40, u64):** above.
- **Status block:** v9's layout, then `FID_PHYSICS` sub-tile x/y and velocity x/y and
  `FID_MINING` dig damage, just before the entity block (948 entries with INV_LOG=1 and
  all ports; 943 for noport). `tl_status_entity0` / `tl_status_len` report it. Port
  meanings of existing entries: attack cooldown = swing progress, hurt cooldown =
  i-frames / 40, mine cooldown = tool time / 21, jump = `Player.jump` / 15. Entity
  phase channel: slime ticks to the next hop, bat line-of-sight timer, fighter stuck
  counter (7 = wandering), Demon Eye vertical velocity bin.
- **Native autoreset info rows** are 5 int32 wide (64-bit mask), as in v9.
