"""Open the live panel in a floating terminal beside the game window (x 1080..2280).

A new window takes keyboard focus, so this waits until no TerrariaBench game is running:
the next run's setup focuses its own window before any agent input. Read-only viewer.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.linux_control import desktop_environment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TITLE = "TerrariaBench live"


def hypr(env, *args):
    return subprocess.check_output(["hyprctl", *args], env=env, text=True, timeout=5)


def main():
    env = desktop_environment()
    clients = json.loads(hypr(env, "-j", "clients"))
    if any(c.get("title") == TITLE for c in clients):
        print("live panel already open")
        return
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
    address = json.dumps("address:" + window["address"])
    if not window.get("floating"):
        hypr(env, "dispatch", "hl.dsp.window.float({window=" + address + ',action="set"})')
    hypr(env, "dispatch", "hl.dsp.window.resize({window=" + address + ",x=1200,y=1024,relative=false})")
    hypr(env, "dispatch", "hl.dsp.window.move({window=" + address + ",x=1080,y=70,relative=false})")
    print(json.dumps({"panel_pid": proc.pid, "window": window["address"]}))


if __name__ == "__main__":
    main()
