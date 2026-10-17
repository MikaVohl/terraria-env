# Interpretation rules for the first diagnostic sweep

This is exploratory screening on one starting world, not a model leaderboard.
Fresh-world scenarios preserve normal gameplay except the named PvE ablation.
Prepared crafting supplies 50 wood, 50 stone and 5 gel before baseline/timer.
Prepared combat removes the Guide and arms one blue slime after window setup.
Neither prepared task constitutes fresh-world campaign progress.

## Contrasts

- tools vs paused: same interface/prompt goal; process is stopped outside action
  and observation windows in paused mode. This is not an exact fixed-tick API.
- tools vs json: tool-driven look/act scheduling vs automatic screenshot after
  every JSON action response. Observation frequency and output grammar both
  change. Equal API-call limits do not imply equal control opportunities.
- json vs notes: same automatic loop, compressed model-authored memory plus the
  last four action results instead of complete prior conversation/images.
- tools vs specific: same interface, explicit wood/workbench objective.
- specific vs guided: same explicit objective plus short controls/recipe guide.
- tools vs inventory: privileged latest-heartbeat inventory/name/HP tool.
- tools vs checkpoints: checkpoint log access AND green checkpoint chat enabled;
  this measures the combined feedback package, not only a filesystem capability.
- tools vs long-hold: max hold raised from 2 to 8 seconds.
- long-hold vs motor: same hold ceiling, plus a declared select-slot/hold macro.
  This is open-loop automation, not a learned controller or perception helper.
- tools vs peaceful: hostile NPC/projectile suppression; also removes hostile
  loot sources, so conclusions apply only to early-game gathering/control.
- tools vs normalized: explicitly request coordinates on a 0..1000 square and
  linearly map them to 0..1023 pixels. No targeting or perception helper is used.

## Limits and confounds

- Most screening cells initially have one attempt. Sample sizes are too small
  for model ranking or confident causal claims. Selected contrasts need repeats.
- One world/save; natural spawn RNG is not pinned. Identical save hashes do not
  create identical hostile encounters or bitwise deterministic trajectories.
- Models use medium reasoning where supported, low for DeepSeek. Effort labels
  and equal token ceilings do not imply equal inference compute.
- Screening has 16 API calls, 300 wall seconds and a nominal 120 seconds of
  observer updates (60 updates/second). Whole-process stopping is verified, but
  update counts are observer measurements rather than an attested step API;
  observation, focus, input release and final cleanup advance simulation too.
- Stock transport has no retry. Truncated calls retain conservative uncertain
  reservations in the campaign cap. Provider failures are separate from agent
  failures. A fresh repeated attempt is a new recorded sample, not a hidden retry.
- The three-image perception probe has manually annotated development boxes.
  It is illustrative, not a validated perception benchmark. Raw JSON compliance
  and offline semantic scoring after optional fence removal are both retained.
- Some perception calls overlapped the initial Gemini pilot. Do not use that
  pilot's inference latency as an isolated provider-throughput measurement.
- Item checkpoint detectors observe possession, not recipe creation. Holding an
  item on the mouse or placing it before a heartbeat can affect inventory maxima.
  Screenshots and per-update checkpoint logs supplement the coarse maxima.
- The initial operator combat calibration recorded a player hit (6 damage) but
  did not finish a kill. It validates input/hit reporting, not the full kill
  detector. Interpret zero player damage separately from a missing kill flag.
- Inspection of N02 found that the first screenshot can precede the armed
  slime's first rendered frame: signaling the mod is asynchronous. Later frames
  contain the target, but the initial combat observation is not standardized.
  Paused mode also adds an 80 ms observation window. These development combat
  attempts therefore cannot establish a clean clock/coordinate effect. A future
  prepared-task protocol needs an explicit scenario-ready/render barrier.
- The tests below do not evaluate native OpenCode/Claude Code/Codex scaffolds,
  learned motor controllers, unfamiliar worlds, bosses or full campaign success.
- Case 22 revealed an asynchronous shutdown race: one raw heartbeat followed
  result export. The exported events are an exact prefix, and all observed
  state in the trailing heartbeat is identical; only clocks advance. Preserve
  the original result/export and mark a qualified `pass_with_inert_tail` after
  checking that property and hashing the raw journal. Any state change or
  trailing checkpoint remains an audit failure. Future attempts wait for their
  owned game process to terminate before reading the final journal. This changes
  cleanup synchronization, not prompts, observations or action semantics.
  The screening driver paused after case 24 completed; case 25 onward and the
  shuffled repeat cohort use the synchronized cleanup. Source hashes distinguish
  this boundary, and every older result/export is preserved.

## Early selection log

- The first Haiku tool-loop attempt was truncated by transport failure after
  eight accounted responses. It is not a clean tools-vs-JSON comparison.
- A complete Haiku JSON fresh run collected wood and obtained a workbench.
  Repeat a clean tool-loop run before attributing the difference to scaffolding.
- The initial Gemini normal-PvE run died before obtaining wood. Compare paused
  and guided conditions, and inspect mob exposure, before attributing failure.
- Crafting and slime probes expose behavior that a wood-only score would miss.
  Keep both task families in diagnostic follow-ups.
- After screening cases 01..09, three static Gemini predictions appeared closer
  to the annotated targets after scaling from 0..1000 than as literal pixels.
  Inserted four explicitly labeled normalized-coordinate attempts (two Gemini,
  one Haiku, one DeepSeek). This is an adaptive hypothesis, not retrospective
  correction of previous executed actions or independent confirmation.
- The coordinator stopped only the screening driver between games, inserted
  normalized attempts, and resumes it afterward. Source synchronization at that
  boundary adds the declared variant; default pixel behavior stays the same.
  Each attempt retains its actual source snapshot/hash, including earlier code.
- After N01 collected wood, selected three new fresh attempts for each of five
  cells: Haiku tools/JSON/paused and Gemini tools/normalized. Randomize order
  within each of three blocks using seed 20261017. This checks early signals
  and replaces the truncated baseline with clean attempts; it remains adaptive
  development on the same world, not held-out confirmation. Run after screening
  and stop at the existing shared budget cap. No hidden response retries.
