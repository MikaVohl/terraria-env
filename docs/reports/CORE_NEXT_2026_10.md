# Sound core, direct selection and experience reuse — 2026-10-12

Status: implementation verified; **both pilots complete and artifact-audited**:
**41,943,040 main transitions across 10 full runs**, two seeds per comparison.
Main checkout remains v4. All completed studies and reserved tests are untouched.
This follows the user's authorization to proceed with the next design/learning
steps; it is not a silent relabeling or promotion of the old benchmark.

Preview/pilot root: `experiments/core-next-20261012.DAW09u`.
Frozen source manifests/settings: `pilot-protocol.json`; exclusive start guard:
`pilot-started.json`; progress: `pilot-status.json` and per-trial `logs/`.

## Separate contracts

| Contract | Changes | Actions | Observations | Items / recipes / achievements |
| --- | --- | ---: | ---: | --- |
| v4 main | Historical default, unchanged | 73 | 2961 | 31 / 19 / 32 |
| v5 preview | Original-art native object footprints | 73 | 2961 | 31 / 19 / 32 |
| v6 preview | v5 + independent tool ownership + necessary ore supply | 73 | 2963 | 33 / 19 / 32 |
| v7 preview | v6 + direct selection of every owned placeable | 83 | 2963 | 33 / 19 / 32 |

Iron and Gold Pickaxes are real inventory items with the original installed
`Item_1` / `Item_3521` icons. Crafting gold first no longer prevents iron crafting
or its achievement; crafting iron never downgrades the strongest automatically
used mining tier. Duplicate tools are legal and consume the normal ingredients,
just like duplicate weapons; the mask does not protect the agent's resources.
The fixed recipe costs and item/achievement universe otherwise stay unchanged.
[Official pickaxe IDs](https://terraria.wiki.gg/wiki/Pickaxes),
[Gold Pickaxe recipe](https://terraria.wiki.gg/wiki/Gold_Pickaxe).

After treasure-room carving, deficient worlds receive ore in randomized existing
stone cells within the appropriate bands: at least 18 copper, 120 iron, 4 silver
and 40 gold ore. These cover one copper sword/shared metal-sword achievement,
anvil+iron pick+chainmail, silver smelting and gold pick respectively. No gifts,
known route, reachable-in-3000-actions claim or recipe strategy is supplied.
Wood/stone are checked separately: 1024 tested worlds have minima 99 wood and
2789 stone. Ore floors are explicit rules; that finite wood/stone census is not
a universal reachability proof or a promise against wasteful consumption.

V7 adds one action for each of the ten placeables; selecting any owned item
costs exactly one simulator tick. Empty stacks are illegal, owned stacks remain
selectable even if already selected, and cycle selection stays available.
SDL inventory clicks queue the same primitive action, never mutate selection
directly. Both frontends have shared direct-selection key bindings. Legal masks
contain no goal/recipe-order logic and preserve attempts into hidden terrain.
The interface may reduce sequence friction but also adds policy choices; its
learning benefit is a hypothesis, not established by implementation correctness.

## Validation and performance

Both previews pass deterministic 100-world mechanics, 24,000-edit exact light
oracle, native object/world-generation regressions, original textures including
all 33 item icons, and gold-before-iron/duplicate ownership fixtures. V7 also
tests all ten direct actions, ownership masks and tick costs. Python scalar/
batch parity, recurrent boundaries and checkpoint schema checks passed.

Supply scanning was reduced from four unconditional scans to one census plus
candidate scans only for deficient ores. 26,584 legal-action transitions across
100 worlds match the pre-optimization observation/reward/mask/terminal digest
exactly: `76c9d10cd8a768b44a0da1066523b03982373075997476a3a9f85c499e3eefd5`.
Original measurements remain in `simulator-v5-v7.json`; the fresh optimized
five-pair result is `simulator-v5-v7-optimized.json`: paired batch ratio **0.9297**,
medians **970,532→901,716 transitions/s**. This passes the 10% cost gate but is
about 7% slower—not a speed improvement over v5. Workloads/trajectories differ;
desktop timing is not a dedicated-machine ceiling or neural training rate.

A real-observation CPU microbenchmark chose four Torch threads without looking
at validation scores. Four and six threads were nearly tied; do not claim a
large gain. Fresh 32k PPO calibration including four-world validation took
about **2.3s CPU versus 6.2s MPS**. This small pilot supports CPU for these runs,
not a conclusion about larger models or MI350X. No cluster access was used.
Collection/optimization alone were CPU **0.287/0.977s**, MPS **1.072/0.851s**:
MPS optimization was slightly faster but collection slower; their sums differ
by about 1.52×, not the 2.68× wall ratio (which also includes small-batch validation).
Investigate larger neural batches and host/device round trips before assuming
GPU arithmetic is the limiter. No hardware-counter bandwidth claim is made.
The follow-on 256-environment /128-rollout calibration makes a 32768 batch.
At this size MPS benefits from evaluating a **separate saved checkpoint on CPU**:
new optional `--evaluation-device cpu` never moves live optimizer parameters.
After all main workers stopped, a matched tiny pair measured CPU **1.681s**
versus MPS+CPU-evaluation **1.362s** including four-world validation (~19% less
wall time). Collection+optimization were **1.124s versus 0.703s**. A two-iteration
65k smoke test confirms optimization continues after intermediate CPU evaluation.
These are one-pair calibrations, not a sustained throughput or learning-quality
claim. Bigger batching changes PPO sampling/update granularity; test learning
quality in a new frozen pilot before adopting it or extrapolating to a cluster.
Preflight calibration snapshots remain separate, excluded from main comparisons.

## Generic replay reference

New `terraria_lite.replay_agent` implements batched **n-step Double DQN** with
uniform replay, a target network, epsilon-greedy exploration over all legal
actions and an MLP512 trunk. It receives only the same observation and sparse
achievement/death reward. No demonstrations, controllers, shaping, strategic
masks or achievement-conditioned replay selection.

Replay stores categorical terrain/light losslessly and status as exact float32,
not quantized inventory values: 131,072 entries require about **550 MiB**.
Tests cover exact compression/ring wrap, n-step lane endings/tails, legal
Double-DQN target selection, zero future value at death/inherent deadline,
checkpoint reload and replay viewer actions. The 32k calibration completed
60 finite-loss updates. Evaluation is greedy for Q and categorical for PPO,
matching their declared deployment behavior. This compares algorithm packages,
not a replay-only causal ablation. Standard uncorrected off-policy n-step
targets are an explicit limitation. This is not a Dreamer/world-model port.

## Frozen learning pilot

Six fresh runs × **4,194,304** transitions = **25,165,824 main transitions**:
PPO on v6/v7 and Double DQN on v7, each with seeds 601 and 602. PPO retains
MLP512, gamma .999, lambda .95, entropy .01, 64×128 batches and a 4M-ending LR
schedule. Replay uses n-step20, uniform capacity131072, batch512 every256
transitions, LR1e-4, target sync8192, epsilon1→.05 over half the run. Three
jobs share the Mac with four threads each; timings are contended.

Validation worlds **13,000,001–13,000,032**, sampler54321; checkpoint comparisons
at 1/2/3/4M. Reserved **15,000,001–15,000,128 remain unused**; no selected-policy
test or promotion in this pilot. Final-policy crafting diagnostics match each
method's actual evaluation behavior. Two seeds are exploratory: no five-seed
non-inferiority claim, checkpoint pooling or outcome cherry-picking. Original
7M/9M/11M test splits are not reused. No automatic retries or source edits after
pilot sealing; failures preserve artifacts and stop the exact child processes.

Initialization seeds are shared, not identical training data: PPO's existing
trainer begins world IDs at `seed*10,000,000`, while this replay reference begins
at `seed`. Both draw the same randomized-world generator, but cross-method
world streams are not paired. V6/v7 PPO streams are paired at reset. This
nuisance difference is explicitly retained in the frozen pilot, not silently
patched mid-training; align it in a fresh follow-on replay snapshot before
claiming a more tightly controlled method comparison.

## Offline LLM harness prototype

`tools/llm_protocol.py` exposes a JSON-lines session, public recipes/rules, the
same partial observation information and legal action IDs. Each response gives
one ID or exact action name. No free multi-action macros, world-state inspection,
station teleporting, inventory manipulation or automatic recipe execution.
Malformed requests consume one noop tick; known illegal actions are actual
attempts. Terminal/deadline stops are enforced; consumed/reserved test ranges
are guarded. Sparse visible-entity encoding reconstructs the RL observation
exactly. Unit tests compare action-by-action against the ordinary environment.

Optional `--out` records an exclusive local request/response transcript with
version, seed and monotonic timestamps; provider usage/cost are explicitly null,
never estimated from these timestamps. Model/provider accounting remains absent.
This is a provider-neutral, **offline** protocol, not a scored model leaderboard.
No API keys, model calls or spending. Provider adapters, transcript/token/cost/
latency accounting and a separately frozen LLM evaluation protocol remain future
work; do not present this prototype as a completed LLM benchmark.

Play the preview: `experiments/core-next-20261012.DAW09u/v7/terraria-px --seed 9`.
Run the offline harness with the matching `PYTHONPATH=v7/python` and repository
venv. All older physical/task contracts remain available for comparison.

## Pilot outcome and follow-on decision

[Results](CORE_NEXT_RESULTS_2026_10.md): initial means v6 PPO **10.11/32**, v7
PPO **10.48**, v7 replay **5.47**. No furnaces. Both PPO seeds are surface-bound;
replay reaches stone in 13/64 worlds but has higher mortality. Direct selection
raises carried-bench selection frequency, not demonstrated crafting proficiency.
Thus we did not promote a default or blindly launch32M versions of these runs.

A separate cohort `experiments/core-controls-20261012.u3HE5B` completed tests of the
previously mining-reliable shared-target package on both contracts for seeds
601/602: **four fresh4M runs / 16,777,216 transitions**, same validation13M range,
no tests. Its source bytes equal the initial pilot's immutable previews; only
declared method arguments change (targets128, entropy.03, lambda.99). This
follow-on was selected after seeing the initial pilot and is exploratory, not
a retroactively preregistered confirmation. It addresses whether the interface
helps a package that can reach mining, before a larger scaling decision.

Targets reached stone in 63/64 v6 worlds and 64/64 v7 worlds, but benches/furnaces
in zero worlds on either version. Means **15.28 versus 15.27/32**: no consistent
score advantage from direct selection. All four have wood below 4 on >99.9% of
stone-sufficient pre-furnace actions and no nearby bench. This refines the next
agent bottleneck to upstream resource allocation/station production, not lack
of mining or simply a long inventory cycle. The observation counts are
descriptive, not proofs of a unique cause. No 32M-per-agent run was launched;
use a fresh schedule and a capable control rather than extending a zero-LR tail.
327,680 calibration transitions are separate from 41.9M main learning compute.
The frozen replay reference also exactly reproduces a checkpoint seed9 tape
and matches the Python/SDL final state; that validates execution, not proficiency.

Portable `CORE_V6.patch` / `CORE_V7.patch` apply cleanly against the current
dirty main checkout; neither is applied. V6/v7 original-action parity also
passes **26,108 transitions across100 worlds** with identical observation,
mask/reward/terminal digests when restricted to the shared73 actions for this
test only. Training uses the full native action set. Off-policy UI fixture:
`experiments/core-next-20261012.DAW09u/ui-v7.png` (not a policy proficiency demo).
