"""v10 transfer PoC, Omarchy side: one game on its own isolated Xwayland display, driven in lockstep.

    .venv/bin/python tools/v10_transfer/game_server.py --fixture runs/fixtures/default-v07-32000401 \
        --output runs/v10-poc/<run> --display :21

Protocol (JSON lines): stdin gets one command per step {"seq", "ticks", "ops", "input"} (see PocBridge.cs);
stdout answers with the game state after the step (written by the 0.8-poc observer while the game thread waits).
One JPEG frame per step goes to <output>/frames (the game-time-only video). {"quit": true} ends the run.
"""
import argparse
import contextlib
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from terrariabench.linux_control import launch, stop_owned_game, XGameControl  # noqa: E402
import isolated_displays  # noqa: E402

TMOD = ROOT / "runs/v10-poc-build/tml/Mods/TerrariaBenchObserver.tmod"
SIZE = 1024


def read_state(path, seq, deadline):
    while time.monotonic() < deadline:
        try:
            state = json.loads(path.read_text())
            if state["seq"] == seq:
                return state
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(.002)
    raise TimeoutError(f"no state for seq {seq}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--display", default=":21")
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True)
    shutil.copytree(a.fixture.resolve(), out / "tml", ignore=shutil.ignore_patterns("Logs", "*.log", "*.bak"))
    shutil.copy2(TMOD, out / "tml/Mods/TerrariaBenchObserver.tmod")
    poc = out / "poc"
    poc.mkdir()
    (out / "frames").mkdir()
    first = int(a.display.lstrip(":"))
    with contextlib.redirect_stdout(sys.stderr):  # stdout is the protocol channel
        isolated_displays.up(1, first=first, geometry=f"{SIZE}x{SIZE}", name="v10poc")
    pid = game = None
    log = lambda *x: print(*x, file=sys.stderr, flush=True)  # noqa: E731
    try:
        pid = launch(out / "tml", out / "client.log", out / "telemetry", skipselect=True, width=SIZE, height=SIZE,
                     display=a.display,
                     config_updates={"Zoom": 1.0, "UIScale": .9, "ResetDefaultUIScale": False, "LightingMode": 3},
                     extra_env={"TERRARIABENCH_PROFILE": "reference-reconstructed-v1", "TERRARIABENCH_PVE": "enabled",
                                "TERRARIABENCH_HOSTILE_DAMAGE": "on", "TERRARIABENCH_REFERENCE_STARTER_PREFIXES": "plain",
                                "TERRARIABENCH_CHECKPOINT_CHAT": "disabled", "TERRARIABENCH_POC_DIR": str(poc)})
        (out / "game.json").write_text(json.dumps({"pid": pid, "display": a.display}))
        log(f"game pid {pid} on {a.display}")
        state = read_state(poc / "state.json", -1, time.monotonic() + 180)
        game = XGameControl(pid, display=a.display, width=SIZE, height=SIZE)
        game.setup_window()
        print(json.dumps(state), flush=True)
        for line in sys.stdin:
            cmd = json.loads(line)
            if cmd.get("quit"):
                break
            tmp = poc / "cmd.json.tmp"
            tmp.write_text(json.dumps(cmd))
            tmp.rename(poc / "cmd.json")
            state = read_state(poc / "state.json", cmd["seq"], time.monotonic() + 60)
            if cmd.get("frame", True):
                from PIL import Image
                with game.lock:
                    raw = game.root.get_image(0, 0, SIZE, SIZE, game.X.ZPixmap, 0xffffffff)
                Image.frombytes("RGB", (SIZE, SIZE), raw.data, "raw", "BGRX").save(
                    out / "frames" / f"{cmd['seq']:05d}.jpg", quality=85)
            print(json.dumps(state), flush=True)
    finally:
        (poc / "release").touch()
        time.sleep(2)
        if game:
            game.close()
        if pid:
            stop_owned_game(pid, out / "tml")
        with contextlib.redirect_stdout(sys.stderr):
            isolated_displays.down(name="v10poc")
        log("stopped game and display")


if __name__ == "__main__":
    main()
