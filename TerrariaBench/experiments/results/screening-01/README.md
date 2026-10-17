# Exploratory screening records

These compact records are intermediate snapshots, updated as attempts finish.
`summary.csv` includes every completed game attempt; `perception-rescored.json`
contains the separate nine-call development probe. Each run retains its manifest,
result and artifact audit, with their SHA-256 digests in `record-hashes.json`.
Raw request/response/input/telemetry/image logs and copied saves remain in ignored
`runs/diagnostic-campaign-01` on Omarchy; source snapshots there support the audits.
An artifact audit establishes internal consistency, not independent correctness
of the task definition or scorer. These are unofficial development results.

At the first nine-run snapshot, Haiku's JSON and paused fresh-world attempts
obtained workbenches (64 and 44 maximum wood respectively). Its explicit-goal
attempt obtained no wood, whereas its initial tool-loop attempt collected 43
wood before a transport interruption. Gemini's tool and JSON attempts and
DeepSeek's tool attempt obtained no wood. This variability warrants repeats and
trajectory inspection rather than a model or scaffold ranking.

Prepared crafting with Haiku JSON obtained a workbench from inherited resources;
the prepared paused combat attempt dealt no measured target damage. The latter
is distinct from combat success, and the operator calibration has established
only hit reporting so far. See `../../interpretation.md` for limitations and the
adaptive selection log. Hostiles remain enabled except the named ablation.

Regenerate after synchronizing completed worker artifacts:

```sh
../.venv/bin/python tools/export_experiments.py \
  runs/diagnostic-campaign-01 experiments/results/screening-01
```
