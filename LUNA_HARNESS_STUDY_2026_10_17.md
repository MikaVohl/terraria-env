# Luna harness study — October17,2026

Status: **complete and independently replay-audited**, October17,2026. See the frozen
[comparison protocol](LUNA_HARNESS_PROTOCOL_2026_10_17.md).

The user authorized **$3 additional spending**, separate from the already
completed historical Luna batch. Eight attempts compare full16, compact16,
compact4 and compact16_interrupt on the same two fresh public worlds32,000,001
and32,000,002. Every attempt has an independent $0.35 conservative guard:
**$2.80 allocated, $0.20 unallocated safety margin**, no allowance recycling.
No new experiments or paid calls after these attempts.

## Findings

**Generic failure-triggered replanning is the strongest follow-up candidate,
not a proven winner.** It finishes14/32 on both paired worlds, produces the
only furnace/copper-smelt episode in this cohort, and cuts pooled illegal-action
attempts from46.2% for compact16 to11.8%. But it spends far more model calls per
game action and both episodes stop at their dollar guards before800 actions.
Zero deaths before that cutoff do not establish reliable3,000-action survival.

| Package | World1 /32 | World2 /32 | Mean /32 | Actions, world1/world2 | Endings | Furnace worlds |
|---|---:|---:|---:|---|---|---:|
|full16|9|12|10.5|784 /1,832|Death / death|0/2|
|compact16|10|7|8.5|1,248 /584|Death / death|0/2|
|compact4|11|14|12.5|756 /1,136|Death / cost guard|0/2|
|compact16_interrupt|14|14|14.0|784 /778|Cost guard / cost guard|1/2|

All8 make workbenches; none makes an anvil, metal sword, armor or upgraded pick.
The interrupt condition on world32,000,001 makes its furnace at action566 and
smelts copper at569. Five attempts die; three remain alive but cost-censored.
**No attempt completes3,000 actions.** These are not eight full-length episodes.

Relative to compact16, paired final-score differences are:

- full16: **−1,+5**; not a consistent benefit from the larger context package.
- compact4: **+1,+7**; more frequent feedback looks promising in these worlds.
- compact16_interrupt: **+4,+7**; strongest final-score pattern here, still
  only two paired worlds and one stochastic model attempt per cell.

Full/compact changes both raw-field duplication and retained history8→2 turns.
It is not a causal serialization-only ablation. Cross-condition world geometry
is paired, not identical sampled model outputs or identical training priors.
No statistical significance, robust ranking or PPO superiority is established.

### Action efficiency versus dollar-budget outcomes

At the predeclared **512-action milestone**, all8 attempts are observed and
alive, permitting an uncensored comparison:

| Package | World1 /32 | World2 /32 | Mean /32 |
|---|---:|---:|---:|
|full16|9|8|8.5|
|compact16|6|7|6.5|
|compact4|10|13|11.5|
|compact16_interrupt|10|10|10.0|

Thus compact4, not interrupt, leads at this common action count. At128 actions,
the corresponding means are4.0,5.0,6.0,3.0. The final-score ordering should not
be relabeled as a universal action-efficiency ranking. Beyond1,024 actions both
interrupt attempts are censored: do not drop them and rank only the remaining
arms. Replay-derived128/512/1024/2048/3000 milestones are in the numeric audit;
death carries its terminal score forward, while still-alive budget cutoffs are
null beyond observed actions.

### Calls, execution and cost

| Package | Calls | Actions/call | Illegal attempts / actions | Actual cost, both worlds |
|---|---:|---:|---|---:|
|full16|210|12.46|898/2,616 (34.3%)|$0.407130|
|compact16|154|11.90|847/1,832 (46.2%)|$0.121380|
|compact4|577|3.28|675/1,892 (35.7%)|$0.437213|
|compact16_interrupt|702|2.23|185/1,562 (11.8%)|$0.493408|

Illegal fractions pool action counts descriptively, not independent statistical
samples. Interrupt executes the first illegal action and pays its tick, then
returns control; it does not strategically choose a replacement. The185
interruptions discard893 unexecuted proposed actions. The mode also changes the
model's subsequent list lengths/choices, so the outcome is not just a mechanical
tail-filter effect. Most calls still finish without triggering an interruption.

Compact16 cuts average input from15,341 to5,501 tokens/call (about64%), but its
world scores/deaths do not show that less history is harmless. Its lower total
bill also reflects early deaths, not simply superior cost efficiency. In this
small cohort, shorter feedback or interruption helps more than compacting alone;
longer-term memory and low-level execution remain separate hypotheses.

**Total provider-reported spend: $1.459130795**, within the user's$3 authority.
Conservative accounted spend is$1.9203985 of the$2.80 allocated allowance.
Deaths leave allowances unused; they are **not recycled** into more trials.
There are1,643 calls,7,902 primitive actions,11,131,276 prompt tokens and1,057,978
completion tokens (12,189,254 total). Reported943,320 reasoning tokens are
included in completion, not added again. Three malformed structured replies
cost one noop each; all1,643 API finish reasons are `stop`. No ambiguous charges,
transport failures, retries or model/provider fallbacks.

## What to do with this evidence

Keep generic interruption and shorter lists as candidates for a future,
predeclared equal-action/per-world-budget comparison. A stronger test would
separate history retention from serialization and use more worlds/repeated
model samples. Measure survival at matching action horizons and costs beside
score; do not infer mastery from an alive cost stop. No such follow-on, paid
diagnostic, new model call or default promotion is launched here.

The earlier20/19 Luna episodes used other worlds and different limits; their
scores cannot establish a regression from these harness changes. Current PPO
policies also use different priors/interfaces and evaluation worlds. This study
does not rank pretrained LLMs against scratch RL. The separate PPO study and
its later user-authorized concurrency amendment continue unchanged.

## Launch provenance

- Frozen root: `experiments/luna-harness-20261017.nhitzl0s`.
- Supervisor PID9446; its own sleep inhibitor PID9447.
- Launch:2026-10-17T22:11:10.877079UTC (**4:11p.m. Edmonton**).
- Source commit: `98e746ae67fe8bdb9a7597199612cbd8eef69717`.
- Protocol SHA256:
  `e824e93a5886934be031950a7acd744e53b5a606707d50cb30b00da223d6f964`.
- Exact model `openai/gpt-6-luna`, high reasoning, no model/provider fallback.
- Same frozen v7 native environment used by the ongoing PPO study; no gameplay
  changes or PPO source/config updates. Main v4/default policies remain unchanged.
- Two concurrent API-bound threads, isolated sessions/histories/claims and
  independent budgets. Complete first-world conditions queue before second-world
  conditions; package order rotates. No extra PPO/neural workers.
- Frozen Python package, CLI, supervisor, all8 configs and live public model
  metadata are hashed in `study-protocol.json`. Key read once into memory over
  the already-authorized SSH source; never stored in files/argv/logs.
- Offline tests pass on v4/v7, including exact compact status reconstruction,
  one-tick cost before interruption, model/source/budget guards, request-state
  replay and an entire mocked eight-job concurrent/report pipeline. No paid
  preflight requests or consumed PPO holdouts.

## Result locations and completed audit

`status.json` and `runner.log` track progress. Each `runs/<arm>-<seed>/` stores
its manifest, single-world claim/events/result/tape and summary. The supervisor
checks frozen hashes before dispatch, validates exact Python replay on each
completed attempt, then writes `results.json` and `results.md` after all8 finish.
Failures preserve evidence and stop new dispatch without retries/replacements;
an already active independently capped attempt may finish.

The independent [compact audit](LUNA_HARNESS_STUDY_2026_10_17.audit.json) verifies
all8 unique cell/world claims, original protocol/source/config/catalog/native
hashes, every requested model/high setting and returned model ID, all usage/
reservations/charges, response-list execution prefixes and interrupted tails.
All1,643 responses report provider OpenAI. A high-reasoning request audit is not
inspection of private reasoning. Every request's observation and every native
transition/reward/state/record passes frozen Python replay; all8 existing tapes
independently match the unmodified SDL headless verifier. No live API or SSH
requests occur during this audit. Original PID9446 and its sleep inhibitor9447
are absent. No reserved/validation PPO worlds were consumed.

The original results JSON hash is
`51c2b9fc0ad0b2c799796cdae0549f76b625cceadaa9bd8ea0e84b429490fdcb`.
The audit retains this measured hash and per-tape/event anchors. The
reporting-only auditor is `tools/audit_luna_harness_study.py`.

README/PLAN are updated; the Luna-only follow-up is paused after completion,
preserving the independent PPO monitor. No additional experiment or API spending.

Interpret outcomes under **equal independent dollar guards**, not necessarily
equal actual spend or executable action counts. Compact versus full bundles
shorter history with redundant-field removal; shorter lists versus interrupt
probe feedback/execution tradeoffs. Only two public worlds and one model sample
per cell: report paired observations and failure modes, not reliable rankings
or statistical significance. All attempts, including deaths and budget stops,
remain in the denominator. No matched-prior or matched-world PPO comparison.
