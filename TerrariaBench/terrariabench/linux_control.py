"""Linux/Hyprland worker. Screenshot pixels in; real OS input events out.

No game memory, console commands, tile control or shell tools are exposed to models.
"""
import argparse
import io
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import threading
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


GAME_SINK_PREFIX, DESKTOP_SINK = "tb_game_", "tb_desktop"


def game_sink(display):
    """PulseAudio/PipeWire sink name of an isolated display's game, e.g. ":11" -> "tb_game_11"."""
    return GAME_SINK_PREFIX + display.lstrip(":").replace(".", "_")


def _pactl(env, *args):
    return subprocess.check_output(["pactl", *args], env=env, text=True, timeout=10)


def _sinks(env):
    return {line.split("\t")[1] for line in _pactl(env, "list", "short", "sinks").splitlines() if "\t" in line}


def ensure_game_sink(display, env=None):
    """Create the display's null sink once (idempotent, serialised by a lock file) and return its name.

    Each isolated game plays into its own null sink: nothing reaches the desktop's speakers and the recorder
    takes that sink's monitor, so parallel instances never hear each other. Omarchy has no audio hardware, so
    WirePlumber would make the first game sink the desktop default and route every other stream into that game's
    recording; a separate null sink tb_desktop then takes the default."""
    import fcntl
    env = env or desktop_environment()
    sink = game_sink(display)
    with open(Path(env["XDG_RUNTIME_DIR"]) / "terrariabench-sinks.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        sinks = _sinks(env)
        for name in (DESKTOP_SINK, sink):
            if name not in sinks:
                _pactl(env, "load-module", "module-null-sink", f"sink_name={name}",
                       f"sink_properties=device.description=TerrariaBench-{name}")
        if _pactl(env, "get-default-sink").strip().startswith(GAME_SINK_PREFIX):
            _pactl(env, "set-default-sink", DESKTOP_SINK)
    return sink


def remove_game_sink(display, env=None):
    """Unload the display's sink; the last one also takes tb_desktop with it (the desktop default falls back)."""
    env = env or desktop_environment()
    modules = _pactl(env, "list", "short", "modules").splitlines()
    remaining = {s for s in _sinks(env) if s.startswith(GAME_SINK_PREFIX)} - {game_sink(display)}
    for name in (game_sink(display),) + (() if remaining else (DESKTOP_SINK,)):
        for line in modules:
            if "module-null-sink" in line and f"sink_name={name}" in line.split():
                _pactl(env, "unload-module", line.split("\t")[0])


def isolated_audio_env(display, env=None):
    """Environment routing an isolated game's audio to its own sink. tModLoader's bundled SDL2 2.28 (FNA/FAudio) already
    picks its PulseAudio backend (pipewire-pulse), which honours PULSE_SINK; SDL_AUDIODRIVER pins that choice because its
    PipeWire backend would ignore PULSE_SINK."""
    return {"SDL_AUDIODRIVER": "pulseaudio", "PULSE_SINK": ensure_game_sink(display, env)}


LAYOUT_MARGIN = 10


def monitor_area(env):
    """Usable logical rectangle (x, y, w, h) of the focused monitor, excluding reserved bars."""
    monitors = json.loads(subprocess.check_output(["hyprctl", "-j", "monitors"], env=env, text=True, timeout=5))
    m = next((m for m in monitors if m.get("focused")), monitors[0])
    left, top, right, bottom = m.get("reserved", [0, 0, 0, 0])
    w, h = round(m["width"] / m["scale"]), round(m["height"] / m["scale"])
    return m["x"] + left, m["y"] + top, w - left - right, h - top - bottom


def game_rect(env, width, height):
    """Top-left placement for the game window; refuses displays where it would not be fully visible."""
    x, y, w, h = monitor_area(env)
    if width + 2 * LAYOUT_MARGIN > w or height + 2 * LAYOUT_MARGIN > h:
        raise RuntimeError(f"display_too_small: {width}x{height} game needs a {width + 2 * LAYOUT_MARGIN}x"
                           f"{height + 2 * LAYOUT_MARGIN} logical area, display offers {w}x{h}")
    return x + LAYOUT_MARGIN, y + LAYOUT_MARGIN, width, height


def panel_rect(env, game_width, game_height):
    """The space right of the game window, for the live panel."""
    gx, gy, _, _ = game_rect(env, game_width, game_height)
    x, y, w, h = monitor_area(env)
    px = gx + game_width + LAYOUT_MARGIN
    return px, gy, x + w - LAYOUT_MARGIN - px, y + h - LAYOUT_MARGIN - gy


def launch(profile, log, telemetry, *, skipselect=False, width=WIDTH, height=HEIGHT, extra_env=None, config_updates=None,
           display=None):
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
    if display:
        # Isolated instance: the game is the only client of its own rootful Xwayland server (see XGameControl).
        env.pop("WAYLAND_DISPLAY", None)
        env["DISPLAY"], env["SDL_VIDEODRIVER"] = display, "x11"
        env.update(isolated_audio_env(display, env))
    else:
        # Native Wayland avoids Xwayland's grabbed-pointer coordinate mismatch.
        env["SDL_VIDEODRIVER"] = "wayland"
    env["FNA_MOUSE_DISABLE_GLOBAL_ACCESS"] = "1"
    # The paused clock SIGSTOPs the game at arbitrary points. tModLoader's FastParallel.For (multi-threaded lighting)
    # times its worker countdown with a wall-clock stopwatch and throws "Fatal Deadlock in FastParallelFor" when a
    # freeze lands inside it (3 paused-run crashes on 2026-11-08). One reported processor makes it run every range
    # on the calling thread; game logic and rules are unchanged.
    env["DOTNET_PROCESSOR_COUNT"] = "1"
    if extra_env:
        env.update(extra_env)
    tml = Path.home() / ".local/share/Steam/steamapps/common/tModLoader"
    args = ["bash", "LaunchUtils/ScriptCaller.sh", "-tmlsavedirectory", str(profile)]
    if skipselect:
        args += ["-skipselect"]
    quiet_desktop()
    with log.open("w") as stream:
        # No core dumps: tModLoader often segfaults/aborts during teardown (94 dotnet dumps of ~125 MB on
        # 2026-11-08), and each dump made omarchy-crash-watch raise a DND-bypassing toast that appeared in recordings.
        proc = subprocess.Popen(args, cwd=tml, env=env, stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
                                preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
    return proc.pid


def quiet_desktop():
    """Keep desktop notifications out of game screenshots/recordings: turn on the Omarchy shell's do-not-disturb mode
    and dismiss visible popups. Best effort and idempotent (other desktops simply lack omarchy-shell); restore with
    `omarchy-shell notifications setDnd false`."""
    env = {**desktop_environment(), "OMARCHY_PATH": os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")}
    for cmd in (["omarchy-shell", "-q", "notifications", "setDnd", "true"],
                ["omarchy-shell", "-q", "notifications", "dismissAll"]):
        try:
            subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass


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
        # Off-display pixels can be neither captured nor clicked: never act on a partly hidden window.
        x, y, w, h = monitor_area(self.env)
        (wx, wy), (ww, wh) = window["at"], window["size"]
        if wx < x or wy < y or wx + ww > x + w or wy + wh > y + h:
            raise RuntimeError(f"game_window_off_display: window {wx},{wy} {ww}x{wh}, display area {x},{y} {w}x{h}")
        return window

    def setup_window(self):
        window = self.window()
        address = "address:" + window["address"]
        if not window.get("floating"):
            self.hypr("dispatch", 'hl.dsp.window.float({window=' + json.dumps(address) + ',action="set"})')
        self.hypr("dispatch", 'hl.dsp.window.resize({window=' + json.dumps(address) + f',x={self.width},y={self.height},relative=false}})')
        x, y, _, _ = game_rect(self.env, self.width, self.height)
        self.hypr("dispatch", 'hl.dsp.window.move({window=' + json.dumps(address) + f',x={x},y={y},relative=false}})')
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


X_KEYSYMS = {"space": "space", "esc": "Escape", "enter": "Return", "backspace": "BackSpace", "tab": "Tab",
             "leftshift": "Shift_L", "leftctrl": "Control_L", "up": "Up", "down": "Down", "left": "Left",
             "right": "Right", "minus": "minus"}
X_BUTTONS = {"left": 1, "middle": 2, "right": 3}


class XGameControl:
    """Same contract as GameControl for a game that is the only client of its own rootful Xwayland server.

    Input goes through that server's XTEST extension and screenshots come from that server, so several
    instances on one desktop neither share keyboard/pointer focus nor see each other's input."""

    def __init__(self, pid, journal=None, *, display, width=WIDTH, height=HEIGHT, max_hold_ms=1000):
        from Xlib import X, XK, display as xdisplay
        from Xlib.ext import xtest
        self.X, self.xtest = X, xtest
        self.pid, self.journal = int(pid), Path(journal) if journal else None
        self.width, self.height, self.max_hold_ms = width, height, max_hold_ms
        self.display_name = display
        self.d = xdisplay.Display(display)
        if not self.d.has_extension("XTEST"):
            raise RuntimeError("isolated display lacks XTEST")
        self.root = self.d.screen().root
        self.keymap = {k: self.d.keysym_to_keycode(XK.string_to_keysym(X_KEYSYMS.get(k, k))) for k in KEY_NAMES}
        if not all(self.keymap.values()):
            raise RuntimeError("isolated display keymap lacks a benchmark key")
        self.held, self.win = set(), None
        # python-xlib connections are not thread-safe (the combo planner captures while the executor acts).
        self.lock = threading.RLock()

    def window(self):
        windows = []
        for w in self.root.query_tree().children:
            attrs, geo = w.get_attributes(), w.get_geometry()
            if attrs.map_state == self.X.IsViewable and geo.width >= self.width // 2:
                windows.append((w, geo))
        if len(windows) != 1:
            raise RuntimeError("game window missing or ambiguous on the isolated display")
        w, geo = windows[0]
        at = w.translate_coords(self.root, 0, 0)
        return w, (-at.x, -at.y), (geo.width, geo.height)

    def setup_window(self):
        with self.lock:
            w, at, size = self.window()
            if size != (self.width, self.height) or at != (0, 0):
                w.configure(x=0, y=0, width=self.width, height=self.height)
                self.d.sync()
                time.sleep(.5)
            self.focus()
            return self.window()

    def focus(self):
        with self.lock:
            w, at, size = self.window()
            if size != (self.width, self.height) or at != (0, 0):
                raise RuntimeError(f"game window not at 0,0 {self.width}x{self.height}: {at} {size}")
            self.d.set_input_focus(w, self.X.RevertToParent, self.X.CurrentTime)
            self.d.sync()
            self.win = w
            return w

    def capture(self, path):
        from PIL import Image
        with self.lock:
            self.focus()
            raw = self.root.get_image(0, 0, self.width, self.height, self.X.ZPixmap, 0xffffffff)
        image = Image.frombytes("RGB", (self.width, self.height), raw.data, "raw", "BGRX")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return {"viewport": [self.width, self.height], "display": self.display_name, "path": str(path),
                "captured_unix": time.time()}

    def _send(self, kind, detail=0, **kw):
        self.xtest.fake_input(self.d, kind, detail, **kw)

    def release(self):
        with self.lock:
            for kind, code in list(self.held):
                self._send(self.X.ButtonRelease if kind == "button" else self.X.KeyRelease, code)
            self.d.sync()
            self.held.clear()

    def act(self, actions, actor="agent"):
        validate_actions(actions, width=self.width, height=self.height, max_hold_ms=self.max_hold_ms)
        receipts = []
        for action in actions:
            with self.lock:
                self.focus()
                if "x" in action:
                    # Absolute XTEST motion reaches SDL only with the root window given explicitly.
                    self._send(self.X.MotionNotify, x=action["x"], y=action["y"], root=self.root)
                    self.d.sync()
            if "x" in action:
                time.sleep(.035)
            started = time.time()
            try:
                with self.lock:
                    for k in action.get("keys", []):
                        self._send(self.X.KeyPress, self.keymap[k])
                        self.held.add(("key", self.keymap[k]))
                    if action.get("mouse"):
                        self._send(self.X.ButtonPress, X_BUTTONS[action["mouse"]])
                        self.held.add(("button", X_BUTTONS[action["mouse"]]))
                    self.d.sync()
                time.sleep(action.get("ms", 100) / 1000)
            finally:
                self.release()
            receipt = {"actor": actor, "action": action, "started_unix": started, "ended_unix": time.time(),
                       "game_pid": self.pid, "display": self.display_name, "dispatch": "xtest_isolated_xwayland"}
            if self.journal:
                with self.journal.open("a") as stream:
                    stream.write(json.dumps(receipt) + "\n")
            receipts.append(receipt)
        return receipts

    def close(self):
        with self.lock:
            self.release()
            self.d.close()


def control(pid, journal=None, *, display=None, **kw):
    """The game's input/screenshot controller: the shared desktop (uinput, grim) or an isolated Xwayland display."""
    return XGameControl(pid, journal, display=display, **kw) if display else GameControl(pid, journal, **kw)


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
