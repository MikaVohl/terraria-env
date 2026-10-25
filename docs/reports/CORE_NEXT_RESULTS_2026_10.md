# Core/interface/replay pilot results — 2026-10-12

Status: **complete and artifact-audited**. See [implementation and protocol](CORE_NEXT_2026_10.md).

| Version/method | Seed | Transitions | Final/latest score /32 | Death | Bench / stone / furnace / anvil worlds out of 32 |
| --- | ---: | ---: | ---: | ---: | --- |
| v6/ppo | 601 | 4,194,304 | 10.188 | 9.4% | 32 / 0 / 0 / 0 |
| v7/ppo | 601 | 4,194,304 | 10.406 | 0.0% | 32 / 0 / 0 / 0 |
| v7/replay | 601 | 4,194,304 | 6.781 | 50.0% | 12 / 7 / 0 / 0 |
| v7/ppo | 602 | 4,194,304 | 10.562 | 0.0% | 32 / 0 / 0 / 0 |
| v6/ppo | 602 | 4,194,304 | 10.031 | 12.5% | 31 / 0 / 0 / 0 |
| v7/replay | 602 | 4,194,304 | 4.156 | 68.8% | 6 / 6 / 0 / 0 |

Six fresh 4M-ending runs total **25,165,824 main transitions**. Validation 13,000,001–13,000,032 only; all reserved test worlds remain unused. Two seeds are exploratory, not a non-inferiority or architecture proof. PPO evaluation is categorical, Q evaluation greedy.

v6/ppo: mean 10.109/32; furnace 0/64; mean wall 260.9s.
v7/ppo: mean 10.484/32; furnace 0/64; mean wall 264.8s.
v7/replay: mean 5.469/32; furnace 0/64; mean wall 343.3s.

All final-policy diagnostics reproduce their corresponding final validation means. See numeric evidence for source hashes, resource sinks, legal furnace opportunities and action-weighted joint prerequisites. Main v4/default policies are unchanged. No additional experiment or reserved evaluation is implied by this report.

Initial interpretation: direct selection increases conditional carried-bench selection (6.6%→36.6% for seed601, 11.4%→40.2% for seed602), but neither PPO seed collects stone. No stone-sufficient furnace opportunities occur in any of the six policies. The interface intervention did not solve progression in this small-budget pilot. Replay reaches stone in 13/64 worlds but scores lower with higher mortality; it is not a demonstrated improvement, nor a verdict against experience reuse/world models. Cross-method world seed streams also differ (PPO seed×10M, replay seed), so retain this as an exploratory package comparison.

## Follow-on mining-reliable package control

Status: **complete**. Chosen after inspecting the first pilot, not a preregistered confirmation. Same frozen game/learner bytes; targets128/lambda.99/entropy.03 versus earlier MLP512/lambda.95/entropy.01 is a package contrast. V6/v7 within targets compares the interface separately. Four additional fresh4M trials (16,777,216 transitions), no reserved evaluation.

| Version/package | Seed | Transitions | Score /32 | Bench / stone / furnace / anvil worlds out of 32 |
| --- | ---: | ---: | ---: | --- |
| v6/targets | 601 | 4,194,304 | 14.969 | 0 / 31 / 0 / 0 |
| v7/targets | 601 | 4,194,304 | 15.312 | 0 / 32 / 0 / 0 |
| v7/targets | 602 | 4,194,304 | 15.219 | 0 / 32 / 0 / 0 |
| v6/targets | 602 | 4,194,304 | 15.594 | 0 / 32 / 0 / 0 |

Total new main training across both stages: **41,943,040 transitions, 10 full runs**. All final diagnostic scores and frozen hashes match; no defaults promoted or tests consumed.

Control interpretation: targets reach stone in63/64 v6 worlds and64/64 v7 worlds, but craft zero benches/furnaces. Means are15.281 versus15.266/32 (paired score changes +.344/−.375). The interface alone does not address production of the first workshop station. Wood is below4 on >99.9% of stone-sufficient pre-furnace actions in every control policy, and a nearby bench is absent100%; those are overlapping descriptive fractions, not isolated causes.

Next agent research should address prerequisite discovery/resource allocation with general representations and experience reuse/predictive learning, using the mining-reliable control. Do not scale a surface-bound4M-ending policy by extending an annealed-to-zero checkpoint. A new32M schedule is a different fresh-budget experiment; no such run was launched here. Uniform Double DQN’s poor pilot is not a verdict against replay or Dreamer. Tool/ore correctness fixes are useful independently of an immediate score gain.
