# Decision register

Open decisions to finalize results for `WEBSITE_PLAN.md`. Process: decide at gates, then freeze, pre-register, run final experiments once, audit, publish.

Status: **Decided**, **Recommended** (awaiting your call), **Blocked** (needs evidence first), **Open**.
Last updated 2026-11-11 UTC.

Hill-climbing (harness, rules, training) starts only after the Gate 1 freeze; every later change is a new declared version, never an edit of v1.

## Process

| Gate | What gets frozen | Status |
|---|---|---|
| Gate 1 | Environment + harnesses tagged (`terraria-lite-1.0`, `lite-llm-harness-1.0`, `terrariabench-default-1.0`), prompts/settings/world fixtures hashed | Open |
| Gate 2 | Pre-registered protocol per track (matrix, seeds, worlds, budgets, stop/cap rules, scoring, statistics, money cap) | Open |
| Gate 3 | Audited results approved for the website | Open |

## A. Official Terraria LLM benchmark

| ID | Decision | Options | Evidence | Status |
|---|---|---|---|---|
| A1 | Game rules | Unmodified Classic, normal enemies | Gentle PvE (no hostile damage) was a crutch; default-v1 shows cheap models progress with enemies on | **Decided** |
| A2 | Shipped variants (max 2) | Real time vs paused | VideoGameBench precedent (real time vs Lite, which pauses); default-v1: Luna better paused, Haiku better in real time | **Decided** |
| A3 | Display settings | Game defaults + Smart Cursor ON | Only Smart Cursor moved play (Haiku ext 1→2, Terra 2→5); zoom 150%, 16:9, UI 1.25 no effect; perception probe flat | **Decided** |
| A4 | Interface | One `act` tool (keys, mouse, wait) returning a fresh JPEG; system prompt = goal + default controls; no hints; remaining time hidden; history + newest 8 screenshots | Simple, OSWorld/VideoGameBench-like | **Decided** |
| A5 | Stopping / continuation rule | Contract in prompt; forced tool call where the API allows; a reply without an action = `wait 1000 ms` + "No action was taken."; no early stop; run ends if the agent leaves the world | Landscape (27 runs): no run stopped by the rule; forced GPT calls 0 no-action turns in 1,701; unforced Haiku drifts into summaries late (counted, reported). Leave-world rule added after Terra's Save & Exit loop. LunaFactors: 4/72 Luna runs ended by an accidental Save & Exit | **Decided** (default-v2): leaving the world (incl. Save & Exit) is the model's own choice and ends the run; no harness compensation. Revisit only if it becomes frequent |
| A6 | Haiku setting | Thinking on (unforced) vs thinking off (forced) | Thinking off: published 0, 16 deaths, 3× cost per game-minute | **Decided**: thinking on, unforced; budget level per A9 (high) |
| A7 | Run length | 20 vs 40 game-minutes | All three 40-min runs scored every fact before 20:00 | **Decided**: 20 game-minutes |
| A8 | Worlds | 3 unseen worlds per cell for v1; extend to 5 later as a declared addition | World spread ≥ model spread among cheap models; 5 worlds roughly doubles the matrix cost. Worlds 401–404 were used to tune the harness (landscape, LunaFactors, Astra probe), so they are development worlds | **Decided**: 3 fresh worlds generated at Gate 1 with `tools/make_world_fixtures.py` (e.g. 501–503), hashed, never run before the final matrix; 401–404 stay development worlds |
| A9 | Models + reasoning | Haiku 5.5, GPT-6 Luna, GPT-6.1 Terra (GPT-5.6 Terra if 6.1 fails its probe), Opus 5.5, GPT-6 Astra; each at its highest allowed effort (`high`; Haiku extended thinking high, unforced); effort stated per row | LunaFactors: effort is the largest lever (Luna low → high: bench placed 0/7 → 6/13 in 20 min; Haiku off → medium 1 → 4 ext). Astra probe: best screen run so far (pub 7 / ext 12, furnace placed) at $0.27/game-min. Sonnet ≈ Haiku at 10–40× cost; Sol no better than Terra | **Decided** |
| A10 | Agent systems | Separate table (e.g. Opus planner + Jev executor) | Best default-v1 run (pub 6) was the combo; mixing with single models would confuse rankings | **Recommended** |
| A11 | Headline score | Extended catalog (crafted/placed/looted separated) headline; published 13-checkpoint score as a comparability column | Published score inflated by loot (Luna 6 mostly chests) | **Recommended** |
| A12 | Final matrix + budget | Paused primary + real-time secondary, each 5 models (A9) × 3 worlds (30 runs); agent-system table: Opus 5.5 (high) planner + Jev executor, both clocks × 3 worlds (6 runs) | Landscape costs at low effort: Haiku $0.1–1.2, Luna $0.1–0.3, Terra $0.7–1.3, Opus $3.7–5.0 per 20-min run; Astra (medium) ≈ $5.4. High effort ≈ ×2–6 per game-minute. Estimate ≈ $100–150 | **Decided**: campaign money cap **$150**; a 1–2-minute price probe per model at Gate 2; if the projection exceeds the cap, Opus and Astra drop to `medium` (stated per row) before any cut in worlds. Per-run caps = expected spend + 2 call reservations |
| A13 | Desktop hygiene on omarchy | No game core dumps; crash watcher ignores `dotnet`; do-not-disturb + popup dismissal at every launch | Crash toasts from 94 tModLoader teardown crashes appeared in recordings (fixed 2026-11-08, `2f1537b`); earlier videos may still contain toasts | **Decided** |
| A14 | Rate-limit errors in the ledger | Keep a 429's reservation as an uncertain charge; or settle it at $0 | A 429 is a rejection by the gateway's rate limiter before the model runs, so nothing is billed; the conservative rule stopped Astra's run 1.6 min early | **Decided**: HTTP 429 = not billed (`sent=False`): the reservation is released, the run treats it as an outage (game frozen, run clock stopped, bounded retries), every 429 is logged in `provider-failures.jsonl`. Implemented in `gateway.py` / `unified.py`. Other failures stay uncertain charges |

## B. Terraria-Lite environment

| ID | Decision | Options | Evidence | Status |
|---|---|---|---|---|
| B1 | Release version | v10 (v9 + real-behaviour ports at 15 ticks/action + tier-4 stepping stones) | Current default (`f196c03` = `4ef5afa` rules), PPO 1B, 5 seeds (`docs/reports/V10_PPO_1B_2026_11.md`): generic IQM 33.9% [32.7, 35.0], shaped 34.3% [33.4, 35.0] (target band 25–35%); deaths ~0.52, return to surface / lens / iron pickaxe 0/10 runs. Previous rules: generic 32.1–32.8%, shaped 33.6–34.9%; 4B no better (32.6–32.8) | **Recommended**, pending B4 night tuning |
| B2 | Return to surface / lens = 0 in every ported build | Bug vs learned behaviour | **Not a bug** (V10SurfaceBug, 2026-11-08): achievement, spawn and lens code identical across builds; scripted climbs and nights pass in every build; the noport policy transplanted into mining-/physics-only builds still returns 22–25/64. Cause: return is a seed-dependent all-or-nothing behaviour (v9: 5/10 seeds learn it at 1B; ported v10: 0/22 runs), and the enemy/combat ports make surface nights far deadlier (scripted iron-gear fighter: 61/64 deaths per night all-ports vs 12/64 noport; combat port: slimes hit every 3 steps because 40-tick i-frames replace the 8-step hurt cooldown) | **Resolved**: tune in B4 |
| B3 | Speed gate (D18) | Accept v10 at 0.52× v8 or optimize | Simulator is only 12% of a v10 PPO iteration; training is host-latency-bound (C6), and `train-speed` (merged) made it 1.18–1.22× faster, bit-identical | **Recommended**: relax gate to 0.5×, note in docs |
| B4 | Why ported policies never return to the surface | Night spawn rate; enemy damage / contact immunity under `FID_MOBS`/`FID_COMBAT`; something specific to 15-tick learning | **Night tuning did not help:** PPO 1B with `NIGHT_SPAWN_PERIOD` 120: 31.2/30.4%, 180: 33.4/32.1%, return to surface 0 in all 4. **Not seed variance:** mining-only and physics-only now 3 seeds each, return 0 in all 6 (at v9's ~50% rate, 6 misses ≈ 1.5%). So even without the enemy/combat ports, policies trained at 15 ticks/action don't learn the return, though a transplanted no-port policy can do it (22–25/64). Open hypotheses: long climbs take many more actions at 15 ticks (credit assignment), or the surface reward arrives too late within 10k steps | **Decided for v1**: ship v10 with the return to surface as a documented open challenge (failure gallery, website); a targeted study (scripted-climb curriculum, shaped return, longer episodes) is post-freeze hill-climbing and does not block Gate 1 |
| B8 | Support rules + leaf visuals (`SUPPORT_RULES`, `TREE_LEAF_VISUAL`, default on since `d277b85`) | Keep on | No floating torches/stations, mushrooms break, chest support protected; ~0.96× throughput. All earlier v10 PPO numbers used the previous rules | **Decided**; 1B re-run on the new default done (`V10_PPO_1B_2026_11.md`): generic 33.9% (+1.5 pp paired vs old rules), shaped 34.3% (+0.2), deaths 0.30 -> 0.52 |
| B9 | 4B budget on v10 | — | Shaped 4B final: 34.8 / 32.2% (1B: 33.6–34.9%); generic 4B 32.6–32.8% | Confirms C2: 1B standard |
| B10 | Explicit tools + Auto Select (`EXPLICIT_TOOLS`, default 1) | Keep on | Starter Copper Shortsword/Pickaxe/Axe as items, best pickaxe = mining power, `held` observed, 9,999 stacks; selftest 193/193, Python checks pass, noport parity 400k steps identical | **Decided** |
| B11 | Pickaxe/axe swings deal damage (`TOOL_DAMAGE`, default `FID_COMBAT&&FID_MINING`) | Keep on | Item.SetDefaults damage/useAnimation/kb (copper pick 4/23/2, iron 5/20/2, gold 6/20/2, axe 3/30/4.5); fid_test 102/102 incl. slime damage sets; EoC script 193/200 | **Decided** |
| B12 | Background walls + placement (`BG_WALLS`, default 1) | Keep on | Dirt Wall Backgrounds + Cave Walls + cabin walls; blocks need a neighbour or wall (no floating sky blocks), torches/platforms on walls; all three knobs: throughput 0.92x previous build-v10 | **Decided**; 1B re-run done (`V10_PPO_1B_2026_11.md`): default in band (generic 33.9%, shaped 34.3%); shaped with `BG_WALLS=0` 37.8%, so walls cost 3.6 pp [1.9, 4.9] (5/5 seeds); return to surface 0 with or without walls. Pillaring under walls fixed by held place: see B14 |
| B5 | Achievements / tiers / weights | 40 achievements, tiers 1/3/5/8, max 145 | Stepping stone "find a Demon Altar" fires (11–68 worlds); "hold 6 lenses" never, because ported policies never return to the surface at night (B2) | **Recommended** |
| B6 | Episode length / view | 10,000 steps; 11×9 view; no minimap | Minimap and LSTM gave no gain on v9 | **Decided** |
| B7 | Oracle achievability audit | Scripted planner per world under the step limit | Scripted climb and night probes already pass in every build (B2); full audit after B4 | **Blocked** on B4 |
| B13 | Simultaneous inputs (B4 follow-up): 15 appended move+use actions (`COMBO_ACTIONS`, option A) | Keep A; factored movement × use action space; drop | `docs/reports/COMBO_ACTIONS_2026_11.md`. PPO 192M at `4ef5afa`, 4 seeds per cell: weighted score generic 27.7 vs 30.0% without, shaped 28.5 vs 29.6% (lower in 7/8 pairs), deaths +15–21 pp, anvil half; combos ~22% of actions, spread evenly (not specialised); return to surface 0 in both arms at this budget. Scripted pillar (32 worlds): since `BG_WALLS` the one-input step makes pillaring nearly impossible in open caves (shaft 11/32 out, open air 0/32) while held jump + place down climbs 32/32; before the wall rules both reached 32/32, so this cannot explain the earlier B4 failures | **Recommended: drop A** (knob stays, default 0). Next: held-use semantics for the standalone `place` (first tick the cell takes the block), then a 1B pilot; factored action space only if that is not enough |
| B14 | Held place (`HELD_PLACE`, default 1 with `FID_PHYSICS`): standalone place actions hold the use over the 15-tick step (place at the start if legal, else at the first tick the cell takes the item, one per step); place mask = selected item stocked | Keep on; step-start only | `docs/reports/HELD_PLACE_AIM_2026_11.md`. Scripted climb (32 worlds), timed policy: shaft 11/32 -> 32/32 (27.7 steps), open air 0/32 -> 32/32 (80 steps, 4/row vs 0.6 without walls), random play open 16/32 -> 32/32; identical to the place combos; knob off token-identical; sim throughput ~1.0x | **Recommended**; 1B PPO pending (with B15, GPU 7) |
| B15 | Aimed attacks (`AIM_ATTACK`, default 1 with `FID_COMBAT`): `attack` = forward + 7 appended relative aims (ids 86-92); shortsword stab along the aim with the exact `CheckAABBvLineCollision` (forward reach 47 -> 42 px); swords/tools pick the side; player turns to the aim | Keep on; horizontal only | `docs/reports/HELD_PLACE_AIM_2026_11.md`; verified against decompiled AI_161 / Projectile.Colliding (type 938). Night probe (64 worlds, iron gear): deaths 61/64 horizontal -> 42 turn-and-attack -> 41 aimed, lenses 63 -> 129; wood gear 62 -> 60; shortsword 64 -> 62 (eye kills 1 -> 5 worlds). Fixtures: Demon Eye overhead / slime below a ledge hit only by the aimed stab | **Recommended**; 1B PPO pending (with B14, GPU 7) |

## C. Terraria-Lite evaluation and RL reference agents

| ID | Decision | Options | Evidence | Status |
|---|---|---|---|---|
| C1 | Headline metric | Weighted % of max (Craftax-style), plus tier rates, Crafter score, deaths | Craftax calibration reproduced (PPO 12.1% vs 11.9%; RNN 16.2% vs 15.3%) | **Decided** |
| C2 | Budgets | 1B standard; 4B extended | v10: 4B = 1B; v9: 4B ≤ 1B | **Recommended**: 1B only, 4B optional appendix |
| C3 | Seeds / statistics | 5 training seeds; IQM + bootstrap 95% CI; reserved test worlds once | Established practice in our studies | **Decided** |
| C4 | Reference agents | PPO generic ("bitter lesson") and PPO shaped ("maximally good"); behaviour cloning optional | v8, runs of 4B+ steps at γ ≥ 0.9998: shaped arm crafts the iron pickaxe in 4 of 11 runs (4 of 13 counting two frontier-surface runs), generic 0 of 9 | **Recommended** (BC: open) |
| C5 | Cost reporting | GPU-hours × stated rental rate (date-stamped) | Site currently assumes $2.50/MI350X-hour (placeholder) | **Open**: pick a public rate source |
| C6 | PPO training speed on v10 (shaped arm) | Exact host-side speedups; learner/algorithm changes only after a learning check | Time split was 12% simulator, 19% recipe potential, 21% sampling/H2D, 43% update; GPU busy only 15% / 35% of collection / update, so training is host-latency-bound, not network-bound (refines B3). Exact changes (reset prefetch in `capi.c`, `logf` skip, two-level potential memo, shaping overlapped with sampling and the C step) give 1.18× wall / 1.22× steps/s solo and 1.22× / 1.26× at 2 runs per GPU, with a bit-identical trainer fingerprint; `--minibatches 8` loses score at matched steps; `--envs 2048 --rollout 64` is 1.10× faster with no loss at 134M (2 seeds) (`docs/reports/TRAIN_SPEED_V10_2026_11.md`) | **Recommended**: merge `train-speed`; study `--envs 2048 --rollout 64` at 1B before adopting |

## D. LLM on Terraria-Lite

| ID | Decision | Options | Evidence | Status |
|---|---|---|---|---|
| D1 | Tracks | Plain actions + rules only; assisted (guide + macros) | Macros ~2× scores (v9 campaign) | **Recommended** |
| D2 | Harness on v10 | Update guide (v9 grid text is stale), check macros under real physics | Not run on v10 yet | **Blocked** on B2 |
| D3 | Models, worlds, cap rule | Same model list as A9; ≥3–5 worlds; full 10k-step episodes; cost-capped = censored | v9: Haiku ~$1/episode, Terra ~$5 | **Recommended** |
| D4 | Fair RL comparison | LLM plain vs PPO generic; LLM + guide vs PPO shaped; optional PPO with macros | Knowledge-track asymmetry | **Recommended** |

## E. Website

| ID | Decision | Options | Status |
|---|---|---|---|
| E1 | Art licensing | Keep official Terraria textures (site, replays, videos, player) | **Decided** (2026-11-10). Public release remains a separate question: Re-Logic owns the art; the repo itself still ships no game assets (textures load from a local install) |
| E2 | Official-track pages | Two leaderboards, milestone timelines, per-run video, harness card, failure gallery, terrariabench.com context, cost/latency | **Recommended** |
| E3 | Placeholders at launch | Only where no final data exists, visibly marked | **Recommended** |

## F. Programmatic tracks

Evidence: `TerrariaBench/experiments/programmatic-track-2026-11-10.md`.

| ID | Decision | Options | Evidence | Status |
|---|---|---|---|---|
| F1 | Scope of the first programmatic track | Official Terraria only (TerrariaBench-API); Terraria-Lite-API and the multiplayer team variant later | Built and tested on the official game first; Lite-API and teams are future work | **Decided** |
| F2 | API contract | `tb-api-1.0` (draft): reads limited to map-revealed or lit on-screen tiles and visible NPCs (position/type/health only); actions = control flags + cursor for N updates, real item use, `Main.CraftItem`, `ItemSlot.SwapEquip`, chest UI code; no teleport/spawn/tile edits; frozen per leaderboard | Live leakage tests pass (0 unrevealed cells or ores returned; NPC field whitelist); proxy refuses non-contract ops | **Recommended** (freeze at Gate 1) |
| F3 | Input attribution | Proxy journals every API action to `inputs.jsonl` (`actor: agent`, `dispatch: tb-api`); published scoring unchanged | Scripted runs score 4–7 published checkpoints with attribution vs 0 without (the transfer-PoC gap) | **Decided** |
| F4 | Pathfinder | Part of the frozen library (`tb/path.py`, published capability list): walk, step, jump ≤4 rows, falls, platforms, ropes, doors, surface swim, dig, pillar; never mines next to liquid | 30 offline tests; real game: walks, digs, pillars work; long climbs out of deep shafts and drowning in flooded caves were the main failures | **Recommended** |
| F5 | Sandbox | `python -I -S` + audit hook + `unshare -rn` (no network namespace) + rlimits; imports stdlib + `tb` + workspace; files workspace-only; default 60 s per program | 18 sandbox tests pass on macOS and Linux (network namespace on Linux) | **Decided** |
| F6 | Run audit | Scripted journal audit on every run (teleport, item provenance, craft provenance, attribution, forbidden ops, harness health); LLM auditor only with spare budget | All scripted proof runs audited; one false positive (coin conversion) fixed | **Decided** |
| F7 | Pilot models / budgets | Opus 5.5 (cheapest strong model with prompt caching); GPT-6 Astra is on the gateway at ~$8.5/M in, $34/M out (probed) | Opus 5.5 pilot reached a placed anvil in 23 game-min for $2.43 (≈$4/game-hour); total spend $2.48 of $10 | **Recommended**: Opus 5.5 for EoC runs; Astra after a re-fit price probe |
