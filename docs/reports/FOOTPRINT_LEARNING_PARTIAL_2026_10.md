# Time-limited v4/v5 learning evidence

Status: **partial — user-requested wall budget**, not a completed five-seed study.

Completed 16M runs: 15/30 (251,658,240 transitions). Across completed and unfinished runs, at least 264,241,152 transitions are represented by valid recorded checkpoints.

The original frozen sources, budgets, LR schedules and queue were not changed. An external user-authorized deadline ended computation. Reserved tests remain unused unless claims are explicitly listed below.

| Package | Completed paired seeds | v4 final mean /32 | v5 final mean /32 | Mean v5−v4 |
| --- | ---: | ---: | ---: | ---: |
| mlp | 3 | 15.854 | 21.562 | +5.708 |
| targets | 2 | 18.008 | 17.137 | -0.871 |
| memory | 2 | 18.469 | 16.969 | -1.500 |

## Audited interpretation

Training stopped at **6:52:34 p.m. Edmonton on 2026-10-11**, following the user's
revised request to finish by 7 p.m. All workers and the prior timer are stopped.
There are 15 complete runs, three interrupted trials and twelve never started.
The supervisor's KeyboardInterrupt records the requested stop, not a failure.

| Package | Matched episodes/version | Furnaces v4/v5 | Anvils v4/v5 | Deaths v4/v5 |
| --- | ---: | ---: | ---: | ---: |
| Plain PPO | 384 | 42 / 248 | 0 / 21 | 1.8% / 3.1% |
| Shared targets | 256 | 5 / 0 | 1 / 0 | 14.8% / 18.0% |
| Recurrent targets | 256 | 7 / 0 | 1 / 0 | 17.6% / 13.7% |

Plain PPO's furnace rate rose **10.9%→64.6%**. Its v5 runs also earned wood
armor in 99/384 episodes and a metal sword in 1/384, but no iron/gold pickaxes
or iron armor. The crafting plateau moved downstream, not to full mastery.
Its paired score differences were +6.594, −0.367, +10.898: two strong gains,
one essentially flat result. The best final v5 score, 23.555/32, is validation
evidence, not a new reserved-test result or official champion selection.

The footprint package is therefore learnable by generic plain PPO, but is not
a universal improvement. Both completed spatial/recurrent pairs lost score.
The unfinished third spatial pair favored v5 at common 4M/8M checkpoints;
it is not included in the final table. Do not attribute the differences solely
to sprite size: placement, station interaction and generation geometry change
together. The causal mechanism was not isolated.

Exploratory paired score intervals are MLP −8.41 to +19.83 (n=3), targets −6.08
to +4.34 (n=2), recurrence −2.49 to −0.51 (n=2). Tiny samples, distributional
assumptions and multiple packages limit interpretation. None establishes the
original five-seed non-inferiority gate. Memory lost score but had fewer deaths.

The no-concurrent-RL simulator ratio was 0.9884, passing the 10% cost gate.
Matched mean wall/run minutes were MLP 20.72/20.36, targets 32.82/34.40,
recurrence 48.48/48.20 (v4/v5), under shared-desktop contention. No large
footprint runtime cost is apparent; these are not isolated efficiency ceilings.

Keep v5 as a credible fidelity candidate, with v4 still the default. Plain PPO
is a useful reference for future work. Neutral inventory selection, resource
reacquisition, workshop access, independent tools and necessary material supply
remain separate hypotheses/design treatments, not changes made during this run.
Earlier v4 joint-prerequisite diagnostics cannot explain the v5 gains causally.
The final diagnostic/replay/selection stages were not reached; no new neural
experiments, diagnostic rollouts or tests filled that gap after stopping.

Artifact audit passed: 15 summaries, **63 evaluated checkpoint hashes**, all
run-package snapshots, **73 v4 / 74 v5 frozen files**, the supervisor hash,
declared validation-world records and recomputed paired means. Prior studies,
failed ZtrJ6E and the preview remain intact. No selection directory or test
claims exist. [Machine-readable audit](FOOTPRINT_LEARNING_PARTIAL_2026_10.audit.json).

## Interpretation limits

Only completed, matched 16M v4/v5 pairs enter the final table. Equal-step partial checkpoint comparisons are retained in JSON, separately. Do not compare mismatched budgets, count checkpoints as independent seeds, or call the five-seed non-inferiority gate passed from a truncated subset.

Completion/queue order, not an outcome-based stopping rule, determines which runs are available. Partial training is not resumable by the current frozen trainer; existing artifacts must never be silently restarted or pooled with a repaired implementation.

Reserved test claims: []. No test was invoked by this budget controller. No game/model defaults promoted.

Artifacts: `/Users/mikavohl/Projects/terraria-lite/experiments/footprints-v45-20261011.UpxFLW`. Full partial evidence: `FOOTPRINT_LEARNING_PARTIAL_2026_10.json`.
