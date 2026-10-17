# Reconstructed reference baseline — October 17, 2026

The user authorized inferring missing details from terrariabench.com. This
profile reconstructs the **published May 7 API sweep**, rather than treating
every proposed feature in the specification as implemented behavior. The spec
describes native coding-agent CLIs; all seven published results label their
actual harness `api`.

Sources: [specification](https://terrariabench.com/spec/),
[chart manifest](https://terrariabench.com/charts/manifest.json),
[Flash result](https://terrariabench.com/runs/20260507_164917_1_api_google_gemini-3-flash-preview_03_open_ended_progress/result.json),
[initial screenshot](https://terrariabench.com/runs/20260507_164917_1_api_google_gemini-3-flash-preview_03_open_ended_progress/frames/frame_00001.png).
`reference/evidence.json` freezes URLs, retrieval statuses, hashes and minimal
scoring facts from all seven results. Raw artifacts live in the ignored
`reference/published/` directory. The snapshot has 19 retrieval records,
including explicit 404s, rather than 19 successful downloads.

## Evidence and implementation

| Dimension | Public evidence | Our baseline |
| --- | --- | --- |
| Observation | PNG is 1024×1024; visible hotbar, minimap, checkpoint chat | 1024×1024 game-window screenshots |
| Interaction | Spec requires real pointer input; direct tile-control evidence invalidates runs | OS keyboard/mouse via uinput, no game-state action tools |
| Task | Open-ended fresh-world progress; endpoint Wall of Flesh | Authored open-ended prompt; no axe/recipe/hotbar strategy hints |
| Harness | Seven published result files say `api` | Shared API loop; exact original tools unavailable |
| Checkpoints | Agent may read checkpoint log; visible checkpoint messages | Sanitized public events and matching style of in-game text |
| Starting state | First frames show 100 HP, 20 MP, plain copper starter tools and forest spawn | Fresh Classic character; plain three-item loadout before timer start |
| PvE | Seven results set hostile mobs and PvE false | Explicit disabled-PvE scenario policy |
| Reasoning/budget | Medium reasoning; 28,800-second declared budgets | Medium reasoning; evaluation mode requires that duration; calibration separate |
| Score | Distinct agent-driven progress checkpoints; diagnostics excluded | Separate public-subset score, excluding inherited facts and diagnostics |

## Inferences and unknowns

- **World:** upstream saves, seed, size and evil are unavailable. Our small
  Classic Corruption world uses ordinary seed `32000001`. Original saves were
  frozen before first world entry and are copied per attempt. Terrain visibly
  differs from the reference, so difficulty is not exactly matched.
- **Graphics/build:** UI scale 0.9 and zoom 1.0 approximate the visible HUD;
  those values are inferred. Omarchy uses Terraria 1.4.4.9 / tModLoader
  v2026.8.3.0. The upstream build is unknown. Runs record our DLL hash.
- **Prompt/tools/context:** original prompt, schemas, transcripts and detailed
  settings are unavailable. The exposed run transcript/settings files return
  404. Our `look`, `act`, `checkpoints` interface, 2-second holds, 16-command
  batches, provider-default sampling, 4,096-token output ceiling and full
  conversation retention are explicit choices. No silent compaction or
  strategy helpers are used.
- **PvE semantics:** upstream booleans do not reveal implementation. Our mod
  deactivates hostile NPCs/projectiles without loot or defeat credit.
  **This includes bosses and prevents boss-completion milestones.** It is an
  early-game baseline, not a validated full-progression scenario. A later
  boss-capable or mobs-enabled profile must have a distinct identity.
- **Scorer:** thirteen public checkpoint identifiers are implemented; only
  wood thresholds/levels have positive published scoring examples. Other
  predicates/levels are inferred. Inventory possession is not proof of
  crafting; Wall of Flesh uses Hardmode as a proxy. Input backing means an
  agent input preceded the fact, not proven causation.
- **Time:** public artifact timestamps and reported game elapsed time do not
  establish identical clock semantics. We record wall time and game updates
  separately and make no speed comparison.

These uncertainties remain in `configs/reference-reconstructed.json` and every
run manifest. No exact or official reproduction claim is made.

## Scorer regression

The reconstructed scorer reproduces all seven published agency counts:

| Published model | Agency score reproduced |
| --- | ---: |
| Gemini 3 Flash Preview | 4 |
| Gemini 3.1 Flash Lite Preview | 3 |
| Gemini 3.1 Pro Preview | 3 |
| Claude Opus 4.7 | 0 |
| Kimi K2.6 | 0 |
| GPT-5.5 | 0 |
| Qwen3.6 27B | 0 |

This is regression against reported facts, not independent reconstruction of
the complete detector. Known identifiers are `wood_1`, `wood_10`, `wood_25`,
`wood_100`, `workbench_1`, `torch_10`, `furnace_1`, `early_bar_5`,
`max_life_160`, `biome_jungle`, `boss_eye_of_cthulhu_defeated`,
`biome_underworld`, and `boss_wall_of_flesh_defeated`. Unknown milestones earn
no credit and are reported. The old 29-fact Moon Lord catalog is separate.

## Runtime validation on Omarchy

Observer/scenario mod v0.3 compiled with zero errors or warnings. An isolated
operator-only plumbing run verified 1024-square capture, plain starting items,
100 HP maintained, and suppression of a deliberately spawned hostile slime.
The probe has two explicit calibration-only environment gates; neither was
enabled for the paid model run. No operator progress earned model credit.
That plumbing test used UI scale 1.0; the model run used the selected 0.9.

`runs/reference-open-ended-calibration-01` tested the new open-ended loop:

| Measure | Result |
| --- | --- |
| Model | `google/gemini-3.8-flash` |
| Reasoning | Medium |
| Stop | Declared 12-call calibration limit |
| Active wall time | 117.91 seconds |
| Input commands | 17 |
| Agent screenshots | 6, all 1024×1024 |
| Invalid tools | 0 |
| Progress | `wood_1`, `wood_10`, `wood_25`; public-subset agency score 3 |
| Reported inference cost | $0.049326375; no uncertain reservation |
| Context | Full conversation retained, including provider reasoning metadata |
| PvE | No active hostile NPC/projectile at recorded heartbeats |
| Audit | Inputs, image/source hashes, model identity, checkpoint visibility and usage pass |

The agent selected its own actions without wood/workbench instructions and was
not stopped by an early milestone. Wood facts occurred around 72.59, 72.85 and
74.18 observer wall seconds. These times are descriptive only. Three checkpoints
in a short calibration do **not** establish equal or better performance than
the reference's much longer runs.

Artifacts, source snapshots and HTML replay are available locally and on
Omarchy under that run name. Scoped termination stopped the dedicated client;
its journal remains explicitly open. The scorer's historical
`valid_for_long_horizon` field tests only direct-control/stall conditions and
must not be interpreted as completion of an eight-hour evaluation. The audit
and manifest identify this attempt as calibration and unofficial.

All 23 regression tests pass. Including two historical coached attempts
($0.037074), total reported paid testing so far is **$0.086400375**.

## Next gate

The public settings above are reconstructed and the early-game loop is tested.
Before comparing modern models, freeze a matched fixture/prompt/tool suite,
report every attempt and resource stop, and validate longer context behavior.
Boss/PvE policy and advanced scoring need separate validation before a
through-Wall-of-Flesh claim. Combat-enabled, richer-control and Moon Lord
extensions follow baseline validation and remain separate profiles.
