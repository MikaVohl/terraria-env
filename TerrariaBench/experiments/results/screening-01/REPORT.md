# Terraria diagnostic campaign results

Snapshot: **47 recorded game attempts**, plus nine static-image probe calls. This is adaptive development on one world, not a model leaderboard or a complete-game evaluation.

Session reported API charges: **$1.838512**; unresolved reservations: **$0.184934**. Combined accounted exposure: **$2.023446** against the $3 session cap. The ledger snapshot may include an active attempt; reservations are retained until reconciled.

Raw records, conditions and stop reasons are in [summary.csv](summary.csv). Per-attempt manifests record prompts, tools, model metadata, source and fixture hashes. Artifact checks verify internal consistency against retained raw logs; they do not independently validate the grader.

## Selected repeated contrasts

The repeat plan was selected after initial screening signals. Each cell has three planned new attempts, shuffled within three blocks. Initial/pilot attempts are excluded from this table. These remain small development samples, with unpinned encounter RNG. Outcome rates and distributions use fully accounted attempts; attempt counts and costs retain interrupted attempts.

| Model / condition | Accounted / recorded / planned | Held ≥25 wood | Workbench | Deaths (runs) | Wood maximum, median [range] | Median calls / frames | Reported cost |
|---|---:|---:|---:|---:|---|---|---:|
| claude-haiku-5.5 / json | 3/3/3 | 0/3 | 0/3 | 0/3 | 0 [0, 13] | 13 / 13 | $0.06526 |
| claude-haiku-5.5 / paused | 3/3/3 | 2/3 | 2/3 | 0/3 | 41 [13, 45] | 16 / 17 | $0.09055 |
| claude-haiku-5.5 / tools | 3/3/3 | 3/3 | 3/3 | 0/3 | 46 [25, 83] | 15 / 15 | $0.07473 |
| gemini-3.8-flash / normalized | 3/3/3 | 2/3 | 1/3 | 2/3 | 42 [0, 94] | 16 / 9 | $0.19819 |
| gemini-3.8-flash / tools | 2/3/3 | 2/2 | 1/2 | 0/2 | 71.5 [41, 102] | 16 / 9 | $0.18848 |

## All fresh-world attempts

| Attempt | Wood max | Bench | Torches max / furnace | Target damage / killed | Damage received / deaths | Calls / limit / frames | Cost | Audit |
|---|---:|---|---|---|---|---|---:|---|
| [01-haiku-tools-fresh](01-haiku-tools-fresh/result.json) | 43 | no | 0 / no | n/a | 0 / 0 | 9 / 16 / 9 | $0.00820 | partial |
| [04-gemini-tools-fresh](04-gemini-tools-fresh/result.json) | 0 | no | 0 / no | n/a | 103 / 1 | 16 / 16 / 9 | $0.07768 | pass |
| [05-haiku-json-fresh](05-haiku-json-fresh/result.json) | 64 | yes | 0 / no | n/a | 42 / 0 | 15 / 16 / 15 | $0.02565 | pass |
| [06-haiku-paused-fresh](06-haiku-paused-fresh/result.json) | 44 | yes | 0 / no | n/a | 0 / 0 | 16 / 16 / 17 | $0.02893 | pass |
| [07-deepseek-tools-fresh](07-deepseek-tools-fresh/result.json) | 0 | no | 0 / no | n/a | 59 / 0 | 16 / 16 / 9 | $0.00313 | pass |
| [08-haiku-specific-fresh](08-haiku-specific-fresh/result.json) | 0 | no | 0 / no | n/a | 14 / 0 | 15 / 16 / 15 | $0.02581 | pass |
| [09-gemini-json-fresh](09-gemini-json-fresh/result.json) | 0 | no | 0 / no | n/a | 61 / 0 | 12 / 16 / 12 | $0.09355 | pass |
| [10-haiku-guided-fresh](10-haiku-guided-fresh/result.json) | 37 | yes | 0 / no | n/a | 0 / 0 | 15 / 16 / 15 | $0.02482 | pass |
| [11-haiku-inventory-fresh](11-haiku-inventory-fresh/result.json) | 0 | no | 0 / no | n/a | 98 / 0 | 16 / 16 / 12 | $0.02471 | pass |
| [12-gemini-paused-fresh](12-gemini-paused-fresh/result.json) | 0 | no | 0 / no | n/a | 0 / 0 | 16 / 16 / 9 | $0.07799 | pass |
| [13-haiku-notes-fresh](13-haiku-notes-fresh/result.json) | 5 | no | 0 / no | n/a | 6 / 0 | 9 / 16 / 9 | $0.00461 | pass |
| [14-haiku-longhold-fresh](14-haiku-longhold-fresh/result.json) | 24 | yes | 0 / no | n/a | 6 / 0 | 15 / 16 / 15 | $0.02485 | pass |
| [15-haiku-motor-fresh](15-haiku-motor-fresh/result.json) | 0 | no | 0 / no | n/a | 6 / 0 | 13 / 16 / 13 | $0.02119 | pass |
| [16-deepseek-json-fresh](16-deepseek-json-fresh/result.json) | 0 | no | 0 / no | n/a | 61 / 0 | 15 / 16 / 15 | $0.00367 | pass |
| [17-haiku-checkpoints-fresh](17-haiku-checkpoints-fresh/result.json) | 12 | no | 0 / no | n/a | 39 / 0 | 14 / 16 / 14 | $0.02240 | pass |
| [18-haiku-peaceful-fresh](18-haiku-peaceful-fresh/result.json) | 35 | yes | 0 / no | n/a | 0 / 0 | 16 / 16 / 16 | $0.02906 | pass |
| [19-gemini-guided-fresh](19-gemini-guided-fresh/result.json) | 2 | no | 0 / no | n/a | 0 / 0 | 15 / 16 / 8 | $0.08029 | pass |
| [N01-gemini-normalized-fresh](N01-gemini-normalized-fresh/result.json) | 89 | no | 0 / no | n/a | 82 / 0 | 16 / 16 / 9 | $0.06766 | pass |
| [N03-haiku-normalized-fresh](N03-haiku-normalized-fresh/result.json) | 45 | no | 0 / no | n/a | 55 / 0 | 14 / 16 / 14 | $0.02343 | pass |
| [N04-deepseek-normalized-fresh](N04-deepseek-normalized-fresh/result.json) | 0 | no | 0 / no | n/a | 35 / 0 | 16 / 16 / 9 | $0.00492 | pass |
| [R1-gemini-normalized-fresh](R1-gemini-normalized-fresh/result.json) | 94 | no | 0 / no | n/a | 124 / 1 | 16 / 16 / 9 | $0.06956 | pass |
| [R1-gemini-tools-fresh](R1-gemini-tools-fresh/result.json) | 41 | no | 0 / no | n/a | 73 / 0 | 16 / 16 / 9 | $0.06267 | pass |
| [R1-haiku-json-fresh](R1-haiku-json-fresh/result.json) | 0 | no | 0 / no | n/a | 78 / 0 | 13 / 16 / 13 | $0.02195 | pass |
| [R1-haiku-paused-fresh](R1-haiku-paused-fresh/result.json) | 45 | yes | 0 / no | n/a | 23 / 0 | 16 / 16 / 17 | $0.03127 | pass |
| [R1-haiku-tools-fresh](R1-haiku-tools-fresh/result.json) | 46 | yes | 0 / no | n/a | 48 / 0 | 16 / 16 / 17 | $0.02742 | pass |
| [R2-gemini-normalized-fresh](R2-gemini-normalized-fresh/result.json) | 0 | no | 0 / no | n/a | 120 / 1 | 16 / 16 / 9 | $0.06901 | pass |
| [R2-gemini-tools-fresh](R2-gemini-tools-fresh/result.json) | 102 | yes | 0 / no | n/a | 7 / 0 | 16 / 16 / 9 | $0.05990 | pass |
| [R2-haiku-json-fresh](R2-haiku-json-fresh/result.json) | 0 | no | 0 / no | n/a | 91 / 0 | 14 / 16 / 14 | $0.02318 | pass |
| [R2-haiku-paused-fresh](R2-haiku-paused-fresh/result.json) | 41 | yes | 0 / no | n/a | 22 / 0 | 16 / 16 / 17 | $0.02921 | pass |
| [R2-haiku-tools-fresh](R2-haiku-tools-fresh/result.json) | 83 | yes | 0 / no | n/a | 37 / 0 | 15 / 16 / 15 | $0.02556 | pass |
| [R3-gemini-normalized-fresh](R3-gemini-normalized-fresh/result.json) | 42 | yes | 0 / no | n/a | 18 / 0 | 16 / 16 / 9 | $0.05961 | pass |
| [R3-gemini-tools-fresh](R3-gemini-tools-fresh/result.json) | 0 | no | 0 / no | n/a | 120 / 0 | 14 / 16 / 7 | $0.06591 | partial |
| [R3-haiku-json-fresh](R3-haiku-json-fresh/result.json) | 13 | no | 0 / no | n/a | 32 / 0 | 13 / 16 / 13 | $0.02012 | pass |
| [R3-haiku-paused-fresh](R3-haiku-paused-fresh/result.json) | 13 | no | 0 / no | n/a | 0 / 0 | 16 / 16 / 17 | $0.03007 | pass |
| [R3-haiku-tools-fresh](R3-haiku-tools-fresh/result.json) | 25 | yes | 0 / no | n/a | 8 / 0 | 14 / 16 / 14 | $0.02175 | pass |

## Prepared crafting

Starting 50 wood, 50 stone and 5 gel are inherited setup. Wood maxima include inherited stock; wood checkpoints are excluded from progress. Workbench/torch/furnace columns measure newly observed possession, not independent proof of the crafting operation.

| Attempt | Wood max | Bench | Torches max / furnace | Target damage / killed | Damage received / deaths | Calls / limit / frames | Cost | Audit |
|---|---:|---|---|---|---|---|---:|---|
| [03-haiku-json-crafting](03-haiku-json-crafting/result.json) | 50 | yes | 0 / no | n/a | 98 / 0 | 15 / 16 / 15 | $0.02780 | pass |
| [20-haiku-tools-crafting](20-haiku-tools-crafting/result.json) | 50 | no | 0 / no | n/a | 104 / 1 | 16 / 16 / 17 | $0.03156 | pass |
| [21-haiku-inventory-crafting](21-haiku-inventory-crafting/result.json) | 50 | yes | 0 / no | n/a | 14 / 0 | 16 / 16 / 8 | $0.02049 | pass |
| [22-gemini-json-crafting](22-gemini-json-crafting/result.json) | 50 | yes | 15 / no | n/a | 106 / 1 | 10 / 16 / 10 | $0.08888 | pass_with_inert_tail |
| [23-haiku-guided-crafting](23-haiku-guided-crafting/result.json) | 50 | yes | 0 / no | n/a | 69 / 0 | 16 / 16 / 16 | $0.03058 | pass |

## Prepared combat

Guide removed; one designated blue slime is armed after window setup, while natural background mobs remain enabled. Only damage to that target is attributed. The initial rendered frame may precede the spawn. Target death and attributed player damage are distinct; the original operator positive control verified one hit, but not the kill detector. These attempts do not establish a clean clock effect.

| Attempt | Wood max | Bench | Torches max / furnace | Target damage / killed | Damage received / deaths | Calls / limit / frames | Cost | Audit |
|---|---:|---|---|---|---|---|---:|---|
| [02-haiku-paused-slime](02-haiku-paused-slime/result.json) | 0 | no | 0 / no | 0 / no | 0 / 0 | 16 / 16 / 17 | $0.02552 | pass |
| [24-haiku-tools-slime](24-haiku-tools-slime/result.json) | 0 | no | 0 / no | 0 / no | 132 / 1 | 16 / 16 / 17 | $0.02760 | pass |
| [25-gemini-tools-slime](25-gemini-tools-slime/result.json) | 0 | no | 0 / no | 0 / no | 40 / 0 | 16 / 16 / 9 | $0.06012 | pass |
| [26-haiku-json-slime](26-haiku-json-slime/result.json) | 0 | no | 0 / no | 0 / no | 80 / 0 | 16 / 16 / 17 | $0.02681 | pass |
| [27-gemini-paused-slime](27-gemini-paused-slime/result.json) | 0 | no | 0 / no | 4 / no | 15 / 0 | 8 / 16 / 4 | $0.02849 | partial |
| [28-deepseek-json-slime](28-deepseek-json-slime/result.json) | 0 | no | 0 / no | 0 / no | 35 / 0 | 11 / 16 / 11 | $0.00495 | pass |
| [N02-gemini-normalized-slime](N02-gemini-normalized-slime/result.json) | 0 | no | 0 / no | 0 / no | 54 / 0 | 16 / 16 / 9 | $0.07700 | pass |

## Interpretation boundaries

- Equal API calls do not mean equal action/observation opportunities. Stop limits include nominal observer updates; inference and cleanup can cross the simulation threshold. This is not an exact fixed-tick API.
- Wood maxima are sampled heartbeat inventory maxima, not cumulative gathered resources. Held-wood thresholds and station milestones use per-update checkpoints; consuming or placing an item can make a heartbeat maximum smaller than a briefly held quantity. Cursor-held items can escape inventory checks.
- Observation age in the CSV is wall time from the latest screenshot in the model request to each input start. It includes inference and earlier actions in the same batch. In paused mode, wall age does not mean equal game-state age.
- PvE is enabled except the explicitly labeled peaceful ablation. Natural hostile encounters differ. Received damage is not evidence of successful combat; natural loot may come from the Guide.
- A partial audit marks an unaccounted provider response/charge, not a model failure. Completed unsuccessful agent trajectories are retained.
- A qualified `pass_with_inert_tail` requires an exact exported journal prefix followed only by heartbeats with identical observed state and advancing timestamps/ticks. Raw data and original result stay unchanged. Future runs wait for process termination before export.
- Named native coding-agent frameworks, learned motor policies, new world seeds, bosses and post-Hardmode progression were not evaluated.
- See [interpretation rules](../../interpretation.md), [selection plan](../../repeats-01.json) and [research rationale](../../design-rationale.md).
