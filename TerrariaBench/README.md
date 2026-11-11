# TerrariaBench

An independent benchmark subproject for agents playing the real Terraria game
on `mika@Omarchy`, using screenshots and real keyboard/mouse inputs.

**Current work: exploratory design experiments.** Latest: [reference profile via the gateway](experiments/reference-gw.md)
(Haiku/Sonnet/Opus 5.5, checkpoint visibility, 10–45-minute runs). Before that: [real-time planner/executor agents](experiments/planner-executor.md)
(fast executors, high-level planners, replan-interval sweep). Earlier: the [campaign plan](experiments/campaign-2026-10-17.md),
[findings](experiments/FINDINGS.md) and [interpretation rules](experiments/interpretation.md). The reconstructed
reference below is retained as a historical baseline, not the final benchmark.

The [audited development results](experiments/results/screening-01/README.md)
are committed incrementally. The [first campaign findings](experiments/FINDINGS.md)
summarize 50 recorded game attempts and their diagnostic limits. Current trials cover early gathering, prepared
crafting and one-slime control across three model families; they do not measure
complete-game success. Native coding-agent frameworks and progression beyond
Wall of Flesh through Moon Lord remain future scope.

The experiment worker uses a shared locked campaign ledger, normal PvE by
default, copied immutable fixtures, and explicit condition manifests. On the
configured Omarchy worker:

```sh
.venv/bin/python tools/diagnostic_campaign.py experiments/screening-01.json
.venv/bin/python tools/analyze_experiments.py runs/diagnostic-campaign-01
```

Only one graphical campaign may run at a time; the current job plans share one
dedicated worker and an already initialized budget ledger. Completed attempts
are skipped, never overwritten. The user-authorized session cap is $3 including
earlier tests; this is not continuing authorization for later sessions.

The default historical `run` command uses
`reference-reconstructed-v1`. Its confirmed settings, explicit inferences and
test results are in [REFERENCE_BASELINE.md](REFERENCE_BASELINE.md). The original
world, prompt, implementation and complete scorer are unavailable; this is an
approximate reproduction, not an equivalent leaderboard.

## Reconstructed baseline

- 1024×1024 screenshots, pixel coordinates and real-time game simulation.
- Open-ended progression through Wall of Flesh, without resource/crafting hints
  or automatic stopping after early objectives.
- API tools: `look`, `act`, `checkpoints`. Complete conversation retention until
  an explicit resource stop; medium reasoning.
- Fresh copied character/world fixtures and plain starter items.
- Hostile mobs/PvE disabled, matching published metadata. The precise policy is
  inferred and currently also prevents boss combat.
- Separate public-checkpoint scorer reproducing all seven published agency
  scores. Thirteen checkpoint identifiers are known; the full catalog is not.

The first uncoached Gemini 3.8 Flash calibration earned three wood checkpoints
in 12 calls, cost $0.049326375, and passed its artifact audit. This validates the
reconstructed loop; it does not establish comparative model performance.

## Run on Omarchy

```sh
cd /home/mika/Projects/TerrariaBench
.venv/bin/python -m terrariabench run --fixture runs/fixtures/reference-reconstructed-v1 --output runs/NEW-UNIQUE-RUN --model google/gemini-3.8-flash --mode calibration --calls 12 --seconds 180 --usd .25
.venv/bin/python -m terrariabench.reference_audit runs/NEW-UNIQUE-RUN
```

Use a new output path for each attempt. The remote worker requires its running
Steam/Hyprland session, installed Terraria/tModLoader, and `/dev/uinput` access.
Python dependencies are isolated in `.venv` using `requirements-worker.txt`.

The runner reads the user-authorized OpenRouter key in remote memory from the
process environment or `~/.hermes/.env`; it never executes that file, uses the
management credential, or copies a key to the Mac. Model identity, vision
support and prices are checked against the live catalog. No fallback or hidden
retry is allowed. Each request reserves a conservative cost allowance and
reconciles reported usage; uncertain charges stop the run.

Calibration is limited to 600 seconds. Evaluation mode requires `--seconds
28800`, matching the reference budget. Independent call, context, token, action
and dollar limits can still stop an attempt early; such a run is truncated.
The local dollar ceiling is $1 per invocation, not a provider billing guarantee
or authorization for repeated paid sweeps. No full eight-hour evaluation has
been performed.

Each run freezes prompts, tool schemas, model metadata, source and fixture
hashes, then archives requests/responses, screenshots, input receipts, private
telemetry, usage, `result.json`, and an `index.html` replay. The agent can read
sanitized checkpoints, not private heartbeat inventory/position data. Dedicated
client termination can leave an open journal; results disclose this.

Run videos (`tools/record_desktop.py`, started by `tools/parallel_queue.py`,
`tools/record_runs.py` and TerraBot sessions) are `<run>/desktop.mp4` plus
`recording.json` (source, fps, size, audio sink, `video_start_unix`,
`audio_start_unix`, ffmpeg version). Isolated-display runs (since 2026-11-11)
record only the game's own Xwayland display: the 1024×1024 window the model
sees, at 30 fps (NVENC, `x11grab`), with the game's audio. `launch(display=...)`
sends each game to its own PipeWire null sink `tb_game_NN` (`PULSE_SINK`,
SDL's PulseAudio backend; `tb_desktop` stays the desktop default), and the
recorder records that sink's monitor, so parallel games never hear each other;
during paused-clock freezes the track is silent. With five parallel games the
recorders added about 6 points of CPU (user 41→47 %), 4 points of GPU SM plus
36 % NVENC, left game speed unchanged (62–64 updates/s) and raised the
harness screenshot time from 88–97 ms to 104–114 ms (median). Shared-desktop
runs keep the older grim recording of the whole output (1100×1100, silent,
timestamps from the first frame).

## Local checks and historical tools

```sh
../.venv/bin/python -m unittest discover -s tests -v
../.venv/bin/python -m terrariabench doctor
```

All 29 tests pass, including regression against seven archived public results.
Public URLs/statuses/hashes are recorded in `reference/evidence.json`;
`tools/snapshot_reference.py` refreshes that archive.

The older coached smoke is preserved in [LIVE_SMOKE.md](LIVE_SMOKE.md) and
`terrariabench.live`. Its normalized coordinates, bounded notes/history, task
hints, and custom 29-point scorer are **not the reference baseline**. The `demo`
and `score` commands still target that historical scorer.

The parent `terraria-lite` simulator remains independent; its results cannot
share this benchmark's scores. Commercial saves, generated packages and raw run
artifacts stay outside Git; compact audited experiment records are versioned.
All results remain `official_eligible: false`.

[SPEC.md](SPEC.md) defines the current protocol and extension boundaries.
[ROADMAP.md](ROADMAP.md) records the remaining gates. [VALIDATION.md](VALIDATION.md)
and [OMARCHY_ASSESSMENT.md](OMARCHY_ASSESSMENT.md) retain earlier setup evidence.
