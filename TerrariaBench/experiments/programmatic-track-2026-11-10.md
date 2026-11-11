# Programmatic track (TerrariaBench-API, official Terraria), first build — 2026-11-10

Question: can the official game be played through a generic bot API (Mineflayer-style; the model writes short
Python programs) under the plan's rules — real mechanics only, no X-ray, normal difficulty, unseen worlds — and is
the API sufficient to reach workbench → furnace → anvil?

Answer, from 12 scripted runs and 2 LLM pilots:
- **The full stack works end to end:** the TerraBot mod, the `tb` client, the sandbox runner, the pathfinder, the
  agent loop, the recorder and the audit. The leakage tests pass.
- **The API is sufficient for the whole opening.** Claude Opus 5.5 got from a fresh character on an unseen world to
  a **placed Lead Anvil in 1,377 game-seconds** (≈23 game-minutes; one 35-minute pilot, $2.43). On the way it
  crafted and placed a work bench and a furnace, smelted 5 bars and made wood armour.
- **The unpaid scripted proof fell short of a placed anvil.** The best run reached workbench → furnace → 5 bars →
  **a crafted Lead Anvil** in 693 game-seconds with 1 death. It then failed to place the anvil: the room it had dug
  was too cramped. Across 10 proof runs, ore finding, flooded caves and station placement underground were the
  failure points. The API never was.
- **Total gateway spend: $2.48 of the $10 cap.**
- Scope: official Terraria only. Terraria-Lite-API and the multiplayer team variant are future work (see the end).

## Design

| Layer | Files | Notes |
|---|---|---|
| TerraBot mod (tModLoader 1.4.4) | `mod/TerraBot/` (separate mod; the observer and its deployed build are untouched) | Unix-socket JSON-lines server, enabled only when `TERRABOT_SOCKET` is set. Requests run on the game thread, both before the player update and after each update, so consecutive holds leave no released-key gap (measured: 5 holds of 3 ticks each jump exactly as high as one 15-tick hold, 5.22 tiles). Journals `game_events.jsonl` and `game_actions.jsonl` |
| Proxy | `tools/terrabot/session.py` | The only socket a program can reach. Whitelists tb-api-1.0 ops and journals every action to `inputs.jsonl` (`actor: agent`, `dispatch: tb-api`, wall-clock start/end). Sends `stop` when a program disconnects. Takes screenshots |
| `tb` library | `terrariabench/tb/` (`__init__.py`, `grid.py`, `path.py`, `CONTRACT.md`) | Reads, holds, use/mine/place/swing, craft/equip/chest, `goto` pathfinder, persistent `tb.store`. Programs get a frozen copy |
| Sandbox | `tools/terrabot/sandbox.py`, `sandbox_boot.py` | `python -I -S`, audit hook, `unshare -rn` on Linux (no network namespace at all), rlimits. Imports: stdlib + `tb` + workspace modules. Files: workspace only. Wall-clock limit per program (default 60 s, agent-chosen up to 600 s) |
| Agent loop | `tools/terrabot/agent.py` | Each turn the model writes `<program timeout=…>` plus optional `<notes>` and `<file path="lib/…">`. The program runs while the game continues. The next turn shows stdout/stderr, new events, a status line, the notes and the workspace module list, and a screenshot on request. The newest 6 turns are kept. Shared ledger with a reservation before every call |
| Harness | `tools/terrabot/run.py` (`live-test`, `scripted`), `dev_session.py` | Own copy of the fixture, own tML save dir. Observer 0.7 + TerraBot enabled in that copy only. Recorder `desktop.mp4` on the slot's output |
| Audit | `tools/terrabot/audit.py` | Scripted journal audit of every run (below) |
| Scoring | `tools/extended_score.py` (additive change) | Adds `track`, `api`, `agent_kind`, `input_dispatch`. Published scoring is unchanged: it credits API-driven milestones because the proxy journal supplies the agent receipts the transfer PoC lacked |

Game conditions: Classic, normal enemies and contact damage (`TERRARIABENCH_PVE=enabled`,
`TERRARIABENCH_HOSTILE_DAMAGE=on`), fresh starter character with plain prefixes. Unseen small worlds were generated
for this work (`runs/terrabot-fixtures/tb-411001{01..08}`, `tools/make_world_fixtures.py`). The game runs in real
time and does not pause while the model thinks.

## API contract tb-api-1.0 (draft)

Full text: [`terrariabench/tb/CONTRACT.md`](../terrariabench/tb/CONTRACT.md). Function list:

- **Read:** `me`, `inventory`, `count`/`has`, `time`, `world`, `tiles(x0,y0,x1,y1)` → `Grid`, `find_tiles(kind, radius)`, `npcs(radius)`,
  `items_near`, `events(since)`, `recipes(item, available)`, `chest`.
- **Move:** `hold(keys, ticks, aim)`, `walk`, `jump`, `face`, `stop`, `sleep`, `goto(x, y, dig, place, near, timeout)`,
  `path_to`.
- **Use:** `select`, `use_at`, `mine`, `place`, `swing_at`.
- **Craft/containers:** `craft(item, n)`, `equip`, `open_chest`, `take`, `put`, `close_chest`.
- **Meta:** `screenshot`, `log`, `store`.

Mechanics:
- **Movement and use** are real control flags and cursor for exactly N updates.
- **`craft`** calls `Main.CraftItem` (the crafting menu's own click handler) after `Player.AdjTiles` + `Recipe.FindRecipes`.
- **`equip`** calls `ItemSlot.SwapEquip`.
- **Chests** must be opened by the player's own `use_tile`. Transfers go through `ChestUI.LootAll` or stack moves.
- **Declared UI shortcuts:** select, craft, equip and chest transfers skip cursor movement inside the inventory UI.
- **Not available:** teleport, item spawn, tile edits, time control, NPC control.

Leakage rules:
- **Tiles:** a tile is known only if it is revealed on the player's own map (`WorldMap.IsRevealed`) or lit on screen.
  A revealed tile reports its *current* state (documented small leak).
- **NPCs and items:** only on-screen and lit ones, or anything within 4 tiles. NPC fields: id, name, type,
  position, size, life, hostile/boss/town. No AI state or velocity.
- **Events:** only what the screen or chat shows.
- **Test-only ops:** truth ops exist only in test mode. The proxy refuses them otherwise, and the audit flags any
  test-mode run.

## Tests

| Suite | Result |
|---|---|
| In-game API tests `tools/terrabot/live_tests.py` (runs `terrabot-live-02`, `-03`, world 41100101) | **10/10 pass** |
| Pathfinder offline tests `tests/test_tb_path.py` (ASCII grids + fake-physics executor) | **30/30 pass** |
| Sandbox `tests/test_tb_sandbox.py` (Mac and Omarchy; network namespace active on Linux) | **18/18 pass** |
| Agent loop helpers `tests/test_tb_agent.py` (reply parsing, ledger reservations refuse before calling, API reference) | **5/5 pass** |

**What the live tests check:**
- **No X-ray, tiles:** at spawn, 3,165 of 40,000 cells are known and all equal ground truth. 0 cells more than 40
  rows below the player are known, against 14,067 solid cells there in truth.
- **No X-ray, ores:** 314 ore cells exist within 100 tiles; `find_tiles` returns 0.
- **No X-ray, NPCs:** `npcs` is a subset of truth with exactly the whitelisted fields.
- **Real recipes:** "missing Wood 0/10"; Furnace refused for "missing station WorkBenches, Stone Block 0/20, Any Wood 0/4, Torch 0/3".
- **Reach:** an out-of-reach tile stays intact.
- **Real mining and pickup:** produce `tile_broken` and `pickup` events.
- **Placement:** placing a block works.
- **Movement limits:** max |vx| 3.06 px/tick; jump rise 5.22 tiles.
- **Proxy:** refuses `teleport`, `spawn_item` and `set_tile`.
- **Journal:** the input journal has only agent receipts.

### Pathfinder capabilities and limits
Published in `tb/path.py` as `CAPABILITIES`, and rendered into the agent prompt.

**Does:**
- walk and step up;
- jumps up to 4 rows and gaps of about 3 tiles (arc simulated with calibrated vanilla physics);
- falls (up to 25 rows; deeper only at a high cost);
- platforms up and down, ropes, doors;
- surface swims across ponds up to 20 columns wide;
- `dig` (mines solid or unrevealed cells in the way);
- `pillar` (places solid blocks under the feet);
- never enters lava, never plans the head under water, never mines a cell next to liquid;
- closed-loop execution with replanning.

**Does not:** dive, use hooks or mounts, bridge, handle enemies, or model falling sand or flooding from afar.

**Observed in the real game:**
- **Works:** surface walks of 25 tiles (4.4 s), digging 8 rows down (16.5 s), chasing items and enemies, digging to ore.
- **Swimming:** the first version walked into a 14-deep spawn pond and drowned. The water rules and swim step above
  came from that, but the swim step is only tested offline.
- **Long climbs fail:** climbing 40–100 rows back up a shaft with `goto(..., place=True)` returned False in all
  scripted attempts (proofs 07–10). Agents should build where they are, which Opus did.
- **Stumps:** `tb.mine` on a tree stump returns True (the tree above is gone), which caused one chop loop in the
  Opus run. This is documented in the docstring.

## Unpaid scripted proof

Programs: `tools/terrabot/proof/01_wood … 05_build` plus `lib/botlib.py`. They use only the public `tb` API and run
in the sandbox, each with its own time limit:
1. Wood, then a bench and a wooden sword.
2. Gel from slimes.
3. Torches.
4. Shaft and tunnels with torches, mining the iron/lead ore that becomes visible.
5. Room, bench, furnace, bars, anvil.

All runs: `runs/terrabot-proof-01…10`. Compact records are in
`results/programmatic-track-2026-11-10/terrabot-proof-*`. Times are game-seconds; the audit verdict was clean on all
runs, except one false positive that was fixed.

| Run | World | Bench placed | Torches | Furnace placed | 5 bars | Anvil | Deaths | Published / ext. | Failure |
|---|---|---|---|---|---|---|---|---|---|
| proof-01 | 41100103 | – | – | – | – | – | 5 | 4 / 1 | killed by Eater of Souls while hunting gel in the corruption; bench spot out of reach |
| proof-03/04 | 41100104 | 18 / 17 | 147 / 326 | – | – | – | 1 / 1 | 5 / 6 | drowned in a flooded cave (dig released water) |
| proof-05 | 41100104 | 25 | 152 | 1,622 | – (4 bars) | – | 1 | 6 / 8 | 12 lead ore, 15 needed |
| proof-06 | 41100104 | 26 | 461 | – | – | – | 0 | 6 / 6 | furnace could not be placed in a 3-tall tunnel |
| **proof-07** | 41100104 | **16** | **356** | **692** | **693** | **crafted 693, not placed** | 1 | **7 / 11** | room too small to place the anvil |
| proof-08 | 41100104 | 24 | 342 | 1,874 | – | – | 1 | 6 / 8 | out of torches at depth; 13 lead |
| proof-09 | 41100105 (held out) | 25 | 500 | 1,926 | – | – | 0 | 6 / 7 | 0 lead in 1,400 s of tunnels (truth: lead sparse above row +120) |
| proof-10 | 41100106 (held out) | 26 | 578 | 788 | – | – | 2 | 6 / 6 | flooded caves; chose lead with 10 iron in hand (bug, fixed afterwards) |

proof-02 stopped at the bench step (no flat spot within 8 tiles).

**Wall time:** ≈ game time (real-time game). Wood takes ~20 s, gel 2–9 min, digging 2–24 min.

**Reading:** the API covered every step of the chain:
- real stations through adjacency;
- recipe groups ("Any Wood");
- real smelting at the furnace;
- `crafted` entries in the observer journal (`RecipeItemCreationContext`);
- placements in the journal.

The scripted *strategy* was the bottleneck: ore finding without X-ray, flooded caves and cramped rooms.

## Paid pilots (cap $10; ledger `results/programmatic-track-2026-11-10/ledger.jsonl`)

| Run | Model | World | Wall | Turns / programs | Spend | Outcome |
|---|---|---|---|---|---|---|
| price probe | gpt-6-astra (exists on the gateway, `gpt-6-astra-2026-09-03`) | – | – | 2 calls | $0.038 | fitted **$8.50/M input, $33.96/M output** (no cache discount observed), so pricier than Opus 5.5 list prices |
| pilot-luna-01 (loop debug) | gpt-6-luna, reasoning low | 41100107 | 8 min | 25 / 25 (2 timeouts, 2 errors) | $0.013 | work bench crafted and placed, torches; published 3; 2 deaths |
| **pilot-opus-01** | claude-opus-5-5, reasoning medium | 41100108 | 35 min (wall budget) | 47 / 46 (1 error, 0 timeouts) | **$2.428** | **work bench 117 s, torches 165 s, wood armour 156 s, furnace placed 1,030 s, Lead Bar + Lead Anvil crafted 1,031 s, 5 bars held 1,709 s, anvil placed 1,377 s**; wood_100; published 7 (wood_1/10/25/100, workbench_1, furnace_1, early_bar_5); extended 15 of 19; 3 deaths (one fall into a deep cave) |

**Total spend: $2.479** ($0.038 probe + $0.013 Luna + $2.428 Opus). Reservations are settled; the ledger cap was never
approached.

**The Opus run:**
- **Its own library:** it wrote `lib/dig.py`, `lib/fight.py` and `lib/ore.py`.
- **Notes:** it kept notes with coordinates of its station pocket and hazards ("Water w/ deadly Blue Jellyfish
  near (2112,460) – avoid").
- **Planning:** it planned around its own deaths ("Don't goto deep targets with long drops").
- **Stations:** it built its stations in a pocket underground, which is exactly what the scripted proof failed to do.

**Audit:** both pilots are clean (no teleport, every inventory gain explained, every craft journaled by the
observer, only contract ops). Every published milestone is attributed via `inputs.jsonl`; without attribution the
published score would be 0.

**Cost per game-hour:**

| Model | Measured | Per game-hour | Notes |
|---|---|---|---|
| Opus 5.5 | $2.43 for 0.58 game-hours | **≈ $4.2** | ~$0.05–0.07 per turn at ~14k prompt tokens, list price |
| GPT-6 Astra | not run | [INFERENCE] ≈ $8–10 | at the same token counts |
| GPT-6 Luna | – | < $0.1 | |

A run to the Eye of Cthulhu, if it takes 2–4 game-hours, would cost ≈ $8–17 with Opus. That is at the low end of the
plan's $10–60 estimate.

## Audit (`tools/terrabot/audit.py`, run on every run; `audit.json` per run)
Checks:
- journal integrity and gaps;
- a teleport check on heartbeat displacement;
- item provenance: every inventory gain explained by a pickup/craft/chest event, coins excluded because they convert;
- craft provenance against observer `crafted` entries;
- attribution: published score with and without the input journal;
- non-contract ops and test mode;
- program timeouts and errors.

Results:
- **No gaming flags on any scored run.** One false positive (copper → silver coin conversion) was fixed.
- **Harness note on every run:** the observer has no `end` event, because the harness kills the game without
  unloading the world. This is the same as in other campaigns.
- **No LLM auditor was run.**

## Open questions / issues
1. **Scripted proof to a placed anvil is still missing.** Fix: dig a larger room (or place stations on revealed cave
   floors) and choose the ore type from what is held (fixed in `05_build.py` after proof-10). A re-run needs a slot.
   The LLM pilot already showed the chain is reachable through the API.
2. **Pathfinder:**
   - long vertical climbs (pillar up a deep shaft) fail;
   - swimming is only tested offline;
   - no dive or breath management.
   Treat these as limits of tb-api-1.0's library, or improve before freezing.
3. **Leak:** a revealed tile shows its current state, not the remembered map state. This is minor, but could be
   closed by reading `Main.Map[x, y]` for off-screen cells.
4. **Declared UI shortcuts** (craft/select/equip/chest without cursor travel). Decide whether to keep them for the
   leaderboard (recommended) and label them.
5. **Real time:** the game does not pause while the model thinks (as designed). Night zombies killed the scripted
   bot repeatedly on the surface. Model latency is part of the score; state that on the leaderboard.
6. **Turn context** keeps 6 turns plus notes. Untested for multi-hour runs (context growth, notes quality).
7. **GPT-6 Astra prices** come from 2 probes. Re-fit before a paid Astra run.

## Plan for Eye of Cthulhu runs
- **Freeze:** tb-api-1.0 plus the library (after fixing items 1–2), the prompt and `agent.py`. Hash them in the
  manifest.
- **Budget:**
  - up to 4 wall-hours per run, with a hard $15 per-run cap through the same ledger;
  - stop on `eye_of_cthulhu_defeated`, the wall budget or the cap.
- **Matrix:** 3 held-out worlds (generate fresh seeds; `tb-411001{05..08}` were seen during development) × Opus 5.5
  (+ Astra if its price is acceptable) ≈ 6 runs ≈ $60–90.
- **Report:**
  - time to each milestone in game and wall time;
  - deaths, programs, API calls (`api_calls.json`), tokens and cost;
  - the per-run audit;
  - the labels in `manifest.json` (what the agent saw, what it could do, who helped).
- **Slots:** one Omarchy slot per run. Runs need about 3 GB RAM each.

## Future work (out of scope here)
- **Terraria-Lite-API:** the same tb-style API over the simulator, for cheap and exactly replayable runs on many seeds.
- **Team variant:** 2–4 agents in one multiplayer world.

## Files
- **Mod and library:** `mod/TerraBot/`, `terrariabench/tb/` (incl. `CONTRACT.md`, `path.py`).
- **Harness and tools:** `tools/terrabot/` (session/proxy, sandbox, run, agent, audit, live tests, pathfinder live
  checks, price probe, export, proof programs).
- **Tests:** `tests/test_tb_{path,sandbox,agent}.py`.
- **Records:** compact records in `experiments/results/programmatic-track-2026-11-10/`. Raw runs (game profiles,
  screenshots, `desktop.mp4` for the scripted and pilot runs) are in Omarchy `runs/terrabot-*`.
