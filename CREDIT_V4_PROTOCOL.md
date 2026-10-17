# v4 finite-horizon and learning study — 2026-10-11

Status: **completed and audited on 2026-10-11**. This document preserves the
predeclared launch protocol; results are in [CREDIT_V4_2026_10.md](CREDIT_V4_2026_10.md)
and [CREDIT_V4_2026_10.json](CREDIT_V4_2026_10.json). The earlier study remains
preserved in [LEARNING_V4_2026_10.md](LEARNING_V4_2026_10.md).
The final stage/process ledger is in
`experiments/credit-v4-20261011.naYwbC/status.json`; the supervisor log is
`experiments/credit-v4-20261011.naYwbC/runner.log`.

## Questions

1. How much did incorrectly bootstrapping value at the benchmark's inherent
   3000-action deadline affect learning?
2. Does removing discounting, extending credit traces/fragments, adding general
   spatial recurrence or persistent generic novelty improve progression?
3. Do promising changes reproduce across five training seeds at 16M?

Production gameplay and art are byte-identical at the source level to the
previous study: v4, 2×3 player, 73 primitive actions, local observation, 32
achievements, 3000-action limit, +1 new achievement and −1 death. No expert
cloning, prerequisite shaping, strategic masks or hand-coded action macros.
The RND condition alone adds a generic **training-only** novelty bonus;
evaluation always uses the unmodified achievement/death reward.

## Deadline correctness

The API labels running out of actions as a truncation. Because this budget is
part of our task, future value at that endpoint must be zero. Both PPO trainers
now use zero by default; `bootstrap_time_limit=True` is an explicitly labelled
legacy/external-truncation control. Unfinished rollout fragments still
bootstrap. Environment rules, checkpoint evaluation compatibility and historical
results are unchanged. All study checkpoints record their training objective.

The previous selected policy was audited on the new **validation** range,
not on reserved test worlds. It scored 21.266/32, with 127 deadline survivors;
their predicted terminal value mean was −0.045, median −0.180, range
−0.516 to 1.185. These are critic predictions, not future rewards. The average
error is small for this particular trained policy; this is not evidence that
the correction necessarily improves training. Matched controls answer that.

## Predeclared comparisons

Five paired training seeds: **101, 202, 303, 404, 405**. All screen runs start
from scratch at **4,194,304 transitions** with the same annealed learning-rate
schedule. The finite target control uses λ=.99, entropy=.03, γ=.999,
64 environments × 128 actions, four epochs/four minibatches, LR=.0003,
six Torch threads and CPU. The MLP pair uses λ=.95, entropy=.01.

| Condition | Difference from matched control |
| --- | --- |
| legacy_mlp / finite_mlp | Deadline bootstrap on / off, otherwise identical |
| legacy_targets / finite_targets | Deadline bootstrap on / off, otherwise identical |
| undiscounted | finite_targets with γ=1 |
| trace | finite_targets with λ=.995 |
| long_rollout | 512-step fragments, 16 minibatches; still 2048 samples/minibatch |
| memory | Same shared spatial target encoder/scorer, plus residual LSTM global memory |
| novelty | Balanced observation RND, coefficient .001, persistent rather than annealed |

Longer fragments also change batch size and policy-refresh cadence. Recurrence
adds parameters and uses sequence minibatches/truncated backpropagation.
Neither is a perfectly isolated causal test of “horizon” or “memory capacity.”
RND includes all observation modalities without choosing desirable recipes or
states; its bonus is capped at .005/action. It is an exploration intervention,
not an extrinsic-only baseline or a recipe controller.

The highest five-seed **final** screen mean among finite_mlp and the five new
conditions is selected for fresh **16,777,216-step** trials. Ties prefer lower
deaths, then name. That alternative and finite_targets each train all five
seeds again from scratch. Both use their own full-budget annealing schedule.
Scaling proceeds even if no alternative wins at 4M, to check delayed learning;
no test results enter this decision.

Total: **356,515,840 main transitions across 55 independent runs**, plus
**294,912 calibration transitions**. This is not one agent trained for 356M
steps. Up to three jobs share the active desktop; equal transitions are not
equal compute. Phase times and conservative same-wall checkpoint snapshots
will be reported with their limitations.

## Selection and reserved test

Validation: **8,000,001–8,000,128**. Reserved test:
**9,000,001–9,000,128**. Sampler seed 54321.

After all main runs finish, select the highest validation mean across corrected-
objective checkpoints; ties prefer lower deaths, fewer steps and run name.
Legacy-bootstrap controls cannot become the official selected model.
The manifest and checkpoint copy are frozen before the **single** test.
Never use or rerun this test for tuning. Previously consumed ranges are not
reused. No default model/checkpoint is automatically promoted.

## Verification and automation

Passed before main trials:

- Final-action targets with zero future value; death/deadline overlap; no reset
  world leakage; finite γ=λ=1 returns equal exact Monte Carlo returns;
  unfinished fragments retain their bootstrap.
- 64,000 scalar/native transitions, 1/2/4/8 workers, encoding/legal-support
  checks, checkpoint reloads and fixed RND target checks.
- Recurrent target step/sequence agreement, state resets, finite gradients
  through both sequence heads and single-step inference.
- Nine end-to-end calibration runs. Old/corrected MLP and target weights are
  exactly identical after 32,768 transitions, before any lane can hit 3000.
- The recurrent calibration policy reproduces its sampled tape exactly, and
  Python and SDL agree on its final state. This is a correctness check, not a
  proficiency result.
- Game mechanics on 100 worlds, 24,000 light edits, all original texture and
  UI fixtures. No gameplay sources changed.

A first calibration snapshot, `experiments/credit-v4-20261011.ZtrJ6E`, caught
a recurrent sequence-head shape error before any main trials. Its artifacts
are preserved, excluded from main results, and replaced by a freshly frozen
snapshot after adding an optimizer-path regression. No official main runs mix
the two implementations.

The supervisor advances stages, writes logs, checks hashes and stops on
failures. It finalizes selection, one-shot testing, validation diagnostics,
deadline audit and exact replay automatically, then creates
`CREDIT_V4_2026_10.json` and `CREDIT_V4_2026_10.md` in the repo. An app follow-up
checked completion/failure and audited the report; it stayed quiet while healthy
and is paused after completion. All 55 main runs finished and the reserved test
was consumed once; it must not be reused for tuning. Idle system sleep inhibition
was scoped to the training supervisor; no permanent power settings were changed.

The prior study's ore-supply and independent-tool-ownership limitations remain
unchanged. This study tests learners, not an easier game.
