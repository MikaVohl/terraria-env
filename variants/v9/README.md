# v9: Terraria-Lite release candidate

Implementation of `docs/ENV_V9_DESIGN.md` (build steps (a)-(d)). Started as a
copy of `variants/v8` (itself the frozen v7 core); v8, v7 and v4 sources are
untouched. `ENV_VERSION` is 9, so v9 checkpoints never load on other versions.

| File | Contents |
|---|---|
| `include/env.h` | knobs, actions, 38 achievements with tiers, observation layout, recipes, `Env` |
| `include/tiles.h` | tiles (+ Demon Altar), items (+ gold chainmail, lens, Suspicious Looking Eye, demonite ore) |
| `src/sim.c` | actions, physics, crafting, day/night, summon, minimap bookkeeping |
| `src/mobs.c` | regular mobs: spawning by layer and time, one AI function per kind, drops |
| `src/boss.c` | Eye of Cthulhu, self-contained (`Boss` state + summon/tick/attack/despawn) |
| `src/worldgen.c` | 128x128 world, layers, caves, ores, trees, rooms, altars, life crystals, supply floors |
| `src/light.c` | v7 lighting with the observation-window refresh built in; sky level follows day/night |
| `src/obs.c` | observation (status additions, 8-channel entity block, optional minimap) |
| `tests/selftest.c` | C gates: determinism, save/load, light parity, mechanic fixtures, scripted boss fight, worldgen supply |
| `tests/check_v9.py` | Python gates: SPEC contract, scalar = native autoreset, scoring, boss-chain potential, evaluation |

## Build

The v7 fast-path Makefile builds v9 (it compiles `mobs.c`/`boss.c` when the
source tree has them). `light.c` already contains the observation-window
refresh, so do **not** pass `LIGHT_WINDOW=1` (the v7 patch would not apply).

    # default game; INV_LOG=1 as in the current best v8 training build
    make -C perf/v7 V7=$PWD/variants/v9 BUILD=build-v9 VARIANT="-DINV_LOG=1"
    # same plus the coarse explored-map channel (prototype option)
    make -C perf/v7 V7=$PWD/variants/v9 BUILD=build-v9-map VARIANT="-DINV_LOG=1 -DMINIMAP=1"

    TERRARIA_LITE_LIB=$PWD/perf/v7/build-v9/libterraria.so PYTHONPATH=python ...

Arms: `v9_gen_g9999` / `v9_shaped_g9999` (library `build-v9`) and
`v9map_gen_g9999` / `v9map_shaped_g9999` (library `build-v9-map`) in
`tools/explore_screen.py`; with `tools/gpu_queue.py` set `"lib"` to the build
directory. The GPU simulator backend (`--sim-backend gpu`) is v7-only.

## Tests

    cc -std=c11 -O2 -Ivariants/v9/include variants/v9/src/{sim,worldgen,light,obs,mobs,boss}.c \
       src/capi.c variants/v9/tests/selftest.c -o /tmp/v9-selftest -lm && /tmp/v9-selftest 512
    TERRARIA_LITE_LIB=$PWD/perf/v7/build-v9/libterraria.so PYTHONPATH=python .venv/bin/python variants/v9/tests/check_v9.py
    TERRARIA_LITE_LIB=$PWD/perf/v7/build-v9/libterraria.so PYTHONPATH=python .venv/bin/python -m terraria_lite.v2_checks
    TERRARIA_LITE_LIB=$PWD/perf/v7/build-v9/libterraria.so PYTHONPATH=python .venv/bin/python perf/check_shaping.py --envs 256 --steps 600
    cc -O2 tools/sim_throughput.c -o /tmp/sim_throughput && \
       /tmp/sim_throughput -n 64 -s 10000 -r 5 perf/v7/build-v8-o3t2-inv/libterraria.so perf/v7/build-v9/libterraria.so

Add `-DMINIMAP=1 -DINV_LOG=1` to the selftest compile line to test the map build.

## Knobs

All compile-time (`VARIANT="-DNAME=value"`); defaults are the design's draft values.

| Knob | Default | Meaning (design ref.) |
|---|---|---|
| `WORLD_W` | 128 | world width (D6) |
| `WORLD_H` | 128 | world depth (D6, [T] 112-144) |
| `CAVERN_Y` | 64 | first cavern row; "reach the caverns" |
| `EPISODE_STEPS` | 10000 | default episode length (D7); runtime override `--episode-steps` |
| `DAY_STEPS`, `NIGHT_STEPS` | 1800, 1200 | day/night cycle, episodes start at dawn (D8) |
| `NIGHT_SKY_LIGHT` | 3 | sky light at night (day 15; dark threshold 2) |
| `MOB_CAP` | 12 | regular mob slots; the boss has its own slot (section 5) |
| `SPAWN_PERIOD` | 120 | steps between spawn attempts (day surface, underground, caverns) |
| `NIGHT_SPAWN_PERIOD` | 60 | steps between spawn attempts on the surface at night |
| `EYE_SPAWN_PCT` | 50 | night surface spawns that are Demon Eyes (else Zombies) |
| `SKELETON_SPAWN_PCT` | 50 | cavern spawns that are Skeletons (else Cave Bats) |
| `SLIME_HP`, `SLIME_DMG` | 25, 7 | Blue Slime (v8 values) |
| `BAT_HP`, `BAT_DMG` | 16, 12 | Cave Bat (v8 values) |
| `ZOMBIE_HP`, `ZOMBIE_DMG` | 30, 10 | Zombie |
| `DEMON_EYE_HP`, `DEMON_EYE_DMG` | 30, 12 | Demon Eye |
| `SKELETON_HP`, `SKELETON_DMG` | 50, 16 | Skeleton |
| `LENS_DROP_PCT` | 33 | Demon Eye lens drop chance |
| `EOC_HP` | 240 | Eye of Cthulhu HP; phase 2 at <= 50% |
| `EOC_DMG1`, `EOC_DMG2` | 12, 18 | contact damage per phase |
| `EOC_HOVER_HEIGHT` | 8 | hover target rows above the player |
| `EOC_HOVER_TICKS1`, `EOC_HOVER_TICKS2` | 30, 15 | hover time between dash series |
| `EOC_DASHES1`, `EOC_DASHES2` | 3, 5 | dashes per series |
| `EOC_DASH_TICKS1`, `EOC_DASH_TICKS2` | 8, 6 | dash duration |
| `EOC_DASH_SPEED1`, `EOC_DASH_SPEED2` | 2, 3 | dash speed (tiles/tick) |
| `EOC_PAUSE_TICKS1`, `EOC_PAUSE_TICKS2` | 6, 3 | pause between dashes |
| `EOC_DEMONITE_MIN`, `EOC_DEMONITE_MAX` | 30, 87 | demonite ore drop |
| `COPPER_MIN` | 30 | copper floor, underground + caverns (D5) |
| `IRON_MIN` | 140 | iron floor, underground + caverns |
| `SILVER_MIN` | 40 | silver floor, caverns |
| `GOLD_MIN` | 60 | gold floor, lower half of the caverns |
| `WOOD_MIN`, `WOOD_REACH` | 150, 48 | trunk tiles within 48 columns of spawn |
| `ALTAR_MIN` | 2 | Demon Altars per world (ALTAR_MIN or +1) |
| `CRYSTAL_MIN` | 3 | Life Crystals per world (3-5) |
| `ORE_DENSITY_PCT` | 100 | vein count: v7's per-row vein rate over each v9 ore band |
| `TREE_HEIGHT_PCT` | 200 | trunk heights 8-12 before the wood floor grows trees (max 16) |
| `IRON_PICK_BARS`, `GOLD_PICK_BARS` | 12, 12 | pickaxe bars (D16; + 3 wood) |
| `IRON_ARMOR_BARS`, `GOLD_ARMOR_BARS` | 20, 25 | chainmail bars (D16) |
| `EYE_LENSES` | 6 | lenses per Suspicious Looking Eye |
| `MINIMAP`, `MINIMAP_CELL` | 0, 8 | explored-map channel (D9 prototype) and its cell size |
| `INV_LOG` | 0 | log-count inventory entries (v8 knob) |
| `VIEW_W`, `VIEW_H` | 11, 9 | observation window (v8 knob) |

## Contract summary

- **Actions (86):** v8's 83 plus `craft gold chainmail`, `craft Suspicious Looking Eye`
  (recipe block) and `use summon item` (last). Summon is legal only at night, holding
  the eye, with no boss alive.
- **Achievements (38, u64):** tiers 1/2/3/4 = 13/12/8/5, weights 1/3/5/8, max 129
  (`tl_ach_tier`, `tl_ach_weight`, `SPEC.achievement_tiers/weights`). Training reward
  stays +1 per unlock and -1 on death; the tiered score is evaluation only
  (`terraria_lite.scoring`, `weighted_score` in validation records).
- **Status block:** v8's 17 scalars, then day phase, is-night, layer one-hot (surface,
  underground, caverns), boss (present, HP fraction, phase 2, dx/32, dy/32), selected
  slot, inventory (sqrt), achievements, [INV_LOG log counts], [MINIMAP 16x16x3:
  explored, solid fraction, station seen], then per visible cell 8 entity channels:
  Blue Slime, Cave Bat, Zombie, Demon Eye, Skeleton, Eye of Cthulhu, health, phase.
- **Native autoreset info rows** are 5 int32 wide (mask low/high words);
  `SPEC.info_width` reads it from the library.
