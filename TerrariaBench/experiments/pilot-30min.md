# TerrariaBench pilot: 30-minute runs (19-20 October 2026)

A 12-hour, budget-capped pilot on one world: three Claude models on their own (real time and frozen clock), planner +
executor combinations (including Jev, from screenshots only), and variants for enemies, the interface card and a
mechanics card. 16 full runs. Every run was judged individually (`pilot-30min/assessments.md`: 0-10 with written
reasons) as well as by the reconstructed milestone score.

**This is a pilot, not a leaderboard:** one world, one run per configuration (two for Opus real time), Halloween season,
and several harness defects found and fixed along the way (`pilot-30min/harness-notes.md`). Use it to decide what
Core v0.1 measures, not to rank models.

## Setup (all runs unless stated)

- World: `reference-reconstructed-v1` (fixed seed and save; reconstructed terrariabench.com profile), 1024×1024 window.
- Normal gameplay **with PvE on** (enemies, night, death and respawn), 30 minutes of game time.
- Screenshot-only observation (JPEG q85), real keyboard/mouse input through the controller, checkpoint log available.
- A short **interface card** in the task prompt: key bindings and screen geometry, no strategy. Variants: no card, or
  **card v2** with two tile-mechanics facts (place onto an empty tile next to solid ground; the 2-tile-wide character only
  falls through holes at least 2 tiles wide).
- Hidden remaining time; a continuation prompt whenever the model stops early ("quits" in the table).
- **Real time:** the game keeps running while the model thinks. **Frozen:** the game process is stopped during every
  model call, so 30 minutes of game time take about an hour of wall time.
- **Combos:** a planner (Opus or Sonnet) sets an objective every 5-60 s and does the inventory work itself; a fast
  executor (Haiku, or Jev from screenshots) acts every 0.4-3 s. combo-v1 planners clicked blind; combo-v2 lets the planner
  re-observe right after its clicks while the executor waits.

## Results

**Judged** is my score (anchored on progress, ±1 for play quality; scale in the assessments file). **Milestones** is
the reconstructed published catalog. Milestone times are game time (mm:ss); depth is the deepest point in tiles below the
start; shot age is the median age of the screenshot an action was based on.

| Run | Setup | Judged | Milestones | wood_1 | wood_25 | wood_100 | workbench_1 | torch_10 | furnace_1 | Deaths | Depth | Quits | Shot age (s) | USD |
|---|---|---:|---:|---|---|---|---|---|---|---:|---:|---:|---:|---:|
| **Single model, real time** | | | | | | | | | | | | | | |
| opus-rt-01 | Opus (realtime) | **6** | 6 | 0:49 | 0:50 | – | 2:22 | 14:52 | 21:40 | 2 | 203 | 5 | 5.02 | 7.18 |
| opus-rt-02 | Opus (realtime) | **3** | 5 | 0:08 | 0:38 | – | 1:09 | 22:41 | – | 29 | 27 | 2 | 5.53 | 5.77 |
| sonnet-rt-01 | Sonnet (realtime) | **2** | 5 | 0:23 | 0:24 | – | 0:48 | 12:59 | – | 34 | 1 | 101 | 6.22 | 5.28 |
| haiku-rt-01 | Haiku (realtime) | **2** | 5 | 0:22 | 0:23 | – | 0:44 | 12:02 | – | 43 | 0 | 63 | 3.44 | 0.50 |
| **Single model, frozen clock** | | | | | | | | | | | | | | |
| opus-frozen-01 | Opus (frozen) | **4** | 4 | 0:12 | 0:14 | – | 0:29 | – | – | 20 | 340 | 7 | 5.53 | 14.14 |
| sonnet-frozen-01 | Sonnet (frozen) | **4** | 4 | 0:15 | 0:16 | – | 0:18 | – | – | 13 | 125 | 72 | 5.69 | 8.96 |
| haiku-frozen-01 | Haiku (frozen) | **4** | 5 | 0:37 | 0:37 | 25:44 | 0:46 | – | – | 28 | 6 | 57 | 3.41 | 0.99 |
| **Variants (real time)** | | | | | | | | | | | | | | |
| sonnet-rt-pveoff-01 | Sonnet (realtime, PvE off) | **2** | 4 | 0:50 | 0:51 | – | 1:05 | – | – | 2 | 129* | 118 | 6.13 | 4.15 |
| haiku-rt-pveoff-01 | Haiku (realtime, PvE off) | **2** | 3 | 0:21 | – | – | 1:45 | – | – | 0 | 2 | 63 | 3.42 | 0.52 |
| haiku-rt-nocard-01 | Haiku (realtime, no card) | **2** | 5 | 3:06 | 3:08 | – | 3:26 | 17:07 | – | 36 | 1 | 34 | 3.02 | 0.55 |
| sonnet-rt-card2-01 | Sonnet (realtime, card v2) | **2** | 4 | 0:42 | 0:43 | – | 1:00 | – | – | 39 | 4 | 115 | 6.43 | 4.61 |
| haiku-rt-card2-01 | Haiku (realtime, card v2) | **2** | 4 | 0:41 | 0:59 | – | 1:04 | – | – | 14 | 7 | 30 | 3.42 | 0.47 |
| **Planner + executor (real time)** | | | | | | | | | | | | | | |
| combo-v2-opus-haiku-01 | Opus planner + Haiku (combo-v2) | **2** | 6 | 0:30 | 0:32 | 2:20 | 1:51 | 14:36 | – | 43 | 0 | – | 2.72 | 2.03 |
| combo-v2-sonnet-haiku-01 | Sonnet planner + Haiku (combo-v2) | **2** | 6 | 1:52 | 1:53 | 4:16 | 4:54 | 18:21 | – | 40 | 1 | – | 2.63 | 1.08 |
| combo-haiku-01 | Sonnet planner + Haiku (combo-v1) | **2** | 5 | 0:41 | 0:42 | 5:52 | – | 13:22 | – | 35 | 5 | – | 2.6 | 1.33 |
| combo-jev-01 | Sonnet planner + Jev (combo-v1) | **2** | 5 | 1:53 | 4:38 | 7:30 | – | 16:31 | – | 24 | 1 | – | 0.44 | 1.66 |

\* Sonnet PvE-off's depth comes from falling into a chasm, not from digging.

## What we learned

1. **Opus 5.5 is the strongest model here, but a single 30-minute run cannot show it reliably.** Opus real-time run 1 is
   the only run that got past torches: it found the 2-tile-wide shaft on its own, dug 200 tiles, lit a cave, mined 27 copper
   and crafted a furnace (21:40), dying twice. The repeat, with identical settings, stalled after workbench, armour and
   sword, and died 29 times. The difference was almost entirely **where Opus was when night fell**: underground in run 1,
   at the surface in run 2. Across its three solo runs Opus still showed the broadest game knowledge (armour, weapons,
   furnace recipe, the shaft technique) and quit far less (2-7 continuations vs 30-118 for the others).

2. **Night is the great filter, but removing it doesn't unlock progress.** Dusk comes at about game-minute 15. Every
   run on the surface at nightfall entered a death loop: 13-43 deaths, mostly at spawn, where tombstones build a
   Graveyard that keeps spawning zombies after dawn. No model built a shelter or dug in on purpose; several decided to
   "wait out the night by dying". But with PvE off, Sonnet and Haiku had 0-2 deaths and **still** never got past the
   workbench: they wandered, quit (63 and 118 times) and never dug. Enemies decide how runs end; they are not what holds
   the weaker models back.

3. **The barriers after the workbench are two physical skills: digging and placing.**
   - *Digging:* a one-tile hole doesn't let the 2-tile-wide character fall in. Only Opus (both solo modes) and frozen Sonnet
     found the 2-wide shaft. Sonnet real time spent 20 minutes believing "the pickaxe only removes the surface layer".
   - *Placing:* clicking the solid ground does not place anything; the target is the empty tile above it. This stopped
     Opus's furnace, Haiku frozen's bench and both combo-v2 benches, and several models reported a bench as placed
     when it was still in their inventory.
   - **Telling them doesn't fix it.** With card v2, Sonnet repeated the rule ("too narrow for my two-tile-wide
     character, I need to widen it") and still dug one-tile holes all run; neither model placed its bench. The gap is
     executing a precise multi-step manipulation from screenshots, not missing knowledge.

4. **Freezing the clock helped the weaker models most** (one run each, so a hint, not a result). Frozen Sonnet and frozen
   Haiku were judged 4, against 2 in real time: both crafted torches themselves and Sonnet dug 125 tiles. Frozen Opus (4)
   landed between its two real-time runs (6 and 3). All three frozen runs were also shown a desktop "Application Not
   Responding" dialog (harness note 7), so these runs understate the frozen condition, if anything.

5. **Quitting is a model trait worth measuring.** Continuation prompts per 30 minutes: Opus 2-7, Haiku 30-63,
   Sonnet 72-118. Sonnet often wrote a "I'm stopping here" report every 15-20 seconds and took one or two actions between them.

6. **Possession milestones overrate surface play.** `torch_10` fired in nine runs, and only one of those (opus-rt-01)
   crafted its torches. Torch Zombies, a night enemy, drop 5-20 torches each. Pumpkins (Halloween) and zombie drops fill
   inventories too. Both combo-v2 runs have milestone score 6, equal to the furnace run, while doing nothing after the
   workbench. Ranked by milestones the pilot looks flat (4-6); judged, the spread is 2-6 and follows real progress.

7. **The interface card buys the opening, nothing more.** Without it Haiku took 3 minutes to switch to the axe (first wood at
   3:06 vs 0:22), then played the rest of the run exactly like the carded run. Card v2 (mechanics) had no visible effect.

8. **Planner + executor splits give the fastest control loop but don't progress yet.** Jev acted on 0.44 s-old
   screenshots (LLM-only loops: 3.0-6.4 s) and gathered the most wood (221). combo-v1 could not craft at all, because a
   key-name bug silently dropped the planners' inventory clicks (harness note 8). combo-v2 fixed that: both planners crafted
   the workbench in a UI session within 2-5 minutes, then hit the same placement and digging walls as the single models,
   with a slower feedback loop for fine corrections. Cheap, though: $1.1-2.0 per run.

9. **Cost per 30 minutes of game time:** Opus real time $5.8 (run 2) to about $9 (run 1, extrapolated: it hit its $8 cap
   at 24 minutes), Sonnet $4.2-5.3, Haiku about $0.5, combos $1.1-2.0. Frozen runs cost about 1.6-2× their real-time
   counterparts for the same game time.

## Harness defects found (all fixed for the runs after them)

Details in `pilot-30min/harness-notes.md`:
- Seasonal events follow the system date. Not fixed yet; pin it in Core v0.1.
- Possession milestones don't prove crafting.
- Jev cannot ground relational boxes ("the tree nearest the player").
- The combo executor's hold limit was 1 s against 2 s for single models.
- Hyprland's "Application Not Responding" dialog appeared over frozen games. Now disabled on Omarchy.
- Planner key names were silently rejected.
- The recorder stopped at 30 wall-minutes. Frozen runs therefore have desktop video for their first 30 minutes only;
  their frames and logs are complete.

## Recommendations for Core v0.1

1. **Pin the game date** (no seasonal events) and record it in the manifest.
2. **Score what the agent did, not what it holds:** crafted items (observer craft hook), placed stations, deepest dug
   point, nights survived, alongside the published milestones.
3. **At least 3 runs per cell, on 2+ worlds.** With PvE on, one run per cell is mostly a measure of where the model was at
   dusk (opus-rt-01 vs opus-rt-02).
4. **Make the frozen clock the main capability track** once rerun without the ANR dialog. It removes latency as a
   confound and was the condition in which the weaker models showed what they know. Keep real time as the second track,
   with latency reported.
5. Report quits (continuations) and screenshot age next to every score.
6. Keep the interface card v1 (it removes a 3-minute tool-switching tax); drop card v2 (no effect).
7. Combos: keep combo-v2 only. The next step is letting the planner take over the mouse for a few precise steps
   (placement, the first shaft tiles) instead of issuing objectives.

## Evidence and playback

Per run on Omarchy, `~/Projects/TerrariaBench/runs/pilot-30min/<run>/`: `desktop.mp4` (whole desktop: game plus live
agent panel), `frames/` (every image the model saw), request/response logs, `telemetry/` (observer heartbeats and
checkpoints), `inputs.jsonl`, `decisions.jsonl` (combos), and `evidence/` (`timeline.md`, `summary.json`,
`contact-sheet.png`) from `tools/run_evidence.py`. 8× time-lapses (`highlights-8x.mp4`) of all 16 runs are in the local,
gitignored `runs/pilot-30min/`. The results table comes from `tools/pilot_table.py`. The world fixture and observer build are
fixed, so starting conditions can be reproduced exactly; outcomes cannot (real time, enemy spawns).

**Spend:** $59.89 on the gateway (cap $70) and $0.59 on OpenRouter (cap $5), including smoke runs, the
aborted key-bug run and all reserved-but-uncharged calls.
