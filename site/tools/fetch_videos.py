"""Copy, trim and transcode the official-Terraria run videos the site shows (site/media/, gitignored).

For every run in RUNS this script

1. copies the run's recording and its small records from Omarchy
   (`desktop.mp4`, `recording.json` if present, `clock.jsonl`, `result.json`, `telemetry/*.jsonl`) into
   site/media/raw/<run>/;
2. places the recording on the wall clock: video time = unix - video start + offset. The video start is
   recording.json `video_start_unix` (TerrariaBench tools/record_desktop.py, since 2026-11-11); older
   recordings have no sidecar and start at the birth time of desktop.mp4 (their wall-clock frame
   timestamps start at 0). For paused-clock runs the offset is fitted: ffmpeg's freezedetect finds the
   stretches where the game window does not change, and the offset (searched in [-3 s, 3 s]) is the one
   that puts the most of the logged freeze intervals (clock.jsonl: `freeze` / `thaw` around every model
   call, the SIGSTOP / SIGCONT of the game) on still video. The fit and its recall are stored;
3. keeps only game time: from the observer journal's `start` event to the end of the evaluation
   (result.json `evaluation_end_unix`, but at most 1 s after the journal's last line: the journal
   stops when the player leaves the world), minus every freeze interval
   in paused mode. The kept length is checked against the played game time (result.json
   `game_seconds`): the script stops if they differ by more than 2 %;
4. two recording formats:
   - old (no recording.json, `source` grim): 1100x1100 desktop, silent. The 1024x1024 game window is
     cropped out and resampled to 10 frames/s; the output has no audio;
   - new (`source` x11grab): the 1024x1024 game window itself at 30 frames/s with the game's audio
     (AAC). No crop; the output keeps 30 frames/s and the audio, cut with the same frame selection
     (for every kept frame the audio samples of its 1/30 s, placed via recording.json
     `audio_start_unix`), so sound stays in sync across the freeze cuts;
   both scaled to 960x960, H.264 (CRF 27, faststart) plus a poster frame;
5. writes site/data/videos.json (durations, offsets, recall, kept segments count, fps, audio) for the pages.

Real-time runs are not shortened: only the launch before the journal start and the seconds after
the evaluation end are dropped, so the video length equals the 20 game-minutes as well.

    python3 site/tools/fetch_videos.py            # every run in RUNS (skips existing outputs)
    python3 site/tools/fetch_videos.py --force c2-opus-pa-w401
    python3 site/tools/fetch_videos.py --adhoc rectest-2026-11-11/single-d31   # any run; prints the row only

Needs ssh access to mika@omarchy, ffmpeg/ffprobe on PATH and numpy.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HOST = "mika@omarchy"
REMOTE = "Projects/terraria-lite/TerrariaBench/runs"
SITE = Path(__file__).resolve().parents[1]
MEDIA = SITE / "media"
RAW = MEDIA / "raw"
OUT_JSON = SITE / "data" / "videos.json"
FPS = 10  # old desktop recordings; new game-window recordings keep their own rate (recording.json fps)
AUDIO_RATE = 48000
SIZE = 960
CRF = 27

# (campaign, run, why it is on the site)
RUNS = [
    ("landscape-2026-11-08", "c2-opus-pa-w401", "Best run of the campaign: Opus paused, extended 7 (torches crafted and placed, silver/gold-tier ore)"),
    ("landscape-2026-11-08", "c3-combo-rt-w401", "Opus planner + Jev executor, real time: published 6, bench placed at 2:25, wooden breastplate"),
    ("landscape-2026-11-08", "c1-opus-rt-w401", "Opus alone, real time: bench placed 8:56, wooden armour, 17 deaths"),
    ("landscape-2026-11-08", "b12-haiku-pa-w402", "Best Haiku paused run: published 5, then an end-of-session wrap-up streak"),
    ("landscape-2026-11-08", "b13-haiku-rt-w402", "Best Haiku real-time run: extended 5, cavern layer at 10:11, 21 deaths"),
    ("landscape-2026-11-08", "b06r-luna-pa-w403", "Best Luna paused run: wood 100 at 4:24 on the unseen corruption world"),
    ("landscape-2026-11-08", "b01-luna-rt-w401", "Best Luna real-time run: torches crafted at 6:44"),
    ("landscape-2026-11-08", "a4-terra-pa-w401", "Best Terra paused run: extended 4, long action batches"),
    ("landscape-2026-11-08", "b09-terra-rt-w402", "Best Terra real-time run: published 4, underground 3:41"),
    ("landscape-2026-11-08", "b05-luna-rt-w403", "Real-time death loop: Luna dies 17 times in 20 minutes"),
    ("landscape-2026-11-08", "b14-haiku-pa-w403", "Haiku stops acting at 12:35 and the no-action rule waits out the session"),
    ("landscape-2026-11-08", "b08-terra-pa-w403", "Terra uses Save & Exit at 1:41 in paused mode; the journal ends with the world"),
    ("default-game-2026-11-08", "m15-terra-rt-w402", "Terra uses Save & Exit at 16:04 in real time; re-entering crashed the game (default-v1)"),
    ("landscape-2026-11-08", "c4-combo-pa-w401", "Opus planner + Jev executor, paused: published 4, extended 4, 886 model calls frozen out"),
    ("landscape-2026-11-08", "d1-terra-pa-w401-40m", "Terra paused, 40 game-minutes"),
    ("landscape-2026-11-08", "d2-haiku-rt-w401-40m", "Haiku real time, 40 game-minutes"),
]


def sh(*cmd: str, **kw) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


def remote_ok(campaign: str, run: str) -> bool:
    """A run is finished once it has result.json (or, for runs that crashed without one, termination.json)."""
    d = f"{REMOTE}/{campaign}/{run}"
    return subprocess.run(["ssh", HOST, f"test -s {d}/desktop.mp4 && (test -e {d}/result.json || test -e {d}/termination.json)"]).returncode == 0


def fetch(campaign: str, run: str) -> Path:
    d = f"{REMOTE}/{campaign}/{run}"
    dst = RAW / run
    dst.mkdir(parents=True, exist_ok=True)
    files = [f"{HOST}:{d}/{f}" for f in ("desktop.mp4", "result.json", "telemetry")]
    sh("rsync", "-a", *files, str(dst) + "/")
    for optional in ("clock.jsonl", "recording.json"):  # real-time runs have no clock.jsonl, old recordings no sidecar
        subprocess.run(["rsync", "-a", f"{HOST}:{d}/{optional}", str(dst) + "/"], capture_output=True)
    birth = sh("ssh", HOST, f"stat -c %.W {d}/desktop.mp4").strip()
    (dst / "birth.txt").write_text(birth + "\n")
    return dst


def recording(dst: Path) -> dict:
    """Recording format: new game-window recordings (x11grab) carry their start, fps and audio start in recording.json."""
    p = dst / "recording.json"
    meta = json.loads(p.read_text()) if p.exists() else {"source": "grim"}
    meta.setdefault("video_start_unix", float((dst / "birth.txt").read_text()))
    window_only = meta["source"] == "x11grab"
    meta["out_fps"] = round(meta["fps"]) if window_only else FPS
    meta["audio_delay"] = meta["audio_start_unix"] - meta["video_start_unix"] if window_only and meta.get("audio_start_unix") else None
    return meta


def journal(dst: Path) -> tuple[float, float]:
    """Unix time of the observer's start event and of its last line."""
    lines = [json.loads(l) for f in sorted((dst / "telemetry").glob("*.jsonl")) for l in f.read_text().splitlines() if l.strip()]
    start = next(e["unix_seconds"] for e in lines if e.get("event") == "start")
    last = max(e["unix_seconds"] for e in lines if "unix_seconds" in e)
    return start, last


def freezes(dst: Path) -> list[tuple[float, float]]:
    p = dst / "clock.jsonl"
    if not p.exists():
        return []
    out, cur = [], None
    for line in p.read_text().splitlines():
        e = json.loads(line)
        if e["event"] == "freeze":
            cur = e["unix"]
        elif e["event"] == "thaw" and cur is not None:
            out.append((cur, e["unix"]))
            cur = None
    if cur is not None:  # the run ended frozen
        out.append((cur, float("inf")))
    return out


def window(raw: Path, at: float) -> tuple[int, int]:
    """Top-left corner of the 1024x1024 game window: its 2-px grey frame (about rgb 68,68,76) on the desktop."""
    png = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(raw), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    w = h = 1100
    a = np.frombuffer(png, np.uint8).reshape(h, w, 3).astype(int)
    frame = (np.abs(a - [68, 68, 76]).max(axis=2) <= 10)
    cols = frame[100:1000].mean(axis=0)
    rows = frame[:, 100:1000].mean(axis=1)
    left = int(np.argmax(cols > 0.8)) + 2
    bottom = int(np.nonzero(rows > 0.8)[0].max()) - 1  # last frame row; content ends 2 rows above it
    top = bottom - 1024
    if not (0 <= left <= w - 1024 and 0 <= top <= h - 1024):
        raise SystemExit(f"{raw}: game window not found (left {left}, top {top})")
    return left, top


def stills(raw: Path, crop: tuple[int, int], dur: float) -> list[tuple[float, float]]:
    log = raw.with_name("stills.txt")
    x, y = crop
    sh("ffmpeg", "-v", "error", "-i", str(raw), "-vf", f"crop=1024:1000:{x}:{y + 24},freezedetect=n=-50dB:d=0.6,metadata=mode=print:file={log.name}",
       "-an", "-f", "null", "-", cwd=raw.parent)
    t = log.read_text()
    st = [float(v) for v in re.findall(r"freeze_start=([\d.]+)", t)]
    en = [float(v) for v in re.findall(r"freeze_end=([\d.]+)", t)]
    en += [dur] * (len(st) - len(en))
    return list(zip(st, en))


def fit_offset(fr, still, birth, dur):
    """Offset (s) that maximises the share of logged freeze time falling on still video, at 0.05 s resolution."""
    n = int(dur * 20) + 2
    det = np.zeros(n, bool)
    for a, b in still:
        det[int(a * 20):int(b * 20)] = True
    best = (0.0, -1.0)
    for o in np.arange(-3, 3.0001, 0.05):
        m = np.zeros(n, bool)
        for a, b in fr:
            a, b = a - birth + o, min(b - birth + o, dur)
            if b > 0:
                m[max(0, int(a * 20)):int(b * 20)] = True
        if m.sum():
            rec = (m & det).sum() / m.sum()
            if rec > best[1]:
                best = (round(float(o), 2), float(rec))
    return best


def keep_segments(t_start, t_end, fr_video):
    segs, cur = [], t_start
    for a, b in sorted(fr_video):
        if b <= cur or a >= t_end:
            continue
        if a > cur:
            segs.append((cur, a))
        cur = max(cur, b)
    if cur < t_end:
        segs.append((cur, t_end))
    return segs


def encode(raw: Path, crop, segs, out: Path, fps: int, audio_delay: float | None):
    """Decode at a constant fps (frame i shows video time i / fps), keep the frames inside the segments, encode them.
    The selection runs in Python because an ffmpeg select expression with hundreds of terms is too deep to parse.
    With audio (audio sample time 0 = video time audio_delay), every kept frame takes the samples of its 1 / fps s,
    so the cut audio stays in sync with the cut video."""
    frame = SIZE * SIZE * 3 // 2  # yuv420p
    starts = np.array([a for a, _ in segs])
    ends = np.array([b for _, b in segs])

    def kept(i):
        t = i / fps
        k = np.searchsorted(starts, t, side="right") - 1
        return k >= 0 and t < ends[k]

    audio_in = []
    if audio_delay is not None:
        pcm, cut = raw.with_name("audio.s16"), raw.with_name("audio_kept.s16")
        sh("ffmpeg", "-v", "error", "-y", "-i", str(raw), "-map", "0:a", "-ac", "2", "-ar", str(AUDIO_RATE), "-f", "s16le", str(pcm))
        src = np.memmap(pcm, np.int16, "r").reshape(-1, 2)
        per = AUDIO_RATE // fps
        with cut.open("wb") as stream:
            for i in range(int(probe(raw) * fps) + 2):
                if kept(i):
                    a = round((i / fps - audio_delay) * AUDIO_RATE)
                    chunk = np.zeros((per, 2), np.int16)
                    lo, hi = max(a, 0), min(a + per, len(src))
                    if hi > lo:
                        chunk[lo - a:hi - a] = src[lo:hi]
                    stream.write(chunk.tobytes())
        del src
        pcm.unlink()
        audio_in = ["-f", "s16le", "-ar", str(AUDIO_RATE), "-ac", "2", "-i", str(cut)]
    vf = (f"crop=1024:1024:{crop[0]}:{crop[1]}," if crop else "") + f"fps={fps},scale={SIZE}:{SIZE}:flags=lanczos"
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(raw), "-vf", vf, "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{SIZE}x{SIZE}", "-r", str(fps),
                            "-i", "-", *audio_in, *(["-c:a", "aac", "-b:a", "128k", "-shortest"] if audio_in else ["-an"]),
                            "-c:v", "libx264", "-preset", "slow", "-crf", str(CRF), "-movflags", "+faststart", str(out)],
                           stdin=subprocess.PIPE)
    i = 0
    while buf := dec.stdout.read(frame):
        if len(buf) < frame:
            break
        if kept(i):
            enc.stdin.write(buf)
        i += 1
    enc.stdin.close()
    if dec.wait() or enc.wait():
        raise SystemExit(f"{raw}: ffmpeg failed")
    if audio_in:
        raw.with_name("audio_kept.s16").unlink()


def probe(p: Path) -> float:
    return float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)))


def process(campaign: str, run: str, why: str, force: bool) -> dict | None:
    out = MEDIA / f"{run}.mp4"
    poster = MEDIA / f"{run}.jpg"
    if not remote_ok(campaign, run):
        print(f"{run}: not finished on {HOST}, skipped", flush=True)
        return None
    dst = RAW / run
    if force or not (dst / "desktop.mp4").exists():
        fetch(campaign, run)
    raw = dst / "desktop.mp4"
    meta = recording(dst)
    start, fps = meta["video_start_unix"], meta["out_fps"]
    dur = probe(raw)
    res = json.loads((dst / "result.json").read_text()) if (dst / "result.json").exists() else {}
    j_start, j_last = journal(dst)
    end_unix = min(res.get("evaluation_end_unix") or j_last, j_last + 1)
    fr = freezes(dst)
    crop = None if meta["source"] == "x11grab" else window(raw, dur / 2)  # new recordings are the game window itself
    offset, recall = 0.0, None
    if fr:
        offset, recall = fit_offset(fr, stills(raw, crop or (0, 0), dur), start, dur)
        if recall < 0.9:
            raise SystemExit(f"{run}: freeze fit recall {recall:.3f} < 0.9; check the recording")
    to_v = lambda u: u - start + offset  # noqa: E731
    fr_v = [(to_v(a), min(to_v(b), dur)) for a, b in fr]
    segs = keep_segments(max(0.0, to_v(j_start)), min(dur, to_v(end_unix)), fr_v)
    kept = sum(b - a for a, b in segs)
    game_s = float(res.get("game_seconds") or (j_last - j_start))
    if abs(kept - game_s) > 0.02 * game_s + 2:
        raise SystemExit(f"{run}: kept {kept:.1f} s of video but the run played {game_s:.1f} game-s")
    if force or not out.exists():
        encode(raw, crop, segs, out, fps, meta["audio_delay"])
        mid = min(40.0, probe(out) / 2)  # early in the run: daylight on the surface, before the first descent
        sh("ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.2f}", "-i", str(out), "-frames:v", "1", "-vf", "scale=480:480", "-q:v", "4", str(poster))
    trimmed = probe(out)
    row = {
        "run": run, "campaign": campaign, "why": why, "clock": res.get("clock") or ("paused" if fr else "realtime"),
        "src": f"media/{run}.mp4", "poster": f"media/{run}.jpg",
        "raw_s": round(dur, 1), "trimmed_s": round(trimmed, 1), "kept_s": round(kept, 1), "game_s": round(game_s, 1),
        "freezes": len(fr), "frozen_cut_s": round(sum(min(b, dur) - a for a, b in fr_v if b > 0), 1),
        "offset_s": offset, "freeze_recall": None if recall is None else round(recall, 4), "segments": len(segs),
        "crop": list(crop) if crop else None, "fps": fps, "audio": meta["audio_delay"] is not None,
        "size_mb": round(out.stat().st_size / 2**20, 1),
    }
    print(f"{run}: raw {dur:.0f} s -> {trimmed:.0f} s (game {game_s:.0f} s, {len(fr)} freezes, offset {offset:+.2f} s, recall {recall}, "
          f"{meta['source']}, {fps} fps, audio {row['audio']})", flush=True)
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="*", help="only these runs (default: all)")
    p.add_argument("--force", action="store_true", help="copy and encode again")
    p.add_argument("--adhoc", metavar="CAMPAIGN/RUN", help="process any run (e.g. a test); prints its row, videos.json untouched")
    a = p.parse_args()
    MEDIA.mkdir(exist_ok=True)
    if a.adhoc:
        campaign, run = a.adhoc.split("/")
        print(json.dumps(process(campaign, run, "ad hoc", a.force)))
        return
    old = {r["run"]: r for r in json.loads(OUT_JSON.read_text())["videos"]} if OUT_JSON.exists() else {}
    rows = []
    for campaign, run, why in RUNS:
        if a.runs and run not in a.runs:
            if run in old:
                rows.append(old[run])
            continue
        r = process(campaign, run, why, a.force)
        if r:
            rows.append(r)
        elif run in old:
            rows.append(old[run])
    OUT_JSON.write_text(json.dumps({
        "_note": "Generated by site/tools/fetch_videos.py. Videos live in site/media/ (gitignored). trimmed_s is the encoded length; "
                 "for paused runs every logged freeze (model call) is cut, so trimmed_s should match game_s.",
        "fps": FPS, "size": SIZE, "crf": CRF, "videos": rows}, indent=1) + "\n")  # fps: old recordings; rows carry their own
    print(f"wrote {OUT_JSON} ({len(rows)} videos)")


if __name__ == "__main__":
    sys.exit(main())
