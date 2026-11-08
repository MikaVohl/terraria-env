"""Game-clock check for one run: game updates per wall second while the game runs, and nothing while frozen.

    python tools/clock_check.py <run> [<run> ...]     # one JSON line per run; writes <run>/evidence/clock.json

Uses the observer heartbeats (one every 60 game updates, with a wall timestamp) and the harness's clock.jsonl
(freeze/thaw times of the paused clock). A heartbeat interval that overlaps a freeze is excluded from the running
rate and checked separately: a frozen game must not emit heartbeats.
"""
import json
import statistics as st
import sys
from pathlib import Path


def check(run):
    run = Path(run)
    tel = [json.loads(line) for f in sorted((run / "telemetry").glob("*.jsonl")) for line in open(f)]
    beats = [(e["game_updates"], e["unix_seconds"]) for e in tel if e.get("event") == "heartbeat"]
    log = [json.loads(line) for line in open(run / "clock.jsonl")] if (run / "clock.jsonl").exists() else []
    frozen, start = [], None
    for e in log:
        if e["event"] == "freeze":
            start = e["unix"]
        elif e["event"] == "thaw" and start is not None:
            frozen.append((start, e["unix"]))
            start = None
    if start is not None:
        frozen.append((start, float("inf")))

    def overlaps(a, b):
        return any(f0 < b and f1 > a for f0, f1 in frozen)

    rates = [(u1 - u0) / (t1 - t0) for (u0, t0), (u1, t1) in zip(beats, beats[1:]) if t1 > t0 and not overlaps(t0, t1)]
    beats_while_frozen = sum(1 for _, t in beats if any(f0 + .05 < t < f1 - .05 for f0, f1 in frozen))
    span = beats[-1][1] - beats[0][1] if len(beats) > 1 else 0
    frozen_in_span = sum(max(0, min(f1, beats[-1][1]) - max(f0, beats[0][1])) for f0, f1 in frozen) if beats else 0
    running = span - frozen_in_span
    result = {"run": run.name, "heartbeats": len(beats), "game_seconds": round(beats[-1][0] / 60, 1) if beats else 0,
              "wall_span_s": round(span, 1), "frozen_s": round(frozen_in_span, 1), "running_wall_s": round(running, 1),
              "freezes": len(frozen),
              "updates_per_running_second_overall": round((beats[-1][0] - beats[0][0]) / running, 2) if running > 0 else None,
              "hz_unfrozen_intervals": {"n": len(rates), "median": round(st.median(rates), 2) if rates else None,
                                        "mean": round(st.mean(rates), 2) if rates else None,
                                        "p05": round(sorted(rates)[len(rates) // 20], 2) if rates else None,
                                        "min": round(min(rates), 2) if rates else None},
              "heartbeats_while_frozen": beats_while_frozen, **screenshot_ages(run, frozen)}
    (run / "evidence").mkdir(exist_ok=True)
    (run / "evidence/clock.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def screenshot_ages(run, frozen):
    """Age of the newest screenshot when each agent input batch starts: wall seconds, and game seconds (the wall age
    minus the time the game was frozen in between; equal in real time). Batches = inputs > 0.5 s after the previous."""
    try:
        caps = sorted(p.stat().st_mtime for p in (run / "frames").glob("*.png"))
        receipts = [json.loads(line) for line in open(run / "inputs.jsonl")]
    except OSError:
        return {}
    firsts, prev = [], 0
    for r in receipts:
        if r.get("actor", "agent") == "agent" and r["started_unix"] - prev > .5:
            firsts.append(r["started_unix"])
        prev = r["ended_unix"]
    wall, game = [], []
    for s in firsts:
        shot = max((c for c in caps if c <= s), default=None)
        if shot is None:
            continue
        wall.append(s - shot)
        game.append(s - shot - sum(max(0, min(f1, s) - max(f0, shot)) for f0, f1 in frozen))
    return {"screenshot_age_wall_median_s": round(st.median(wall), 2) if wall else None,
            "screenshot_age_game_median_s": round(st.median(game), 2) if game else None}


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(json.dumps(check(path)), flush=True)
