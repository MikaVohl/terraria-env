# Campaign 03: real-time planner/executor agents (2026-10-18)

Question: with the game never paused, does splitting an agent into a slow planner and a
fast executor beat the single-model loop, and how often does the planner need to act?
Operator hypothesis under test: given a good enough action agent, the planner is only
needed for high-level direction every 10 s to 1 min.

Compact records: [results/planner-executor-01](results/planner-executor-01/summary.csv)
(frozen plans, manifests, results, ledger). Every analysed hybrid run passed the input
audit: executed inputs equal, in order, the actions logged by executor decisions and
planner UI batches, and every model call has a stored request/response.

## Setup

- Real time only. Normal PvE. Four held-out small Classic worlds (seeds 32000101..104),
  one attempt per world per cell. Tasks: `fresh` (wood/workbench) and `slime`
  (designated-target combat), 120 game-seconds; the interval sweep uses `fresh` for 300.
- Runner: `terrariabench/hybrid.py`. A planner thread and an executor loop share one
  game; the executor never waits for the planner and always acts on its newest observation.
- Planner: Claude Haiku 5.5, low reasoning. Executors: Haiku 5.5 without reasoning, or
  TypeSafe Jev 1.14 through OpenRouter (`/api/alpha/decisions`, about 0.2 s per decision).
- Observations: screenshots (`*-pixel` conditions), or **privileged structured state**
  from observer v0.6 (trees, hostiles, drops and terrain with screen coordinates, written
  about 10 times per second). Every Jev condition in this campaign uses the structured state.
  The pre-campaign image probe sent images in TypeSafe's native `assets` format, which
  OpenRouter ignores, and wrongly concluded that Jev was text-only on this route. OpenRouter's
  Decisions API takes images as `image_url` data-URL parts in the `state` array. Re-tested
  that way, Jev 1.14 separates black, red and real frames (nouls 0.97 / 0.99 / 0.98) and boxes
  the player correctly, at about 0.45 s and $0.00013 per 1024x1024 frame.
- State-based executors choose from a fixed action catalog whose options expand to
  ordinary keyboard/mouse input. Aiming (where to click on a trunk or a hostile) is done
  in code from the state, so these conditions measure decisions over prepared actions,
  not perception or aiming.

| Condition | Planner | Executor |
|---|---|---|
| `single-haiku` | none | Haiku tool loop, screenshots (campaign-01 harness) |
| `ll-pixel` / `ll-state` | continuous Haiku (tactical goals every 3-5 s) | Haiku, screenshots / state + catalog |
| `lj-state` | continuous Haiku | Jev, state + catalog |
| `hl-lj-state-rN` | high-level Haiku: objective + completion condition, replanned on completion, death, or after N s | Jev, state + catalog |
| `hl-ll-pixel-r30` | high-level Haiku | Haiku, screenshots only |
| `jev` | none (Jev also picks a subgoal each decision) | Jev, state + catalog |
| `scripted` | none | fixed priority rule over the same catalog, no model (unpaid ceiling reference) |

## Results: 120 game-seconds

Wood is the maximum held per world (101 / 102 / 103 / 104). Observation age is the median
time from the observation an action was based on to its first input.

| Task | Condition | n | Result | Obs. age |
|---|---|---:|---|---:|
| fresh | scripted | 4 | 273 / 591 / 314 / 13 | 0.07 s |
| fresh | **jev** | 4 | **176 / 516 / 178 / 14** | 0.34 s |
| fresh | lj-state | 4 | 107 / 261 / 131 / 14 | 0.32 s |
| fresh | hl-lj-state-r30 | 4 | 94 / 356 / 73 / 14 | 0.42 s |
| fresh | ll-state | 3 | 80 / 90 / 12 | 0.95 s |
| fresh | hl-ll-pixel-r30 | 3 | 0 / 3 / 1 | 1.75 s |
| fresh | ll-pixel | 2 | 0 / 0 | 1.74 s |
| slime | scripted | 4 | 4/4 kills at 14-30 game-s | 0.06 s |
| slime | **jev** | 4 | **3/4 kills** at 51-74 game-s | 0.35 s |
| slime | hl-lj-state-r30 | 4 | 2/4 kills | 0.38 s |
| slime | **hl-ll-pixel-r30** | 4 | **2/4 kills** at 50 and 83 game-s | 1.77 s |
| slime | lj-state | 4 | 1/4 kills | 0.34 s |
| slime | single-haiku | 4 | 1/4 kills (at 100 game-s) | ~6-10 s |
| slime | ll-state | 2 | 0/2 (8 and 17 damage) | 0.90 s |

Nobody crafted a workbench: only the LLM planner can click through the crafting menu,
and it never completed one. Deaths are common in `slime` for every condition, about one
per run, including the scripted rule.

## Results: replan-interval sweep (fresh, 300 game-seconds)

| Condition | Wood 101 / 102 / 103 / 104 | Total | Planner calls per run | Cost per run |
|---|---|---:|---|---:|
| hl-lj-state-r10 | 165 / 532 / 190 / 14 | 901 | 18-25 | ~$0.028 |
| hl-lj-state-r30 | 208 / 564 / 290 / 14 | 1,076 | 9-15 | ~$0.026 |
| hl-lj-state-r60 | 126 / 525 / 240 / 14 | 905 | 4-14 | ~$0.022 |
| jev (no planner) | 169 / 691 / 192 / 17 | 1,069 | 0 | ~$0.012 |
| scripted | 622 / 958 / 389 / 15 | 1,984 | - | $0 |

Deaths: 0-2 per run, with no pattern by condition.

## Interpretation

1. **Latency was the binding problem, and removing it pays off.** With the same visual
   interface, the high-level planner plus a fast Haiku executor (1.8 s observation age)
   killed the slime 2/4 times against 1/4 for the single-model loop (6-10 s).
   With structured state, executors at 0.3-0.4 s outperform the same split at 0.9 s.
2. **A good action agent does not yet need a planner on these tasks.** Jev alone matched
   or beat every planner + Jev configuration in both blocks. Over 300 s, replanning every
   10, 30 or 60 s spans 4-25 planner calls with no reliable effect on wood: the 30 s cell
   is highest, but the spread between worlds is far larger than between intervals, with
   one run per cell. This supports the hypothesis's premise (high-level direction is
   enough) more strongly than its conclusion (that direction adds value): on these tasks
   the planner contributed nothing measurable.
3. **The catalog does much of the work.** The no-model scripted rule beats every model on
   both tasks. Model executors currently lose to a fixed priority rule over the same
   options, so these runs do not show that models are good players; they show how to
   remove latency from the loop. The structured-state conditions are privileged and must
   be reported separately from screenshot play.
4. **Exploration is unsolved.** World 32000104 has almost no reachable trees near spawn.
   Every condition, including planners choosing `explore_left/right` and the scripted rule,
   stays at 13-17 wood there. That is the situation where high-level direction should
   matter, and none of the current planners exploit it.
5. **The continuous tactical planner is the wrong shape.** Its goals restate coordinates
   from screenshots 3-5 s old, and it did no better than the planner-free executor.

## What this does not show

One attempt per cell on four worlds: no rankings or significance. The tasks are short and
early-game; crafting, night, bosses and multi-stage goals are untested. No Jev run here saw
pixels (see Setup). Executors decide sequentially (decide, then act for 0.25-0.75 s);
overlapped deciding and interruptible actions are untested.

## Infrastructure incidents (no effect on retained results)

- After a Moonlight disconnect at 16:57, a launched client entered the world but never
  ran its update loop. A harness bug then left each hung client alive, and 42 runs failed
  at startup in a cascade (43 orphaned clients; Sunshine crashed once). No model call had
  been made. Fixes: `start_game` terminates its own client on any startup failure; the
  campaign driver archives startup or display failures as `<id>.infra-failed-N` and
  retries once. No startup failure recurred in the remaining runs. The first hang's
  trigger is not established.
- A 1920x1240 Moonlight session at scale 1.25 gave a 1536x992 logical display, so the
  1024 px game window was partly off screen. Two runs played that way and are archived
  (`.excluded-display-1536x992`). The Sunshine display script now uses scale 1 for
  1920x1240. The harness places the game and live panel from the actual display, and
  refuses any capture or input while the game window is not fully visible.
- The catalog's `close_inventory` option sent the invalid key name `escape` (valid:
  `esc`). One run's executor was stuck while the inventory was open; it is archived
  (`.excluded-esc-key-bug`) and was rerun. A regression test covers it.

## Recordings

Every run after 19:16 has a full-desktop recording (`<run>/desktop.mp4` on Omarchy,
10-15 fps, game plus live panel). Selected clips are copied to `runs/recordings/`
(git-ignored): Jev alone at 516 wood, a screenshot-only high-level planner + Haiku slime
kill, and a high-level planner + Jev slime kill without dying.

## Spending

Ledger cap $2.00: $1.146647 reported plus one uncertain $0.021504 reservation (a failed
planner call in `P-32000101-fresh-ll-state`), $1.168151 conservative exposure. It covers all
smoke runs, campaign runs and the sweep. Jev executor calls cost about $0.00005 each.

## Next candidates

- Overlapped deciding and interruptible holds for the executor (target: beat the scripted rule).
- Exploration and multi-stage tasks of 10+ game-minutes, where direction should matter;
  repeat the interval sweep there.
- A crafting action, so that progression beyond wood is reachable without menu clicking
  by the planner.
- A screenshot-only Jev executor (image input via OpenRouter, Box answers for aiming), to
  bring the latency gains to non-privileged play.
