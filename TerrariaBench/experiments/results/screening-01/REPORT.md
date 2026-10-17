# Terraria diagnostic campaign results

Snapshot: **28 completed game attempts**, plus nine static-image probe calls. This is adaptive development on one world, not a model leaderboard or a complete-game evaluation.

Session reported API charges: **$1.100954**; unresolved reservations: **$0.043008**. Combined accounted exposure: **$1.143962** against the $3 session cap. The ledger snapshot may include an active attempt; reservations are retained until reconciled.

Raw records, conditions and stop reasons are in [summary.csv](summary.csv). Per-attempt manifests record prompts, tools, model metadata, source and fixture hashes. Artifact checks verify internal consistency against retained raw logs; they do not independently validate the grader.

## Selected repeated contrasts

The repeat plan was selected after initial screening signals. Each cell has three planned new attempts, shuffled within three blocks. Initial/pilot attempts are excluded from this table. These remain small development samples, with unpinned encounter RNG. Outcome rates and distributions use fully accounted attempts; attempt counts and costs retain interrupted attempts.

| Model / condition | Accounted / recorded / planned | ≥25 wood | Workbench | Deaths (runs) | Wood maximum, median [range] | Median calls / frames | Reported cost |
|---|---:|---:|---:|---:|---|---|---:|

Repeats have not completed yet.

## All fresh-world attempts

| Attempt | Wood max | Bench | Torches max / furnace | Target damage / killed | Damage received / deaths | Calls / frames | Cost | Audit |
|---|---:|---|---|---|---|---|---:|---|
| [01-haiku-tools-fresh](01-haiku-tools-fresh/result.json) | 43 | no | 0 / no | n/a | 0 / 0 | 9 / 9 | $0.00820 | partial |
| [04-gemini-tools-fresh](04-gemini-tools-fresh/result.json) | 0 | no | 0 / no | n/a | 103 / 1 | 16 / 9 | $0.07768 | pass |
| [05-haiku-json-fresh](05-haiku-json-fresh/result.json) | 64 | yes | 0 / no | n/a | 42 / 0 | 15 / 15 | $0.02565 | pass |
| [06-haiku-paused-fresh](06-haiku-paused-fresh/result.json) | 44 | yes | 0 / no | n/a | 0 / 0 | 16 / 17 | $0.02893 | pass |
| [07-deepseek-tools-fresh](07-deepseek-tools-fresh/result.json) | 0 | no | 0 / no | n/a | 59 / 0 | 16 / 9 | $0.00313 | pass |
| [08-haiku-specific-fresh](08-haiku-specific-fresh/result.json) | 0 | no | 0 / no | n/a | 14 / 0 | 15 / 15 | $0.02581 | pass |
| [09-gemini-json-fresh](09-gemini-json-fresh/result.json) | 0 | no | 0 / no | n/a | 61 / 0 | 12 / 12 | $0.09355 | pass |
| [10-haiku-guided-fresh](10-haiku-guided-fresh/result.json) | 37 | yes | 0 / no | n/a | 0 / 0 | 15 / 15 | $0.02482 | pass |
| [11-haiku-inventory-fresh](11-haiku-inventory-fresh/result.json) | 0 | no | 0 / no | n/a | 98 / 0 | 16 / 12 | $0.02471 | pass |
| [12-gemini-paused-fresh](12-gemini-paused-fresh/result.json) | 0 | no | 0 / no | n/a | 0 / 0 | 16 / 9 | $0.07799 | pass |
| [13-haiku-notes-fresh](13-haiku-notes-fresh/result.json) | 5 | no | 0 / no | n/a | 6 / 0 | 9 / 9 | $0.00461 | pass |
| [14-haiku-longhold-fresh](14-haiku-longhold-fresh/result.json) | 24 | yes | 0 / no | n/a | 6 / 0 | 15 / 15 | $0.02485 | pass |
| [15-haiku-motor-fresh](15-haiku-motor-fresh/result.json) | 0 | no | 0 / no | n/a | 6 / 0 | 13 / 13 | $0.02119 | pass |
| [16-deepseek-json-fresh](16-deepseek-json-fresh/result.json) | 0 | no | 0 / no | n/a | 61 / 0 | 15 / 15 | $0.00367 | pass |
| [17-haiku-checkpoints-fresh](17-haiku-checkpoints-fresh/result.json) | 12 | no | 0 / no | n/a | 39 / 0 | 14 / 14 | $0.02240 | pass |
| [18-haiku-peaceful-fresh](18-haiku-peaceful-fresh/result.json) | 35 | yes | 0 / no | n/a | 0 / 0 | 16 / 16 | $0.02906 | pass |
| [19-gemini-guided-fresh](19-gemini-guided-fresh/result.json) | 2 | no | 0 / no | n/a | 0 / 0 | 15 / 8 | $0.08029 | pass |
| [N01-gemini-normalized-fresh](N01-gemini-normalized-fresh/result.json) | 89 | no | 0 / no | n/a | 82 / 0 | 16 / 9 | $0.06766 | pass |
| [N03-haiku-normalized-fresh](N03-haiku-normalized-fresh/result.json) | 45 | no | 0 / no | n/a | 55 / 0 | 14 / 14 | $0.02343 | pass |
| [N04-deepseek-normalized-fresh](N04-deepseek-normalized-fresh/result.json) | 0 | no | 0 / no | n/a | 35 / 0 | 16 / 9 | $0.00492 | pass |

## Prepared crafting

Starting 50 wood, 50 stone and 5 gel are inherited setup. Wood maxima include inherited stock; wood checkpoints are excluded from progress. Workbench/torch/furnace columns measure newly observed possession, not independent proof of the crafting operation.

| Attempt | Wood max | Bench | Torches max / furnace | Target damage / killed | Damage received / deaths | Calls / frames | Cost | Audit |
|---|---:|---|---|---|---|---|---:|---|
| [03-haiku-json-crafting](03-haiku-json-crafting/result.json) | 50 | yes | 0 / no | n/a | 98 / 0 | 15 / 15 | $0.02780 | pass |
| [20-haiku-tools-crafting](20-haiku-tools-crafting/result.json) | 50 | no | 0 / no | n/a | 104 / 1 | 16 / 17 | $0.03156 | pass |
| [21-haiku-inventory-crafting](21-haiku-inventory-crafting/result.json) | 50 | yes | 0 / no | n/a | 14 / 0 | 16 / 8 | $0.02049 | pass |
| [22-gemini-json-crafting](22-gemini-json-crafting/result.json) | 50 | yes | 15 / no | n/a | 106 / 1 | 10 / 10 | $0.08888 | pass_with_inert_tail |
| [23-haiku-guided-crafting](23-haiku-guided-crafting/result.json) | 50 | yes | 0 / no | n/a | 69 / 0 | 16 / 16 | $0.03058 | pass |

## Prepared combat

Guide removed; one blue slime is armed after window setup. The initial rendered frame may precede the spawn. Target death and attributed player damage are distinct; the original operator positive control verified one hit, but not the kill detector. These attempts do not establish a clean clock effect.

| Attempt | Wood max | Bench | Torches max / furnace | Target damage / killed | Damage received / deaths | Calls / frames | Cost | Audit |
|---|---:|---|---|---|---|---|---:|---|
| [02-haiku-paused-slime](02-haiku-paused-slime/result.json) | 0 | no | 0 / no | 0 / no | 0 / 0 | 16 / 17 | $0.02552 | pass |
| [24-haiku-tools-slime](24-haiku-tools-slime/result.json) | 0 | no | 0 / no | 0 / no | 132 / 1 | 16 / 17 | $0.02760 | pass |
| [N02-gemini-normalized-slime](N02-gemini-normalized-slime/result.json) | 0 | no | 0 / no | 0 / no | 54 / 0 | 16 / 9 | $0.07700 | pass |

## Interpretation boundaries

- Equal API calls do not mean equal action/observation opportunities. Stop limits include nominal observer updates; inference and cleanup can cross the simulation threshold. This is not an exact fixed-tick API.
- PvE is enabled except the explicitly labeled peaceful ablation. Natural hostile encounters differ. Received damage is not evidence of successful combat; natural loot may come from the Guide.
- A partial audit marks an unaccounted provider response/charge, not a model failure. Completed unsuccessful agent trajectories are retained.
- A qualified `pass_with_inert_tail` requires an exact exported journal prefix followed only by heartbeats with identical observed state and advancing timestamps/ticks. Raw data and original result stay unchanged. Future runs wait for process termination before export.
- Named native coding-agent frameworks, learned motor policies, new world seeds, bosses and post-Hardmode progression were not evaluated.
- See [interpretation rules](../../interpretation.md), [selection plan](../../repeats-01.json) and [research rationale](../../design-rationale.md).
