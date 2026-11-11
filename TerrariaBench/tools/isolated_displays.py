"""Isolated game displays for parallel runs: one headless Hyprland output + one rootful Xwayland server each.

    python tools/isolated_displays.py up 4      # displays :11..:14 on new outputs + sinks; writes ~/tb-queue/displays.json
    python tools/isolated_displays.py down      # stops those Xwayland servers, removes the outputs and sinks

Each game runs as the only X client of its display (launch(display=...)); XGameControl injects input with that
server's XTEST and reads screenshots from it, so instances share neither focus nor input. The headless output keeps
each Xwayland window visible (frame callbacks at 60 Hz). Each display also gets its own null audio sink tb_game_NN
(linux_control.ensure_game_sink): the game plays there, and tools/record_desktop.py --display records the display's
game window plus that sink's monitor.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.linux_control import desktop_environment, ensure_game_sink, remove_game_sink  # noqa: E402

STATE_DIR = Path.home() / "tb-queue"


def hypr(env, *args):
    return subprocess.check_output(["hyprctl", *args], env=env, text=True, timeout=10)


def up(n, first=11, geometry="1024x1024", name="displays"):
    state = STATE_DIR / f"{name}.json"
    if state.exists():
        raise SystemExit(f"{state} exists; run down first")
    w, h = (int(v) for v in geometry.split("x"))
    env = desktop_environment()
    before = {m["name"] for m in json.loads(hypr(env, "-j", "monitors"))}
    displays = []
    for i in range(n):
        hypr(env, "output", "create", "headless")
        time.sleep(1)
        monitors = json.loads(hypr(env, "-j", "monitors"))
        new = [m for m in monitors if m["name"] not in before and m["name"] not in {d["output"] for d in displays}]
        if len(new) != 1:
            raise RuntimeError("could not identify the new headless output")
        m = new[0]
        hypr(env, "eval", f'hl.monitor({{output="{m["name"]}", mode="{w + 76}x{h + 76}@60", '
                          f'position="{4000 + 1500 * (first - 11 + i)}x0", scale=1}})')
        time.sleep(1)
        m = next(x for x in json.loads(hypr(env, "-j", "monitors")) if x["name"] == m["name"])
        display = f":{first + i}"
        proc = subprocess.Popen(["Xwayland", display, "-geometry", geometry, "-noreset"], env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        window = None
        for _ in range(50):
            time.sleep(.2)
            window = next((c for c in json.loads(hypr(env, "-j", "clients")) if c["pid"] == proc.pid), None)
            if window:
                break
        if not window:
            raise RuntimeError(f"Xwayland {display} window did not appear")
        address = "address:" + window["address"]
        hypr(env, "dispatch", f'hl.dsp.window.move({{window="{address}",workspace="{m["activeWorkspace"]["id"]}",follow=false}})')
        hypr(env, "dispatch", f'hl.dsp.window.float({{window="{address}",action="set"}})')
        hypr(env, "dispatch", f'hl.dsp.window.resize({{window="{address}",x={w},y={h},relative=false}})')
        hypr(env, "dispatch", f'hl.dsp.window.move({{window="{address}",x={m["x"] + 20},y={m["y"] + 20},relative=false}})')
        displays.append({"display": display, "xwayland_pid": proc.pid, "output": m["name"], "window": window["address"],
                         "geometry": geometry, "audio_sink": ensure_game_sink(display, env)})
    state.write_text(json.dumps(displays, indent=2) + "\n")
    print(json.dumps(displays, indent=2))


def down(name="displays"):
    state = STATE_DIR / f"{name}.json"
    env = desktop_environment()
    displays = json.loads(state.read_text())
    for d in displays:
        cmdline = Path(f"/proc/{d['xwayland_pid']}/cmdline")
        if cmdline.exists() and cmdline.read_bytes().startswith(b"Xwayland\0" + d["display"].encode()):
            subprocess.run(["kill", str(d["xwayland_pid"])])
        hypr(env, "output", "remove", d["output"])
        remove_game_sink(d["display"], env)
    state.unlink()
    print(f"removed {len(displays)} isolated displays")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=("up", "down"))
    p.add_argument("n", type=int, nargs="?", default=4)
    p.add_argument("--first", type=int, default=11)
    p.add_argument("--geometry", default="1024x1024")
    p.add_argument("--name", default="displays", help="state file ~/tb-queue/<name>.json")
    a = p.parse_args()
    up(a.n, a.first, a.geometry, a.name) if a.action == "up" else down(a.name)
