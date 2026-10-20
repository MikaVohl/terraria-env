# Pilot 30-minute runs: per-run assessments

One reviewer's (the harness author's) judgement of each run, written from the evidence pack
(`evidence/timeline.md`, `summary.json`, `contact-sheet.png`), the frames the model saw and the
desktop recording. The scores are subjective by design. They complement the milestone score; they do not replace it.

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

Played 28.1 game-minutes (plus 20.3 minutes paused while thinking); the $15 cap ended it. Milestone score 4: wood ×3 at 25 s,
workbench 0:55. 20 deaths, deepest 340 tiles, 7 continuation prompts. Cost $14.14, twice the real-time run for similar game time.

**What went well**
- Fastest start of any run: 25 wood in 25 s, workbench and wood armour within 2 minutes.
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

Played 29.9 game-minutes (plus 28.7 minutes paused while thinking), $8.96. Milestone score 4: wood ×3 at 35 s,
workbench 0:56. 13 deaths, deepest 125 tiles, 72 continuation prompts.

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

Played 30.0 game-minutes (plus 30.2 minutes paused while thinking), $0.99. Milestone score 5: wood ×3 at 1:10,
workbench 2:18, wood_100 at the end. 28 deaths, deepest 6 tiles, 57 continuation prompts.

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
- **The planner never crafted.** Its schema lets it click in the inventory itself, but in 70 plans it used that twice (a hotbar
  key and one stray click) and mentioned crafting twice. It never made a workbench, even with 121 wood. The executor cannot open
  menus on its own initiative, so nothing was crafted all run.
- From 6 minutes on, the plans became "kill the slime, stay nearby, walk right": reactive steering of the executor
  instead of progression. A planner that sees one screenshot every 10-30 s ends up narrating combat.
- 35 deaths at night near spawn and in the graveyard, the same pattern as every surface run.

**Judgement.** The fastest and freshest control loop of the pilot, applied to the wrong job. Delegation removed the
crafting step entirely: Sonnet alone crafted a workbench in under a minute, but as a planner it never did. This is a design
issue of combo-v1 (the planner treats itself as a coach, not the player), not proof that combos can't work.
Anchor 2 (wood only).
