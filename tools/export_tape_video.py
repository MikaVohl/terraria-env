"""Render a recorded tape to MP4 at one or more playback speeds.

1x is terraria-px's default pace: 80 ms per action (12.5 actions/s), so a full
3,000-action episode lasts 4 minutes. Every action is shown in order; speed only
changes how many actions advance per 30 fps frame. Rendering uses the given
game snapshot's own renderer and core (tools/replay_video.c), headless.

    PYTHONPATH=python .venv/bin/python tools/export_tape_video.py \
        --env-root experiments/v7-reward-20261017.sGYPqq/variants/v7 \
        --tape run.tape --speeds 1 1.5 2 3 --out videos/ --title "..." --subtitle "..."
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

FPS = 30
BASE_ACTIONS_PER_SECOND = 1000 / 80   # terraria-px DEFAULT_TICK_MS


def build(env_root: Path, out: Path) -> Path:
    repo = Path(__file__).resolve().parents[1]
    exe = out / "replay-video"
    cflags = subprocess.check_output(["sdl2-config", "--cflags"], text=True).split()
    libs = subprocess.check_output(["sdl2-config", "--libs"], text=True).split()
    subprocess.run(["cc", "-std=c11", "-O2", "-Wno-unused-function", "-Wno-unused-const-variable",
                    f"-I{env_root/'include'}", f"-I{env_root/'src'}", f"-I{env_root/'third_party'}", *cflags,
                    f'-DVIDEO_RENDER_SOURCE="{env_root/"src/px_render.c"}"',
                    f'-DVIDEO_MAIN_SOURCE="{env_root/"src/px_main.c"}"', str(repo / "tools/replay_video.c"),
                    *[str(env_root / "src" / f) for f in ("sim.c", "worldgen.c", "light.c", "obs.c")],
                    "-o", str(exe), "-lm", *libs], check=True)
    return exe


def schedule(actions: int, speed: float) -> list[int]:
    """Action count to have applied by each frame: 1.5 s hold, playback, 3 s hold."""
    per_frame = BASE_ACTIONS_PER_SECOND * speed / FPS
    frames = [0] * int(1.5 * FPS)
    k = 1
    while (target := min(actions, int(k * per_frame))) < actions:
        frames.append(target)
        k += 1
    return frames + [actions] * (3 * FPS)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env-root", type=Path, required=True, help="game snapshot with src/, include/, third_party/")
    p.add_argument("--tape", type=Path, required=True)
    p.add_argument("--speeds", type=float, nargs="+", default=[1.0])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--title", default="TERRARIA-LITE | PPO POLICY REPLAY")
    p.add_argument("--subtitle", default="")
    p.add_argument("--plain", action="store_true",
                   help="no title header and only the one-line stats footer (game canvas and crafting list at the top)")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    exe = build(a.env_root.resolve(), a.out)
    lines = a.tape.read_text().splitlines()
    actions = int(next(x for x in lines if x.startswith("actions ")).split()[1])
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_RENDER_DRIVER": "software"}
    for speed in a.speeds:
        tag = f"{speed:g}x"
        sched = a.out / f"schedule_{tag}.txt"
        frames = schedule(actions, speed)
        sched.write_text("".join(f"{s}\n" for s in frames))
        video = a.out / f"{a.tape.stem}_{tag}.mp4"
        note = "" if a.plain else (f"Playback {tag} ({BASE_ACTIONS_PER_SECOND*speed:g} actions/s; "
                                   "1x = terraria-px default 80 ms/action). Every action shown in order.")
        title = "" if a.plain else a.title
        # Must match replay_video.c: PX_WIN 736x528, header 48|0, footer 48|20.
        width, height = 736, 528 + (48 if title else 0) + (20 if a.plain else 48)
        with (a.out / f"render_{tag}.log").open("w") as log:
            render = subprocess.Popen([str(exe), str(a.tape), str(sched), title, a.subtitle, note],
                                      stdout=subprocess.PIPE, stderr=log, env=env)
            encode = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                                     "-pixel_format", "rgb24", "-video_size", f"{width}x{height}", "-framerate", str(FPS),
                                     "-i", "pipe:0", "-vf", f"scale={2*width}:{2*height}:flags=neighbor", "-c:v", "libx264",
                                     "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                                     "-movflags", "+faststart", str(video)], stdin=render.stdout)
            render.stdout.close()
            rc = render.wait()
        if rc or encode.returncode:
            raise SystemExit(f"{tag}: renderer rc={rc}, ffmpeg rc={encode.returncode} (see render_{tag}.log)")
        final = json.loads(next(x for x in (a.out / f"render_{tag}.log").read_text().splitlines()
                                if x.startswith("VIDEO_FINAL ")).split(" ", 1)[1])
        print(f"{video}  {len(frames)/FPS:.1f} s  final {final}")


if __name__ == "__main__":
    main()
