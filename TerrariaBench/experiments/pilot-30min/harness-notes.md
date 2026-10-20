# Pilot 30-minute runs: harness and benchmark-design findings

Things the pilot exposed about the benchmark itself (not about the models). Each needs a decision before Core v0.1.

1. **Seasonal events follow the real system date.** Terraria enables Halloween from the machine clock. The pilot ran
   on 19-20 October, so every run is Halloween-season Terraria: pumpkins (item 1725) grow on the surface and appear in
   Sonnet, Haiku and Opus frozen inventories. Runs are consistent with each other within the pilot, but the same world and
   seed will play differently in another month. Core v0.1 must pin the date (fake system time for the game process,
   or the observer mod forcing the seasonal flags off).
2. **Possession milestones don't prove crafting.** `torch_10` (published catalog) fires on holding 10 torches. Sonnet and
   Haiku real-time and the Haiku combo all reached it by picking up 20-61 torches at night (gel unchanged, no crafting call):
   the Torch Zombie, a night surface variant, always drops 5-20 torches. One zombie kill satisfies the milestone. The extended scorer needs crafted-item attribution (observer
   `OnCraft` hook) next to possession.
3. **Every 30-minute run contains a night.** The first dusk comes at about game-minute 15. Where the model is at
   nightfall (deep underground vs. surface) dominated deaths: Opus real time underground, 2 deaths; Opus frozen,
   Sonnet and Haiku on the surface, 20-43 deaths with Graveyard biomes forming from tombstones at spawn. Night survival should be
   reported as its own measure, and single runs per cell are noisy because of it.
4. **Continuation policy dominates some runs.** Sonnet needed 101 continuation prompts and Haiku 63. The count is a real
   behaviour measure, but each continuation costs a call and wall time. Report it next to the score.
5. **Jev cannot ground relational boxes.** "The tree closest to the player" boxes the player itself in 11/12 frames;
   without the relation it boxes the most salient tree far away. Combo-v1 uses side classification plus fixed reach
   sweeps, and only runs `attack`/`chop_tree` when Jev reports a target on that side.
6. **Executor parity.** The first combo executor capped holds at 1 s while single-model runs allow 2 s; trees took
   about 100 s to fell. Fixed to 2 s before any 30-minute combo run.
7. **Frozen runs were shown a desktop "Application Not Responding" dialog.** SIGSTOP makes the game miss Hyprland's
   window pings, so Hyprland overlaid an ANR dialog on the game window during long model calls. All three frozen runs
   saw it in their screenshots (Haiku 3+ times; Opus and Sonnet blamed "lag" on it), and Haiku clicked the screen while
   it was up. Real-time runs were not affected. Fixed on Omarchy with `misc.enable_anr_dialog = false` (runtime and
   `~/.config/hypr/hyprland.lua`). The frozen-vs-real-time comparison in this pilot carries this confound.
8. **Combo planners' inventory clicks were silently rejected.** Planners wrote `"Escape"`; the controller only accepts
   `"esc"`, so 92 planner replies in combo-haiku-01 and combo-jev-01 (106 attempts to open the inventory, including the
   smoke runs) failed validation and were dropped without telling the planner. Fixed: key aliases are normalised, and a
   rejected reply is reported back on the planner's next call with the valid key names. combo-v1 results therefore
   do not measure planner crafting at all.
9. **Recordings of frozen runs stop at 30 wall-minutes.** The desktop recorder had a 1800 s cap; frozen runs take
   about 60 wall-minutes. The second half of opus-, sonnet- and haiku-frozen-01 has frames and logs but no desktop
   video. Fixed (4 h cap; recording still ends on result.json).
