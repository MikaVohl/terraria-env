# Initial validation record

Historical local setup record. Later remote controls/API testing is in
[LIVE_SMOKE.md](LIVE_SMOKE.md); current reference reconstruction and its
23-test validation are in [REFERENCE_BASELINE.md](REFERENCE_BASELINE.md).

Date: October 17, 2026. All checks were local; no model API calls were made.

## Python prototype

Runtime: Python 3.12.13 from the parent project's existing virtual environment.
Command: `../.venv/bin/python -m unittest discover -s tests -v`.
Result: **8 tests passed**.

Tests cover synthetic round-trip scoring and refusal to overwrite journals,
inherited boss exclusion, mismatched sources/run IDs/schema, invalid numeric
values, unknown milestones, duplicate checkpoints, post-close events, truncated
sessions, Moon Lord detection, malformed JSON, and C#/Python catalog agreement.
The synthetic demo scored 2/29 facts, recorded one death, and was correctly
marked synthetic and ineligible. These are fixture values, not agent results.

The installation doctor detected both Terraria and tModLoader. It correctly
reported `live_runner_ready: false`. Source whitespace checks passed.

## Observer compilation

Built the final `Observer.cs` with the installed tModLoader's bundled compiler:

```text
Reading properties: TerrariaBenchObserver
Building: TerrariaBenchObserver
Compiling TerrariaBenchObserver.dll
Compilation finished with 0 errors and 0 warnings
Packaging: TerrariaBenchObserver
```

The build command is documented in README.md. It used an isolated tModLoader
save directory inside `runs/build/tml`, not the normal player save directory.
The bundled .NET runtime is 8.0.0, osx-x64. No standalone SDK was installed.

| Artifact | SHA-256 |
| --- | --- |
| Local `tModLoader.dll` | `fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5` |
| `mod/TerrariaBenchObserver/Observer.cs` | `23993339805cc9f08210bb5fbb58d94d51c6cc31192d90dfba8382586bbaff3e` |
| Generated observer `.tmod` (14,305 bytes) | `97a721a9ac768711b37ce608033d06e5a1506d4cbdd55a07a6628b251025cae4` |

The generated package is at
`runs/build/tml/Mods/TerrariaBenchObserver.tmod`, ignored by Git. Package hashes
may change on rebuild; this table identifies this particular build.

## Not yet validated

The mod has not been enabled in a live graphical game session. Actual event
timing, milestone semantics and boss attribution need gameplay tests. No input
bridge, screenshot loop, isolated agent, provider adapter, live budget guard,
world reset worker, full-game agent trajectory, deterministic replay or official
leaderboard exists yet. Compile and unit-test success do not establish those
properties. All scored journals remain explicitly unofficial.

## Remote startup follow-up

After the user installed the games on Omarchy, the source was deployed to
`/home/mika/Projects/TerrariaBench`. All 8 tests passed on its Python 3.14.7.
The official launcher initialized a local .NET 8.0.0 runtime, and the observer
compiled and packaged with **0 errors and 0 warnings** on Linux as well.

A bounded client test used an isolated save directory. Logs identify NVIDIA
RTX 2060 hardware rendering through OpenGL/Xwayland. A game-window-only
screenshot was visually checked and shows the first-run language-selection
screen, tModLoader v2026.8.3.0 and Terraria v1.4.4.9. The test process was closed.
There was no player/world session and no observer journal was expected/emitted.
Runtime mod loading, input control and gameplay telemetry remain unvalidated.
See OMARCHY_ASSESSMENT.md for the updated machine assessment.

## Live reproduction follow-up

The later observer v0.2, native Wayland/uinput bridge, immutable fixture runner,
OpenRouter adapter, budget guards, normalized coordinate conversion and replay
reporter were tested on Omarchy. There are now **16 passing regression tests**.
An operator trajectory and a 5-call model trajectory both reached wood/workbench
objectives. Both paid attempts passed frame/source/input/usage/journal consistency
audits. Total reported cost was **$0.03707400**. See LIVE_SMOKE.md; historical
limitations above describe the earlier setup and are not a current feature list.
