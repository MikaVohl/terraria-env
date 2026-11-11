"""Copy compact records of TerraBot runs (Omarchy run dirs) into experiments/results/<name>/<run>/.

    python tools/terrabot/export_records.py --dest experiments/results/programmatic-track-2026-11-10 runs/terrabot-proof-07 ...

Kept: manifest, result, audit, extended-score, live/pathfinder test results, api call counts, programs (outputs
truncated by the runner), agent turns, and gzipped journals (observer telemetry, TerraBot events/actions, proxy input
journal). Not kept: the game profile, screenshots and the video (they stay in the raw run directory).
"""
import argparse
import gzip
import json
from pathlib import Path
import shutil

PLAIN = ("manifest.json", "result.json", "audit.json", "extended-score.json", "live-tests.json", "path-live.json",
         "api_calls.json", "system_prompt.txt")
GZ = ("programs.jsonl", "turns.jsonl", "game_events.jsonl", "game_actions.jsonl", "inputs.jsonl", "session.log")


def export(run, dest):
    run = Path(run)
    out = Path(dest) / run.name
    out.mkdir(parents=True, exist_ok=True)
    for name in PLAIN:
        if (run / name).exists():
            shutil.copy2(run / name, out / name)
    for name in GZ:
        if (run / name).exists():
            with open(run / name, "rb") as src, gzip.open(out / (name + ".gz"), "wb") as dst:
                shutil.copyfileobj(src, dst)
    tele = sorted((run / "telemetry").glob("*.jsonl"))
    if tele:
        with gzip.open(out / "telemetry.jsonl.gz", "wb") as dst:
            for f in tele:
                dst.write(f.read_bytes())
    ws = run / "workspace"
    if ws.exists():
        for f in list(ws.glob("notes.md")) + list(ws.glob("lib/*.py")):
            target = out / "workspace" / f.relative_to(ws)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
    return {"run": run.name, "files": sorted(p.name for p in out.iterdir())}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dest", required=True)
    p.add_argument("runs", nargs="+")
    a = p.parse_args()
    for r in a.runs:
        print(json.dumps(export(r, a.dest)))
