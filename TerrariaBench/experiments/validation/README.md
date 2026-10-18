# Independent operator combat controls

These controls use real keyboard/mouse input and no model/API calls. All input
receipts are labeled `operator_calibration`, and `model_run` is false. The
versioned script is `tools/calibrate_combat.py`. Compact records and raw artifact
hashes are stored here; screenshots/input journals/telemetry remain in ignored
`runs/experiment-combat-control-02` and `-03` on Omarchy and locally.

| Control | Observer | Target killed | Recorded damage | Interpretation |
|---|---|---|---:|---|
| 02 | 0.4 | Yes | 24 | Input/hit/kill path works; lethal damage omitted. |
| 03 | 0.5 | Yes | 28 | Kill and full damage-counter path validated; totals can include overkill. |

Both targets started with 25 HP. The 0.4 guard excluded hit callbacks once the
kill flag was set, omitting the fatal blow. Version 0.5 tags the designated NPC
per spawn, counts its hit callbacks even after its kill flag, and clears the tag
for new spawns so reuse of an NPC slot does not add unrelated damage. This uses
the documented per-entity [tModLoader GlobalNPC hooks](https://docs.tmodloader.net/docs/stable/class_global_n_p_c.html).

The first 49 paid attempts use the immutable `diagnostic-v04` fixture and retain
their original snapshots. None killed the target, so fatal-hit omission does not
affect their observed target damage. New private instrumentation is compiled
into the separate `diagnostic-v05` fixture. `observer-v05-build.json` records the
frozen build inputs/package hash; compilation had zero errors and warnings.

Remote build and validation:

```sh
# From the installed tModLoader directory; source is frozen first.
bash LaunchUtils/ScriptCaller.sh \
  -build /home/mika/Projects/TerrariaBench/runs/observer-v05-build/ModSources/TerrariaBenchObserver \
  -tmlsavedirectory /home/mika/Projects/TerrariaBench/runs/observer-v05-build/tml

# From the worker project; no other graphical worker may be active.
.venv/bin/python tools/calibrate_combat.py \
  --fixture runs/fixtures/diagnostic-v05 --output runs/NEW-OPERATOR-CONTROL
```

## Combat render barrier (unpaid, 2026-10-18)

Campaign 01 combat attempts could start from a screenshot captured before the
armed slime existed (`interpretation.md`, N02). `experiments.run` now waits,
after arming, for the first heartbeat whose designated target has a slot, is
active and has positive life (`target_ready`), then waits 0.25 s (≥15 rendered
frames at 60 FPS) before the first observation. The result records
`scenario_ready`.

Unpaid check on `diagnostic-v05`, no API calls: a frame captured immediately
after arming (`render-barrier-01/unbarriered.png`) shows no slime. After the
barrier (ready 1.40 s after arming, at heartbeat 240, slime at 25 HP in NPC slot 1),
`render-barrier-01/barriered.png` shows the slime on the grass about 160 px
right of the player, matching the mod's spawn offset. The wait lets up to about
1.4 s of game time pass in both clock modes before the agent's first frame.
