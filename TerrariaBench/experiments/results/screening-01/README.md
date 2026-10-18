# Terraria diagnostic records

Start with the [complete scorecard](REPORT.md), including the separately selected
repeat cohort, task-specific outcomes, declared limits and cost accounting.
The [findings report](../../FINDINGS.md) interprets the completed 50-attempt campaign.
These are unofficial development results on one world, not a model leaderboard
or a complete-game evaluation.

The campaign screens early gathering, prepared crafting and designated-target
combat across three model families. Most attempts allow 16 API calls, 300 wall
seconds and 120 nominal simulation seconds; the combined combat follow-up allows
32 calls/600 wall seconds. The final, interrupted budget probe allowed 64 calls;
its actual five calls cannot answer the longer-horizon question. Actual calls, commands, observations and game updates
vary. Check each manifest rather than assuming equal control opportunities.

[Manual trajectory reviews](../../trajectory-reviews.md) describe dynamic crafting
UI mistakes, an offered-but-unused macro, and an in-game menu pause. The
[interpretation rules](../../interpretation.md) retain limitations and the adaptive
selection log. The [research rationale](../../design-rationale.md) links primary
benchmark sources and distinguishes proposed design choices from tested behavior.

Every recorded game attempt has a manifest, result and audit, with SHA-256 hashes
in `record-hashes.json`. `summary.csv` and `summary.json` include all attempts;
`perception-rescored.json` contains the separate nine-call development probe.
Raw requests/responses, images, inputs, telemetry, source snapshots and copied
saves remain in ignored `runs/diagnostic-campaign-01` on Omarchy. Screenshots and
source snapshots are also synchronized locally for review. They are not included
in this compact Git export.

An artifact audit verifies internal consistency, not independent correctness of
the task or scorer. Interrupted provider calls retain uncertain charges and are
excluded from the repeated-outcome rates. A qualified legacy telemetry-tail audit
is disclosed separately; original results and raw logs are preserved.

`budget-snapshot.json` includes reported campaign charges and pending reservations.
The additional $0.086400375 of earlier session tests also counts toward the user’s
$3 session cap. Active-attempt reservations can appear in intermediate snapshots.
This session’s authorization does not establish an ongoing spending allowance.

Regenerate after synchronizing completed worker artifacts:

```sh
../.venv/bin/python tools/export_experiments.py \
  runs/diagnostic-campaign-01 experiments/results/screening-01
../.venv/bin/python tools/report_experiments.py experiments/results/screening-01
```
