# v10 PPO policy in real Terraria: transfer proof of concept, 2026-11-08

Question: does the Terraria-Lite v10 generic PPO policy (1B steps, seed 3001, final checkpoint `step-1073741824.pt`)
still behave sensibly when it drives the player in the real game (tModLoader 1.4.4.9), with no retraining?

Answer, crude and from one run: **partly yes.** The surface opening transferred. It chopped trees, collected
wood, crafted and placed a work bench, crafted a wooden sword, a wood breastplate, torches and platforms, placed
torches, killed slimes and walked 72 columns. It took no deaths in 1,500 steps. It never dug down, never got
stone or ore, and spammed wood platforms (90 crafted). In the simulator the same policy reaches ~15
achievements in 1,500 steps and usually starts digging by step ~900. In the real game it reached 9.

Video (game time only, one frame per policy step, 12 fps, caption = step/action/inventory):
`~/Downloads/v10-policy-real-terraria-poc.mp4` on the Mac. The raw run is on Omarchy at
`~/Projects/TerrariaBench/runs/v10-poc/v10-poc-01/`. Compact records:
[`results/v10-transfer-poc-2026-11-08/`](results/v10-transfer-poc-2026-11-08/): `steps.jsonl.gz` (one line per step:
action, probability, legal count, shortcut results, position, life, inventory, sim achievements), `summary.json`,
`extended-score.json`.

## Setup

| | |
|---|---|
| Policy | v10 generic PPO (`architecture: targets`, 481k params), CPU torch on the Mac, sampled from the masked policy with the training-time 1 % uniform mix over legal actions (`unimix 0.01`), seed 12345 |
| Game | world `default-v07-32000401` (crimson, small classic), fresh starter character, normal PvE and hostile damage on, 1024×1024 window, zoom 1, Color lighting, own isolated Xwayland display `:21` (removed afterwards; the landscape runs on `:11`–`:15` were not touched) |
| Lockstep | observer **0.8-poc** (= observer 0.7 + `tools/v10_transfer/PocBridge.cs`, installed only into this run's profile). After each action, the game thread blocks inside `PostUpdateEverything` and writes the state until the driver sends the next command, so the game is paused between steps. Each action holds its inputs for exactly **15 game updates**, verified by the tick counter: 1,500 steps = 22,500 updates = 6.25 game-minutes. |
| Observation | the mod exports a 49×37 tile window (type, frame, solid, `Lighting.Brightness`, liquid), hostile NPCs within 40×30 tiles, the player (position, velocity, life, jump, item animation, immunity, potion delay, fall start, tool hit damage), the inventory, day/night time and the layer lines. `policy_driver.py` maps tiles and mobs to the sim kinds. `bridge.c` writes them into a synthetic v10 `Env` and calls the simulator's own `env_obs` and `env_action_mask`, built from the committed v10 sources with `INV_LOG=1`. |
| Encoder check | `bridge_parity.c` rebuilds 2,400 real simulator states (4 seeds × 600 random legal steps) through the bridge from a 49×37 window. **0 observation mismatches and 0 mask mismatches.** The only exclusion is the per-mob movement-phase channel, which the bridge sends as 0 because the real game has no counterpart. |
| Actions | Movement, jump, climb and drop are the player's control flags. Mining, placing, attacking and using items are `controlUseItem` with the mouse set to the target reach cell (cell centre) or, for attacks, 24 px in the facing direction. All of these are set in `ModPlayer.SetControls` for the 15 updates. Mining picks the copper axe for tree tiles and the best pickaxe otherwise; the sim picks the tool implicitly. |
| Declared shortcuts (not game input) | `hold` (select an inventory item; it is swapped into hotbar slot 10 if needed), `craft` (one real recipe: real ingredients incl. recipe groups, real station adjacency via `Player.AdjTiles`, product spawned at the player and journaled as `crafted` with `via: v10_poc_shortcut`), `loot` (Loot All of a chest within 4 tiles; never used in this run), `equip` (body armour). No game rule was changed. |
| Wall time | 452 s for 1,500 steps (~0.3 s per step incl. ssh round trip, encoding, inference and the screenshot) |

Reproduce:

```sh
# Mac: bridge library from the committed v10 sources
git archive HEAD variants/v10 src/capi.c | tar -x -C /tmp/v10poc && cd /tmp/v10poc && S=variants/v10/src && \
  gcc -std=c11 -O2 -DINV_LOG=1 -Ivariants/v10/include -I$S -fPIC -fvisibility=hidden -shared $S/{sim,worldgen,light,obs,mobs,boss}.c \
  src/capi.c <repo>/TerrariaBench/tools/v10_transfer/bridge.c -o libv10bridge.dylib -lm
# Omarchy: observer 0.8-poc
bash tools/v10_transfer/build_mod.sh
# Mac: run (starts game_server.py on Omarchy over ssh, display :21, frames to runs/v10-poc/<run>/frames)
TERRARIA_LITE_LIB=/tmp/v10poc/libv10bridge.dylib PYTHONPATH=python .venv/bin/python \
  TerrariaBench/tools/v10_transfer/policy_driver.py --checkpoint <ckpt> --steps 1500 --run v10-poc-01 --log /tmp/v10poc/v10-poc-01.jsonl
```

## Results (run v10-poc-01, 1,500 steps)

| | real Terraria (this run) | simulator, same checkpoint, 16 validation seeds, 1,500 steps |
|---|---|---|
| v10 achievements | **9**: place block (step 34), collect wood (69), place platform (95), craft workbench (102), craft wooden sword (180), craft wood breastplate (184), defeat Blue Slime (234), place torch (436), explore 30 columns (744) | mean **14.8** (max 17); also climb rope, heal, open chest, collect stone (15/16, median step 930), craft furnace (12/16), collect copper (8/16), reach caverns (4/16) |
| Deaths | 0 (min life 82, 3 slime kills, mobs in view on 501 steps; no night within 6.25 game-min) | 0 |
| Depth | max 2 tiles below the start, surface only | mean peak row 55 (underground) |
| Mean probability of the sampled action | 0.067 (28 legal actions on average) | 0.095 (27 legal) |
| Final inventory | 57 wood, 19 torches, 2 work benches, 8 platforms, 2 dirt, wooden sword, wood breastplate | – |

The achievements in this table are the v10 achievements that the bridge tracks for the policy's observation.
They are inferred from inventory, shortcut results and NPC disappearances, so they are approximate.

Benchmark scoring (`tools/extended_score.py runs/v10-poc/v10-poc-01`):

- **Extended 4 of 19**: gel at 91 s, torches crafted at 105 s, work bench placed at 45 s, wood armour crafted
  at 46 s.
- The header says `observer_version 0.7` because 0.8-poc reuses 0.7's journal unchanged.
- **Published score 0 by rule.** The journal reached wood_1, wood_10, wood_25, workbench_1 and torch_10, but
  published scoring only credits milestones preceded by an agent input in `inputs.jsonl`. This run has no such
  file because inputs were injected as control flags, not XTEST.
- Of the extended facts, two depend on the declared craft shortcut (torch_crafted, wood_armor_crafted).
  workbench_placed is a real placement, but the bench itself came from the shortcut.

Action mix (1,500 steps):

| Action group | Steps |
|---|---|
| mine | 591 |
| place | 400 |
| select | 151 |
| noop | 73 |
| right | 70 |
| craft | 56 (45 of them platforms) |
| cycle weapon | 53 |
| left | 44 |
| jump | 29 |
| attack | 17 |
| drop through platform | 15 |
| eat mushroom | 1 |

Every `hold` and `craft` command succeeded (the mask allowed only satisfiable crafts). The only failure was `equip`
of the freshly crafted breastplate (see gap 3).

## What transferred

- **Tree chopping and the wood economy.** It goes to trees, hits a trunk until it falls (the dig-damage
  observation from `Player.hitTile` matters, see below), picks up wood and repeats along the forest. Wood 25 came
  within ~3 game-min.
- **The crafting opening.** Order: workbench, wooden sword, wood breastplate, torches (from slime gel), then
  platforms. The sim opening has the same order.
- **Placement.** Blocks, torches, platforms and work benches were placed at the targeted reach cells. Real
  placement and mining land exactly where the sim reach geometry says (mouse aim through `Main.mouseX/Y`
  works).
- **Combat when needed.** It killed 3 slimes and ended at 94–100 life.

## What did not transfer

- **Going underground.** It never mined downward through dirt into stone. The sim policy digs down after its
  surface opening (stone in 15/16 seeds by ~930 steps). In the real forest it stayed in a
  chop/place-platform/craft-platform loop: 90 platforms crafted, 276 platform holds.
- **Confidence.** Probabilities of the sampled actions are ~30 % lower than in the sim. The observations are in
  distribution enough to act, but not sharply.

## Mapping gaps (biggest first)

1. **Input path.** The actions are control flags plus mouse position set inside the game (`ModPlayer.SetControls`),
   not XTEST key and mouse events. Effects are the same as held keys and buttons, but the run has no
   `inputs.jsonl`, so published scoring cannot attribute milestones. A faithful version needs XTEST input with the
   game unpaused for exactly 15 updates. That needs an update-count barrier: XTEST timing against SIGSTOP gives
   ±1–2 updates.
2. **Declared shortcuts.** Crafting skips the crafting UI. `hold` replaces hotbar keys or inventory dragging,
   `loot` replaces the chest UI and `equip` replaces armour dragging. All use real recipes, stations and items,
   but a UI-faithful version needs scripted crafting-menu clicks (slow, and scrolling depends on the number of
   available recipes).
3. **Crafted items arrive a tick later.** The product is spawned at the player and picked up on the next update.
   `equip` in the same step therefore found no breastplate, so armour was never equipped (sim crafting
   auto-equips). Fix: insert the item straight into the inventory, or equip on the next step.
4. **Tile taxonomy (24 kinds).** Plants, tall grass, herbs, small and large piles and cobwebs (tile 51:
   27,970 cell-steps, it slows the player in the real game) become air. Tin, lead, tungsten and platinum merge
   into copper, iron, silver and gold. Sand, clay, mud, silt, snow and ash become dirt. Marble, granite,
   sandstone, ice, ebonstone and crimstone become stone. Water and lava are invisible (none met in this run).
   Real trees have roots and branches; only the trunk column is a sim log. Multi-tile stations and chests are
   approximated cell by cell. Unmapped counts are in `summary.json` (all decorative non-solid tiles; no unmapped
   solid tile and no unmapped mob in this run).
5. **Scale.** The real world is 4,200×1,200 tiles; the sim world is 128×128. The bridge pins the sim
   x-coordinate to 64 + (real column − spawn column), clamped to 20–107. Depth is mapped piecewise so the layer
   one-hot matches the real layer (surface 22–38, underground 39–63, caverns 64+). The ACROSS/DEPTH scalars and
   the explore achievement are therefore only qualitatively right.
6. **Time.** A sim day is 1,800 + 1,200 steps (7.5 + 5 game-min at 15 ticks per step). A real day is 15 + 9
   game-min. The bridge maps the real day phase onto the sim cycle, so the day-phase input advances half as fast
   as in training, and the 10,000-step episode clock is approximate. This run never reached night.
7. **Mobs.** Only 5 kinds. NPCs are mapped by AI style and name (slimes, bats, fighters → zombie, skeletons,
   flyers → demon eye). The movement-phase channel is 0. Kills are inferred when a mapped NPC that was within
   4 tiles disappears (also counts despawns). The Eye of Cthulhu maps to the boss slot (not met).
8. **Policy-side bookkeeping.** The achievement mask, selected placeable, current weapon and `safe_ticks` (steps
   since last damage) are kept by the driver, not read from the game. The achievement bits feed the policy, so
   inference errors become observation errors.
9. **Light.** `Lighting.Brightness` 0–1 is scaled to the sim's 0–15 levels. The unknown-tile threshold (level
   < 2) then follows real lighting; the scale was not calibrated against the sim's propagation constants.
10. **Physics and tool timing** are the ones v10 ported (20×42 hitbox, 15 ticks per action, copper tool
    times), so movement and chopping matched well. Real auto-swing and reach details were not checked step by
    step.

## What a faithful version needs

- An XTEST input path with an exact update-count barrier, and scripted crafting through the real UI. Or accept
  and declare the shortcuts, but journal agent-driven inputs so scoring can attribute milestones.
- A richer tile and mob taxonomy, or explicit "other solid / other decor / liquid" kinds, with the policy
  retrained on a sim that has them (liquids, cobwebs and tin/lead variants exist in every real world).
- Real-scale time and world coordinates in training, or randomised scale, so the day-phase and position scalars
  are not out of range.
- More than one world and seed. This is a single 1,500-step run on one world: the numbers are an anecdote.

## Files

- `tools/v10_transfer/PocBridge.cs`: observer 0.8-poc additions (lockstep, state export, control injection,
  shortcuts). Inert unless `TERRARIABENCH_POC_DIR` is set; built separately by `tools/v10_transfer/build_mod.sh`.
  `mod/` is unchanged.
- `tools/v10_transfer/game_server.py`: Omarchy side (own isolated display, launch, lockstep protocol, one frame per
  step, cleanup).
- `tools/v10_transfer/policy_driver.py`: Mac side (mapping, bridge, policy, action translation, logs).
- `tools/v10_transfer/bridge.c`, `bridge_parity.c`: synthetic v10 Env encoder and its parity check.
