# Fresh paired v4/v5 footprint learning study

Status: **complete and independently artifact-audited**, 2026-10-12.

Bottom line: native-size objects are cheap to simulate and learnable, but their
learning effect is package-dependent. V5 raises plain MLP's mean and crafting
reach while spatial/recurrent packages lose some progression. The predeclared
five-seed learning non-inferiority gate is **inconclusive for every package**;
this is neither demonstrated safety nor proof of an unacceptable regression.
Keep v4/default policies unchanged pending an explicit promotion decision.

503,316,480 retained main transitions across 30 fresh-initialized runs; five paired seeds per policy package. No defaults or game versions automatically promoted.

Completion provenance: 15 verified complete original runs were retained without retraining; three interrupted runs restarted from scratch and twelve previously unstarted runs were trained. Original partial attempts remain preserved and excluded. Frozen gameplay/learner bytes, budgets, schedules and selection criteria did not change. Additional main training was 251,658,240 transitions; prior discarded partial compute is separately recorded in the protocol.

| Package | v4 final /32 | v5 final /32 | Paired v5−v4 | 95% interval | Furnace v4/v5 |
| --- | ---: | ---: | ---: | --- | --- |
| mlp | 13.787 | 17.316 | +3.528 | [−2.694, +9.750] | 6.6%/38.8% |
| targets | 17.680 | 17.072 | −0.608 | [−1.281, +0.065] | 1.1%/0.0% |
| memory | 17.759 | 17.045 | −0.714 | [−1.612, +0.184] | 1.1%/0.0% |

These are final 16M validation means, not best-checkpoint scores. The 128 worlds
per policy do not create 128 independent training seeds. Five-seed paired
Student-t intervals are exploratory; intervals on rate differences are not
clipped to [0,1]. Packages also differ in entropy/trace settings, so contrasts
between packages are not architecture-only experiments.

| Package | Death v4/v5 | Paired death change (percentage points), 95% interval | Anvil v4/v5 | Learning gate |
| --- | ---: | --- | ---: | --- |
| mlp | 1.4% / 2.0% | +0.63 [−1.98, +3.23] | 0/640 / 21/640 | Inconclusive: score lower bound below −1 |
| targets | 11.7% / 17.0% | +5.31 [−2.70, +13.32] | 1/640 / 0/640 | Inconclusive: score and death bounds cross margins |
| memory | 17.8% / 16.3% | −1.56 [−6.83, +3.71] | 1/640 / 0/640 | Inconclusive: score lower bound below −1 |

The MLP gain is concentrated in seeds 501/503 (+6.59/+10.90), not a uniformly
shifted learning curve. Both versions' last two MLP seeds finish near 11/32
without furnaces. Furnace counts are 42→248/640 for MLP, 7→0 for targets and
7→0 for memory; paired furnace-rate intervals are respectively
[−23.8,+88.2], [−2.40,+0.21] and [−3.22,+1.03] percentage points. Anvil-change
intervals are [−0.86,+7.42] points for MLP and [−0.59,+0.28] for each other
package. Raw paired values are in the audit; no universal improvement is claimed.

## Frozen paired selection and one-shot test

Selected package memory, paired seed 501; both final policies were frozen before either test.

v4: 18.461/32, death 10.9%, furnace 1/128.

v5: 17.016/32, death 14.8%, furnace 0/128.

Test worlds 11,000,001–11,000,128 are now consumed once per version. Do not rerun/tune against them.

The paired test score change is −1.445/32, deaths +3.906 percentage points,
furnace 1→0 and anvil 0→0/128. These are results for **one validation-selected
paired training seed**, not a five-seed test estimate. The rule chose memory
because its cross-version validation mean was 17.402 versus targets 17.376 and
MLP 15.552. It therefore selects consistency across seeds, not the most
impressive single MLP policy. Do not retroactively test a new winner on this
consumed split. The earlier 20.79/32 policy used different reserved worlds and
remains preserved, not directly head-to-head ranked by these numbers.

The selected v4 seed-9 replay ends at 3000 actions, health 120, 19 achievements;
v5 dies at action 2675 with 15 achievements. Both tapes were exactly reproduced
from their frozen checkpoints and matched the Python/SDL final states. Exact
replay is a correctness/provenance check, not evidence of mastery.

## What the crafting diagnostics say

All 30 final policies were replayed on the declared validation worlds with the
read-only observer. Their scores exactly match final validation scores. A
[per-policy breakdown](FOOTPRINT_CRAFTING_2026_10.md) includes joint prerequisite
failures, station selection and resource sinks; full 16-combination histograms,
events and actual consumed wood remain in each `crafting.json`.

Before the first furnace, conditional on carrying at least 20 stone:

| Package/version | Missing wood | Missing nearby bench | Missing both | Worlds with any furnace opportunity /640 |
| --- | ---: | ---: | ---: | ---: |
| MLP v4 | 87.4% | 94.0% | 81.6% | 42 |
| MLP v5 | 61.0% | 98.0% | 59.1% | 264 |
| Targets v4 | 95.9% | 99.2% | 95.1% | 8 |
| Targets v5 | 99.3% | 99.9% | 99.3% | 0 |
| Memory v4 | 96.8% | 98.8% | 95.6% | 7 |
| Memory v5 | 99.4% | 99.9% | 99.3% | 0 |

Fractions overlap and weight actions, not seeds or episodes equally. Surface-only
MLP seeds have no stone-sufficient actions and are reported as n/a individually.
The relatively rare all-ready moments matter more than the overwhelmingly many
blocked actions: v5 MLP has more opportunities despite its higher station-missing
fraction. It chooses the furnace on 710/824 whole-episode legal actions, with
mean conditional probability 85.9%; v4 MLP chooses all 42/42 (99.9% probability).
Targets/memory v4 have only 20/22 legal actions total and choose 8/7; v5 has none.
Do not conflate rare prerequisite coordination with inability to learn a legal
craft action, or repeated furnace crafting with distinct achievement coverage.

V5 targets/memory craft a workbench in only **4/640 and 3/640 worlds** versus
406/640 and 260/640 on v4. They acquire roughly 16 wood/world (including recovery),
consume about 10 on platforms and 2.5–2.7 on torches. This is consistent with
early resource-allocation/bench-production failure, not simply forgetting an
already-built remote workshop. V4 failures more often also leave existing
benches far away. Selection of a carried bench is low in spatial/recurrent
packages (about 2–5% of owned-bench actions); physical placement space is
available on >98% in every package/version aggregate. Thus a blanket claim that
larger benches cannot be placed is not supported, although rare useful moments
and the specific worldgen/interaction changes are not isolated here.

Our interpretation is a learner/environment interaction: generic mining is
reliable, but the sparse objective permits stable workshop-avoiding policies.
Some MLP seeds learn coordinated wood retention/reacquisition, station use and
smelting in v5, while others never learn mining. Memory capacity by itself did
not remove the prerequisite bottleneck. This study does not prove that replay,
different credit assignment or a neutral inventory interface will solve it;
those remain separately versioned and budgeted next experiments.

## Performance and design implications

The saved five-pair, no-concurrent-RL batch measurement gives v5/v4 median ratio
**0.9884** (about **1.16% loss**, within the 10% gate), with medians 961,420 versus
954,742 transitions/s. Extra object state adds 12,288 bytes/world (~0.75 MiB for
64 worlds). There is no evidence of a crazy simulator cost. Rendering original
sprites is separate from headless training; keep that fidelity.

Mean full-run walls across five seeds are approximately 20.5/20.2 minutes for
v4/v5 MLP, 33.1/33.8 for targets and 47.0/45.9 for memory. These span two dates
and shared-desktop contention, not dedicated hardware or equal FLOPs. Neural
optimization accounts for about 73%, 75–76% and 79% of collection+optimization
time respectively; simulator simplification is not the obvious throughput win.

Recommend preserving native footprints as a low-cost, plausible fidelity
candidate, **not automatically promoting it as learner-neutral**. Keep bounded
combat, loot, lighting and mobility; do not remove them because PPO settles into
an incomplete strategy. Next decisions should focus on neutral direct item
selection, independent tool ownership and necessary randomized-world material
supply, tested separately from the footprint package. Generic experience reuse
and predictive learning deserve an agent track on a frozen, sound core contract.
No new experiments or gameplay fixes were launched at completion.

## Completion audit and history

[Audit JSON](FOOTPRINT_LEARNING_2026_10.audit.json) and
`tools/audit_footprint_completion.py` verify 30 summaries and 120 checkpoints,
73/74 frozen source/library hashes against both original and new snapshots,
15 retained main artifact manifests plus six reused calibration manifests,
all run settings, original/new supervisor hashes, unchanged paired selection,
two exclusive test claims with 128 unique declared world records each, all 30
diagnostic provenance records, and both exact checkpoint/Python/SDL replays.
The audit only reads saved artifacts; it never evaluates a policy.

The completion supervisor ran 15:52:40–20:09:10 UTC on October 12 (09:52–14:09
Edmonton), about **4h16m including final tests/diagnostics/replays**. The earlier
stopped cohort and [partial report](FOOTPRINT_LEARNING_PARTIAL_2026_10.md) remain
unchanged. Its 12,582,912 checkpoint-backed interrupted transitions are excluded;
503,316,480 is retained full-trial compute, not all physical work. Six retained
calibrations add 196,608 transitions. Both earlier completed studies, failed
calibration ZtrJ6E and object-scale preview remain intact. Main v4 and existing
policy defaults are not changed.

The comparison is the footprint/worldgen/interaction package, not sprite scaling alone. Different game trajectories, five seeds, bundled policy settings and shared-desktop timings limit causal and efficiency claims.

No training controller, demonstrations, strategic masks, resource-floor or recipe changes. Diagnostic hidden-state reads never enter the policy. Full curves, gate telemetry, protocols, hashes and exact replays are preserved.

Artifacts: `/Users/mikavohl/Projects/terraria-lite/experiments/footprints-v45-complete-20261012.JabnGY`. Numeric report: `FOOTPRINT_LEARNING_2026_10.json`.
