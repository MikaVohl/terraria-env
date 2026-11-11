"""Record a run to an MP4 plus a sidecar recording.json, without any interactive portal approval. Passive: never sends input.

Isolated display (--display :NN, tools/isolated_displays.py): ffmpeg grabs only the game's own rootful Xwayland
server (x11grab, the WxH game window at 0,0 -- the same pixels the model's screenshots read) at --fps (default 30)
and the monitor of the display's null sink (linux_control.ensure_game_sink; launch() routes the game there), so the
MP4 has the game's audio and nothing from other instances. H.264 NVENC + AAC.

Shared desktop (no --display): grim screenshots of the Hyprland output (wlr-screencopy) piped into ffmpeg with
wall-clock timestamps (variable frame rate, NVENC H.264, no audio).

recording.json (next to the MP4) maps video time to the wall clock: unix = video_start_unix + t. With audio,
audio sample time 0 is audio_start_unix (both are the inputs' wall-clock start timestamps as ffmpeg reports them).
Stops cleanly on SIGINT/SIGTERM, when --until-file exists, or after --max-seconds.

    python tools/record_desktop.py OUT.mp4 --display :11 [--fps 30] [--until-file PATH]
    python tools/record_desktop.py OUT.mp4 [--output-name HEADLESS-1] [--fps 10] [--until-file PATH]
"""
import argparse
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.linux_control import desktop_environment, ensure_game_sink  # noqa: E402

stopping = False


def stop(*_):
    global stopping
    stopping = True


def ffmpeg_version():
    return subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0]


def wait_until_done(a, started, alive=lambda: True):
    while not stopping and time.monotonic() - started < a.max_seconds and alive():
        if a.until_file and a.until_file.exists():
            break
        time.sleep(.25)


def record_display(a, env, sidecar, meta):
    """x11grab of the isolated display + its sink monitor; returns the sidecar fields learnt from ffmpeg."""
    sink = ensure_game_sink(a.display, env)
    log = a.output.with_name(a.output.stem + ".ffmpeg.log")
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-y",
           "-thread_queue_size", "1024", "-f", "x11grab", "-framerate", str(a.fps), "-video_size", a.size, "-draw_mouse", "0",
           "-i", f"{a.display}+0,0",
           "-thread_queue_size", "1024", "-f", "pulse", "-sample_rate", "48000", "-channels", "2", "-i", f"{sink}.monitor",
           "-t", str(a.max_seconds + 60), "-fps_mode", "passthrough",
           "-c:v", "h264_nvenc", "-preset", "p5", "-cq", str(a.cq),  # NVENC converts bgr0 to yuv420p on the GPU
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(a.output)]
    meta.update(source="x11grab", display=a.display, size=a.size, audio_sink=sink, audio_source=f"pulse:{sink}.monitor",
                audio_rate=48000, ffmpeg_log=log.name)
    started = time.monotonic()
    with log.open("w") as stream:
        ff = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stream)
        starts = {}
        while len(starts) < 2 and ff.poll() is None and time.monotonic() - started < 30:
            time.sleep(.2)
            starts = {kind: float(t) for kind, t in re.findall(r"Input #\d+, (x11grab|pulse), from .*\n\s+Duration: .*?start: ([\d.]+)",
                                                                log.read_text())}
        meta.update(video_start_unix=starts.get("x11grab"), audio_start_unix=starts.get("pulse"))
        sidecar.write_text(json.dumps(meta, indent=2) + "\n")
        wait_until_done(a, started, lambda: ff.poll() is None)
        if ff.poll() is None:
            ff.communicate(b"q", timeout=60)  # finalize the MP4
    return ff.returncode


def record_output(a, env, sidecar, meta):
    """Shared desktop: grim screenshots of one Hyprland output, wall-clock timestamps from the first frame on."""
    meta.update(source="grim", output_name=a.output_name, audio_source=None)
    ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-c:v", "ppm",
                           "-use_wallclock_as_timestamps", "1", "-i", "-", "-fps_mode", "vfr",
                           "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "26", "-pix_fmt", "yuv420p",
                           "-movflags", "+faststart", str(a.output)], stdin=subprocess.PIPE)
    started, frames, period = time.monotonic(), 0, 1 / a.fps
    try:
        while not stopping and time.monotonic() - started < a.max_seconds:
            if a.until_file and a.until_file.exists():
                break
            t0 = time.monotonic()
            grabbed = time.time()
            frame = subprocess.run(["grim", "-o", a.output_name, "-t", "ppm", "-"], env=env, capture_output=True, timeout=5).stdout
            if frame:
                ff.stdin.write(frame)
                if not frames:
                    # ffmpeg stamps each frame with its arrival time and starts the video at the first one.
                    meta["video_start_unix"] = grabbed
                    sidecar.write_text(json.dumps(meta, indent=2) + "\n")
                frames += 1
            time.sleep(max(0, period - (time.monotonic() - t0)))
    finally:
        ff.stdin.close()
        ff.wait(timeout=60)
    return ff.returncode


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("output", type=Path)
    p.add_argument("--display", help="isolated X display of the game (x11grab + audio); default: grim of --output-name")
    p.add_argument("--size", default="1024x1024", help="game window size at 0,0 of --display")
    p.add_argument("--fps", type=float, help="frames per second (default 30 with --display, else 10)")
    p.add_argument("--cq", type=int, default=28, help="NVENC constant quality (--display)")
    p.add_argument("--output-name", default="HEADLESS-1")
    p.add_argument("--until-file", type=Path, help="stop once this file exists")
    p.add_argument("--max-seconds", type=float, default=1800)
    a = p.parse_args()
    a.fps = a.fps or (30 if a.display else 10)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    env = desktop_environment()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    sidecar = a.output.with_name("recording.json")
    meta = {"video": a.output.name, "fps": a.fps, "ffmpeg": ffmpeg_version(), "started_unix": time.time()}
    t0 = time.monotonic()
    code = (record_display if a.display else record_output)(a, env, sidecar, meta)
    meta.update(ended_unix=time.time(), ffmpeg_exit=code)
    sidecar.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"{a.output}: {time.monotonic() - t0:.1f}s, ffmpeg exit {code}", flush=True)


if __name__ == "__main__":
    main()
