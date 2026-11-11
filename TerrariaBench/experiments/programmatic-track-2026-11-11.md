# Programmatic track follow-up: tb-api-1.0-rc1 — 2026-11-11

Follow-up to [`programmatic-track-2026-11-10.md`](programmatic-track-2026-11-10.md) (open issues 1–3). Goal: fix the
pathfinder's long climbs and water handling, close the map leak, and retry the unpaid proof before the Eye of Cthulhu
runs. Contract: [`terrariabench/tb/CONTRACT.md`](../terrariabench/tb/CONTRACT.md) (changelog at the end).

Summary:
- **Long climbs fixed.** `goto(..., place=True)` now pillars with Terraria's held use. Live: **5/5 climbs out of
  55–80-row shafts, 15.6–22.5 s each, 0 deaths**, through dug ceilings, torches and platforms in the pillar column.
  Before: 0 of 4 scripted attempts.
- **Map leak closed.** Tiles off screen now report what the player's map remembers (`Main.Map`). The new live test
  passes.
- **Breath is exposed, never managed.** `me()` has `breath`, `breath_max`, `breath_ticks_per_point` and `submerged`
  (checked live). `CAPABILITIES`, `CONTRACT.md` and the agent prompt say that staying alive in water is the agent's
  job.
- **Swim step now verified live** (follow-up below): 10/10 crossings of a natural open-air pond (world 41100108),
  0 deaths, after three `path.py` fixes for sloped banks. Before the fixes it failed every time. Before those
  fixes, the first live attempt in this session had not exercised the swim step at all (no reachable open-air pond).
- **Unpaid proof: anvil placed** in proof-16 (world 41100107, 681.2 game-s, scripted, not test mode, audit clean).
  Earlier attempts proof-11 to proof-15 failed (listed below).
- **Paid pilot (Opus 5.5, 16 wall-min): $1.737.** Published 7 (furnace placed, 5 bars), 0 deaths, audit clean.

## Changes (tb-api-1.0-rc1)
| Area | Change | Files |
|---|---|---|
| Pillaring | Held pillar: jump with use held and the cursor on the cell the feet leave, so the block lands the first tick the cell is clear of the body (`Collision.EmptyTile`, checked in the decompiled source). The cursor moves up a row after each landed block (detected by the held stack dropping), so one jump can place several rows. Before each jump it mines the f−3 ceiling (and f−4 best effort), mines torches/ropes/plants in the pillar column, and stands on platforms. Consecutive pillar steps run as one held climb. Running out of blocks raises `_NoBlocks` → `last_error` "out of blocks…"; a missing path that more blocks would fix → "out of blocks: the path needs N blocks to pillar, M in the inventory". Pillar cost 70 → 20 ticks/row (measured ~17–20) | `tb/path.py` |
| Executor | `tb.path.last_error` (no path / out of blocks / failed steps / timeout / died). Arrival check accepts feet sunk ≤ 8 px into the floor cell (half blocks, slopes), which used to fail every replan in the cave case | `tb/path.py`, `tb/__init__.py` |
| Water | Library scope is traversal only: no breath logic anywhere in `tb`. `me()` adds `breath_ticks_per_point` and `submerged` (`Collision.DrownCollision`). The agent status line shows "HEAD UNDER WATER breath n/200". The prompt, `CAPABILITIES` and `CONTRACT.md` state the rule | mod, `tb/__init__.py`, `tb/path.py`, `tools/terrabot/agent.py` |
| Map memory | `tiles`/`find_tiles` report lit on-screen cells live. Every other revealed cell reports the `Main.Map` entry, inverted via `MapHelper.tileLookup`/`wallLookup`/`liquidPosition`, with flag 512 `REMEMBERED` (`Grid.remembered`, `Cell.remembered`). Test-only `truth_edit` for the leak test | mod, `tb/grid.py`, proxy |
| Test setup | Test-only `truth_give` / `truth_morning` (torches/platforms and daylight for the live pathfinder tests on dev worlds). The proxy allows them only in test mode, and the audit flags test mode | mod, `session.py` |
| Proof | `05_build.py` carves a 17×3 room outward column by column, walking and lighting so cells are revealed before mining, and picks the anvil metal from what is held (anvil → 5 bars → more ore) | `tools/terrabot/proof/05_build.py` |
| Version | `tb-api-1.0-rc1` in the mod, `tb.API_VERSION`, proxy and prompt; changelog in `CONTRACT.md` | |

## Small fixes
1. **`tb.mine` on a stump** returned True at once when there was no trunk above. It now mines until the stump is gone.
2. **Offline fake game.** It had a released-key gap after every hold, which the real mod does not have (consecutive
   holds are continuous). It also placed blocks only on the first tick of a hold. Fixed so it models held use.
3. **Live test fragility.** The placement spot no longer picks tree/plant cells. `no_xray_tiles` compares lit cells
   with truth exactly, and remembered cells are covered by the map-memory test.
4. **Version-neutral texts** in the proxy manifest, audit and sandbox test.

## Tests
| Suite | Result |
|---|---|
| `tests/test_tb_path.py` (offline; 3 new: 60-row shaft with torches + platform, ceiling dig with/without `dig`, out-of-blocks message) | **33/33** |
| `tests/test_tb_agent.py` | 5/5 |
| Live climbs `tools/terrabot/climb_water_live.py climb` (runs `terrabot-dev-07`, `-08`; worlds 41100105/06) | **5/5** shafts ≥ 50 rows (below) |
| Live `live_tests.py` on a fresh session (`terrabot-live-04`, world 41100105) | **8/11**. `map_memory_no_leak` passes. The 3 failures (`basics` life < 100, `mining_reach_and_pickup`, `placement` "no block") all came from a Green Slime hitting the player at spawn (hurt events at ticks 1795–2875), not from the API. The same three passed on the first fresh run (`terrabot-dev-05`) |
| Live water (`climb_water_live.py water`, `terrabot-dev-08`) | breath fields ✓; plan to a pond bottom refused ✓; swim step not exercised (below) |

**Climbs:** 2-wide shafts dug with `goto(dig=True)`, lit every 6 rows, a Wood Platform every 18 rows, two blocks
placed over the head at the bottom (a ceiling to dig), then `goto(surface, dig=True, place=True)`. Shaft columns
were chosen with test-only truth (no liquid, no caves) because flooding is the agent's problem.
| Run | Rows | Climb (game s) | s/row | Blocks | Torches / platforms in column | Life | Result |
|---|---|---|---|---|---|---|---|
| dev-07 #1 | 55 | 18.5 | 0.34 | 39 | 9 / 3 | 100→100 | ✓ |
| dev-08 #1 | 55 | 19.9 | 0.36 | 35 | 10 / 3 | 100→100 | ✓ |
| dev-08 #2 | 55 | 15.6 | 0.28 | 39 | 10 / 3 | 100→100 | ✓ |
| dev-08 #3 | 55 | 18.5 | 0.34 | 35 | 10 / 3 | 100→100 | ✓ |
| dev-08 #4 | 80 | 22.5 | 0.28 | 58 | 14 / 4 | 100→100 | ✓ |

A 60-row climb out of a cave the shaft had broken into also succeeded (157 s). It needed 11 replans, which led to
the reach and half-block fixes above. Setup failures (shaft not dug to 50 rows: flooded cave, caves, hard tiles) are
not counted; they are digging and strategy problems.

**Leak test (`terrabot-live-04`):** the player walked off screen. Then three revealed cells were changed without a map
update: air→dirt (2092,299), dirt→air (2106,310), air→water (2093,299). Off screen, `tiles` returned the remembered
empty, the remembered Grass and no water, all flagged remembered, and `find_tiles("Dirt")` did not list the new
dirt. Back on screen, the live dirt and the hole showed. All three cells were then restored.

**Water:**
- `me()` read live while the head was under water: `submerged` true, breath 193→183 at 1 per 7 ticks
  (`breath_ticks_per_point` 7).
- `path_to` the bottom of a 5-deep pool returned None.
- The swim step was not exercised. The only pools found near reachable ground were cave pools under an overhang or
  over 600 columns away. The test player also stayed in that pool: **`goto` cannot start from deep water** (no
  path). It never plans into such water, but it cannot get out once in.

## Unpaid scripted proof (dev world 41100107, `runs/terrabot-proof-11`)
Wood 25 s, gel 329 s, bench + torches 2 s, dig 602 s (100 rows, 13 iron, out of torches). In `05_build` the room and
the furnace worked: published 6, incl. furnace_1; 0 deaths; audit clean. The next station placement then failed,
and the failure path's `tb.screenshot()` crashed. The cause was the harness: `run.py` was started with the system
python, which has no PIL. Then `goto(home, place=True)` returned False. **Still no scripted placed anvil.** It also
had only 13 iron, and 15 are needed. A rerun must use `.venv/bin/python` (the pilot did). Not rerun within this
session.

**Rerun `runs/terrabot-proof-12`** (dev world 41100108, `.venv/bin/python`, 15 game-min). Milestones: wood 9 s,
bench 12 s, torches 442 s, furnace placed 916 s. Published 6, 4 deaths (slimes while gathering gel, one death while
digging), audit clean.
- The bench was not picked back up after step 3, so the underground build had no bench to place.
- `04_dig` found **0 iron/lead** (died and respawned mid-dig).
- `05_build` climbed back toward home, placed the furnace on the surface, and then failed with no stations or bars.

No anvil. The remaining gap is scripted strategy (ore finding, survival, carrying the bench), not the API. Two
goto calls in these runs returned False:
- proof-11's climb home, from 100 rows down in dark, partly unrevealed tunnels (not the lit shafts of the climb
  test);
- proof-12's walk home on the surface.

## Paid pilot (cap $3; this pilot capped at $2)
| Run | Model | World | Wall | Calls | Spend | Outcome |
|---|---|---|---|---|---|---|
| pilot-opus-02 | claude-opus-5-5 medium | 41100106 | 0 | 0 | $0.000 | crashed before the first call (system python without PIL) |
| **pilot-opus-03** | claude-opus-5-5 medium | 41100106 | 16 min (918 game-s) | 34 | **$1.7368** | wood 16 s, bench 132 s, torches 133 s, **furnace 546 s, 5 bars 571 s** (iron, tin, tungsten bars crafted), wood helmet; published 7; 0 deaths; 3 program errors; audit clean |

- **Prompt changes:** the agent read `tb.path.last_error` after failed gotos (13 programs use `goto`).
- **Not exercised:** it did not need a long pillar climb or a swim in 15 game-minutes.
- **Spend ledger:** this task $1.7368 settled, 0 open reservations. Shared TerraBot ledger total $4.2156
  ($2.4788 before).

## Remaining limits
- **Swim step:** verified live on one natural pond (10/10, world 41100108). The wide-pool case (> 20 columns, no
  exit) was not recorded live: the player died about 10 times at night on the 1,200-column walk there. `goto`
  cannot leave deep water once in it; getting out is the agent's job.
- **Map memory gaps:** remembered cells lack slopes, half blocks, liquid under a tile and walls behind a tile, as
  the map does. The game itself refreshes revealed map cells when a tile is re-framed anywhere (the full-screen map
  shows such changes too).
- **Darkness:** in the dark, cells stay unknown, and `tb.mine` refuses unrevealed tiles. Digging needs torches.
- **Scripted proof:** a placed anvil is still missing. Ore finding (13/15 iron) and the harness python must be fixed
  before a rerun.
- **Live test flakiness:** `live_tests.py` assumes an undisturbed fresh spawn. Slimes can break 3 checks.

## Follow-up 2026-11-11 (afternoon): live swim and placed anvil (unpaid)
### Swim (run `runs/terrabot-swim-02`, world 41100108)
**The pond:**
- Natural, open-air: surface row 239, columns 2307–2312 (6 wide), 3 deep, open sky for 92 rows. Its rim has
  **sloped** tiles.
- Found with a test-only `truth_tiles` scan of the surface band of worlds 05–08; the other candidates were in
  caves, more than 20 columns wide, or could only be swum one way.
- Reaching it took `goto(dig=True, place=True)` with test-only `truth_give` torches/dirt, because there is no
  path over a hill with an overhang without digging. All test cases used `dig=False, place=False`.

| Case | Before fixes | After fixes |
|---|---|---|
| Cross and back (`swim` in every plan) | 0/2 (stuck in the pond, no path) | **10/10** (round trips 4 + 1): across 3.0–8.7 s, back 2.6–3.7 s, min breath 199, head under for 0–2 reads, 0 deaths |
| Goal at the pond bottom (2309,241) | `path_to` None, but `goto` walked the player into the water | ✓ ×3: `path_to` None, `goto` False, player stayed dry |
| Goal in the enclosed channel (2299,242) | – | ✓ None / False / dry |
| Breath while sunk | – | ✓ ×2: `submerged` true, breath 200→183, 1 point per 7 ticks |

**`path.py` fixes:**
1. The swim exit must have dry feet. The planner used to end the swim on a node held up only by the sloped rim,
   and the player slid into 2-deep water.
2. A slope alone no longer holds a node whose feet are in water.
3. `_swim` walks once the player is out of the water at or above the exit row. Walk/step/fall steps that lead
   into a swim run inside `_swim`, so the player no longer slips off the sloped bank before the swim starts.

Offline tests: `/` (sloped solid) added to the fixtures, plus `test_swim_exits_onto_dry_bank` and
`test_swim_onto_bank_next_to_the_rim`. 35/35 pass, and the planner test fails on the old `path.py`.

**Dev-session drowning:** the player drowned once outside any recorded case, after a debugging script left it in
the pond. A `.jsonl` line where the player never reached the bank is marked invalid.

### Scripted proof to a placed anvil (world 41100107, scripted mode, public `tb` API only)
| Run | Bench | 10 torches | Furnace placed | 5 bars | Anvil placed | Deaths | Published / ext. | Failure |
|---|---|---|---|---|---|---|---|---|
| proof-13 | 53.7 | 446.7 | – | – | – | 0 | 6 / 6 | `04_dig` looped on "shaft wet" with both sides wet; 9 gel, 4 iron; killed after 859 s wall |
| proof-14 | 37.1 | 296.8 | 705.1 | 720.6 | – | 0 | 7 / 10 | furnace placed 12 columns from the bench, so the anvil craft had no bench in reach |
| proof-15 | 34.4 | 293.0 | crafted 788.5, not placed | – | – | 0 | 6 / 5 | no 3×2 spot at the shaft bottom; room torches blocked the furnace |
| **proof-16** | 34.8 | 414.1 | 680.2 | 680.6 | **681.2 (Iron Anvil at 2108,319)** | 1 (Pinky) | **7 / 10** | – (all programs ok, audit clean) |

Proof-16's extended score has `anvil_held` 681.0 and `anvil_placed` 681.2; the published list has no anvil entry.
It succeeded once, on one world; it was not repeated on worlds 05, 06 or 08.

**Strategy changes in `tools/terrabot/proof/`:**
- **Wood and bench:** gather 85 wood; pick the bench back up and verify it is in the inventory, or craft a spare
  from wood.
- **Gel and night:** collect gel with rests when hurt, and go underground before dusk.
- **Digging for ore:** dig to the underground layer, then zigzag tunnels. Mine revealed iron/lead found with
  `find_tiles` until 15 of one metal. Torches go only where darkness stops the dig.
- **Survival underground:** rest when hurt, leave water, craft torches underground.
- **Building:** carve the room first, and remove torches from its low rows. Place a second bench next to the
  furnace when needed.
