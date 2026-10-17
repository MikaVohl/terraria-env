# Feasibility assessment

Assessment date: October 17, 2026.

This is the original full-game design assessment. The current priority and
reconstructed-reference protocol are in
[REFERENCE_BASELINE.md](REFERENCE_BASELINE.md); its prompt, context, viewport,
score and disabled-PvE scenario supersede the initial proposed settings below.

## Verdict

Building a reproducible full-game benchmark is feasible. Reliably completing
Terraria from scratch with any particular current model is unproven. The
benchmark should measure failure and partial progress usefully rather than
depend on completion for its only signal.

Use the real installed game through tModLoader, with observation-only benchmark
instrumentation. Reimplementing Terraria would introduce a very large fidelity
problem and would measure a different environment. The parent project's bounded
simulator remains useful for fast RL studies, but it cannot stand in for the
complete game here.

The local machine already has Terraria and tModLoader. Its bundled .NET runtime
successfully compiled the observer with zero warnings/errors. Game-side hooks
are documented by [ModSystem](https://docs.tmodloader.net/docs/stable/class_mod_system.html),
and progression flags through Moon Lord by the
[NPC API](https://docs.tmodloader.net/docs/stable/class_n_p_c.html). That supports
the instrumentation approach; a compilation does not establish correct gameplay
telemetry, fair input or agent competence.

## What makes it hard

| Problem | Consequence | Proposed treatment |
| --- | --- | --- |
| Millisecond combat versus slow model decisions | Planning quality alone may not win a fight | Start with a real-time primitive track; later label learned-controller tracks separately |
| Many hours of progression | Sparse completion signal; expensive repeated trials | Report progress vectors and run isolated boss/task suites alongside campaign runs |
| Hidden map and long memory | State estimates drift and plans loop | Screenshots plus bounded model-authored notes; freeze the memory policy |
| World randomness and alternative routes | A single seed or best clip is misleading | Paired world fixtures, repeated attempts, both evil variants, all results retained |
| Instrumentation can leak or modify state | High scores can be invalid | Evaluator-only telemetry, restricted agent process, actual input receipts and integrity audits |
| Version drift | Seeds and saves may cease to match | Hash complete installation/mod/config manifests and immutable fixture files |
| Long-lived credentials and save files | Unrestricted coding agents can bypass the task | Run agents with only an observation/action bridge and separate evaluator storage |

Equal seeds alone do not establish bitwise deterministic replay in real Terraria.
Preserve videos, world/player fixtures, input timing and game telemetry. State
that replay determinism is unverified until measured.

## Define “complete” explicitly

The default goal is campaign completion through Moon Lord, in the full commercial
game environment. It is not a promise of 100% item collection, achievements,
fishing quests, bestiary, housing or every optional event. Add a separately
versioned completionist suite if that breadth is required. The initial observer
already includes optional boss flags, but its 29 milestones are a coarse starter
catalog, not an exhaustive description of Terraria.

An agent can be evaluated across the entire game before it can traverse the
entire campaign: curated midgame/endgame saves support isolated tasks. Such
scores must be labeled snapshot-suite results, never scratch-to-finish success.

## Model selection and cost

Use a small matrix of current vision-capable models from multiple providers and
one open-weight candidate where practical. Before running, verify exact API IDs,
image support, reasoning settings, prices and limits against provider catalogs.
`configs/models.example.json` intentionally leaves IDs and prices unset. There
are no fabricated availability claims or results.

Start with one model on short wood/workbench smokes, then compare several models
on the same scaffold. Native coding-agent harnesses belong in a separate
agent-system track because their prompts, tools and memory differ. A more
capable scaffold is itself an experimental variable.

Compute budget from a pilot's measured calls, image/token usage, duration and
provider prices. An illustrative sweep of 4 systems × 5 worlds × 3 attempts ×
8 hours requires up to **480 game-instance hours**. At an illustrative $25
per-attempt local cap, 60 attempts have a planned $1,500 aggregate inference
allowance, excluding machines/storage; neither number is a price estimate or a
provider billing guarantee. Draft config ceilings are not enforced by today's
offline prototype.

## Effort estimate and decision

Planning estimate for one experienced engineer: roughly 1–2 weeks to reach an
audited short live smoke, and 4–8 additional weeks for robust resets, accounting,
multiworld suites and a reviewable pilot. These are rough estimates, not delivery
commitments; OS input, version-specific hooks and long-run recovery are the
largest unknowns. Reliable autonomous Moon Lord completion has no justified
schedule estimate.

Proceed with a narrow integrity-first live pilot. The first acceptance criterion
is a real, input-attributed wood/workbench trajectory with replayable evidence.
Only then spend on broad model comparisons or a public leaderboard.
