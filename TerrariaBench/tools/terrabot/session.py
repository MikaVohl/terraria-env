"""One TerraBot game session on Omarchy: an isolated game instance with the TerraBot mod, the API proxy that agent
programs talk to, the desktop recorder, and the run records.

    run/
      tml/                 copy of the world fixture + TerraBot.tmod (own save dir; enabled: observer + TerraBot)
      telemetry/*.jsonl    observer journal (scoring evidence, unchanged observer 0.7)
      game_events.jsonl    TerraBot event stream (game side)
      game_actions.jsonl   TerraBot inventory-step actions as the game executed them (craft/select/equip/chest)
      inputs.jsonl         every agent action call as the proxy forwarded it (actor=agent, dispatch=tb-api)
      api_calls.json       call counts per op and per program
      screens/             screenshots taken by programs or the harness
      manifest.json, result.json, desktop.mp4, extended-score.json, audit.json

The proxy (agent.sock) is the only socket a program can reach. It whitelists the tb-api ops, journals every
action with wall-clock start/end (so published scoring attributes milestones to the agent), and releases all keys
when a program disconnects. game.sock (the mod) is reachable only from the harness.
"""
import json
import os
from pathlib import Path
import resource
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from terrariabench.linux_control import (XGameControl, desktop_environment, isolated_audio_env, quiet_desktop,  # noqa: E402
                                         stop_owned_game)

TML = Path.home() / ".local/share/Steam/steamapps/common/tModLoader"
TMOD = ROOT / "runs/terrabot-build/tml/Mods/TerraBot.tmod"
API_VERSION = "tb-api-1.0-rc1"
SIZE = 1024
READ_OPS = {"me", "inventory", "time", "world", "tiles", "find_tiles", "npcs", "items", "events", "recipes", "chest"}
ACTION_OPS = {"input", "stop", "select", "craft", "equip", "take", "put", "close_chest"}
OTHER_OPS = {"wait", "screenshot"}
TEST_OPS = {"truth_tiles", "truth_npcs", "truth_edit", "truth_give", "truth_morning"}


def launch(profile, log, telemetry, *, display, extra_env):
    """linux_control.launch for an isolated display, but enabling TerraBot next to the observer in this profile only."""
    profile, log, telemetry = (Path(p).resolve() for p in (profile, log, telemetry))
    telemetry.mkdir(parents=True, exist_ok=True)
    config_path = profile / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    config.update(Language="en-US", Fullscreen=False, WindowBorderless=False, WindowMaximized=False, DisplayWidth=SIZE,
                  DisplayHeight=SIZE, AutoPause=False, CloudSavingDefault=False, Zoom=1.0, UIScale=.9,
                  ResetDefaultUIScale=False, LightingMode=3, MapEnabled=True)
    config_path.write_text(json.dumps(config, indent=2))
    (profile / "Mods/enabled.json").write_text(json.dumps(["TerrariaBenchObserver", "TerraBot"]))
    env = desktop_environment()
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_MANAGEMENT_KEY"):
        env.pop(name, None)
    env.pop("WAYLAND_DISPLAY", None)
    env.update(DISPLAY=display, SDL_VIDEODRIVER="x11", FNA_MOUSE_DISABLE_GLOBAL_ACCESS="1",
               TERRARIABENCH_TELEMETRY_DIR=str(telemetry), **isolated_audio_env(display, env), **extra_env)
    quiet_desktop()
    with log.open("w") as stream:
        proc = subprocess.Popen(["bash", "LaunchUtils/ScriptCaller.sh", "-tmlsavedirectory", str(profile), "-skipselect"],
                                cwd=TML, env=env, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True, preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
    return proc.pid


class GameLink:
    """Blocking JSON-lines client for game.sock (one per thread)."""

    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(path))
        self.file = self.sock.makefile("rwb", buffering=0)

    def raw(self, line):
        self.file.write(line if line.endswith(b"\n") else line + b"\n")
        reply = self.file.readline()
        if not reply:
            raise ConnectionError("game closed the API socket")
        return reply

    def call(self, op, **args):
        r = json.loads(self.raw(json.dumps({"id": 0, "op": op, "args": args}).encode()))
        if not r.get("ok"):
            raise RuntimeError(f"{op}: {r.get('error')}")
        return r["result"]

    def close(self):
        self.sock.close()


class Proxy:
    def __init__(self, run, game_sock, *, capture, allow_test_ops=False):
        self.run, self.game_sock, self.capture = Path(run), Path(game_sock), capture
        self.path = self.run / "agent.sock"
        self.allowed = READ_OPS | ACTION_OPS | OTHER_OPS | (TEST_OPS if allow_test_ops else set())
        self.program, self.agent_kind, self.workspace = "harness", "scripted", None
        self.counts, self.lock, self.shots = {}, threading.Lock(), 0
        self.inputs = (self.run / "inputs.jsonl").open("a")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.path.exists():
            self.path.unlink()
        self.server.bind(str(self.path))
        self.server.listen(8)
        self.stopping = False
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self.stopping:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def count(self, op):
        with self.lock:
            per = self.counts.setdefault(self.program, {})
            per[op] = per.get(op, 0) + 1

    def screenshot(self):
        with self.lock:
            self.shots += 1
            n = self.shots
        path = self.run / "screens" / f"{n:05d}-{self.program}.png"
        self.capture(path)
        if self.workspace:
            dest = Path(self.workspace) / "screens"
            dest.mkdir(exist_ok=True)
            shutil.copy2(path, dest / "latest.png")
            return "screens/latest.png"
        return str(path)

    def _serve(self, conn):
        game = None
        f = conn.makefile("rwb", buffering=0)
        try:
            game = GameLink(self.game_sock)
            for line in f:
                try:
                    req = json.loads(line)
                    op, rid = req.get("op"), req.get("id", 0)
                except (ValueError, AttributeError):
                    f.write(b'{"id":0,"ok":false,"error":"bad request"}\n')
                    continue
                if op not in self.allowed:
                    f.write((json.dumps({"id": rid, "ok": False, "error": f"op '{op}' is not part of {API_VERSION}"}) + "\n").encode())
                    continue
                self.count(op)
                if op == "screenshot":
                    try:
                        reply = json.dumps({"id": rid, "ok": True, "result": self.screenshot()})
                    except Exception as e:  # noqa: BLE001
                        reply = json.dumps({"id": rid, "ok": False, "error": f"screenshot failed: {e}"})
                    f.write((reply + "\n").encode())
                    continue
                started = time.time()
                out = game.raw(line)
                if op in ACTION_OPS:
                    ok = b'"ok":true' in out[:200]
                    rec = {"actor": "agent", "agent_kind": self.agent_kind, "dispatch": "tb-api", "api": API_VERSION,
                           "op": op, "args": req.get("args", {}), "ok": ok, "program": self.program,
                           "started_unix": started, "ended_unix": time.time()}
                    with self.lock:
                        if not self.inputs.closed:
                            self.inputs.write(json.dumps(rec) + "\n")
                            self.inputs.flush()
                f.write(out)
        except (ConnectionError, BrokenPipeError, OSError):
            pass
        finally:
            # A program that ends (or is killed) must not leave keys held.
            try:
                (game or GameLink(self.game_sock)).call("stop")
            except Exception:  # noqa: BLE001
                pass
            if game:
                game.close()
            conn.close()

    def close(self):
        self.stopping = True
        self.server.close()
        if self.path.exists():
            self.path.unlink()
        with self.lock:
            self.inputs.close()
        (self.run / "api_calls.json").write_text(json.dumps(self.counts, indent=1))


class Session:
    def __init__(self, run, fixture, *, display=":15", test_mode=False, record=True,
                 manifest=None):
        self.run = Path(run).resolve()
        self.fixture, self.display = Path(fixture).resolve(), display
        self.test_mode, self.record, self.manifest = test_mode, record, dict(manifest or {})
        self.pid = self.game = self.recorder = self.proxy = self.link = None

    def log(self, *parts):
        line = time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts)
        print(line, file=sys.stderr, flush=True)
        with (self.run / "session.log").open("a") as f:
            f.write(line + "\n")

    def start(self):
        if self.run.exists():
            raise SystemExit(f"refusing to reuse {self.run}")
        self.run.mkdir(parents=True)
        (self.run / "screens").mkdir()
        shutil.copytree(self.fixture, self.run / "tml", ignore=shutil.ignore_patterns("Logs", "*.log", "*.bak"))
        shutil.copy2(TMOD, self.run / "tml/Mods/TerraBot.tmod")
        # Workshop mods auto-update; a stale list makes tModLoader stop on an "Updated Mods" dialog before the menu.
        (self.run / "tml/LastLaunchedMods.txt").unlink(missing_ok=True)
        fixture_meta = json.loads((self.fixture / "fixture.json").read_text())
        self.manifest.update({
            "track": "programmatic", "api": API_VERSION, "harness": "tools/terrabot", "fixture": str(self.fixture),
            "world_seed": fixture_meta.get("seed"), "world_evil": fixture_meta.get("evil"), "display": self.display,
            "difficulty": "classic", "pve": "normal", "hostile_damage": "on", "test_mode": self.test_mode,
            "started_unix": time.time(),
            "labels": {"saw": "structured state via tb (map-revealed tiles + lit on-screen tiles, visible NPCs/items, own "
                              "player and inventory), program output, events, optional screenshot",
                       "could_do": f"write Python programs against {API_VERSION}: control flags for N ticks with a cursor, "
                                   "real item use, real recipes/stations, equip, chest UI transfers, pathfinder (library)",
                       "helped_by": self.manifest.get("helped_by", "nobody")}})
        (self.run / "manifest.json").write_text(json.dumps(self.manifest, indent=2))
        game_sock = self.run / "game.sock"
        env = {"TERRARIABENCH_PROFILE": "reference-reconstructed-v1", "TERRARIABENCH_PVE": "enabled",
               "TERRARIABENCH_HOSTILE_DAMAGE": "on", "TERRARIABENCH_REFERENCE_STARTER_PREFIXES": "plain",
               "TERRARIABENCH_CHECKPOINT_CHAT": "disabled", "TERRABOT_SOCKET": str(game_sock), "TERRABOT_DIR": str(self.run)}
        if self.test_mode:
            env["TERRABOT_TEST"] = "1"
        self.pid = launch(self.run / "tml", self.run / "client.log", self.run / "telemetry", display=self.display, extra_env=env)
        (self.run / "game.json").write_text(json.dumps({"pid": self.pid, "display": self.display}))
        self.log(f"game pid {self.pid} on {self.display}")
        try:
            self._enter_world(game_sock)
        except BaseException:
            self.log("start failed; stopping the game")
            self.stop({"kind": "start_failed"})
            raise
        return self

    def _enter_world(self, game_sock):
        deadline = time.monotonic() + 300
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("game did not enter the world")
            try:
                link = GameLink(game_sock)
                if link.call("ping")["in_world"]:
                    self.link = link
                    break
                link.close()
            except (FileNotFoundError, ConnectionRefusedError, ConnectionError, RuntimeError):
                pass
            time.sleep(1)
        # The player may still be on the spawn fade-in; wait until updates tick.
        t0 = self.link.call("me")["tick"]
        while self.link.call("me")["tick"] < t0 + 30:
            time.sleep(.2)
        self.game = XGameControl(self.pid, display=self.display, width=SIZE, height=SIZE)
        self.game.setup_window()
        if self.record:
            self.recorder = subprocess.Popen(
                [sys.executable, str(ROOT / "tools/record_desktop.py"), str(self.run / "desktop.mp4"), "--display", self.display,
                 "--until-file", str(self.run / "result.json"), "--max-seconds", "30000"],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.proxy = Proxy(self.run, game_sock, capture=self.game.capture, allow_test_ops=self.test_mode)
        self.log("in world; proxy at", self.proxy.path)


    def stop(self, result=None):
        result = dict(result or {})
        result["ended_unix"] = time.time()
        try:
            result["final_me"] = self.link.call("me") if self.link else None
        except Exception as e:  # noqa: BLE001
            result["final_me_error"] = str(e)
        if self.proxy:
            self.proxy.close()
        (self.run / "result.json").write_text(json.dumps(result, indent=2))
        if self.recorder:
            try:
                self.recorder.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.recorder.terminate()
        if self.link:
            self.link.close()
        if self.game:
            self.game.close()
        if self.pid:
            self.log("stopping game", stop_owned_game(self.pid, self.run / "tml"))
        try:
            subprocess.run([sys.executable, str(ROOT / "tools/extended_score.py"), str(self.run)], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        except subprocess.TimeoutExpired:
            pass
