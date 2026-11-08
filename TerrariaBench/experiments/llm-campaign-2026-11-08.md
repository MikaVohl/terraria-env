# LLM campaign on official Terraria, 2026-11-08

Question: once the harness gives models a fair chance at the early game (every change declared), how far do the
cheap models get on real Terraria (tModLoader 1.4.4.9, real keyboard/mouse, screenshots only), how do they compare
with the published terrariabench.com runs and our earlier gateway runs, and which harness changes matter?

Run unattended on Omarchy from 04:43 to 11:21 UTC. **22 campaign runs** (18 × 15 game-min, 1 × 10 game-min frozen,
2 × 40 min, 1 Opus run stopped by its budget at 10 min) plus 3 smoke runs and one unpaid operator validation. Compact records: [`results/llm-campaign-2026-11-08/`](results/llm-campaign-2026-11-08/)
(`summary.json` one row per run, `results-table.md` full table, `runs/<run>/` manifest, result, extended score,
timeline, contact sheet, `ledger-gateway-openrouter.json`). Raw runs (frames, requests/responses, telemetry,
`desktop.mp4` for every run) stay on Omarchy under `runs/llm-campaign-2026-11-08/`.

**One run per cell, three worlds: signals, not rankings.** World-to-world spread is large (Luna 5 / 1 / 0).

## Headline

1. **Opus 5.5 scored 7 on the published catalog in 15 minutes** (wood_100 1:01, bench 1:23 and *placed* 1:27,
   wooden armour, underground 2:46, 18 torches crafted 5:53, furnace crafted 6:26), the best result in any of our
   campaigns and above the best published 8-hour run (4, Gemini 3 Flash). Its budget-capped replicate on world 303
   placed its bench at 1:17 and crafted torches at 7:51 before the cap stopped it at 10 minutes (score 4).
2. **The cheap models all stall at the same physical step: placing a station.** Haiku, Sonnet, Terra, Luna and the
   Jev combos crafted a work bench in 14 of 19 runs (often within a minute; the published `workbench_1` fires on
   crafting), but **none of the 17 cheap runs of 10–15 game-minutes placed one**. The single cheap placement was Terra at 27:59
   of its 40-minute run (then a furnace at 30:49, published score 7). Torches were crafted in 3 cheap runs.
3. **The published catalog mostly measures looting for cheap models.** Luna scored 5 with zero crafts (chest loot),
   Haiku 5 thanks to Torch Zombie drops; Luna's deepest run (cavern layer, 198 tiles) scored 0. The extended catalog
   with crafted/placed evidence separates these.
4. **Cheap-tier ranking by behaviour, not score:** Terra (explores, crafts benches/platforms/torches, underground in
   4/4 runs, the only cheap model to place a bench, given 40 min; $0.55–0.66 per 15 min) > Haiku (bench within ~1 min
   every time, stays near the surface for 15 min, quits 21–50 times per 15 min; $0.07–0.29) > Luna (explores/loots,
   rarely cuts trees in real time; $0.04–0.10). Sonnet repeated Haiku's pattern at 10–40× the cost ($2.95). Sol
   (1 run) scored 1 and hallucinated a placed bench.
5. **Length matters more than any prompt factor for cheap models:** at 40 minutes Terra placed a bench and crafted a
   furnace, and Haiku reached the cavern layer (259 tiles) and crafted torches; neither did either at 15 minutes on the
   same world.
6. **Planner + Jev executor is fast (0.39 s screenshot age) and cheap ($0.11–0.29) but hits the same wall:** the
   planner crafts the bench through UI clicks, nobody places it, and the catalog executor cannot follow pixel-level
   dig/place instructions.

## Profiles and harness changes

Three declared profiles (recorded in each `manifest.json` as `campaign_profile`, plus every individual flag):

| | reference (published reconstruction) | **camp-v1** (screening) | **camp-v2** (main comparison) |
|---|---|---|---|
| Hostiles | PvE off (suppressed) | **PvE on, hostile contact damage off** | same as camp-v1 |
| Screenshot | PNG, only on `look` | JPEG q85, **one after every `act`** | same |
| Interface card | none | v1 (keys, hotbar, crafting UI, screen geometry; no strategy) | **v3 = v1 + Smart Cursor (Left Ctrl) line** |
| Checkpoint tool | published events | published events | **+ crafted items and placed stations ("ext. log")** |
| Clock | real time | real time (one frozen-clock factor run) | real time |
| Remaining time | hidden | hidden | hidden |
| Continuation | "The run is still in progress. Continue playing."; 5 tool-less replies in a row end the run | same | same |
| Context | all text until 120k tokens; newest 8–15 screenshots | same | same |
| Worlds | 32000001 (reference world) | 32000301 (unseen) | 32000302, 32000303 (unseen) |

Code changes (this campaign):

| Change | Why | Where |
|---|---|---|
| GPT-5.6 Luna/Terra/Sol via the gateway's Unified route using the **OpenAI Responses API** (function tools + reasoning; encrypted reasoning items replayed each turn, `store=false`) | Chat completions on this route reject function tools unless `reasoning_effort=none` (HTTP 400 in the first smoke) | `terrariabench/unified.py`, `reference_live.py --provider unified` |
| Combo planner/executor accepts GPT planners and a Luna executor | Cross-vendor planner + fast executor | `terrariabench/combo.py` |
| Observer 0.7: `TERRARIABENCH_HOSTILE_DAMAGE=off` (`CanBeHitByNPC/Projectile` false): slimes and zombies spawn, can be killed and drop gel/lenses/torches, but cannot hit the player | PvE off removes gel (no torches/furnace); normal PvE turned every surface night into 13–43 deaths per 30 min in the pilot | `mod/TerrariaBenchObserver/ReferenceMode.cs` (`runs/observer-v07-build`, 0 errors/warnings) |
| Observer 0.7 journals `crafted` (recipe crafts) and `placed` (stations, torches, furniture) events | Possession milestones cannot tell crafting from looting, or crafting from placing | same |
| `--checkpoint-log extended`: the checkpoints tool also lists crafted/placed evidence | Models read `workbench_1` (fires on crafting) as "bench placed" | `reference_live.py` |
| Interface card v3 (one Smart Cursor line), validated by an unpaid operator run (`validate-smart-cursor-01`: off-target hold mines nothing; after one Left Ctrl the same hold mines 2 dirt) | Digging/placing need tile-exact aiming; Smart Cursor is a stock game control that relaxes it | `prompts/interface_card_v3.txt`, `tools/validate_smart_cursor.py` |
| Extended milestone catalog (19 facts: gel, torch/armour/furnace/bar/metal-gear **crafted**, bench/furnace/anvil **placed**, underground and cavern **layer entry** from the world header, ore tiers, bars, anvil, life crystal, lens/eye) scored offline next to the published subset | Published catalog misses layers, ores and anything the agent *did* | `tools/extended_score.py` |
| Unseen small Classic worlds 32000301–303 (crimson, crimson, corruption), observer 0.7; `LastLaunchedMods.txt` refreshed (a workshop update otherwise stalls startup) | No campaign world was used for harness development | `runs/fixtures/campaign-v07-*` |
| Campaign table, per-run ledger | Reporting | `tools/campaign_table.py`, `tools/campaign_ledger.py` |

Models and reasoning: Haiku 5.5 medium (8,192-token thinking budget, the only captured Haiku shape), Sonnet 5.5 low,
Opus 5.5 low (adaptive thinking, `effort: low`), Luna/Terra/Sol `reasoning.effort: low`. Jev 1.14 via OpenRouter
Decisions, one JPEG per decision. GPT prices were fitted from the gateway's own `X-Token-Usage-Cost` header on six
probes (Luna ≈ $0.17/$0.82, Terra ≈ $1.7/$8.2, Sol ≈ $3.4/$13.6 per M in/out); every GPT call's reported cost is the header.

## Results

Game time 15 min (900 s) unless stated, real time. Pub. = published-subset score (13 reconstructed checkpoints,
possession-based). Ext. = extended catalog facts reached (of 19). Milestone times are game mm:ss.

| Run | Setup | World | Game min | Pub. | Published milestones (game mm:ss) | Ext. | Extended highlights | Deaths | Depth | Contin. | Calls | USD |
|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|
| haiku-w301-15m | Haiku (medium), rt [camp-v1] | 301 | 15 | 4 | wood25 0:12, bench 0:34 | 1 | – | 0 | 5 | 31 | 91 | 0.07 |
| luna-w301-15m | Luna (low), rt [camp-v1] | 301 | 15 | 5 | wood25 11:22, torch10 10:04 | 3 | – | 1 | 74 | 1 | 63 | 0.05 |
| terra-w301-15m | Terra (low), rt [camp-v1] | 301 | 15 | 5 | wood25 12:11, bench 7:06, torch10 1:20 | 3 | underground 3:44 | 2 | 76 | 1 | 66 | 0.55 |
| sonnet-w301-15m | Sonnet (low), rt [camp-v1] | 301 | 15 | 4 | wood25 0:25, bench 0:51 | 2 | underground 12:06 | 0 | 76 | 30 | 129 | 2.95 |
| combo-terra-jev-w301-15m | Terra planner + Jev executor, rt [camp-v1-combo] | 301 | 15 | 5 | wood25 0:34, bench 2:42, torch10 12:37 | 1 | – | 0 | 1 | – | 395 | 0.29 |
| combo-luna-jev-w301-15m | Luna planner + Jev executor, rt [camp-v1-combo] | 301 | 15 | 4 | wood25 0:33, bench 3:36 | 1 | – | 0 | 37 | – | 501 | 0.11 |
| luna-refprofile-w001-15m | Luna (low), rt, no card, no shot-after-act, PNG, PvE off [reference-reconstructed-v1] | 001 | 15 | 0 | – | 0 | – | 1 | 119 | 4 | 88 | 0.04 |
| haiku-card3-w301-15m | Haiku (medium), rt, card v3 [camp-v1] | 301 | 15 | 5 | wood25 1:27, bench 1:54, torch10 12:45 | 1 | – | 0 | 6 | 45 | 138 | 0.20 |
| luna-card3-w301-15m | Luna (low), rt, card v3 [camp-v1] | 301 | 15 | 4 | wood25 1:45, bench 2:56 | 2 | – | 0 | 4 | 1 | 76 | 0.07 |
| haiku-card3-extlog-w301-15m | Haiku (medium), rt, card v3, ext. log [camp-v1] | 301 | 15 | 5 | wood25 1:06, bench 1:16, torch10 13:30 | 3 | – | 0 | 8 | 35 | 127 | 0.19 |
| luna-frozen-w301-10m | Luna (low), frozen [camp-v1] | 301 | 10 | 4 | wood25 4:36, wood100 6:23 | 1 | – | 0 | 20 | 2 | 111 | 0.10 |
| sol-w301-15m | Sol (low), rt [camp-v1] | 301 | 15 | 1 | torch10 12:18 | 2 | underground 2:42 | 2 | 76 | 1 | 51 | 0.80 |
| haiku-v2-w302-15m | Haiku (medium), rt, card v3, ext. log [camp-v2] | 302 | 15 | 4 | wood25 0:20, bench 0:51 | 2 | torch crafted 13:34 | 0 | 29 | 50 | 157 | 0.29 |
| haiku-v2-w303-15m | Haiku (medium), rt, card v3, ext. log [camp-v2] | 303 | 15 | 5 | wood25 6:54, bench 0:57, torch10 13:27 | 2 | – | 0 | 3 | 21 | 114 | 0.11 |
| luna-v2-w302-15m | Luna (low), rt, card v3, ext. log [camp-v2] | 302 | 15 | 1 | torch10 12:09 | 1 | – | 0 | 4 | 3 | 78 | 0.06 |
| luna-v2-w303-15m | Luna (low), rt, card v3, ext. log [camp-v2] | 303 | 15 | 0 | – | 3 | underground 3:27, cavern 9:40 | 1 | 198 | 5 | 77 | 0.06 |
| terra-v2-w302-15m | Terra (low), rt, card v3, ext. log [camp-v2] | 302 | 15 | 4 | wood25 4:48, bench 5:32 | 3 | underground 3:38 | 1 | 78 | 1 | 67 | 0.60 |
| terra-v2-w303-15m | Terra (low), rt, card v3, ext. log [camp-v2] | 303 | 15 | 5 | wood25 10:07, bench 10:29, torch10 12:37 | 3 | torch crafted 5:52, underground 7:59 | 2 | 129 | 1 | 73 | 0.66 |
| opus-v2-w302-15m | Opus (low), rt, card v3, ext. log [camp-v2] | 302 | 15 | 7 | wood25 0:29, bench 1:23, wood100 1:01, torch10 5:58, furnace 6:26 | 6 | bench placed 1:27, torch crafted 5:53, furnace crafted 6:26, underground 2:46 | 2 | 80 | 0 | 85 | 2.56 |
| terra-v2-w302-40m | Terra (low), rt, card v3, ext. log [camp-v2] | 302 | 40 | 7 | wood25 12:51, bench 14:21, wood100 32:11, torch10 1:43, furnace 30:49 | 7 | bench placed 27:59, furnace crafted 30:49, underground 2:42 | 2 | 111 | 12 | 190 | 2.50 |
| haiku-v2-w302-40m | Haiku (medium), rt, card v3, ext. log [camp-v2] | 302 | 40 | 5 | wood25 0:58, bench 1:26, torch10 31:54 | 6 | torch crafted 16:20, underground 23:11, cavern 33:51 | 0 | 259 | 109 | 360 | 0.92 |
| opus-v2-w303-15m | Opus (low), rt, card v3, ext. log [camp-v2] | 303 | 10 | 4 | wood25 0:30, bench 1:13 | 5 | bench placed 1:17, torch crafted 7:51, underground 2:40 | 2 | 73 | 0 | 49 | 1.30 |

Full table with every milestone column: [`results-table.md`](results/llm-campaign-2026-11-08/results-table.md).

### Who did what (all non-smoke runs; 15-min runs unless the 40-min runs are noted)

| | Haiku (6, one 40 min) | Luna (6, one frozen 10 min) | Terra (4, one 40 min) | Sonnet (1) | Combos + Jev (2) | Sol (1) | Opus (2, one capped at 10 min) |
|---|---|---|---|---|---|---|---|
| Bench crafted | 6/6 | 1/6 | 4/4 | 1/1 | 2/2 | 0/1 | 2/2 |
| Bench **placed** | 0/6 | 0/6 | 1/4 (40-min run, 27:59) | 0/1 | 0/2 | 0/1 | **2/2 (1:27, 1:17)** |
| Torches **crafted** | 2/6 (13:34; 16:20 in 40 min) | 0/6 | 1/4 (5:52) | 0/1 | 0/2 | 0/1 | 2/2 (5:53, 7:51) |
| Furnace crafted | 0/6 | 0/6 | 1/4 (40-min run, 30:49) | 0/1 | 0/2 | 0/1 | 1/2 (6:26) |
| Underground layer | 1/6 (40-min run; cavern 33:51) | 1/6 (cavern 9:40) | 4/4 | 1/1 | 0/2 | 1/1 | 2/2 |
| Continuations per 15 min (median) | 35 | 2.5 | 1 | 30 | – | 1 | 0 |
| Calls per 15 min (median) | 127 | 77 | 67 | 129 | 33–48 planner, 360–450 Jev | 51 | 85 |
| Median model latency | 3.0–3.2 s | 6.4–7.2 s | 6.6–7.3 s | 3.5 s | Jev 0.29–0.31 s | 6.6 s | 4.0 s |
| USD per 15 min | 0.07–0.29 | 0.04–0.10 | 0.55–0.66 | 2.95 | 0.11–0.29 | 0.80 | 2.56 |

## Comparison with published and earlier results

| Source | Profile / length | Best published-catalog score | What was reached |
|---|---|---:|---|
| terrariabench.com (7 published runs, 8 h budgets, ~6.1 h play) | PvE off, `api` harness | **4** (Gemini 3 Flash; wood_100 at 47 min) | wood only; Opus 4.7, GPT-5.5, Kimi K2.6, Qwen3.6: 0 |
| Our reference-gw (Oct 18–19) | reconstructed reference, 10–45 min | 5 (Opus, 30 min) | bench in 1–3 min, nothing after; Haiku/Sonnet 3–4 |
| Our pilot-30min (Oct 19–20) | normal PvE, card v1, 30 min | 6 (Opus; furnace + bars only in Opus runs) | 13–43 deaths per run in real time |
| **This campaign, reference profile** | Luna, 15 min | **0** | no tree cut; same score as GPT-5.5's published run |
| **This campaign, camp-v1/v2, cheap models, 15 min** | 15 min | 5 (Terra, Haiku, Luna; loot-assisted) | bench crafted, never placed; 2 runs crafted torches; Terra underground 3/3 |
| **This campaign, camp-v2, cheap models, 40 min** | 40 min | **7** (Terra) | Terra: bench placed 27:59, furnace 30:49; Haiku: cavern layer, torches crafted (5) |
| **This campaign, camp-v2, Opus** | 15 min | **7** | bench placed, armour, torches and furnace crafted; replicate placed its bench at 1:17 |

Extended-catalog re-score of the earlier campaigns (observer 0.3, so crafted/placed facts are unavailable):
[`prior-runs-extended-score.jsonl`](results/llm-campaign-2026-11-08/prior-runs-extended-score.jsonl). Best
were Sonnet hidden 45 min (5: cavern, three ore tiers) and Opus frozen-01 (5); the 30-minute normal-PvE Haiku and
Sonnet runs reached 1–2 facts (gel, sometimes looted ore) with 32–43 deaths.

Comparing like with like:
- **Gentle PvE removes the death loop without removing gel.** Cheap-model real-time runs had 0–2 deaths per
  15 min, all environmental since hostiles cannot hit (the timelines show drownings), against 13–43 per 30 min with
  normal PvE in the pilot, and every cheap camp run held gel by 3:07. It did not, by itself, produce torch crafting:
  3 of 19 cheap runs crafted torches.
- **On the reference profile the GPT-class cheap model behaves like the published GPT-5.5 run (0).** The same Luna
  under camp-v1 scored 5 (loot) on world 301, so profile choice moves cheap-model scores as much as model choice.
- **Opus under camp-v2 (15 min) beat every earlier Opus run** (reference 30 min: 5; pilot real-time 30 min: 5–6),
  and placed its bench 4 s after crafting it, the step no cheap model managed in 17 runs of 10–15 minutes.

## Factor tests (one factor at a time on world 301 unless stated; n = 1 each)

| Factor | Model | Without → with | Read |
|---|---|---|---|
| Interface card v1 → v3 (Smart Cursor) | Haiku | 0 Left Ctrl uses; pub 4 → 5 (looted torches), ext 1 → 1 | Haiku ignored the control |
| Interface card v1 → v3 | Luna | 32 Left Ctrl uses; no tree cut → wood 25 at 1:46 + bench | Helped Luna's motor control on 301, but Luna did not use it again on 302/303 (0 presses) |
| Checkpoint log published → extended | Haiku (card v3) | Read the log 22×, still claimed "crafted and placed a Work Bench" | No effect on belief or placement; harmless |
| Real time → frozen clock (10 game-min) | Luna (card v1) | 0 wood → **140 wood** (wood_100 at 6:23) | Fixes timing-limited skills (chopping before walking past); no crafting |
| camp-v1 → reference profile (different world) | Luna | 5 (loot) → 0 | Profile + world; not separable here |
| Single model → planner + Jev executor | Terra, Luna | bench, more wood; same placement wall | Executor speed is not the bottleneck |
| 15 → 40 game-min (world 302) | Terra | pub 4 → 7; ext 3 → 7: bench placed 27:59, furnace crafted 30:49 | The only cheap placement needed ~28 min of retries |
| 15 → 40 game-min (world 302) | Haiku | pub 4 → 5; ext 2 → 6: cavern 33:51 (259 tiles), torches crafted | Depth grows with time; placement does not; 109 continuations |

## What helped, what did not

Helped (declared, keep): **hostile contact off** (no death loops, gel available, slimes still killable);
**screenshot after every act** + JPEG (screenshot age 3–7 s); **Responses API for GPT** (reasoning with tools);
**frozen clock** for timing-limited play (Luna 0 → 140 wood); **extended catalog with crafted/placed evidence**
(scores what the agent did; exposed loot-only 5s and the 0-scoring cavern run); several unseen worlds.

Did not help measurably: Smart Cursor card (model-dependent adoption: Luna in 1 of 3 card-v3 runs, Haiku 2 presses in
5 card-v3 runs, Opus 4–5 presses per run); extended checkpoint feedback (Haiku ignores contradicting evidence); bigger GPT (Sol); Jev executor
for anything beyond chopping. Within 15 minutes nothing tried here got a cheap model to place a station; 40 minutes did
for Terra (once).

## Recommended benchmark protocol

1. **Two tracks, both reported:** (a) *published-reconstruction* track (PvE off, PNG, no card) for comparability with
   terrariabench.com; (b) **camp-v2** as the main early-game capability track: hostile contact damage off, screenshot
   after every act (JPEG q85), interface card v3, extended checkpoint log, hidden time, fixed continuation message.
2. **Score with both catalogs.** Publish the 13-checkpoint subset for comparability, but rank on the extended catalog
   with *crafted* and *placed* evidence (observer ≥ 0.7). Treat possession-only facts (torch_10, early_bar_5,
   furnace_1) as loot-sensitive.
3. **Clock:** real time as the default (cheap, 1:1 wall time); a frozen-clock companion run for models whose route
   latency exceeds ~5 s (all GPT-5.6 on this gateway: 6.4–7.2 s vs Haiku 3.0 s). Report latency, calls and
   screenshot age next to every score.
4. **Worlds and length:** ≥ 3 unseen worlds per cell (world spread here ≥ the model spread among cheap models).
   15 game-minutes separates Opus-class play (bench placed in ~1.5 min, furnace by ~6.5) from the rest, but cheap
   models only show placement/furnace/cavern progress at ~25–35 minutes: use **40 game-minutes** as the main length
   (Terra $2.5, Haiku $0.9, Luna ≈ $0.3 per run here) and 15 minutes for screening.
5. **Continuations:** keep the fixed message and report counts (Claude Haiku/Sonnet 20–50 per 15 min; GPT 1–5; Opus 0).
6. **Budget per cell (camp-v2, 15 game-min):** Luna ≈ $0.06, Haiku ≈ $0.15, Terra ≈ $0.6, Sol ≈ $0.8, Sonnet ≈ $3,
   Opus ≈ $2.6. Three worlds × Haiku, Luna and Terra at 40 minutes ≈ $11; adding Sol ≈ +$6, Sonnet ≈ +$24.
7. **Report claims vs evidence:** Haiku, Terra and Sol all reported a bench as "placed" when telemetry shows none;
   the journaled `placed` event is the only reliable signal.

## Spend

Ledger: [`ledger-gateway-openrouter.json`](results/llm-campaign-2026-11-08/ledger-gateway-openrouter.json) (per run,
from each run's accounting; GPT costs from the gateway's `X-Token-Usage-Cost` header, Claude costs at list price).

| Route | Cap | Reported | Uncertain reservations | Conservative |
|---|---:|---:|---:|---:|
| AMD gateway (Anthropic + Unified), incl. $0.025 price probes | $17.00 | **$14.37** | $1.50 | **$15.87** |
| OpenRouter (Jev executor) | $0.50 | **$0.14** | $0 | **$0.14** |

Uncertain reservations are requests in flight when a run's clock ran out (e.g. Sol $0.83, Terra 40 min $0.46) plus
one HTTP 400 smoke call; they were probably not or only partly billed but are kept in the conservative total. The
queue refused any job whose cap would push conservative spend past $16.90; the second Opus run was therefore
started with a $2.30 cap and stopped itself at 10 game-minutes. All paid calls ended at 11:21 UTC.

## Limitations

- One run per cell; three worlds; game date not pinned (8 Nov, no seasonal event active).
- Gentle PvE changes difficulty: hostiles cannot hit or knock back the player but still spawn, can be killed and drop
  loot, so night brings Torch Zombies whose drops inflate `torch_10` by possession. Drowning and fall damage remain.
- `workbench_placed`/`torch_crafted` need observer 0.7; earlier campaigns cannot be compared on those facts.
- Combo runs used combo-v2 (planner UI sessions) with card v1 in the planner prompt (combo.py) and the camp-v1 world settings.
- The Responses-API GPT loop and the Anthropic loop share prompt, tools, context policy and continuation policy, but
  provider-side reasoning differs (OpenAI effort low vs Anthropic adaptive low / Haiku 8k budget).

## Per-run insights (written after each run)

- **haiku-w301-15m** (Haiku medium, camp-v1): wood/bench by 0:35 as always, then 13 minutes of 1-tile-wide digging at screen centre (max depth 5) and 31 "I'm stopping here" replies. 26 gel held, never a torch; bench crafted, never placed.
- **luna-w301-15m** (Luna low): never chopped a tree (axe swings 1–3 tiles off the trunk), but explored 200+ tiles right, found two chests and a cave: torches, 5 iron bars, rope, 87 wood. Published score 5 comes entirely from loot; zero crafts. One drowning/fall death (hostile contact is off). 7.2 s median latency.
- **terra-w301-15m** (Terra low): looted 14 torches at 1:20, reached the underground layer at 3:44 through a cave, crafted a bench at 7:06 and then *reported it placed*; telemetry shows no placement. Two drownings. $0.55 for 15 min (OpenAI prompt caching keeps it ~5× cheaper than Sonnet).
- **sonnet-w301-15m** (Sonnet low): the Claude pattern again: wood 0:25, bench 0:51 (crafted, never placed), 17 gel, no torch, underground at 12:06, 30 continuations. $2.95: by far the most expensive per minute of the cheap tier.
- **combo-terra-jev-w301-15m** (Terra planner + Jev executor, 1 screenshot/decision, 0.39 s shot age): Jev chops well (wood 25 at 0:34); the planner crafted a bench at 2:42 through a UI session and then spent 12 minutes ordering "place it" and "dig a 2-wide shaft" with pixel coordinates the catalog executor cannot follow (depth 1). 19 looted torches, 34 gel, no torch crafted. $0.29.
- **combo-luna-jev-w301-15m** (Luna planner + Jev): same shape, bench crafted at 3:36, never placed, depth 37 (Jev's `dig_down`), 26 gel. $0.11, the cheapest run with a bench.
- **validate-smart-cursor-01** (unpaid operator check): holding the pickaxe 3 tiles off-target mines nothing; one Left Ctrl press through the controller shows the yellow Smart Cursor outline on the nearest tile and the same hold mines 2 dirt. Interface card v3 (card v1 + one Smart Cursor line) is therefore a real, executable control fact.
- **luna-refprofile-w001-15m** (Luna low on the reconstructed published profile: PvE off, PNG, no card, no screenshot after act, world 32000001): published score **0**, like GPT-5.5 and four other published models. It never cut a tree; it fell/dug to 119 tiles and died once. Same model under camp-v1 on world 301 scored 5 (loot), so the profile matters as much as the model for GPT-class agents.
- **haiku-card3-w301-15m** (Haiku, card v3 = Smart Cursor line): never pressed Left Ctrl (0 of 138 calls), so the card did nothing for control. It read the published `workbench_1` checkpoint (fired when the bench is *crafted*) as "a workbench is placed in the world" and from then on wrote "I'm stopping here" reports (45 continuations). 55 torches from Torch Zombies (looted, not crafted). The published checkpoint wording actively misleads.
- **luna-card3-w301-15m** (Luna, card v3): Luna *did* use Smart Cursor (32 Left Ctrl presses) and, unlike its card-v1 run on the same world, cut trees (wood 25 at 1:46) and crafted a bench (2:56), never placed; it stayed near spawn (depth 4) instead of exploring and looting. Published 4 vs 5, but the 4 is earned rather than looted.
- **haiku-card3-extlog-w301-15m** (Haiku, card v3 + extended checkpoint log): read the log 22 times, which listed "crafted Work Bench" and no placement, and still wrote "Crafted and placed a Work Bench" in every stop report (35 continuations). Again no Left Ctrl. Truthful feedback did not correct Haiku's belief; it did no harm, so camp-v2 keeps it.
- **luna-frozen-w301-10m** (Luna, card v1, frozen clock, 10 game-min = 25 wall-min): with the game paused during inference Luna chopped steadily (wood 25 at 4:36, **wood_100 at 6:23**, 140 wood), which it never did in real time with the same card, but it never opened the crafting list (no bench) and did not explore (depth 20). Frozen clock fixes timing-dependent skills (chopping a trunk before walking past it), not the crafting/placing gap.
- **sol-w301-15m** (GPT-5.6 Sol low, camp-v1, one of the few large-model runs): published score **1** (looted torches). Like Luna and Terra it went into the cave beside spawn instead of cutting trees, drowned twice, and at 7:45 declared "gathered wood, crafted and placed a workbench" — none of which happened (0 wood all run). $0.80. Bigger GPT did not mean better play here; its failure is the same unverified-belief pattern.
- **haiku-v2-w302-15m** (Haiku, camp-v2, unseen world 302): the campaign's first **crafted torches** (13:34, from its own gel and wood) and 6 wood platforms, two benches crafted, none placed; depth 29; 50 continuations. One Left Ctrl press in 157 calls.
- **haiku-v2-w303-15m** (Haiku, camp-v2, world 303): wood/bench in under a minute, then the usual stall at depth 3; published 5 only because Torch Zombies dropped 32 torches at night.
- **luna-v2-w302-15m** (Luna, camp-v2): no Left Ctrl, no wood; published 1 from 53 looted torches; 32 gel unused. Luna's Smart Cursor adoption on world 301 did not repeat.
- **luna-v2-w303-15m** (Luna, camp-v2): published **0**, yet the deepest run of the campaign so far: underground at 3:27, **cavern layer at 9:40**, 198 tiles down through caves, one death. The published catalog cannot see this at all.
- **terra-v2-w302-15m** (Terra, camp-v2): bench ×2 and 8 wood platforms crafted, underground at 3:38 via a cave, gold ore at 8:32, one drowning; wood_25 only at 4:48 because it explored first. Bench still never placed.
- **terra-v2-w303-15m** (Terra, camp-v2): **crafted torches at 5:52** (6) from its own gel, underground at 7:59, 129 tiles deep, bench crafted 10:29 (not placed). Terra is the only model that combined exploration with a crafting step in both camp-v2 worlds.
- **opus-v2-w302-15m** (Opus 5.5 low, camp-v2, one of the few large-model runs): published score **7** in 15 minutes, the best run in any of our campaigns and above the best published 8-hour run (4). Wood 100 at 1:02, the campaign's **only placed work bench** (1:27, 4 s after crafting), wooden breastplate + greaves (1:40), underground layer 2:46, 18 torches crafted 5:54, furnace crafted 6:26 (not placed: it stayed underground). 0 continuations, 4 Left Ctrl presses, 2 drownings. $2.56.
- **terra-v2-w302-40m** (Terra, camp-v2, 40 min, same world as the 15-min Terra run): published **7**, extended 7. Looted torches early, underground at 2:42, lead and copper ore by 7:49, then after ~28 minutes of failed attempts **placed a work bench (27:59)**, crafted a furnace (30:49), wooden bow and table; wood_100 at 32:11. The only cheap-model bench placement in the campaign needed 2.7× the screening length. 12 continuations, 2 drownings, $2.50.
- **haiku-v2-w302-40m** (Haiku, camp-v2, 40 min): extended 6, published 5. Bench at 1:27 (crafted, never placed), torches crafted 16:20, then it finally dug: underground 23:11, **cavern 33:51, 259 tiles**, lead/platinum ore. 109 continuations (one every 22 s) and $0.92. Length helped Haiku's depth, not its placement.
- **opus-v2-w303-15m** (Opus, camp-v2, world 303, run with a $2.30 cap to stay inside the campaign budget; the cap stopped it at 10:10 game time): bench crafted 1:13 and **placed 1:17**, underground 2:40, lead ore 2:54, torches crafted 7:51, wooden sword; published 4, extended 5. Confirms on a second world that Opus places its station immediately.
