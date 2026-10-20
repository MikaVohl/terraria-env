# Pilot 30-minute runs: per-run assessments

One reviewer's (the harness author's) judgement of each run, written from the evidence pack
(`evidence/timeline.md`, `summary.json`, `contact-sheet.png`), the frames the model saw and the
desktop recording. The scores are subjective by design. They complement the milestone score; they do not replace it.

Harness caveats (details in `harness-notes.md`): the three frozen-clock runs were intermittently shown a desktop
"Application Not Responding" dialog over the game (note 7), and combo-v1 planners could not open the inventory because
of a key-name bug (note 8). All runs played during the Halloween season (note 1). Milestone times are game time;
other times quoted for frozen runs come from their timelines and are wall time (including thinking pauses).

## Scale (0-10)

Anchors are progress within the 30-minute window. Play quality moves a score by up to ±1 from its anchor.

| Score | Anchor |
|---:|---|
| 0 | No meaningful progress: no wood, or the controls never worked |
| 2 | Wood gathered |
| 3 | Workbench crafted and used |
| 4 | Workbench plus a deliberate next step (armour, a shaft, gel collection) |
| 5 | Torches crafted (needs gel, so it means surviving and fighting slimes) |
| 6 | Furnace crafted, or ore mined with light underground |
| 7 | Bars smelted |
| 8 | Ore tools, weapons or armour crafted |
| 9 | Several of: anvil, life crystal, ore armour, a safe base |
| 10 | Ready for or fighting a boss (for example the Eye of Cthulhu) |

Play quality covers: does the model read the screen correctly, correct its own errors, use time well, and avoid
dying or quitting?

---

## opus-rt-01: Opus 5.5 (reasoning low), real time, PvE on, interface card. **6/10**

Played 24.0 of 30 minutes; the $8 cap ended the run (about $0.30 per minute).
Milestone score 6: wood ×3 at 50 s, workbench 2:23, torch_10 14:52, furnace 21:40. 2 deaths, deepest 203 tiles,
5 continuation prompts (it said "I'm stopping here" at 6:00, 18:27 and 23:15).

**What went well**
- Wood in the first minute, then a planned build: workbench, wooden breastplate and greaves, equipped by 3 minutes.
- Worked out on its own that the character is two tiles wide and dug a 2-wide shaft (at 7:30). It then dug 200 tiles
  in about 6 minutes, collected stone, clay and copper.
- Identified gel and crafted torches (its own reasoning, 14 min), used them to light a cave and mined a copper vein (27 ore).
- Placed a second workbench underground and crafted a furnace from stone, wood and torches, so the recipe chain was right.

**What went wrong**
- Both deaths were from slimes while it was crafting or digging at the surface (2:02 and 6:55). It identified a slime
  as "hostile bunny" and said "something invisible must be hurting me", which is the latency problem: the slime that hit
  it was not in the screenshot it had acted on.
- About 3.5 minutes (3:15-6:40) spent failing to start the shaft before the 2-wide insight. It blamed "game running
  sluggishly" and "pickaxe swings slowed down", wrong explanations it never tested.
- Inventory/UI handling cost about 5 of the last 8 minutes: it repeatedly confused which item was held, toggled the
  inventory with Escape at the wrong moment, and could not tell a placement preview from a placed furnace. The last
  heartbeat still lists the furnace in the inventory, so it was never placed and no bars were smelted.
- Quit three times and needed a continuation prompt each time.

**Judgement.** Correct, purposeful early-game plan executed end to end up to the furnace, the first run to clear
the torch barrier. Held back by latency-blind combat and UI state confusion, not by lack of game knowledge.
Anchor 6 (furnace), no adjustment: the strong plan and self-discovered 2-wide shaft balance the deaths, quitting and
UI churn.

---

## opus-frozen-01: Opus 5.5 (reasoning low), frozen clock, PvE on, interface card. **4/10**

Played 28.1 game-minutes (plus 20.3 minutes paused while thinking); the $15 cap ended it. Milestone score 4 (game time): wood ×3 at 0:14,
workbench 0:29. 20 deaths, deepest 340 tiles, 7 continuation prompts. Cost $14.14, twice the real-time run for similar game time.

**What went well**
- Fastest start of any run: 25 wood in 14 game-seconds, workbench at 29 game-seconds, wood armour soon after.
- Crafted 6 torches at 9 minutes, earlier than the real-time run. That is below the `torch_10` threshold, so the milestone
  score misses it. Dug a 2-wide shaft to 340 tiles by 24 minutes, collecting 12 copper and 7 lead ore.
- Correctly diagnosed the Graveyard biome (tombstones from its own deaths) and walked out of it.

**What went wrong**
- Never lit the shaft (it decided torches "need an adjacent wall" after one failed placement) and dug blind, so it missed ore.
- Drowned in a flooded cave at 340 tiles, then respawned at the surface at night. Zombies and an Eater of Souls killed it
  repeatedly; its attempts to wall itself in failed, and it chose to "wait out the night through repeated deaths since they're cheap".
  The tombstones from those deaths created a Graveyard biome at spawn, which kept spawning zombies after daybreak:
  15 deaths in 9 wall-minutes. Two more deaths were from falling down its own shaft.
- Blamed "lag" for missed clicks although the game was paused while it thought; the misses were placement and targeting errors.
- Quit 7 times. The last 8 minutes were spent re-chopping wood and re-crafting armour lost to deaths.

**Judgement.** The first 20 minutes were better than the real-time run (faster crafting, deeper digging). The run was
then lost to one bad position at nightfall and a passive response to it. Freezing the clock did not help survival:
the deaths were strategic (night at the surface, drowning, falls), not reaction-time failures. Anchor 5 (torches), −1 for
the death spiral and passive "die until morning" plan.

---

## sonnet-rt-01: Sonnet 5.5 (reasoning low), real time, PvE on, interface card. **2/10**

Played the full 30 minutes, $5.28. Milestone score 5: wood ×3 at 24 s, workbench 0:48, torch_10 at 13:00.
**34 deaths, never below the surface (deepest 1 tile), 101 continuation prompts.**

**What went well**
- Fast opening: 29 wood within 20 s from one 3×2 s chop sequence on an adjacent trunk, workbench crafted and placed in under a minute.
- Accurate self-reports. Each death, coin loss and health level it reported matched telemetry.

**What went wrong**
- **It quit 101 times.** From the second call onward almost every turn ended in a "I'm stopping here" report, so a
  continuation prompt was needed every ~18 s. Each one took one or two actions before the next report. It spent most of the
  run writing status reports instead of playing.
- **It never learned to dig.** It concluded "the pickaxe only removes the surface layer" and repeated that for 20 minutes,
  without ever widening the hole or trying a 2-wide shaft (the insight Opus found at 7 minutes).
- **It died at night on the surface 30+ times** to slimes, zombies and an Eater of Souls, with 1-hit-to-death health
  most of the time. It never retreated, built shelter or dug in. Graveyard formed at spawn from its tombstones.
- `torch_10` did not come from crafting. Telemetry shows the torches arrived in two pickups while walking (0→9→29), with gel
  unchanged at 22 and no crafting call: drops from Torch Zombies (5-20 torches each). The milestone is real by the published
  definition (possession), but it is not evidence of the gel→torch chain.

**Judgement.** Strong first minute, then no progress for 29 minutes. The failure is persistence and problem-solving,
not control or latency: it diagnosed its problems in words, kept giving up, and never tried a new approach. The milestone score
(5) overrates this run; it is the clearest example of why possession milestones need a crafting check.
Anchor 3 (workbench), −1 for constant quitting and the passive death spiral.

---

## haiku-rt-01: Haiku 5.5 (reasoning medium), real time, PvE on, interface card. **2/10**

Played the full 30 minutes for $0.50 (0.07 of Opus' cost per minute). Milestone score 5: wood ×3 at 24 s,
workbench 0:45, torch_10 12:02. **43 deaths, never below the surface, 63 continuation prompts.**

**What went well**
- The fastest opening in the pilot: an adjacent trunk chopped with two 2 s holds (33 wood by 24 s), workbench crafted at 45 s.
- Mined 9 gold ore from a surface vein next to spawn in its second minute.
- Cheapest run by far, at 3.1 s median latency, with a fresher view (3.4 s screenshot age) than Opus or Sonnet.

**What went wrong**
- The workbench stayed in the inventory for the whole run, so nothing was ever crafted at it. The gold ore was never used.
- After the opening it had no plan. It tried to mine at the surface, wandered, and wrote "I'm stopping here" reports
  every ~30 s from minute 3 onward.
- From nightfall (about 12 minutes) it died at spawn every ~25 s: 39 deaths in 18 minutes, without ever moving
  away from spawn, building cover or digging in. In its own words: "I can't reliably tell which nearby figures are friendly and which are hostile."
- `torch_10` came from a Torch Zombie drop at night (20 torches, gel unchanged), not from crafting, as in sonnet-rt-01.

**Judgement.** Real-time control is good enough to gather and craft quickly, but Haiku has no early-game plan
beyond the workbench and no survival response to night. The milestone score (5) badly overrates it.
Anchor 2-3 (workbench crafted but never placed or used); 2 because the last 18 minutes were a passive death loop.

---

## sonnet-frozen-01: Sonnet 5.5 (reasoning low), frozen clock, PvE on, interface card. **4/10**

Played 29.9 game-minutes (plus 28.7 minutes paused while thinking), $8.96. Milestone score 4 (game time): wood ×3 at 0:16,
workbench 0:18. 13 deaths, deepest 125 tiles, 72 continuation prompts.

**What went well**
- Placed the workbench and **crafted torches from gel at 9.5 minutes** (its own crafting call; wood and gel both dropped).
  Real-time Sonnet never crafted anything after the workbench.
- After ~7 minutes of failing to dig, it worked out the 2-tile-wide shaft and dug to 125 tiles, collecting stone,
  clay and 7 copper ore.
- Picked up 28 pumpkins (Halloween season, see harness notes).

**What went wrong**
- ~7 minutes lost to the same digging misconception as real-time Sonnet ("the pickaxe only removes the surface layer"),
  before discovering the fix on its own.
- Never placed a torch underground ("ores should pick up automatically"), so it dug blind and found little ore.
- Two deaths deep in its shaft (~117 tiles), then 11 surface deaths at night after respawning, the same nightfall pattern as opus-frozen-01.
- At 29.8 wall-minutes it declared "the game appears to have frozen". Telemetry shows the game advanced at full speed
  during all 204 input batches of 2 s or more; it was stuck and misread identical frames as a hang.
- Quit 72 times.

**Judgement.** The frozen clock clearly helped Sonnet: it reached the torch and shaft stage that real-time Sonnet never did,
mostly because it had time to recover from mistakes rather than dying while thinking. Anchor 5 (torches crafted),
−1 for the night deaths, constant quitting and blind digging.

---

## haiku-frozen-01: Haiku 5.5 (reasoning medium), frozen clock, PvE on, interface card. **4/10**

Played 30.0 game-minutes (plus 30.2 minutes paused while thinking), $0.99. Milestone score 5 (game time): wood ×3 at 0:37,
workbench 0:46, wood_100 25:44. 28 deaths, deepest 6 tiles, 57 continuation prompts.

**What went well**
- Crafted torches from its first gel at about 2 minutes, the earliest crafted torches in the pilot.
- At ~17 minutes it stated the correct furnace plan unprompted (20 stone, a nearby workbench, torches) and gathered
  26 stone for it.
- Collected 108 wood and 38 gel, enough materials for the next tier.

**What went wrong**
- The furnace never appeared in its crafting list. It re-placed workbenches and re-opened the menu several times but could
  not tell whether a bench was standing in range [INFERENCE: placement failed or the bench was out of range].
- Could not dig: the deepest point was 6 tiles. Like real-time Haiku and Sonnet, it never found the 2-wide shaft.
- 28 deaths, mostly at night after minute 25 (wall), and quit 57 times ("more clicks aren't likely to help").

**Judgement.** Better than real-time Haiku: it crafted, placed and planned the right next step, and the frozen clock gave
it time to do so. UI state confusion (is the bench in range?) and no digging technique stopped it one step
before the furnace. Anchor 5 (torches crafted), −1 for the death loop and constant quitting.

---

## combo-haiku-01: Sonnet 5.5 (low) planner + Haiku 5.5 executor, real time, PvE on. **2/10**

Played the full 30 minutes, $1.34 (planner $1.21, executor $0.13). Milestone score 5: wood ×3 at 0:43, wood_100 5:54,
torch_10 13:24 (a Torch Zombie drop). **No workbench**, 35 deaths, never below 5 tiles. 70 plans, 638 executor actions,
2.6 s median screenshot age (fresher than any single-model run).

**What went well**
- The split works mechanically: the planner gave concrete, screen-referenced objectives ("trunk at x~480 just left of the
  player") every 10-30 s and Haiku carried them out; 121 wood, the most of any run.
- Correct tactical calls at the surface (kill this slime, avoid the pit), and once night fell it recognised the graveyard
  and tried to lead the executor out of it.

**What went wrong**
- **The harness blocked crafting.** The planner tried to open the inventory with `"Escape"` dozens of times; the controller
  only accepts `"esc"`, so those replies were rejected and dropped without feedback (harness note 8). The executor cannot
  open menus on its own initiative, so nothing was crafted all run. This run does not measure the planner's crafting.
- From 6 minutes on, the accepted plans were "kill the slime, stay nearby, walk right": reactive steering of the executor
  instead of progression.
- 35 deaths at night near spawn and in the graveyard, the same pattern as every surface run.

**Judgement.** The fastest and freshest control loop of the pilot, with its crafting path broken by a harness bug.
The score reflects what happened in the game, not what the setup can do; combo-v2 reruns it with the bug fixed.
Anchor 2 (wood only).

---

## combo-jev-01: Sonnet 5.5 (low) planner + Jev 1.14 screenshot executor, real time, PvE on. **2/10**

Played the full 30 minutes, $1.66 (planner $1.14, Jev $0.51). Milestone score 5: wood_1 1:53, wood_25 4:38, wood_100 7:30,
torch_10 16:31 (Torch Zombie drop). No workbench, 24 deaths, never below the surface.
**0.38 s median executor latency and 0.44 s screenshot age**, an order of magnitude fresher than any LLM-only loop.

**What went well**
- 221 wood, the most of any run, from about 1,280 Jev decisions (side classification plus reach sweeps).
- Fewest deaths of the surface-bound runs (24 vs 35-43), probably because Jev reacts within half a second. Not tested.

**What went wrong**
- No crafting: 47 planner replies containing inventory clicks were dropped by the key-name bug (harness note 8).
- Jev's own action choice is weak: in 348 of its decisions the harness had to override `attack`/`chop_tree` because Jev
  reported no target on that side, and 327 decisions were `wait`.
- Slow start: the first wood came at 1:53, against about 25 s for every LLM-only run.

**Judgement.** Fast reflexes and endless gathering, but no progression, partly because of the harness bug.
Anchor 2 (wood only).

---

## combo-v2-opus-haiku-01: Opus 5.5 (low) planner + Haiku 5.5 executor, combo-v2 UI sessions, real time, PvE on. **2/10**

Played the full 30 minutes, $2.03. Milestone score 6: wood ×3 at 0:32, workbench 1:51, wood_100 2:20, torch_10 14:36
(Torch Zombie drop). 43 deaths, never below the surface. 33 planner click batches, no rejected replies.

**What went well**
- The combo-v2 mechanics work: the planner opened the inventory and crafted the workbench itself, inside a UI session
  ("Wait while the planner crafts"), less than 2 minutes in. combo-v1 never got that far.
- 112 wood and 35 gel collected: materials for torches and more were there.

**What went wrong**
- **It never placed the workbench.** For about five minutes (2:15-7:20) every plan was "select slot 6 and click the
  ground next to you". Clicks on the solid ground tile itself do not place anything; telemetry shows the bench still in
  the inventory at the end, so nothing was ever crafted at it and the 35 gel never became torches.
- Digging failed the same way as for the other non-Opus-solo runs: single-tile holds under the feet, so depth stayed 0.
- Night death loop: 43 deaths, plans degenerating into "swing at the zombie touching you".

**Judgement.** The fix moved the bottleneck from the harness to the game: crafting now works, block placement and
digging do not. Planning from screenshots every 5-60 s cannot correct a fine placement error that a single model in a tight
look-act loop eventually fixes. Anchor 2-3 (workbench crafted, never placed or used), 2 for the death loop.

---

## combo-v2-sonnet-haiku-01: Sonnet 5.5 (low) planner + Haiku 5.5 executor, combo-v2 UI sessions, real time, PvE on. **2/10**

Played the full 30 minutes, $1.08. Milestone score 6: wood ×3 at 1:52, wood_100 4:16, workbench 4:54, torch_10 18:21
(Torch Zombie drop: torches 0→15 with gel unchanged). 40 deaths, deepest 1 tile. 17 planner click batches, no rejected replies.

**What went well**
- The planner crafted the workbench itself in a UI session, with the executor waiting ("Stand still; crafting in progress").
- Plans were concrete and screen-referenced throughout.

**What went wrong**
- The workbench was never placed (still in the inventory at the end), so nothing else was crafted.
- Digging: every plan was "aim at the block directly below your feet", one tile wide, from minute 10 to the end; the
  2-tile-wide shaft was never found. Deepest point 1 tile.
- 40 deaths in the night loop at spawn.

**Judgement.** Same outcome as the Opus-planner combo, a little slower. With the harness bug fixed, the combo's limits
are the same two game skills the single models struggle with (placing, digging), now without a tight feedback loop.
Anchor 2-3 (workbench crafted, never placed or used), 2 for the death loop.

---

## haiku-rt-pveoff-01: Haiku 5.5, real time, **PvE off**, interface card. **2/10**

Played the full 30 minutes, $0.52. Milestone score 3: wood_1 0:21, wood_10 1:31, workbench 1:45. **0 deaths**, deepest 2 tiles,
63 continuation prompts.

**What went well**
- No deaths, as expected without enemies; a workbench within 2 minutes.

**What went wrong**
- Fewer than 25 wood all run, and the workbench stayed in the inventory (never placed).
- From about minute 5 to the end it tried to dig down with one-tile holes and reported "stuck on the same digging problem"
  dozens of times, quitting 63 times. Without enemies there is no gel, so torches were out of reach anyway.

**Judgement.** Taking the enemies away removed the deaths but not the barrier: Haiku's limit in this pilot is the
digging and placing technique, not combat. Its PvE-on run had a higher milestone score only through zombie drops.
Anchor 2 (wood, workbench crafted but never placed).

---

## haiku-rt-nocard-01: Haiku 5.5, real time, PvE on, **no interface card**. **2/10**

Played the full 30 minutes, $0.55. Milestone score 5 (game time): wood ×3 at 3:06-3:08, workbench 3:26, torch_10 17:07
(Torch Zombie drop; 29 gel never used). 36 deaths, deepest 1 tile, 34 continuation prompts.

**Compared with haiku-rt-01 (same setup with the card)**
- The opening was **2.7 minutes slower**: about 3 minutes of holding the mouse on trunks without selecting the axe
  (the card names the hotbar keys; without it Haiku took a while to switch tools).
- Everything after the opening matched: no digging (depth 1), a night death loop from about minute 10 (36 deaths), and
  "workbench placed" claims while the bench stayed in the inventory.
- Fewer continuation prompts (34 vs 63), probably because more of the run was spent dead or respawning.

**Judgement.** The card buys the opening minutes, not the barriers. Anchor 2-3 (workbench crafted, not demonstrably
placed or used), 2 for the death loop.

---

## sonnet-rt-pveoff-01: Sonnet 5.5 (reasoning low), real time, **PvE off**, interface card. **2/10**

Played the full 30 minutes, $4.15. Milestone score 4 (game time): wood ×3 at 0:50, workbench 1:05. 2 deaths (both falls into
chasms; the "depth 129" in the summary is the fall, not digging), **118 continuation prompts**.

**What went well**
- Crafted **and placed** the workbench by about 2 minutes, after first mistaking a placement preview for a placed bench and
  then correcting itself ("that earlier sighting must have been a ghost image").

**What went wrong**
- Never dug: 16 dirt blocks in 30 minutes. After the bench it wandered the surface (214 tiles right and back twice),
  fell into chasms twice, and later mined its own bench back up.
- Quit 118 times, the most of any run; with no enemies there was nothing to react to, and it reported instead of playing.
- No gel exists without enemies, so torches were impossible; it did not look for other progress (ore, caves).

**Judgement.** Removing enemies removed deaths but not passivity. Sonnet's real-time problem in this pilot is giving up and
not finding a digging technique, not combat. Anchor 3 (workbench crafted and placed), −1 for the constant quitting and
aimless wandering.

---

## opus-rt-02: Opus 5.5 (reasoning low), real time, PvE on, interface card ($11 cap). Repeat of opus-rt-01. **3/10**

Played the full 30 minutes, $5.77 (fewer, cheaper calls than run 1: it spent much of the night dead). Milestone score 5
(game time): wood_1 0:08, wood_25 0:38, workbench 1:09, torch_10 22:41 (Torch Zombie drop; 51 gel never crafted).
**29 deaths**, deepest 27 tiles, 2 continuation prompts.

**What went well**
- Same knowledgeable opening as run 1: workbench placed, wooden sword, hammer and breastplate crafted and equipped by
  4.5 minutes; 112 wood; 10 tin ore mined from a surface vein.
- Rarely quit (2 continuations), against 5 in run 1 and 34-118 for Sonnet and Haiku.

**What went wrong**
- It started digging only at about 7 minutes, with one-tile holes ("I seem to be standing next to the hole rather than in
  it"), and was still at the surface when night fell at about 12 minutes.
- Night loop: 27 deaths between 11:51 and 22:24 at spawn, almost exactly one every 25 s.
- The same perception errors as run 1: slimes and zombies read as "hostile bunnies", "lag" and "dropped inputs"
  blamed for missed chops.
- 51 gel and a placed bench, but no torches crafted.

**Judgement.** Same model, same world, same settings: run 1 reached a furnace with 2 deaths, run 2 stalled at the bench
with 29. The difference is almost entirely where Opus was when night fell. Single 30-minute runs with PvE on can't rank
models. Anchor 4 (workbench plus armour, weapon and a shaft attempt), −1 for the death loop.

---

## haiku-rt-card2-01: Haiku 5.5, real time, PvE on, **interface card v2** (tile mechanics). **2/10**

Played the full 30 minutes, $0.47. Milestone score 4 (game time): wood_1 0:41, wood_25 0:59, workbench 1:04. 14 deaths,
deepest 7 tiles, 30 continuation prompts.

**Compared with haiku-rt-01 (card v1)**
- Deeper (7 tiles vs 0) and fewer deaths (14 vs 43), but it got down by digging into a dirt pocket and then fought zombies
  in a small cave for most of the last 15 minutes, not by a 2-wide shaft.
- Still never placed the workbench (in the inventory all run) and never crafted torches (15 gel unused).
- No `torch_10` from zombie drops this time, so its milestone score is lower even though play was marginally better.

**Judgement.** Being told how placement and holes work did not change what Haiku does on screen; its failures are
execution and persistence ("the same failing digging approach"), not missing facts. Anchor 2 (workbench crafted, never placed).
