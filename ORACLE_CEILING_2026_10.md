# terraria-lite v7: oracle ceiling (October 2026)

**Question.** PPO stalls at about 25/32 achievements (best 25.67). Is that wall a property of the v7 environment (the 3,000-step episode is too short, or the hard tier is infeasible) or a property of the learners?

**Answer: the wall comes from the learners, not the environment.** An omniscient scripted planner that acts only through the normal action interface earns **31.97/32 on average** on the 128 validation worlds within 3,000 steps. It scores **32/32 on 124 of 128 worlds** and never dies. Every hard achievement that no policy has ever earned is earned in 124–128 of the 128 worlds:

- iron pickaxe, gold pickaxe, wood breastplate and return to surface: 128/128
- iron chainmail: 124/128

In the median world the planner finishes all 32 achievements by step 2,391, about 600 steps before the limit. The four misses are chainmail runs that need 27–75 steps more than the budget to finish everything. With 6,000 steps every world scores 32/32. No world is provably infeasible under the necessary-condition lower bounds.

## Method

### Planner (`oracle/oracle_v7.c`)

The planner is written in C and links directly against the frozen v7 game sources. Those sources are vendored byte-for-byte in `oracle/v7/`; `oracle/v7/SHA256SUMS` matches the experiment tree `experiments/v7-reward-20261017.sGYPqq/variants/v7`, and `make verify-sources` checks this.

- **What it may know (privileged).** At every decision it reads the full `Env`: all tiles, ore positions, chests, mobs and inventory. It does not predict or modify the RNG, and it never writes to the `Env`.
- **What it may do (constrained).** It acts only through `env_step`, one action per step, under the normal `max_steps` limit. Before each step it calls `env_action_mask` and refuses any action the mask marks illegal. The run then aborts and is flagged `illegal`; no run was flagged.
- **Movement model.** Dijkstra runs over player anchors (left column, feet row) using the real 2×3 body. Each edge mirrors the simulator's rules, and each cell that must be mined is costed at the current pickaxe period (4 − tier: 3, 2 or 1 steps). Wanted ore costs one step, because mining it is progress anyway. The edge types are:
  - walk;
  - bridge (place a block under the destination);
  - walk off a ledge and fall, using the true landing row;
  - auto step-up;
  - dig down;
  - pillar-jump up (jump, then place a block under the feet). Consecutive open rows are chained into a single jump of up to 6 rows.

  Falls longer than the safe 25 rows are arrested by placing a block mid-fall and digging through it, which resets fall damage. The planner replans after every executed edge.
- **Strategy.**
  1. **Surface sweep.** Chop trunks from the bottom; each mine fells the whole trunk. The planner picks the shortest column interval that yields about 62 wood. Along the way it kills a slime for gel and takes a mushroom for the first heal.
  2. **Wood crafting session.** Craft the workbench, wooden sword, breastplate and a platform, and place a block, a platform and a torch.
  3. **Underground tour.** Repeatedly take the target with the smallest weighted path cost from a single Dijkstra field: iron (120 needed), gold (40), copper (18, for the copper sword, which is the cheapest metal sword), silver (4) and the nearest underground chest room. The chest room gives torches, potions, rope, a Cloud in a Bottle and the life crystal. Gold is down-weighted ×4 until the iron pickaxe exists, and iron is down-weighted ×2 until the gold pickaxe exists. In worlds with few trees, chest-room floor wood counts as a target.
  4. **Crafting sessions.** A session starts whenever crafting would earn a new achievement or pickaxe tier. The planner carries the workbench, furnace and anvil, places them, smelts everything, crafts and picks the stations up again.
  5. **Opportunistic actions.** Mine wanted ore in reach, keep about 6 bulk blocks, and handle the rope climb, the double jump and the life crystal on the way. Attack mobs in sword range, and briefly chase bats and slimes when the kill is still missing.
  6. **Return.** Head for the surface when the remaining budget is at most 1.25 × the Dijkstra return cost + 40 steps, or when nothing is left to collect.
- **Recording.** Every step is recorded on a tape (1 byte per action) together with the step at which each achievement fired.

### Replay verification (`oracle/replay_verify.py`)

Each tape is replayed through the normal v7 Python binding: `terraria_lite.TerrariaLite(max_steps=H)` with the same seed, one `step()` per action. Before each action the script asserts that `action_mask()[a]` is true. It then checks that the episode does not end early and that every achievement fires on the same step as in the planner's record.

| tapes | replay result |
|---|---|
| validation, horizons 3k, 6k and 12k (3 × 128) | identical |
| best-of-6 portfolio (128) | identical |
| extra seeds (256) | identical |
| validation at 3k, replayed against the original experiment `libterraria.dylib` | identical |

### Lower bounds (`oracle_v7 -L`)

For each world and each hard achievement, the lower bound is the earliest step at which the achievement could possibly be earned. It is computed only from the initial world and a list of actions that must happen. It is independent of planner quality.

- **Material counts.** Every ore or stone tile is exactly one mine action. A felled trunk yields its height in wood for one mine action, and a wood block yields one. Requirements:
  - anvil: 15 iron ore, 14 wood, 20 stone, 3 torches
  - iron pickaxe: 45 iron ore
  - gold pickaxe: 15 iron + 40 gold ore
  - chainmail: 90 iron ore
  - metal sword: the cheapest metal (18 copper ore)
  - breastplate: 40 wood
  - all seven hard achievements together: 120 iron + 40 gold + 18 copper + 51 wood
- **Pickaxe-period chain.** Consecutive mines are spaced by the period that was in force when each mine was made. This is minimised over the possible upgrade orders: no upgrade, iron pickaxe first, gold pickaxe first, or iron then gold. An upgrade's own mines always come first, at period 3.
- **Action count.**
  - one action per mine, smelt and craft
  - select + place for each station that must be placed
  - one action to obtain torches
  - at least the horizontal moves needed to span a column window holding the required ore and wood (`px` changes only through move actions, at most 1 per step)
- **Descent and climb rates.** The feet descend at most 1 row per step and rise at most 2 rows per step, which bounds the time to reach the needed ore depth and to return from row ≥ 70.

The bound is the maximum of these terms. It ignores tunnelling, enemies and detours, so it is loose but sound. As a check, it was never above the step the planner actually achieved, in any of 7 × 128 cases.

## Results

### Scores

| horizon | worlds | mean /32 | median | min | max | 32/32 worlds | deaths | histogram |
|---|---|---|---|---|---|---|---|---|
| 3,000 | 128 | 31.97 | 32 | 31 | 32 | 124 | 0 | 31:4, 32:124 |
| 6,000 | 128 | 32.00 | 32 | 32 | 32 | 128 | 0 | 32:128 |
| 12,000 | 128 | 32.00 | 32 | 32 | 32 | 128 | 0 | 32:128 |
| 3,000, extra seeds 24000001–24000256 | 256 | 31.94 | 32 | 30 | 32 | 241 | 0 | 30:1, 31:14, 32:241 |
| 3,000, best of 6 planner configs per world | 128 | 31.99 | 32 | 31 | 32 | 127 | 0 | 31:1, 32:127 |

Notes on the rows:
- The default configuration uses gold weight 4 and iron weight 2.
- The 6,000- and 12,000-step runs replay the same plan with a later return, so their achievement steps equal the times each achievement actually needs.
- The extra-seed check deliberately excludes the reserved seeds 25000001–25000128.
- The portfolio row takes, per world, the best of the gold weight {1, 2, 4} × iron weight {1, 2} variants. Every portfolio tape is replay-verified, so it is still a lower bound on that world's ceiling.

### Per achievement at 3,000 steps (128 validation worlds)

| achievement | earned /128 | median step | max step |
|---|---|---|---|
| collect wood | 128 | 98.5 | 199 |
| collect stone | 128 | 528.5 | 918 |
| place block | 128 | 3 | 6 |
| craft workbench | 128 | 377 | 552 |
| craft furnace | 128 | 747 | 1267 |
| **craft anvil** | 128 | 950.5 | 1301 |
| place torch | 128 | 622.5 | 855 |
| place platform | 128 | 384.5 | 560 |
| collect copper | 128 | 526.5 | 1098 |
| collect iron | 128 | 621 | 1019 |
| collect silver | 128 | 729 | 1263 |
| collect gold | 128 | 992.5 | 1533 |
| smelt copper | 128 | 754.5 | 1270 |
| smelt iron | 128 | 814.5 | 1276 |
| smelt silver | 128 | 875.5 | 1340 |
| smelt gold | 128 | 1169.5 | 1625 |
| defeat Blue Slime | 128 | 28 | 376 |
| defeat Cave Bat | 128 | 856.5 | 2362 |
| open chest | 128 | 651 | 1692 |
| craft wooden sword | 128 | 380 | 555 |
| **craft metal sword** | 128 | 978 | 1605 |
| **craft wood breastplate** | 128 | 431 | 1405 |
| **craft iron chainmail** | 124 | 2268.5 | 2856 |
| heal with food or potion | 128 | 18 | 145 |
| use life crystal | 128 | 683 | 1708 |
| double jump | 128 | 669 | 1702 |
| descend deep | 128 | 749.5 | 1396 |
| **return to surface** | 128 | 2391 | 2931 |
| explore 30 columns | 128 | 83.5 | 159 |
| climb rope | 128 | 664 | 1695 |
| **craft iron pickaxe** | 128 | 1296.5 | 1820 |
| **craft gold pickaxe** | 128 | 1924.5 | 2556 |

### Hard tier: success, failure classification and time needed

The 3,000-step failures are classified in two ways:
- **lower bound > 3,000**: the achievement is provably infeasible in that world;
- **planner ran out**: the bound allows the achievement, but the planner did not finish in time.

| achievement | earned @3k | earned @6k | earned @12k | lower bound median (max) | 3k failures: lower bound > 3k | 3k failures: planner ran out | steps actually needed: median / p90 / max |
|---|---|---|---|---|---|---|---|
| craft anvil | 128 | 128 | 128 | 112 (112) | 0 | 0 | 950 / 1141 / 1301 |
| craft metal sword | 128 | 128 | 128 | 166 (166) | 0 | 0 | 978 / 1182 / 1605 |
| craft iron pickaxe | 128 | 128 | 128 | 202 (205) | 0 | 0 | 1296 / 1498 / 1820 |
| craft gold pickaxe | 128 | 128 | 128 | 232 (285) | 0 | 0 | 1924 / 2395 / 2556 |
| craft iron chainmail | 124 | 128 | 128 | 293 (297) | 0 | 4 | 2284 / 2687 / 3025 |
| craft wood breastplate | 128 | 128 | 128 | 47 (62) | 0 | 0 | 431 / 755 / 1405 |
| return to surface | 128 | 128 | 128 | 60 (65) | 0 | 0 | 2391 / 2792 / 3075 |

Lower bound for all seven hard achievements together: median 451, range 363–465. No world has a bound above 3,000.

The four 3,000-step failures are worlds 23000068, 23000083, 23000113 and 23000124. Each one misses only chainmail, after collecting 113–119 of the 120 iron ore it needs. Given more steps, these worlds finish all 32 achievements at steps 3,027–3,075. In three of them the unconstrained run crafts chainmail before step 3,000 (at 2,926, 2,997 and 2,882), but the 3,000-step planner has to head home first to secure return to surface.

Time to the 32nd achievement, from the 12,000-step runs:

| statistic | step |
|---|---|
| median | 2,391 |
| p90 | 2,792 |
| max | 3,075 |

### Where the budget goes

Median action mix in a 3,000-step run:

| action | median count |
|---|---|
| moves and jumps | 751 |
| mines through rock | 443 |
| waiting for the pickaxe cooldown | 434 |
| ore and log mines | 216 |
| airborne ticks (falling or rising) | 204 |
| block placements (pillars, bridges, fall arrests) | 202 |
| crafts and smelts | 73 |

The surface wood phase ends at a median step of 377 (workbench crafted).

The binding resource is iron. The world generator only guarantees 120 iron ore, and **60 of 128 validation worlds contain exactly 120**. In those worlds every iron tile on the map must be found and mined. They take longer: the median time to the 32nd achievement is 2,589 steps, against 2,278 in the 45 worlds with more than 130 iron ore. All four 3,000-step misses are chainmail runs that are a few ore short.

World resources across the validation set:

| resource | min | median | max | notes |
|---|---|---|---|---|
| iron ore | 120 | 122 | 202 | |
| gold ore | 40 | 52 | 107 | 31 worlds have exactly 40 |
| copper ore | 100 | 198 | 264 | |
| silver ore | 42 | 100.5 | 156 | |
| wood | 90 | 117 | 130 | trunks plus 56 room-floor blocks |

## Caveats

- **The planner score is a lower bound on the true ceiling.** It is a hand-written greedy planner, not an optimum. It uses nearest-target tours with no TSP optimisation, a simple return trigger and a mostly fixed phase order. The true 3,000-step ceiling is at least 31.97/32 on these worlds, and likely 32/32 in more than 124 of them.
- **The lower bounds are necessary conditions only.** They ignore tunnelling, which accounts for most of the real cost. The gap between about 450 and about 2,400 steps is therefore not slack the planner left behind. It only shows that no world is ruled out on counting grounds alone.
- **The planner is privileged.** It sees the whole map, so it never searches for ore. A learning agent sees only an 11×9 window and must explore, which needs memory and exploration that PPO lacks. The oracle shows the steps exist and fit the budget; it does not show they are easy to discover from the observation.
- **No game change was made.** Vendored sources are byte-identical to the frozen experiment tree, and the run used CPU only.

## Is the ~25/32 wall an environment property?

No.

**The environment is not the limit.** Within the same 3,000-step budget and action interface, all seven hard achievements are achievable in essentially every validation world. That covers the five that no policy has ever earned (iron pickaxe, gold pickaxe, iron chainmail, wood breastplate, return to surface) and the two that are earned only rarely (anvil, metal sword). Chainmail is the only one that is tight: 4 of 128 worlds miss it, each by at most 75 steps. The others leave several hundred spare steps.

**What separates PPO from the ceiling is skill.** A policy at about 25/32 typically holds at most about 5 iron bars and 13 wood. Reaching 32 instead requires:
- systematically harvesting about 60 wood;
- tunnelling to and clearing nearly every iron tile in the world (120 ore);
- managing pickaxe upgrades so that mining speeds up from 1 per 3 steps to 1 per step;
- carrying and reusing crafting stations;
- climbing about 50 rows back to the surface at the end.

These are long-horizon exploration, memory and planning problems for the learner. They are not budget infeasibility.

## Reproduce

```sh
cd oracle
make                      # oracle_v7 + v7 libterraria (python binding), CPU only
make verify-sources       # vendored v7 sources == frozen experiment tree
python3 run_oracle.py --horizon 3000 --out results/h3000      # also 6000, 12000
./oracle_v7 -L -n 128 > results/lower_bounds.jsonl
python3 replay_verify.py results/h3000.bin results/h3000.jsonl   # *.bin.gz also accepted
python3 analyze.py        # tables above + results/summary.json
```

Single-world debugging: `./oracle_v7 -s 23000001 -h 3000 -v -v`. Add more `-v` flags for per-action and per-path traces. Planner weights can be changed with `-p w_gold_a=4 -p w_iron_b=2` (also `chest_bonus`, `return_reserve`, `wood_goal`).

Files in `oracle/results/`:

| file | contents |
|---|---|
| `h{3000,6000,12000}.jsonl` | per-world score, step of every achievement, action mix, ore collected |
| `*.bin.gz` | action tapes |
| `lower_bounds.jsonl` | per-world resources and lower bounds |
| `extra_h3000.*` | 256 extra seeds at 3,000 steps |
| `portfolio_h3000.*` | best-of-6 runs |
| `summary.json` | all tables in machine-readable form |
