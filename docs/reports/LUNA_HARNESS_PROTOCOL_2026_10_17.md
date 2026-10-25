# Luna harness comparison — predeclared October17,2026

User authorization: **up to $3 additional API spending** for broad Luna harness
experiments and methodology/progression comparisons. This is distinct from the
[completed $0.896 development batch](LLM_LUNA_2026_10_17.md).

## Conditions and comparisons

Eight attempts: four harness packages × the same two fresh public worlds
**32,000,001 and32,000,002**, one independent model attempt per cell/world.
No tuning, selection, replacement or extra calls after seeing outcomes.

| Package | Observation | Recent history | Maximum primitive list | Early return |
|---|---|---:|---:|---|
|full16|Original full symbolic packet|8 turns|16|Never|
|compact16|Remove redundant flat status; preserve named information|2 turns|16|Never|
|compact4|Same compact packet|2 turns|4|Never|
|compact16_interrupt|Same compact packet|2 turns|16|After an illegal action has consumed its tick|

The full/compact comparison deliberately bundles shorter history with duplicate
field removal: it is a **scaffold-package** contrast, not a causal estimate of
serialization alone. Compact4 versus compact16 changes observation cadence;
interrupt versus compact16 changes generic failure feedback. The interrupt
does not skip the first illegal action for free, change its result, try another
action automatically or use a strategic mask. It discards only the unexecuted
tail after the paid attempt; Luna must choose what happens next.

All use exact **`openai/gpt-6-luna`, high reasoning**, the same frozen v7 game,
public rules/recipes, partial symbolic observations, legal masks and unweighted
achievements/death. Compact packets remove only redundant raw status, retaining
scalars, inventory, achievements, selection and visible entities. Offline tests
reconstruct the status encoding. No hidden map, recipe controller, gameplay
changes, demonstrations, code execution, automatic planner or model tools.
Model-authored notes persist only within a world and reset between attempts.

## Budget and scheduling

- **$0.35 independent conservative guard per attempt; $2.80 total allowances.**
  The remaining $0.20 is unallocated safety margin, not an extra trial budget.
  No recycling a short/dead episode's unused allowance into another episode.
- The guard charges the greater of reported cost and tokens at checked price
  ceilings: $0.125/M input (including listed short-context cache-write rate)
  and $0.50/M output. Live catalog metadata is frozen before launch. The100KB
  context plus schema/framing stays below the272K-token surcharge tier. A
  pre-request UTF8-byte/framing and8,192-output-token reservation must fit.
- This is a local conservative accounting guard, **not an absolute provider
  billing guarantee**. Unexpected model/usage/cost or an ambiguous request stops
  further dispatch; no automatic retry. Unknown in-flight charges remain labeled.
- Each attempt permits up to3,000 primitive actions,1,000 model calls,20M tokens,
  two hours wall time and120 seconds per request. Death or any budget may stop
  earlier. High reasoning and8,192 maximum output tokens are common to all arms.
- Two concurrent I/O-bound evaluations; no extra training workers. The first
  world's four conditions queue first; order rotates for the second world.
- Supervisor loads the already-authorized Hermes OpenRouter credential into
  memory only. No keys/headers/private reasoning in configs, logs or commands.
  No Sol calls, old-test use, PPO validation access or cluster spending.
- A source/config/protocol snapshot is sealed before any paid request. Old Sol,
  Luna and PPO artifacts remain byte-identical. No supervisor restart/resume.

## Reporting contract

Primary descriptive comparison: **final achievements under the same independent
accounted-dollar guard and3,000-action ceiling**, paired by world. Always show
actual costs and action counts: different call sizes/history mean different
numbers of executable actions, not a pure equal-action learning comparison.
No dropped deaths, budget stops or cherry-picked best attempt. Two public worlds
are exploratory and cannot support a robust ranking/significance claim.

Report per-world score, survival/death, bench/furnace/anvil/smelting and unlock
times; native replay-derived achievement curves at128/512/1024/2048/3000 actions;
tokens, calls, actual/accounted cost, elapsed/call latency, malformed responses,
illegal attempts and interrupted/discarded tails. At action milestones, death
carries terminal score forward; still-alive budget truncations beyond observed
actions are **censored/null**, not zeros or falsely extrapolated full episodes.
Do not compare curves using only whichever arms happened to reach a milestone.

Frozen runner automatically validates each hash-chained request observation,
native action/reward/state, final record/claim and tape. A completion audit checks
all eight exact model IDs/high settings, both-source provenance, totals and
independent SDL tape results before reporting. No additional API calls during
analysis; fresh configuration and authority are needed for any follow-on.

Implementation: `tools/luna_harness_study.py`, versioned harnessv0.2. Offline
provider tests pass on v4/v7; an eight-job mocked supervisor test covers independent
guards, frozen hashes, concurrent dispatch, replay and paired reporting without
SSH/API calls. The compact packet has no more game information than the full
packet. Native simulation/gameplay and the active PPO snapshots are unchanged.

The OpenAI Docs skill guided verification of the preserved model/high-reasoning
contract, not game strategy. [Official model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna),
[OpenRouter catalog](https://openrouter.ai/api/v1/models).
