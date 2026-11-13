
Inspiration:
- https://terrariabench.com/
- I like the craftax blog https://craftaxenv.github.io/ style and im sure there are LOTS of things we can use from craftax
    - UI is pretty good too
    - The methodology behind craftax is very well thought out and we should definitely note it
- Cool blog posts:
    - https://danijar.com/project/dreamer4/
    - https://www.uber.com/ca/en/blog/go-explore/
    - https://github.com/eliahuhorwitz/Academic-project-page-template
    - https://www.reactor.ink/blog/open-dreamer
    - https://craftaxenv.github.io/

- Two versions:
    - Official Terraria Game
        - Every AI model in same harness
        - Show cost
        - Set timeframe
        - Compare to RL if possible
            - Bitter lesson PPO
            - Maximally good: potential shaping, behavior cloning, etc
            - Estimate price for training and price for inference based on GPU renting price
        - AI and RL harness have same information
    - Terraria Lite
        - Standardized custom interface for AI's, operating at the same level of information as the RL solution
        - Show cost
        - Set timeframe
        - Compare to RL if possible
            - Bitter lesson PPO
            - Maximally good: potential shaping, behavior cloning, etc
            - Estimate price for training and price for inference based on GPU renting price
- terraria-lite/viz has
    - great playback/replay/rendering of the terraria world
    - great UI in case we want to show loss, value function, episode return, crafting recipes, rewards, achievements, inventory, etc
    - great visualization for this type of "zoom out and see all the environments playing in parallel"
    - lots of these visualization features can be added as an additional part of the site at some point
- Section about changes I made over time, in-progress results, the timeline, different versions, etc.
    - Maybe a gallery of each version, watching the performance, and mentioning what changed and whats wrong
- Any human-playable demo should give the human concessions to make it easier where constrained. for example, mouse anywhere on screen can highlight the furthest selectable tile in your range from player to mouse.

## Agent Notes

- **Score vs cost and vs time (Pareto plots).** One chart per track: x = dollars (GPU-hours × a stated rental rate with its date, or API cost), y = score. Runs already log wall time and steps; the Luna studies have audited costs. Makes "a $1.46 LLM run vs a 4B-step PPO run" comparable at a glance.
- **Human baseline in the browser.** The viz Play chapter already runs the real simulator. Let visitors play the fixed public seeds and submit scores and replays. A real human score distribution beats Craftax's "an author needed 5 hours for a perfect run", and it's engaging.
- **Craftax calibration as a credibility section.** Official Craftax baselines on our hardware against the published scoreboard (PPO 11.9%, PPO-RNN 15.3% of max reward), plus our PPO settings on Craftax. "Our pipeline reproduces Craftax" makes every Terraria-Lite number trustworthy.
- **Rigor visible by default (rliable conventions).** IQM with 95% CIs and the seed count on every bar, held-out test worlds, all 32 per-achievement rates, the Crafter-style score, a "verified" flag. TerrariaBench flags invalid runs; we can do better with exact replay verification: every leaderboard entry links to a replay that reproduces bit-for-bit.
- **Craftax-style "fast / hard / open-ended" sections, our version.**
    - Fast: actions/s for Terraria-Lite vs Crafter, Craftax and real tModLoader (from the Omarchy measurement).
    - Hard: achievement-tier bar chart showing the wall (iron pickaxe 0% generic vs ~40% shaped; chainmail never).
    - Skills: short clips of mining, crafting, the climb home.
- **TerrariaBench-style progress views.** A cumulative-achievements step chart over steps or minutes, and a first-unlock heatmap per agent (we already record each achievement's first-unlock step per episode).
- **"Bitter lesson" story page.** Environment fairness (supply) mattered more than algorithms (+0.9); a longer horizon was the biggest algorithmic gain; architecture tweaks did ~nothing; recipe shaping ties the generic arm on the mean but alone unlocks the pickaxe; 6B combined pickaxe and return to surface (29.33). An interactive one-dimension-at-a-time ablation explorer (as in the notebook) would be unique.
- **Failure gallery.** LLM illegal-action rates, PPO never returning to the surface on some seeds, bars wasted on a second anvil. People learn more from these than from leaderboards.
- **Submission kit.** Pinned environment version (v7 vs v8 clearly labelled), public validation seeds plus hidden test seeds, one eval command, a JSON results schema, and LLM harness rules (action budget, cost cap, time limit). Turns "set timeframe" into a concrete contract.

## Additional agent notes for TerrariaBench
1. Two leaderboards (real time, paused). Rows are models with their reasoning effort.
- Columns: extended score (headline, with crafted/placed/looted shown separately), published score (for comparison with terrariabench.com), furthest milestone, deaths, no-action turns, median latency, cost per
    run, number of worlds.
- Real-time vs paused side by side per model.
2. Milestone timelines: when each agent got wood, workbench placed, torches, furnace, underground, cavern.
3. Video per run, with the agent's text panel and key moments marked (the Opus bench at 3:07, Terra's cavern entry, deaths).
4. Harness card: the full system prompt, tool schema, settings, the no-action rule, and what's hidden from the model.
5. Failure gallery:
- false "placed" claims;
- the placement wall before Smart Cursor;
- real-time death loops;
- Haiku's summaries instead of actions;
- Terra choosing "Save & Exit".
6. Context: the published terrariabench.com runs (8 hours, best 4), and a note that loot can inflate the published score.
7. Cost and latency: dollars per game-minute, and how much of the game time a model spends thinking (real time only).

**My comment:** "Terra choosing "Save & Exit"" this is hilarious: mika@omarchy:Projects/TerrariaBench/runs/default-game-2026-11-08/m15-terra-rt-w402/desktop.mp4