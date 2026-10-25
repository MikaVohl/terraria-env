# Joint crafting prerequisites — 2026-10-11

Status: **diagnostics complete; fresh v4/v5 learning study running**.

Two preserved v4 policies were observed on the same existing validation worlds
8,000,001–8,000,128, sampler 54321. These are diagnostic evaluations, not new
reserved tests and not an algorithm comparison: the policies have different
architectures, training seeds, schedules and objective histories. Their scores
were 18.914/32 (newer recurrent selection) and 21.266/32 (earlier MLP selection).

## What actually blocks the furnace

The read-only C observer checks the exact joint conditions for the implemented
furnace recipe: **4 wood + 20 stone + 3 torches + a workbench in range**. All 16
condition combinations were tested against the frozen handler on both versions.
Its true station-location reads are diagnostic-only; the policy still sees its
normal partial observation and legal mask. State, rewards and actions are not
changed. Statistics below stop at the first furnace achievement, where relevant,
so post-crafting resource consumption does not create a spurious bottleneck.

| Diagnostic | Newer recurrent policy | Earlier successful MLP |
| --- | ---: | ---: |
| Episodes with any legal furnace opportunity | 0/128 | 108/128 |
| Missing 4 wood, when stone is sufficient and before first furnace | 97.9% of actions | 61.9% |
| Missing nearby workbench under the same condition | 98.2% | 96.5% |
| Missing both wood and nearby workbench | 96.1% | 58.5% |
| Missing 3 torches under the same condition | 52.7% | 21.0% |
| Bench selected, conditional on carrying one (whole episode) | 2.5% | 19.2% |
| Wood acquired per episode, including recovered placed wood | 33.5 | 58.4 |
| Wood consumed making platforms per episode (whole episode) | 9.85 | 3.75 |

The percentages are action-weighted, overlapping prerequisite failures, not
exclusive causes or per-world averages. The two policies spend different amounts
of time before their first furnace; this is attribution, not a causal treatment.

The newer policy has 319,760 stone-sufficient actions before its first furnace
would have been earned, yet **zero** complete opportunities. It carries benches
for 38,031 actions and physically has at least one valid placement footprint
on every one of those actions, but selects the bench on only 958. It does place
and recover benches sometimes (526 placements, 387 removals), so placement is
not categorically impossible. Benches exist out of range on 84.4% of all actions.

The successful policy gets 108 first opportunities and immediately crafts in
all 108. Across the entire episode it crafts on all 181 legal opportunities;
mean conditional action probability is 99.7%. Rare opportunities are enough
when the policy makes the prerequisites coincide.

**Interpretation:** the problem is joint resource retention/reacquisition and
workshop access, not a missing furnace action or insufficient stone. The newer
policy spends its small wood supply on benches, swords, torches and especially
platforms, then continues exploring without assembling a workshop. Wood gathering
has only a one-time achievement reward even though its later utility repeats.
That is a legitimate long-horizon learning challenge, not grounds for an expert
wood-reservation rule. These measurements do not prove that changing platform
costs, adding direct item selection or increasing memory will fix it.

## Improvements worth testing next

1. **Neutral inventory selection interface**, in a separate version: directly
   select any owned placeable with one primitive action, mirrored in the human
   UI. Do not auto-select a workbench based on a goal. Current human clicks also
   enqueue selection-cycle actions, so this is removal of shared interface
   friction, not repair of an existing free-action human advantage.
2. **Replay-capable general learning**, so rare crafting breakthroughs are
   reused rather than discarded after PPO updates. A world-model/replay baseline
   is a candidate; simply feeding old trajectories into on-policy PPO without
   appropriate corrections is not a valid implementation.
3. **Generic predictive auxiliary learning** of observed inventory changes,
   next observations or rewards, versus a capacity-matched control. No labels
   such as "save four wood for furnace", demonstrations or recipe-specific bonus.
4. Test longer recurrent training fragments only after measuring persistent
   memory and critic learning; the previous 128-step recurrent package did not
   solve crafting. Its state can persist beyond 128 steps, so that number is not
   a hard memory horizon.

These are proposed follow-on treatments, not silently added to the running
footprint study. That study first compares fresh MLP, shared-target and recurrent
packages across v4/v5, all with the same respective learner source/settings.

## v5 simulator cost confirmation

Five alternating-order pairs, three repetitions per harness, **without concurrent
RL jobs** on the active desktop. Random legal-action workloads include masks,
steps, observations and resets; these are not identical trajectories or neural
training timings.

- Core medians: v4 1,282,361; v5 1,283,447 transitions/s.
- Native batch medians: v4 961,420; v5 954,742 transitions/s.
- Median paired batch ratio: **0.9884** (about 1.2% lower); pair range
  0.9799–1.0059. The predeclared maximum 10% simulator loss gate passes.

This confirms no large simulation cost in this workload, not learning
non-inferiority. That requires the fresh study in
[FOOTPRINT_LEARNING_PROTOCOL.md](FOOTPRINT_LEARNING_PROTOCOL.md).

Full diagnostic records and benchmark repetitions are preserved in
`experiments/footprints-v45-20261011.UpxFLW`; compact evidence is in
[CRAFTING_BOTTLENECKS_2026_10.json](CRAFTING_BOTTLENECKS_2026_10.json).
