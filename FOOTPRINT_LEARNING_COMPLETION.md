# Completing the paired v4/v5 study — 2026-10-12

Status: **complete and artifact-audited**, 2026-10-12. Authorized by the user's request
"Run the rest of the runs." This supersedes the previous evening time cutoff;
there is no new wall-clock deadline. The earlier stopped cohort and its
[partial report](FOOTPRINT_LEARNING_PARTIAL_2026_10.md) remain intact.

Completion cohort:
`experiments/footprints-v45-complete-20261012.JabnGY`.
Protocol: `study-protocol.json`; detailed restart/copy provenance:
`completion-plan.json`; progress: `status.json` and `runner.log`.

## What is retained and what is newly trained

- **15 complete original runs** are retained as verified byte-for-byte artifact
  copies; they are not retrained. All six completed calibration runs are also
  reused, without new calibration training.
- **Three interrupted trials restart from scratch:** v5 targets seed 503,
  v4 memory seed 503 and v5 memory seed 503. The old checkpoints lack optimizer,
  environment and RNG state for exact training resume. None is warm-started.
- **Twelve previously unstarted trials:** all three policy packages on both
  versions for seeds 504 and 505, fresh initialization.

New main training is **251,658,240 transitions across 15 runs**. Together with
the retained 251,658,240, the final comparison contains the original planned
**503,316,480 transitions across 30 fresh-initialized full runs**, five paired
seeds per package. The interrupted original attempts consumed at least another
12,582,912 checkpoint-backed transitions; these remain preserved but excluded
from final full-run comparisons. Retained-trial compute is not total physical
compute, and prior partial checkpoints are not extra independent seeds.

## What stays frozen

Both variants are copied from the stopped cohort, not today's working tree.
Every gameplay/learner/tool/library source hash matches the original protocol.
Only the new supervisor's orchestration is changed: skip and revalidate verified
complete trial directories rather than failing because they exist. Existing
incomplete directories in the new cohort still fail closed; no automatic retries.
Fresh exclusive run-start guard, source checks and failure preservation remain.

Budgets, 16M-ending LR schedules, method settings, validation seeds, original
queue order among remaining trials, masks/rewards and predeclared paired
selection/test rules are unchanged. Restarts are due to user timing, not model
score. Same paired RNG seeds do not imply identical rollout data; measurements
span two dates and shared-desktop contention, not dedicated-device equal FLOPs.

Validation remains 10,000,001–10,000,128. Reserved tests 11,000,001–11,000,128
were unconsumed at launch and are **now consumed once per version**. After all
30 main results existed, the paired memory/501 selection was frozen before
either test. Both exclusive claims/128-world records, all 30 final-policy
crafting diagnostics and exact checkpoint-reproduced Python/SDL seed-9 replays
are audited. Do not rerun consumed or ambiguous
claims or tune against test results. No game/default model promotion is automatic.

Final reports: [FOOTPRINT_LEARNING_2026_10.md](FOOTPRINT_LEARNING_2026_10.md),
numeric JSON and [audit](FOOTPRINT_LEARNING_2026_10.audit.json); partial reports
stay historical. The completion follow-up audited results, updated project
documents and paused. MLP improves on average; targets/memory decline, and all
five-seed non-inferiority gates are inconclusive. No defaults promoted.
No additional algorithms/game variants beyond this protocol are launched.

Actual supervisor interval: **15:52:40–20:09:10 UTC on October 12**, about
**4h16m including final diagnostics/tests/replays**. All study workers and the
supervisor-scoped sleep inhibitor have exited. No old budget timer was reactivated.
No agents, external messages, PRs, cluster access, LLM API spending, expert
cloning, strategic masks or recipe controllers are involved.
