# Decision register

Open decisions to finalize results for `WEBSITE_PLAN.md`. Process: decide at gates, then freeze, pre-register, run final experiments once, audit, publish.

Status: **Decided**, **Recommended** (awaiting your call), **Blocked** (needs evidence first), **Open**.
Last updated 2026-11-08 20:45 UTC.

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
| A5 | Stopping / continuation rule | Contract in prompt; forced tool call where the API allows; a reply without an action = `wait 1000 ms` + "No action was taken."; no early stop | BALROG-style default action. Pilot (landscape, running): Haiku thinking 5 no-action turns / 115 calls; Haiku forced 1 / 234 | **Recommended**, confirm after pilot |
| A6 | Haiku setting | Thinking medium (unforced) vs thinking off (forced) | Pilot running (a1/a2) | **Blocked** on pilot |
| A7 | Run length | 20 vs 40 game-minutes | Cheap models reached furnaces only at 40 min (Oct campaign); landscape tests 40 min for top 2 | **Blocked** on landscape |
| A8 | Worlds | 5 unseen worlds per cell (fixtures 401+ style) | World spread ≥ model spread among cheap models | **Recommended** |
| A9 | Models + reasoning | Haiku 5.5, GPT-5.6 Luna (low), GPT-5.6 Terra (low), Opus 5.5 (low) as strong reference; reasoning stated per row | Sonnet ≈ Haiku at 10–40× cost; Sol no better than Terra | **Recommended** |
| A10 | Agent systems | Separate table (e.g. Opus planner + Jev executor) | Best default-v1 run (pub 6) was the combo; mixing with single models would confuse rankings | **Recommended** |
| A11 | Headline score | Extended catalog (crafted/placed/looted separated) headline; published 13-checkpoint score as a comparability column | Published score inflated by loot (Luna 6 mostly chests) | **Recommended** |
| A12 | Final matrix + budget | ~4 models × 2 modes × 5 worlds + agent system; ~45–50 runs; ~$50–70 at 20 min (≈2× at 40) | 4–5 parallel game slots at 60 Hz verified; ~1 day of omarchy time | **Open** (after A5–A7) |

## B. Terraria-Lite environment

| ID | Decision | Options | Evidence | Status |
|---|---|---|---|---|
| B1 | Release version | v10 (v9 + real-behaviour ports at 15 ticks/action + tier-4 stepping stones) | v10 generic PPO 1B: 32.1–32.8%, shaped 33.6–34.9% (target band 25–35%); 4B no better (32.6–32.8) | **Recommended**, pending B4 night tuning |
| B2 | Return to surface / lens = 0 in every ported build | Bug vs learned behaviour | **Not a bug** (V10SurfaceBug, 2026-11-08): achievement, spawn and lens code identical across builds; scripted climbs and nights pass in every build; the noport policy transplanted into mining-/physics-only builds still returns 22–25/64. Cause: return is a seed-dependent all-or-nothing behaviour (v9: 5/10 seeds learn it at 1B; ported v10: 0/22 runs), and the enemy/combat ports make surface nights far deadlier (scripted iron-gear fighter: 61/64 deaths per night all-ports vs 12/64 noport; combat port: slimes hit every 3 steps because 40-tick i-frames replace the 8-step hurt cooldown) | **Resolved**: tune in B4 |
| B3 | Speed gate (D18) | Accept v10 at 0.52× v8 or optimize | Training is network-bound; v10 trains fine | **Recommended**: relax gate to 0.5×, note in docs |
| B4 | Night difficulty under the enemy/combat ports | `NIGHT_SPAWN_PERIOD` 60 → 120/180; lower Zombie/Demon Eye damage or longer contact immunity under `FID_MOBS`/`FID_COMBAT` | Scripted deaths/night (iron gear): 60 → 61/64, 90 → 49, 120 → 38, 180 → 20 (noport 12). Running: PPO 1B at 120 and 180 (2 seeds each); more seeds for mining-/physics-only (their zeros may be seed variance, ~20% chance) | **Blocked** on running PPO tests |
| B5 | Achievements / tiers / weights | 40 achievements, tiers 1/3/5/8, max 145 | Stepping stone "find a Demon Altar" fires (11–68 worlds); "hold 6 lenses" never, because ported policies never return to the surface at night (B2) | **Recommended** |
| B6 | Episode length / view | 10,000 steps; 11×9 view; no minimap | Minimap and LSTM gave no gain on v9 | **Decided** |
| B7 | Oracle achievability audit | Scripted planner per world under the step limit | Scripted climb and night probes already pass in every build (B2); full audit after B4 | **Blocked** on B4 |

## C. Terraria-Lite evaluation and RL reference agents

| ID | Decision | Options | Evidence | Status |
|---|---|---|---|---|
| C1 | Headline metric | Weighted % of max (Craftax-style), plus tier rates, Crafter score, deaths | Craftax calibration reproduced (PPO 12.1% vs 11.9%; RNN 16.2% vs 15.3%) | **Decided** |
| C2 | Budgets | 1B standard; 4B extended | v10: 4B = 1B; v9: 4B ≤ 1B | **Recommended**: 1B only, 4B optional appendix |
| C3 | Seeds / statistics | 5 training seeds; IQM + bootstrap 95% CI; reserved test worlds once | Established practice in our studies | **Decided** |
| C4 | Reference agents | PPO generic ("bitter lesson") and PPO shaped ("maximally good"); behaviour cloning optional | v8: shaped arm gets iron pickaxe in 5/15 runs, generic 0/9 | **Recommended** (BC: open) |
| C5 | Cost reporting | GPU-hours × stated rental rate (date-stamped) | Site currently assumes $2.50/MI350X-hour (placeholder) | **Open**: pick a public rate source |

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
| E1 | Art licensing | Original art / bring-your-own textures / abstract tiles | **Open**: blocks public replays and videos |
| E2 | Official-track pages | Two leaderboards, milestone timelines, per-run video, harness card, failure gallery, terrariabench.com context, cost/latency | **Recommended** |
| E3 | Placeholders at launch | Only where no final data exists, visibly marked | **Recommended** |
