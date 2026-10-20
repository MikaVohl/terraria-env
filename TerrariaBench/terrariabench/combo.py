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
import copy
import io
import json
import queue
import shutil
import threading
import time
from pathlib import Path

from . import gateway
from .linux_control import GameControl, launch, stop_owned_game, validate_actions
from .openrouter import Budget, ProviderError, decide, hermes_key
from .reference_live import ROOT, digest, dump, reference_metrics
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
HAIKU_EXECUTOR_SYSTEM = (
    "You are the fast EXECUTOR of a Terraria agent. A planner gives you an objective; act on the newest screenshot "
    "right now. The game runs in real time. Holding a mouse button keeps swinging the held tool, about one swing "
    "per 0.3 s.\n" + CARD +
    "\nReply with one JSON object only: {\"actions\": 1-4 actions {\"keys\":[...],\"mouse\":\"left|right\","
    "\"x\":0-1023,\"y\":0-1023,\"ms\":20-2000}, \"status\": \"working\" | \"done\" | \"stuck\"}. Coordinates are screenshot pixels.")
CENTER, SWEEP_PX = 512, (24, 40, 56)  # screen centre; axe/sword holds at 1.5, 2.5, 3.5 tiles from the player


def jpeg_url(path, quality=85):
    from PIL import Image
    buffer = io.BytesIO()
    Image.open(path).convert("RGB").save(buffer, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def json_object(text):
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


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
    session = gateway.session_id()
    body = gateway.body(model, reasoning, system, [{"role": "user", "content": content}], [], session)
    body.pop("tools")
    if not thinking:
        body.pop("output_config", None)
        body["thinking"] = {"type": "disabled"}
    message, meta = gateway.messages(body, key=key, session=session, timeout=90)
    return gateway.normalize(message, meta, model)


def image_block(url):
    head, data = url.split(",", 1)
    return {"type": "image", "source": {"type": "base64", "media_type": head[5:].split(";")[0], "data": data}}


def run(args):
    root, fixture = args.output.resolve(), args.fixture.resolve()
    if root.exists() or root.is_relative_to(fixture):
        raise ValueError("new output outside the fixture required")
    profile = json.loads((ROOT / "configs/reference-reconstructed.json").read_text())
    task = (ROOT / profile["agent"]["task_prompt"]).read_text()
    if args.pve:
        task = task.replace("This scenario begins with hostile PvE disabled.", "Hostile enemies are active under normal game rules.")
    gkey = gateway.load_key()
    root.mkdir(parents=True)
    (root / "calls").mkdir()
    pprice = gateway.MODELS[args.planner]["price"]
    roles = {"planner": Role("planner", root, Budget(args.usd_planner, {"prompt": f"{pprice['input']:.10f}", "completion": f"{pprice['output']:.10f}"},
                                                      input_ceiling=180000, output_ceiling=16384), "gateway")}
    if args.executor == "haiku":
        eprice = gateway.MODELS["claude-haiku-5-5"]["price"]
        roles["executor"] = Role("executor", root, Budget(args.usd_executor, {"prompt": f"{eprice['input']:.10f}", "completion": f"{eprice['output']:.10f}"},
                                                         input_ceiling=60000, output_ceiling=4096), "gateway")
    else:
        okey = hermes_key()
        roles["executor"] = Role("executor", root, Budget(args.usd_executor, JEV_PRICING, input_ceiling=40000, output_ceiling=4096), "openrouter")
    manifest = {"protocol": "combo-v1", "config": {"planner_model": args.planner, "planner_reasoning": args.planner_reasoning,
                "executor": args.executor, "executor_model": JEV_MODEL if args.executor == "jev" else "claude-haiku-5-5",
                "pve": args.pve, "clock": "realtime", "seconds": args.seconds, "jev_frames": args.jev_frames},
                "task_prompt": task, "planner_system": PLANNER_SYSTEM, "executor_system": HAIKU_EXECUTOR_SYSTEM if args.executor == "haiku" else None,
                "privileged_state": False, "official_eligible": False, "started_unix": time.time(),
                "source_hashes": {p.name: digest(p) for p in Path(__file__).parent.glob("*.py")}}
    dump(root / "manifest.json", manifest)

    lock, stop = threading.Lock(), threading.Event()
    plan = {"objective": "Look around and start making progress.", "notes": "", "version": 0, "since": time.monotonic(), "replan": 15}
    ui_queue, executed, frames, fatal = queue.Queue(), [], [], []
    replan_now = threading.Event()
    frame_n = [0]
    pid = game = None
    stop_reason, started = "startup", None

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

    def planner_loop():
        role = roles["planner"]
        while not stop.is_set():
            try:
                with lock:
                    recent = list(frames[-1:])
                    current, history = dict(plan), executed[-12:]
                newest, meta = capture()
                shots = [p for p, _ in recent] + [newest]
                events = checkpoint_view(load_reference_events(root / "telemetry")) if list((root / "telemetry").glob("*.jsonl")) else []
                text = json.dumps({"task": task, "your_notes": current["notes"], "current_objective": current["objective"],
                                   "executor_recent_actions": history, "checkpoint_log": events,
                                   "seconds_since_start": round(time.monotonic() - started)})
                content = [{"type": "text", "text": text}] + [b for i, p in enumerate(shots) for b in (
                    {"type": "text", "text": "Newest screenshot:" if i == len(shots) - 1 else "Earlier screenshot:"}, image_block(jpeg_url(p)))]
                archived = {"text": text, "frames": [str(p.relative_to(root)) for p in shots]}
                response, latency, n = role.call(lambda: gateway_text(args.planner, args.planner_reasoning, PLANNER_SYSTEM, content, gkey), archived)
                body = json_object(response["choices"][0]["message"]["content"] or "{}")
                ui = body.get("ui_actions") or []
                if ui:
                    validate_actions(ui, width=1024, height=1024, max_hold_ms=2000)
                    ui_queue.put((n, ui))
                replan = max(10, min(60, int(body.get("replan_seconds", 20))))
                with lock:
                    plan.update(objective=str(body.get("objective", plan["objective"]))[:300], notes=str(body.get("notes", ""))[:1500],
                                version=plan["version"] + 1, since=time.monotonic(), replan=replan)
                log({"role": "planner", "n": n, "latency": latency, "objective": plan["objective"], "replan_seconds": replan,
                     "ui_actions": len(ui), "frame": str(newest.relative_to(root)), "unix": time.time()})
                replan_now.clear()
                replan_now.wait(replan)
            except (ProviderError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                log({"role": "planner", "error": f"{type(error).__name__}: {error}"[:300], "unix": time.time()})
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
            lambda: gateway_text("claude-haiku-5-5", "medium", HAIKU_EXECUTOR_SYSTEM, content, gkey, thinking=False),
            {"objective": objective, "recent": recent, "frame": str(frame.relative_to(root))})
        body = json_object(response["choices"][0]["message"]["content"] or "{}")
        actions = body.get("actions") or []
        if not isinstance(actions, list) or not 1 <= len(actions) <= 4:
            raise ValueError("executor must return 1-4 actions")
        validate_actions(actions, width=1024, height=1024, max_hold_ms=2000)
        summary = "; ".join(f'{"+".join(a.get("keys", []))}{" " + a["mouse"] if a.get("mouse") else ""}'
                            f'{"@%d,%d" % (a["x"], a["y"]) if "x" in a else ""}' for a in actions)
        return actions, summary, body.get("status", "working"), latency, n, frame, meta, {}

    def jev_step(objective, recent):
        frame, meta = capture()
        with lock:
            history = [p for p, _ in frames[-args.jev_frames:]]
        state = [f"Task: {task}", f"Planner objective: {objective}", f"Your recent actions (newest last): {recent}",
                 "Terraria screenshots, oldest first; the newest is the current view. The camera keeps your character "
                 "at the screen centre (512, 512)."]
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
            "hostile_side": {"type": "choice", "instructions": "Is a hostile creature (slime, zombie, flying eye) within 6 tiles (96 px) "
                                                                "of the player character in the current screenshot, and on which side?",
                             "criteria": {"left": "Hostile close on the left.", "right": "Hostile close on the right.",
                                          "none": "No hostile within 6 tiles."}},
            "inventory_open": {"type": "noul", "instructions": "Is the inventory screen open in the current screenshot (grid of item slots and a crafting list)?"},
            "objective_done": {"type": "noul", "instructions": "Do the screenshots show that `Planner objective` has been achieved?"},
            "action": {"type": "choice", "instructions": "Choose the action that best advances `Planner objective` right now from the "
                                                          "current screenshot. Survive: deal with hostiles that are close.",
                       "criteria": {"walk_left": "Walk left.", "walk_right": "Walk right.", "jump_left": "Jump while moving left.",
                                    "jump_right": "Jump while moving right.", "chop_tree": "Step toward the nearest tree and chop it with the axe.",
                                    "attack": "Swing the sword at the nearest hostile.",
                                    "dig_down": "Dig straight down two tiles wide with the pickaxe.",
                                    "dig_left": "Dig a tunnel to the left with the pickaxe.", "dig_right": "Dig a tunnel to the right with the pickaxe.",
                                    "toggle_inventory": "Press escape to open or close the inventory.", "wait": "Do nothing for a moment."}}}
        archived = {"state": state[:4] + [f"[{len(history)} screenshots]"], "frames": [str(p.relative_to(root)) for p in history], "questions": questions}
        response, latency, n = roles["executor"].call(
            lambda: decide({"model": JEV_MODEL, "state": state, "questions": questions}, key=okey, timeout=20), archived)
        a = response["answers"]
        choice = a["action"]["choice"]
        tree_side, foe_side = a["tree_side"]["choice"], a["hostile_side"]["choice"]
        executed_choice = choice
        if choice == "toggle_inventory" and a["inventory_open"].get("noul", 0) < .5 and not args.allow_open_inventory:
            choice = executed_choice = "wait_inventory_closed"
        if choice == "chop_tree" and tree_side in ("left", "right"):
            s, key = (1, "d") if tree_side == "right" else (-1, "a")
            actions = [{"keys": ["3"], "ms": 40}, {"keys": [key], "ms": 250}] + \
                      [{"x": CENTER + s * d, "y": 505, "mouse": "left", "ms": 600} for d in SWEEP_PX]
        elif choice == "attack":
            sides = [1 if foe_side == "right" else -1] if foe_side in ("left", "right") else [-1, 1]
            actions = [{"keys": ["1"], "ms": 40}] + [{"x": CENTER + s * 40, "y": 500, "mouse": "left", "ms": 350} for s in sides]
        else:
            actions = {"walk_left": [{"keys": ["a"], "ms": 500}], "walk_right": [{"keys": ["d"], "ms": 500}],
                       "jump_left": [{"keys": ["space", "a"], "ms": 450}], "jump_right": [{"keys": ["space", "d"], "ms": 450}],
                       "dig_down": [{"keys": ["2"], "ms": 40}] + [{"x": x, "y": 548, "mouse": "left", "ms": 450} for x in (504, 520, 504, 520)],
                       "dig_left": [{"keys": ["2"], "ms": 40}, {"x": 488, "y": 500, "mouse": "left", "ms": 500},
                                    {"x": 488, "y": 524, "mouse": "left", "ms": 500}, {"keys": ["a"], "ms": 250}],
                       "dig_right": [{"keys": ["2"], "ms": 40}, {"x": 536, "y": 500, "mouse": "left", "ms": 500},
                                     {"x": 536, "y": 524, "mouse": "left", "ms": 500}, {"keys": ["d"], "ms": 250}],
                       "toggle_inventory": [{"keys": ["esc"], "ms": 60}]}.get(choice, [])
            if choice == "chop_tree":
                executed_choice = "chop_tree_no_target"
        status = "done" if a["objective_done"].get("noul", 0) > .7 else "working"
        detail = {"choice": choice, "executed": executed_choice, "confidence": a["action"].get("confidence"),
                  "probabilities": a["action"].get("probabilities"), "tree_side": tree_side, "hostile_side": foe_side,
                  "inventory_open": a["inventory_open"].get("noul"),
                  "objective_done": a["objective_done"].get("noul")}
        return actions, executed_choice, status, latency, n, frame, meta, detail

    try:
        shutil.copytree(fixture, root / "tml", ignore=shutil.ignore_patterns("Logs", "*.log", "*.bak"))
        pid = launch(root / "tml", root / "client.log", root / "telemetry", skipselect=True, width=1024, height=1024,
                     config_updates={"UIScale": profile["environment"]["ui_scale"], "ResetDefaultUIScale": False, "Zoom": 1.0},
                     extra_env={"TERRARIABENCH_PROFILE": profile["profile_id"], "TERRARIABENCH_PVE": "enabled" if args.pve else "disabled",
                                "TERRARIABENCH_REFERENCE_STARTER_PREFIXES": "plain", "TERRARIABENCH_CHECKPOINT_CHAT": "enabled"})
        dump(root / "game.json", {"pid": pid, "profile": str(root / "tml")})
        deadline = time.monotonic() + 100
        while not list((root / "telemetry").glob("*.jsonl")):
            if time.monotonic() > deadline or not Path(f"/proc/{pid}").exists():
                raise RuntimeError("world/observer startup failed")
            time.sleep(.5)
        game = GameControl(pid, root / "inputs.jsonl", width=1024, height=1024, max_hold_ms=2000)
        game.setup_window()
        started = time.monotonic()
        planner = threading.Thread(target=planner_loop, name="planner", daemon=True)
        planner.start()
        time.sleep(.5)
        stop_reason, step, errors = "wall_limit", 0, 0
        step_fn = haiku_step if args.executor == "haiku" else jev_step
        while time.monotonic() - started < args.seconds:
            if stop.is_set():
                stop_reason = fatal[0] if fatal else "planner_stopped"
                break
            try:
                n, ui = ui_queue.get_nowait()
                receipts = game.act(ui)
                with lock:
                    executed.append({"source": f"planner_ui_{n}", "at_s": round(time.monotonic() - started)})
                log({"role": "planner_ui", "n": n, "actions": ui, "receipts": len(receipts), "unix": time.time()})
                continue
            except queue.Empty:
                pass
            with lock:
                objective, recent = plan["objective"], [e["source"] for e in executed[-4:]]
            try:
                actions, summary, status, latency, n, frame, meta, detail = step_fn(objective, recent)
                receipts = game.act(actions) if actions else (time.sleep(.3) or [])
                with lock:
                    executed.append({"source": summary, "at_s": round(time.monotonic() - started)})
                if status in ("done", "stuck"):
                    replan_now.set()
                log({"role": "executor", "n": n, "step": step, "objective": objective, "summary": summary, "status": status,
                     "actions": actions, "latency": latency, "frame": str(frame.relative_to(root)), "observed_unix": meta["captured_unix"],
                     "first_input_unix": receipts[0]["started_unix"] if receipts else None, **detail, "unix": time.time()})
                step += 1
            except (ProviderError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                errors += 1
                log({"role": "executor", "step": step, "error": f"{type(error).__name__}: {error}"[:300], "unix": time.time()})
                if errors >= 40:
                    stop_reason = "executor_error_limit"
                    break
                time.sleep(1 if not isinstance(error, ProviderError) or error.sent else 5)
        game.capture(root / "final.png")
    except Exception as error:
        stop_reason = f"{type(error).__name__}: {error}"
    finally:
        stop.set()
        end = time.time()
        if game:
            game.close()
        if pid:
            dump(root / "termination.json", stop_owned_game(pid, root / "tml"))
        events = load_reference_events(root / "telemetry") if list((root / "telemetry").glob("*.jsonl")) else []
        dump(root / "evaluation-events.json", events)
        receipts = [json.loads(s) for s in (root / "inputs.jsonl").read_text().splitlines()] if (root / "inputs.jsonl").exists() else []
        started_unix = end - (time.monotonic() - started) if started else end
        result = {"protocol": "combo-v1", "config": manifest["config"], "stop_reason": stop_reason, "frames": frame_n[0],
                  "input_commands": len(receipts), "active_wall_seconds": time.monotonic() - started if started else 0,
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
    p.add_argument("--planner", default="claude-sonnet-5-5", choices=sorted(gateway.MODELS))
    p.add_argument("--planner-reasoning", default="low")
    p.add_argument("--executor", choices=("haiku", "jev"), required=True)
    p.add_argument("--seconds", type=int, default=1800)
    p.add_argument("--usd-planner", type=float, default=5)
    p.add_argument("--usd-executor", type=float, default=3)
    p.add_argument("--jev-frames", type=int, default=3)
    p.add_argument("--pve", action="store_true")
    p.add_argument("--allow-open-inventory", action="store_true", help="let Jev open the inventory (default: only close it)")
    run(p.parse_args())


if __name__ == "__main__":
    main()
