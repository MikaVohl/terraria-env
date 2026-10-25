# V7 progression/reward study — launch record

Status at launch: **training**, October17, 2026, 1:45p.m. Edmonton (19:45UTC).
The first three workers are active; this is not a completed-results report.

- Study: `experiments/v7-reward-20261017.sGYPqq`.
- Supervisor launch PID: **99218**; initial worker PIDs99220/99221/99222.
- Base commit: `dc5093048bf921faf42b703dc32839fcb5abacb3`.
- Protocol: [V7_REWARD_PROTOCOL_2026_10_17.md](V7_REWARD_PROTOCOL_2026_10_17.md).
- Frozen machine protocol: `study-protocol.json` inside the study directory.
- Protocol SHA256: `5f3d6fc9114d4aff1670754897884a1aadde226afadd9594a48473a3f162cdd1`.
- Frozen supervisor SHA256: `92c7e02495bd62f13ba964b737561a1e6c4c6b2fd0cb4b5c83375b17ad558a9b`.

## Budget and comparisons

**25 fresh16M-ending runs / 419,430,400 main transitions**, paired seeds801–805.
Five cells: v4 equal/.999; v7 equal/.999; v7 equal/1.0; v7 difficulty/.999;
v7 difficulty/1.0. Spatial targets128, lambda.99, entropy.03, CPU4threads,
three concurrent workers; unchanged 64×128 batch and four epochs/minibatches.
The two version snapshots have96/98 hashed source/binary entries. V7 C sources
are byte-identical to the earlier core-next preview; main gameplay is untouched.

Equal reward is still the default. Fixed difficulty tiers are scaled by32/101
to preserve total achievement reward32, with death−1 and no health rewards.
This tests a different training objective, not a change to headline evaluation.

Fresh validation17,000,001–17,000,128 at4/8/12/16M checkpoints; final read-only
crafting diagnostics must reproduce final validation scores. No test selection:
reserved19,000,001–19,000,128 remains unused even after completion. Earlier
consumed splits, old studies, failed/partial artifacts and previews are intact.

## Preflight evidence

Both snapshots passed deterministic100-world mechanics,24,000 exact lighting
edits, 2×3 geometry/reach checks, original-art UI fixtures,64,000 scalar/native
parity transitions at1/2/4/8 workers, PPO finite-deadline/recurrent/model tests,
reward/autoreset boundary tests and pure protocol/statistics/guard tests.
V7 also passed256-world native-object tests;33 original item icons were loaded.

All five conditions then completed exactly16,384 transitions and two optimizer/
checkpoint/evaluation cycles. Total **81,920 preflight transitions**, excluded
from the main budget. Their four diagnostic worlds21,000,001–21,000,004 are
disjoint from main validation and reserved evaluation. These tiny checks were
not used to choose methods or hyperparameters.

## Follow-up and outputs

Read `status.json`, `runner.log` and per-trial `logs/`; validate process start
identity rather than trusting a stale PID. Sources/settings/ordering are frozen;
the exclusive start guard forbids duplicate launch. No automatic retries,
resumes, new experiments or default promotions. Report-only repairs are allowed;
training repairs require a fresh snapshot and explicit provenance.

The supervisor produces `results.json` in the study directory and
`V7_REWARD_STUDY_2026_10_17.json/.md` in the repository after all25 final crafting
audits pass. Report paired five-seed final score contrasts, full learning curves,
deaths, station progression and resource allocation; use the protocol's four
primary comparisons and uncertainty treatment, not checkpoint pseudoreplication.

The existing completion follow-up is reactivated at its20-minute cadence, quiet
while healthy. It audits/annotates completed evidence, updates documentation,
commits verified reporting changes, and pauses after completion or a reported
terminal failure. It does not restart trials or spend on APIs/cluster access.

Provisional wall estimate: **4–7 hours** based on prior spatial-PPO studies,
not a measured ETA for this cohort. Keep the computer powered and the desktop
app running for local follow-ups; the supervisor uses `caffeinate` to inhibit
idle sleep. Main v4/default policies are unchanged.
