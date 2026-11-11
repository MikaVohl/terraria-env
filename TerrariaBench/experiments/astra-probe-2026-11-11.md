# GPT-6 Astra on official Terraria (default-v2, pure computer use), 2026-11-11

Question: how far does **GPT-6 Astra** get in unmodified Terraria through the default-v2 interface (one `act` tool:
key/mouse primitives in pixel coordinates, a 1024² JPEG screenshot after every act; no scripts, no game API, no
game-specific tools), and what does it cost, under a **$10 hard cap** on the AMD gateway (conservative accounting:
reported + uncertain + running caps)?

**Model.** `gpt-6-astra` on the gateway's Unified route (`/models` lists it, owned by AzureOpenAI, 1.05M context,
128k max output). Deployment recorded in every manifest as `model.deployment = gpt-6-astra-2026-09-03` (TerraBotAPI's
probe); every Responses reply names it `dvue-aoai-006-gpt-6-astra` (per call in `calls.jsonl`). Price in
`terrariabench/unified.py`: $8.50/M input, $34/M output (fitted from TerraBotAPI's two header-cost probes, 2,114 + 4
tokens = $0.0181, 14 + 584 = $0.0200). **Cached input is billed at $0.68/M** (the `/models` cache-read price; checked
on every cached call here, e.g. 22,628 prompt / 21,144 cached / 109 out = $0.0305), so the fitted price is the
cache-miss price and an upper bound. **Reasoning effort: medium** (stated choice; see Design).

**Protocol.** default-v2 unchanged (no factor flags: `manifest.factors = {}`), **paused clock**, 20 game-minutes,
fresh copies of the LunaFactors fixtures `runs/fixtures/lf-v07-3200040{1,4}` (worlds identical to the landscape
fixtures). Runs through `tools/parallel_queue.py` on one isolated Xwayland slot with per-run `desktop.mp4`, then
`run_evidence`, `extended_score`, `clock_check`. Campaign: `runs/astra-probe-2026-11-11/` on Omarchy.

## Headline

1. **Astra made the most extended progress of any screen-track (computer-use) run we have, in 18.4 game-minutes:
   published 7, extended 12** (world 401, paused, medium; previous screen-track maximum: extended 7). Work bench
   crafted 0:47 and placed 0:48, full wooden armour 0:53, torches crafted 6:21, underground 6:55, copper 7:30,
   gold-tier ore 8:04, cavern layer 9:39, **furnace crafted 10:23 and placed 15:13, first bars smelted 15:14 (gold,
   tungsten)**, 10 torches 18:04, lens 13:41. On the default-v2 worlds 401–404 nobody had crafted a furnace (landscape,
   LunaFactors; best earlier run there: Opus paused, published 5 / extended 7 in 15.6 censored minutes); in the older
   llm-campaign 2026-11-08 (world 302) Opus (15 min) and Terra (40 min) crafted one and reached published 7, but no
   screen-track run had placed a furnace or smelted a bar. (The programmatic TerraBot track, with a game API, reached
   extended 15; not comparable.)
2. **It is censored by money, not by play.** The run stopped at 18.4 of 20 game-minutes (`dollar reservation limit
   reached`) because one HTTP 429 at call 8 kept its full $2.09 reservation as an uncertain charge under the
   conservative rule (a 429 is almost certainly unbilled; at its spend rate the missing 1.6 minutes would have cost
   ≈ $0.45 [INFERENCE]). n = 1 world for
   the full-length run plus one 1.5-minute probe on world 404: **a single, strong data point, not a ranking.**
3. **Cost: $0.27 per game-minute** in the main run (88 calls, 12.6 game-s per call), $0.58 in the probe (short
   batches, 3.3 game-s per call): 23–44× Luna6-high and ≈ 0.85× Opus-low paused per game-minute. A full 20-minute paused
   run costs ≈ $5.4 reported and needs a ≈ $9.6 cap (expected + 2 reservations of $2.09), so **$10 buys exactly one
   default-v2 run** — worlds 402/403 and any variant were out of budget.
4. **Failure modes are survival and a wrong model of the input tool, not perception or menus.** 12 deaths (night-time
   surface fights with a shortsword that does not auto-swing; two in its own mine shaft), no accidental world exit,
   0 invalid tool calls, 0 no-action turns. From call 54 on it wrongly believed mouse buttons were not
   released between primitives and padded batches with middle clicks; it also suspected a coordinate offset and toggled
   Smart Cursor several times. Aiming in the world and in the inventory/crafting UI was accurate throughout.

## Design

- **Effort.** "Strongest allowed effort the budget supports": Astra's per-call price is ~95× Luna6's, and for Luna6
  high effort cost 2.4–5× medium per game-minute (more, shorter calls and longer histories). A 1.5-minute probe at
  medium projected ≈ $5–12 per 20-minute run (batch length decides), i.e. at most one run in $10 — high would not have
  fit one run. So medium for both runs.
- **Cost probe** (p00): 90 game-s, medium, paused, world 404 (keeps 401–403 fresh), cap $3.00. Result $0.86 = $0.58
  per game-minute at 3.3 game-s per call; cache-hit calls cost $0.017–0.03, a cache miss (every 8th call, when
  default-v2's 8-image block is trimmed and the prompt prefix changes) $0.11–0.12.
- **Primary** (m01): default-v2, paused, 20 game-min, medium, world 401 (the world with the most comparison runs:
  landscape Opus/Terra/Haiku/Luna and all LunaFactors cells), cap = $10 − probe spend = **$9.13**. The harness reserves
  $2.09 per call (180k input + 16,384 output tokens at the fitted prices), so the run could spend ≈ $7 before the gate
  closed. No second world, real-time run or Vals-style variant (e.g. a notes field) was affordable afterwards
  ($2.09 conservative headroom left = one reservation).

## Results

Pub. = published 13-checkpoint subset (possession-based, counts `wood_10`). Ext. = extended catalog facts (of 19,
`tools/extended_score.py`). Times are game m:ss. Full per-run table with every checkpoint column:
[`results-table.md`](results/astra-probe-2026-11-11/results-table.md).

| Run | World | Game min | Stop | Pub. | Ext. | Key facts (game time) | Crafted | Placed | Deaths | Depth (tiles) | Calls | No-action | Invalid tools | Game-s / call | Latency median / p90 / max (s) | Wall min | Wall / game-min | USD reported | USD / game-min |
|---|---|---:|---|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| p00-med-pa-probe-w404 | 404 | 1.5 | game time (probe) | 4 | 2 | wood 25 0:08, bench 0:19, bench placed 0:21, wood armour 0:24 | Work Bench 2, Sign, Wooden Sword, Wood Helmet/Greaves/Breastplate | bench | 0 | 35 | 27 | 0 | 0 | 3.3 | 6.2 / 12.7 / 21.6 | 5.2 | 3.5 | 0.8634 | 0.576 |
| **m01-medium-pa-20m-w401** | 401 | **18.4** (censored, $ cap) | dollar reservation limit | **7** | **12** | wood 100 0:33, bench 0:47, bench placed 0:48, wood armour 0:53, gel 2:16, torch crafted 6:21, underground 6:55, copper/tin 7:30, silver/gold-tier ore 8:04, cavern 9:39, furnace 10:23, lens 13:41, furnace placed 15:13, bar smelted 15:14, torch 10 18:04 | Work Bench 1, Wood Platform 2, Wooden Sword, Wood Helmet 2/Breastplate/Greaves, **Torch 24, Furnace 1, Gold Bar 1, Tungsten Bar 1** | bench 1, torch 8, furnace 1 | 12 | 208 | 88 (87 + one HTTP 429 retried) | 0 | 0 | 12.6 | 8.4 / 26.3 / 53.9 | 36.8 | 2.0 | 4.9588 | 0.269 |

Workbench placed: yes in both runs (0:48 / 0:21). Furnace: crafted and placed in m01. Left world: never. Clock check
(m01): 1,106 heartbeats for 1,106 game-s, 89 freezes, **0 heartbeats while frozen**, 60.0 Hz unfrozen, screenshot
age 0.06 game-s (8.4 s wall) — paused as specified. Game vs wall: 18.4 game-min in 36.8 wall-min (18.5 min frozen
for model calls).

Probe on world 404 against the only other world-404 runs (LunaFactors Luna6, 20 min): at 90 game-s Luna6 high had
published 3 / extended 0, low 0 / 0; over their full 20 minutes neither placed a bench. Astra placed one at 0:21.

### Against the landscape and LunaFactors baselines

World 401, same fixtures, paused unless stated. "At 18:26" counts only facts reached by 1,106 game-s (Astra's censor
point) so every run gets the same horizon; runs shorter than that (10-min screening, censored runs) are shown with their
own length.

| Run | Model (effort) | Clock | Played (min) | Pub. at 18:26 | Ext. at 18:26 | Bench placed | Torch crafted | Furnace | Bar | USD / game-min |
|---|---|---|---:|---:|---:|---|---|---|---|---:|
| **m01 (this)** | **Astra (medium)** | paused | 18.4 | **7** | **12** | 0:48 | 6:21 | crafted 10:23, placed 15:13 | 15:14 | 0.27 |
| c2-opus-pa | Opus 5.5 (low) | paused | 15.6 ($ cap) | 5 | 7 | 0:31 | 4:20 | – | – | 0.32 |
| c1-opus-rt | Opus 5.5 (low) | real time | 20 | 4 | 4 | 8:56 | – | – | – | 0.18 |
| c3-combo-rt | Opus (low) + Jev | real time | 20 | 6 | 5 | 2:25 | – | – | – | 0.06 |
| c4-combo-pa | Opus (low) + Jev | paused | 20 | 4 | 4 | 2:26 | – | – | – | 0.10 |
| a4-terra-pa | Terra 5.6 (low) | paused | 20 | 3 | 3 | – | – | – | – | 0.036 |
| a1-haiku-think-pa | Haiku 5.5 (medium) | paused | 20 | 3 | 2 | – | – | – | – | 0.023 |
| a3-luna-pa | Luna 5.6 (low) | paused | 20 | 1 | 3 | – | – | – | – | 0.011 |
| e02-high-pa-20m | Luna6 (high) | paused | 20 | 5 | 4 | 8:12 | 15:15 | – | – | 0.017 |
| e06-high-know-pa-20m | Luna6 (high) + knowledge card | paused | 20 | 6 | 3 | 0:42 | 7:02 | – | – | – |
| e04-high-rt-20m | Luna6 (high) | real time | 20 | 6 | 3 | 6:28 | – | – | – | – |
| a05-eff-high | Luna6 (high) | paused | 10 | 6 | 4 | – | yes | – | – | – |
| b00-haiku-base-pa | Haiku 5.5 (medium) | paused | 10 | 4 | 6 | yes | – | – | – | – |

Cell means for context (all three worlds, 20 game-min, paused): landscape Haiku 2.3 ext, Luna 2.0, Terra 2.7, Opus
7.0 (one censored run); LunaFactors Luna6 high e02 published 4.7 / extended 3.0, high + knowledge card e06 5.3 / 3.3
(bench placed 3/3). At Opus' censor point (15:35) Astra already had published 6 / extended 12 vs Opus' 5 / 7; at the
10-minute screening horizon Astra had published 5 / extended 8 vs the best 10-minute LunaFactors cell (Luna6 high,
w401) 6 / 4 and Haiku medium 4 / 6.

## Cost per game-minute

| Configuration | USD / game-min | Calls / game-min | Wall min / game-min | Latency median (s) |
|---|---:|---:|---:|---:|
| Astra medium, paused, probe (1.5 min, short batches) | 0.576 | 18 | 3.5 | 6.2 |
| **Astra medium, paused, main (18.4 min)** | **0.269** | 4.8 | 2.0 | 8.4 |
| Opus 5.5 low, paused (landscape c2) | 0.32 | 8.7 | 1.6 | 4.0 |
| Luna6 high, paused (LunaFactors) | 0.006–0.012 | 6–8 | 2.1–2.6 | 8.3–13.3 |
| Luna6 low, paused (LunaFactors) | 0.002–0.004 | 3–6 | 1.4–1.7 | 4.5–6.3 |

Where Astra's money goes (m01, 87 billed calls): mean prompt 24.8k tokens (max 42.1k, the 120k trim never fired),
mean output 217 tokens (reasoning tokens ≈ 14 per call at medium), 83 % of input tokens served from cache. Cache-hit
calls cost $0.02–0.08; the 12 cache-miss calls (every 8th, at default-v2's 8-image block trim) cost $0.12–0.28 each
— **$1.97 of $4.96 (40 %)**. Batch length is the other lever: long 16-primitive mining batches (≈ 30 game-s each)
made the main run half as expensive per game-minute as the probe. Expected full 20-minute run: ≈ $5.4 reported,
cap ≈ $9.6.

## Qualitative notes (timeline, reasoning summaries, frames)

- **Perception and aiming: good.** First tree hit on call 0–1 (wood 25 at 0:12); inventory and crafting clicks land on
  the right slots (crafting list at x ≈ 40, armour slots at x ≈ 918–961), bench crafted on its first crafting-menu
  visit and placed one click later; full wooden armour crafted and equipped within 53 s. Ore recognised and mined in the
  shaft (copper, gold, tungsten in inventory).
- **Strategy: a vertical shaft.** From call 38 (≈ 6:20 game) it selects the pickaxe (`2`) and repeats "hold left on the tile under
  the feet, 2 s" 14× per call, with a torch slot (`0`) click between batches: 0 → 208 tiles in ≈ 4 game-minutes,
  cavern layer at 9:39. It then went back to the surface to smelt: furnace crafted 10:23 (call 51) but placing it took
  until 15:13 (several attempts at calls 54–56 and 74–75), then the first two bars.
- **Survival is the weak spot.** 12 deaths, most at night on the surface (zombies/demon eyes; it reasoned "the wooden
  sword doesn't auto swing, and that's causing me to die" and considered turning on autoswing in the settings), two at
  the bottom of its own shaft (206/208 tiles). Each death respawns it at the surface, away from the shaft.
- **Wrong model of the input tool.** Repeated reasoning that "clicks aren't releasing between calls" (calls 5, 50 and
  more); from call 54 it inserted middle-button clicks between primitives as a "neutral" release. It also suspected
  "screenshots show offset action coordinates" (call 32, "off by 170px") and toggled Smart Cursor (`leftctrl`) on and
  off several times (calls 20–70). The harness releases every input at the end of each primitive and leaves ≥ 35 ms
  (≈ 2 game updates) between a release and the next positioned press (`linux_control.XGameControl.act`), and
  coordinates are window pixels, so the padding and toggles were unnecessary; they cost calls, not progress.
- **Menus: no forfeit.** It never left the world (the LunaFactors Save & Exit hazard), and made no invalid calls.
- **Time awareness.** It tracks the session clock from the prompt ("about 69 seconds" left in the probe, "17 minutes
  for 510 actions", "about five minutes left") — once it read the in-game clock as session time ("4 hours 42 minutes
  left").
- Reasoning summaries (`summary: auto`) are often generic and do not always match the action batch; treat them as
  colour, not evidence.

## Spend

Ledger: [`ledger.json`](results/astra-probe-2026-11-11/ledger.json) (`tools/campaign_ledger.py`; reported = gateway
`X-Token-Usage-Cost` per call; uncertain = failed sent attempts at their full reservation).

| Item | Cap | Reported | Uncertain | Conservative |
|---|---:|---:|---:|---:|
| p00 probe (90 game-s) | $3.00 | $0.8634 | $0 | $0.8634 |
| m01 main (18.4 game-min) | $9.13 | $4.9588 | $2.0871 (one HTTP 429, 4 s, retried) | $7.0459 |
| `/models` listing (ID/price check) | – | $0 | $0 | $0 |
| **Total AMD gateway** | **$10.00** | **$5.8222** | **$2.0871** | **$7.9093** |

The queue refused any start whose spend + running caps + own cap would exceed $10.00 (`--gateway-budget 10`); within
a run the harness refuses a call unless spend + uncertain + one reservation stays under the run cap, so the $10 bound
held including reservations. TerraBotAPI's earlier Astra price probe ($0.038) belongs to its own ledger. No other
models or routes were used.

## Limitations

- **n = 1** full-length run (world 401, censored at 18.4 min) plus a 1.5-minute probe (world 404). World spread in
  LunaFactors is large; the matched-time table compares single runs on one world.
- Astra ran at medium effort; Opus at low, Luna/Terra at low, Luna6 at high: effort settings differ across models (each
  is the setting its campaign used; LunaFactors recommends the strongest allowed per model).
- Censoring: the 429's reservation, not play, ended the run 1.6 minutes early; the last 1.6 minutes (night) would
  most likely have added deaths rather than facts, but this is untested.
- Real-time clock not measured (Astra's 8.4 s median latency would leave ≈ 8 s of unseen game per screenshot).

## Files

- `terrariabench/unified.py`: `gpt-6-astra` (price, deployment, fitted-probe note); `tools/campaign_table.py`: "Astra"
  label. Harness and protocol otherwise unchanged.
- Job script: [`astra-probe-2026-11-11.sh`](astra-probe-2026-11-11.sh) (`PHASE=probe`, `PHASE=main CAP=9.13 WORLD=1`).
- Compact records: [`results/astra-probe-2026-11-11/`](results/astra-probe-2026-11-11/) — `summary.json`,
  `results-table.md`, `ledger.json`, `jobs/` (both queued commands + queue log), `runs/<run>/` (manifest, result,
  accounting, termination, extended score, clock log, provider failures, evidence timeline + contact sheet, and
  `calls.jsonl`: per-call returned model, prompt/cached/output/reasoning tokens, header USD, latency).
- Raw runs (frames, requests/responses, telemetry, inputs) and **videos** on Omarchy:
  `~/Projects/TerrariaBench/runs/astra-probe-2026-11-11/m01-medium-pa-20m-w401/desktop.mp4` (45 MB, 36.8 wall-min),
  `.../p00-med-pa-probe-w404/desktop.mp4` (11 MB).
- Omarchy left clean: queue exited (`dg-STOP`, then removed), isolated display `:11` taken down, no game or harness
  process running, `~/tb-queue/dg-jobs` and `dg-running` empty.
