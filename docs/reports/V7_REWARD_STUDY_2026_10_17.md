# V7 progression and reward/discount study — 2026-10-17

Status: complete and artifact-audited.

25 fresh 16M-ending trials; **419,430,400 main transitions**, five paired training seeds. All headline evaluations retain unweighted achievement counts and native death penalties. No reserved tests or default promotions.

| Cell | Mean /32 ± sample SD | Per-seed scores | Bench / furnace / anvil worlds /640 | Death |
| --- | --- | --- | --- | --- |
| v4-equal-g999 | 17.967 ± 0.555 | 18.297, 17.383, 17.500, 18.719, 17.938 | 501 / 10 / 1 | 17.0% |
| v7-equal-g999 | 16.675 ± 0.148 | 16.586, 16.820, 16.797, 16.469, 16.703 | 3 / 0 / 0 | 10.2% |
| v7-equal-g1 | 15.895 ± 1.020 | 14.125, 16.203, 16.219, 16.164, 16.766 | 0 / 0 / 0 | 5.5% |
| v7-difficulty-g999 | 16.334 ± 1.308 | 15.016, 18.008, 15.711, 15.500, 17.438 | 278 / 0 / 0 | 7.5% |
| v7-difficulty-g1 | 15.141 ± 1.033 | 14.945, 16.078, 13.641, 14.883, 16.156 | 0 / 0 / 0 | 3.3% |

## Prespecified score contrasts

| Contrast | Paired mean | Descriptive 95% | Four-contrast familywise 95% |
| --- | --- | --- | --- |
| v7_equal_minus_v4 | -1.292 | [-2.165, -0.420] | [-2.648, +0.064] |
| discount_main_effect | -0.987 | [-1.503, -0.470] | [-1.790, -0.184] |
| weight_main_effect | -0.548 | [-1.717, +0.622] | [-2.365, +1.270] |
| interaction | -0.414 | [-2.446, +1.618] | [-3.572, +2.743] |

Five training seeds—not 640 independent learners or four independent checkpoints. Curves, deaths, per-achievement outcomes and full joint crafting-prerequisite/resource-sink diagnostics are in the numeric report. Intervals crossing zero are inconclusive, not equivalence. V4/v7 compares bundled game versions. Difficulty tiers are subjective and maximum-total-normalized, not a proven optimal objective or a replica of Craftax's health/difficulty rewards.

Training is fresh with an unchanged 16M LR schedule, masks and observations. Tests 19,000,001–19,000,128 remain unused. Historical consumed splits were not evaluated. Existing v4 default, old studies, interrupted checkpoints and v5–v7 previews are preserved.

Study artifacts: `/Users/mikavohl/Projects/terraria-lite/experiments/v7-reward-20261017.sGYPqq`.

## Completed interpretation and independent audit

The original frozen reporter produced the tables above at **October17,6:49p.m.
Edmonton** (2026-10-18T00:49:21UTC). A subsequent reporting-only
[independent audit](V7_REWARD_STUDY_2026_10_17.audit.json), implemented in
[tools/audit_v7_reward_study.py](../../tools/audit_v7_reward_study.py), verifies all25
summaries,100 distinct checkpoint hashes and metadata,100 validation curve
points/12,800 world records, both complete frozen source/binary manifests,
probe and diagnostic hashes, reward/config metadata and exact counts. All3,200
final diagnostic outcomes match final validation **per world**, including
achievement masks, health, action counts and returns, not just average scores.
No new inference, replay, training, test evaluation or selection was needed for
this audit. Raw study `results.json` is byte-identical to the numeric report;
that generated numeric evidence remains unchanged.

### What the factorial says

- **Keep .999 as the reference for this PPO package.** Changing to1.0 has a
  negative score main effect in every paired seed, averaging **−0.987/32**.
  Its Bonferroni98.75% interval **[−1.790,−0.184]** excludes zero. The
  corresponding death-rate change is −4.45 percentage points (descriptive95%
  interval [−8.28,−0.62]): better survival is not better progression. This is
  evidence about the tested16M learner/settings, not proof that undiscounted RL
  or longer-horizon methods cannot work. Lambda remains.99 and rollout128;
  setting gamma1 does not create perfect long-range credit assignment.
- **Difficulty weighting did not establish a headline improvement.** The
  main score effect is −0.548 with a wide family-adjusted interval
  [−2.365,+1.270]; the interaction is also inconclusive. At gamma.999 it
  does alter workshop behavior: bench coverage rises **3/640→278/640**, but
  final furnaces remain **0/640**. Bench counts by training seed are0/127/0/25/126
  for weighted versus0/1/2/0/0 for equal rewards. Thus this is a seed-dependent
  upstream behavior change, not a reliable solution to the crafting chain.
  At gamma1 both reward arms have zero benches. Maximum-total normalization
  does not equalize actual experienced reward density, advantage scaling or
  death penalty relative to encountered achievements.
- **V7 is not a demonstrated policy improvement over v4.** The equal/.999
  paired score difference is negative in all five seeds, −1.292 on average.
  Its descriptive95% interval excludes zero, but the predeclared
  four-primary-contrast interval reaches +0.064: the family-adjusted verdict is
  **inconclusive**, with a consistently negative observed direction, not
  equivalence or a formally established adjusted-significance result. This
  compares bundled environments, not isolated effects of object scale, direct
  selection, ore supply or tool ownership. No non-inferiority test was
  predeclared here.

Death, furnace and anvil paired intervals are retained in the numeric report
and audit, in rate units. V7equal−v4 death is −6.88pp (descriptive95%
[−14.15,+0.40]); furnace −1.56pp [−4.04,+0.91]; anvil −0.16pp [−0.59,+0.28].
V4 has10 furnaces and1 anvil in640 final validation worlds. All v7 furnace/anvil
factorial contrasts are observed zero. Their algebraic paired-t intervals
collapse to [0,0] because all five samples are zero; **this is not evidence
that the underlying rare-event probabilities or method effects are exactly
zero**. Secondary rate intervals are descriptive, not multiplicity-adjusted.

### Complete learning curves, without early-winner selection

Values below average the same five training seeds at every checkpoint.
Checkpoints use the original16M-ending LR schedule, not independently trained
4M/8M/12M policies, and are correlated observations of each learner.

| Condition | 4.19M | 8.39M | 12.58M | 16.78M |
| --- | ---: | ---: | ---: | ---: |
| v4 equal,.999 | 14.258 | 17.216 | 17.744 | 17.967 |
| v7 equal,.999 | 14.931 | 16.023 | 16.466 | 16.675 |
| v7 equal,1.0 | 10.295 | 14.528 | 15.281 | 15.895 |
| v7 difficulty,.999 | 12.381 | 15.175 | 15.794 | 16.334 |
| v7 difficulty,1.0 | 11.298 | 13.891 | 14.600 | 15.141 |

V7equal starts ahead at4M, but v4 is ahead from8M onward. All five means still
improve late in training; the result is not a proof of an asymptotic ceiling.
The persistent workshop gap is more informative than selecting a favorable
early checkpoint. Weighted/.999 seed802 does craft a furnace in **one
validation world at8.39M**, but none at16.78M. Thus "never discovered furnace
behavior" would be inaccurate; the observed rare intermediate success is not
sustained. This is a validation trajectory, not a measurement of training-time
discovery or proof of catastrophic forgetting. No checkpoint or policy was
selected/promoted or evaluated on reserved tests.

### The remaining bottleneck is coordinated workshop preparation

The observer is read-only and never informs policy inputs, masks or rewards.
Its furnace gate is joint **wood≥4, stone≥20, torches≥3, nearby workbench**.
Action counts below refer to pre-action states, not independent statistical
samples. World/step pooling is descriptive only; the five learners remain the
experimental units.

| Condition | Wood acquired/world | Worlds with any furnace opportunity /640 | Pre-first-furnace joint legal actions | Missing both wood and nearby bench, conditional on sufficient stone |
| --- | ---: | ---: | ---: | ---: |
| v4 equal,.999 | 35.67 | 10 | 12 | 93.88% |
| v7 equal,.999 | 16.82 | 0 | 0 | 99.24% |
| v7 equal,1.0 | 33.23 | 0 | 0 | 99.13% |
| v7 difficulty,.999 | 23.67 | 1 | 13 | 98.68% |
| v7 difficulty,1.0 | 20.24 | 0 | 0 | 99.86% |

For v7equal/.999, average pre-furnace wood sinks are5.84 on platforms,8.84
on block placement and2.04 on torches; only0.047 on benches. Increasing total
wood alone is not an established fix: v7equal/gamma1 acquires33.23 per world
but spends22.27 on block placement and7.61 on platforms and never crafts a
bench. These are legitimate actions with competing downstream uses, not
illegal-action bugs. Timing and simultaneous retention of resources matter.

Weighted/.999 uses7.45wood/world on benches,5.00 on platforms,8.01 on placement
and1.86 on torches. It creates687 station placements and836 departures from
bench range across the640 trajectories, yet reaches just one joint opportunity.
That opportunity lasts13 actions and the agent never chooses the furnace.
V4 chooses it10 times across12 joint pre-first-furnace legal actions. It would
be misleading to call the single weighted opportunity evidence of a general
furnace-action avoidance mechanism: almost all failures occur **before the
full prerequisite state exists**.

Physical placement space exists on99.95–100% of ticks when a bench is carried
in groups that carry any. Bench selection occurs on3.60%/10.20%/19.91% of
owned-bench ticks for v4equal, v7equal and v7weighted at.999 respectively.
The two gamma1 groups never carry benches, so that conditional ratio is
undefined. Direct selection has not automatically solved coordination, and
lack of placement space is not the main observed gate in these trajectories.
Neither conditional telemetry nor this bundled comparison isolates the causal
effect of menu design, footprints, memory or resource scarcity.

### Direction, with no new experiments launched

Retain the finite-deadline correction, legal masks and neutral interfaces, and
leave **v4/default policies unchanged**. Do not adopt gamma1 or these reward
tiers as a proven improvement. V7 can remain a useful, mechanically cleaner
preview without pretending that this learner progresses further on it.

The next research proposal is a **generic experience-reuse/predictive-learning
baseline** on one frozen contract, with a fresh PPO control, matched transition
and practical compute accounting, and held-out evaluation reserved in advance.
It should test whether rare successful preparation sequences can be learned
and reused, rather than prescribing recipes or masking resource spending.
Representation/time-context ablations may also be useful, but the previous
memory/RND results and this gamma experiment caution against assuming that
more memory, longer discount or simply more weights will solve crafting.
No such follow-on, controller, shaping, API spend or game edit is authorized
or launched by this completion audit.

### Orchestration and timing provenance

The [explicit user-requested amendment](V7_REWARD_PARALLEL_AMENDMENT_2026_10_17.md)
preserved all frozen gameplay/learner/probe/supervisor bytes and original
protocol hash. Twenty-one runs were complete; three original workers kept
their PIDs/start identities and live optimizer/RNG state. Exactly one new
fresh trial, `v7-difficulty-g999-805`, was dispatched by the hashed coordinator.
The original24 dispatch records plus that one launch cover each of25 trials
once. The old suspended dispatcher was removed without dispatching it again.
All main workers, diagnostic workers, coordinator27793 and old dispatcher99218
are now absent. Completion and launch records/hashes are in the audit.

The original21 three-way trials took a median **35.16min** including validation
(range34.42–37.37min). The three adopted final trials took37.63–37.64min each;
the newly launched last trial took31.11min, overlapping the others for only
part of its run. These contended timings are separate descriptive accounting,
**not an intrinsic method throughput comparison or a concurrency speedup
experiment**. Measured optimization accounts for76.3–76.9% of collection plus
optimization time by condition; physics alone is not the dominant cost in
these runs. The complete study plus original diagnostics/report ran from
1:45p.m. to6:49p.m. Edmonton, about5h04m.

The completed follow-up is paused. Both earlier completed studies, interrupted
cohorts, failed calibration ZtrJ6E, object-scale preview and v5–v7 snapshots
remain preserved. Reserved19,000,001–19,000,128 has no claim or evaluation
record and remains unused; earlier consumed splits were not touched.
