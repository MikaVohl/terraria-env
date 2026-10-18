"""Open the live panel in a floating terminal in the space right of the game window.

Layout comes from linux_control: the game sits at the top-left of the usable display area
and the panel fills the remainder. A new window takes keyboard focus, so opening waits until
no TerrariaBench game is running. --relayout only moves/resizes an existing panel (no focus
change), e.g. after the display resolution changes. Read-only viewer.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.linux_control import desktop_environment, panel_rect  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TITLE = "TerrariaBench live"
GAME_SIZE = 1024


def hypr(env, *args):
    return subprocess.check_output(["hyprctl", *args], env=env, text=True, timeout=5)


def place(env, window):
    address = json.dumps("address:" + window["address"])
    if not window.get("floating"):
        hypr(env, "dispatch", "hl.dsp.window.float({window=" + address + ',action="set"})')
    x, y, w, h = panel_rect(env, GAME_SIZE, GAME_SIZE)
    hypr(env, "dispatch", "hl.dsp.window.resize({window=" + address + f",x={w},y={h},relative=false}})")
    hypr(env, "dispatch", "hl.dsp.window.move({window=" + address + f",x={x},y={y},relative=false}})")
    return x, y, w, h


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--relayout", action="store_true", help="only reposition an existing panel")
    args = p.parse_args()
    env = desktop_environment()
    existing = next((c for c in json.loads(hypr(env, "-j", "clients")) if c.get("title") == TITLE), None)
    if existing:
        print(json.dumps({"relayout": place(env, existing)}))
        return
    if args.relayout:
        raise SystemExit("no live panel window to relayout")
    while any(c.get("class") == "dotnet" for c in json.loads(hypr(env, "-j", "clients"))):
        time.sleep(.5)  # never steal focus from an agent mid-run
    proc = subprocess.Popen(["foot", "--title", TITLE, "-o", "font=Noto Sans Mono:size=10", "-o", "colors.alpha=0.92",
                             str(ROOT / ".venv/bin/python"), str(ROOT / "tools/live_panel.py")],
                            env=env, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 10
    while True:
        window = next((c for c in json.loads(hypr(env, "-j", "clients")) if c.get("pid") == proc.pid and c.get("mapped")), None)
        if window or time.monotonic() > deadline:
            break
        time.sleep(.1)
    if not window:
        raise SystemExit("live panel window did not appear")
    print(json.dumps({"panel_pid": proc.pid, "window": window["address"], "rect": place(env, window)}))


if __name__ == "__main__":
    main()
