"""Paused-clock robustness test: SIGSTOP/SIGCONT a running game many times at random phases (operator only).

    python tools/freeze_stress.py --fixture F --out D --display :11 --cycles 3000 [--env DOTNET_PROCESSOR_COUNT=2]

The game walks back and forth (XTEST) while being frozen for 30-200 ms after 30-150 ms of running, like the paused
clock but much more often. Reports cycles survived, whether the client logged "Main engine crash", and Hz while running.
"""
import argparse
import json
import os
import random
import shutil
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.linux_control import XGameControl, launch, stop_owned_game  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--display", required=True)
    p.add_argument("--cycles", type=int, default=3000)
    p.add_argument("--env", nargs="*", default=[])
    a = p.parse_args()
    root = a.out
    shutil.copytree(a.fixture, root / "tml", ignore=shutil.ignore_patterns("Logs", "*.log", "*.bak"))
    pid = launch(root / "tml", root / "client.log", root / "telemetry", skipselect=True, width=1024, height=1024,
                 display=a.display, config_updates={"UIScale": 0.9, "ResetDefaultUIScale": False, "Zoom": 1.0},
                 extra_env={"TERRARIABENCH_PROFILE": "reference-reconstructed-v1", "TERRARIABENCH_PVE": "enabled",
                            "TERRARIABENCH_HOSTILE_DAMAGE": "on", "TERRARIABENCH_REFERENCE_STARTER_PREFIXES": "plain",
                            "TERRARIABENCH_CHECKPOINT_CHAT": "disabled", **dict(e.split("=", 1) for e in a.env)})
    while not list((root / "telemetry").glob("*.jsonl")):
        time.sleep(.5)
    time.sleep(2)
    game = XGameControl(pid, None, display=a.display, width=1024, height=1024, max_hold_ms=2000)
    game.setup_window()
    stop = threading.Event()

    def walk():
        key = "d"
        while not stop.is_set():
            try:
                game.act([{"keys": [key], "ms": 600}])
            except Exception:
                return
            key = "a" if key == "d" else "d"

    walker = threading.Thread(target=walk, daemon=True)
    walker.start()
    survived, rng, crashed = 0, random.Random(7), False
    started = time.monotonic()
    for survived in range(1, a.cycles + 1):
        time.sleep(rng.uniform(.03, .15))
        os.killpg(pid, signal.SIGSTOP)
        time.sleep(rng.uniform(.03, .2))
        os.killpg(pid, signal.SIGCONT)
        if "Main engine crash" in (root / "client.log").read_text(errors="replace"):
            crashed = True
            break
    stop.set()
    time.sleep(1)
    crashed = crashed or "Main engine crash" in (root / "client.log").read_text(errors="replace")
    game.close()
    stop_owned_game(pid, root / "tml")
    tel = [json.loads(line) for f in sorted((root / "telemetry").glob("*.jsonl")) for line in open(f)]
    beats = [e for e in tel if e.get("event") == "heartbeat"]
    result = {"env": a.env, "cycles_survived": survived, "crashed": crashed, "minutes": round((time.monotonic() - started) / 60, 1),
              "game_seconds": beats[-1]["game_updates"] / 60 if beats else 0,
              "proc_count_in_log": [l for l in (root / "client.log").read_text(errors="replace").splitlines() if "Proc Count" in l][:1]}
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
