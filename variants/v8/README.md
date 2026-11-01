# v8 preview: environment-option study

A copy of the frozen v7 core (`src/{sim,worldgen,light,obs}.c`, `include/*.h`)
with compile-time knobs. With every knob at its default the build is
byte-for-byte v7: identical worlds (save_state) for seeds 0-255 and
23,000,001-23,000,128, and identical observations and rewards over a
16,000-step random rollout (`tools/v8_probe.py`, see
`docs/reports/ENV_OPTIONS_2026_10.md`).

| Knob | Default (= v7) | Meaning |
|---|---|---|
| `ORE_PCT` | 100 | Iron and gold supply as a percentage of the recipe floor (120 iron, 40 gold), added as extra in-band veins after v7's floors. |
| `TREE_HEIGHT_PCT` | 100 | Trunk heights (4-6 tiles) scaled; felling a tree yields one wood per trunk tile. |
| `VIEW_W`, `VIEW_H` | 11, 9 | Observation window (odd, at least 11x9). Changes the observation size. |

Episode length is a runtime option (`--episode-steps` in `tools/iterate_ppo.py`).
Recipes, rewards, actions and achievements are unchanged.

Build one library per variant with the v7 fast-path Makefile:

    make -C perf/v7 V7=$PWD/variants/v8 LIGHT_WINDOW=1 BUILD=build-v8-ore300 VARIANT="-DORE_PCT=300"
    TERRARIA_LITE_LIB=$PWD/perf/v7/build-v8-ore300/libterraria.so ...

The flags are recorded in `$(BUILD)/variant`. `ENV_VERSION` stays 7 (same
observation contract for the default view); a run's protocol records its library path.
