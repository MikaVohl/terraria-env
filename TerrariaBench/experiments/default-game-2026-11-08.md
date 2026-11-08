# Default-game benchmark on official Terraria, real time vs paused, 2026-11-08

Question: on the **original, unmodified Terraria** (tModLoader 1.4.4.9 with only our read-only observer journal;
normal PvE with hostile damage on; small Classic worlds; default rules), with the simplest screen-based agent
interface (one `act` tool that returns a screenshot), how far do cheap models get in **20 game-minutes**, and how much
does the clock policy matter: **real time** (the game never pauses) vs **paused** (the game process is frozen while
each model response generates)?

Compact records: [`results/default-game-2026-11-08/`](results/default-game-2026-11-08/) (`summary-main.json`,
`results-table-main.md`, `summary-screening.json`, `results-table-screening.md`, `ledger.json`, `jobs/` = every
queued command + `queue.log`, `runs/<run>/` = manifest, result, extended score, clock log, evidence timeline,
contact sheet, clock check; `settings-probe/`; `parallel-probe-*.json`). Raw runs (frames, requests/responses,
telemetry, **`desktop.mp4`** of each run's isolated display) stay on Omarchy under
`~/Projects/TerrariaBench/runs/default-game-2026-11-08/<run>/`.

**Two worlds per cell, n = 1–2: signals, not rankings.** Several cells lost game time to two harness failures (fixed
mid-campaign, affected paused cells re-run) and to per-run dollar caps; every short run is marked.

## Headline

1. **Smart Cursor (a stock setting, now on in default-v1) is the first thing that got cheap single models to place a
   work bench within 20 minutes:** Haiku placed one in **both** real-time runs (9:41, 13:07), the combination
   Opus planner + Jev executor in both of its runs (5:20 real time, 3:07 paused). Luna and Terra never placed one
   (0/8). Nobody crafted a furnace; Luna (paused, w401, crashed run) crafted 15 torches.
2. **Real time vs paused is model-specific, not uniformly "paused is better":**
   - **Luna** (7–8 s latency) is the clear paused winner: 14 and 18 deaths in real time (published 3/4, extended
     2/1) vs 0–12 deaths paused (published 4/5/6, extended 6*/1/5; w402: wood_100 at 3:54, underground, ore, lens).
   - **Haiku** (3 s latency) is *better in real time* (extended 4 and 4 vs 1 and 1): paused, it narrates and stops
     (96 and 146 continuations; one paused run was ended at 4:15 by the five-tool-less-replies rule) and never
     placed its bench.
   - **Terra** goes deeper when paused (132 and 164 tiles, the cavern layer at 12:37) but scores about the same
     (published 3/5 vs 3/5, extended 2/5 vs 3/5).
   - **Opus + Jev**: same extended count (4 vs 4); paused got published 6 (bench placed 3:07, wooden armour 3:10,
     161 tiles deep) vs 5.
3. **Normal PvE is costly for slow real-time agents:** deaths per 20 min in real time — Luna 14/18, Terra 11/11,
   Opus+Jev 18, Haiku 0/16; paused runs of the same models 0–12.
4. **Published scores of 5–6 are again mostly possession/loot:** Luna paused w402 scored 6 (5 bars and 10 torches
   appear in the same second = a chest), Terra 5 (bars at 2:26–3:00, looted). The extended catalog with
   crafted/placed facts separates these; no cheap run crafted a bar or a furnace.
5. **Parallel instances work:** each game runs on its own rootful Xwayland server on its own headless output (XTEST
   input, X screenshots). Five concurrent games held **60.0 game updates/s (median, every run)** with isolated
   input; the 25 paid runs (screening + matrix; 11.7 h of summed run wall time) finished in 3 h 22 min (11:19–14:41
   Omarchy time).

## Method

**Profile `default-v1`** (`terrariabench run --profile default-v1 …`, `terrariabench.combo --profile default-v1 …`):

| | default-v1 |
|---|---|
| Game | tModLoader 1.4.4.9; only mod: TerrariaBenchObserver 0.7 (journal: heartbeats, checkpoints, crafted/placed events). Rules unchanged: `TERRARIABENCH_PVE=enabled`, `TERRARIABENCH_HOSTILE_DAMAGE=on`, checkpoint chat lines off. Starter items' random prefixes reset to none (as in every earlier profile). |
| Worlds | new unseen small Classic worlds generated with default settings by the dedicated server: **32000401** (crimson) and **32000402** (crimson) for the matrix, 32000403 (corruption) spare, **32000404** (crimson) for the settings screening only. Fresh copy per run. |
| Tool | one `act(actions)`: 1–16 primitives `{keys?, mouse?, x?, y?, ms?}` = key press, key hold (ms), mouse move, click/hold at screenshot pixels, wait (ms only). Returns a fresh JPEG (q85) screenshot and `game_time_played`. Schema: Appendix B. |
| System prompt | the goal (progress toward defeating the Wall of Flesh) + Terraria's default key bindings as plain facts; no strategy, recipes, macros, checkpoint tool or remaining time. **Identical in both clock modes** (it does not mention the clock). Appendix A. First user turn = the opening screenshot. |
| Context | all text and tool results until 120k tokens (then oldest turns dropped); newest 8–15 screenshots (dropped 8 at a time). |
| Continuation | a reply without a tool call gets "The run is still in progress. Continue playing."; 5 tool-less replies in a row end the run (unchanged from all earlier campaigns). Counted per run. |
| Budget | **1200 game seconds** = 72,000 game updates from the observer's `game_updates` (not wall time); actions stop between primitives once it is spent; scoring is cut at the budget. A wall-clock safety cap on unfrozen time (game + 600 s) never triggered. |
| Clock | `realtime`: game never pauses. `paused`: the game's process group is SIGSTOPped during every model call (both roles for the combination, which then runs planner and executor in turn) and SIGCONTed for the actions and the screenshot. |
| Display settings | frozen after the screening below: 1024×1024 window, zoom 100 %, UI scale 0.9, lighting Color, framed minimap (game defaults) and **Smart Cursor on** (stock toggle; one Left Ctrl press before the first screenshot). Recorded in every `manifest.json` → `display_settings`. |
| Scoring (offline, hidden) | published 13-checkpoint subset (terrariabench.com comparability) + extended catalog (19 facts: crafted/placed/looted, layers, ores, bars, furnace, anvil; `tools/extended_score.py`). |
| Models | Haiku 5.5 (thinking medium = 8k budget), GPT-5.6 Luna and Terra (`reasoning.effort: low`, Responses API), and the **combination Opus 5.5 (low) planner + Jev 1.14 executor** (planner: same goal + controls, does inventory/crafting with the same primitives; Jev picks catalog moves that are built from the same primitives, pixel offsets scaled to the window/zoom). |
| Game process | `DOTNET_PROCESSOR_COUNT=1` from 13:07 on (bug fix below; lighting runs on the calling thread, rules unchanged). |

Code: `terrariabench/reference_live.py` (profile, scripted dry-run provider, game clock, display settings),
`terrariabench/combo.py` (default-v1, paused sequential mode, settings), `terrariabench/linux_control.py`
(`XGameControl`, isolated launch), `prompts/default_v1.txt`, tools `clock_check.py`, `isolated_displays.py`,
`parallel_queue.py`, `dg_job.py`, `dg_finish.sh`, `parallel_probe.py`, `settings_probe.py`, `freeze_stress.py`;
`extended_score.py` (budget cut) and `campaign_table.py` (default-v1 columns).

## Unpaid validation

| Check | Result |
|---|---|
| `dryrun-paused-01` (scripted operator policy, 4 s simulated latency, 90 game-s, world 401) | stop `game_time_limit` at 91 game-s; 47 freezes, **0 heartbeats while frozen**; **60.0 updates/s** median while running (overall 60.7: a short catch-up after each thaw); input moved 70 tiles, dug, killed a slime (gel), took PvE damage; game-time screenshot age 0.03 s (wall 4.0 s); extended score: gel |
| `dryrun-realtime-01` (same, real time, world 402) | stop `game_time_limit` at 90 s; **60.0 updates/s** (p05 60.0); screenshot age 4.0 s |
| combination smoke (Haiku planner + Jev, 60 s paused / 45 s real time, world 404, $0.01) | paused: 31 freezes, 0 heartbeats while frozen, 60.0 updates/s; real time: wood 25 in 44 s, 60.0 updates/s |
| XTEST input on isolated displays | keys, absolute pointer motion (needs the root window given explicitly) and button holds verified: 33 wood chopped, dirt mined |

## Parallel instances (verdict: adopted, all runs used it)

Approach: one **headless Hyprland output + one rootful Xwayland server per game** (`tools/isolated_displays.py`); the
game is the only client of its server (SDL x11), input goes through that server's **XTEST**, screenshots are **X
GetImage** of that server, so instances share neither focus nor input; the headless output keeps the Xwayland window
visible at 60 Hz and is what each run's `desktop.mp4` records. No Steam or tModLoader multi-instance problems
(5 concurrent clients). No sudo, nothing installed except `python-xlib` in the venv.

| Unpaid probe (`tools/parallel_probe.py`, 1 s holds + screenshot loop) | Updates/s per instance (median / p05 / min) | Input isolation | Load |
|---|---|---|---|
| 1 instance, 45 s | 60.0 / 59.94 / 59.94 | walked +171 tiles | 1.0 |
| 4 instances, 120 s | 60.0 / ≥59.88 / ≥58.1 (overall 59.96–60.0) | even instances walked right (+92, +98), odd left (−297, −335) | 7/8 cores |
| 4 instances + 4 recorders (10 fps), 90 s | 60.0 / ≥59.7 / ≥55.6 (overall 59.91–59.98) | +251/+137 right, −145/−151 left | 12–15 |

Campaign: 4 isolated 1024×1024 slots + one 1280×720 slot, recorders at 5 fps, real-time and paused runs mixed.
**Every run's median was 60.0 updates/s** (unfrozen heartbeat intervals); overall updates per running second
58.6–61.5 (real time 58.6–60.0, paused 60.2–61.5 = post-thaw catch-up). Real-time runs were not measurably
disadvantaged, so real-time and paused runs both ran in parallel.

## Harness failures found and fixed (affected cells re-run)

1. **Paused-clock crash.** tModLoader's multi-threaded lighting (`FastParallel.For`) measures its worker countdown
   with a wall-clock stopwatch; a SIGSTOP landing inside it makes the game throw "Fatal Deadlock in FastParallelFor"
   after the thaw (3 paused runs, all underground: `s1-terra-base` at 2:35, `m04-luna-pa-w401` at 11:04,
   `m06-terra-pa-w401` at 14:13). A blind stress test (4000 random freezes on the surface) did not reproduce it.
   Fix: launch the game with `DOTNET_PROCESSOR_COUNT=1` (tML logs "CPU: 1 processors"; lighting ranges run on the
   calling thread; game rules unchanged). No crash in the 9 runs after the fix; the three cells were re-run
   (`s9-…`, `m09-…-rerun`, `m10-…-rerun`). The crashed runs stay in the tables, marked.
2. **Lost result on a re-entered world.** Terra (`m15-terra-rt-w402`) used the game's own *Save & Exit* at 16:04 and
   clicked back into the world, which crashed tModLoader (`WorldMap.Load` NullReferenceException); the harness then
   raised while stopping the changed process and wrote no `result.json`. Fixed (`termination.json` records the error);
   that run's result was reconstructed offline from its accounting, telemetry and logs (`recovered_offline: true`).
3. **Combination thread safety on X**: the planner thread and the executor shared one python-xlib connection
   (deadlock in the first smoke). `XGameControl` now serialises Xlib use; found before any paid combination run.
4. **XTEST motion**: without an explicit root window, absolute motion did not reach SDL (settings probe v1); fixed and
   re-captured before any model saw a screenshot.

## Display-settings study (before freezing default-v1)

Stock options only. **Static perception probe** (`tools/settings_probe.py`, unpaid capture on world 404, $0.05 of
questions): for 9 variants (base; zoom 150 %; Smart Cursor on; lighting White / Retro; minimap off / overlay;
UI scale 1.25; 1280×720 window) the same operator path gave 4 viewpoints × 2 screenshots, ground truth from the
observer's privileged state snapshot (probe only). Zoom 75 % is not offered by the game at a 1024-px window (the
image is identical to 100 %). Results (Haiku / Luna, correct of 4 each): nearest-tree location 3–4 / 2–3 in every
variant, axe hotbar slot 4/4 everywhere (Luna 3/4 at UI 1.25), object under the cursor 1–2 / 1–2 everywhere. **No
setting separated perception**; so the decision went to a paid screening.

**Paused screening** (world 404, 10 game-min each, one setting changed at a time):

| Run | Setting | Pub. | Ext. | Highlights | Deaths | Depth | Contin. | Calls | USD |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|
| s1-haiku-base | base | 4 | 1 | bench crafted 0:34 | 0 | 1 | 97 | 324 | 0.47 |
| s2-haiku-smart | **Smart Cursor on** | 4 | **2** | iron/lead ore 5:36; stopped at 9:00 (5 tool-less replies) | 1 | 22 | 83 | 269 | 0.35 |
| s3-haiku-zoom150 | zoom 150 % | 4 | 1 | – | 0 | 3 | 68 | 234 | 0.32 |
| s4-haiku-wide | 1280×720 | 4 | 1 | – | 1 | 12 | 56 | 236 | 0.30 |
| s5-haiku-ui125 | UI 1.25 | 4 | 1 | – | 1 | 5 | 108 | 387 | 0.61 |
| s1-terra-base | base | 2 | 1 | *crashed at 2:35 (bug 1)* | 1 | 33 | 0 | 26 | 0.17 |
| s9-terra-base-rerun | base | 1 | 2 | copper ore 7:49, wood only at 9:20 | 2 | 42 | 1 | 102 | 1.10 |
| s2-terra-smart | **Smart Cursor on** | 3 | **5** | **torches crafted 5:50**, underground 3:58, copper + iron ore | 2 | 93 | 1 | 91 | 0.91 |
| s3-terra-zoom150 | zoom 150 % | 4 | 1 | 3 benches crafted, none placed | 3 | 17 | 1 | 103 | 0.99 |

Decision: **Smart Cursor on** (the only setting that moved both models: extended 1 → 2 for Haiku, 2 → 5 for Terra;
it is a stock toggle that a human player would normally use); every other setting stays at the game default
(no gain for zoom 150 %, 16:9, UI 1.25; lighting and minimap not separable in the static probe). n = 1 per cell.

## Results (main matrix, 20 game-min, default-v1 frozen)

Pub. = published-subset score (possession-based). Ext. = extended catalog facts (of 19). Times are game mm:ss.
Latency = median model latency (combination: planner / Jev). Shot age = median age of the newest screenshot when an
action batch starts, wall / game seconds. Wall = run wall time. Hz = median game updates/s while running.

| Run | Setup | World | Game min | Pub. | Ext. | Highlights | Bench placed | Furnace | Deaths | Depth | Contin. | Calls | Latency (s) | Shot age wall / game (s) | Wall min | Hz | USD |
|---|---|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| m01-haiku-rt-w401 | Haiku, real time | 401 | 20.0 | 5 | 4 | wood_100 1:40, copper 6:13, underground 8:54 | **9:41** | – | 0 | 65 | 34 | 197 | 3.1 | 3.3 / 3.3 | 20.0 | 60.0 | 0.23 |
| m11-haiku-rt-w402 | Haiku, real time | 402 | 20.0 | 4 | 4 | underground 4:09, lens 14:55 | **13:07** | – | 16 | 81 | 31 | 204 | 2.6 | 2.9 / 2.9 | 20.0 | 60.0 | 0.23 |
| m02-haiku-pa-w401 | Haiku, paused | 401 | **4.3** (5 tool-less replies) | 4 | 1 | copper 1:27, bench crafted 3:31 | – | – | 0 | 32 | 96 | 276 | 3.1 | 5.4 / 0.06 | 19.4 | 60.0 | 0.36 |
| m12-haiku-pa-w402 | Haiku, paused | 402 | 20.0 | 4 | 1 | 2 benches crafted | – | – | 10 | 26 | 146 | 507 | 2.9 | 3.8 / 0.04 | 48.2 | 60.0 | 0.87 |
| m03-luna-rt-w401 | Luna, real time | 401 | 20.0 | 3 | 2 | wood only at 8:13 | – | – | 14 | 24 | 2 | 92 | 7.3 | 7.4 / 7.4 | 20.5 | 60.0 | 0.09 |
| m13-luna-rt-w402 | Luna, real time | 402 | 20.0 | 4 | 1 | bench crafted 9:30 | – | – | 18 | 2 | 5 | 105 | 7.0 | 7.1 / 7.1 | 20.1 | 60.0 | 0.10 |
| m04-luna-pa-w401 | Luna, paused | 401 | *11.1 (crash, bug 1)* | 4 | 6 | **15 torches crafted 9:12**, underground 4:40, silver/gold-tier + iron ore | – | – | 0 | 63 | 1 | 136 | 7.0 | 7.1 / 0.06 | 27.7 | 60.0 | 0.14 |
| m09-luna-pa-w401-rerun | Luna, paused | 401 | 20.0 | 5 | 1 | wood_100 18:27, bench crafted 14:40 | – | – | 8 | 28 | 1 | 249 | 7.7 | 7.8 / 0.06 | 54.1 | 60.0 | 0.36 |
| m14-luna-pa-w402 | Luna, paused | 402 | 20.0 | 6 | 5 | wood_100 3:54, underground 7:09, 5 bars + 10 torches 9:31 (chest), lens, 13 torches placed | – | – | 12 | 69 | 1 | 256 | 7.8 | 7.9 / 0.06 | 55.6 | 60.0 | 0.35 |
| m05-terra-rt-w401 | Terra, real time | 401 | **19.4** ($ cap) | 3 | 2 | wood only at 9:57, underground 12:41 | – | – | 11 | 45 | 6 | 127 | 7.0 | 7.1 / 7.1 | 19.5 | 60.0 | 1.35 |
| m15-terra-rt-w402 | Terra, real time | 402 | **16.1** (Save & Exit, bug 2) | 5 | 5 | 5 bars 3:00 (looted), underground 3:10, copper, lens | – | – | 11 | 58 | 2 | 93 | 6.7 | 6.7 / 6.7 | 16.3 | 60.0 | 0.89 |
| m06-terra-pa-w401 | Terra, paused | 401 | *14.2 (crash, bug 1)* | 3 | 3 | iron ore 4:01, underground 4:24 | – | – | 3 | 93 | 1 | 148 | 7.3 | 7.3 / 0.06 | 33.2 | 60.0 | 1.80 |
| m10-terra-pa-w401-rerun | Terra, paused | 401 | 20.0 | 3 | 3 | copper 9:54, underground 10:04 | – | – | 9 | 132 | 14 | 191 | 7.3 | 7.5 / 0.06 | 44.8 | 60.0 | 2.59 |
| m16-terra-pa-w402 | Terra, paused | 402 | **17.1** ($ cap) | 5 | 5 | 5 bars 2:26 (looted), underground 1:40, **cavern 12:37**, wood_100 7:59 | – | – | 4 | 164 | 13 | 205 | 7.3 | 7.5 / 0.06 | 43.8 | 60.0 | 2.79 |
| m07-combo-rt-w401 | Opus (low) planner + Jev, real time | 401 | 20.0 | 5 | 4 | wood_100 4:57, underground 7:51 | **5:20** | – | 18 | 62 | – | 61 + 807 | 4.4 / 0.28 | 0.36 / 0.36 | 20.0 | 60.0 | 1.20 + 0.13 |
| m08-combo-pa-w401 | Opus (low) planner + Jev, paused | 401 | **18.3** ($ cap) | 6 | 4 | wood_100 2:51, **wooden armour 3:10**, underground 7:50, 10 torches 13:54 | **3:07** | – | 11 | 161 | – | 79 + 934 | 4.4 / 0.29 | 0.41 / 0.02 | 29.0 | 60.0 | 1.52 + 0.15 |

Full table with every milestone column: [`results-table-main.md`](results/default-game-2026-11-08/results-table-main.md).
Furnaces: none crafted or placed in any run. `$ cap` = the run's own dollar ceiling (reserved output tokens per call
included) stopped it before 20 game-minutes; those cells have less game time than planned.

### Per model × mode (complete runs and partial runs together; crashed runs in brackets)

| Model | Mode | Runs | Game min | Pub. | Ext. | Bench placed | Deaths | Depth | Contin. / run | Calls / 20 min | Latency | USD / run |
|---|---|---:|---|---|---|---|---|---|---|---|---|---|
| Haiku | real time | 2 | 20, 20 | 5, 4 | 4, 4 | **2/2** | 0, 16 | 65, 81 | 31–34 | ~200 | 2.6–3.1 s | 0.23 |
| Haiku | paused | 2 | 4.3, 20 | 4, 4 | 1, 1 | 0/2 | 0, 10 | 32, 26 | 96–146 | ~510 | 2.9–3.1 s | 0.36–0.87 |
| Luna | real time | 2 | 20, 20 | 3, 4 | 2, 1 | 0/2 | 14, 18 | 24, 2 | 2–5 | ~100 | 7.0–7.3 s | 0.09–0.10 |
| Luna | paused | 2 (+1) | 20, 20 [11.1] | 5, 6 [4] | 1, 5 [6] | 0/3 | 8, 12 [0] | 28, 69 [63] | 1 | ~250 | 7.7–7.8 s | 0.35 [0.14] |
| Terra | real time | 2 | 19.4, 16.1 | 3, 5 | 2, 5 | 0/2 | 11, 11 | 45, 58 | 2–6 | ~130 | 6.7–7.0 s | 0.89–1.35 |
| Terra | paused | 2 (+1) | 20, 17.1 [14.2] | 3, 5 [3] | 3, 5 [3] | 0/3 | 9, 4 [3] | 132, 164 [93] | 13–14 | ~200 | 7.3 s | 2.59–2.79 [1.80] |
| Opus + Jev | real time | 1 | 20 | 5 | 4 | 1/1 (5:20) | 18 | 62 | – | 61 planner + 807 Jev | 4.4 / 0.28 s | 1.33 |
| Opus + Jev | paused | 1 | 18.3 | 6 | 4 | 1/1 (3:07) | 11 | 161 | – | 79 + 934 | 4.4 / 0.29 s | 1.66 |

### Real time vs paused, per model

- **Haiku:** real time wins. Both real-time runs placed a bench and went underground (extended 4, 4); paused runs
  crafted benches but never placed them, explored less (26–32 tiles) and replied without a tool call 96–146 times
  (one run ended at 4:15 by the 5-in-a-row rule). In paused mode those replies cost no game time, so Haiku's
  "report and stop" habit dominates; in real time the game moves on and Haiku keeps acting.
- **Luna:** paused wins. In real time it dies 14–18 times and barely gathers wood (wood at 8:13 / bench at 9:30); paused
  it holds wood 25 within ~1 min on w402, reaches the underground layer and (crashed run) crafted 15 torches.
- **Terra:** paused goes deeper (132/164 tiles vs 45/58; the only cavern-layer entry) with fewer deaths, scores about the
  same; costs 2–3× more per game minute because it makes more calls.
- **Opus + Jev:** the fast Jev executor (0.28 s, screenshot age 0.36 s) makes real time workable; paused gave earlier
  bench/armour and more depth. Both placed the bench within ~5 minutes.
- Wall time: paused runs took 2.2–2.8× their game time for GPT models (7 s latency) and 2.4× for Haiku; real time 1×.

### Comparison with terrariabench.com and our earlier campaigns

| Source | Profile / length | Best published-catalog score | Placed bench? |
|---|---|---:|---|
| terrariabench.com (7 published runs, 8 h budgets) | PvE off, api harness | 4 (Gemini 3 Flash) | – |
| LLM campaign 2026-11-08 morning (camp-v2: hostile damage **off**, interface card, checkpoint tool) | 15 min | 7 (Opus); cheap 5 | Opus 2/2; cheap models 0/17 in 15 min |
| **This campaign, default-v1 (unmodified game, normal PvE, minimal prompt)** | 20 game-min | **6** (Luna paused w402; Opus+Jev paused) | **Haiku 2/2 real time, Opus+Jev 2/2**; Luna/Terra 0/8 |

On the unmodified game with only the controls in the prompt, the cheap models reach the published 4–6 range in
20 game-minutes — above the best published 8-hour run — but again largely through loot (bars/torches from chests).
Compared with the morning's camp-v2 profile, **Smart Cursor + default-v1 turned Haiku's placement wall (0/6) into
2/2 placements in real time**, while normal PvE added many deaths for the slow GPT models in real time.

### Per-run insights (written after each run)

- **s1–s5 Haiku screening:** benches crafted within 12–50 s in every variant, never placed in 10 paused minutes;
  56–108 continuations per run; Smart Cursor gave the only extra fact (iron ore). UI 1.25 cost the most ($0.61, 387 calls).
- **s2-terra-smart:** crafted torches from its own gel at 5:50 and went 93 tiles down; best screening run. s3 (zoom 150 %)
  crafted three benches but stayed on the surface. s1 crashed (bug 1); its rerun s9 cut its first wood at 9:20.
- **m01-haiku-rt-w401:** wood 100 at 1:40, copper ore 6:13, underground 8:54 and the first cheap-model **bench placement
  in 10 minutes (9:41)** plus a wooden table; 0 deaths, $0.23.
- **m02-haiku-pa-w401:** bench crafted 3:31 and two platforms, then a streak of "summary" replies; the 5-in-a-row rule
  ended it at 4:15 game time (96 continuations in 276 calls).
- **m03-luna-rt-w401:** 14 deaths in normal PvE, first wood only at 8:13; 7.3 s latency means ~7 s of game per screenshot.
- **m04-luna-pa-w401 (crashed 11:04):** the best Luna play: copper 1:21, silver/gold-tier ore 3:53, underground 4:40,
  **15 torches crafted 9:12** and placed; crash = bug 1.
- **m05-terra-rt-w401:** explored and fought (11 deaths), wood only at 9:57, underground 12:41; dollar cap at 19:26.
- **m06-terra-pa-w401 (crashed 14:13):** iron ore and underground in ~4 min, 93 tiles; crash = bug 1.
- **m07-combo-rt-w401:** Jev chops fast (wood 25 at 0:10, wood 100 4:57); Opus crafted and **placed a bench (5:20)**,
  table and door; 18 deaths; $1.20 planner + $0.13 Jev.
- **m08-combo-pa-w401:** bench placed 3:07, wooden breastplate + greaves 3:10, 161 tiles deep; published 6; planner cap
  stopped it at 18:17.
- **m09-luna-pa-w401-rerun:** slow wood (wood 10 at 6:45) but wood 100 by 18:27, bench crafted 14:40, not placed.
- **m10-terra-pa-w401-rerun:** surface-first, then a 132-tile dig after 10:00; 14 continuations; $2.59.
- **m11-haiku-rt-w402:** underground 4:09, **bench placed 13:07**, a lens; 16 deaths after nightfall.
- **m12-haiku-pa-w402:** 146 continuations in 507 calls, two benches crafted, never placed; 48 wall-minutes.
- **m13-luna-rt-w402:** 18 deaths, stayed at the surface (2 tiles), bench crafted 9:30.
- **m14-luna-pa-w402:** wood 100 at 3:54, underground 7:09, chest loot (5 bars + 10 torches at 9:31), lens, 13 torches
  placed; published 6 / extended 5.
- **m15-terra-rt-w402:** looted 5 bars at 3:00, underground 3:10, then opened the menu and **Save & Exit**-ed at 16:04;
  re-entering crashed the game (bug 2).
- **m16-terra-pa-w402:** fastest descent of the campaign: underground 1:40, looted bars 2:26, **cavern layer 12:37**,
  164 tiles; dollar cap at 17:08.

## Spend

Ledger: [`ledger.json`](results/default-game-2026-11-08/ledger.json) (per run from each run's accounting; GPT
cost = gateway `X-Token-Usage-Cost`, Claude at list price; uncertain = failed sent attempts).

| Route | Cap | Reported | Uncertain | Conservative |
|---|---:|---:|---:|---:|
| AMD gateway (Anthropic + Unified), incl. $0.05 perception probe and $0.01 smokes | $25.00 | **$20.11** | $0.03 | **$20.14** |
| OpenRouter (Jev) | $1.00 | **$0.29** | $0 | **$0.29** |

Of the gateway spend: settings screening $5.20 (incl. one crashed run), main matrix $14.85 (incl. $1.95 in the two
crashed paused runs), perception probe $0.05, combination smokes < $0.01. The queue refused to
start any job whose cap, plus all running caps, plus spend would exceed the budget.

## Recommended protocol

1. **default-v1 as the main track**: unmodified game, normal PvE, one `act` tool, goal + default key bindings, Smart
   Cursor on, hidden scoring, 20 game-minutes counted in game updates, both catalogs reported (rank on the extended one;
   treat bars/torches by possession as loot-sensitive).
2. **Run both clocks for every model** and report them side by side: the best clock differs by model (Luna/Terra
   paused, Haiku real time). Report latency, screenshot age (wall and game), continuations and deaths with each score.
3. **Paused clock needs `DOTNET_PROCESSOR_COUNT=1`** (or a pause point inside the game loop); whole-process freezes can
   crash tModLoader's parallel lighting otherwise.
4. **Isolated parallel displays** (rootful Xwayland per game, XTEST input) with ≤5 concurrent games on this 8-core host;
   check every run's clock (`tools/clock_check.py`: median 60.0 here).
5. Per-run dollar caps must cover 20 game-minutes plus one per-call reservation (Terra $0.46, Opus planner $1.05):
   Terra paused cap ≈ $3.8 (spend ≈ $3.3), Opus planner cap ≈ $3 (spend ≈ $1.7), Haiku paused ≈ $1.2, Luna ≈ $0.6; budget ≈ $25 for 2 worlds × 2 clocks × {Haiku, Luna, Terra} + one combination
   per clock, with screening.
6. Next: ≥3 worlds per cell (world spread is as large as the clock effect), and a paused-mode continuation policy that
   does not let tool-less replies end a run early (Haiku).

## Limitations

- n = 1–2 per cell, two worlds; three cells lost time (two crashes before the fix, three dollar caps, one agent
  Save & Exit). Real-time runs 01–07 ran before `DOTNET_PROCESSOR_COUNT=1` (lighting threading only; no effect on rules
  or measured 60 Hz).
- Smart Cursor was chosen from n = 1 screening runs per setting (both models moved in the same direction).
- Game date not pinned; normal PvE makes night dangerous, so deaths depend on how fast the 20 minutes reach nightfall.
- GPT models via the Responses API (reasoning effort low) vs Claude adaptive/budgeted thinking — provider-side
  reasoning differs.

## Appendix A: system prompt (default-v1, identical in both clock modes)

```text
You are playing Terraria on a fresh character in a fresh small Classic world. The game is unmodified: enemies,
damage, day and night follow the normal game rules. Your goal is to progress as far as possible toward defeating the
Wall of Flesh. Keep playing until the run ends.

You see the game through 1024x1024 screenshots and control it with the act tool, which sends ordinary keyboard and
mouse input to the game window and then returns a new screenshot and the game time played so far.

Controls (Terraria's default key bindings):
- A / D: move left / right. W: move up (climb ropes). S: move down (drop through platforms).
- Space: jump (hold longer to jump higher).
- Left mouse button: use the selected item at the mouse cursor (swing, mine, chop, place).
- Right mouse button: interact (open doors and chests, talk to townspeople, equip items from the inventory).
- 1-9 and 0: select hotbar slots 1-10.
- Escape: open / close the inventory (including the crafting menu).
- Left Ctrl: toggle Smart Cursor. Left Shift (hold): auto select.
- H: quick heal. J: quick mana. B: quick buff. E: grapple. R: quick mount. T: throw the selected item.
- M: full-screen map. Tab: change the minimap style.
```

First user turn: `Current game screenshot:` + the opening screenshot. Continuation message: `The run is still in progress. Continue playing.`.

## Appendix B: tool schema

```json
[
 {
  "type": "function",
  "function": {
   "name": "act",
   "description": "Send keyboard and mouse input to the game, then return a new screenshot and the game time played. The actions run in order. Each action optionally moves the mouse to (x, y) in screenshot pixels (x 0-1023, y 0-1023), then presses and holds the listed keys and/or the mouse button for ms milliseconds (20-2000, default 100) and releases everything. Examples: key press {\"keys\": [\"3\"], \"ms\": 50}; key hold {\"keys\": [\"d\"], \"ms\": 1500}; mouse move {\"x\": 600, \"y\": 400}; click or hold at a point {\"x\": 600, \"y\": 400, \"mouse\": \"left\", \"ms\": 800}; wait {\"ms\": 1000}.",
   "parameters": {
    "type": "object",
    "additionalProperties": false,
    "required": [
     "actions"
    ],
    "properties": {
     "actions": {
      "type": "array",
      "minItems": 1,
      "maxItems": 16,
      "items": {
       "type": "object",
       "additionalProperties": false,
       "properties": {
        "keys": {
         "type": "array",
         "items": {
          "type": "string",
          "enum": [
           "a",
           "b",
           "c",
           "d",
           "e",
           "f",
           "g",
           "h",
           "i",
           "j",
           "k",
           "l",
           "m",
           "n",
           "o",
           "p",
           "q",
           "r",
           "s",
           "t",
           "u",
           "v",
           "w",
           "x",
           "y",
           "z",
           "0",
           "1",
           "2",
           "3",
           "4",
           "5",
           "6",
           "7",
           "8",
           "9",
           "space",
           "esc",
           "enter",
           "backspace",
           "tab",
           "leftshift",
           "leftctrl",
           "up",
           "down",
           "left",
           "right",
           "minus"
          ]
         }
        },
        "mouse": {
         "type": "string",
         "enum": [
          "left",
          "right",
          "middle"
         ]
        },
        "x": {
         "type": "integer",
         "minimum": 0,
         "maximum": 1023
        },
        "y": {
         "type": "integer",
         "minimum": 0,
         "maximum": 1023
        },
        "ms": {
         "type": "integer",
         "minimum": 20,
         "maximum": 2000
        }
       }
      }
     }
    }
   }
  }
 }
]
```

Act result (tool message): `{"dispatched_commands": n, "game_time_played": "m:ss", "image_follows": true}` followed by the new screenshot (JPEG q85, 1024×1024).

## Appendix C: combination planner system prompt

```text
You are the PLANNER of a two-part agent playing Terraria. A fast EXECUTOR acts every few seconds from the newest screenshot and pursues the objective you give it with movement, jumping, mining, chopping, attacking and placing blocks. It cannot open menus or craft: you do inventory and crafting yourself with ui_actions (keyboard and mouse actions, executed while the executor pauses).

You are playing Terraria on a fresh character in a fresh small Classic world. The game is unmodified: enemies,
damage, day and night follow the normal game rules. Your goal is to progress as far as possible toward defeating the
Wall of Flesh. Keep playing until the run ends.

Controls (Terraria's default key bindings):
- A / D: move left / right. W: move up (climb ropes). S: move down (drop through platforms).
- Space: jump (hold longer to jump higher).
- Left mouse button: use the selected item at the mouse cursor (swing, mine, chop, place).
- Right mouse button: interact (open doors and chests, talk to townspeople, equip items from the inventory).
- 1-9 and 0: select hotbar slots 1-10.
- Escape: open / close the inventory (including the crafting menu).
- Left Ctrl: toggle Smart Cursor. Left Shift (hold): auto select.
- H: quick heal. J: quick mana. B: quick buff. E: grapple. R: quick mount. T: throw the selected item.
- M: full-screen map. Tab: change the minimap style.

Screenshots are 1024x1024 pixels. Reply with one JSON object only: {"objective": concrete instruction for the executor (max 300 chars), "replan_seconds": 10-60 (game seconds until you look again), "notes": your memory for next time (max 1500 chars), "ui_actions": optional list of 1-16 actions {"keys":[...],"mouse":"left|right","x":0-1023,"y":0-1023,"ms":20-2000}; each action moves the mouse to (x, y) if given, then holds the keys and/or mouse button for ms milliseconds and releases them}. After your ui_actions run you immediately get a new screenshot and can keep clicking; the executor stays paused until you reply without ui_actions.
```

Planner user turn: JSON with `task` (the goal paragraph), `your_notes`, `current_objective`, `executor_recent_actions`, `game_time_played`, plus the newest two screenshots. Jev executor: OpenRouter Decisions (tree side, hostile side, inventory open, objective done, action choice from a catalog of walk/jump/chop/attack/dig/toggle-inventory moves built from the same primitives), one screenshot per decision.

