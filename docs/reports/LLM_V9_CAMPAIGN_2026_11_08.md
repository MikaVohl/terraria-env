# LLM campaign on Terraria-Lite v9 — November 8, 2026

Status: **complete**, 04:25–07:45 UTC, November 8, 2026. 18 paid episodes, every one
replay-verified (one Jev screen with the h2 verifier fix, see below). Compact per-run records:
`experiments/llm-v9-20261108/records/*.json`; frozen configs `configs/`, harness copies
`harness/h1…h5/`, spend ledger `ledger.json`. Raw journals/tapes stay local (not committed).

## Headline

**Claude Haiku 5.5 (no thinking) on the macro track reaches 67.4% weighted on two of three
full 10,000-step v9 episodes (32/38 achievements, alive, ≈$0.90-1.03 each) and died on the
third at step 3,636 (24.0%).** The three-world mean is **53.0%** (tier success
94.9/80.6/54.2/13.3%). The generic PPO v9 pilot at 1B steps scores 57.5% (tiers
100/81/66/14%, figures from the campaign brief). On the two worlds where Haiku survived it beat the PPO pilot's mean;
the death on the third world decides Haiku's mean, not missing knowledge. GPT-5.6 Terra is stronger per step
(58.9% at step 5,968 when its $3 guard stopped it; 39.5% after 1,609 steps on world 3) but
costs ≈6x Haiku per call, so no Terra episode finished 10,000 steps. Luna has a 24.0%
three-world mean with three deaths. A Terra-planner/Luna-executor mix (17.8%, died) and Jev
(9.3% primitive, 18.6% with macros) trail.

This is a development comparison on 3+1 public worlds, one attempt per cell, with a declared
game-knowledge guide, text view and macro actions. It is **not** a like-for-like replacement for
the PPO headline: PPO learns from scratch on unseen worlds and its score averages many episodes.

## Results

### Long runs (worlds 33,000,001–003, 10,000-step budget, macro track, harness h3)

| Run | Model | Track | Steps (end) | Weighted % | Ach. | Tiers 1/2/3/4 | W% @1000 / @1500 / @3000 / @5000 / @10000 | Calls | Ticks/call | Illegal | $ accounted / reported | Wall min | Harness | Replay verified |
|---|---|---|---|---:|---:|---|---|---:|---:|---:|---|---:|---|---|
| L-terra-M-s1 | gpt-5.6-terra | macro | 5968 (cost_budget) | 58.91 | 30 | 13/11/6/0 | 24.03 / 24.03 / 52.71 / 58.91 / - | 400 | 14.92 | 0.0147 | 2.815 / 2.087 | 66.3 | h3 | yes |
| L-terra-M-s2 | gpt-5.6-terra | macro | 1464 (cost_budget) | 13.95 | 14 | 12/2/0/0 | 13.95 / - / - / - / - | 135 | 10.84 | 0.0232 | 0.877 / 0.648 | 21.8 | h3 | yes |
| L-terra-M-s3 | gpt-5.6-terra | macro | 1609 (cost_budget) | 39.53 | 23 | 13/6/4/0 | 20.93 / 36.43 / - / - / - | 142 | 11.33 | 0.023 | 0.963 / 0.710 | 23.6 | h3 | yes |
| L-haiku-M-s1 | claude-haiku-5-5 | macro | 10000 (action_budget) | 67.44 | 32 | 13/12/6/1 | 23.26 / 25.58 / 27.91 / 41.09 / 67.44 | 881 | 11.35 | 0.0283 | 1.027 / 1.027 | 158.6 | h3 | yes |
| L-haiku-M-s2 | claude-haiku-5-5 | macro | 3636 (death) | 24.03 | 17 | 11/5/1/0 | 13.18 / 17.83 / 24.03 / 24.03† / 24.03† | 284 | 12.8 | 0.0212 | 0.290 / 0.290 | 50.8 | h3 | yes |
| L-haiku-M-s3 | claude-haiku-5-5 | macro | 10000 (action_budget) | 67.44 | 32 | 13/12/6/1 | 24.03 / 27.91 / 34.11 / 46.51 / 67.44 | 812 | 12.32 | 0.021 | 0.897 / 0.897 | 142.3 | h3 | yes |
| L-luna-M-s1 | gpt-5.6-luna | macro | 9881 (death) | 30.23 | 19 | 12/4/3/0 | 17.05 / 17.05 / 19.38 / 29.46 / 30.23† | 709 | 13.94 | 0.0264 | 0.498 / 0.369 | 110.1 | h3 | yes |
| L-luna-M-s2 | gpt-5.6-luna | macro | 9059 (death) | 34.88 | 21 | 12/6/3/0 | 20.16 / 20.16 / 34.88 / 34.88 / 34.88† | 767 | 11.81 | 0.039 | 0.557 / 0.412 | 120.7 | h3 | yes |
| L-luna-M-s3 | gpt-5.6-luna | macro | 289 (death) | 6.98 | 7 | 6/1/0/0 | 6.98† / 6.98† / 6.98† / 6.98† / 6.98† | 33 | 8.76 | 0.0346 | 0.018 / 0.013 | 5.1 | h3 | yes |
| L-mix-TL-s1 | gpt-5.6-luna | macro | 1918 (death) | 17.83 | 15 | 12/2/1/0 | 13.95 / 13.95 / 17.83† / 17.83† / 17.83† | 138 | 13.9 | 0.0193 | 0.460 / 0.363 | 22.0 | h5 | yes |

† = after death (score carried forward); `-` = not observed (cost-censored before that step).

| Model (3 worlds) | Mean weighted % | Per-world | Tier success 1/2/3/4 | Deaths | $ accounted / reported |
|---|---:|---|---|---:|---|
| Haiku 5.5, no thinking | **53.0** | 67.4 / 24.0† / 67.4 | 94.9 / 80.6 / 54.2 / 13.3 % | 1 | 2.21 / 2.21 |
| GPT-5.6 Terra, low | 37.5 (all cost-censored) | 58.9 (5,968 steps) / 14.0 (1,464) / 39.5 (1,609) | 97.4 / 52.8 / 41.7 / 0 % | 0 | 4.66 / 3.45 |
| GPT-5.6 Luna, low | 24.0 | 30.2† / 34.9† / 7.0† | 76.9 / 30.6 / 25.0 / 0 % | 3 | 1.07 / 0.80 |
| PPO generic, 1B steps (v9 pilot, from the brief) | 57.5 | many episodes | 100 / 81 / 66 / 14 % | — | GPU |

Action efficiency at a common horizon (weighted % at step 1,500; † dead): Terra 24.0 / 14.0 (1,464) / 36.4;
Haiku 25.6 / 17.8 / 27.9; Luna 17.1 / 20.2 / 7.0†. Terra leads per step on every world where it
was observed. Haiku's later gains are from surviving long enough to finish the chain (anvil → metal
sword → silver/gold → Skeleton → lens).

### Screening (world 33,000,101, 1,500-step budget)

| Run | Model | Track | Steps (end) | Weighted % | Ach. | Tiers 1/2/3/4 | W% @500 / @1000 / @1500 | Calls | Ticks/call | Illegal | $ accounted / reported | Wall min | Harness | Replay verified |
|---|---|---|---|---:|---:|---|---|---:|---:|---:|---|---:|---|---|
| s1-haiku-P | claude-haiku-5-5 | primitive | 1500 (action_budget) | 12.4 | 14 | 13/1/0/0 | 12.4 / 12.4 / 12.4 | 221 | 6.79 | 0.0707 | 0.231 / 0.231 | 40.3 | h1 | yes |
| s1-haiku-M | claude-haiku-5-5 | macro | 1500 (action_budget) | 21.71 | 18 | 13/5/0/0 | 10.08 / 21.71 / 21.71 | 164 | 9.15 | 0.0373 | 0.179 / 0.179 | 30.7 | h1 | yes |
| s1-luna-P | gpt-5.6-luna | primitive | 591 (death) | 13.18 | 11 | 8/3/0/0 | 12.4 / 13.18† / 13.18† | 135 | 4.38 | 0.0677 | 0.085 / 0.063 | 20.4 | h1 | yes |
| s1-luna-M | gpt-5.6-luna | macro | 1384 (death) | 21.71 | 16 | 12/2/2/0 | 9.3 / 10.08 / 21.71† | 162 | 8.54 | 0.0614 | 0.118 / 0.087 | 25.4 | h1 | yes |
| s1-terra-M | gpt-5.6-terra | macro | 1500 (action_budget) | 22.48 | 17 | 13/2/2/0 | 10.08 / 21.71 / 22.48 | 118 | 12.71 | 0.0207 | 0.816 / 0.601 | 20.1 | h1 | yes |
| s1-sonnet-M | claude-sonnet-5-5 | macro | 338 (death) | 10.08 | 11 | 10/1/0/0 | 10.08† / 10.08† / 10.08† | 34 | 9.94 | 0.0118 | 0.277 / 0.232 | 4.4 | h1 | yes |
| s1-jev-P | typesafe/jev-1.14 | primitive | 642 (cost_budget) | 9.3 | 10 | 9/1/0/0 | 6.98 / - / - | 642 | 1.0 | 0.0 | 0.348 / 0.089 | 2.7 | h2 | yes (h2v: verify() fix only) |
| s1-jev-M | typesafe/jev-1.14 | macro | 784 (death) | 18.6 | 12 | 8/2/2/0 | 6.98 / 18.6† / 18.6† | 164 | 4.78 | 0.0 | 0.076 / 0.026 | 0.7 | h4 | yes |

The Haiku smoke test before screening (`runs/smoke-haiku`, 40 calls, pre-macro harness, $0.037)
is counted in the ledger but is not a result; it was not re-verifiable after the harness changed.
The macro track doubled Haiku (12.4 → 21.7%) and roughly doubled Luna's and Jev's tick throughput and score.
Every Jev decision was legal (0 illegal) at 0.25 s each. Terra was the best screened model
(22.5%, alive, 12.7 ticks/call), so it got the most long-run money.

### Per-run insights

- **s1-haiku-P** — Primitive track (16 ticks/call max, cooldown wait on but manual noops from the h1 guide): only 12.4% at 1,500 steps, stuck in tier 1 (one tier-2 unlock), 6.8 ticks/call. Same model/world on the macro track reached 21.7%: macros are the largest harness factor for Haiku.
- **s1-haiku-M** — Haiku without thinking on the macro track: 21.7% at 1,500 steps, alive, 3.7% illegal, $0.18 accounted. Five tier-2 unlocks (furnace chain started) while still writing manual noops between mines (h1 guide told it to; fixed in h3).
- **s1-luna-P** — Primitive track still reached furnace (302) and copper smelting (345), far earlier than Luna on v7 (736-2035), thanks to the guide; died at 591 to a Skeleton at y=109 while carrying only the copper shortsword. 6.8% illegal, 4.4 ticks/call.
- **s1-terra-M** — Best screen: 22.5% at 1,500 steps, alive. Macros used heavily (dig down/left/right, stairs); collected silver (563) and gold (816) and opened a chest, but never built a furnace: raw collection outpaced the crafting chain.
- **s1-sonnet-M** — Fastest early progress per call (11 achievements by step 338, 1% illegal) but died from fall damage: 'walk right 10' stepped off a dark cavern ledge. Led to h3 drop-safety in walk/dig macros and a FALLING status line.
- **s1-jev-P** — Jev as single-action chooser over the legal set: 0 illegal actions, 0.25 s/decision, 10 achievements by 642 (9.3%); stopped by the conservative accounted guard (ceiling 0.10/M vs actual 0.042/M; reported spend $0.089). No notes, so no multi-step plans.
- **s1-jev-M** — Jev choosing among legal primitives plus 7 fixed macros: 18.6% by step 784 (2x the primitive Jev screen at similar steps), 0 illegal, but 16 macro stops and death in the caverns (defeated one Skeleton at 651, died at 784). Reported $0.026.
- **L-terra-M-s1** — Best run: 58.9% weighted (30/38; tiers 13/11/6/0) when its $3 guard stopped it at step 5,968, alive. Collected all four ores by 816, then built furnace, smelted all four bars and an anvil within 20 steps (1,609-1,626), returned to the surface, survived the first night (3,000) killing a Zombie and a Demon Eye, crafted a metal sword (3,908). Missing: iron pickaxe/chainmail (needed more iron), Skeleton kill, wood breastplate, and the lens/boss chain.
- **L-terra-M-s2** — Cost-censored at 1,464 steps (13.9%) on world 33,000,002: reached the caverns at 202 with ore but no furnace, then spent its last ~40 calls climbing a rope shaft one row per call (15 macro stops, 32 illegal). Upward navigation, not game knowledge, limited it; a rope-climb macro and a smaller output reservation would help.
- **L-terra-M-s3** — Cost-censored at 1,609 steps (39.5%, 23/38, alive): fastest early climber of the campaign (furnace chain and four tier-3 unlocks inside 1,600 steps), confirming Terra's per-step strength; only the $1.15 guard (≈$0.006 accounted per call) stopped it.
- **L-haiku-M-s1** — 67.4% (32/38; 13/12/6/1). Slow start (anvil only at 4,606) but steady: metal sword, breastplate, silver and gold smelted by 6,301, Skeleton 6,991, lens from a Demon Eye at 7,896, Zombie 8,013. Same 6 missing achievements as seed 3: iron pickaxe, iron chainmail and the boss chain.
- **L-haiku-M-s2** — Died at step 3,636 (24.0%) to a Skeleton at y=72 with a wooden sword: it had survived the first night underground and killed one Skeleton at 2,200, but tried to tunnel away at 18 health instead of walling in early. Same death pattern as the Luna runs.
- **L-haiku-M-s3** — Best complete episode: 67.4% (32/38; tiers 13/12/6/1) over the full 10,000 steps, alive, $0.90. Survived three nights, anvil + gold smelting at ~3,826, Skeleton 4,132, Zombie 4,836, metal sword, return to surface, breastplate, then a Demon Eye kill with a lens drop (tier 4) at 8,386. Missing: iron pickaxe and iron chainmail (12/20 iron bars) and the boss chain.
- **L-luna-M-s1** — 30.2% (19/38), died at step 9,881 to a Skeleton at y=117. Reached the caverns at 208, killed a Skeleton at 401 and survived the first night underground, but never built a furnace or even a wooden sword: ~9,000 steps of cavern wandering (silver 3,392, gold 4,058) with the copper shortsword. Notes never turned into a return-and-craft plan.
- **L-luna-M-s2** — 34.9% (21/38), died at 9,059 to a Skeleton in a bedrock pocket (y=125). Built a furnace and smelted iron by 676 and survived the first night, but never made the anvil (5 iron bars) and added nothing after step 3,000; 339 illegal attempts (3.9%) and 21 macro stops show long, unproductive cavern navigation.
- **L-luna-M-s3** — Died at step 289 (7.0%): dug straight into the caverns (reached at 178) carrying only the copper shortsword and lost a melee exchange with a Skeleton (16 damage per hit) while retreating with illegal moves instead of walling off.
- **L-mix-TL-s1** — Terra planner (every 5th call + after macro stops; 34 of 138 calls) with a Luna executor on the world where Terra alone reached 48% by step 1,946: only 17.8% and died at 1,918 to a Skeleton at y=120 at night. The mixture cost 40% of Terra-alone per step but did not transfer Terra's crafting discipline: the executor wandered the deep caverns without building a furnace.

## What the runs show

1. **Macros are the largest harness factor.** On the same world, Haiku primitive 12.4% vs macro
   21.7%; Luna 13.2% (dead at 591) vs 21.7% (dead at 1,384); Jev 9.3% vs 18.6%. Macros raise ticks
   per call (Haiku 6.8 → 9-12; Luna 4.4 → 8.5-14) and make 10,000-step episodes affordable
   (≈700-900 calls ≈ 2-2.6 h at ≈10 s gateway latency per call).
2. **The guide removes the knowledge bottleneck.** Luna on v7 needed 736-2,035 steps for its first
   furnace without a guide; with the guide on v9 it reached the furnace in 302 (primitive) and Haiku/Terra in
   596-1,609 steps.
3. **Skeleton melee kills cheap models.** Seven of the nine deaths were confirmed Skeleton fights in the caverns
   with a copper or wooden sword at low health (the Jev-macro death in the caverns was not examined). The models kept retreating with illegal or slow moves
   instead of walling in or leaving the caverns. One death was a long fall in the dark (Sonnet), which led to the h3
   drop-safety fix; no run on h3-h5 died from a fall.
4. **Upward navigation and long crafting trips are the next bottlenecks.** Terra on world 2 spent
   its budget climbing rope one row per call. Luna never turned cavern notes into a
   return-and-craft trip. No run made the iron pickaxe or iron chainmail (12/20 iron bars) or any boss step beyond
   collecting a lens.
5. **Planner/executor mixing did not transfer quality.** Terra planning every 5th call over Luna
   cost 40% of Terra-alone per step but scored like Luna and died.
6. **Cost per complete episode:** Haiku ≈$0.90-1.03 (list price, header-confirmed), Luna ≈$0.50-0.56
   accounted per 9-10k-step episode (≈$0.37-0.41 reported), Terra ≈$4.5-5 projected, Sonnet ≈$8+ projected.

## Comparison with prior results

- **PPO v9 pilot (generic, 1B):** 57.5% weighted, tiers 100/81/66/14%. Haiku-macro-guide: 53.0% mean,
  67.4% on 2/3 worlds, tiers 94.9/80.6/54.2/13.3%. The tier profile is almost the same; the gap is one death.
  The LLM track has priors, a guide and macros; PPO has none of those but 1B steps of training.
- **Luna on v7 (Oct 17, primitive, no guide):** 20 and 19/32 with deaths at 2,478/1,802 steps;
  furnace at 736-2,035; illegal-action rate 35%. The harness study found interrupt-on-illegal best
  (14/32, 11.8% illegal). In this campaign, illegal rates are 1.5-7% (events interrupt, cooldown wait, legal list
  in the view). The v7/v8 secondary comparison was not run, for budget.
- **TerrariaBench (real Terraria, terrariabench.com, reference-gw.md):** best published score 4;
  Haiku/Sonnet/Opus reach a workbench in 1-3 min and then stall. In Terraria-Lite's symbolic text
  interface the same model family goes through the whole pre-boss progression. The bottleneck in
  real Terraria is perception and control, not planning.

## What helped (declared factors) and what did not

Helped: text view with annotated legal actions, game guide, events interrupt, cooldown wait,
macro actions, persistent notes, chunked history with prompt caching (Haiku ≈$0.001/call at
≈12k-token prompts), h3 drop safety. Did not help: the Terra→Luna mixture. Not tested, for budget: thinking for Haiku,
Opus/Sol (only a Sol price probe), env variants with things disabled, v8 comparison.

## Recommended LLM protocol for Terraria-Lite v9

- **Tracks:** report (A) *primitive* (`action_set=primitive`, text view, rules only) and
  (B) *assisted* (guide + macros + cooldown wait) separately. Never mix them in one leaderboard row.
- **Budget:** full 10,000-step episodes on ≥3 fixed public worlds (here 33,000,001-003), one
  attempt per world, no best-of. Report weighted %, tier success, milestones at 1k/1.5k/3k/5k/10k
  steps, deaths, illegal rate, calls, accounted and reported cost. A dollar cap that stops an episode makes it
  *censored*. Report it, never average it as a completed episode.
- **Harness:** h3 settings (events interrupt, cooldown wait, notes 2,048 chars, chunked 6-12 turn
  history, 48-tick macro cap); provider-reported cost plus a list-price guard; replay verification of every episode.
- **Next harness changes worth a controlled test:** a rope-climb macro, Skeleton facts in the guide (50 HP,
  16 damage, wall in with blocks), and a smaller output reservation for reasoning models (the 8k
  reservation cut each Terra episode ≈$0.2 early).

## Spend

Gateway (cap $11): **$10.15 accounted (conservative), $8.26 provider-reported**,
including probes outside the harness. OpenRouter/Jev (cap $0.50): $0.423 accounted,
$0.115 reported. One failed request (Jev screen, SSL transport error) was retried once and its full reservation ($0.0024) is counted as charged. No infrastructure aborts. Paid calls stopped at 07:45 UTC.

## Setup

**Environment.** v9 release candidate (`variants/v9`, ENV_VERSION 9): 128x128 layered world,
day/night (1,800 + 1,200 steps), night mobs, cavern Skeletons, Demon Altars, Eye of Cthulhu,
38 achievements in four tiers (weights 1/3/5/8, max 129), 10,000-step episodes, 86 actions.
Library: `perf/v7/build-v9` (`-DINV_LOG=1`, the PPO pilot build; INV_LOG only changes the RL
observation encoding, not dynamics), frozen as a copy in the campaign directory,
sha256 `6547bf27…d6318ff96d`. Headline: **weighted score** = Σ weights of unlocked
achievements / 129 (`python/terraria_lite/scoring.py`), plus tier counts, milestones,
deaths, illegal-action rate, calls and cost.

**Worlds.** Dedicated public LLM development worlds, outside the protected PPO test ranges:
screening world 33,000,101; long-run worlds 33,000,001–33,000,003. No world was dropped
or replaced; no best-of selection.

**Models and routes.** AMD LLM gateway: Claude Haiku 5.5 / Sonnet 5.5 (Anthropic Messages
route, prompt caching on the system block and the newest user turn) and GPT-5.6 Luna /
Terra (Unified OpenAI-compatible route, automatic prefix caching). TypeSafe Jev 1.14 via
OpenRouter's Decisions API (`/api/alpha/decisions`, key read over SSH from omarchy into
memory only). Reasoning: Haiku without thinking (its JSON reply carries a `plan` field),
Sonnet adaptive thinking at effort `low`, Luna/Terra `reasoning_effort=low`.

**Prices and accounting.** Every request reserves a conservative upper bound before it is
sent; charged = max(list-price estimate, provider-reported cost) per call. The gateway's
`X-Token-Usage-Cost` header is recorded per call. Haiku/Sonnet list prices match the header
exactly. Unified-route prices measured with probe calls: Luna $0.136/$0.816 per M in/out,
Terra $1.36/$8.16, Sol $2.72/$13.6 (all 0.68x OpenRouter's public list); the guard used
OpenRouter's list (Luna 0.20/1.20, Terra 2/12, cache read 10%) as ceilings. Jev: reported
$0.042/M prompt, $0 completion; the guard used a 0.10/M ceiling, so Jev's accounted spend
is 2-4x its reported spend.

## Harness (`terraria-llm-dev-v0.3`)

`python/terraria_lite/llm_bench.py`, `llm_protocol.py`, `llm_providers.py`, new
`llm_text.py` and `llm_macros.py`, CLI `tools/eval_llm.py`, ledger `tools/llm_ledger.py`.
Each run is frozen in `experiments/llm-v9-20261108/harness/<h1|h2|h3>/` (the copy that
actually ran) with its config in `configs/`.

v9 support: action budgets up to the native episode length (10,000), u64 achievement masks,
weighted score/tier report per episode and in the summary, v9 status fields (time of day,
layer, boss, selected slot) decoded from the RL observation, a `--library` option and
a ledger that counts running runs at their full cap.

Declared harness factors (all knobs in the config; defaults reproduce v0.2):

| Factor | Setting used | What it changes |
|---|---|---|
| `observation_format=text` | all LLM runs | ASCII map of the same 11x9 view (own glyph table: air `.`, unlit `?`, body `@`, mobs as letters), named status (health, weapon, armor, pickaxe, cooldowns, time to dawn/nightfall, layer, position), inventory, achievements with weighted score, visible mobs with offsets, and the legal actions with each mine target's tile. Re-encoding of the RL observation and mask; drops per-cell light levels and mob movement phase. |
| `action_format=names` | all LLM runs | exact action names, `name xN` repeats; JSON `{plan, actions, memory}` extracted from the reply (code fences/prose tolerated) |
| `knowledge=guide` | all LLM runs | **game-knowledge track**: tier list with weights, layer depths, ore layers, mining cooldowns, movement/jump/fall numbers, crafting chain with stations and quantities, station footprints, combat and night facts, the boss chain and the typical progression. Facts about this environment, no scripted policy. |
| `batch_interrupt=events` | all LLM runs | the rest of a list is discarded after an illegal attempt, damage, an achievement, a new mob kind, nightfall or dawn; the next observation reports what happened |
| `cooldown_wait` | all LLM runs | a `mine`/`attack` issued during its cooldown is preceded by noop ticks (counted) |
| notes | 2,048 chars | the model rewrites its persistent `memory` every call |
| history | chunked, 6–12 turns | keeps a stable cached prefix for 6 calls, then drops back to 6 turns |
| per-call tick cap | 16 primitive, 48 macro | primitive ticks executed per call |
| `action_set=macro` | **macro track** (`-M` runs) | observation-driven controllers: `walk left/right N`, `dig left/right N`, `dig down N`, `stairs up-left/up-right N`. Each emits one primitive per tick from the current observation and stops when blocked (reason reported) or on an interrupt event. h3 adds drop safety (never step off a ledge whose landing is not visible within 3 rows) and a `FALLING` status line. |

Replay verification is unchanged in substance: every primitive (including macro- and
cooldown-inserted noops) is journaled with the observation hash; `--mode verify` replays
the native transitions and now also checks that every model request contained exactly the
model observation recomputed from the replayed state.

Harness versions: **h1** (screens), **h2** = h1 + Jev Decisions provider (Jev screen),
**h3** = h2 + macro drop safety, FALLING line, guide text consistent with cooldown wait,
verifier fix for providers that embed the user turn in a larger string (long runs).
