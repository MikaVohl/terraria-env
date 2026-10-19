# Diagnostic campaign findings

Early-game progress is feasible with the current screenshot/keyboard/mouse
bridge. The repeated trials do not support a universal best harness. They
overturned several impressions from the first single attempts, while exposing
specific control, measurement and provider-reliability issues worth studying.

We recorded **50 game attempts**: 32 screening attempts, 15 shuffled repeats and
three adaptive combat/budget probes, across three model families. Nine separate
static-image calls probed perception. This is development on one starting world,
not a complete-game evaluation, model leaderboard or native coding-agent
framework comparison. The [complete scorecard](results/screening-01/REPORT.md)
links every game result; [interpretation rules](interpretation.md) preserve the
selection log and limitations.

## Findings supported by the repeated cohort

Initial screening/pilot attempts are excluded from this table. Outcomes use
fully accounted attempts; all interrupted attempts remain in the raw scorecard
and costs. Three attempts per cell were planned, with order shuffled in blocks.

| Model / condition | Fully accounted / attempted | Held ≥25 wood | Workbench |
|---|---:|---:|---:|
| Haiku 5.5, native tools, real-time | 3/3 | 3/3 | 3/3 |
| Haiku 5.5, native tools, paused | 3/3 | 2/3 | 2/3 |
| Haiku 5.5, automatic-observation JSON | 3/3 | 0/3 | 0/3 |
| Gemini 3.8 Flash, native tools, pixels | 2/3 | 2/2 | 1/2 |
| Gemini 3.8 Flash, native tools, normalized | 3/3 | 2/3 | 1/3 |

Haiku's initial JSON run obtained a workbench, while its initial tools run was
interrupted after gathering wood. The repeats reversed the apparent advantage:
the native tool loop is a useful development baseline. They do not prove JSON
control is intrinsically inferior: the package also changes observation
scheduling, required notes and action-contract presentation, and the sample is
small. Syntax errors alone do not explain every unsuccessful JSON trajectory.

The static Gemini probe suggested a 0..1000 coordinate convention: scaling its
three predictions moved them closer to manually annotated target centers. Its
first normalized game run gathered 89 maximum observed wood after initial pixel
runs gathered none. Repeats showed that pixels can also support substantial
progress, including 102 maximum wood and a workbench. Normalization is not an
established end-to-end improvement. Keep coordinate conventions explicit and
test them on unseen scenes/worlds before standardizing an adapter.

Pausing inference is a valid diagnostic clock policy, verified by whole-process
freezing and resumption. It did not improve the observed Haiku workbench rate in
this small cohort. One paused attempt failed to obtain a workbench despite zero
damage and zero observed hostiles. Control/interpretation failures remain even
when inference-time danger is removed.

## Diagnostics the aggregate progress score would hide

Prepared crafting supplied 50 wood, 50 stone and five gel before scoring. Four
of five attempts obtained a workbench, one reached ten torches, and none recorded
a furnace. In a [reviewed sequence](trajectory-reviews.md), a successful recipe
selection moved the workbench icon, then the next click selected another recipe
instead of crafting. Privileged inventory helped in one crafting attempt but
not its fresh-world counterpart; these are single-attempt observations.

Eight fully accounted designated-target combat attempts produced no target
kill. A 16-call paused Gemini attempt dealt eight damage; the combined normalized
and paused 32-call attempt dealt 21, leaving the 25-HP target at four HP. Clock,
coordinates and opportunity changed together, so this does not isolate a cause.
The further 64-call probe was interrupted by transport on call five; its
re-run C04 killed the target (see campaign 02 below). Two additional combat
attempts were partial.
Background mobs, starter equipment and initial-render timing limit interpretation;
this is not evidence of inability to fight with other equipment or longer play.

The offered select-slot/hold macro was never invoked. That is an adoption result,
not a test of its execution quality. The long-hold condition did use eight inputs
above two seconds and obtained a workbench. Bounded notes reduced maximum prompt
size from about 28,400 to 2,900 tokens and the observed run cost, but its single
attempt gathered only five wood. Longer memory experiments need a stable shared
interaction contract before drawing conclusions about long-horizon competence.

## Measurement repairs and evidence

Fifty artifact audits found no unresolved consistency failures: 46 attempts have
all calls accounted for, including one qualified legacy result with an unchanged
post-snapshot heartbeat. Four provider-interrupted attempts remain partial. We
preserved their original records and uncertain charges. Shutdown now waits for
the owned game process to exit before exporting its journal.

Two [unpaid operator controls](validation/README.md) killed the target through
the same real input path. They exposed a fatal-hit counter omission in observer
0.4. Observer 0.5 uses a per-spawn target tag and passed the full damage/kill
control after compiling with zero errors/warnings. The first 49 paid attempts
retain observer 0.4 and their immutable fixture; none killed the target, so their
damage is unaffected by fatal-hit omission. Only C03 uses observer 0.5. Its
transport interruption prevents a longer-horizon gameplay conclusion.

Actual API calls, commands, screenshots, holds, game updates, damage, context size,
provider identity and observation age are exported separately. Equal API calls
buy different control opportunities. In-game menus can pause a nominally
real-time episode. Wall observation age includes inference and earlier actions
in a batch; a paused game's wall age does not equal game-state age. Wood maxima
are sampled inventory quantities, not cumulative gathering. Station possession
is not independent proof of crafting/placement.

## Follow-up campaign 02 (2026-10-18)

Nine further attempts under a separate $1.50 ledger
(`runs/diagnostic-campaign-02`, compact records in
[results/campaign-02](results/campaign-02/summary.csv)). Two harness changes
apply to every attempt: a declared bounded provider retry policy
(`openrouter.RETRY_POLICY`; each failed attempt logged and its reservation kept as
an uncertain charge) and a [combat render barrier](validation/README.md). All
nine artifact audits pass, all calls are accounted for, and all used observer 0.5.

**Held-out worlds.** Four small Classic worlds were generated after campaign 01
from declared seeds 32000101..32000104 (`tools/make_world_fixtures.py`; three
Crimson, one Corruption, chosen by seed). Each received one attempt of the
repeat-cohort baseline (native tools, real time, pixel coordinates, normal PvE,
16 calls) per model, in shuffled order:

| Model | ≥25 wood | Workbench | Max wood per world (101/102/103/104) |
|---|---:|---:|---|
| Haiku 5.5 | 1/4 | 2/4 | 6 / 32 / 10 / 7 |
| Gemini 3.8 Flash | 1/4 | 0/4 | 71 / 0 / 0 / 0 |

On the development world the same Haiku condition obtained a workbench 3/3 with
25–83 maximum wood; Gemini pixels reached 25 wood 2/2. The inspected spawn
frames of worlds 102–104 (where Gemini gathered nothing) each show a forest with
choppable trees 30–45 px from the player. Damage received (0–90) is in the
development tools cohort's range (7–120). So neither absent trees nor unusual
hostile exposure explains the drop. One Gemini final frame (world 102) shows
it beside a tree with the axe selected and no wood gathered. The likely cause is
targeting/execution, not route planning [INFERENCE: one frame inspected]. With
one attempt per cell this is a generalization warning, not a rate: development
world results overstate early-game reliability, and benchmark variants should be
selected on unseen worlds.

**Combat budget.** C04 re-ran the interrupted C03 probe (normalized coordinates,
paused inference, 64 calls, $0.75 local cap) with the render barrier. It **killed
the 25-HP target** (26 recorded damage including overkill), the first model kill
in either campaign. Damage began within the first five calls. The kill heartbeat
(game update 2400) falls between the actions of call 35 and call 37, just beyond
C02's 32-call budget, where that attempt stopped at 21 damage. It took 95 damage
without dying, then gathered wood. This is one attempt with a changed first frame
and observer, so it shows feasibility, not a budget effect or a kill rate.

**Retry policy in use.** One transport failure (URLError, call 61 of C04) was
retried after 2 s and succeeded; the episode completed. The attempt's $0.070963
reservation remains an uncertain charge. Under campaign 01's no-retry rule this
run would have been partial.

## Campaign 03: real-time planner/executor (2026-10-18)

Full report: [planner-executor.md](planner-executor.md). With the game never paused, a fast
executor acting on fresh observations (Jev at about 0.3 s observation age) outperformed the
single-model loop (6-10 s). With screenshots only, a high-level planner plus a fast Haiku executor
killed the slime 2/4 times against 1/4. A planner added nothing measurable on top of a good
executor: Jev alone matched planner + Jev at 120 s, and over 300 s replanning every 10, 30 or 60 s
made no reliable difference. Structured-state conditions are privileged. A no-model scripted rule
over the same action catalog still beats every model, and exploration of a barren world is unsolved.

## Candidates to discuss for the next benchmark phase

These are proposals for selection together, not newly implemented benchmarks.

| Candidate | Question it would answer | Next control needed |
|---|---|---|
| Visual native-tool loop, real-time, normal PvE | Can the whole agent make progress under ordinary game timing? | Unseen worlds, explicit budget information, declared menu/pause policy. |
| Same visual loop with paused inference | What changes when inference latency stops advancing the world? | Match action/observation contracts; record actual simulation exposure. |
| Structured-state and instruction diagnostics | Is a task blocked by UI perception, knowledge or planning? | Fresh synchronized state, matched opportunity budgets, separate guide/inventory factors. |
| Longer memory / controller experiments | Can progress persist beyond initial gathering, and can low-level combat be made reliable? | Stable action contract, prepared loadouts and independently validated task graders. Render barrier now in place. |

Native agent frameworks and learned motor policies remain untested. Full-game
evaluation requires progression beyond Wall of Flesh through the later game,
with validated intermediate fixtures and end conditions. Campaign 02 added a
bounded, logged provider retry policy; any retry must remain visible in records
and accounting, never an unlogged rerun.
The [research rationale](design-rationale.md) links the mature benchmark ideas
behind these proposals.

## Spending and closure

Campaign-reported charges were **$1.980374055**. Including **$0.086400375** in
earlier session tests gives **$2.066774430** reported session charges. Unresolved
reservations total **$0.255897600**, for conservative exposure of
**$2.322672030**, below the authorized **$3**. Independent operator controls used
no API calls. The paid campaign is closed; this is not an ongoing spending grant.

Campaign 02 used a separate user-authorized **$1.50** ledger: **$0.713794400**
reported charges plus **$0.070963200** uncertain reservation, for
**$0.784757600** conservative exposure. That campaign is also closed.
