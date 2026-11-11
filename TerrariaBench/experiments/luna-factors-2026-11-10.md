# What gives a cheap LLM agent the best chance in real Terraria? Luna factor study, 2026-11-10/11

Question: on the default-v2 protocol (unmodified Terraria, normal enemies, one `act` tool, screenshot after every act,
goal + default controls, no-action rule, leave-world ends the run), which harness, clock, enemy and reasoning
settings change how far a cheap model gets — and should any of them change what "TerrariaBench Official v1" ships?

**Model.** The requested "GPT-6.1 Luna" does not exist on the AMD gateway (Unified route `/models` lists Luna only
as `gpt-6-luna` and `gpt-5.6-luna`; `gpt-6.1-luna` returns "Deployment not found" on both Responses and
ChatCompletions). With Main's approval every Luna run here uses **`gpt-6-luna`, deployment
`gpt-6-luna-2026-09-22`** (Responses reports `dvue-aoai-006-gpt-6-luna`; recorded in every manifest as
`model.deployment`, returned name per response in `response-*.json`). Called "Luna6" below. Landscape baselines used
`gpt-5.6-luna`; three matched gpt-5.6-luna runs are included. After the start the user also allowed **Claude Haiku
5.5** (gateway Anthropic route) to check whether factor effects generalise across vendors, and **TypeSafe Jev 1.14**
(OpenRouter) as a fast executor under a Luna6 planner (labelled as an agent system). Reasoning effort ≤ high
throughout (Luna6: `none`/`low`/`medium`/`high` — `minimal` is rejected by this deployment; Haiku: the two existing
gateway shapes, thinking off and medium = 8k budget).

**93 scored runs** (+2 unpaid dry runs, 2 paid smokes): 55 screening runs (17 Luna6 cells + 1 gpt-5.6-luna cell × worlds 401/402/403, plus one
baseline re-run; 10 game-min), 14 Haiku runs (7 cells × 401/402, 10 game-min), 4 Luna6+Jev runs, 20 Luna6 confirmation runs at the
benchmark length (20 game-min, worlds 401–404). Spend: gateway **$8.14 reported, $9.57 conservative** of the $15 cap;
OpenRouter $0.25 of $1. Compact records: [`results/luna-factors-2026-11-10/`](results/luna-factors-2026-11-10/)
(`summary.json`, `results-table.md`, `ledger.json`, `jobs/` = every queued command + `queue.log`, `runs/<run>/` =
manifest, result, extended score, clock log, evidence timeline + contact sheet). Raw runs (frames, requests/responses,
telemetry, **`desktop.mp4`**) stay on Omarchy under `~/Projects/TerrariaBench/runs/luna-factors-2026-11-10/<run>/`.

**n = 2–4 per cell: signals, not rankings.** World spread is large; ±1 extended fact between cells is noise.

## Headline

1. **Reasoning effort is the only factor with a large, monotone and cross-vendor effect.** Luna6 at 10 game-min,
   paused (n = 3–4): effort none / low / medium / high → published 1.0 / 1.5 / 3.0 / 4.3, extended 1.3 / 1.0 / 2.3 /
   2.7, wood 25 in 1/3, 2/4, 3/3, 3/3 runs. At the benchmark length (20 game-min) **high effort crafted something in
   9 of 13 runs and placed a work bench in 6 of 13** (earliest 0:38); **low effort crafted nothing and placed nothing in
   7 of 7** (both clocks). This is the first time a Luna-class model placed a station in any of our campaigns
   (default-v2 gpt-5.6-luna: 0 of 7). Haiku shows the same direction: thinking off (forced) published 0 / extended 1.0 vs
   medium 4.0 / 4.0.
2. **No harness factor beat the default-v2 harness at low effort.** Knowledge card, crafted/placed feedback, a notes
   field, 1 screenshot in context, 30k history and split tools all stayed within noise (extended 1.0–2.3 vs 1.0;
   nobody crafted). Four factors look **harmful to basic motor play** (wood 25 in 0/12 runs vs 2/4 for the baseline):
   512-px screenshots, normalized 0–1000 coordinates, at most 4 actions per call, and dropping the controls list.
   Split key/mouse/wait tools cost 4× the calls and 2.4× the wall time for nothing.
3. **On top of high effort, the knowledge card (recipes/stations facts) is the best single addition seen** — bench
   placed 3/3 (0:42, 4:21, 7:35) vs 2/3 without, extended 3.3 vs 3.0 — but it did nothing at low effort (1.0 vs 1.0)
   and nothing for Haiku (2.5 vs 4.0). Weak evidence: a candidate *declared* knowledge variant, not a default.
4. **Clock.** At high effort, paused ≥ real time (extended 3.0 vs 2.3; bench placed 2/3 vs 1/3); a bounded-staleness
   real-time clock ("game runs the first 2 s of every model call, then freezes") reached 2.7 extended and crafted
   torches in 2/3, but placed no bench and costs 2.3× wall time — no reason to ship it. At low effort the clocks tie
   on score; real time triples the deaths at 20 min (15.3 vs 5.7).
5. **Enemies are not what stops Luna or Haiku in 10 minutes.** Hostile damage off (diagnostic) lowered deaths (1.0
   vs 1.8) but not progress (Luna extended 1.7 vs 1.0, no crafting; Haiku 2.5 vs 4.0). Over 20 minutes deaths climb
   to 9–17 per run for high-effort Luna (nights), so normal PvE does cost late-session time.
6. **A harness hazard: accidental world exit.** 4 of 72 single-model Luna6 runs ended by `agent_left_world` (2.1–15.6 game-min).
   Frames show the mechanism: the agent opens the game's Settings menu (Settings button of the open inventory) and,
   aiming for *Close Menu*, clicks *Save & Exit* 38 px lower. Under default-v2 that forfeits the rest of the session.
7. **Cost is not a constraint for Luna6:** $0.002–0.004 per game-minute at low effort, $0.006–0.012 at high (≈ $0.12–
   0.24 per 20-min paused run), 2.5× cheaper per call than gpt-5.6-luna (latency 4.6 s vs 7.1 s at low). Haiku
   medium paused costs 10× more per game-minute ($0.039) because of its no-action replies (80 per 10 min).
8. **Luna6 planner + Jev executor**: wood fast (published 4 in 4/4), nothing crafted, depth ≤ 11; same wall as the
   earlier Luna/Terra + Jev runs.

## Experiment design

Base condition: **default-v2 unchanged** (landscape 2026-11-08 definition: 1024² window, Smart Cursor on, JPEG q85
after every act, newest 8–15 screenshots, 120k-token history, `tool_choice: "required"` for Responses, 1 s wait on a
reply without a valid act, leave-world ends the run), Luna6 effort **low** (the landscape setting), **paused** clock
(the recommended primary track), **10 game-minutes**, worlds 401/402/403 (default-v07 fixtures, fresh copy per run).
One factor changed per cell. Phase B repeats the cheapest-to-interpret factors on Haiku (default-v2 Haiku setting:
thinking medium, unforced). Phase C runs the most promising factor (effort) and its best companion at the benchmark
length (20 game-min) in both clocks on three worlds, plus a fourth world (404) for high vs low paused.

Declared factors (new, `terrariabench/reference_live.py`; only on default-v2; recorded as `manifest["factors"]` with
`factor_defaults`; with no factor flag the tool schema and prompt are byte-identical to default-v2 — checked against a
landscape manifest):

| Flag | Factor | Implementation |
|---|---|---|
| `--reasoning none/low/medium/high` | reasoning effort | Responses `reasoning.effort` (existing) |
| `--clock realtime/paused` | clock | existing |
| `--think-grace 2` | bounded-staleness real time | real-time clock, but a timer freezes the game process group 2 s into each model call until the reply (screenshot age ≤ 2 game-s; `clock = realtime-grace-2s`) |
| `--hostile-damage off` | enemies (diagnostic) | observer 0.7 switch (hostiles spawn and drop, cannot hit); prompt sentence states it |
| `--knowledge-card` | declared knowledge | appends [`prompts/knowledge_card_v1.txt`](../prompts/knowledge_card_v1.txt): factual recipes/stations (bench, torch, furnace, bars, anvil, placement), no strategy |
| `--progress-feedback` | checkpoint-style feedback | every act result carries `crafted_and_placed` (observer journal: crafted items, placed tiles) |
| `--notes` | persistent memory | optional `notes` string in `act`; the latest notes are prefixed to every screenshot turn |
| `--keep-images 1 --image-block 1` | screenshots kept | existing context policy |
| `--max-context-tokens 30000` | history length | existing trimming (oldest whole turns) |
| `--obs-size 512` | screenshot size | JPEG downscaled to 512²; coordinates in that space, mapped to the window |
| `--coords normalized` | coordinate convention | x, y in 0–1000, mapped to window pixels |
| `--max-actions 4` | batch size limit | schema `maxItems` + check |
| `--controls-card off` | no key-bindings list | prompt cut before "Controls" |
| `--tool-set split` | explicit tools | `key(keys, ms)`, `mouse(x, y, button?, ms?)`, `wait(ms)`; several calls per reply, one screenshot after the last |

Not run: reduced spawn rates (needs an observer-mod change and rebuild; hostile damage off is the cheaper diagnostic),
slowed game speed, PNG vs JPEG, game length > 20 min (the landscape showed 40 min adds nothing for low-effort cheap
models), medium effort at 20 min (withdrawn for wall time; 10-min data exist).

Infrastructure: isolated rootful Xwayland slots + `tools/parallel_queue.py` (spend-gated, per-run `desktop.mp4`,
evidence/extended score/clock check after each run), 5 slots, then 4 + one hand-run extra slot while another agent
(TerraBotAPI) borrowed `:15`. A workshop mod update (SerousCommonLib 1.0.6.2 → 1.0.7) stalled every launch on an "Updated
Mods" dialog; runs use copies `runs/fixtures/lf-v07-3200040{1..4}` with only that `LastLaunchedMods.txt` line bumped
(originals untouched). Unpaid dry runs (scripted operator policy, 60 game-s): grace clock froze 22 times, **0
heartbeats while frozen**, 60.0 Hz while running, screenshot age 1.02 game-s for a 1 s grace; paused + hostile-off +
1 image + no controls: 36 freezes, 0 heartbeats while frozen, 60.0 Hz. Paid smokes ($0.003): split tools and notes +
normalized + feedback worked as specified.

## Results

Pub. = published 13-checkpoint subset (possession-based). Ext. = extended catalog facts (of 19). wood 25 / any craft /
torch crafted / bench placed = runs reaching it. Depth = max tiles below spawn. Wall / game-min = wall minutes per game
minute. USD = gateway header cost (combination: planner gateway + Jev OpenRouter).

### Phase A — Luna6 screening (10 game-min, paused unless stated, worlds 401–403)

| Cell | Setup | n | Pub. mean | Ext. mean | wood 25 | any craft | torch crafted | bench placed | Deaths mean | Depth median | Left world | Calls mean | No-action mean | USD / game-min | Wall / game-min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a00-base-pa | baseline (default-v2, low, paused) | 4 | 1.5 | 1.00 | 2/4 | 0/4 | 0/4 | 0/4 | 1.8 | 19 | 1/4 | 58 | 0 | 0.0036 | 1.72 |
| a01-rt | clock: real time | 3 | 2.3 | 1.33 | 1/3 | 0/3 | 0/3 | 0/3 | 1.7 | 24 | 0/3 | 34 | 0 | 0.0016 | 1.01 |
| a02-grace2 | clock: real time + 2 s think grace | 3 | 0.7 | 2.00 | 0/3 | 0/3 | 0/3 | 0/3 | 2.0 | 51 | 0/3 | 45 | 0 | 0.0017 | 1.30 |
| a03-eff-none | effort none | 3 | 1.0 | 1.33 | 1/3 | 0/3 | 0/3 | 0/3 | 1.7 | 27 | 0/3 | 66 | 0 | 0.0032 | 1.70 |
| a04-eff-med | effort medium | 3 | 3.0 | 2.33 | 3/3 | 0/3 | 0/3 | 0/3 | 2.3 | 122 | 0/3 | 35 | 0 | 0.0024 | 1.52 |
| a05-eff-high | effort high | 3 | **4.3** | **2.67** | 3/3 | 1/3 | 1/3 | 0/3 | 1.3 | 80 | 0/3 | 65 | 0 | 0.0061 | 2.12 |
| a06-hostoff | hostile damage off (diagnostic) | 3 | 2.0 | 1.67 | 2/3 | 0/3 | 0/3 | 0/3 | 1.0 | 24 | 0/3 | 42 | 0 | 0.0023 | 1.49 |
| a07-know | knowledge card | 3 | 2.3 | 1.00 | 2/3 | 0/3 | 0/3 | 0/3 | 2.0 | 39 | 0/3 | 41 | 0 | 0.0018 | 1.39 |
| a08-feedback | progress feedback (crafted/placed log) | 3 | 0.0 | 2.33 | 0/3 | 0/3 | 0/3 | 0/3 | 2.7 | 69 | 0/3 | 63 | 0 | 0.0032 | 1.61 |
| a09-notes | persistent notes field | 3 | 2.0 | 1.67 | 1/3 | 0/3 | 0/3 | 0/3 | 2.3 | 24 | 0/3 | 58 | 0 | 0.0033 | 1.65 |
| a10-keep1 | 1 screenshot in context | 3 | 3.0 | 1.33 | 2/3 | 0/3 | 0/3 | 0/3 | 1.3 | 40 | 0/3 | 46 | 0 | 0.0033 | 1.43 |
| a11-obs512 | screenshot 512x512 | 3 | 0.0 | 1.00 | 0/3 | 0/3 | 0/3 | 0/3 | 2.3 | 7 | 1/3 | 54 | 0 | 0.0020 | 1.60 |
| a12-norm | normalized coords 0-1000 | 3 | 0.7 | 1.67 | 0/3 | 0/3 | 0/3 | 0/3 | 0.7 | 24 | 0/3 | 46 | 0 | 0.0023 | 1.48 |
| a13-max4 | max 4 actions per act | 3 | 0.7 | 1.33 | 0/3 | 0/3 | 0/3 | 0/3 | 3.3 | 28 | 0/3 | 77 | 0 | 0.0031 | 1.80 |
| a14-noctrl | no controls card | 3 | 0.0 | 1.33 | 0/3 | 0/3 | 0/3 | 0/3 | 2.7 | 24 | 0/3 | 70 | 0 | 0.0039 | 1.64 |
| a15-ctx30k | history 30k tokens | 3 | 1.0 | 1.33 | 1/3 | 0/3 | 0/3 | 0/3 | 1.0 | 24 | 1/3 | 53 | 0 | 0.0035 | 1.72 |
| a16-split | split key/mouse/wait tools | 3 | 2.0 | 1.00 | 2/3 | 0/3 | 0/3 | 0/3 | 2.3 | 23 | 0/3 | 287 | 0 | 0.0150 | 4.08 |
| a17-luna56-pa | gpt-5.6-luna (old model), low, paused | 3 | 1.3 | 1.33 | 1/3 | 1/3 | 0/3 | 0/3 | 1.3 | 26 | 0/3 | 95 | 0 | 0.0090 | 2.21 |

Baseline includes the re-run `a00-base-pa-w401-r2` (the first w401 run left the world at 2:06).

### Phase B — Haiku 5.5 (10 game-min, thinking medium unless stated, paused unless stated, worlds 401/402)

| Cell | Setup | n | Pub. mean | Ext. mean | wood 25 | any craft | torch crafted | bench placed | Deaths mean | Depth median | Left world | Calls mean | No-action mean | USD / game-min | Wall / game-min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b00-haiku-base-pa | Haiku medium, paused (baseline) | 2 | 4.0 | 4.00 | 2/2 | 2/2 | 0/2 | 1/2 | 1.0 | 106 | 0/2 | 270 | 80 | 0.0387 | 2.40 |
| b01-haiku-rt | Haiku: real time | 2 | 3.5 | 1.50 | 2/2 | 1/2 | 0/2 | 0/2 | 1.0 | 33 | 0/2 | 92 | 4 | 0.0079 | 1.00 |
| b03-haiku-eff-none | Haiku: thinking off (forced) | 2 | 0.0 | 1.00 | 0/2 | 0/2 | 0/2 | 0/2 | 1.0 | 1 | 0/2 | 188 | 0 | 0.0177 | 1.93 |
| b06-haiku-hostoff | Haiku: hostile damage off | 2 | 4.0 | 2.50 | 2/2 | 2/2 | 0/2 | 1/2 | 0.5 | 120 | 0/2 | 145 | 6 | 0.0146 | 1.69 |
| b07-haiku-know | Haiku: knowledge card | 2 | 3.5 | 2.50 | 1/2 | 2/2 | 0/2 | 1/2 | 0.0 | 47 | 0/2 | 242 | 94 | 0.0353 | 2.27 |
| b08-haiku-feedback | Haiku: progress feedback | 2 | 4.0 | 1.50 | 2/2 | 2/2 | 0/2 | 0/2 | 1.0 | 29 | 0/2 | 171 | 27 | 0.0219 | 1.97 |
| b09-haiku-notes | Haiku: notes | 2 | 4.0 | 3.50 | 2/2 | 2/2 | 0/2 | 1/2 | 2.5 | 66 | 0/2 | 274 | 100 | 0.0484 | 2.49 |

### Phase D — agent system: Luna6 (low) planner + Jev 1.14 executor (combo.py, default-v2, 10 game-min)

| Cell | Setup | n | Pub. mean | Ext. mean | wood 25 | any craft | torch crafted | bench placed | Deaths mean | Depth median | Left world | Calls mean | No-action mean | USD / game-min | Wall / game-min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| d01-combo-luna6-jev-rt | Luna6 planner + Jev, real time | 2 | 4.0 | 1.00 | 2/2 | 0/2 | 0/2 | 0/2 | 0.5 | 2 | 0/2 | 316 | 0 | 0.0054 | 1.00 |
| d02-combo-luna6-jev-pa | Luna6 planner + Jev, paused | 2 | 4.0 | 1.00 | 2/2 | 0/2 | 0/2 | 0/2 | 2.5 | 6 | 0/2 | 554 | 0 | 0.0094 | 1.66 |

USD / game-min here is planner (gateway, ≈ $0.001) + Jev (OpenRouter, ≈ $0.005–0.009).

### Phase C — confirmation at the benchmark length (Luna6, 20 game-min, worlds 401/402/403; w404 separately)

| Cell | Setup | n | Pub. mean | Ext. mean | wood 25 | any craft | torch crafted | bench placed | Deaths mean | Depth median | Left world | Calls mean | No-action mean | USD / game-min | Wall / game-min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e01-low-pa-20m | low, paused | 3 | 1.0 | 1.67 | 1/3 | 0/3 | 0/3 | 0/3 | 5.7 | 50 | 0/3 | 62 | 0 | 0.0019 | 1.37 |
| f03-low-pa-20m | low, paused (w404) | 1 | 1.0 | 2.00 | 0/1 | 0/1 | 0/1 | 0/1 | 14.0 | 43 | 0/1 | 84 | 0 | 0.0022 | 1.59 |
| e02-high-pa-20m | high, paused | 3 | 4.7 | 3.00 | 3/3 | 2/3 | 1/3 | 2/3 | 9.7 | 54 | 0/3 | 149 | 0 | 0.0116 | 2.62 |
| f02-high-pa-20m | high, paused (w404) | 1 | 4.0 | 3.00 | 1/1 | 0/1 | 0/1 | 0/1 | 17.0 | 140 | 0/1 | 106 | 0 | 0.0075 | 2.36 |
| e06-high-know-pa-20m | high + knowledge card, paused | 3 | **5.3** | **3.33** | 3/3 | 3/3 | 1/3 | **3/3** | 9.3 | 34 | 0/3 | 122 | 0 | 0.0085 | 2.39 |
| e03-low-rt-20m | low, real time | 3 | 1.0 | 1.67 | 0/3 | 0/3 | 0/3 | 0/3 | 15.3 | 50 | 0/3 | 64 | 0 | 0.0014 | 1.00 |
| e04-high-rt-20m | high, real time | 3 | 4.3 | 2.33 | 3/3 | 2/3 | 1/3 | 1/3 | 11.7 | 24 | 1/3 | 53 | 0 | 0.0025 | 1.02 |
| f01-high-grace2-rt-20m | high, real time + 2 s grace | 3 | 3.7 | 2.67 | 3/3 | 2/3 | 2/3 | 0/3 | 9.0 | 50 | 0/3 | 134 | 0 | 0.0094 | 2.32 |

Matched worlds (same world, low → high, paused 20 min, extended / bench placed): 401: 1 → 4, placed 8:12; 402:
2 → 3, –; 403: 2 → 2, placed 0:38; 404: 2 → 3, –. Real time: 401: 1 → 3, placed 6:28; 402: 2 → 2 (torches
crafted 10:00, then left the world at 15:36); 403: 2 → 2. High effort was never worse on the same world.

Per-run table (all 93 scored runs): [`results-table.md`](results/luna-factors-2026-11-10/results-table.md);
the condensed version is Appendix A.

## Per-factor effects (replication counts in brackets)

| Factor | Luna6 (n per level) | Haiku (n) | Verdict |
|---|---|---|---|
| **Reasoning effort** | 10 min: none 1.3 → low 1.0 → medium 2.3 → high 2.7 ext; wood 25 1/3 → 2/4 → 3/3 → 3/3 (3–4). 20 min: low crafted 0/7, high 9/13, bench placed 0/7 vs 6/13 (7 vs 13 runs, 4 worlds, both clocks) | thinking off 1.0 vs medium 4.0 ext; off never got wood 25 (2 vs 2) | **Large, monotone, generalises.** Latency doubles (4.6 → 8–12 s), cost ×3–6 per game-minute, still ≈ $0.24 per 20-min paused run |
| Clock (paused / real time) | low: tie on score both lengths; deaths 5.7 vs 15.3 at 20 min (3+3). high: paused 3.0 vs rt 2.3 ext, bench 2/3 vs 1/3 (3+3) | medium: paused 4.0 vs rt 1.5 ext (2+2) | Paused ≥ real time for slow-thinking settings; keep both tracks |
| Bounded-staleness real time (2 s grace) | low 10 min: 2.0 vs 1.3 rt (3); high 20 min: 2.7 vs 2.3 rt, torches crafted 2/3, bench 0/3, wall 2.3× (3) | – | Between rt and paused, adds wall time; not worth a third clock |
| Hostile damage off (diagnostic) | 1.7 vs 1.0 ext, deaths 1.0 vs 1.8, no crafting (3) | 2.5 vs 4.0 ext (2) | Combat is not the 10-min bottleneck; keep normal PvE |
| Knowledge card | low: 1.0 vs 1.0 (3); high 20 min: 3.3 vs 3.0 ext, bench 3/3 vs 2/3 (3+3) | 2.5 vs 4.0 (2) | Helps only once the model plans (high effort); weak; declared variant candidate at most |
| Progress feedback (crafted/placed log) | 2.3 vs 1.0 ext but published 0 (no wood 25 in 0/3) (3) | 1.5 vs 4.0 (2) | No benefit; do not add |
| Notes field | 1.7 vs 1.0 (3) | 3.5 vs 4.0, most no-action turns (100) (2) | No benefit |
| 1 screenshot kept (vs 8–15) | 1.3 vs 1.0, published 3.0 vs 1.5 (3) | – | Neutral; context size is not binding at 10 min |
| History 30k tokens | 1.3 vs 1.0 (3) | – | Neutral |
| 512² screenshots | 1.0, published 0, wood 25 0/3 (3) | – | Harmful for aiming; keep full resolution |
| Normalized coordinates | 1.7, published 0.7, wood 25 0/3 (3) | – | No gain, worse wood; keep pixels |
| Max 4 actions per call | 1.3, wood 25 0/3, deaths 3.3 (3) | – | Shorter batches did not make low-effort Luna more careful; keep 16 |
| No controls list | 1.3, published 0, wood 25 0/3 (3) | – | Controls card helps; keep it |
| Split key/mouse/wait tools | 1.0, 287 calls vs 58, wall 4.1 vs 1.7 per game-min (3) | – | No gain, much slower/costlier; keep one `act` |
| Model generation (gpt-5.6-luna vs gpt-6-luna, low, paused) | 1.3 vs 1.0 ext; latency 7.1 vs 4.6 s; $0.009 vs $0.004 per game-min (3 vs 4) | – | Same play at low effort; Luna6 cheaper and faster |
| Planner + Jev executor (agent system) | published 4.0 (wood), extended 1.0, nothing crafted, depth ≤ 11 (4) | – | Same placement wall as Nov 8; not a Luna improvement |

What the effort factor changes (from timelines and batch statistics): at low effort Luna6 writes long open-loop
batches — 10–15 primitives covering 15–30 game-seconds per call in the 20-minute runs (e.g. sixteen identical
"hold D + jump + left click at (700, 450) for 1.8 s") — and never opens the crafting list. At high effort it plans
from the screenshot (shorter batches in paused mode: 4–6 primitives, 6–12 game-s per call), opens the inventory, crafts
the bench from the crafting list and places it with a click near the player; e02-w403 placed its bench 38 s into the
run, e06-w401 at 0:42 and first crafted torches at 7:02 (15 in total, 7 placed).

## Recommendations

Ranked by expected value for the benchmark:

1. **Fix and report reasoning effort per model as part of the protocol; give each model its strongest allowed
   setting (here `high`) for the official runs.** Effort is a model setting, not a game-rule change, and it dominates
   every harness factor tested (Luna6 bench placement 0/7 → 6/13). The landscape's `low` setting understated Luna
   (and the user cap "≤ high" is the natural ceiling). Report effort, latency and cost per game-minute next to the
   score; keep a `low` row only as a cost-matched reference.
2. **Keep the default-v2 harness as is.** Full-resolution 1024² JPEG after every act, pixel coordinates, up to 16
   actions per call, one `act` tool, the controls list, 8–15 screenshots and 120k history. Every alternative tried was
   neutral or worse; none is worth a variant.
3. **Shipped variants: paused primary, real time secondary (unchanged).** At high effort paused ≥ real time on every
   world; the 2-s grace clock is not better enough to justify a third clock. Real time remains the
   latency-aware/second number.
4. **Diagnostics only (never default):** hostile damage off (did not unlock progress for either vendor), progress
   feedback, notes. Candidate *declared* variant if a "knowledge" track is ever wanted: the knowledge card (helps only
   with high effort, n = 3; hurt nothing).
5. **Address the accidental Save & Exit before freezing v1** (open question below): 4/72 Luna6 runs lost 4–18
   game-minutes to a misclick in the Settings menu, which the leave-world rule turns into a forfeit.
6. Budget: Luna6 high, paused, 20 min ≈ $0.12–0.34 per run (≈ 45–60 wall-min); 3 worlds × 2 clocks ≈ $1.3. Haiku
   medium paused ≈ $0.8 per 20 min.

### Cost per game-minute by configuration (gateway USD; mean over the cell)

| Configuration | USD / game-min | Wall min / game-min | Latency (s) |
|---|---:|---:|---:|
| Luna6 none, paused | 0.0032 | 1.7 | 5.1–5.6 |
| Luna6 low, paused | 0.0019–0.0036 | 1.4–1.7 | 4.5–6.3 |
| Luna6 low, real time | 0.0014–0.0016 | 1.0 | 4.6–6.2 |
| Luna6 medium, paused | 0.0024 | 1.5 | 7.1–8.8 |
| Luna6 high, paused | 0.0061–0.0116 | 2.1–2.6 | 8.3–13.3 |
| Luna6 high, real time | 0.0025 | 1.0 | 9.4–11.9 |
| Luna6 high, real time + 2 s grace | 0.0094 | 2.3 | 11.0–12.2 |
| Luna6 low, split tools | 0.0150 | 4.1 | 5.2–6.1 |
| gpt-5.6-luna low, paused | 0.0090 | 2.2 | 6.6–7.6 |
| Haiku medium, paused | 0.0387 | 2.4 | 2.7–2.8 |
| Haiku medium, real time | 0.0079 | 1.0 | 2.8–2.9 |
| Haiku thinking off (forced), paused | 0.0177 | 1.9 | 2.4–2.7 |
| Luna6 low + Jev, real time / paused | 0.0054 / 0.0094 (≈ 80 % OpenRouter) | 1.0 / 1.7 | 5–6 / 0.3 |

## Spend

Ledger: [`ledger.json`](results/luna-factors-2026-11-10/ledger.json) (`tools/campaign_ledger.py`; per run from its
accounting; GPT cost = gateway `X-Token-Usage-Cost`, Claude at list price; uncertain = sent attempts that failed and
whose charge is unknown, counted in full).

| Route | Cap | Reported | Uncertain | Conservative |
|---|---:|---:|---:|---:|
| AMD gateway (Unified + Anthropic), incl. $0.001 model/price probes and $0.003 smokes | $15.00 | **$8.14** | $1.43 | **$9.57** |
| OpenRouter (Jev) | $1.00 | **$0.25** | $0 | **$0.25** |

The uncertain amount is 63 failed sent Luna6 attempts (46 HTTP 504, 10 HTTP 429, 6 HTTP 503, 1 read timeout) at the
$0.022 per-call reservation; most were probably not billed. Haiku runs were $3.69 of the reported gateway spend.
The queue refused any job whose cap + running caps + spend would exceed $14.50.

## Open questions

- **Accidental world exit.** Options: (a) keep the forfeit (it is the agent's input); (b) have the harness re-enter
  the world after Save & Exit (time keeps running, counted as an event) — needs the observer journal to survive
  re-entry; (c) report exits separately and re-run. Our data: 4/72 single-model Luna6 runs, 3 on world 401, all from the
  Settings-menu misclick; 0 in Haiku or the combination.
- Does high effort help the other cheap models the same way (Terra; Haiku with a high thinking budget — only the
  medium 8k and off shapes are captured on the gateway)? Haiku off vs medium points the same way.
- Medium effort at 20 min (10-min data suggest it sits between low and high at a third of high's wall time).
- The knowledge card on top of high effort: n = 3, +1 placement; a 3–6-world replicate would settle whether a
  declared knowledge variant is worth shipping.
- High-effort runs die 9–17 times in 20 minutes (they explore farther and stay out at night); a hostile-off diagnostic
  at high effort and 20 minutes was not run.
- World spread: world 401 accounts for 3 of 4 exits; world 404 (unseen by Luna6) gave no bench to either effort.

## Limitations

- n = 2–4 per cell, 3–4 worlds; screening at 10 game-minutes (a floor: low-effort Luna6 crafts nothing in 10 min, so
  harness factors could only show through wood/depth/ore). Effects of ±1 extended fact are noise.
- Effort was screened and confirmed on the same three worlds (plus one new world in confirmation).
- Haiku used the default-v2 Haiku shape (thinking medium, unforced) as its baseline, with only 2 worlds per cell.
- `--think-grace`: each provider attempt (including retries after HTTP 504) gets its own 2-s real-time grace;
  f01-w402 needed 66 wall-minutes for 20 game-minutes (218 calls).
- Fixtures differ from the landscape fixtures only in the `LastLaunchedMods.txt` line (startup dialog); game, world and
  player files are identical.
- Game date not pinned; nights after ~15 game-minutes dominate deaths in 20-minute runs.

## Code and files

- `terrariabench/reference_live.py`: declared factors (`FACTOR_DEFAULTS`, `default_tools(..., max_actions, notes,
  normalized)`, `split_tools`/`split_action`, `factor_prompt`, `to_window`, `--think-grace` timer freeze,
  `--obs-size` downscale, notes in screenshot turns, `crafted_and_placed` in act results; `manifest.factors`,
  `observation_encoding.coords/window`, `model.deployment`).
- `terrariabench/unified.py`: `gpt-6-luna` (fitted price $0.09/M in, $0.35/M out; deployment id).
- `prompts/knowledge_card_v1.txt` (new); `tools/dg_job.py` (factor flags now override the defaults); `tools/campaign_table.py`
  (Luna6 name, factors in the setup label).
- Job scripts: `experiments/luna-factors-2026-11-10-screen.sh` (phase A), `-haiku-combo.sh` (B, D), `-confirm.sh`
  (C; `FOLLOWUP=1` for the grace/w404 follow-ups).

## Best-run videos (Omarchy)

`~/Projects/TerrariaBench/runs/luna-factors-2026-11-10/<run>/desktop.mp4`:
- `e06-high-know-pa-20m-w401` — bench placed 0:42, torches crafted from 7:02 (15 crafted, 7 placed; published 6).
- `e02-high-pa-20m-w401` — bench placed 8:12, torches crafted 15:15, 118 tiles deep (extended 4).
- `e04-high-rt-20m-w401` — real time, bench placed 6:28, iron/lead ore (published 6).
- `a00-base-pa-w401` — the Settings-menu misclick on *Save & Exit* at 2:06.

## Appendix A — per-run table

| Run | Setup | World | Game min | Stop | Pub. | Ext. | Extended facts (game mm:ss) | Crafted | Placed | Deaths | Depth | No-action | Calls | Latency s | Shot age game s | Wall min | USD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a00-base-pa-w401 | baseline (default-v2, low, paused) | 401 | 2.1 | left world | 0 | 0 | – | – | – | 1 | 24 | 0 | 21 | 4.6 | 0.06 | 4.6 | 0.006 |
| a00-base-pa-w402 | baseline (default-v2, low, paused) | 402 | 10.0 | budget | 3 | 1 | gel_1 2:28 | – | – | 2 | 14 | 0 | 75 | 4.7 | 0.06 | 17.5 | 0.048 |
| a00-base-pa-w403 | baseline (default-v2, low, paused) | 403 | 10.0 | budget | 3 | 2 | gel_1 0:49, ore_iron_lead 4:35 | – | – | 0 | 7 | 0 | 75 | 4.5 | 0.06 | 16.6 | 0.032 |
| a01-rt-w401 | clock: real time | 401 | 10.0 | budget | 1 | 1 | gel_1 2:28 | – | – | 3 | 24 | 0 | 37 | 4.6 | 4.8 | 10.3 | 0.020 |
| a01-rt-w402 | clock: real time | 402 | 10.0 | budget | 2 | 1 | gel_1 0:38 | – | – | 0 | 12 | 0 | 36 | 5.2 | 5.26 | 10.0 | 0.014 |
| a01-rt-w403 | clock: real time | 403 | 10.0 | budget | 4 | 2 | gel_1 1:01, layer_underground 6:13 | – | – | 2 | 122 | 0 | 29 | 4.9 | 4.94 | 10.0 | 0.015 |
| a02-grace2-w401 | clock: real time + 2 s think grace | 401 | 10.0 | budget | 0 | 1 | gel_1 2:26 | – | – | 3 | 24 | 0 | 31 | 5.2 | 2.06 | 12.5 | 0.011 |
| a02-grace2-w402 | clock: real time + 2 s think grace | 402 | 10.0 | budget | 2 | 4 | gel_1 1:58, ore_iron_lead 6:10, layer_underground 7:21, ore_copper_tin 7:29 | – | torch 1 | 3 | 96 | 0 | 57 | 4.9 | 2.06 | 13.1 | 0.021 |
| a02-grace2-w403 | clock: real time + 2 s think grace | 403 | 10.0 | budget | 0 | 1 | gel_1 2:49 | – | – | 0 | 51 | 0 | 47 | 4.0 | 2.06 | 13.5 | 0.018 |
| a03-eff-none-w401 | effort none | 401 | 10.0 | budget | 0 | 1 | gel_1 1:00 | – | – | 1 | 27 | 0 | 75 | 5.1 | 0.06 | 18.9 | 0.043 |
| a03-eff-none-w402 | effort none | 402 | 10.0 | budget | 3 | 1 | gel_1 0:45 | – | – | 2 | 1 | 0 | 72 | 5.6 | 0.06 | 17.3 | 0.031 |
| a03-eff-none-w403 | effort none | 403 | 10.0 | budget | 0 | 2 | layer_underground 1:43, gel_1 3:49 | – | – | 2 | 122 | 0 | 50 | 5.3 | 0.06 | 14.8 | 0.021 |
| a04-eff-med-w401 | effort medium | 401 | 10.0 | budget | 3 | 2 | layer_underground 1:37, gel_1 5:33 | – | – | 3 | 131 | 0 | 33 | 7.1 | 0.06 | 14.8 | 0.020 |
| a00-base-pa-w401-r2 | baseline (default-v2, low, paused) | 401 | 10.0 | budget | 0 | 1 | gel_1 4:55 | – | – | 4 | 24 | 0 | 60 | 4.8 | 0.06 | 16.6 | 0.030 |
| a04-eff-med-w402 | effort medium | 402 | 10.0 | budget | 3 | 3 | gel_1 1:31, layer_underground 5:09, ore_copper_tin 8:50 | – | – | 2 | 70 | 0 | 40 | 8.8 | 0.06 | 16.6 | 0.028 |
| a04-eff-med-w403 | effort medium | 403 | 10.0 | budget | 3 | 2 | gel_1 0:17, layer_underground 4:55 | – | torch 1 | 2 | 122 | 0 | 31 | 8.2 | 0.06 | 14.2 | 0.023 |
| a05-eff-high-w401 | effort high | 401 | 10.0 | budget | 6 | 4 | gel_1 2:01, torch_crafted 4:05, layer_underground 4:53, ore_iron_lead 6:25 | Work Bench 1, Torch 12 | torch 6 | 2 | 80 | 0 | 102 | 8.3 | 0.06 | 24.8 | 0.107 |
| a05-eff-high-w402 | effort high | 402 | 10.0 | budget | 4 | 2 | gel_1 1:43, layer_underground 3:17 | – | torch 6 | 1 | 69 | 0 | 63 | 10.9 | 0.06 | 23.7 | 0.057 |
| a05-eff-high-w403 | effort high | 403 | 10.0 | budget | 3 | 2 | gel_1 1:02, layer_underground 3:58 | – | – | 1 | 122 | 0 | 31 | 8.8 | 0.06 | 15.2 | 0.019 |
| a06-hostoff-w401 | hostile damage off (diagnostic) | 401 | 10.0 | budget | 3 | 1 | gel_1 1:58 | – | – | 1 | 24 | 0 | 23 | 5.6 | 0.06 | 13.4 | 0.009 |
| a06-hostoff-w402 | hostile damage off (diagnostic) | 402 | 10.0 | budget | 3 | 2 | gel_1 1:41, ore_iron_lead 7:05 | – | – | 1 | 14 | 0 | 53 | 4.9 | 0.06 | 15.6 | 0.031 |
| a06-hostoff-w403 | hostile damage off (diagnostic) | 403 | 10.0 | budget | 0 | 2 | layer_underground 1:33, gel_1 3:22 | – | – | 1 | 122 | 0 | 49 | 4.5 | 0.06 | 15.7 | 0.028 |
| a07-know-w401 | knowledge card | 401 | 10.0 | budget | 4 | 1 | gel_1 3:14 | – | – | 0 | 2 | 0 | 22 | 5.2 | 0.06 | 13.1 | 0.009 |
| a07-know-w402 | knowledge card | 402 | 10.0 | budget | 0 | 1 | layer_underground 1:40 | – | – | 0 | 69 | 0 | 43 | 4.0 | 0.06 | 13.2 | 0.018 |
| a07-know-w403 | knowledge card | 403 | 10.0 | budget | 3 | 1 | gel_1 1:41 | – | – | 6 | 39 | 0 | 57 | 4.9 | 0.06 | 15.3 | 0.027 |
| a08-feedback-w401 | progress feedback (crafted/placed log) | 401 | 10.0 | budget | 0 | 2 | ore_iron_lead 1:05, gel_1 2:28 | – | – | 1 | 27 | 0 | 57 | 5.0 | 0.07 | 15.5 | 0.025 |
| a08-feedback-w402 | progress feedback (crafted/placed log) | 402 | 10.0 | budget | 0 | 2 | layer_underground 1:02, gel_1 3:40 | – | – | 5 | 69 | 0 | 60 | 4.6 | 0.07 | 16.1 | 0.025 |
| a08-feedback-w403 | progress feedback (crafted/placed log) | 403 | 10.0 | budget | 0 | 3 | gel_1 2:14, ore_iron_lead 9:23, layer_underground 9:35 | – | – | 2 | 122 | 0 | 73 | 4.6 | 0.06 | 16.7 | 0.046 |
| a09-notes-w401 | persistent notes field | 401 | 10.0 | budget | 4 | 1 | gel_1 7:45 | – | – | 1 | 24 | 0 | 66 | 5.8 | 0.06 | 17.3 | 0.043 |
| a09-notes-w402 | persistent notes field | 402 | 10.0 | budget | 2 | 2 | gel_1 2:49, ore_silver_gold_tier 3:28 | – | torch 2 | 3 | 22 | 0 | 45 | 5.5 | 0.06 | 15.8 | 0.029 |
| a09-notes-w403 | persistent notes field | 403 | 10.0 | budget | 0 | 2 | layer_underground 2:10, gel_1 9:13 | – | – | 3 | 122 | 0 | 62 | 4.8 | 0.06 | 16.4 | 0.027 |
| a10-keep1-w401 | 1 screenshot in context | 401 | 10.0 | budget | 4 | 1 | gel_1 2:56 | – | torch 5 | 3 | 25 | 0 | 32 | 4.9 | 0.06 | 13.1 | 0.021 |
| a10-keep1-w402 | 1 screenshot in context | 402 | 10.0 | budget | 2 | 2 | gel_1 1:07, ore_copper_tin 1:47 | – | – | 1 | 40 | 0 | 86 | 4.1 | 0.06 | 17.4 | 0.065 |
| a10-keep1-w403 | 1 screenshot in context | 403 | 10.0 | budget | 3 | 1 | gel_1 0:28 | – | – | 0 | 42 | 0 | 21 | 5.2 | 0.06 | 12.3 | 0.015 |
| a11-obs512-w401 | screenshot 512x512 | 401 | 3.5 | left world | 0 | 1 | gel_1 1:09 | – | – | 2 | 24 | 0 | 27 | 4.0 | 0.07 | 5.3 | 0.006 |
| a11-obs512-w402 | screenshot 512x512 | 402 | 10.0 | budget | 0 | 1 | gel_1 4:13 | – | – | 5 | 1 | 0 | 55 | 4.8 | 0.08 | 15.8 | 0.021 |
| a11-obs512-w403 | screenshot 512x512 | 403 | 10.0 | budget | 0 | 1 | gel_1 2:44 | – | – | 0 | 7 | 0 | 81 | 4.3 | 0.07 | 16.5 | 0.020 |
| a12-norm-w401 | normalized coords 0-1000 | 401 | 10.0 | budget | 0 | 1 | gel_1 2:06 | – | – | 1 | 24 | 0 | 35 | 5.1 | 0.06 | 13.6 | 0.018 |
| a12-norm-w402 | normalized coords 0-1000 | 402 | 10.0 | budget | 1 | 2 | gel_1 2:10, ore_silver_gold_tier 6:00 | – | – | 1 | 27 | 0 | 51 | 5.2 | 0.06 | 15.1 | 0.031 |
| a12-norm-w403 | normalized coords 0-1000 | 403 | 10.0 | budget | 1 | 2 | gel_1 1:06, ore_iron_lead 2:52 | – | – | 0 | 7 | 0 | 51 | 5.3 | 0.06 | 15.7 | 0.021 |
| a13-max4-w401 | max 4 actions per act | 401 | 10.0 | budget | 0 | 0 | – | – | – | 5 | 24 | 0 | 78 | 5.1 | 0.06 | 19.3 | 0.031 |
| a13-max4-w402 | max 4 actions per act | 402 | 10.0 | budget | 2 | 2 | gel_1 2:52, ore_iron_lead 9:21 | – | – | 3 | 28 | 0 | 75 | 5.3 | 0.06 | 17.4 | 0.031 |
| a13-max4-w403 | max 4 actions per act | 403 | 10.0 | budget | 0 | 2 | gel_1 0:42, layer_underground 2:24 | – | – | 2 | 122 | 0 | 77 | 4.4 | 0.06 | 17.3 | 0.032 |
| a14-noctrl-w401 | no controls card | 401 | 10.0 | budget | 0 | 1 | gel_1 2:50 | – | – | 2 | 24 | 0 | 77 | 5.1 | 0.06 | 17.5 | 0.048 |
| a14-noctrl-w402 | no controls card | 402 | 10.0 | budget | 0 | 1 | gel_1 3:47 | – | – | 4 | 2 | 0 | 60 | 5.2 | 0.06 | 15.7 | 0.037 |
| a14-noctrl-w403 | no controls card | 403 | 10.0 | budget | 0 | 2 | gel_1 2:35, layer_underground 4:31 | – | – | 2 | 122 | 0 | 73 | 4.7 | 0.06 | 16.1 | 0.031 |
| a15-ctx30k-w401 | history 30k tokens | 401 | 3.0 | left world | 0 | 1 | gel_1 1:07 | – | – | 1 | 24 | 0 | 25 | 4.4 | 0.06 | 5.0 | 0.013 |
| a15-ctx30k-w402 | history 30k tokens | 402 | 10.0 | budget | 3 | 1 | gel_1 1:47 | – | – | 1 | 13 | 0 | 62 | 5.5 | 0.06 | 17.2 | 0.038 |
| a15-ctx30k-w403 | history 30k tokens | 403 | 10.0 | budget | 0 | 2 | layer_underground 1:36, gel_1 2:01 | – | – | 1 | 122 | 0 | 73 | 4.5 | 0.06 | 17.5 | 0.031 |
| a16-split-w401 | split key/mouse/wait tools | 401 | 10.0 | budget | 3 | 1 | gel_1 3:37 | – | – | 3 | 23 | 0 | 288 | 6.1 | 0.03 | 41.8 | 0.141 |
| a16-split-w402 | split key/mouse/wait tools | 402 | 10.0 | budget | 3 | 1 | layer_underground 2:52 | – | – | 4 | 69 | 0 | 284 | 6.0 | 0.03 | 41.0 | 0.138 |
| a16-split-w403 | split key/mouse/wait tools | 403 | 10.0 | budget | 0 | 1 | gel_1 0:17 | – | – | 0 | 18 | 0 | 288 | 5.2 | 0.02 | 39.7 | 0.172 |
| a17-luna56-pa-w401 | gpt-5.6-luna (old model), low, paused | 401 | 10.0 | budget | 0 | 2 | ore_iron_lead 3:51, gel_1 6:05 | – | – | 2 | 26 | 0 | 78 | 7.1 | 0.06 | 20.1 | 0.069 |
| a17-luna56-pa-w402 | gpt-5.6-luna (old model), low, paused | 402 | 10.0 | budget | 1 | 1 | gel_1 1:07 | – | – | 2 | 1 | 0 | 107 | 7.6 | 0.06 | 24.8 | 0.107 |
| a17-luna56-pa-w403 | gpt-5.6-luna (old model), low, paused | 403 | 10.0 | budget | 3 | 1 | gel_1 1:19 | Wood Platform 2 | – | 0 | 33 | 0 | 99 | 6.6 | 0.06 | 21.5 | 0.094 |
| b00-haiku-base-pa-w401 | Haiku medium, paused (baseline) | 401 | 10.0 | budget | 4 | 6 | gel_1 0:55, layer_underground 1:27, ore_copper_tin 2:53, ore_silver_gold_tier 3:49, layer_cavern 6:30, workbench_placed 7:09 | Work Bench 1 | bench 1 | 2 | 191 | 22 | 173 | 2.8 | 0.05 | 19.8 | 0.205 |
| b00-haiku-base-pa-w402 | Haiku medium, paused (baseline) | 402 | 10.0 | budget | 4 | 2 | gel_1 2:04, ore_iron_lead 3:12 | Work Bench 1 | – | 0 | 21 | 137 | 366 | 2.7 | 0.06 | 28.2 | 0.568 |
| b01-haiku-rt-w401 | Haiku: real time | 401 | 10.0 | budget | 3 | 1 | gel_1 0:51 | – | – | 1 | 1 | 2 | 80 | 2.9 | 2.93 | 10.0 | 0.067 |
| b01-haiku-rt-w402 | Haiku: real time | 402 | 10.0 | budget | 4 | 2 | gel_1 1:17, layer_underground 3:11 | Work Bench 1 | torch 3 | 1 | 65 | 5 | 105 | 2.8 | 2.86 | 10.0 | 0.092 |
| b03-haiku-eff-none-w401 | Haiku: thinking off (forced) | 401 | 10.0 | budget | 0 | 1 | gel_1 2:07 | – | – | 0 | 1 | 0 | 174 | 2.4 | 0.06 | 18.1 | 0.151 |
| b03-haiku-eff-none-w402 | Haiku: thinking off (forced) | 402 | 10.0 | budget | 0 | 1 | gel_1 1:29 | – | – | 2 | 1 | 0 | 202 | 2.7 | 0.06 | 20.4 | 0.203 |
| b06-haiku-hostoff-w401 | Haiku: hostile damage off | 401 | 10.0 | budget | 4 | 2 | layer_underground 0:58, ore_iron_lead 5:59 | Work Bench 1 | – | 0 | 155 | 6 | 117 | 2.5 | 0.06 | 15.2 | 0.108 |
| b06-haiku-hostoff-w402 | Haiku: hostile damage off | 402 | 10.0 | budget | 4 | 3 | workbench_placed 0:33, layer_underground 1:18, gel_1 3:37 | Work Bench 2 | bench 2 | 1 | 86 | 5 | 173 | 2.5 | 0.06 | 18.6 | 0.184 |
| b07-haiku-know-w401 | Haiku: knowledge card | 401 | 10.0 | budget | 4 | 3 | gel_1 0:37, ore_silver_gold_tier 0:37, layer_underground 1:22 | Work Bench 1 | – | 0 | 67 | 76 | 235 | 2.4 | 0.06 | 22.0 | 0.324 |
| b07-haiku-know-w402 | Haiku: knowledge card | 402 | 10.0 | budget | 3 | 2 | workbench_placed 0:29, ore_iron_lead 0:51 | Work Bench 1 | bench 1 | 0 | 27 | 112 | 250 | 2.9 | 0.06 | 23.4 | 0.383 |
| b08-haiku-feedback-w401 | Haiku: progress feedback | 401 | 10.0 | budget | 4 | 2 | ore_copper_tin 1:21, gel_1 3:19 | Work Bench 1 | – | 1 | 32 | 32 | 153 | 2.9 | 0.04 | 18.2 | 0.176 |
| b08-haiku-feedback-w402 | Haiku: progress feedback | 402 | 10.0 | budget | 4 | 1 | gel_1 1:36 | Work Bench 1, Wood Platform 2 | – | 1 | 26 | 22 | 189 | 3.1 | 0.04 | 21.1 | 0.263 |
| b09-haiku-notes-w401 | Haiku: notes | 401 | 10.0 | budget | 4 | 3 | layer_underground 0:55, ore_copper_tin 5:27, gel_1 7:23 | Work Bench 2 | – | 2 | 53 | 22 | 164 | 2.9 | 0.06 | 18.5 | 0.216 |
| b09-haiku-notes-w402 | Haiku: notes | 402 | 10.0 | budget | 4 | 4 | gel_1 1:17, layer_underground 2:04, workbench_placed 2:59, wood_armor_crafted 4:19 | Work Bench 2, Rope Coil 1, Wood Greaves 1 | bench 1 | 3 | 78 | 177 | 385 | 2.7 | 0.04 | 31.3 | 0.751 |
| d01-combo-luna6-jev-rt-w401 | Luna6 planner + Jev, real time | 401 | 10.0 | budget | 4 | 1 | gel_1 1:06 | – | – | 0 | 2 | 0 | 307 | 4.8/0.3 | 0.42 | 10.0 | 0.053 |
| d01-combo-luna6-jev-rt-w402 | Luna6 planner + Jev, real time | 402 | 10.0 | budget | 4 | 1 | gel_1 2:47 | – | – | 1 | 1 | 0 | 325 | 5.9/0.3 | 0.44 | 10.0 | 0.055 |
| d02-combo-luna6-jev-pa-w401 | Luna6 planner + Jev, paused | 401 | 10.0 | budget | 4 | 1 | gel_1 1:07 | – | – | 3 | 11 | 0 | 460 | 5.3/0.3 | 0.02 | 15.6 | 0.079 |
| d02-combo-luna6-jev-pa-w402 | Luna6 planner + Jev, paused | 402 | 10.0 | budget | 4 | 1 | gel_1 1:21 | – | – | 2 | 2 | 0 | 647 | 5.1/0.3 | 0.03 | 17.7 | 0.110 |
| e01-low-pa-20m-w401 | low, paused | 401 | 20.0 | budget | 0 | 1 | gel_1 1:52 | – | – | 12 | 24 | 0 | 55 | 6.3 | 0.06 | 26.3 | 0.041 |
| e01-low-pa-20m-w402 | low, paused | 402 | 20.0 | budget | 3 | 2 | gel_1 0:38, layer_underground 0:47 | – | – | 0 | 50 | 0 | 40 | 5.6 | 0.05 | 24.1 | 0.028 |
| e01-low-pa-20m-w403 | low, paused | 403 | 20.0 | budget | 0 | 2 | gel_1 0:56, layer_underground 7:04 | – | – | 5 | 122 | 0 | 91 | 5.6 | 0.06 | 31.7 | 0.044 |
| e02-high-pa-20m-w401 | high, paused | 401 | 20.0 | budget | 5 | 4 | gel_1 1:34, workbench_placed 8:12, layer_underground 9:51, torch_crafted 15:15 | Work Bench 5, Torch 3 | bench 2, torch 1 | 11 | 118 | 0 | 187 | 11.9 | 0.07 | 60.5 | 0.338 |
| e06-high-know-pa-20m-w403 | high + knowledge card, paused | 403 | 20.0 | budget | 5 | 3 | gel_1 1:50, workbench_placed 7:35, eoc_summon_or_lens 15:59 | Work Bench 1 | bench 1 | 16 | 9 | 0 | 110 | 12.7 | 0.06 | 44.5 | 0.151 |
| e02-high-pa-20m-w402 | high, paused | 402 | 20.0 | budget | 4 | 3 | gel_1 0:23, ore_copper_tin 1:36, layer_underground 10:41 | – | – | 4 | 54 | 0 | 102 | 12.3 | 0.06 | 44.5 | 0.107 |
| e02-high-pa-20m-w403 | high, paused | 403 | 20.0 | budget | 5 | 2 | workbench_placed 0:38, gel_1 0:51 | Work Bench 1, Copper Coin 100 | bench 1 | 14 | 39 | 0 | 158 | 10.9 | 0.06 | 52.3 | 0.248 |
| e03-low-rt-20m-w401 | low, real time | 401 | 20.0 | budget | 0 | 1 | gel_1 2:37 | – | – | 21 | 24 | 0 | 58 | 6.2 | 6.3 | 20.0 | 0.026 |
| e06-high-know-pa-20m-w402 | high + knowledge card, paused | 402 | 20.0 | budget | 5 | 4 | gel_1 0:40, layer_underground 3:01, workbench_placed 4:21, eoc_summon_or_lens 12:28 | Wood Platform 2, Work Bench 3, Wood 1 | bench 1 | 2 | 102 | 0 | 120 | 11.9 | 0.06 | 46.0 | 0.146 |
| e03-low-rt-20m-w402 | low, real time | 402 | 20.0 | budget | 2 | 2 | gel_1 2:53, layer_underground 15:43 | – | – | 13 | 50 | 0 | 80 | 5.3 | 5.39 | 20.1 | 0.035 |
| e03-low-rt-20m-w403 | low, real time | 403 | 20.0 | budget | 1 | 2 | gel_1 2:20, layer_underground 10:57 | – | – | 12 | 122 | 0 | 54 | 5.9 | 5.93 | 20.0 | 0.024 |
| e04-high-rt-20m-w401 | high, real time | 401 | 20.0 | budget | 6 | 3 | gel_1 2:14, workbench_placed 6:28, ore_iron_lead 11:55 | Work Bench 1 | bench 1 | 13 | 24 | 0 | 60 | 11.9 | 12.12 | 21.2 | 0.062 |
| e04-high-rt-20m-w402 | high, real time | 402 | 15.6 | left world | 3 | 2 | gel_1 1:07, torch_crafted 10:00 | Torch 3 | – | 9 | 2 | 0 | 58 | 10.1 | 10.14 | 15.8 | 0.050 |
| e04-high-rt-20m-w403 | high, real time | 403 | 20.0 | budget | 4 | 2 | layer_underground 5:15, gel_1 8:13 | – | – | 13 | 122 | 0 | 40 | 9.4 | 9.5 | 20.0 | 0.027 |
| e06-high-know-pa-20m-w401 | high + knowledge card, paused | 401 | 20.0 | budget | 6 | 3 | gel_1 0:30, workbench_placed 0:42, torch_crafted 7:02 | Work Bench 2, Torch 15, Wood Platform 4 | bench 2, torch 7 | 10 | 34 | 0 | 136 | 12.7 | 0.06 | 53.0 | 0.212 |
| f03-low-pa-20m-w404 | low, paused (w404) | 404 | 20.0 | budget | 1 | 2 | ore_copper_tin 4:54, gel_1 12:15 | – | – | 14 | 43 | 0 | 84 | 7.7 | 0.06 | 31.8 | 0.044 |
| f01-high-grace2-rt-20m-w401 | high, real time + 2 s grace | 401 | 20.0 | budget | 5 | 2 | gel_1 1:34, torch_crafted 6:32 | Wood Platform 4, Work Bench 1, Torch 3, Copper Coin 100 | torch 4 | 0 | 37 | 0 | 90 | 11.0 | 2.06 | 37.1 | 0.090 |
| f01-high-grace2-rt-20m-w402 | high, real time + 2 s grace | 402 | 20.0 | budget | 3 | 2 | gel_1 4:54, layer_underground 13:22 | – | – | 13 | 50 | 0 | 218 | 12.2 | 2.06 | 65.6 | 0.388 |
| f01-high-grace2-rt-20m-w403 | high, real time + 2 s grace | 403 | 20.0 | budget | 3 | 4 | gel_1 0:37, layer_underground 3:21, torch_crafted 9:19, eoc_summon_or_lens 14:58 | Wood Platform 4, Torch 3 | torch 1 | 14 | 156 | 0 | 93 | 11.6 | 2.06 | 36.5 | 0.086 |
| f02-high-pa-20m-w404 | high, paused (w404) | 404 | 20.0 | budget | 4 | 3 | ore_copper_tin 1:51, layer_underground 2:26, gel_1 3:54 | – | – | 17 | 140 | 0 | 106 | 13.3 | 0.06 | 47.1 | 0.151 |
