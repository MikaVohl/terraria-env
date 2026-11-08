"""Unpaid operator check for interface card v3: does Left Ctrl through the controller toggle Smart Cursor,
and does a smart pickaxe dig below the player with the mouse held off-tile?

    python tools/validate_smart_cursor.py --fixture runs/fixtures/<fixture> --output runs/<campaign>/validate-smart-cursor-01

Same launch settings as reference_live (PvE off). Saves before/after frames and the telemetry; no model calls.
Inputs are journaled with actor "operator", so no milestone can be credited to an agent.
"""
import argparse
import json
import shutil
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.linux_control import GameControl, launch, stop_owned_game  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True)
    profile = json.loads((ROOT / "configs/reference-reconstructed.json").read_text())
    shutil.copytree(args.fixture, out / "tml", ignore=shutil.ignore_patterns("Logs", "*.log", "*.bak"))
    pid = launch(out / "tml", out / "client.log", out / "telemetry", skipselect=True, width=1024, height=1024,
                 config_updates={"UIScale": profile["environment"]["ui_scale"], "ResetDefaultUIScale": False, "Zoom": 1.0},
                 extra_env={"TERRARIABENCH_PROFILE": profile["profile_id"], "TERRARIABENCH_PVE": "disabled",
                            "TERRARIABENCH_REFERENCE_STARTER_PREFIXES": "plain", "TERRARIABENCH_CHECKPOINT_CHAT": "enabled"})
    (out / "game.json").write_text(json.dumps({"pid": pid, "profile": str(out / "tml")}))
    game = None
    try:
        deadline = time.monotonic() + 100
        while not list((out / "telemetry").glob("*.jsonl")):
            if time.monotonic() > deadline:
                raise RuntimeError("startup failed")
            time.sleep(.5)
        game = GameControl(pid, out / "inputs.jsonl", width=1024, height=1024, max_hold_ms=2000)
        game.setup_window()
        time.sleep(2)
        game.capture(out / "0-start.png")
        # Pickaxe, mouse 3 tiles right and 3 below the player: dumb cursor mines nothing reachable there.
        game.act([{"keys": ["2"], "ms": 60}, {"x": 560, "y": 600, "ms": 200}], actor="operator")
        game.act([{"x": 560, "y": 600, "mouse": "left", "ms": 1500}], actor="operator")
        game.capture(out / "1-dumb-dig.png")
        game.act([{"keys": ["leftctrl"], "ms": 80}, {"x": 560, "y": 600, "ms": 300}], actor="operator")
        game.capture(out / "2-smart-on.png")
        game.act([{"x": 560, "y": 600, "mouse": "left", "ms": 2000}, {"x": 560, "y": 600, "mouse": "left", "ms": 2000}],
                 actor="operator")
        game.capture(out / "3-smart-dig.png")
    finally:
        if game:
            game.close()
        (out / "termination.json").write_text(json.dumps(stop_owned_game(pid, out / "tml")))
        beats = [json.loads(l) for f in (out / "telemetry").glob("*.jsonl") for l in open(f) if '"heartbeat"' in l]
        inv = [{i["name"]: i["stack"] for i in b["inventory"]} for b in (beats[0], beats[-1])] if beats else None
        (out / "result.json").write_text(json.dumps({"validation": "smart_cursor", "inventory_first_last": inv}, indent=1))
        print(json.dumps(inv))


if __name__ == "__main__":
    main()
