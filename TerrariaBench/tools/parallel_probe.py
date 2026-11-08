"""Unpaid parallel-instance probe: N games at once, each the only client of its own rootful Xwayland display.

    python tools/parallel_probe.py --fixture runs/fixtures/default-v07-32000401 --out runs/parallel-probe/<name> \
        --displays :11 :12 [--seconds 120]

Instance i walks right if i is even and left if odd (1 s holds, a screenshot after each, like the harness),
so input crosstalk would show up as the wrong direction or no net movement. Reports per instance: game
updates per wall second (observer heartbeats), net horizontal movement in tiles, screenshots taken, and the
host load. Operator-only: no model calls.
"""
import argparse
import json
import os
import shutil
import statistics as st
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.linux_control import XGameControl, launch, stop_owned_game  # noqa: E402


def instance(i, display, fixture, out, seconds, results):
    root = out / f"instance-{i}"
    shutil.copytree(fixture, root / "tml", ignore=shutil.ignore_patterns("Logs", "*.log", "*.bak"))
    pid = launch(root / "tml", root / "client.log", root / "telemetry", skipselect=True, width=1024, height=1024,
                 config_updates={"UIScale": 0.9, "ResetDefaultUIScale": False, "Zoom": 1.0}, display=display,
                 extra_env={"TERRARIABENCH_PROFILE": "reference-reconstructed-v1", "TERRARIABENCH_PVE": "enabled",
                            "TERRARIABENCH_HOSTILE_DAMAGE": "on", "TERRARIABENCH_REFERENCE_STARTER_PREFIXES": "plain",
                            "TERRARIABENCH_CHECKPOINT_CHAT": "disabled"})
    game, shots, error = None, 0, None
    try:
        deadline = time.monotonic() + 150
        while not list((root / "telemetry").glob("*.jsonl")):
            if time.monotonic() > deadline or not Path(f"/proc/{pid}").exists():
                raise RuntimeError("startup failed")
            time.sleep(.5)
        time.sleep(2)
        game = XGameControl(pid, root / "inputs.jsonl", display=display, width=1024, height=1024, max_hold_ms=2000)
        game.setup_window()
        key = "d" if i % 2 == 0 else "a"
        results[i] = {"started_unix": time.time()}
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            game.act([{"keys": [key], "ms": 1000}])
            game.capture(root / "frames" / f"{shots:05d}.png")
            shots += 1
    except Exception as e:  # report, never hide
        error = f"{type(e).__name__}: {e}"
    finally:
        if game:
            game.close()
        stop_owned_game(pid, root / "tml")
    tel = [json.loads(line) for f in sorted((root / "telemetry").glob("*.jsonl")) for line in open(f)]
    beats = [e for e in tel if e.get("event") == "heartbeat"]
    t0 = results.get(i, {}).get("started_unix", 0)
    beats = [e for e in beats if e["unix_seconds"] >= t0]
    rates = [60 / (b["unix_seconds"] - a["unix_seconds"]) for a, b in zip(beats, beats[1:])]
    results[i] = {"display": display, "direction": "right" if i % 2 == 0 else "left", "error": error, "screenshots": shots,
                  "heartbeats": len(beats),
                  "hz_median": round(st.median(rates), 2) if rates else None,
                  "hz_mean": round(st.mean(rates), 2) if rates else None,
                  "hz_p05": round(sorted(rates)[len(rates) // 20], 2) if rates else None,
                  "hz_min": round(min(rates), 2) if rates else None,
                  "overall_updates_per_s": round((beats[-1]["game_updates"] - beats[0]["game_updates"]) /
                                                 (beats[-1]["unix_seconds"] - beats[0]["unix_seconds"]), 2) if len(beats) > 1 else None,
                  "net_dx_tiles": round((beats[-1]["position"][0] - beats[0]["position"][0]) / 16) if beats else None}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--displays", nargs="+", required=True)
    p.add_argument("--seconds", type=int, default=120)
    a = p.parse_args()
    a.out.mkdir(parents=True)
    results, load = {}, []
    threads = [threading.Thread(target=instance, args=(i, d, a.fixture.resolve(), a.out.resolve(), a.seconds, results))
               for i, d in enumerate(a.displays)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        load.append(os.getloadavg()[0])
        time.sleep(5)
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    summary = {"instances": [results[i] for i in sorted(results)], "loadavg_1m_max": max(load) if load else None,
               "loadavg_1m_median": st.median(load) if load else None, "cpu_count": os.cpu_count(), "gpu_after": gpu}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
