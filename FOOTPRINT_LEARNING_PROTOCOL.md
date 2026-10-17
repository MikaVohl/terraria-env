# Fresh v4/v5 learning comparison

**2026-10-12 completion update:** the user requested the remaining runs.
[A separate completion cohort](FOOTPRINT_LEARNING_COMPLETION.md) retained
15 complete runs, restarts the three interrupted trials from scratch and trains
the twelve untouched trials with byte-identical gameplay/learner sources.
The [full study is now complete and audited](FOOTPRINT_LEARNING_2026_10.md).
The stopped cohort described below remains historical; its cutoff did not
limit the newly authorized completion. Original selection/test rules remain;
reserved tests are now consumed once per version. No defaults promoted.

Status: **stopped at user deadline; partial evidence audited**, not a completed
five-seed protocol. [Results](FOOTPRINT_LEARNING_PARTIAL_2026_10.md). Study:
`experiments/footprints-v45-20261011.UpxFLW`; frozen machine-readable protocol:
`study-protocol.json`; live ledger `status.json`, supervisor `runner.log`.

**User budget amendment:** on 2026-10-11 the user limited remaining work to
about three hours, then revised the completion target to **7 p.m. Edmonton**.
Training stopped at **6:52:34 p.m.** (2026-10-12 00:52:34 UTC). Earlier 7:23/7:33
targets no longer apply; both amendment records are preserved. The recorded
`budget-amendment.json` preserves the original protocol;
its 503M/30-run plan is now an upper bound, **not expected completed work**.
No frozen sources, LR schedules or queue order are changed. Completed matched
16M pairs and equal-step partial curves are reported separately in
`FOOTPRINT_LEARNING_PARTIAL_2026_10.json/.md`. Reserved tests are not consumed
for a truncated study, and no automatic restart or promotion is allowed.

## Scope and budget

**30 fresh runs × 16,777,216 transitions = 503,316,480 main transitions**.
Each of MLP, shared spatial target scoring, and recurrent target scoring has
five paired seeds (501–505) on v4 and v5. Six 32,768-transition calibrations add
196,608 transitions, excluded from the main budget. All six calibrations passed.
Both versions passed mechanics, original-art UI fixtures, 64k scalar/native
parity, objective/gradient/recurrent checks and the read-only observer checks.

Each full-budget run starts from scratch with a 16M-ending learning-rate
schedule; checkpoints are recorded at 4M, 8M, 12M and 16M. Primary comparisons
use **final** scores, not each run's best checkpoint. Paired seeds mean common
initial RNG seeds, not identical training trajectories or episode sequences.
Order alternates which version goes first across seeds; up to three jobs share
the Mac, so timings are contended, not isolated device ceilings.

Common: CPU, 6 Torch threads, 64 environments, 128-step rollouts, 4 epochs,
4 minibatches, gamma .999, LR .0003 annealed to zero. MLP uses lambda .95 and
entropy .01; spatial/recurrent packages use lambda .99 and entropy .03. Compare
packages, not architecture alone. Intrinsic novelty is off. Legal masks,
primitive actions, +1 new achievement/−1 death, 3000-action budget and zero
deadline bootstrap apply throughout. No expert cloning, goal controllers,
strategic masks or prerequisite shaping.

v4 is copied from the completed credit study. v5 is copied from the object-scale
preview. Learner files are byte-identical except the versioned binding docstring
(its executable AST is equal). Physics differences are confined to the recorded
seven header/source files for footprints and their worldgen, interaction, light
and UI corrections. Thus this measures the **whole footprint package**, not
sprite size alone. Recipes, tools, resources, observation/action dimensions and
achievements are unchanged. Main checkout remains v4.

## Measurement and promotion gates

Report paired five-seed v5-minus-v4 differences for achievement scores, deaths,
furnace/anvil hit rates, learning curves and measured neural/collection time.
Five-seed paired Student-t intervals are exploratory, not universal guarantees.

- Simulator gate: at most 10% median paired native-throughput loss. The completed
  no-concurrent-RL confirmation passed (batch ratio 0.9884).
- Learning support gate: each package's lower 95% score-difference bound must be
  at least −1 achievement, and its upper death-difference bound at most +5
  percentage points. Wide intervals mean **inconclusive**, not automatic failure
  or success. Report crafting regressions separately, even if aggregate scores
  pass. No automatic v5 or checkpoint promotion.

Validation: **10,000,001–10,000,128**, sampler 54321. Reserved test:
**11,000,001–11,000,128**, once **per version**, not yet consumed at launch.
After all 30 runs finish, select the package with the highest mean final
validation score across both versions and all five seeds (ties lower deaths,
then name). Within it, select the paired seed with the highest average final
v4/v5 score (ties lower deaths, then smaller seed). Freeze both final policies
and their joint selection manifest **before either test is run**. No independent
per-version winner selection and no use of tests to decide what to train next.

Each reserved evaluation creates an exclusive consumption claim before loading
the policy. A crash leaves that claim intact and cannot trigger an automatic
retry. Old consumed ranges 7M/9M are never used here. Each selected policy also
gets a seed-9 replay reproduced exactly from its checkpoint and verified against
Python/SDL. Replays are not additional reserved tests.

## Crafting attribution and provenance

The observer measures simultaneous ingredients/station range, bench carrying,
selection and placement, stations left behind and wood consumption by action.
Every final policy is diagnosed on the declared validation worlds. Hidden world
reads are **only** attribution; they do not enter learner inputs or rewards.
Current historical-policy diagnostics are completed separately in
[CRAFTING_BOTTLENECKS_2026_10.md](CRAFTING_BOTTLENECKS_2026_10.md).

All versions, binaries, learner/tools and the supervisor have frozen hashes.
Existing/partial trial directories are never silently restarted. The supervisor
stops and preserves artifacts on failure. Any training repair requires a fresh
snapshot with explicit provenance. Reporting-only repairs may be made safely.
Completed evidence will be written to `FOOTPRINT_LEARNING_2026_10.json/.md`;
the completion follow-up audits these and updates project documentation.
No extra trials are automatically spawned after the frozen protocol finishes.

The original full-study estimate was roughly **6–10 hours of awake compute**;
the user budget amendment above now takes precedence.
Sleep inhibition is scoped to the supervisor; keep the Mac powered and the app
running for the follow-up. No cluster, API spending, new agents or external
messages are involved. Previous studies, the v5 preview, and failed calibration
snapshot `ZtrJ6E` remain intact.
