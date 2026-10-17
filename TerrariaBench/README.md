# TerrariaBench

An independent benchmark subproject for agents playing the real Terraria game
on `mika@Omarchy`, using screenshots and real keyboard/mouse inputs.

**Current work: exploratory design experiments.** We are comparing observation
loops, timing, instructions, memory, control granularity and prepared tasks
before selecting benchmark variants. See the [campaign plan](experiments/campaign-2026-10-17.md)
and [interpretation rules](experiments/interpretation.md). The reconstructed
reference below is retained as a historical baseline, not the final benchmark.

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

## Local checks and historical tools

```sh
../.venv/bin/python -m unittest discover -s tests -v
../.venv/bin/python -m terrariabench doctor
```

All 23 tests pass, including regression against seven archived public results.
Public URLs/statuses/hashes are recorded in `reference/evidence.json`;
`tools/snapshot_reference.py` refreshes that archive.

The older coached smoke is preserved in [LIVE_SMOKE.md](LIVE_SMOKE.md) and
`terrariabench.live`. Its normalized coordinates, bounded notes/history, task
hints, and custom 29-point scorer are **not the reference baseline**. The `demo`
and `score` commands still target that historical scorer.

The parent `terraria-lite` simulator remains independent; its results cannot
share this benchmark's scores. Commercial saves, generated packages and run
artifacts stay outside Git. All results remain `official_eligible: false`.

[SPEC.md](SPEC.md) defines the current protocol and extension boundaries.
[ROADMAP.md](ROADMAP.md) records the remaining gates. [VALIDATION.md](VALIDATION.md)
and [OMARCHY_ASSESSMENT.md](OMARCHY_ASSESSMENT.md) retain earlier setup evidence.
