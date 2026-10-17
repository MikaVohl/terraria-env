# Omarchy worker assessment

Historical pre-installation assessment. Terraria/tModLoader have since been
installed and live controls tested. Current runtime validation is in
[REFERENCE_BASELINE.md](REFERENCE_BASELINE.md).

Inspected October 17, 2026 over Tailscale SSH as `mika@Omarchy`.
Verdict: **suitable hardware and a reachable graphical session for a dedicated
Terraria worker using API-hosted models; game installation and live input/game
validation remain necessary.** No remote packages, settings or files were changed.

## Observed

| Component | Result |
| --- | --- |
| OS | Omarchy 4.0.3, Arch-based Linux x86_64 |
| CPU | Intel Core i7-9700, 8 physical cores, up to 4.7 GHz |
| RAM | 31 GiB reported total; about 21 GiB available during inspection |
| GPU | NVIDIA RTX 2060, 6 GiB VRAM; NVIDIA driver loaded; 1% utilization during inspection |
| Root/home storage | About 47 GiB free |
| Additional storage | About 402 GiB free on `/mnt/storage`, suitable for larger replay archives |
| Graphics | Active Hyprland Wayland session; Xwayland available |
| Output | Active `HEADLESS-1`, 2304×1488 at 60 Hz, scale approximately 1.333 |
| Capture | `grim` successfully captured the Wayland output over SSH; image discarded, never saved |
| Input prerequisites | `wtype` and `hyprctl` available; `/dev/uinput` readable/writable by `mika` |
| Other tools | Python 3.14.7, .NET 10 runtime, FFmpeg, Xorg |

No Steam executable was found in PATH or the checked normal installation paths.
The detected `~/.local/share/Steam` library had no Terraria or tModLoader
directories/manifests. This is a check of standard locations, not a whole-disk
inventory.

## Remaining setup and validation

1. Install the owned Linux Terraria game and a pinned tModLoader release, using
   the [official installation guide](https://github.com/tModLoader/tModLoader/wiki/tModLoader-guide-for-players).
   Check the chosen release's runtime needs; the system's .NET 10 alone is not
   proof of compatibility. The local prototype was compiled against a .NET 8
   tModLoader installation on the Mac.
2. Deploy the benchmark to its own directory and isolate player/world fixtures.
3. Implement and test Linux keyboard/mouse dispatch. No input was injected during
   this assessment; writable uinput is a prerequisite, not proof of correct input.
4. Set a fixed benchmark viewport/scale in the dedicated session and validate
   screenshot-to-pointer coordinates. The present fractional display scaling
   needs explicit handling.
5. Launch the graphical game, verify hardware rendering, focus behavior and
   stable frame timing, then test manual wood/workbench telemetry before models.

The active headless graphical output means a physical monitor was not required
for the successful capture test. It does not by itself establish that Terraria
will render correctly. Keep capture and input dispatch on the remote worker;
use SSH for orchestration and result retrieval. Benchmark input will target
Omarchy's session, leaving the Mac's keyboard/mouse available for normal use.

No local-model throughput, game FPS, simulation determinism, long-duration
stability or official benchmark eligibility was established in this assessment.

## Follow-up after game installation

Verified October 17, 2026 after the user installed both games:

- Terraria and tModLoader are installed under
  `/home/mika/.local/share/Steam/steamapps/common/`.
- Steam manifests report Terraria build `24893155` and tModLoader build `25640906`.
- The remote `tModLoader.dll` hash exactly matches the initial Mac build recorded
  in VALIDATION.md. The graphical client identifies tModLoader **v2026.8.3.0**
  and Terraria **v1.4.4.9**.
- Copied the independent benchmark sources to
  `/home/mika/Projects/TerrariaBench`. All eight unit tests passed on Python 3.14.7.
- The official launcher successfully installed its local .NET **8.0.0** runtime
  and compiled/packaged the observer with zero warnings and zero errors.
- A bounded graphical startup test used only
  `/home/mika/Projects/TerrariaBench/runs/omarchy-smoke/tml` for saves/settings.
  Logs confirm X11 through Xwayland, OpenGL, and the **RTX 2060 hardware renderer**.
- Captured and visually inspected only the test game's window. The game rendered
  its first-run language-selection screen correctly on the headless display.
  The test instance was then closed; no gameplay or model calls took place.
- Prepared the observer's enabled-mod config in the isolated profile, but have
  not verified its runtime loading or gameplay telemetry. The first-run screen
  appears before that validation. No player or world fixture was created.

Startup artifacts are under `runs/omarchy-smoke/` locally and remotely. The normal
Steam installation's launcher/runtime initialization did write its standard logs
and runtime files; tModLoader also normalized one vanilla asset filename's case.
The initial assessment above was read-only; this follow-up performed the stated
project deployment, runtime initialization and isolated launch test.

The remaining gates are fixed window geometry, Linux input control, completion
of first-run setup, observer loading, world fixtures and the manual gameplay
telemetry audit. Installation and hardware rendering are now verified.

## Live worker follow-up

These early gates were subsequently exercised: native Wayland capture, bounded
uinput controls, fixed screenshot geometry, observer v0.2 loading, immutable fresh
fixtures, manual harvesting/crafting, and a successful OpenRouter model smoke.
The native Wayland path resolved pointer-position delivery that failed under
the initial Xwayland test. The model run completed wood/workbench objectives;
see [LIVE_SMOKE.md](LIVE_SMOKE.md) for full results, costs and remaining limits.
