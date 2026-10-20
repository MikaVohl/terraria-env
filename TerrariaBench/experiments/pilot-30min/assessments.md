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
