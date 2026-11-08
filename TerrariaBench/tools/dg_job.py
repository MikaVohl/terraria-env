"""Write one default-v1 queue job (tools/parallel_queue.py) and print its path.

    python tools/dg_job.py NAME KIND MODEL REASONING CLOCK FIXTURE GAME_SECONDS CAP [settings flags...]

KIND: gateway | unified (single model, terrariabench run) or combo (Opus-class planner via the gateway + Jev executor
via OpenRouter; CAP is the planner cap, the Jev cap is fixed at 0.15). Settings flags (--zoom, --smart-cursor, ...)
are passed through unchanged; jobs without them use the frozen default-v1 settings given by --settings-file.
"""
import argparse
import json
import shlex
from pathlib import Path

CAMPAIGN = "runs/default-game-2026-11-08"
JEV_CAP = 0.15


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("name")
    p.add_argument("kind", choices=("gateway", "unified", "combo"))
    p.add_argument("model")
    p.add_argument("reasoning")
    p.add_argument("clock", choices=("realtime", "paused"))
    p.add_argument("fixture")
    p.add_argument("game_seconds", type=int)
    p.add_argument("cap", type=float)
    p.add_argument("--jobs", type=Path, default=Path.home() / "tb-queue/dg-jobs")
    p.add_argument("--settings-file", type=Path, default=None, help="JSON list of frozen setting flags")
    a, extra = p.parse_known_args()
    settings = extra or (json.loads(a.settings_file.read_text()) if a.settings_file else [])
    out = f"{CAMPAIGN}/{a.name}"
    common = (f"--fixture runs/fixtures/{a.fixture} --output {out} --profile default-v1 --clock {a.clock} "
              f"--game-seconds {a.game_seconds} --display \"$TB_DISPLAY\" " + " ".join(shlex.quote(s) for s in settings))
    if a.kind == "combo":
        # Paused: wall time includes every frozen model call, so the wall safety cap is generous.
        cap_line = f"# cap gateway={a.cap} openrouter={JEV_CAP}"
        command = (f".venv/bin/python -u -m terrariabench.combo {common} --planner {a.model} --planner-reasoning {a.reasoning} "
                   f"--executor jev --jev-frames 1 --ui-session --seconds {a.game_seconds * 9 if a.clock == 'paused' else a.game_seconds + 600} "
                   f"--usd-planner {a.cap} --usd-executor {JEV_CAP} --campaign-profile default-v1-combo")
    else:
        cap_line = f"# cap gateway={a.cap}"
        reserve = " --reserve-output-tokens 16384" if a.kind == "gateway" else ""
        command = (f".venv/bin/python -u -m terrariabench run {common} --provider {a.kind} --model {a.model} "
                   f"--reasoning {a.reasoning} --mode calibration --seconds {a.game_seconds + 600} --calls 4096 --usd {a.cap}"
                   f"{reserve} --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 "
                   f"--campaign-profile default-v1")
    a.jobs.mkdir(parents=True, exist_ok=True)
    job = a.jobs / f"{a.name}.sh"
    window = settings[settings.index("--window") + 1] if "--window" in settings else "1024x1024"
    job.write_text(f"{cap_line}\n# run {out}\n# window {window}\n# {a.name}: {a.kind} {a.model} ({a.reasoning}), {a.clock}, "
                   f"{a.fixture}, {a.game_seconds} game-s\n{command}\n")
    print(job)


if __name__ == "__main__":
    main()
