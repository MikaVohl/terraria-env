# TerrariaBench pilot: 30-minute runs (19-20 October 2026)

A 12-hour, budget-capped pilot on one world: three Claude models alone (real time and frozen clock), planner +
executor combinations (including Jev, from screenshots only), and a few variants. Every run was judged individually
(`pilot-30min/assessments.md`, 0-10 with written reasons) as well as by the reconstructed milestone score.

**This is a pilot, not a leaderboard:** one world, one run per configuration (two for Opus real time), Halloween season,
and several harness defects found and fixed along the way (`pilot-30min/harness-notes.md`). Use it to choose what Core
v0.1 measures, not to rank models.

## Setup (all runs unless stated)

- World: `reference-reconstructed-v1` (fixed seed and save; reconstructed terrariabench.com profile), 1024×1024 window.
- Normal gameplay **with PvE on** (enemies, night, death and respawn), 30 minutes of game time.
- Screenshot-only observation (JPEG q85), real keyboard/mouse input through the controller, checkpoint log available.
- A short **interface card** in the task prompt: key bindings and screen geometry only, no strategy.
- Hidden remaining time; a continuation prompt when the model stops early.
- **Real time:** the game keeps running while the model thinks. **Frozen:** the game process is stopped during
  every model call, so 30 minutes of game time take about an hour of wall time.
- **Combos:** a planner model (gateway) sets an objective every 5-60 s and does inventory work itself; a fast
  executor (Haiku or Jev) acts on fresh screenshots every 0.4-3 s. combo-v1 planners click blind; combo-v2 lets the
  planner re-observe immediately after its clicks while the executor waits.

## Results

Subjective score first (my judgement, anchored on progress, ±1 for play quality); milestone score is the reconstructed
published catalog. Milestone times are game time (mm:ss).

RESULTS_TABLE

## What we learned

1. **Opus 5.5 in real time is the only run that got past torches, to a furnace (21:40).** It found the 2-tile-wide
   shaft on its own, dug 200 tiles, lit a cave and mined 27 copper ore. It was underground when night fell and died only
   twice. Its blockers were UI state (which item is held, is the inventory open) and placing the furnace.

2. **Night is the great filter.** Dusk comes at about game-minute 15. Every run that was on the surface at nightfall
   entered a death loop: 13-43 deaths, mostly at spawn, where tombstones accumulate into a Graveyard biome that keeps
   spawning zombies after dawn. No model built a shelter or dug in deliberately; several chose to "wait out the night by
   dying". Where the model happens to be at dusk is the largest single source of variance in these runs.

3. **Two specific skills separate the runs: digging and placing.**
   - *Digging:* the player is two tiles wide, so a one-tile hole doesn't work. Opus found the 2-wide shaft in both of its
     solo runs, Sonnet only in its frozen run (after 7 minutes), Haiku and every combo never. Sonnet real time spent 20
     minutes believing "the pickaxe only removes the surface layer".
   - *Placing:* clicking the solid ground does not place a block or station; the target must be the empty tile above it.
     This stopped Opus real time's furnace, Haiku frozen's workbench and the Opus-planner combo's workbench.

4. **Freezing the clock helped the weaker models, not Opus** (one run each, so treat as a hint). Sonnet and Haiku both
   crafted torches only when frozen, and Sonnet dug to 125 tiles. Opus frozen was faster through the opening than Opus
   real time but drowned deep down, respawned at night and died 20 times. The frozen runs were also shown a desktop
   "Application Not Responding" dialog (harness note 7), which some models blamed for "lag".

5. **Sonnet and Haiku give up constantly.** Continuation prompts per run: Opus 5-7, Haiku 57-63, Sonnet 72-101. Sonnet
   real time wrote a "I'm stopping here" report roughly every 18 seconds. Quitting rate is a measurement worth keeping.

6. **Possession milestones overrate surface play.** `torch_10` fired in four runs that never crafted a torch: Torch
   Zombies drop 5-20 torches each. Pumpkins (Halloween) and zombie drops inflate inventories too. The milestone score
   ranks Sonnet and Haiku real time (5) above Opus frozen (4); by what they actually achieved it should be the reverse.

7. **Planner + executor splits give the fastest control loop but don't progress yet.** The Jev executor acted on
   0.44 s-old screenshots (LLM-only runs: 3.4-6.2 s) and gathered the most wood (221). combo-v1 could not craft at all
   because of a key-name bug that silently dropped the planner's inventory clicks (harness note 8). combo-v2 fixed that and
   the Opus planner crafted a workbench in under 2 minutes, then could not place it.

8. **Cost.** Per 30 minutes of real-time play: Opus about $9 (cap hit at 24 minutes with $8), Sonnet $5.3, Haiku $0.5,
   combos $1.3-2.0. Frozen runs cost about 2× their real-time counterparts for the same game time.

VARIANTS_SECTION

## Harness defects found (all fixed before the next run used them)

See `pilot-30min/harness-notes.md` for details: seasonal events follow the system date (to pin in Core v0.1),
possession milestones vs crafting, Jev cannot ground relational boxes, combo executor hold parity, the ANR dialog over
frozen games, planner key names, and the 30-minute recorder cap (frozen runs have video for their first 30 wall-minutes
only; frames and logs are complete).

## Recommendations for Core v0.1

1. Pin the game date (no seasonal events) and record it in the manifest.
2. Score crafted items separately from possession (observer craft hook), and add digging depth and nights survived.
3. Keep PvE on, but report night survival separately; run at least 3 seeds/worlds per cell, because nightfall position
   dominates single runs.
4. Report the frozen-clock condition as a second track only after rerunning it without the ANR dialog.
5. Report continuation count and screenshot age next to every score.
6. Combos: continue with combo-v2 only. The next bottleneck there is fine placement; consider letting the planner
   take over the mouse for a few turns rather than issuing blind objectives.

## Evidence and playback

Per run on Omarchy, `~/Projects/TerrariaBench/runs/pilot-30min/<run>/`:
`desktop.mp4` (whole desktop: game plus live agent panel), `frames/` (every image the model saw), request/response
logs, `telemetry/` (observer heartbeat, checkpoints), `inputs.jsonl`, and `evidence/` (`timeline.md`, `summary.json`,
`contact-sheet.png`) from `tools/run_evidence.py`. 8× time-lapses (`highlights-8x.mp4`) for the single-model runs are in
the local gitignored `runs/pilot-30min/`. The world fixture and observer build are fixed, so starting conditions can be
reproduced exactly; game outcomes cannot (real time, enemy spawns).

Spend: SPEND_LINE
