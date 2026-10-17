# Evaluation specification

Current profile: `reference-reconstructed-v1`. The machine-readable contract is
`configs/reference-reconstructed.json`; [REFERENCE_BASELINE.md](REFERENCE_BASELINE.md)
distinguishes evidence from implementation choices. Every run is unofficial.
The earlier `configs/protocol.json` / `progress-v0.1` 29-fact catalog is retained
for historical demos and future endgame work, not baseline scoring.

## Current game and agent contract

Use the pinned Terraria/tModLoader installation with only the benchmark mod.
Copy an immutable fresh Classic player/world fixture per attempt; never modify
the fixture or reset the live world for the agent. Record game/mod/source,
configuration and fixture hashes. Plain starter prefixes are standardized by
trusted scenario setup before timer start. No items or progress are granted.

Launch a dedicated native Wayland client on Omarchy. Capture only its window at
1024×1024, with UI scale 0.9, zoom 1.0 and English language. Screenshot pixels
map to actual OS pointer locations. Each input releases held keys/buttons;
focus, geometry and dispatch receipts are recorded. Time advances during model
inference and input holds; there is no simulation stepping or lockstep mode.

The reconstructed API harness exposes exactly `look`, `act`, `checkpoints`.
`act` accepts at most 16 explicit keyboard/mouse commands with holds of 20–2,000
ms. Coordinates are pixels 0–1023 on both axes. There are no conditional skills,
targeting helpers or game-state action APIs. The agent has no shell/filesystem,
save access, hidden map, private inventory or arbitrary memory access.
`checkpoints` returns only sanitized public events; private liveness and
inventory telemetry remain evaluator-side. This is an API boundary, not a
hardened separate-OS-principal security boundary.

The task prompt requests open-ended progress toward Wall of Flesh without
gameplay hints or early wood/workbench termination. Complete conversation,
screenshots and provider reasoning/signature metadata are retained until an
explicit resource stop. No cross-attempt memory, external web tools or hidden
compaction is supplied. These context details are inferred, not upstream facts.

## Disabled-PvE scenario

Both published PvE booleans are false. Our inferred policy deactivates hostile
NPCs/projectiles without executing kill hooks, dropping loot or setting defeat
flags. It preserves townsfolk and critters. It also suppresses bosses, so the
current policy cannot validate boss completion. The end goal expresses the
reference task; it is not a completion claim under this early-game profile.
Any boss-capable interpretation or combat-enabled extension needs a new frozen
profile. Scenario changes and plain-prefix setup are not described as a
read-only observer; the historical/default observer mode remains read-only.

## Scoring

Count distinct action-backed public progress checkpoints from the thirteen
identifiers in `terrariabench/reference_scoring.py`. Exclude starting baseline,
duplicates and diagnostics such as selecting an axe or opening inventory.
Reject direct tile control. Unknown checkpoints earn no credit and are reported.
Preserve per-checkpoint timing and progress vectors alongside the aggregate.

Our action attribution requires a preceding logged agent input; this is not
causal proof. Inventory predicates do not establish crafting, world flags do
not establish individual boss causation, and upstream predicates are unknown.
Never conflate this subset count with the legacy 29-fact score or a complete
upstream score. The scorer is regression-checked against seven public results.

## Models, limits and evidence

Verify the current model ID, image/tool support and prices before execution.
Freeze prompts, tools, requested/returned identity, reasoning, sampling,
history policy and limits. Use medium reasoning, provider-default sampling
and a 4,096 completion-token ceiling. Disable model fallback and automatic
retry. Preserve uncertain failures and their reserved cost.

Calibration lasts at most 600 seconds. Evaluation mode requests 28,800 seconds;
early call/context/cost/action/token stops remain truncated attempts, not full
reference evaluations. Current local guards allow at most 4,096 calls,
65,536 input commands, two million reported aggregate tokens, a 65,536-token
per-request accounting ceiling and $1 per invocation. The input ceiling is
checked after provider usage: there is no exact preflight multimodal tokenizer.
Conservative reservations are local guards, not provider billing guarantees.
Do not silently restart or stitch runs together after a budget stop.

Archive starting identities, frozen sources/prompts, request/response/usage
records, screenshot hashes, timestamped inputs, checkpoints, private heartbeat
telemetry, final image, stop reason and a local HTML report. No secrets enter
prompts or artifacts. A terminated game can leave `journal_closed: false`;
retain observed facts with that limitation. No generated artifacts are published
without a separate publication instruction.

## Comparison and future extensions

A short successful calibration establishes plumbing, not model ranking.
Use the same frozen fixture/prompt/tools/settings across models, retain all
attempts, and report resource limits, progress and failures. Upstream world,
prompt, clock and complete scoring remain unknown, so public comparisons must
be qualified as approximate. Avoid speed claims based on unmatched clocks.

After baseline validation: test longer context/session behavior, stronger
event attribution, both world evils and multiple seeds; then evaluate combat,
Moon Lord, richer controllers, native coding-agent harnesses and correctly
stepped simulation as separate profiles. Full game coverage is still the
project goal; those extensions do not change the reconstructed baseline.
