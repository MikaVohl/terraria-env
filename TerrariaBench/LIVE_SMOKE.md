# Live reproduction smoke: October 17, 2026

**Historical coached plumbing test.** The active reconstructed-reference profile
and its later uncoached calibration are documented in
[REFERENCE_BASELINE.md](REFERENCE_BASELINE.md). Settings below remain the record
of these earlier attempts and are not the current comparison protocol.

**The remote game → screenshot → OpenRouter → real input → evaluator loop works.**
Gemini 3.8 Flash harvested wood and crafted a workbench in the actual game on
Omarchy. This validates early-game plumbing, not campaign completion, model
ranking or official benchmark eligibility.

## Results

| Attempt | Coordinates | Calls | Input commands | Smoke objectives | Invalid outputs | Reported cost |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| `gemini38-smoke-01` | Screenshot pixels | 9 | 35 | Wood ≥25; no workbench | 3 | $0.02602875 |
| `gemini38-normalized-02` | Explicit normalized 0–1000 | 5 | 15 | Wood ≥25 and workbench | 0 | $0.01104525 |

**Total reported inference cost: $0.03707400.** No uncertain charges remain in
either run's accounting. The first attempt stopped on its invalid-output limit;
the second stopped automatically when the evaluator observed both objectives.
Both had zero recorded deaths. The normalized attempt reached wood ≥25 at
19.71 seconds and workbench possession at **33.48 seconds** after observer start.
Its final screenshot visibly shows the workbench and the game's Benched toast.

There were only two exploratory attempts on one development world. These are
not independent model comparison samples. Both are retained, including the
coordinate failure. The normalized interface was selected after inspecting the
first run and is therefore a development change, not a predeclared comparison.

## What was installed and tested

Worker: `mika@Omarchy`, source at `/home/mika/Projects/TerrariaBench`, RTX 2060,
Hyprland 0.56.2, Python 3.14.7, tModLoader v2026.8.3.0 / Terraria v1.4.4.9.
The game's .NET 8.0.0 runtime was initialized by the official launcher.
Worker dependencies are isolated in the project's `.venv`.

Observer v0.2 compiled on Linux with zero errors/warnings. It records starting
facts, milestones, deaths and periodic evaluator-only heartbeat/inventory data.
All **16 regression tests pass**, including input bounds, malformed batches,
normalized mapping, inherited milestones, accounting and credential-file parsing.

An operator control test first harvested 47 wood and crafted a workbench through
the same input bridge. Both checkpoints were emitted, and normal Save & Exit
closed its journal. The model fixture had been frozen **before first world entry**,
so no operator-earned items or progression entered either paid attempt.

The fixture is a small Classic Corruption world with ordinary seed `32000001`
and a standard Classic character. Immutable local save files are copied per
attempt. Their hashes and the game/mod/config identities are recorded. The saves
and screenshots stay outside Git under ignored `runs/` directories.

## Interface corrections found by testing

1. Hyprland 0.56 uses Lua dispatchers; older command strings failed explicitly.
2. Compositor pointer warps alone worked in menus but failed to update SDL's
   gameplay pointer reliably. The validated bridge launches native Wayland and
   delivers a real net-zero Linux mouse-motion event after each cursor placement.
   Keyboard/buttons are real uinput events, released after each bounded command.
3. Gemini repeatedly described actual image positions in normalized 0–1000
   coordinates despite the original pixel instruction. Several y coordinates
   exceeded the screenshot's 720-pixel height and were rejected. An explicit
   normalized contract and deterministic axis scaling resolved this in the next
   fresh attempt. It adds no perception, targeting, recipes or gameplay strategy.

## Model and accounting

The exact model ID `google/gemini-3.8-flash`, vision support and prices were
verified against OpenRouter's live catalog. Each run archives its own catalog
snapshot, prompts, schema and requested/returned model identity. The runner used
low reasoning, temperature 0.2 and a 2,048 completion-token ceiling. No model
fallback or hidden retry was used.

The first run had a $1 local cap; the follow-up had an $0.80 cap after the first
spent about $0.026. Their combined configured remaining exposure stayed below
the stated $1 total allowance. Requests reserve conservative input/output cost
before execution and reconcile provider-reported usage/cost afterward. This is
local accounting, not a provider-enforced billing limit.

The user-authorized key was read only into remote process memory from Hermes's
`.env`. No management key was used. A remote scan of 122 generated/source text
files found no occurrence of the API key. The key was never copied to the Mac,
included in a prompt, printed, or saved in run artifacts.

The model received only the current 1280×720 game image, up to 2,000 characters
of its own notes and the previous four action batches. It had no filesystem,
shell, hidden map or checkpoint-log access. Time continued during inference.

## Evidence and audit

Artifacts are available locally and remotely:

- `runs/gemini38-normalized-02/index.html`: successful decision-by-decision replay.
- `runs/gemini38-smoke-01/index.html`: retained pixel-coordinate attempt.
- Each run: manifest, frozen Python sources, request/response records, image
  hashes, input receipts, provider usage, observer journal, final image and result.
- `runs/manual-calibrated/`: independent operator control trajectory and score.

`terrariabench.audit` passed on both paid attempts: it verified 14 response/frame
pairs, requested/returned model IDs, frozen source hashes, all 50 dispatched
commands against model outputs (including invalid-output noops), objective
journals and usage totals. Fixture manifests agree between the two attempts.
This is a file-consistency audit, not cryptographic attestation against the
evaluator or an independent audit of Terraria's mechanics.

Both model runs stopped their dedicated client after the smoke. No benchmark
game or paid model loop is left running. Their journals are explicitly open
because process termination did not execute normal world unload; the final
observed checkpoints remain valid development evidence. The separate operator
trajectory demonstrated clean journal closure through Save & Exit.

The earliest result files retain an old explanatory string saying some
components were not implemented. Those frozen strings are historical; actual
eligibility remains **false**, because integrity hardening and the official
evaluation protocol are incomplete. Current scoring uses updated wording.

## Remaining work

Validate boss/crafting event attribution and all coarse milestone proxies,
graceful live-run saving/closure, fixture automation, process isolation and long
sessions. Freeze a multiworld suite and model/harness matrix before publishing
performance claims. The short shared API scaffold also differs from the
reference's native coding-agent harnesses and agent-readable checkpoint logs.
Moon Lord, full campaign success, private tests and deterministic replay remain
untested. The real game environment supports that scope; this smoke establishes
only the first resource/crafting objectives.

Implementation references: [OpenRouter API](https://openrouter.ai/docs/api_reference/overview),
[model catalog](https://openrouter.ai/api/v1/models),
[Hyprland control](https://wiki.hypr.land/configuring/core/advanced-configuration/using-hyprctl/),
[dispatchers](https://wiki.hypr.land/configuring/core/dispatchers/),
[Linux uinput](https://python-evdev.readthedocs.io/en/latest/tutorial.html).
