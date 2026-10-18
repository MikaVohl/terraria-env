"""Real-time planner/executor agents sharing one live game. The game is never paused.

A slow planner thread sets the current goal; a fast executor loop acts on the newest
observation without waiting for the planner. Conditions:

  ll-pixel  Haiku planner (screenshot) + Haiku executor (fresh screenshot, raw pixel actions)
  ll-state  Haiku planner (screenshot + agent state) + Haiku executor (agent state, action catalog)
  lj-state  Haiku planner (screenshot + agent state) + Jev executor (agent state, action catalog)
  jev       Jev alone: subgoal and action choices from agent state

"Agent state" is privileged structured observation from observer v0.6 (tree trunks,
hostiles, drops and terrain with screen coordinates). Jev is reached through OpenRouter,
which forwards text state only. Catalog options expand to ordinary keyboard/mouse input.
"""
import argparse
import base64
import copy
from decimal import Decimal
import json
from pathlib import Path
import queue
import statistics
import threading
import time

from .experiments import Ledger, dump, digest, metrics, read_events, snapshot_inputs, start_game, stop_game, model_pricing
from .linux_control import validate_actions
from .openrouter import Budget, ProviderError, decide, hermes_key, request

PLANNER_MODEL = "anthropic/claude-haiku-5.5"
EXECUTOR_MODEL = "anthropic/claude-haiku-5.5"
JEV_MODEL = "typesafe/jev-1.14"
JEV_PRICING = {"prompt": "0.000000042", "completion": "0", "request": "0"}  # TypeSafe list price; output free
CONDITIONS = {
    "ll-pixel": {"planner": "llm", "planner_state": False, "executor": "llm-pixel"},
    "ll-state": {"planner": "llm", "planner_state": True, "executor": "llm-catalog"},
    "lj-state": {"planner": "llm", "planner_state": True, "executor": "jev"},
    "jev": {"planner": "jev", "planner_state": True, "executor": "jev"},
    # Unpaid reference: a fixed priority rule over the same catalog, no model.
    "scripted": {"planner": None, "planner_state": False, "executor": "rule"},
}
RULE_PRIORITY = {
    "fresh": ("attack", "chop_tree", "collect_drop", "approach_tree", "walk_right"),
    "slime": ("attack", "approach_hostile", "chop_tree", "collect_drop", "approach_tree", "walk_right"),
}
TASKS = {
    "fresh": "Fresh character and world. Gather wood from trees, craft a workbench, and keep making progress. Hostile mobs are enabled: survive.",
    "slime": "A blue slime starts nearby. Defeat it with your starter equipment while avoiding damage, then keep making progress.",
}
CONTROLS = ("Terraria, 1024x1024 window, game runs in real time and never pauses. Controls: A/D walk, space jumps, "
            "number keys select hotbar slots (1 sword, 2 pickaxe, 3 axe), left mouse uses the held item at the cursor, "
            "escape toggles the inventory, whose crafting list is at the lower left.")
SUBGOALS = {
    "gather_wood": "Walk to the nearest tree and chop it with the axe.",
    "collect_drops": "Pick up dropped items by walking over them.",
    "fight_hostile": "Attack the nearest hostile creature with the sword.",
    "evade_hostile": "Move away from a dangerous hostile creature.",
    "explore_left": "Travel left to find trees or resources.",
    "explore_right": "Travel right to find trees or resources.",
}
PIXEL_HOLD_MS = 800


def read_state(path):
    for _ in range(5):
        try:
            return json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError):
            time.sleep(.02)
    raise RuntimeError("agent_state_unavailable")


def compact_state(s):
    """The text observation given to state-based deciders (screen coordinates omitted)."""
    strip = lambda rows: [{k: v for k, v in r.items() if k not in ("sx", "sy")} for r in rows]
    p = s["player"]
    return {"player": {k: p[k] for k in ("life", "life_max", "dead", "on_ground", "facing", "held", "inventory_open")},
            "hotbar": [f'{h["key"]}:{h["name"]}' for h in s["hotbar"] if h["name"]], "wood": s["wood"],
            "terrain": s["terrain"], "trees": strip(s["trees"]), "hostiles": strip([h for h in s["hostiles"] if h["on_screen"]]),
            "drops": strip(s["items"])}


def _slot(s, kind):
    return next((h["key"] for h in s["hotbar"] if h[kind]), None)


def _walk(direction, s, ms=400):
    side = "left" if direction < 0 else "right"
    keys = ["a" if direction < 0 else "d"] + (["space"] if s["terrain"]["wall_" + side] >= 2 else [])
    return [{"keys": keys, "ms": ms}]


def catalog(s):
    """Options valid in this state: key -> (description, actions). Every option is ordinary input."""
    opts = {"wait": ("Do nothing for a moment.", []),
            "walk_left": (f'Walk left briefly (wall height {s["terrain"]["wall_left"]}, drop {s["terrain"]["drop_left"]} tiles).', _walk(-1, s)),
            "walk_right": (f'Walk right briefly (wall height {s["terrain"]["wall_right"]}, drop {s["terrain"]["drop_right"]} tiles).', _walk(1, s)),
            "jump_left": ("Jump while moving left.", [{"keys": ["space", "a"], "ms": 400}]),
            "jump_right": ("Jump while moving right.", [{"keys": ["space", "d"], "ms": 400}])}
    if s["player"]["inventory_open"]:
        opts["close_inventory"] = ("Close the open inventory screen.", [{"keys": ["escape"], "ms": 60}])
    axe, sword = _slot(s, "axe"), _slot(s, "melee")
    if s["trees"]:
        t = s["trees"][0]
        if t["in_reach"] and axe:
            opts["chop_tree"] = (f'Hold the axe on the trunk of the nearest tree ({t["dx"]} tiles away); it falls and drops wood after several hits.',
                                 [{"keys": [axe], "ms": 50}, {"x": t["sx"], "y": t["sy"], "mouse": "left", "ms": 700}])
        elif t["dx"]:
            opts["approach_tree"] = (f'Walk toward the nearest tree ({t["dx"]} tiles {"left" if t["dx"] < 0 else "right"}).', _walk(t["dx"], s))
    if s["items"] and s["items"][0]["dx"]:
        d = s["items"][0]
        opts["collect_drop"] = (f'Walk toward dropped {d["name"]} x{d["stack"]} ({d["dx"]} tiles).', _walk(d["dx"], s))
    visible = [h for h in s["hostiles"] if h["on_screen"]]
    if visible:
        h = visible[0]
        where = f'{h["name"]} at dx {h["dx"]}, dy {h["dy"]}, life {h["life"]}/{h["life_max"]}'
        if abs(h["dx"]) <= 4 and abs(h["dy"]) <= 3 and sword:
            opts["attack"] = (f"Stab the nearest hostile with the sword: {where}.",
                              [{"keys": [sword], "ms": 50}, {"x": h["sx"], "y": h["sy"], "mouse": "left", "ms": 300}])
        elif h["dx"]:
            opts["approach_hostile"] = (f"Walk toward the nearest hostile: {where}.", _walk(h["dx"], s))
        if h["dx"]:
            away = 1 if h["dx"] < 0 else -1
            opts["retreat"] = (f"Jump away from the nearest hostile: {where}.", [{"keys": ["space", "d" if away > 0 else "a"], "ms": 450}])
    for _, actions in opts.values():
        if actions:
            validate_actions(actions, width=1024, height=1024, max_hold_ms=2000)
    return opts


class Role:
    """Accounting and call logging for one model role; failed attempts stay uncertain charges."""

    def __init__(self, name, root, ledger, budget):
        self.name, self.root, self.ledger, self.budget = name, root, ledger, budget
        self.calls = self.failures = 0
        self.latencies = []
        self.lock = threading.Lock()

    def call(self, fn, payload, archived):
        with self.lock:
            n = self.calls
            self.calls += 1
            self.budget.reserve()
            key = f"{self.root.name}#{self.name}{n:04d}"
            try:
                self.ledger.change(key, reserve=self.budget.reservation)
            except Exception:
                self.budget.pending = Decimal(0)
                raise
        dump(self.root / "calls" / f"{self.name}-{n:04d}-request.json", archived)
        t0 = time.monotonic()
        try:
            response = fn(payload)
        except ProviderError:
            with self.lock:
                self.failures += 1
                self.budget.abandon()
            raise
        latency = time.monotonic() - t0
        dump(self.root / "calls" / f"{self.name}-{n:04d}-response.json", response)
        usage = response.get("usage")
        with self.lock:
            self.latencies.append(latency)
            try:
                self.budget.reconcile(usage)
            finally:
                if usage and usage.get("cost") is not None:
                    self.ledger.change(key, charge=Budget.decimal(usage["cost"]))
        return response, latency, n


def image_part(path):
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()}}


def archive_messages(payload, paths):
    """Replace inline images with artifact references and hashes for the stored request."""
    stored, it = copy.deepcopy(payload), iter(paths)
    for msg in stored.get("messages", []):
        if isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if part.get("type") == "image_url":
                    p = next(it)
                    part["image_url"] = {"artifact": str(p), "sha256": digest(p)}
    return stored


def json_content(response):
    text = (response["choices"][0]["message"].get("content") or "").strip()
    # Haiku sometimes wraps JSON-mode output in one markdown fence; accept exactly that wrapper.
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].removeprefix("json").strip()
    body = json.loads(text)
    if not isinstance(body, dict):
        raise ValueError("expected a JSON object")
    return body


def run(args):
    cond = CONDITIONS[args.condition]
    if args.scenario not in TASKS or not 10 <= args.sim_seconds <= 600 or not 0 < args.usd <= 1:
        raise ValueError("invalid hybrid bounds")
    root, fixture = args.output.resolve(), args.fixture.resolve()
    if root.exists() or root.is_relative_to(fixture):
        raise ValueError("new output outside fixture required")
    ledger = Ledger(args.campaign)
    catalog_models = {m["id"]: m for m in request("/models")["data"]}
    key = hermes_key()
    root.mkdir(parents=True)
    (root / "calls").mkdir()
    source_hashes, fixture_hashes = snapshot_inputs(root, fixture)
    roles = {}
    if cond["planner"] == "llm":
        roles["planner"] = Role("planner", root, ledger, Budget(args.usd / 2, model_pricing(catalog_models[PLANNER_MODEL]), input_ceiling=32768, output_ceiling=2048))
    if cond["executor"] == "jev":
        roles["executor"] = Role("executor", root, ledger, Budget(args.usd / 2, JEV_PRICING, input_ceiling=32768, output_ceiling=4096))
    elif cond["executor"] != "rule":
        roles["executor"] = Role("executor", root, ledger, Budget(args.usd / 2, model_pricing(catalog_models[EXECUTOR_MODEL]), input_ceiling=16384, output_ceiling=512))
    state_file = root / "agent-state.json"
    config = {"condition": args.condition, **cond, "scenario": args.scenario, "pve": True, "clock": "realtime",
              "planner_model": {"llm": PLANNER_MODEL, "jev": JEV_MODEL}.get(cond["planner"]),
              "executor_model": {"jev": JEV_MODEL, "rule": None}.get(cond["executor"], EXECUTOR_MODEL),
              "planner_reasoning": "low", "executor_reasoning": "none", "pixel_hold_ms": PIXEL_HOLD_MS}
    manifest = {"protocol": "planner-executor-v1", "config": config, "task": TASKS[args.scenario], "controls": CONTROLS,
                "subgoals": SUBGOALS, "limits": {"simulation_seconds": args.sim_seconds, "wall_seconds": args.seconds, "usd": args.usd},
                "privileged_state": cond["planner_state"] or cond["executor"] != "llm-pixel",
                "source_hashes": source_hashes, "fixture_hashes": fixture_hashes, "official_eligible": False, "started_unix": time.time()}
    dump(root / "manifest.json", manifest)

    lock = threading.Lock()
    stop = threading.Event()
    plan = {"goal": "Start: " + TASKS[args.scenario], "notes": "", "version": 0}
    ui_queue = queue.Queue()
    log_lock = threading.Lock()
    executed = []  # (choice/actions summary) for planner context
    frame_n = [0]
    pid = game = None
    stop_reason = "startup"
    start_tick = 0
    started_wall = None
    scenario_ready = None

    def log(entry):
        with log_lock, (root / "decisions.jsonl").open("a") as s:
            s.write(json.dumps(entry) + "\n")

    def capture():
        with lock:
            n = frame_n[0]
            frame_n[0] += 1
        path = root / "frames" / f"{n:05d}.png"
        meta = game.capture(path)
        return path, meta

    def game_updates():
        return max((e["game_updates"] for e in read_events(root)), default=start_tick) - start_tick

    def planner_loop():
        role = roles["planner"]
        while not stop.is_set():
            try:
                frame, meta = capture()
                state = read_state(state_file) if cond["planner_state"] else None
                with lock:
                    recent = executed[-10:]
                    current = dict(plan)
                text = {"task": TASKS[args.scenario], "your_previous_notes": current["notes"], "current_goal": current["goal"],
                        "recent_executor_actions": recent}
                if state:
                    text["agent_state"] = compact_state(state)
                content = [{"type": "text", "text": json.dumps(text)}, image_part(frame)]
                payload = {"model": PLANNER_MODEL, "max_tokens": 2048, "stream": False, "reasoning": {"effort": "low"},
                           "response_format": {"type": "json_object"},
                           "provider": {"allow_fallbacks": False, "require_parameters": True},
                           "messages": [{"role": "system", "content": CONTROLS + " You are the PLANNER. A separate fast executor plays in real time and "
                                         "follows your goal. Reply with one JSON object: goal (what the executor should do now, max 300 chars), "
                                         "notes (your memory, max 1000 chars), and optional ui_actions (1..16 raw actions "
                                         '{"keys":[...],"mouse":"left|right","x":0-1023,"y":0-1023,"ms":20-2000} for inventory/crafting menus only; '
                                         "the executor is suspended while they run)."},
                                        {"role": "user", "content": content}]}
                response, latency, n = role.call(lambda p: request("/chat/completions", key=key, payload=p, timeout=60),
                                                 payload, archive_messages(payload, [frame]))
                body = json_content(response)
                goal, notes = str(body.get("goal", ""))[:300], str(body.get("notes", ""))[:1000]
                ui = body.get("ui_actions") or []
                if ui:
                    validate_actions(ui, width=1024, height=1024, max_hold_ms=2000)
                    ui_queue.put((n, ui))
                with lock:
                    plan.update(goal=goal or plan["goal"], notes=notes, version=plan["version"] + 1)
                log({"role": "planner", "n": n, "frame": str(frame.relative_to(root)), "frame_unix": meta["captured_unix"],
                     "latency": latency, "goal": goal, "ui_actions": len(ui), "unix": time.time()})
            except (ProviderError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                log({"role": "planner", "error": f"{type(error).__name__}: {error}", "unix": time.time()})
                stop.wait(2.0)
            except Exception as error:  # budget exhaustion or game failure ends the run
                log({"role": "planner", "fatal": f"{type(error).__name__}: {error}", "unix": time.time()})
                stop.set()

    def execute(actions, source):
        if not actions:
            time.sleep(.25)
            return []
        receipts = game.act(actions)
        with lock:
            executed.append({"source": source, "actions": len(actions), "at_game_s": round(game_updates() / 60, 1)})
        return receipts

    def executor_step(step):
        role = roles.get("executor")
        with lock:
            goal = plan["goal"]
            recent = [e["source"] for e in executed[-4:]]
        if cond["executor"] == "llm-pixel":
            frame, meta = capture()
            payload = {"model": EXECUTOR_MODEL, "max_tokens": 512, "stream": False, "reasoning": {"effort": "none"},
                       "response_format": {"type": "json_object"}, "provider": {"allow_fallbacks": False, "require_parameters": True},
                       "messages": [{"role": "system", "content": CONTROLS + " You are the fast EXECUTOR. Follow the planner's goal using the "
                                     'current screenshot. Reply with JSON only: {"actions":[1..3 actions]}, each action '
                                     '{"keys":[...],"mouse":"left|right","x":0-1023,"y":0-1023,"ms":20-' + str(PIXEL_HOLD_MS) + "}. "
                                     "x,y are screenshot pixels."},
                                    {"role": "user", "content": [{"type": "text", "text": json.dumps({"goal": goal, "your_recent_actions": recent})},
                                                                 image_part(frame)]}]}
            response, latency, n = role.call(lambda p: request("/chat/completions", key=key, payload=p, timeout=30),
                                             payload, archive_messages(payload, [frame]))
            actions = json_content(response)["actions"]
            if not isinstance(actions, list) or not 1 <= len(actions) <= 3:
                raise ValueError("expected 1..3 actions")
            validate_actions(actions, width=1024, height=1024, max_hold_ms=PIXEL_HOLD_MS)
            obs = {"frame": str(frame.relative_to(root)), "observed_unix": meta["captured_unix"]}
            choice = "pixel_actions"
        else:
            state = read_state(state_file)
            opts = catalog(state)
            view = compact_state(state)
            if cond["executor"] == "rule":
                choice = next(k for k in RULE_PRIORITY[args.scenario] if k in opts)
                latency, n, detail = 0.0, step, {}
            elif cond["executor"] == "llm-catalog":
                payload = {"model": EXECUTOR_MODEL, "max_tokens": 64, "stream": False, "reasoning": {"effort": "none"},
                           "response_format": {"type": "json_object"}, "provider": {"allow_fallbacks": False, "require_parameters": True},
                           "messages": [{"role": "system", "content": CONTROLS + " You are the fast EXECUTOR. Choose the one option that best "
                                         'advances the planner goal right now. Reply with JSON only: {"choice":"<option key>"}.'},
                                        {"role": "user", "content": json.dumps({"goal": goal, "state": view, "your_recent_choices": recent,
                                                                                "options": {k: d for k, (d, _) in opts.items()}})}]}
                response, latency, n = role.call(lambda p: request("/chat/completions", key=key, payload=p, timeout=30), payload, payload)
                choice = json_content(response).get("choice")
                detail = {}
            else:
                questions = {"action": {"type": "choice", "criteria": {k: d for k, (d, _) in opts.items()},
                                        "instructions": "Choose the next Terraria player action that best advances `goal` right now. "
                                                        "Survive: avoid hostiles that are close unless attacking them is the goal."}}
                if cond["planner"] == "jev":
                    questions["subgoal"] = {"type": "choice", "criteria": SUBGOALS,
                                            "instructions": "Given `task` and `state`, which subgoal should the player pursue now?"}
                payload = {"model": JEV_MODEL, "state": {"task": TASKS[args.scenario], "goal": goal, "state": view, "recent_actions": recent},
                           "questions": questions}
                response, latency, n = role.call(lambda p: decide(p, key=key, timeout=15), payload, payload)
                answer = response["answers"]["action"]
                choice = answer["choice"]
                detail = {"confidence": answer.get("confidence"), "probabilities": answer.get("probabilities")}
                if cond["planner"] == "jev":
                    sub = response["answers"]["subgoal"]
                    with lock:
                        plan.update(goal=f'{sub["choice"]}: {SUBGOALS[sub["choice"]]}', version=plan["version"] + 1)
                    detail["subgoal"] = sub["choice"]
                    detail["subgoal_confidence"] = sub.get("confidence")
            if choice not in opts:
                raise ValueError(f"choice outside offered options: {choice!r}")
            actions = opts[choice][1]
            obs = {"state_tick": state["tick"], "observed_unix": state["unix"], **detail}
        receipts = execute(actions, choice)
        log({"role": "executor", "n": n, "step": step, "goal": goal, "choice": choice, "actions": actions, "latency": latency,
             "receipts": len(receipts), "first_input_unix": receipts[0]["started_unix"] if receipts else None, **obs,
             "unix": time.time()})

    try:
        pid, game, scenario_ready = start_game(root, config, max_hold_ms=2000,
                                               extra_env={"TERRARIABENCH_STATE_FILE": str(state_file)})
        deadline = time.monotonic() + 10
        while not state_file.exists():
            if time.monotonic() > deadline:
                raise RuntimeError("agent_state_missing")
            time.sleep(.05)
        start_tick = max(e["game_updates"] for e in read_events(root))
        started_wall = time.monotonic()
        planner = None
        if "planner" in roles:
            planner = threading.Thread(target=planner_loop, name="planner", daemon=True)
            planner.start()
        stop_reason = "simulation_limit"
        step = errors = 0
        while True:
            if stop.is_set():
                stop_reason = "planner_fatal"
                break
            if game_updates() >= args.sim_seconds * 60:
                break
            if time.monotonic() - started_wall >= args.seconds:
                stop_reason = "wall_limit"
                break
            try:
                n, ui = ui_queue.get_nowait()
                receipts = execute(ui, f"planner_ui_{n}")
                log({"role": "planner_ui", "n": n, "actions": ui, "receipts": len(receipts), "unix": time.time()})
                continue
            except queue.Empty:
                pass
            try:
                executor_step(step)
                step += 1
            except (ProviderError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                errors += 1
                log({"role": "executor", "step": step, "error": f"{type(error).__name__}: {error}", "unix": time.time()})
                if errors >= 15:
                    stop_reason = "executor_error_limit"
                    break
                time.sleep(.3)
        game.capture(root / "final.png")
    except Exception as error:
        stop_reason = f"{type(error).__name__}: {error}".replace(key, "[redacted]")
    finally:
        stop.set()
        agent_seconds = time.monotonic() - started_wall if started_wall else 0
        time.sleep(.1)
        stop_game(root, pid, game)
        events = read_events(root)
        dump(root / "evaluation-events.json", events)
        receipts = [json.loads(s) for s in (root / "inputs.jsonl").read_text().splitlines()] if (root / "inputs.jsonl").exists() else []
        decisions = [json.loads(s) for s in (root / "decisions.jsonl").read_text().splitlines()] if (root / "decisions.jsonl").exists() else []
        result = {"run": root.name, "config": config, "stop_reason": stop_reason, "scenario_ready": scenario_ready,
                  "agent_wall_seconds": agent_seconds, "commands": len(receipts), "frames": frame_n[0],
                  "roles": {name: {"calls": r.calls, "failures": r.failures, "latency_median": statistics.median(r.latencies) if r.latencies else None,
                                   "latency_p90": sorted(r.latencies)[int(.9 * (len(r.latencies) - 1))] if r.latencies else None,
                                   "accounting": r.budget.summary()} for name, r in roles.items()},
                  "timing": timing(decisions, receipts, agent_seconds),
                  "metrics": metrics(events, receipts, start_tick), "official_eligible": False}
        dump(root / "result.json", result)
        print(json.dumps(result), flush=True)
    return result


def timing(decisions, receipts, agent_seconds):
    """Observation age at first input, executor cadence and share of time spent holding input."""
    ex = [d for d in decisions if d.get("role") == "executor" and d.get("first_input_unix")]
    ages = [d["first_input_unix"] - d["observed_unix"] for d in ex]
    held = sum(r["ended_unix"] - r["started_unix"] for r in receipts)
    return {"executor_decisions": len([d for d in decisions if d.get("role") == "executor" and "choice" in d]),
            "executor_errors": len([d for d in decisions if d.get("role") == "executor" and "error" in d]),
            "planner_updates": len([d for d in decisions if d.get("role") == "planner" and "goal" in d]),
            "observation_age_median": statistics.median(ages) if ages else None,
            "observation_age_p90": sorted(ages)[int(.9 * (len(ages) - 1))] if ages else None,
            "input_held_fraction": held / agent_seconds if agent_seconds else None}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--campaign", type=Path, required=True)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--condition", choices=CONDITIONS, required=True)
    p.add_argument("--scenario", choices=TASKS, default="fresh")
    p.add_argument("--sim-seconds", type=int, default=120)
    p.add_argument("--seconds", type=int, default=240)
    p.add_argument("--usd", type=float, default=.12)
    run(p.parse_args())


if __name__ == "__main__":
    main()
