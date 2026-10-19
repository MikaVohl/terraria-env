# Reference profile through the gateway (2026-10-18/19)

Question: on the reconstructed terrariabench.com profile (single model, 1024² screenshots,
real keyboard/mouse, real time, PvE off, open-ended prompt), how far do current Claude models
get, and do checkpoint/time information or run length change that?

All runs are `calibration` mode on world `32000001` (one world, one run per cell): signals,
not rankings. Compact records: [`results/reference-gw/`](results/reference-gw/)
(`summary.json` has one row per run). Full runs (frames, requests, responses,
`desktop.mp4`) stay on Omarchy under `runs/reference-gw-0{1,2}/`.

## Setup

- Route: Anthropic Messages via `<gateway>` (tailnet `a relay host` → gateway),
  requests shaped like omp 18.1.16's ([`gateway.py`](../terrariabench/gateway.py)).
  Reasoning follows omp's mappings: Haiku 5.5 medium = thinking budget 8,192; Sonnet/Opus 5.5
  low = adaptive thinking with `effort: low`.
- Profile: [REFERENCE_BASELINE.md](../REFERENCE_BASELINE.md). Context keeps all text until 120k
  tokens (then oldest whole turns are dropped) and the newest 8–15 screenshots. A tool-less
  reply before the budget ends gets a fixed "Continue playing." message.
- Conditions: **ref** = checkpoint tool and chat visible, as published; **hidden** = no
  checkpoint tool, chat lines or remaining-time count. The 10/15-minute ref runs still showed
  remaining time in continuations; the 45/30-minute ref runs hid it.
- Recording: every run under `runs/<campaign>/<run>/desktop.mp4` (game + live agent panel).

## Results

| Run | Played | Score | Milestones (s) | Calls | Continue msgs | Inputs | USD |
|---|---:|---:|---|---:|---:|---:|---:|
| Haiku medium, ref, 15 min | 905 s | 3 | wood 1/10 28, workbench 55 | 108 | 21 | 278 | 0.26 |
| Haiku medium, hidden, 10 min | 605 s | 4 | wood 1/10/25 57, workbench 113 | 73 | 15 | 127 | 0.18 |
| Sonnet low, ref, 10 min | 606 s | 4 | wood 1/10 42–45, workbench 69, wood_25 365 | 78 | 32 | 139 | 1.15 |
| Sonnet low, hidden, 10 min | 604 s | 4 | wood 1/10/25 28, workbench 51 | 69 | 14 | 169 | 2.79 |
| Haiku medium, ref, 45 min | 2,708 s | 4 | wood 1/10/25 49, workbench 80 | 269 | 70 | 634 | 0.37 |
| Sonnet low, ref, 45 min † | 2,006 s | 4 | wood 1/10/25 76, workbench 186 | 148 | 43 | 519 | 1.67 |
| **Opus low, ref, 30 min** | 1,806 s | **5** | wood 1/10/25 30–32, workbench 57, **wood_100 1,741** | 113 | 7 | 679 | 4.32 |
| Haiku medium, hidden, 45 min ‡ | 2,706 s | 4 | wood 1/10 93, workbench 109, wood_25 180 | 231 | 39 | 556 | 0.40 |
| Sonnet low, hidden, 45 min | 2,702 s | 4 | wood 1/10/25 52, workbench 82 | 157 | 23 | 965 | 3.32 |

† Ended after 33 of 45 minutes of play: it rode out a 29-minute gateway outage (13:50–14:19,
game frozen), then exceeded the 30-minute cumulative outage limit when the route dropped again
at ~14:40. ‡ Possible operator Smart Cursor toggle via Moonlight at 16:07–16:10, after its last
milestone (`operator-note.json`). The first 15-minute Haiku run (score 4 at 52 s, stopped
itself at 272 s before continuations existed) and smoke runs are in `summary.json`.

For comparison, the seven published runs (8 h budgets, ~6.1 h of play) reached at most wood:
Gemini 3 Flash 4 (wood_100 at 2,819 s), Gemini 3.1 Flash Lite and Pro 3, the other four 0.

## Findings

1. **Current models clear the published frontier in minutes.** Every run reached wood and
   placed a workbench within 1–3 minutes; no published model placed a workbench in six hours.
   Opus is the only run to score past that stage (wood_100 at 29 minutes, score 5).
2. **Everything scored happens in the first ~3 minutes, then progress stops.** After the
   workbench no Haiku or Sonnet run earned another milestone in up to 45 minutes. The final
   inventories show real activity the scorer does not count: Sonnet hidden ended with 492
   stone, 21 copper ore, 33 rope and 2 torches; Opus with 101 wood, 180 stone and 8 copper ore.
3. **The profile itself blocks the next milestones.** A furnace needs 3 torches, torches need
   gel, and early gel comes from slimes, which disabled PvE removes. Torches then come only from
   pots/chests (Sonnet hidden found 2). So `torch_10`, `furnace_1` and `early_bar_5` are close to
   unreachable here regardless of model. Opus claimed a furnace that telemetry never recorded.
4. **Models quit.** Without a continuation message Haiku ended its first run at 4.5 minutes.
   With it, Haiku needed 70 continuations in 45 minutes and Sonnet 23–43; Opus needed 7 and kept
   acting. Showing remaining time made early stopping worse (observed by the operator).
5. **Hiding checkpoints did not change scores** (4 vs 4 for Haiku and Sonnet at both lengths).
   Hidden Sonnet explored more (965 inputs vs 519; 492 vs 19 stone), but single runs on one
   world cannot separate that from run-to-run variance.
6. **Cost per minute of play:** Haiku $0.008–0.018, Sonnet $0.05–0.28, Opus $0.14. An 8-hour
   reference-length run would cost roughly Haiku $4–9, Sonnet $25–40, Opus ~$70. Dropping old
   screenshots 8 at a time cut provider cache writes, which were $2.60 of $2.79 in the first
   10-minute hidden Sonnet run.

## What the traces show

Per-run timelines (model words, actions, milestones, once-a-minute game state) were built for
the five long runs.

| Run | Max depth below spawn | Tool-less replies (of which "stopping") | Inference share of play | Screenshot age at action (median) |
|---|---:|---:|---:|---:|
| Haiku ref 45 | 26 tiles | 70 (68) | 68% | 11.8 s |
| Haiku hidden 45 | 17 tiles | 39 (37) | 73% | 11.6 s |
| Sonnet ref 45 (33 min) | 63 tiles | 43 (13) | 61% | 18.6 s |
| Sonnet hidden 45 | **519 tiles** | 23 (2) | 48% | 19.4 s |
| Opus ref 30 | 232 tiles | 7 (7) | 48% | 13.8 s |

1. **The breakthrough skill is a camera-relative routine, not perception.** The camera keeps the
   player centred, so holding the mouse at a fixed point just below centre and pressing S always
   digs the tile underneath. Sonnet (hidden) found this at ~950 s after ~15 minutes of failing
   to dig by aiming at tiles in screenshots, then repeated it blind in the dark down to 519
   tiles. Opus dug the same way from ~214 s. Neither Haiku run found it; both stayed within 26
   tiles of the surface.
2. **Actions run on stale screenshots.** `look` and `act` are separate model calls, so a
   screenshot is at least one inference old when acted on: median 12–19 s. The model spends
   48–73% of play time thinking while the game runs. Clicking a specific tile from a screenshot
   fails once the camera has moved; the fixed-point routine above survives because it does not
   depend on the screenshot.
3. **Tool-less replies are status reports.** They are assistant-style summaries ("Done so far…
   Where it stands…") that end the turn; the continuation message turns them back into play.
   Haiku's almost always announce stopping; most of Sonnet's are progress notes. Opus produced
   the fewest (7 in 30 minutes).
4. **Control and UI knowledge gaps cost minutes.** Sonnet spent minutes concluding that arrow keys
   do nothing (Terraria moves with WASD). Haiku (ref) spent long stretches "digging" with hotbar
   slot 6 selected, which holds the workbench; it found the mistake at 2,418 s. Several runs
   fought the inventory toggle and the crafting list before the workbench.
5. **Unchecked claims of progress.** Opus believed it had "the workbench and furnace set up" at
   214 s; no furnace existed. Later it reasoned correctly that a furnace needs torches, that torches
   need gel and that disabled PvE removes slimes (896 s), and planned to break pots for torches
   (1,440 s). Reading the checkpoint log corrected its beliefs; the hidden runs had no such check.
6. **Opus's extra point was incidental.** Trapped in a flooded, dark shaft 25 tiles down, it
   deliberately drowned to respawn (1,701 s), then picked up 3 wood on the surface: 98 → 101
   gave wood_100. Its depth (232 tiles), copper ore and 180 stone earned nothing.
7. **The scorer misses real progress.** Depth, ore and loot (Sonnet hidden: 519 tiles, 21 copper
   ore, rope, bombs, 2 torches from pots) are invisible to the published catalog. The spec
   deliberately dropped descent counters as reward-hackable, so layer entry (underground,
   cavern) as a one-time milestone is the natural candidate.

Implications: report screenshot age and inference share alongside scores; a variant that returns
a screenshot with every `act` result would separate perception from latency; the
continuation policy is load-bearing for any long run and must be stated with results.

## Spend and incidents

- Reported charges for every run in both campaigns: **$15.46**, plus $0.17 in three runs
  restarted for harness fixes (`runs/reference-gw-02-aborted/` on Omarchy). Under the $40
  authorization. Uncertain reservations are listed per run; all connection failures
  (`URLError`) provably never reached the gateway.
- The gateway route dropped four times (~01:55, 13:04–13:21, 13:50–14:19, ~14:40–15:30). The
  first outage killed four queued runs; later runs freeze the game process and pause the run
  clock during outages (up to 30 minutes per run), and the scheduler waits for the route before
  each run.

## Next

- Decide the PvE question with gel in mind: a profile where hostile damage is off but slimes
  still spawn and drop gel would make torches and furnaces reachable without combat.
- Repeat cells on several worlds before reading anything into ref vs hidden.
- If an 8-hour run is wanted, Opus is the only model here that kept acting without prompting;
  budget ~$70 for one run.
