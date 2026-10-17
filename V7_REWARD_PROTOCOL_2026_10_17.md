# V7 progression and reward/discount study — frozen design

Launch date: October 17, 2026. Main gameplay/default remains v4; v7 remains a
separate preview. This is a user-authorized larger study, not a promotion.

## Questions and budget

1. Does the mining-reliable spatial PPO package progress further on v7 with a
   full 16M schedule, and how does its curve compare with a fresh matched v4?
2. On v7, do discounting and fixed achievement difficulty weights change
   progression, separately or jointly?

Five cells × five paired training seeds **801–805** × **16,777,216** transitions:
**25 fresh runs, 419,430,400 main transitions**. No warm starts, extended
annealed checkpoints, retries, expert data, strategic masks or recipe controller.

| Cell | Game | Discount | Training achievements |
| --- | --- | ---: | --- |
| v4-equal-g999 | Frozen main v4 | .999 | +1 each |
| v7-equal-g999 | Frozen v7 preview | .999 | +1 each |
| v7-equal-g1 | Same v7 | 1.0 | +1 each |
| v7-difficulty-g999 | Same v7 | .999 | Fixed normalized difficulty weights |
| v7-difficulty-g1 | Same v7 | 1.0 | Same difficulty weights |

The frozen v7 C sources must match the previous core-next preview exactly.
Both games use the same newly instrumented Python learner. The default equal
scheme bypasses reward rewriting. The only additional numerical safeguard is a
finite-loss check; no PPO update formula or model architecture changes.

## Fixed training package

Shared spatial target scoring, hidden128, 64 environments × 128 rollout ticks,
four PPO epochs, four minibatches, Adam LR3e-4 with a fresh 16M-ending linear
schedule, GAE lambda .99, entropy .03, clip .2, gradient clip .5, KL stop .03.
CPU, four Torch threads per worker, up to three concurrent workers. Cell order
rotates across five seed blocks to reduce systematic temporal ordering.

Every simulator action still costs one tick; episodes end at death or 3,000
actions. Deadline future value is zero under both discounts. Existing finite
GAE/autoreset tests remain required. Training worlds start at seed×10,000,000
and advance normally; paired seeds do not imply identical trajectories or
identical generated terrain after version-specific object/ore rules.

## Reward intervention

The simulator and all evaluations retain **+1 per first achievement, −1 death,
no health-change reward**. The difficulty conditions replace only first-unlock
training rewards. Multiple unlocks, simultaneous death and true final
observations at autoreset are accounted for. No reward for partial ingredients,
station proximity, attempted recipes, repeated crafting or selected actions.

Subjective, predeclared tiers:

- **1:** wood/stone collection; block/torch/platform placement; Blue Slime;
  chest opening; healing; life crystal; double jump; exploration; rope climbing.
- **3:** workbench; copper/iron/silver/gold collection; Cave Bat; wooden sword;
  wood breastplate; deep descent; return to surface.
- **5:** furnace; anvil; all four smelts; metal sword.
- **8:** iron chainmail; iron pickaxe; gold pickaxe.

The 32 raw weights sum to 101. Multiply each by **32/101**, preserving a maximum
total achievement reward of32 while changing relative incentives. Death stays
−1. This controls nominal maximum scale, not expected reward density or all
optimizer effects. It is a deliberately human-chosen objective variant, not a
claim that these tiers are optimal, potential-based shaping or Craftax parity.

## Evaluation, analysis and safeguards

At **4,194,304 / 8,388,608 / 12,582,912 / 16,777,216** transitions evaluate on
fresh validation worlds **17,000,001–17,000,128**, categorical policy sampling
seed54321, without autoresetting ended evaluation worlds. Record score, death,
all32 achievement rates, depth and first-achievement timing. Reproduce each
final policy's validation score with the read-only crafting observer, retaining
joint ingredient/station prerequisites, resource sinks and selection behavior.

Primary score comparisons use paired final16M training seeds:

1. V7 equal/.999 minus v4 equal/.999.
2. Discount main effect, averaged over both reward schemes on v7.
3. Weight main effect, averaged over both discounts on v7.
4. Interaction: discount effect under weighting minus under equal rewards.

Report all per-seed scores, sample SD, descriptive paired-t95% intervals, and
Bonferroni98.75% intervals for the four primary score contrasts (familywise95%).
Five seeds are small; an inconclusive interval is not equivalence. Curves,
per-achievement/death/crafting rates and their contrasts are secondary and
descriptive. Checkpoints and validation worlds are not independent training
replicates. V4/v7 is a bundled environment comparison, not an isolated test of
direct inventory selection. Do not choose a winner from early curves.

**No reserved evaluation or automatic policy selection.** Worlds
**19,000,001–19,000,128** are reserved but stay unused throughout this study.
All previously consumed test worlds remain untouched. No retries/resumes or
mid-study source, reward, schedule, sampling or gameplay changes. On a true
failure stop only this supervisor's children and preserve artifacts; any
training repair requires a fresh snapshot and explicit provenance.

Before sealing, each of five cells receives exactly one 16,384-transition
two-update smoke run (total **81,920 calibration transitions**, excluded from
main counts), evaluated only on diagnostic worlds21,000,001–21,000,004. These
checks establish valid updates/checkpoints/evaluation, not method selection.
Source/probe/supervisor hashes are frozen after preflight. The exclusive start
guard prevents duplicate launch. Reports are produced from saved artifacts;
no held-out test is needed to finish the study.

Implementation: `tools/v7_reward_study.py`; reward definitions:
`python/terraria_lite/achievement_rewards.py`. Prior studies, interrupted runs,
all frozen previews and the unrelated `PPO_EXPERIMENTS.md` edit are preserved.
