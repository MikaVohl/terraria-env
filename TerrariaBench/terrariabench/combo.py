"""Planner + executor agents on the reconstructed reference profile, from screenshots only.

A planner model (gateway) sets an objective every 10-60 s (its own choice) from the newest screenshots,
the checkpoint log, its notes and the executor's recent actions; it performs inventory/crafting clicks
itself while the executor pauses. A fast executor acts every few seconds from the newest screenshot(s):
  haiku  Claude Haiku 5.5 via the gateway, thinking off, returns 1-4 raw keyboard/mouse actions.
  jev    TypeSafe Jev via OpenRouter Decisions: a Choice over actions built from its own Box/Noul answers
         about the screenshots (no game state). Its action set is a designed scaffold (open track).
Same world, PvE setting, task prompt (+ interface card), JPEG screenshots, recording layout and scorer
as reference_live. Real-time clock: the game never pauses.
"""
import argparse
import base64
import io
import json
import queue
import shutil
import threading
import time
from pathlib import Path

from . import gateway, unified
from .linux_control import KEY_NAMES, control, launch, stop_owned_game, validate_actions
from .openrouter import Budget, ProviderError, decide, hermes_key
from .reference_live import (DEFAULT_PROFILE_ID, DEFAULT_PROMPT, LIGHTING_MODES, ROOT, GameClock, digest, display_settings,
                             dump, game_time, reference_metrics)
from .reference_scoring import checkpoint_view, load_reference_events, reference_score

JEV_MODEL = "typesafe/jev-1.14"
JEV_PRICING = {"prompt": "0.000000042", "completion": "0", "request": "0"}
CARD = (ROOT / "prompts/interface_card.txt").read_text()
PLANNER_SYSTEM = (
    "You are the PLANNER of a two-part agent playing Terraria. A fast EXECUTOR acts every few seconds from the newest "
    "screenshot and pursues the objective you give it with movement, jumping, mining, chopping, attacking and placing "
    "blocks. It cannot open menus or craft: you do inventory and crafting yourself with ui_actions (raw clicks, "
    "executed while the executor pauses). The game runs in real time and never pauses.\n" + CARD +
    "\nReply with one JSON object only: {\"objective\": concrete instruction for the executor (max 300 chars), "
    "\"replan_seconds\": 10-60 (when you want to look again), \"notes\": your memory for next time (max 1500 chars), "
    "\"ui_actions\": optional list of 1-16 actions {\"keys\":[...],\"mouse\":\"left|right\",\"x\":0-1023,\"y\":0-1023,\"ms\":20-2000}}.")
UI_SESSION_NOTE = (" After your ui_actions run you immediately get a new screenshot and can keep clicking; the executor stays "
                   "paused until you reply without ui_actions.")
# default-v1 combination: the single-model system prompt's goal and default controls, the same act primitives for
# the planner's ui_actions, no checkpoint log and no statement about the clock (identical in both clock modes).
_DEFAULT_PARAS = (ROOT / DEFAULT_PROMPT).read_text().split("\n\n")
DEFAULT_GOAL, DEFAULT_CONTROLS = _DEFAULT_PARAS[0], _DEFAULT_PARAS[2]


def planner_default_system(width, height):
    return (
        "You are the PLANNER of a two-part agent playing Terraria. A fast EXECUTOR acts every few seconds from the newest "
        "screenshot and pursues the objective you give it with movement, jumping, mining, chopping, attacking and placing "
        "blocks. It cannot open menus or craft: you do inventory and crafting yourself with ui_actions (keyboard and mouse "
        "actions, executed while the executor pauses).\n\n" + DEFAULT_GOAL + "\n\n" + DEFAULT_CONTROLS +
        f"\nScreenshots are {width}x{height} pixels. Reply with one JSON object only: {{\"objective\": concrete instruction "
        "for the executor (max 300 chars), \"replan_seconds\": 10-60 (game seconds until you look again), \"notes\": your "
        "memory for next time (max 1500 chars), \"ui_actions\": optional list of 1-16 actions {\"keys\":[...],"
        f"\"mouse\":\"left|right\",\"x\":0-{width - 1},\"y\":0-{height - 1},\"ms\":20-2000}}; each action moves the mouse "
        "to (x, y) if given, then holds the keys and/or mouse button for ms milliseconds and releases them}.")


HAIKU_EXECUTOR_SYSTEM = (
    "You are the fast EXECUTOR of a Terraria agent. A planner gives you an objective; act on the newest screenshot "
    "right now. The game runs in real time. Holding a mouse button keeps swinging the held tool, about one swing "
    "per 0.3 s.\n" + CARD +
    "\nReply with one JSON object only: {\"actions\": 1-4 actions {\"keys\":[...],\"mouse\":\"left|right\","
    "\"x\":0-1023,\"y\":0-1023,\"ms\":20-2000}, \"status\": \"working\" | \"done\" | \"stuck\"}. Coordinates are screenshot pixels.")
CENTER, SWEEP_PX = 512, (24, 40, 56)  # screen centre; axe/sword holds at 1.5, 2.5, 3.5 tiles from the player


def jev_actions(choice, tree_side, foe_side, cx=CENTER, cy=CENTER, zoom=1.0):
    """Jev's catalog actions as primitive inputs; pixel offsets (designed at zoom 1, centre 512) follow window and zoom."""
    def px(dx, dy):
        return round(cx + dx * zoom), round(cy + dy * zoom)
    if choice == "chop_tree":
        s = 1 if tree_side == "right" else -1
        return [{"keys": ["3"], "ms": 40}] + [dict(zip("xy", px(s * d, -7)), mouse="left", ms=700) for d in SWEEP_PX]
    if choice == "attack":
        s = 1 if foe_side == "right" else -1
        return [{"keys": ["1"], "ms": 40}, dict(zip("xy", px(s * 40, -12)), mouse="left", ms=350),
                dict(zip("xy", px(s * 56, -22)), mouse="left", ms=350)]
    return {"walk_left": [{"keys": ["a"], "ms": 500}], "walk_right": [{"keys": ["d"], "ms": 500}],
            "jump_left": [{"keys": ["space", "a"], "ms": 450}], "jump_right": [{"keys": ["space", "d"], "ms": 450}],
            "dig_down": [{"keys": ["2"], "ms": 40}] + [dict(zip("xy", px(dx, 36)), mouse="left", ms=450) for dx in (-8, 8, -8, 8)],
            "dig_left": [{"keys": ["2"], "ms": 40}, dict(zip("xy", px(-24, -12)), mouse="left", ms=500),
                         dict(zip("xy", px(-24, 12)), mouse="left", ms=500), {"keys": ["a"], "ms": 250}],
            "dig_right": [{"keys": ["2"], "ms": 40}, dict(zip("xy", px(24, -12)), mouse="left", ms=500),
                          dict(zip("xy", px(24, 12)), mouse="left", ms=500), {"keys": ["d"], "ms": 250}],
            "toggle_inventory": [{"keys": ["esc"], "ms": 60}]}.get(choice, [])


def jpeg_url(path, quality=85):
    from PIL import Image
    buffer = io.BytesIO()
    Image.open(path).convert("RGB").save(buffer, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def json_object(text):
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


KEY_ALIASES = {"escape": "esc", "spacebar": "space", "return": "enter", "shift": "leftshift", "ctrl": "leftctrl",
               "control": "leftctrl", "arrowup": "up", "arrowdown": "down", "arrowleft": "left", "arrowright": "right"}


def normalized(actions):
    """Map common key spellings ("Escape", "Space", "Shift") onto the controller's key names before validation."""
    for action in actions:
        if isinstance(action, dict) and isinstance(action.get("keys"), list):
            action["keys"] = [KEY_ALIASES.get(str(k).lower(), str(k).lower()) for k in action["keys"]]
    return actions


class Role:
    """One model role: budget, call log and live accounting snapshot (read by tools/pilot_spend.py)."""

    def __init__(self, name, root, budget, provider):
        self.name, self.root, self.budget, self.provider = name, root, budget, provider
        self.calls, self.failures, self.latencies, self.lock = 0, 0, [], threading.Lock()

    def call(self, fn, archived):
        with self.lock:
            self.budget.reserve()
            self.calls += 1
            n = self.calls
        t0 = time.monotonic()
        try:
            response = fn()
        except ProviderError as error:
            with self.lock:
                self.budget.abandon(error.sent)
                self.failures += 1
                dump(self.root / f"accounting-{self.name}.json", self.budget.summary())
            raise
        latency = time.monotonic() - t0
        with self.lock:
            self.budget.reconcile(response.get("usage"))
            self.latencies.append(latency)
            dump(self.root / f"accounting-{self.name}.json", self.budget.summary())
        dump(self.root / "calls" / f"{self.name}-{n:04d}.json", {"request": archived, "response": response, "latency": latency})
        return response, latency, n

    def summary(self):
        lat = sorted(self.latencies)
        return {"provider": self.provider, "calls": self.calls, "failures": self.failures,
                "latency_median": lat[len(lat) // 2] if lat else None, "accounting": self.budget.summary()}


def gateway_text(model, reasoning, system, content, key, thinking=True):
    if model in unified.MODELS:
        # Anthropic content blocks -> OpenAI parts; no thinking = reasoning_effort "none".
        parts = [{"type": "text", "text": b["text"]} if b["type"] == "text" else
                 {"type": "image_url", "image_url": {"url": f'data:{b["source"]["media_type"]};base64,{b["source"]["data"]}'}}
                 for b in content]
        payload = unified.body(model, reasoning if thinking else "none",
                               [{"role": "system", "content": system}, {"role": "user", "content": parts}], max_tokens=16384)
        return unified.chat(payload, key=key, timeout=90)
    session = gateway.session_id()
    body = gateway.body(model, reasoning, system, [{"role": "user", "content": content}], [], session)
    body.pop("tools")
    if not thinking:
        body.pop("output_config", None)
        body["thinking"] = {"type": "disabled"}
    message, meta = gateway.messages(body, key=key, session=session, timeout=90)
    return gateway.normalize(message, meta, model)


EXECUTOR_MODELS = {"haiku": "claude-haiku-5-5", "luna": "gpt-5.6-luna", "jev": JEV_MODEL}


def price_of(model):
    price = (gateway.MODELS.get(model) or unified.MODELS[model])["price"]
    return {"prompt": f"{price['input']:.10f}", "completion": f"{price['output']:.10f}"}


def image_block(url):
    head, data = url.split(",", 1)
    return {"type": "image", "source": {"type": "base64", "media_type": head[5:].split(";")[0], "data": data}}


def run(args):
    root, fixture = args.output.resolve(), args.fixture.resolve()
    if root.exists() or root.is_relative_to(fixture):
        raise ValueError("new output outside the fixture required")
    profile = json.loads((ROOT / "configs/reference-reconstructed.json").read_text())
    task = (ROOT / profile["agent"]["task_prompt"]).read_text()
    if args.pve and args.hostile_damage == "off":
        task = task.replace("This scenario begins with hostile PvE disabled.", "Hostile enemies spawn and can be fought for "
                            "their drops, but in this scenario they cannot damage you.")
    elif args.pve:
        task = task.replace("This scenario begins with hostile PvE disabled.", "Hostile enemies are active under normal game rules.")
    default, paused = args.profile == DEFAULT_PROFILE_ID, args.clock == "paused"
    if default:
        if not args.game_seconds or args.hostile_damage != "on":
            raise ValueError("default-v1 needs --game-seconds and the unmodified game rules")
        args.pve, task = True, DEFAULT_GOAL
    elif paused:
        raise ValueError("the paused clock is implemented for the default-v1 profile")
    gkey = gateway.load_key()
    root.mkdir(parents=True)
    (root / "calls").mkdir()
    roles = {"planner": Role("planner", root, Budget(args.usd_planner, price_of(args.planner),
                                                      input_ceiling=180000, output_ceiling=16384), "gateway")}
    if args.executor in ("haiku", "luna"):
        roles["executor"] = Role("executor", root, Budget(args.usd_executor, price_of(EXECUTOR_MODELS[args.executor]),
                                                         input_ceiling=60000, output_ceiling=16384 if args.executor == "luna" else 4096), "gateway")
    else:
        okey = hermes_key()
        roles["executor"] = Role("executor", root, Budget(args.usd_executor, JEV_PRICING, input_ceiling=40000, output_ceiling=4096), "openrouter")
    settings = display_settings(args)
    width, height = settings["window"]
    if not default and (width, height) != (1024, 1024):
        raise ValueError("the reference combo keeps the 1024x1024 window")
    planner_system = (planner_default_system(width, height) if default else PLANNER_SYSTEM) + (UI_SESSION_NOTE if args.ui_session else "")
    protocol = "combo-v2" if args.ui_session else "combo-v1"
    manifest = {"protocol": protocol, "config": {"planner_model": args.planner, "planner_reasoning": args.planner_reasoning,
                "executor": args.executor, "executor_model": EXECUTOR_MODELS[args.executor],
                "pve": args.pve, "hostile_contact_damage": args.hostile_damage, "clock": args.clock, "seconds": args.seconds,
                "jev_frames": args.jev_frames, "ui_session": args.ui_session, "campaign_profile": args.campaign_profile,
                "profile": args.profile, "game_seconds": args.game_seconds},
                "profile_id": args.profile, "game_seconds_budget": args.game_seconds, "display_settings": settings,
                "task_prompt": task, "planner_system": planner_system, "executor_system": HAIKU_EXECUTOR_SYSTEM if args.executor != "jev" else None,
                "privileged_state": False, "official_eligible": False, "started_unix": time.time(), "game_display": args.display,
                "source_hashes": {p.name: digest(p) for p in Path(__file__).parent.glob("*.py")}}
    dump(root / "manifest.json", manifest)

    lock, stop = threading.Lock(), threading.Event()
    plan = {"objective": "Look around and start making progress.", "notes": "", "version": 0, "since": time.monotonic(), "replan": 15}
    ui_queue, executed, frames, fatal = queue.Queue(), [], [], []
    replan_now = threading.Event()
    # combo-v2 UI session: while set, the executor only runs planner clicks; ui_done marks each click batch as executed.
    ui_session, ui_done = threading.Event(), threading.Event()
    frame_n = [0]
    pid = game = None
    stop_reason, started = "startup", None
    clock = GameClock(root / "telemetry")

    def log(entry):
        with lock, (root / "decisions.jsonl").open("a") as s:
            s.write(json.dumps(entry) + "\n")

    def capture():
        with lock:
            n = frame_n[0]
            frame_n[0] += 1
        path = root / "frames" / f"{n:05d}.png"
        meta = game.capture(path)
        with lock:
            frames.append((path, meta["captured_unix"]))
        return path, meta

    frozen = {"total": 0.0}

    def clock_log(entry):
        with (root / "clock.jsonl").open("a") as stream:
            stream.write(json.dumps({**entry, "game_updates": clock.read(), "unix": time.time()}) + "\n")

    def model_call(fn):
        """Paused clock: the game process group is stopped while a model generates (both roles run sequentially)."""
        if not paused:
            return fn()
        import os
        import signal
        os.killpg(pid, signal.SIGSTOP)
        t0 = time.monotonic()
        clock_log({"event": "freeze"})
        try:
            return fn()
        finally:
            os.killpg(pid, signal.SIGCONT)
            frozen["total"] += time.monotonic() - t0
            clock_log({"event": "thaw"})

    planner_state = {"rejected": None}  # last reply the harness could not use; shown to the planner once

    def planner_step():
        """One planner call on a fresh screenshot; updates the plan and returns (call number, ui actions, replan s)."""
        role = roles["planner"]
        with lock:
            recent = list(frames[-1:])
            current, history = dict(plan), executed[-12:]
        newest, meta = capture()
        shots = [p for p, _ in recent] + [newest]
        if default:
            info = {"game_time_played": game_time(clock.read())}
        else:
            events = checkpoint_view(load_reference_events(root / "telemetry")) if list((root / "telemetry").glob("*.jsonl")) else []
            info = {"checkpoint_log": events, "seconds_since_start": round(time.monotonic() - started)}
        rejected = planner_state["rejected"]
        text = json.dumps({"task": task, "your_notes": current["notes"], "current_objective": current["objective"],
                           "executor_recent_actions": history, **info,
                           **({"your_previous_reply_was_rejected": rejected} if rejected else {})})
        planner_state["rejected"] = None
        content = [{"type": "text", "text": text}] + [b for i, p in enumerate(shots) for b in (
            {"type": "text", "text": "Newest screenshot:" if i == len(shots) - 1 else "Earlier screenshot:"}, image_block(jpeg_url(p)))]
        archived = {"text": text, "frames": [str(p.relative_to(root)) for p in shots]}
        response, latency, n = role.call(lambda: model_call(
            lambda: gateway_text(args.planner, args.planner_reasoning, planner_system, content, gkey)), archived)
        body = json_object(response["choices"][0]["message"]["content"] or "{}")
        ui = normalized(body.get("ui_actions") or [])
        if ui:
            validate_actions(ui, width=width, height=height, max_hold_ms=2000)
        replan = max(10, min(60, int(body.get("replan_seconds", 20))))
        with lock:
            plan.update(objective=str(body.get("objective", plan["objective"]))[:300], notes=str(body.get("notes", ""))[:1500],
                        version=plan["version"] + 1, since=time.monotonic(), replan=replan)
        log({"role": "planner", "n": n, "latency": latency, "objective": plan["objective"], "replan_seconds": replan,
             "ui_actions": len(ui), "frame": str(newest.relative_to(root)), "game_updates": clock.read(), "unix": time.time()})
        return n, ui, replan

    def planner_error(error):
        log({"role": "planner", "error": f"{type(error).__name__}: {error}"[:300], "unix": time.time()})
        if not isinstance(error, ProviderError):
            planner_state["rejected"] = f"{type(error).__name__}: {error}"[:300] + \
                f" (key names: a-z, 0-9, {', '.join(k for k in KEY_NAMES if len(k) > 1)})"

    def planner_loop():
        """Real-time clock: the planner runs concurrently with the executor."""
        while not stop.is_set():
            try:
                n, ui, replan = planner_step()
                if ui:
                    if args.ui_session:
                        ui_done.clear()
                        ui_session.set()
                    ui_queue.put((n, ui))
                else:
                    ui_session.clear()
                replan_now.clear()
                if ui and args.ui_session:
                    while not (ui_done.wait(1) or stop.is_set()):
                        pass
                    continue
                replan_now.wait(replan)
            except (ProviderError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                planner_error(error)
                ui_session.clear()  # never leave the executor paused behind a failed planner call
                stop.wait(3)
            except Exception as error:
                fatal.append(f"{type(error).__name__}: {error}")
                log({"role": "planner", "fatal": fatal[-1], "unix": time.time()})
                stop.set()

    def haiku_step(objective, recent):
        frame, meta = capture()
        content = [{"type": "text", "text": json.dumps({"objective": objective, "your_recent_actions": recent})},
                   {"type": "text", "text": "Newest screenshot:"}, image_block(jpeg_url(frame))]
        response, latency, n = roles["executor"].call(
            lambda: model_call(lambda: gateway_text(EXECUTOR_MODELS[args.executor], "medium", HAIKU_EXECUTOR_SYSTEM, content, gkey, thinking=False)),
            {"objective": objective, "recent": recent, "frame": str(frame.relative_to(root))})
        body = json_object(response["choices"][0]["message"]["content"] or "{}")
        actions = body.get("actions") or []
        if not isinstance(actions, list) or not 1 <= len(actions) <= 4:
            raise ValueError("executor must return 1-4 actions")
        validate_actions(normalized(actions), width=width, height=height, max_hold_ms=2000)
        summary = "; ".join(f'{"+".join(a.get("keys", []))}{" " + a["mouse"] if a.get("mouse") else ""}'
                            f'{"@%d,%d" % (a["x"], a["y"]) if "x" in a else ""}' for a in actions)
        return actions, summary, body.get("status", "working"), latency, n, frame, meta, {}

    def jev_step(objective, recent):
        frame, meta = capture()
        with lock:
            history = [p for p, _ in frames[-args.jev_frames:]]
        state = [f"Task: {task}", f"Planner objective: {objective}", f"Your recent actions (newest last): {recent}",
                 "Terraria screenshots, oldest first; the newest is the current view. The camera keeps your character "
                 f"at the screen centre ({width // 2}, {height // 2})."]
        for i, p in enumerate(history):
            state += ["Current screenshot:" if i == len(history) - 1 else "Earlier screenshot:",
                      {"type": "image_url", "image_url": {"url": jpeg_url(p)}}]
        questions = {
            # Jev cannot ground "nearest to the player" in a box (it boxes the player or the most salient tree), so
            # targeting uses side classification plus fixed reach sweeps; holds on empty tiles are harmless.
            "tree_side": {"type": "choice", "instructions": "On which side of the player character (the small person at the exact "
                                                             "screen centre) is the nearest tree trunk in the current screenshot?",
                          "criteria": {"left": "Nearest trunk is left of the player.", "right": "Nearest trunk is right of the player.",
                                       "none": "No tree trunk visible."}},
            "hostile_side": {"type": "choice", "instructions": f"Is a hostile creature (slime, zombie, flying eye) within 6 tiles ({round(96 * args.zoom)} px) "
                                                                "of the player character in the current screenshot, and on which side?",
                             "criteria": {"left": "Hostile close on the left.", "right": "Hostile close on the right.",
                                          "none": "No hostile within 6 tiles."}},
            "inventory_open": {"type": "noul", "instructions": "Is the inventory screen open in the current screenshot (grid of item slots and a crafting list)?"},
            "objective_done": {"type": "noul", "instructions": "Do the screenshots show that `Planner objective` has been achieved?"},
            "action": {"type": "choice", "instructions": "Choose the action that best advances `Planner objective` right now from the "
                                                          "current screenshot. Survive: deal with hostiles that are close.",
                       "criteria": {"walk_left": "Walk left.", "walk_right": "Walk right.", "jump_left": "Jump while moving left.",
                                    "jump_right": "Jump while moving right.",
                                    "chop_tree": "Chop a tree trunk within about 4 tiles of the player with the axe. If the nearest tree is "
                                                 "farther away, walk toward it instead.",
                                    "attack": "Fight a hostile creature (slime, zombie) that is close, with the sword. Never for trees.",
                                    "dig_down": "Dig straight down two tiles wide with the pickaxe.",
                                    "dig_left": "Dig a tunnel to the left with the pickaxe.", "dig_right": "Dig a tunnel to the right with the pickaxe.",
                                    "toggle_inventory": "Press escape to open or close the inventory.", "wait": "Do nothing for a moment."}}}
        archived = {"state": state[:4] + [f"[{len(history)} screenshots]"], "frames": [str(p.relative_to(root)) for p in history], "questions": questions}
        response, latency, n = roles["executor"].call(
            lambda: model_call(lambda: decide({"model": JEV_MODEL, "state": state, "questions": questions}, key=okey, timeout=20)), archived)
        a = response["answers"]
        tree_side, foe_side = a["tree_side"]["choice"], a["hostile_side"]["choice"]
        # Jev's action choice is used only when its target exists; otherwise the next most probable valid action.
        valid = lambda c: not ((c == "chop_tree" and tree_side == "none") or (c == "attack" and foe_side == "none")
                               or (c == "toggle_inventory" and a["inventory_open"].get("noul", 0) < .5 and not args.allow_open_inventory))
        ranked = sorted((a["action"].get("probabilities") or {a["action"]["choice"]: 1}).items(), key=lambda kv: -kv[1])
        choice = next((c for c, _ in ranked if valid(c)), "wait")
        executed_choice = choice if choice == a["action"]["choice"] else f'{choice} (instead of {a["action"]["choice"]})'
        actions = jev_actions(choice, tree_side, foe_side, width // 2, height // 2, args.zoom)
        status = "done" if a["objective_done"].get("noul", 0) > .7 else "working"
        detail = {"choice": choice, "executed": executed_choice, "confidence": a["action"].get("confidence"),
                  "probabilities": a["action"].get("probabilities"), "tree_side": tree_side, "hostile_side": foe_side,
                  "inventory_open": a["inventory_open"].get("noul"),
                  "objective_done": a["objective_done"].get("noul")}
        return actions, executed_choice, status, latency, n, frame, meta, detail

    try:
        shutil.copytree(fixture, root / "tml", ignore=shutil.ignore_patterns("Logs", "*.log", "*.bak"))
        pid = launch(root / "tml", root / "client.log", root / "telemetry", skipselect=True, width=width, height=height,
                     display=args.display,
                     config_updates={"UIScale": args.ui_scale, "ResetDefaultUIScale": False, "Zoom": args.zoom,
                                     "LightingMode": LIGHTING_MODES[args.lighting]},
                     extra_env={"TERRARIABENCH_PROFILE": profile["profile_id"], "TERRARIABENCH_PVE": "enabled" if args.pve else "disabled",
                                "TERRARIABENCH_HOSTILE_DAMAGE": args.hostile_damage,
                                "TERRARIABENCH_REFERENCE_STARTER_PREFIXES": "plain",
                                "TERRARIABENCH_CHECKPOINT_CHAT": "disabled" if default else "enabled"})
        dump(root / "game.json", {"pid": pid, "profile": str(root / "tml")})
        deadline = time.monotonic() + 100
        while not list((root / "telemetry").glob("*.jsonl")):
            if time.monotonic() > deadline or not Path(f"/proc/{pid}").exists():
                raise RuntimeError("world/observer startup failed")
            time.sleep(.5)
        game = control(pid, root / "inputs.jsonl", display=args.display, width=width, height=height, max_hold_ms=2000)
        game.setup_window()
        if settings["setup_keys"]:
            time.sleep(1)
            game.act(settings["setup_keys"], actor="operator_setup")
            time.sleep(.5)
        started = time.monotonic()
        stop_reason, step, errors = "wall_limit", 0, 0
        step_fn = jev_step if args.executor == "jev" else haiku_step

        def out_of_game_time():
            return default and clock.seconds() >= args.game_seconds

        def act_within_budget(actions):
            receipts = []
            for action in actions:
                if out_of_game_time():
                    break
                receipts += game.act([action])
            return receipts

        def executor_turn():
            """One executor decision + its actions; returns False when the run must stop."""
            nonlocal step, errors, stop_reason
            with lock:
                objective, recent = plan["objective"], [e["source"] for e in executed[-4:]]
            try:
                actions, summary, status, latency, n, frame, meta, detail = step_fn(objective, recent)
                receipts = act_within_budget(actions) if actions else (time.sleep(.3) or [])
                with lock:
                    executed.append({"source": summary, "at_s": round(clock.seconds() if default else time.monotonic() - started)})
                if status in ("done", "stuck"):
                    replan_now.set()
                log({"role": "executor", "n": n, "step": step, "objective": objective, "summary": summary, "status": status,
                     "actions": actions, "latency": latency, "frame": str(frame.relative_to(root)), "observed_unix": meta["captured_unix"],
                     "first_input_unix": receipts[0]["started_unix"] if receipts else None, **detail,
                     "game_updates": clock.read(), "unix": time.time()})
                step += 1
            except (ProviderError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                errors += 1
                log({"role": "executor", "step": step, "error": f"{type(error).__name__}: {error}"[:300], "unix": time.time()})
                if errors >= 40:
                    stop_reason = "executor_error_limit"
                    return False
                time.sleep(1 if not isinstance(error, ProviderError) or error.sent else 5)
            return True

        if paused:
            # Paused clock: one thread; every model call (planner or executor) runs with the game stopped, and the
            # planner is due every replan_seconds of game time (or when the executor reports done/stuck).
            next_plan, planner_errors = 0, 0
            while time.monotonic() - started < args.seconds:
                if out_of_game_time():
                    stop_reason = "game_time_limit"
                    break
                if clock.read() >= next_plan or replan_now.is_set():
                    try:
                        n, ui, replan = planner_step()
                    except (ProviderError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                        planner_error(error)
                        planner_errors += 1
                        if planner_errors >= 40:
                            stop_reason = "planner_error_limit"
                            break
                        time.sleep(3)
                        continue
                    replan_now.clear()
                    if ui:
                        receipts = act_within_budget(ui)
                        with lock:
                            executed.append({"source": f"planner_ui_{n}", "at_s": round(clock.seconds())})
                        log({"role": "planner_ui", "n": n, "actions": ui, "receipts": len(receipts),
                             "game_updates": clock.read(), "unix": time.time()})
                        if args.ui_session:
                            continue  # UI session: the planner looks again at once
                    next_plan = clock.read() + replan * 60
                    continue
                if not executor_turn():
                    break
        else:
            planner = threading.Thread(target=planner_loop, name="planner", daemon=True)
            planner.start()
            time.sleep(.5)
            while time.monotonic() - started < args.seconds:
                if out_of_game_time():
                    stop_reason = "game_time_limit"
                    break
                if stop.is_set():
                    stop_reason = fatal[0] if fatal else "planner_stopped"
                    break
                try:
                    n, ui = ui_queue.get_nowait()
                    receipts = act_within_budget(ui)
                    with lock:
                        executed.append({"source": f"planner_ui_{n}", "at_s": round(clock.seconds() if default else time.monotonic() - started)})
                    log({"role": "planner_ui", "n": n, "actions": ui, "receipts": len(receipts), "unix": time.time()})
                    ui_done.set()
                    continue
                except queue.Empty:
                    if ui_session.is_set():
                        time.sleep(.1)
                        continue
                if not executor_turn():
                    break
        game.capture(root / "final.png")
    except Exception as error:
        stop_reason = f"{type(error).__name__}: {error}"
    finally:
        stop.set()
        end = time.time()
        if game:
            game.close()
        if pid:
            try:
                dump(root / "termination.json", stop_owned_game(pid, root / "tml"))
            except (RuntimeError, OSError) as error:  # e.g. the game crashed and its pid was reused
                dump(root / "termination.json", {"error": str(error)})
        events = load_reference_events(root / "telemetry") if list((root / "telemetry").glob("*.jsonl")) else []
        dump(root / "evaluation-events.json", events)
        receipts = [json.loads(s) for s in (root / "inputs.jsonl").read_text().splitlines()] if (root / "inputs.jsonl").exists() else []
        started_unix = end - (time.monotonic() - started) if started else end
        result = {"protocol": protocol, "profile_id": args.profile, "config": manifest["config"], "stop_reason": stop_reason,
                  "frames": frame_n[0], "input_commands": len(receipts), "clock": args.clock,
                  "active_wall_seconds": time.monotonic() - started if started else 0, "think_frozen_seconds": frozen["total"],
                  "game_seconds": clock.read() / 60, "game_seconds_budget": args.game_seconds,
                  "evaluation_end_unix": end, "roles": {k: r.summary() for k, r in roles.items()},
                  "score": reference_score(events, actions=receipts),
                  "score_metrics": reference_metrics(receipts, frame_n[0], started_unix, end), "official_eligible": False}
        dump(root / "result.json", result)
        print(json.dumps(result), flush=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--planner", default="claude-sonnet-5-5", choices=sorted(gateway.MODELS) + sorted(unified.MODELS))
    p.add_argument("--planner-reasoning", default="low")
    p.add_argument("--executor", choices=("haiku", "luna", "jev"), required=True)
    p.add_argument("--seconds", type=int, default=1800)
    p.add_argument("--usd-planner", type=float, default=5)
    p.add_argument("--usd-executor", type=float, default=3)
    p.add_argument("--jev-frames", type=int, default=3)
    p.add_argument("--pve", action="store_true")
    p.add_argument("--hostile-damage", choices=("on", "off"), default="on")
    p.add_argument("--campaign-profile", default=None)
    p.add_argument("--profile", choices=("reference", DEFAULT_PROFILE_ID), default="reference")
    p.add_argument("--clock", choices=("realtime", "paused"), default="realtime",
                   help="paused (default-v1): the game is stopped during every planner/executor call; roles run in turn")
    p.add_argument("--game-seconds", type=int, default=None, help="game-time budget (observer game_updates / 60)")
    p.add_argument("--display", default=None, help="isolated instance: rootful Xwayland display for the game")
    p.add_argument("--window", default="1024x1024")
    p.add_argument("--zoom", type=float, default=1.0)
    p.add_argument("--ui-scale", type=float, default=0.9)
    p.add_argument("--lighting", choices=tuple(LIGHTING_MODES), default="color")
    p.add_argument("--smart-cursor", choices=("off", "on"), default="off")
    p.add_argument("--minimap", choices=("frame", "overlay", "off"), default="frame")
    p.add_argument("--allow-open-inventory", action="store_true", help="let Jev open the inventory (default: only close it)")
    p.add_argument("--ui-session", action="store_true",
                   help="combo-v2: after planner clicks, replan at once on a fresh screenshot; executor waits until the planner stops clicking")
    run(p.parse_args())


if __name__ == "__main__":
    main()
