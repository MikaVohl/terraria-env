# Landscape of the official Terraria LLM benchmark (profile default-v2), 2026-11-08

Question: with the protocol we intend to freeze (**default-v2** = the default-v1 game and interface + a no-action rule
instead of continuation messages and early stops), how do Haiku, Luna, Terra, Opus and Opus+Jev compare in real time and
paused mode, on three worlds (one unseen), and what changes at 40 game-minutes?

Compact records: [`results/landscape-2026-11-08/`](results/landscape-2026-11-08/). Raw runs (frames, requests,
responses, telemetry, `desktop.mp4`) stay on Omarchy under `~/Projects/TerrariaBench/runs/landscape-2026-11-08/<run>/`.

## Headline

1. **The no-action rule works:** 27 scored runs, 0 early stops; forced GPT calls gave 0 no-action turns in 1,701 calls.
   Unforced Haiku still "quits" near the end of the session (up to 338 no-action turns in one paused run), now measured
   instead of ending the run. Forcing Haiku by turning thinking off made it worse and 3× more expensive.
2. **Opus-based agents are the only ones that build** (bench placed 5/5, wooden armour 3/5); best run single Opus paused
   (extended 7 in 15.6 censored minutes); best real-time run Opus + Jev (published 6 / extended 5) at a third of single
   Opus' cost. Cheap models (Haiku, Luna, Terra) are indistinguishable at 2.0–2.7 extended facts per 20 minutes.
3. **Paused helps slow and strong models** (Opus: 7 vs 4 extended, 4 vs 17 deaths; Terra: 11 vs 41 deaths), not the
   cheap fast ones; **40 minutes added zero facts** for Haiku, Luna and Terra.
4. Spend: **$27.77** gateway (conservative) of $30, **$0.26** OpenRouter of $1; 3 h 32 min wall on 5 parallel slots.

## Definition: profile default-v2

| | default-v2 |
|---|---|
| Game | tModLoader 1.4.4.9, only the read-only TerrariaBenchObserver 0.7 journal; unmodified rules (normal PvE, hostile damage on); starter-item random prefixes reset to none; `DOTNET_PROCESSOR_COUNT=1` (lighting on the calling thread; fixes the paused-clock crash). |
| Worlds | fresh copies of small Classic worlds 32000401 (crimson), 32000402 (crimson), **32000403 (corruption, unseen by every earlier run)**. |
| Display | 1024×1024 window, zoom 100 %, UI 0.9, Color lighting, framed minimap, **Smart Cursor on** (one stock Left Ctrl press before the first screenshot). Enforced by the profile (other values are rejected). |
| Interface | one `act(actions)` tool (1–16 key/mouse/wait primitives, Appendix B; identical to default-v1); every act returns `{"dispatched_commands", "game_time_played", "image_follows"}` + a fresh JPEG q85 screenshot. |
| System prompt | goal + "The session lasts exactly N minutes of game time and cannot be ended early." + "Every reply must call the act tool." + Terraria's default key bindings (Appendix A). No hints, recipes, progress feedback or remaining time. Identical in both clock modes. |
| Context | all text and tool results (until 120k tokens, then oldest whole turns dropped); newest 8 screenshots (dropped 8 at a time). |
| **No-action rule** | Tool call forced where the API supports it: GPT-5.6 Responses `tool_choice: "required"`; Claude with thinking **off** `tool_choice: {"type": "any"}`; Claude with thinking on cannot be forced (API rejects it) and stays at the default. Any reply without a valid `act` call (no tool call, invalid arguments, unknown tool) is executed as `wait 1000 ms` — the game advances 1 s in **both** clock modes — and the next user turn is a fresh screenshot introduced by `No action was taken.` Counted per run (`no-action.jsonl`, `result.no_action_turns`). No continuation message, no 5-in-a-row stop, no invalid-call stop. |
| End | the game-time budget (game updates / 60 from the observer); a dollar / call cap → **censored**. Added during this campaign (after b08): the agent leaving the world via the game's Save & Exit ends the run (`agent_left_world`, remaining time forfeited, not censored); no game-time progress for 60 s of unfrozen time ends it as `game_clock_stalled` (censored). |
| Clock | `realtime`: the game never pauses. `paused`: the game process group is SIGSTOPped during every model call and resumed for actions, waits and screenshots. |
| Scoring | offline and hidden: published 13-checkpoint subset (terrariabench.com comparable) + extended catalog (19 facts: crafted / placed / looted, layers, ores, bars, furnace, anvil; `tools/extended_score.py`, cut at the budget). |
| Combination (Opus planner + Jev executor) | planner gets the default-v2 goal paragraph (with the session length) and the controls; it replies with JSON plans, not act calls. An executor turn without usable actions waits 1 s (game running) and counts as a no-action turn; no error-count stops. |

Code: `terrariabench/reference_live.py` (`DEFAULT_V2_ID`, `forced_tool_choice`, `no_action_turn`, `GameClock.left_world`), `terrariabench/combo.py`
(`--profile default-v2`), `terrariabench/gateway.py` (Haiku `--reasoning none` = thinking disabled; `tool_choice`),
`terrariabench/unified.py` (`tool_choice`), `prompts/default_v2.txt`, `tools/dg_job.py --profile/--campaign`,
`tools/campaign_table.py` (no-action column).

## Unpaid validation (scripted operator policy, 90 game-s, simulated 3 s latency)

| Check | Result |
|---|---|
| `dryrun-v2-realtime` (forced path, `--scripted-tool-choice required`, world 402) | stop `game_time_limit` at 90.0 game-s, not censored; 19 calls; the 2 scripted invalid act calls (steps 7, 16) were each executed as a 1 s wait: **exactly 60 game updates** (2340→2400, 4800→4860) and answered with a fresh screenshot + `No action was taken.`; `tool_choice: "required"` recorded |
| `dryrun-v2-paused` (unforced path, `--scripted-tool-choice auto`: every 4th reply text only, world 401) | 37 calls, **12 no-action turns** (9 text-only, 3 invalid) in 57 game-s, each a 1 s wait of 60 updates (one 120: heartbeat resolution) with the game thawed; no continuation message, no early stop. Ended at 67 game-s when the first queued paid run was started on the same display (operator slip, `game window missing or ambiguous`); the budget end in paused mode is the default-v1 code path and was then proven by every paid paused run below. |
| Request shapes (unsent) | Haiku `--reasoning none`: `thinking: disabled`, `tool_choice: {"type": "any"}`; Haiku medium / Opus low: thinking on, no tool_choice (provider default); Luna/Terra Responses: `tool_choice: "required"`. The default-v2 tool schema is byte-identical to default-v1's. |

## Results

Campaign: 31 run directories = 27 scored runs + 2 unscored harness/provider failures (b06, b08) + 2 unpaid dry runs, queue
15:29–19:02 Omarchy time (**3 h 32 min wall**), 5 parallel isolated slots, **every run's median 60.0 game updates/s**.
Pub. = published-subset score (possession-based, terrariabench.com comparable). Ext. = extended catalog facts (of 19).
Times are game mm:ss. Latency = median model latency (combination: planner / Jev). No-action = turns executed as a 1 s
wait. Wall = run wall time. Full milestone table: [`results-table.md`](results/landscape-2026-11-08/results-table.md).

| Run | Setup | Clock | World | Game min | Pub. | Ext. | Highlights (game mm:ss) | Crafted | Placed | Deaths | Depth | No-action | Calls | Latency (s) | Wall min | Hz | USD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a1-haiku-think-pa-w401 | Haiku (medium, unforced) | paused | 401 | 20.0 | 3 | 3 | wood 25 0:07, underground 1:42, iron/lead 10:08 | – | – | 1 | 80 | 69 | 310 | 2.4 | 34.9 | 60.0 | 0.46 |
| a2-haiku-forced-pa-w401 | Haiku (no thinking, forced) | paused | 401 | 16.1 (censored ($ cap)) | 0 | 1 | – | – | – | 16 | 24 | 1 | 819 | 2.1 | 50.1 | 60.0 | 1.47 |
| a3-luna-pa-w401 | Luna (low, forced) | paused | 401 | 20.0 | 1 | 3 | underground 4:07, copper/tin 2:12 | – | – | 3 | 56 | 0 | 183 | 6.2 | 41.8 | 60.0 | 0.22 |
| a4-terra-pa-w401 | Terra (low, forced) | paused | 401 | 20.0 | 3 | 4 | wood 25 3:28, underground 11:17, iron/lead 8:50, copper/tin 19:11 | – | – | 4 | 79 | 0 | 68 | 7.0 | 28.4 | 60.0 | 0.72 |
| b01-luna-rt-w401 | Luna (low, forced) | real time | 401 | 20.0 | 5 | 3 | wood 100 10:02, torches crafted 6:44, iron/lead 3:23 | Torch 3 | torch 1 | 7 | 24 | 0 | 90 | 6.4 | 20.0 | 60.0 | 0.09 |
| b02-terra-rt-w401 | Terra (low, forced) | real time | 401 | 20.0 | 3 | 2 | wood 25 16:48, copper/tin 10:07 | – | – | 14 | 35 | 0 | 77 | 7.0 | 20.0 | 60.0 | 0.79 |
| b03-luna-rt-w402 | Luna (low, forced) | real time | 402 | 20.0 | 0 | 2 | lens 14:04 | – | – | 13 | 26 | 0 | 89 | 6.1 | 20.0 | 60.0 | 0.08 |
| b04-luna-pa-w402 | Luna (low, forced) | paused | 402 | 20.0 | 3 | 2 | wood 25 4:25, iron/lead 9:54 | – | – | 11 | 40 | 0 | 236 | 6.8 | 48.7 | 60.0 | 0.30 |
| b05-luna-rt-w403 | Luna (low, forced) | real time | 403 | 20.0 | 3 | 2 | wood 25 13:04, iron/lead 4:18 | – | – | 17 | 18 | 0 | 95 | 6.4 | 20.2 | 60.0 | 0.09 |
| b06r-luna-pa-w403 | Luna (low, forced) | paused | 403 | 20.0 | 5 | 1 | wood 100 4:24, torch_10 18:25 (loot) | – | – | 14 | 24 | 0 | 218 | 7.0 | 48.7 | 60.0 | 0.28 |
| b07-terra-rt-w403 | Terra (low, forced) | real time | 403 | 20.1 | 1 | 2 | underground 7:57 | – | – | 15 | 181 | 0 | 65 | 6.5 | 20.1 | 60.0 | 0.68 |
| b08r-terra-pa-w403 | Terra (low, forced) | paused | 403 | 20.0 | 1 | 1 | – | – | – | 6 | 41 | 0 | 106 | 7.1 | 35.3 | 60.0 | 1.25 |
| b09-terra-rt-w402 | Terra (low, forced) | real time | 402 | 20.0 | 4 | 2 | wood 25 11:53, underground 3:41, torch_10 15:19 (loot) | Wood Platform 4 | – | 12 | 69 | 0 | 75 | 6.5 | 20.4 | 60.0 | 0.78 |
| b10-terra-pa-w402 | Terra (low, forced) | paused | 402 | 20.0 | 1 | 3 | underground 3:38, copper/tin 4:00 | Wood Platform 8 | – | 1 | 90 | 0 | 78 | 6.8 | 29.2 | 60.0 | 0.82 |
| b11-haiku-rt-w401 | Haiku (medium, unforced) | real time | 401 | 20.0 | 4 | 1 | wood 25 0:20, bench 0:34 | Work Bench 1 | – | 0 | 38 | 4 | 206 | 2.4 | 20.0 | 60.0 | 0.27 |
| b12-haiku-pa-w402 | Haiku (medium, unforced) | paused | 402 | 20.0 | 5 | 3 | wood 25 0:21, bench 0:24, underground 1:14, iron/lead 0:45, torch_10 15:46 (loot) | Work Bench 1 | – | 8 | 140 | 50 | 395 | 2.5 | 41.0 | 60.0 | 0.70 |
| b13-haiku-rt-w402 | Haiku (medium, unforced) | real time | 402 | 20.0 | 3 | 5 | bench 0:39, underground 5:39, cavern 10:11, iron/lead 8:13, copper/tin 7:04 | Work Bench 1 | – | 21 | 192 | 7 | 137 | 2.6 | 20.0 | 60.0 | 0.14 |
| b14-haiku-pa-w403 | Haiku (medium, unforced) | paused | 403 | 20.0 | 3 | 1 | bench 0:19 | Work Bench 1 | – | 9 | 48 | 338 | 571 | 2.6 | 50.0 | 60.0 | 1.18 |
| b15-haiku-rt-w403 | Haiku (medium, unforced) | real time | 403 | 20.0 | 4 | 1 | wood 25 1:26, bench 0:55 | Work Bench 1 | – | 11 | 38 | 32 | 195 | 2.6 | 20.0 | 60.0 | 0.24 |
| c1-opus-rt-w401 | Opus (low, unforced) | real time | 401 | 20.0 | 4 | 4 | wood 25 0:19, bench 0:54, bench placed 8:56, wood armour 9:25, underground 5:23 | Work Bench 1, Wood Greaves 1, Wood Breastplate 1 | bench 1 | 17 | 127 | 0 | 104 | 4.4 | 20.0 | 60.0 | 3.65 |
| c2-opus-pa-w401 | Opus (low, unforced) | paused | 401 | 15.6 (censored ($ cap)) | 5 | 7 | wood 25 0:07, bench 0:31, bench placed 0:31, torches crafted 4:20, underground 1:04, silver/gold-tier ore 13:58, iron/lead 6:55, copper/tin 7:03 | Work Bench 2, Torch 12 | bench 2, torch 13 | 4 | 183 | 0 | 136 | 4.0 | 25.4 | 60.0 | 4.95 |
| c3-combo-rt-w401 | Opus (low) + Jev | real time | 401 | 20.0 | 6 | 5 | wood 100 1:46, bench 2:19, bench placed 2:25, wood armour 2:52, underground 9:42, iron/lead 15:25, torch_10 13:59 (loot) | Work Bench 2, Wood Breastplate 1 | bench 2 | 8 | 54 | 1 | 665 | 4.5/0.3 | 20.0 | 60.0 | 1.25 |
| c4-combo-pa-w401 | Opus (low) + Jev | paused | 401 | 20.0 | 4 | 4 | wood 25 0:08, bench 2:25, bench placed 2:26, underground 5:22, iron/lead 11:55 | Work Bench 1, Wooden Sword 2 | bench 1, torch 2 | 7 | 154 | 0 | 886 | 5.0/0.3 | 31.5 | 60.0 | 1.99 |
| c5-combo-rt-w403 | Opus (low) + Jev | real time | 403 | 10.6 (censored ($ cap)) | 5 | 5 | wood 100 2:59, bench 1:56, bench placed 2:05, wood armour 7:21, underground 9:30, iron/lead 8:36 | Work Bench 1, Wooden Bow 1, Wood Breastplate 1 | bench 2 | 1 | 95 | 0 | 251 | 5.1/0.3 | 10.6 | 60.0 | 0.80 |
| d1-terra-pa-w401-40m | Terra (low, forced) | paused | 401 | 27.6 (censored ($ cap)) | 4 | 2 | wood 25 2:33, bench 14:31, bench placed 14:34 | Work Bench 1 | bench 1 | 12 | 34 | 0 | 144 | 7.4 | 46.7 | 60.0 | 2.07 |
| d2-haiku-rt-w401-40m | Haiku (medium, unforced) | real time | 401 | 40.0 | 4 | 4 | wood 25 0:30, bench 0:47, bench placed 0:53, silver/gold-tier ore 1:05, iron/lead 1:32 | Work Bench 4 | bench 2 | 6 | 35 | 296 | 447 | 2.7 | 40.0 | 60.0 | 0.85 |
| d3-luna-rt-w401-40m | Luna (low, forced) | real time | 401 | 40.0 | 5 | 2 | wood 100 7:40, lens 19:00, torch_10 15:02 (loot) | – | – | 33 | 24 | 0 | 177 | 6.6 | 40.3 | 60.0 | 0.21 |

### Per model × clock (20 game-minutes, worlds 401/402/403)

| Model | Clock | Runs (worlds) | Pub. (per run) | Ext. (per run) | Mean ext. | Bench placed | Deaths | No-action / calls | Latency (s) | USD / run | Censored |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Haiku (medium, unforced) | real time | 3 (401, 402, 403) | 4, 3, 4 | 1, 5, 1 | 2.3 | 0/3 | 0, 21, 11 | 43 / 538 | 2.4, 2.6, 2.6 | 0.27, 0.14, 0.24 | 0 |
| Haiku (medium, unforced) | paused | 3 (401, 402, 403) | 3, 5, 3 | 3, 3, 1 | 2.3 | 0/3 | 1, 8, 9 | 457 / 1276 | 2.4, 2.5, 2.6 | 0.46, 0.70, 1.18 | 0 |
| Haiku (no thinking, forced) | paused | 1 (401) | 0 | 1 | 1.0 | 0/1 | 16 | 1 / 819 | 2.1 | 1.47 | 1 |
| Luna (low, forced) | real time | 3 (401, 402, 403) | 5, 0, 3 | 3, 2, 2 | 2.3 | 0/3 | 7, 13, 17 | 0 / 274 | 6.4, 6.1, 6.4 | 0.09, 0.08, 0.09 | 0 |
| Luna (low, forced) | paused | 3 (401, 402, 403) | 1, 3, 5 | 3, 2, 1 | 2.0 | 0/3 | 3, 11, 14 | 0 / 637 | 6.2, 6.8, 7.0 | 0.22, 0.30, 0.28 | 0 |
| Terra (low, forced) | real time | 3 (401, 403, 402) | 3, 1, 4 | 2, 2, 2 | 2.0 | 0/3 | 14, 15, 12 | 0 / 217 | 7.0, 6.5, 6.5 | 0.79, 0.68, 0.78 | 0 |
| Terra (low, forced) | paused | 3 (401, 403, 402) | 3, 1, 1 | 4, 1, 3 | 2.7 | 0/3 | 4, 6, 1 | 0 / 252 | 7.0, 7.1, 6.8 | 0.72, 1.25, 0.82 | 0 |
| Opus (low, unforced) | real time | 1 (401) | 4 | 4 | 4.0 | 1/1 | 17 | 0 / 104 | 4.4 | 3.65 | 0 |
| Opus (low, unforced) | paused | 1 (401) | 5 | 7 | 7.0 | 1/1 | 4 | 0 / 136 | 4.0 | 4.95 | 1 |
| Opus (low) + Jev | real time | 2 (401, 403) | 6, 5 | 5, 5 | 5.0 | 2/2 | 8, 1 | 1 / 916 | 4.5/0.3, 5.1/0.3 | 1.25, 0.80 | 1 |
| Opus (low) + Jev | paused | 1 (401) | 4 | 4 | 4.0 | 1/1 | 7 | 0 / 886 | 5.0/0.3 | 1.99 | 0 |

Pilot cells (a1–a4) are the w401 paused cells of the matrix; the Haiku matrix uses thinking medium (unforced), chosen
from the pilot. The forced no-thinking Haiku row is the pilot alternative. Opus+Jev real time = c3 (20 min) and c5
(censored at 10.6 min). Opus paused = c2, censored at 15.6 min (its Ext. 7 is in 15.6 minutes).

### 20 vs 40 game-minutes (world 401, same model and clock)

| Model, clock | 20-min run: Pub. / Ext. | 40-min run: Pub. / Ext. | 40-min run, facts reached after 20:00 | 40-min notes |
|---|---|---|---|---|
| Haiku medium, real time | b11: 4 / 1 | d2: 4 / 4 | **0** (all four extended facts by 1:32) | 296 no-action turns, 256 of them after 20:00 ("I'm stopping here") |
| Luna low, real time | b01: 5 / 3 | d3: 5 / 2 | **0** | 33 deaths |
| Terra low, paused | a4: 3 / 4 | d1: 4 / 2 (censored at 27.6 min, $ cap) | **0** (bench placed 14:34) | 12 deaths |

## Verdicts

**No-action rule (adopt).** 27 scored runs, **zero early stops**: every run ended at the game-time budget except four
dollar-cap censorings (a2, c2, c5, d1 — all per-run cap sizing, none caused by the rule) and none by tool-less or invalid
replies. Forcing works where the API allows it: GPT-5.6 Responses `tool_choice: "required"` gave **0 no-action turns in
1,380 Luna/Terra calls** of the 20-minute matrix (and 321 more in the 40-minute runs); forced Haiku (thinking off, `{"type": "any"}`) 1 in 819. Unforced Claude: Opus 0 in 240 calls,
the combination 1 (an executor error) in 1,802; **Haiku medium 43 / 538 calls in real time but 457 / 1,276 paused**. Haiku's
no-action turns cluster at the end of the session: it reads `game_time_played`, knows the session length, and switches to
writing final summaries (a1: from ~16:00; b12: 40 of 50 after 17:30; b14 quit at 12:35 and produced 338 summaries;
d2: 256 after 20:00 of 40). The rule keeps such runs alive and bounded (1 game-s per reply) and makes the behaviour
measurable instead of ending the run, but it cannot make an unforced model act; in paused mode a quitting model costs
one call per game second (b14: $0.70 of $1.19). Forcing Haiku by switching thinking off is **not** a fix: a2 sent 1–2
tiny actions per call, made no progress (published 0) and burned 3× the dollars per game-minute until censored. So:
Claude thinking models stay unforced, and `no_action_turns` is reported as a first-class metric.

**Real time vs paused (model-specific; paused is the fairer capability track).**
- Opus (single): paused clearly better — extended 7 in 15.6 min vs 4 in 20 min; deaths 4 vs 17; bench placed at 0:31
  vs 8:56; torches crafted and placed only paused. Paused costs more per game-minute ($0.32 vs $0.18).
- Terra: paused slightly better (mean extended 2.7 vs 2.0) and far safer (11 vs 41 deaths over three worlds).
- Luna: no clear difference (2.0 vs 2.3; deaths 28 vs 37); paused costs 3× and 2.4× the wall time.
- Haiku: no difference in score (2.3 vs 2.3) but paused has 10× the no-action turns and 3× the cost: real time keeps
  Haiku acting.
- Opus + Jev: real time ≥ paused (c3 6/5 vs c4 4/4): the 0.3 s Jev executor makes real time workable.
- Real time mostly measures surviving with ~6–7 s of unseen game per screenshot (Luna/Terra 12–17 deaths per run in
  real time); paused removes latency from the score and is the better primary track for comparing models' play; real time
  is a useful second number for latency-aware agents.

**20 vs 40 game-minutes (20 is enough for cheap models).** In all three 40-minute runs every scored fact was reached
before 20:00; the second 20 minutes added nothing (Haiku stopped acting, Luna kept dying, Terra was censored after
finding its bench). Cheap models plateau within minutes; 40 minutes would only help models that progress past the
bench/torch stage (Opus), which costs ≈ $13 per paused 40-minute Opus run.

**Opus vs Opus + Jev.** The combination matches or beats single Opus in real time at a third of the cost (c3: published 6
/ extended 5, bench placed 2:25, wooden breastplate 2:52, 8 deaths, $1.25 vs c1: 4 / 4, 17 deaths, $3.65; c5 on the
unseen world: 5 / 5 in 10.6 censored minutes). Paused, single Opus is the strongest run of the campaign (c2: extended 7,
torches crafted and placed, silver/gold-tier ore) while the paused combination stays at 4 / 4. Single Opus is the
stronger player when latency is free; the combination is the cheaper and safer real-time agent.

**Models (20 min, 3 worlds per cell).** Cheap models are indistinguishable on the extended catalog (means 2.0–2.7) and
the world spread (Luna published 0–5) is as large as any model or clock effect; none placed a bench in 20 minutes
(Haiku crafted one in 5/6 runs within 0:19–0:55 and placed one only in the 40-minute run, at 0:53; Terra placed one at
14:34 in its 40-minute run). Only Opus-based agents placed a bench within 20 minutes (5/5 runs) or crafted wooden armour (3/5); torches were
crafted by Luna once (b01: 3, one placed) and by single Opus paused (c2: 12, 13 placed). Nobody crafted a furnace.

### Compared with default-v1 (same worlds 401/402, same models)

| | default-v1 | default-v2 |
|---|---|---|
| Early stops by the harness rule | 1 (Haiku paused stopped at 4:15 by 5 tool-less replies) | **0** |
| Haiku paused continuations / no-action per run | 96, 146 | 69, 50, 338 |
| Haiku real time | bench placed 2/2 (9:41, 13:07), extended 4, 4 | bench crafted 3/3, placed 0/3; extended 1, 5, 1 |
| Terra paused calls / USD per 20 min | 191–205 / $2.6–2.8 | 68–106 / $0.72–1.25 (longer action batches under `required`) |
| Opus + Jev | published 5–6 / extended 4 | published 4–6 / extended 4–5 |

Bench placement by Haiku in default-v1 real time (2/2) did not reproduce (0/3 in 20 min, 1 in the 40-min run): with
n = 1 per world, placement is a coin flip for Haiku, not a stable effect of either profile.

## Recommended final protocol and matrix

1. **Profile default-v2 as defined above**, plus the rule found here: the run ends when the agent leaves the world
   (game's Save & Exit; `agent_left_world`, remaining time forfeited, not censored) or game time stalls for 60 s of
   unfrozen time (`game_clock_stalled`, censored).
2. **Forced tool choice for every API that allows it with the model's normal reasoning** (GPT Responses `required`);
   Claude with thinking stays unforced; never switch thinking off just to force the call. Report `no_action_turns` and
   their timing next to the score.
3. **Primary track: paused, 20 game-minutes, 3 worlds** (401, 402, 403). Secondary: real time, same worlds. 40 minutes only
   for models that still gain facts at 20:00.
4. **Per-run dollar caps = expected spend + 2 per-call reservations** (Opus reserves $1.05 per call; three caps here were
   too tight). Expected spend per 20-minute run: Haiku $0.25 (rt) / $0.80 (pa); Luna $0.09 / $0.27; Terra $0.75 / $0.93;
   Opus $3.65 / ≈$6.35; Opus+Jev $1.25 / $2.00.
5. Matrix cost (3 worlds, both clocks, 20 min): Haiku ≈ $3.2, Luna ≈ $1.1, Terra ≈ $5.0 — the three cheap models ≈ **$9.3**;
   Opus ≈ $30; Opus+Jev ≈ $9.8. Full set ≈ **$49**; paused-only primary track ≈ $6 (cheap three) + $19 (Opus) + $6
   (Opus+Jev) ≈ $31. Wall time with 5 slots: ≈ 50 min per paused wave.

## Per-run insights (appended as runs finished)

- **b01-luna-rt-w401** (Luna low, real time, forced): full 20:00; published 5 / extended 3; iron/lead ore 3:23, **torches crafted 6:44** (3, one placed), wood 100 at 10:02, torch_10 18:52; 7 deaths (default-v1 Luna real time: 14 and 18), 24 tiles deep; 90 calls, 0 no-action turns, 6.4 s latency, 60.0 Hz, $0.09.
- **a4-terra-pa-w401** (pilot; Terra low, paused, forced): full 20:00; published 3 / extended 4; wood 25 at 3:28, iron/lead ore 8:50, underground 11:17, copper/tin 19:11; nothing crafted; 4 deaths, 79 tiles deep; **68 calls only** (default-v1 Terra paused: 191 calls) — long action batches, ~18 game-s per call; 0 no-action turns; $0.72 (default-v1: $2.59).
- **a1-haiku-think-pa-w401** (pilot; Haiku thinking medium, paused, **unforced**): full 20:00, no early stop; published 3 / extended 3; wood 25 at 0:07, underground 1:42, iron/lead 10:08; nothing crafted; 1 death (drowned in its own shaft), 80 tiles; **69 no-action turns in 310 calls (22 %)**: 1 invalid call early, scattered text-only replies after 3:27, then from ~16:00 a wrap-up streak (every other reply a "the session is nearly finished … the Wall of Flesh was never reached" summary). Each cost 1 game-s (≈ 69 s of the 1200). 2.4 s latency, $0.46. Default-v1 continuations on the same model/mode: 96–146 per run, one run ended at 4:15.
- **b02-terra-rt-w401** (Terra low, real time, forced): full 20:00; published 3 / extended 2; wood 10 at 2:49 but wood 25 only at 16:48, copper/tin 10:07; nothing crafted; **14 deaths**, 35 tiles; 77 calls, 0 no-action turns, 7.0 s latency, $0.79. Same picture as default-v1 Terra real time (11 deaths, extended 2): ~7 s of unseen game per screenshot is lethal at night.
- **a3-luna-pa-w401** (pilot; Luna low, paused, forced): full 20:00; published 1 / extended 3; only 1–9 wood (0:07), copper/tin 2:12, underground 4:07, 56 tiles; nothing crafted; 3 deaths; 183 calls, 0 no-action turns, 6.2 s latency, 41.8 wall-min, $0.22. Dug instead of gathering wood: on this world the paused Luna went down, the real-time Luna (b01) chopped and crafted torches.
- **b03-luna-rt-w402** (Luna low, real time, forced): full 20:00; **published 0** / extended 2 (gel 1:19, lens 14:04); never held wood; 13 deaths, 26 tiles; 89 calls, 0 no-action, $0.08. Default-v1 Luna real time on w402: 18 deaths, published 4 — real-time Luna stays deaths-dominated.
- **a2-haiku-forced-pa-w401** (pilot; Haiku thinking **off**, paused, **forced** `tool_choice: any`): **censored by its $1.50 cap at 16:07**; published 0 / extended 1 (gel 1:24); never held wood; 16 deaths, 24 tiles; **1 no-action turn (an invalid call) in 819 calls** — the forced call works, but without thinking Haiku sends 1–2 tiny actions per call (2.1 s latency, 1281 inputs), so it pays 3× Haiku-medium's dollars per game-minute ($0.09 vs $0.023) for far less progress. Verdict for the matrix: **Haiku = thinking medium, unforced**.
- **b06-luna-pa-w403** (harness/provider failure, not scored): the Responses endpoint timed out 4× on the same request (90 s each, game frozen) at 0:21 game time and the retry policy ended the run (`ProviderError … TimeoutError`, $0.007 reported + $0.18 uncertain, counted). Re-run as b06r.
- **b05-luna-rt-w403** (Luna low, real time, forced, unseen corruption world): full 20:00; published 3 / extended 2; iron/lead ore 4:18, wood only at 6:31 (25 at 13:04); **17 deaths**, 18 tiles; 95 calls, 0 no-action, $0.09.
- **b07-terra-rt-w403** (Terra low, real time, forced, unseen world): full 20:00; published 1 / extended 2; underground 7:57 and **181 tiles deep** (deepest so far), first wood only at 10:27; 15 deaths; "crafted" 100 copper coins = automatic coin stacking, not a craft; 65 calls, 0 no-action, $0.68.
- **b08-terra-pa-w403** (harness gap found, not scored): at 1:41 game time Terra opened the menu and used the game's own **Save & Exit**, then re-entered the world (three times). Re-entry no longer crashes (default-v1 bug 2), but the observer journal ends when the player leaves the world, so game time stopped advancing and the run kept calling the model with the clock frozen at 1:41 (97 calls, **$0.96 lost**) until stopped by hand. Fix (from 16:44, runs started later): default-v2 ends the run when the journal reports the player left the world (`agent_left_world`: the agent's own action, remaining time forfeited, not censored) or when game time makes no progress for 60 s of unfrozen time (`game_clock_stalled`, censored); the combination checks the former. Re-run as b08r.
- **b09-terra-rt-w402** (Terra low, real time, forced): full 20:00; published 4 / extended 2; underground 3:41, wood 25 at 11:53, **torch_10 at 15:19 by loot** (no torch crafted), 4 platforms crafted; 12 deaths; 75 calls, 0 no-action, $0.78.
- **b04-luna-pa-w402** (Luna low, paused, forced): full 20:00; published 3 / extended 2; wood 25 at 4:25, iron/lead 9:54; nothing crafted; 11 deaths (paused does not protect against nightfall), 40 tiles; 236 calls, 0 no-action, 48.7 wall-min, $0.30. Default-v1 Luna paused on w402 was the lucky chest run (published 6).
- **b11-haiku-rt-w401** (Haiku medium, real time, unforced): full 20:00; published 4 / extended 1; bench **crafted 0:34** but never placed; 0 deaths, 38 tiles; **4 no-action turns in 206 calls** (default-v1 Haiku real time: 34 continuations); 2.4 s latency, $0.27. Default-v1 placed its bench on this world at 9:41.
- **b10-terra-pa-w402** (Terra low, paused, forced): full 20:00; published 1 / extended 3; underground 3:38, copper/tin 4:00, 90 tiles; 8 platforms crafted (from its few wood), never 10 wood; 1 death; 78 calls, 0 no-action, 29.2 wall-min, $0.82.
- **b06r-luna-pa-w403** (re-run; Luna low, paused, forced): full 20:00; published 5 / extended 1; **wood 100 at 4:24** (fastest wood of the campaign), torch_10 at 18:25 by loot; nothing crafted; 14 deaths on the corruption world even paused; 218 calls, 0 no-action, $0.28.
- **b13-haiku-rt-w402** (Haiku medium, real time, unforced): full 20:00; published 3 / **extended 5**; bench crafted 0:39 (not placed), underground 5:39, copper/tin 7:04, iron/lead 8:13, **cavern layer 10:11**, 192 tiles; 21 deaths (dug into the caverns at night); 7 no-action turns in 137 calls; $0.14.
- **b12-haiku-pa-w402** (Haiku medium, paused, unforced): full 20:00; published 5 / extended 3; iron/lead 0:45, underground 1:14, bench crafted 0:24 (not placed), torch_10 15:46 by loot, 140 tiles; 8 deaths; **50 no-action turns in 395 calls, 40 of them after 17:30** — the same end-of-session wrap-up as a1 (paused Haiku reads `game_time_played`, knows the session length and starts writing summaries); $0.70.
- **b08r-terra-pa-w403** (re-run; Terra low, paused, forced): full 20:00, no menu exits this time; **published 1 / extended 1** (gel; a few wood at 2:13); 6 deaths, 41 tiles; 106 calls, 0 no-action, $1.25. Terra's weakest run: the unseen corruption world is hard for it in both clocks.
- **b15-haiku-rt-w403** (Haiku medium, real time, unforced): full 20:00; published 4 / extended 1; bench crafted 0:55 (not placed), wood 25 at 1:26; 11 deaths, 38 tiles; 32 no-action turns (+2 invalid) in 195 calls; $0.24.
- **c1-opus-rt-w401** (Opus 5.5 low, single model, real time, unforced): full 20:00; published 4 / extended 4; bench crafted 0:54 and **placed 8:56**, **wooden breastplate + greaves 9:25**, underground 5:23, 127 tiles; 17 deaths; 104 calls, **0 no-action**, 4.4 s latency, **$3.65** (≈ 15× Haiku).
- **c2-opus-pa-w401** (Opus 5.5 low, single model, paused, unforced): **censored by its $6 cap at 15:35** (reported $4.96 + one ~$1.05 per-call reservation); still the **best run of the campaign: published 5 / extended 7** — bench crafted and **placed 0:31**, underground 1:04, **12 torches crafted 4:20 and 13 placed**, iron/lead 6:55, copper/tin 7:03, **silver/gold-tier ore 13:58**, 183 tiles; 4 deaths; 136 calls, 0 no-action, 4.0 s latency. Paused vs real time for Opus on the same world: extended 7 in 15.6 min vs 4 in 20 min, 4 vs 17 deaths.
- **c3-combo-rt-w401** (Opus low planner + Jev executor, real time): full 20:00; **published 6 / extended 5**; wood 100 at 1:46, bench crafted 2:19 and **placed 2:25**, **wooden breastplate 2:52**, underground 9:42, torch_10 13:59 (loot), iron/lead 15:25; 8 deaths (single Opus real time: 17); 59 planner + 606 Jev calls (4.5 s / 0.29 s), 1 executor no-action turn; **$1.25 total** — a third of single Opus real time for a better result.
- **b14-haiku-pa-w403** (Haiku medium, paused, unforced): full 20:00 by rule, but **338 no-action turns in 571 calls**: at 12:35 Haiku declared "I'm not taking any further actions" and repeated a final-state summary for the rest of the session (302 of the no-action turns after 10:00); each cost 1 game-s, so the remaining 7.5 minutes passed as ~300 one-second waits ($0.70 of the run's $1.19). Before that: bench crafted 0:19 (not placed), wood 10 at 0:17; published 3 / extended 1; 9 deaths. The rule keeps the run alive and bounded, but cannot make an unforced model act.
- **c4-combo-pa-w401** (Opus low planner + Jev executor, paused): full 20:00; published 4 / extended 4; bench crafted 2:25 and **placed 2:26**, underground 5:22, iron/lead 11:55, 154 tiles, 2 wooden swords; 7 deaths; 94 planner + 792 Jev calls, 0 no-action; $1.86 planner + $0.13 Jev. Here the paused combination did *not* beat real time (c3: published 6 / extended 5) — the opposite of single Opus.
- **d2-haiku-rt-w401-40m** (Haiku medium, real time, 40 game-min): full 40:00; published 4 / extended 4 — **all of it in the first 1:32** (bench crafted 0:47 and **placed 0:53** — Haiku's only placement in default-v2 —, silver/gold-tier ore 1:05, iron/lead 1:32), 4 benches crafted, 2 placed; then nothing new for 38 minutes; 6 deaths; **296 no-action turns in 447 calls, 256 of them after 20:00** ("I'm stopping here … about 32 minutes of the 40-minute session played"); $0.85. The second 20 minutes added no fact.
- **d1-terra-pa-w401-40m** (Terra low, paused, 40 game-min planned): **censored by its $2.50 cap at 27:36** (cap lowered from $3.50 to fit the campaign budget); published 4 / extended 2; wood 25 at 2:33, bench crafted 14:31 and **placed 14:34** (Terra's only placement); 12 deaths, 34 tiles; 144 calls, 0 no-action, $2.07 reported. Same world and setting as a4 (20 min: extended 4, no bench): a different path, not more progress per minute.
- **c5-combo-rt-w403** (Opus low planner + Jev, real time, unseen world; added at the end with the remaining budget): **censored at 10:36** — its $1.80 planner cap left room for only $0.77 of spend because every Opus call reserves $1.05 (operator sizing error); in 10.6 minutes published 5 / extended 5: wood 100 at 2:59, bench crafted 1:56 and **placed 2:05**, **wooden breastplate 7:21**, iron/lead 8:36, underground 9:30; 1 death; 40 planner + 211 Jev calls; $0.80.
- **d3-luna-rt-w401-40m** (Luna low, real time, 40 game-min): full 40:00; published 5 / extended 2; wood 100 at 7:40, torch_10 15:02 (loot), lens 19:00; **33 deaths**, 24 tiles; 177 calls, 0 no-action, $0.21. Every fact was reached before 20:00 (b01 on the same world/setting: extended 3).

## Spend

Ledger: [`ledger.json`](results/landscape-2026-11-08/ledger.json) (`tools/campaign_ledger.py`: per run from its accounting;
GPT cost = gateway `X-Token-Usage-Cost`, Claude at list price; uncertain = sent attempts whose charge is unknown, counted
in full). Dry runs and the request-shape check were unpaid.

| Route | Cap | Reported | Uncertain | Conservative |
|---|---:|---:|---:|---:|
| AMD gateway (Anthropic + Unified) | $30.00 | **$27.04** | $0.73 | **$27.77** |
| OpenRouter (Jev) | $1.00 | **$0.26** | $0.00 | **$0.26** |

Lost to harness/provider failures: b08 (Save & Exit stall) $0.96 + $0.46 uncertain, b06 (provider timeouts) $0.01 + $0.18
uncertain. The queue (`tools/parallel_queue.py`) started a job only if spend + all running caps + its own cap stayed within
the budget; two caps were lowered to fit (d1 $3.50 → $2.50, d3 $0.80 → $0.35).

## Limitations

- n = 1 per model × clock × world; three worlds per cell. World spread is large (Luna published 0–5); differences of
  ±1 extended fact are noise.
- Four censored runs (a2, c2, c5, d1) stopped at their dollar caps; c2 (Opus paused, best run) and c5 (Opus+Jev on the
  unseen world) have 15.6 and 10.6 game-minutes. Opus single and the paused combination were run on one world only.
- The world-exit/stall rule was added mid-campaign (16:44) after b08; runs started before it could not have used it
  (none left the world).
- The paused dry run was cut at 67 game-s by an operator slot clash; its budget end was shown by every paid paused run.
- GPT models use Responses `reasoning.effort: low`; Haiku a fixed 8k thinking budget; Opus adaptive thinking (low) —
  provider-side reasoning differs.
- Game date not pinned; normal PvE nights dominate deaths in both clocks.

## Best-run videos (Omarchy)

`~/Projects/TerrariaBench/runs/landscape-2026-11-08/<run>/desktop.mp4` (5 fps recording of the run's isolated display):
- `c2-opus-pa-w401/desktop.mp4` — best run (extended 7: bench placed 0:31, torches crafted and placed, silver/gold-tier ore)
- `c3-combo-rt-w401/desktop.mp4` — best real-time run (published 6 / extended 5, wooden breastplate 2:52)
- `c5-combo-rt-w403/desktop.mp4` — unseen world, Opus+Jev (bench placed 2:05)
- `b13-haiku-rt-w402/desktop.mp4` — best cheap run (extended 5, cavern layer 10:11)
- `d2-haiku-rt-w401-40m/desktop.mp4` — Haiku places its bench at 0:53, then stops acting (no-action loop)
- `b01-luna-rt-w401/desktop.mp4` — best GPT cheap run (published 5, torches crafted)

## Appendix A: system prompt (default-v2, 20-minute session, identical in both clock modes)

```text
You are playing Terraria on a fresh character in a fresh small Classic world. The game is unmodified: enemies,
damage, day and night follow the normal game rules. Your goal is to progress as far as possible toward defeating the
Wall of Flesh. The session lasts exactly 20 minutes of game time and cannot be ended early.

You see the game through 1024x1024 screenshots and control it with the act tool, which sends ordinary keyboard and
mouse input to the game window and then returns a new screenshot and the game time played so far. Every reply must
call the act tool.

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

First user turn: `Current game screenshot:` + the opening screenshot. After every act: the tool result (below) + a user
turn `Current game screenshot:` + the new screenshot. After a reply without a valid act call: the 1 s wait, then a user
turn `No action was taken.` / `Current game screenshot:` + the new screenshot (an invalid call also gets its tool result
`{"error": ..., "nothing_dispatched": true}`).

## Appendix B: tool schema (identical to default-v1)

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

Act result (tool message): `{"dispatched_commands": n, "game_time_played": "m:ss", "image_follows": true}` followed by the
new screenshot (JPEG q85, 1024×1024). Request fields: GPT-5.6 Responses `tool_choice: "required"`,
`reasoning: {"effort": "low"}`; Claude Haiku `thinking: {"type": "enabled", "budget_tokens": 8192}`, no tool_choice
(pilot alternative: `thinking: {"type": "disabled"}`, `tool_choice: {"type": "any"}`); Claude Opus
`thinking: {"type": "adaptive"}`, `output_config: {"effort": "low"}`, no tool_choice.

## Appendix C: combination planner system prompt (default-v2)

```text
You are the PLANNER of a two-part agent playing Terraria. A fast EXECUTOR acts every few seconds from the newest screenshot and pursues the objective you give it with movement, jumping, mining, chopping, attacking and placing blocks. It cannot open menus or craft: you do inventory and crafting yourself with ui_actions (keyboard and mouse actions, executed while the executor pauses).

You are playing Terraria on a fresh character in a fresh small Classic world. The game is unmodified: enemies,
damage, day and night follow the normal game rules. Your goal is to progress as far as possible toward defeating the
Wall of Flesh. The session lasts exactly 20 minutes of game time and cannot be ended early.

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

Planner user turn: JSON with `task` (the default-v2 goal paragraph), `your_notes`, `current_objective`,
`executor_recent_actions`, `game_time_played`, plus the newest two screenshots. Jev executor (OpenRouter decisions,
catalog moves built from the same primitives) as in default-v1.
