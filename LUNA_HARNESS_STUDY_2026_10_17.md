# Luna harness study — October17,2026

Status: **launched**, not yet results. See the frozen
[comparison protocol](LUNA_HARNESS_PROTOCOL_2026_10_17.md).

The user authorized **$3 additional spending**, separate from the already
completed historical Luna batch. Eight attempts compare full16, compact16,
compact4 and compact16_interrupt on the same two fresh public worlds32,000,001
and32,000,002. Every attempt has an independent $0.35 conservative guard:
**$2.80 allocated, $0.20 unallocated safety margin**, no allowance recycling.
No new experiments or paid calls after these attempts.

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

## Result locations and completion checks

`status.json` and `runner.log` track progress. Each `runs/<arm>-<seed>/` stores
its manifest, single-world claim/events/result/tape and summary. The supervisor
checks frozen hashes before dispatch, validates exact Python replay on each
completed attempt, then writes `results.json` and `results.md` after all8 finish.
Failures preserve evidence and stop new dispatch without retries/replacements;
an already active independently capped attempt may finish.

The completion follow-up audits independent budget totals, every request/response
pair (actual count determined by this study, not assumed from the old one),
high reasoning, source provenance, exact Python/SDL tapes, paired-world results,
crafting times and action-milestone censoring. It then updates this report and
README/PLAN and pauses only the Luna monitor. No extra live model diagnostics.

Interpret outcomes under **equal independent dollar guards**, not necessarily
equal actual spend or executable action counts. Compact versus full bundles
shorter history with redundant-field removal; shorter lists versus interrupt
probe feedback/execution tradeoffs. Only two public worlds and one model sample
per cell: report paired observations and failure modes, not reliable rankings
or statistical significance. All attempts, including deaths and budget stops,
remain in the denominator. No matched-prior or matched-world PPO comparison.
