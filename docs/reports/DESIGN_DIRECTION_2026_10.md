# Design direction: learnable Terraria, not exhaustive Terraria

Working decisions updated 2026-10-12. The original user-deadline
[partial evidence](FOOTPRINT_LEARNING_PARTIAL_2026_10.md) is preserved; the user
then authorized completing the remaining runs in a separate frozen cohort.
The [completed 30-run / 503.3M study](FOOTPRINT_LEARNING_2026_10.md) finds a cheap
simulator cost (~1.16% paired median loss), mixed learner effects and
**inconclusive five-seed non-inferiority in every package**. MLP mean rises
13.79→17.32/32 and furnaces 6.6%→38.8%, while targets/memory fall by .61/.71
and reach zero v5 furnaces. V5 remains a credible fidelity candidate, not a
universal improvement or promoted default. Future interventions below are
proposals, not changes to frozen games; new experiments need a new budget.

The user subsequently authorized these next steps. [V6/v7 work](CORE_NEXT_2026_10.md)
now implements independent pick ownership, necessary ore supply and neutral
direct selection as separate previews. The 25.2M exploratory PPO/replay pilot
is complete but did not solve progression; the separate 16.8M mining-package
control also completed. Targets mine reliably but build zero benches on either
preview (15.28→15.27/32); upstream resource allocation remains the candidate
bottleneck, not just menu cycling. Larger-batch MPS training with CPU checkpoint
evaluation has a promising tiny calibration; learning quality remains untested.
No additional 32M run or default promotion was made. These are not changes
to the completed v4/v5 study or main defaults.
That October12 pilot used an offline LLM prototype; the subsequent explicitly
authorized October17 provider studies are documented below.

## October 17 completed PPO evidence

The [25-run reward/discount study](V7_REWARD_STUDY_2026_10_17.md),
419,430,400 main transitions across five paired seeds, is complete and
[independently audited](V7_REWARD_STUDY_2026_10_17.audit.json). It compares
fresh16M spatial PPO on v4equal/.999 with a v7 reward×discount factorial.
Means are17.97 for v4equal/.999,16.68 for v7equal/.999,15.90 for v7equal/1.0,
16.33 for v7weighted/.999 and15.14 for v7weighted/1.0. Gamma1's−0.987 score
main effect excludes zero under the predeclared four-contrast correction;
weighting and interaction do not establish improvement. V7's matched equal
contrast is negative in all seeds but family-adjusted inconclusive, not
equivalence or a demonstrated isolated mechanics effect. All means continue
improving late; this is a finite-budget result, not an asymptotic ceiling.

The high-level implication is **do not treat a more faithful/cleaner game or
a less discounted objective as an automatic learning improvement**. Keep
gamma.999/equal as the PPO reference, main v4/default policies unchanged and
v7 as an unpromoted, usable preview. Do not undo cheap fidelity or declare
combat/scale infeasible based on a bundled version comparison. For future
learner work, freeze one contract and explicitly name its costs/benefits.

Weighting at.999 changes bench coverage3→278/640 but produces no final furnaces;
one weighted seed reaches a furnace in one validation world at8M, not16M.
the gamma1 groups have no benches. Missing joint preparation dominates:
98.68–99.86% of stone-sufficient pre-furnace actions in v7 lack both enough
wood and a nearby bench. More total wood is not sufficient in the recorded
policies; v7equal/1.0 acquires33.23wood/world but makes zero benches. Placement
space is virtually always available when a bench is owned. Direct selection
removes menu friction but does not solve strategic coordination by itself.

The next **proposal**, not a launched experiment, is generic experience reuse
or predictive/world-model learning, with fresh PPO and both transition and
compute accounting. Test reuse of rare preparation successes without expert
trajectories, recipe controllers or strategic spending masks. These findings
do not prove a particular replay learner will work, or that PPO cannot improve.
No new neural diagnostics/trials or reserved evaluations were run at completion.
All100 checkpoints and exact3,200 final diagnostic/validation outcomes passed
audit; reserved19M worlds remain unused. The explicit final concurrency-only
amendment is preserved and separately timing-accounted; study workers and both
supervisors are stopped and follow-up paused.

## Priority order

1. **A valid, fair capability task.** Fixed item/recipe/achievement universe per
   version, reproducible randomized worlds, consistent human/RL/LLM action costs,
   honest partial observations, and progression that is not structurally
   impossible because of accidental shortages or ownership bugs.
2. **Meaningful strategic diversity.** Mining, exploration/loot, survival/combat,
   mobility/building and workshop progression should interact. Impressive play
   means coordinated behavior across these systems, not a large unused catalog.
3. **Learning efficiency under a declared compute budget.** Track achievement
   coverage, crafting reach, deaths and time-to-achievement across seeds and
   both transition/wall budgets. The fastest rollout or the luckiest policy is
   not the best product metric.
4. **Terraria fidelity that earns its cost.** Favor recognizable real objects,
   recipes and item roles. Exact collision minutiae, timing, catalog completeness
   and menu friction can yield when they strongly harm the first three goals.

This ordering explicitly permits overriding past design decisions. It does not
permit silently changing a published task to improve its score.

## Keep, change, defer

| Decision | Direction | Reason / evidence |
| --- | --- | --- |
| Slimes/bats, bounded combat, chests, healing and mobility | Keep the existing core | They supply non-ore progression and resource tradeoffs; the simulator still approaches 1M batched transitions/s. Their existence is not evidence of infeasibility. |
| Original textures and matched human UI | Keep | Rendering is separate from headless rollouts. Art fidelity does not require expensive simulation. Assets stay locally installed, not redistributed. |
| 2×3 avatar, pass-through trees | Keep unless a controlled counterexample warrants a change | Mining is learnable on this geometry. Width alone was not proven to cause the earlier collapse. |
| Native-size furniture/crystals | Keep as a low-cost preview; explicit promotion decision still needed | Simulator gate passes; MLP workshop gains coexist with targets/memory regressions and inconclusive non-inferiority. Not inherently infeasible, but not proven learner-neutral. |
| Irreversible pick-upgrade ownership | Fix in a separate future version | Gold-first blocking iron crafting is an artificial achievement trap, not desirable difficulty. Own/craft tools independently; keep real costs. |
| Worlds with insufficient progression materials | Add necessary resource-supply guarantees in that future version | Keep randomized locations and a gathering challenge. Do not give ingredients directly to the policy or prescribe a route. Supply is necessary, not a 3000-step reachability proof. |
| Cycling the placement inventory | Test neutral direct selection separately | Current policy often carries an easily placeable bench without selecting it. A one-action selection for every owned item removes interface friction without implementing a recipe strategy. Apply the same interface/cost to humans and agents. |
| Expanding ore/weapon/mob catalogs | Add only distinct strategic roles | Cosmetic alternatives and near-identical tiers inflate learning burden without much new capability. Keep the taxonomy fixed within each benchmark version. |
| Liquids, wiring, extensive biomes/day-night/boss systems | Defer from the minimal core | Potentially feasible with bounded/vectorized rules, but not needed to investigate today's workshop bottleneck. No claim that RL can never learn them. |

The new diagnostics make arbitrary changes such as cheap furnaces, automatic
station placement, "save wood" strategic masks or a mining macro particularly
unattractive. They would hide the coordination failure we want an agent to learn.
Conversely, keeping an artificial inventory-menu sequence for its own sake is
not a first-principles requirement.

## Two levels of ambition

Maintain a **compact core contract** aimed at high coverage within the action
budget. Once its supply/ownership semantics are sound and several seeds reliably
progress, introduce a **richer challenge contract** with selected new systems.
Both have fixed universes, explicit versions and their own results; do not mix
their scores or randomly remove achievements inside a single official task.
Keep a core progression breakdown when reporting the expanded contract.

This follows the useful Classic/full distinction in Craftax. Its paper reports
strong PPO performance on the simpler Classic task but substantial remaining
open-ended learning challenges in the expanded environment. Complexity and
fast simulation can coexist; fast simulation alone does not establish mastery.
[Craftax paper](https://arxiv.org/abs/2402.16801),
[author benchmark site](https://craftaxenv.github.io/).

## Algorithm direction

Stay algorithm-agnostic. PPO is a reference, not a constraint on the project.
The newest recurrent/RND trials did not solve crafting, and a more expensive
memory package is not automatically better. The earlier successful policy shows
that useful workshop behavior exists; the problem is reproducing it reliably.

After the footprint comparison, prioritize generic reuse of successful agent
experience and predictive state learning. A replay/world-model baseline is a
reasonable next research track, not a guaranteed solution or an immediately
implemented port. DreamerV3 is relevant because its authors demonstrate broad
learning with a world model and report Minecraft diamond collection without
human data or curricula. That is evidence for the approach, not a forecast of
our scores. [DreamerV3 paper](https://arxiv.org/abs/2301.04104).

The completed [final-policy diagnostics](FOOTPRINT_CRAFTING_2026_10.md) refine
the bottleneck: v5 targets/memory craft benches in only 4/640 and 3/640 worlds,
acquire about 16 wood/world, and spend roughly 10 on platforms. They have zero
joint furnace opportunities; failures are not all simply remote-station memory.
V4 counterparts acquire more wood and craft more benches but rarely coordinate
all prerequisites. Generic mining, sparse resource allocation and interface
coordination can settle into different stable policies. Successful v5 MLP seeds
show workshop learning is possible; the late MLP seeds fail mining itself.
No one mechanism has been isolated as the cause. Bench placement-space telemetry
is >98% available when owned in every group; do not use larger footprints as a
blanket excuse or claim direct selection is already a demonstrated fix.

No expert behavior cloning, recipe-specific shaping, forced prerequisite order,
controller-generated trajectories or goal-aware masks. If exploration changes,
evaluate generic episodic/predictive mechanisms with a separate extrinsic-only
control; the tested RND configuration's failure is not a theorem about novelty.

## October 17 LLM harness addendum

The [benchmark research](LLM_BENCHMARK_RESEARCH_2026_10.md) motivates a shared
native score/action contract but separately labeled interfaces and inference
budgets. The [development harness](LLM_EVALUATION.md) exposes only local
symbolic RL information plus public rules/recipes; no code execution, strategy
controller, hidden map or model-based judge. Primitive and bounded open-loop
tracks are distinct. Report world-level reliability, costs and errors, not
best-of demonstrations. Private administration and human-relative action scores
remain future work, not implied by replay verification.

The [Sol smoke](LLM_SMOKE_2026_10_17.md) is plumbing evidence only. The user
then chose **Luna high**; the [three-world batch](LLM_LUNA_2026_10_17.md) and
subsequently authorized [$3 harness comparison](LUNA_HARNESS_STUDY_2026_10_17.md)
are complete. The latter spent$1.459 and verified all8 attempts/replays.
Shorter feedback intervals/illegal-tail interruption look useful, but two
worlds and budget-censored episodes do not establish a robust methodology
ranking or matched-budget advantage over PPO. Both follow-ups are now paused;
no automatic continued spend. These calls supersede the historical October12
no-spend status, not frozen PPO restrictions or main game/policy defaults.

## Performance and acceptance policy

Measure complete mask/step/observe/reset workloads with and without active
training, plus full learner inference/optimization. Preserve worst-case bounded
object/entity counts and allocation-free per-step state. Promote cheap rendering
fidelity more readily than new propagation systems or larger policy interfaces.

Use the footprint study's provisional 10% simulator-loss gate and −1 achievement/
+5 percentage-point death learning margins as **decision aids**, not universal
laws. Five-seed intervals can be inconclusive. A strategically valuable feature
can justify a measured cost or a harder task, but document that decision and
preserve the earlier benchmark. Never assert preserved learnability from SPS.

Current CPU experiments spend roughly three quarters or more of measured loop
time in optimization, not raw C physics. First test neural batching, kernels and
data movement under matched learning settings; do not start by removing mobs or
rewriting an already-fast simulator. Craftax's architectural lesson is massive
parallelism and device-local simulation/learning, not simply "use JAX".
[Author performance explanation](https://craftaxenv.github.io/).
A GPU/cluster path needs end-to-end and learning-quality pilots before large
spending; no cluster experiment is part of the current protocol.

## Sequence

1. The full completion audit is done: preserve the original partial/interrupted
   attempts and all 30 full results. Two reserved tests are consumed, replays
   exact, follow-up paused; no new experiments launched.
2. Make an explicit footprint promotion decision. Simulator cost is acceptable;
   learning effects are mixed and non-inferiority inconclusive. Main v4 stays.
3. Test neutral direct item selection independently; fix tool ownership and
   necessary world material supply with explicit versioning and regressions.
4. On a frozen sound contract, compare PPO with a replay/predictive learner under
   both equal-transition and practical compute budgets.
5. Build the LLM harness against the same knowledge, primitive actions and score
   contract; additionally report model token/cost/latency budgets. Do not wait for
   PPO saturation to prototype the harness, but stabilize/version the contract
   before presenting a leaderboard. No LLM API calls/spending were made here.
