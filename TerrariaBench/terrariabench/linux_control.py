"""Linux/Hyprland worker. Screenshot pixels in; real OS input events out.

No game memory, console commands, tile control or shell tools are exposed to models.
"""
import argparse
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import time

WIDTH, HEIGHT = 1280, 720
KEY_NAMES = tuple("abcdefghijklmnopqrstuvwxyz0123456789") + (
    "space", "esc", "enter", "backspace", "tab", "leftshift", "leftctrl",
    "up", "down", "left", "right", "minus",
)


def validate_actions(actions, *, width=WIDTH, height=HEIGHT, max_hold_ms=1000):
    if not isinstance(actions, list) or not 1 <= len(actions) <= 16:
        raise ValueError("actions must contain 1..16 primitive inputs")
    for action in actions:
        if not isinstance(action, dict) or set(action) - {"keys", "mouse", "x", "y", "ms"}:
            raise ValueError("unknown action fields")
        keys = action.get("keys", [])
        if (not isinstance(keys, list) or len(keys) > 5
                or any(type(k) is not str or k not in KEY_NAMES for k in keys)
                or len(set(keys)) != len(keys)):
            raise ValueError("invalid keys")
        if action.get("mouse") not in (None, "left", "right", "middle"):
            raise ValueError("invalid mouse button")
        if type(action.get("ms", 100)) is not int or not 20 <= action.get("ms", 100) <= max_hold_ms:
            raise ValueError(f"duration must be 20..{max_hold_ms} ms")
        if ("x" in action) != ("y" in action):
            raise ValueError("pointer needs x and y")
        for name, limit in (("x", width), ("y", height)):
            if name in action and (type(action[name]) is not int or not 0 <= action[name] < limit):
                raise ValueError("pointer outside screenshot")
    return actions


def desktop_environment():
    env = os.environ.copy()
    # Copy only graphical-session variables, never the Steam process's secrets.
    for pid in subprocess.check_output(["pgrep", "-x", "steam"], text=True).split()[:1]:
        for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
            key, _, value = item.partition(b"=")
            if key.decode(errors="replace") in (
                "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
                "DBUS_SESSION_BUS_ADDRESS", "HYPRLAND_INSTANCE_SIGNATURE",
            ):
                env[key.decode()] = value.decode()
    if not env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        instances = json.loads(subprocess.check_output(["hyprctl", "instances", "-j"], text=True))
        if len(instances) != 1:
            raise RuntimeError("expected exactly one Hyprland session")
        env["HYPRLAND_INSTANCE_SIGNATURE"] = instances[0]["instance"]
        env["WAYLAND_DISPLAY"] = instances[0]["wl_socket"]
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    return env


def launch(profile, log, telemetry, *, skipselect=False, width=WIDTH, height=HEIGHT, extra_env=None, config_updates=None):
    profile, log, telemetry = (Path(p).resolve() for p in (profile, log, telemetry))
    for p in (profile / "Mods", log.parent, telemetry):
        p.mkdir(parents=True, exist_ok=True)
    config_path = profile / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    config.update(Language="en-US", Fullscreen=False, WindowBorderless=False,
                  WindowMaximized=False, DisplayWidth=width, DisplayHeight=height,
                  AutoPause=False, CloudSavingDefault=False)
    if config_updates:
        config.update(config_updates)
    config_path.write_text(json.dumps(config, indent=2))
    (profile / "Mods/enabled.json").write_text(json.dumps(["TerrariaBenchObserver"]))
    env = desktop_environment()
    for credential_name in ("OPENROUTER_API_KEY", "OPENROUTER_MANAGEMENT_KEY"):
        env.pop(credential_name, None)
    env["TERRARIABENCH_TELEMETRY_DIR"] = str(telemetry)
    # Native Wayland avoids Xwayland's grabbed-pointer coordinate mismatch.
    env["SDL_VIDEODRIVER"] = "wayland"
    env["FNA_MOUSE_DISABLE_GLOBAL_ACCESS"] = "1"
    if extra_env:
        env.update(extra_env)
    tml = Path.home() / ".local/share/Steam/steamapps/common/tModLoader"
    args = ["bash", "LaunchUtils/ScriptCaller.sh", "-tmlsavedirectory", str(profile)]
    if skipselect:
        args += ["-skipselect"]
    with log.open("w") as stream:
        proc = subprocess.Popen(args, cwd=tml, env=env, stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    return proc.pid


def stop_owned_game(pid, profile, timeout=5):
    """Wait for our direct game child to finish before snapshotting its journal."""
    path=Path(f'/proc/{pid}/cmdline')
    if not path.exists():return {'already_exited':True}
    if str(Path(profile).resolve()).encode() not in path.read_bytes():
        raise RuntimeError('refuse to terminate a process outside this game profile')
    started=time.monotonic();stamp=time.time();forced=False
    os.killpg(pid,signal.SIGTERM)
    deadline=started+timeout
    while True:
        try:
            child,_=os.waitpid(pid,os.WNOHANG)
            if child==pid:break
        except ChildProcessError:
            if not path.exists():break
        if time.monotonic()>=deadline:
            # Only this owned process group; never Steam or another client.
            if path.exists() and str(Path(profile).resolve()).encode() in path.read_bytes():
                os.killpg(pid,signal.SIGKILL);forced=True
            try:os.waitpid(pid,0)
            except ChildProcessError:pass
            break
        time.sleep(.02)
    return {'termination_requested_unix':stamp,'forced':forced,'wait_seconds':time.monotonic()-started}


class GameControl:
    def __init__(self, pid, journal=None, *, width=WIDTH, height=HEIGHT, max_hold_ms=1000):
        from evdev import UInput, ecodes
        self.env = desktop_environment()
        self.pid, self.journal = int(pid), Path(journal) if journal else None
        self.width, self.height, self.max_hold_ms = width, height, max_hold_ms
        self.e = ecodes
        self.keymap = {k: getattr(ecodes, "KEY_" + k.upper()) for k in KEY_NAMES}
        self.buttons = {k: getattr(ecodes, "BTN_" + k.upper()) for k in ("left", "right", "middle")}
        self.device = UInput({ecodes.EV_KEY: list(self.keymap.values()) + list(self.buttons.values()),
                              ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y]},
                             name="TerrariaBench OS input")
        self.held = set()
        time.sleep(.5)  # Allow libinput/udev to register the new virtual device.

    def hypr(self, *args):
        return subprocess.check_output(["hyprctl", *args], env=self.env, text=True, timeout=5)

    def window(self):
        windows = [w for w in json.loads(self.hypr("-j", "clients"))
                   if w.get("pid") == self.pid and w.get("mapped")]
        if len(windows) != 1:
            raise RuntimeError("game window missing or ambiguous")
        return windows[0]

    def focus(self):
        window = self.window()
        self.hypr("dispatch", 'hl.dsp.focus({window=' + json.dumps("address:" + window["address"]) + '})')
        active = json.loads(self.hypr("-j", "activewindow"))
        if active.get("pid") != self.pid:
            raise RuntimeError("game did not receive focus")
        return window

    def setup_window(self):
        window = self.window()
        address = "address:" + window["address"]
        if not window.get("floating"):
            self.hypr("dispatch", 'hl.dsp.window.float({window=' + json.dumps(address) + ',action="set"})')
        self.hypr("dispatch", 'hl.dsp.window.resize({window=' + json.dumps(address) + f',x={self.width},y={self.height},relative=false}})')
        self.hypr("dispatch", 'hl.dsp.window.move({window=' + json.dumps(address) + ',x=30,y=70,relative=false})')
        self.focus()
        time.sleep(.3)
        return self.window()

    def capture(self, path):
        from PIL import Image
        window = self.focus()
        x, y = window["at"]
        w, h = window["size"]
        data = subprocess.check_output(["grim", "-s", "1", "-g", f"{x},{y} {w}x{h}", "-"],
                                       env=self.env, timeout=10)
        image = Image.open(io.BytesIO(data)).convert("RGB")
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height), Image.Resampling.LANCZOS)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return {"viewport": [self.width, self.height], "window": window, "path": str(path), "captured_unix": time.time()}

    def release(self):
        for code in list(self.held):
            self.device.write(self.e.EV_KEY, code, 0)
        self.device.syn()
        self.held.clear()

    def act(self, actions, actor="agent"):
        validate_actions(actions, width=self.width, height=self.height, max_hold_ms=self.max_hold_ms)
        receipts = []
        for action in actions:
            window = self.focus()
            if "x" in action:
                x, y = window["at"]
                w, h = window["size"]
                self.hypr("dispatch", f"hl.dsp.cursor.move({{x={x + round(action['x']*w/self.width)},y={y + round(action['y']*h/self.height)}}})")
                # A compositor warp alone doesn't send wl_pointer motion to SDL.
                # Dispatch a real, net-zero relative motion to deliver position.
                for delta in (1, -1):
                    self.device.write(self.e.EV_REL, self.e.REL_X, delta)
                    self.device.syn()
                    time.sleep(.035)
            codes = [self.keymap[k] for k in action.get("keys", [])]
            if action.get("mouse"):
                codes.append(self.buttons[action["mouse"]])
            started = time.time()
            try:
                for code in codes:
                    self.device.write(self.e.EV_KEY, code, 1)
                    self.held.add(code)
                self.device.syn()
                time.sleep(action.get("ms", 100) / 1000)
            finally:
                self.release()
            receipt = {"actor": actor, "action": action, "started_unix": started,
                       "ended_unix": time.time(), "game_pid": self.pid,
                       "window_address": window["address"], "dispatch": "linux_uinput"}
            if self.journal:
                with self.journal.open("a") as stream:
                    stream.write(json.dumps(receipt) + "\n")
            receipts.append(receipt)
        return receipts

    def type_text(self, text):
        # Operator fixture setup only. Not exposed to the model.
        if any(c.lower() not in "abcdefghijklmnopqrstuvwxyz0123456789 -" for c in text):
            raise ValueError("unsupported setup text")
        for c in text:
            keys = ["space" if c == " " else "minus" if c == "-" else c.lower()]
            if c.isupper():
                keys = ["leftshift"] + keys
            self.act([{"keys": keys, "ms": 25}], actor="operator_setup")
            time.sleep(.025)

    def close(self):
        self.release()
        self.device.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--setup-window", action="store_true")
    parser.add_argument("--actions", help="JSON primitive actions (operator only)")
    parser.add_argument("--text", help="Operator fixture setup text")
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args()
    game = GameControl(args.pid, args.journal)
    try:
        if args.setup_window:
            game.setup_window()
        if args.actions:
            game.act(json.loads(args.actions), actor="operator_setup")
        if args.text:
            game.type_text(args.text)
        if args.capture:
            print(json.dumps(game.capture(args.capture)))
    finally:
        game.close()


if __name__ == "__main__":
    main()
