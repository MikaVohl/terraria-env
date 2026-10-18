"""Record the whole Omarchy desktop (HEADLESS-1) to an MP4 without any interactive portal approval.

Captures frames with grim (wlr-screencopy, the same path the harness uses for observations) and
encodes them with ffmpeg using real capture timestamps (variable frame rate, NVENC H.264).
Stops cleanly on SIGINT/SIGTERM, or when --until-file exists. Passive: never sends input.

    python tools/record_desktop.py OUT.mp4 [--fps 10] [--until-file PATH]
"""
import argparse
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.linux_control import desktop_environment  # noqa: E402

stopping = False


def stop(*_):
    global stopping
    stopping = True


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("output", type=Path)
    p.add_argument("--fps", type=float, default=10)
    p.add_argument("--output-name", default="HEADLESS-1")
    p.add_argument("--until-file", type=Path, help="stop once this file exists")
    p.add_argument("--max-seconds", type=float, default=1800)
    a = p.parse_args()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    env = desktop_environment()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-c:v", "ppm",
                               "-use_wallclock_as_timestamps", "1", "-i", "-", "-fps_mode", "vfr",
                               "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "26", "-pix_fmt", "yuv420p",
                               "-movflags", "+faststart", str(a.output)], stdin=subprocess.PIPE)
    started, frames, period = time.monotonic(), 0, 1 / a.fps
    try:
        while not stopping and time.monotonic() - started < a.max_seconds:
            if a.until_file and a.until_file.exists():
                break
            t0 = time.monotonic()
            frame = subprocess.run(["grim", "-o", a.output_name, "-t", "ppm", "-"], env=env, capture_output=True, timeout=5).stdout
            if frame:
                ffmpeg.stdin.write(frame)
                frames += 1
            time.sleep(max(0, period - (time.monotonic() - t0)))
    finally:
        ffmpeg.stdin.close()
        ffmpeg.wait(timeout=60)
    print(f"{a.output}: {frames} frames in {time.monotonic() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
