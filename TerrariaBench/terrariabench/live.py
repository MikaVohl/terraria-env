"""Small screenshot/uinput development runner. Always an unofficial result."""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import time

from .linux_control import GameControl, WIDTH, HEIGHT, KEY_NAMES, launch, validate_actions
from .openrouter import Budget, hermes_key, model_metadata, request
from .scoring import read_journal, score

SYSTEM = """You control Terraria through screenshots and real keyboard/mouse inputs.
Your goal for this development smoke is harvest at least 25 wood, then craft a
workbench using the normal inventory UI. Start with the standard starter items.
Hotbar 1 is sword, 2 pickaxe, 3 axe. Select 3 and hold left mouse near a tree's
base to chop it. Walk near drops to collect. A/D walk, Space jumps, Esc toggles
inventory. Craft through the inventory crafting panel. The game keeps running
while you think. Watch enemies and recover from mistakes.

The screenshot is 1280x720; coordinates refer to those pixels. Each action is
an object with optional keys (list of names), mouse (left/right/middle), x and y,
and ms (20..1000 milliseconds). Combine held keys and mouse in the same action.
You may return 1..16 actions per response; they execute open-loop with no
intermediate observation. A wait is {"ms":100}. Allowed keys: a-z, 0-9, space,
esc, enter, backspace, tab, leftshift, leftctrl, up, down, left, right, minus.

Return JSON only: {"notes":"your bounded memory and plan", "actions":[...] }.
Do not claim completion from guesses. You have no shell, filesystem, hidden map,
telemetry or game-state API. Your notes carry between calls, plus the previous
four action batches. Do not interact with any application outside the game.
"""

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["notes", "actions"],
          "properties": {"notes": {"type": "string", "maxLength": 2000},
                         "actions": {"type": "array", "minItems": 1, "maxItems": 16,
                                     "items": {"type": "object", "additionalProperties": False,
                                               "properties": {"keys": {"type": "array", "items": {"type": "string", "enum": list(KEY_NAMES)}},
                                                              "mouse": {"type": "string", "enum": ["left", "right", "middle"]},
                                                              "x": {"type": "integer"}, "y": {"type": "integer"},
                                                              "ms": {"type": "integer", "minimum": 20, "maximum": 1000}}}}}}


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file() and p.suffix in (".py", ".cs", ".json", ".plr", ".wld", ".tplr", ".twld", ".tmod")
            and "__pycache__" not in p.parts}


def pixel_actions(actions, coordinate_system):
    """Representation-only mapping; no perception, aiming or strategy helper."""
    if coordinate_system == "pixels":
        return validate_actions(actions)
    if coordinate_system != "normalized1000" or not isinstance(actions, list):
        raise ValueError("invalid coordinate system/actions")
    converted = []
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("invalid action")
        action = dict(action)
        for name, size in (("x", WIDTH), ("y", HEIGHT)):
            if name in action:
                value = action[name]
                if type(value) is not int or not 0 <= value <= 1000:
                    raise ValueError("normalized coordinate must be 0..1000")
                action[name] = min(size-1, round(value*size/1000))
        converted.append(action)
    return validate_actions(converted)


def run(args):
    # Do not read credentials until local arguments and catalog are verified.
    if args.calls < 1 or args.calls > 64 or not 1 <= args.seconds <= 1800 or not 0 < args.usd <= 1:
        raise ValueError("development ceiling: 64 calls, 1800 seconds, $1")
    fixture, root = args.fixture.resolve(), args.output.resolve()
    if root.is_relative_to(fixture):
        raise ValueError("run output must be outside the immutable fixture")
    if not list((fixture / "Players").glob("*.plr")) or not list((fixture / "Worlds").glob("*.wld")):
        raise ValueError("fixture requires a real player and world")
    model = model_metadata(args.model)
    budget = Budget(args.usd, model["pricing"])
    key = hermes_key()
    root.mkdir(parents=True, exist_ok=False)
    profile = root / "tml"
    shutil.copytree(fixture, profile, ignore=shutil.ignore_patterns("Logs", "*.log", "*.bak"))
    telemetry = root / "telemetry"
    shutil.copytree(Path(__file__).parent, root / "source/terrariabench", ignore=shutil.ignore_patterns("__pycache__"))
    system_prompt = SYSTEM
    if args.coordinates == "normalized1000":
        system_prompt = SYSTEM.replace(
            "The screenshot is 1280x720; coordinates refer to those pixels.",
            "The screenshot image is 1280x720 pixels. For your action output use NORMALIZED coordinates from 0 to 1000 on EACH axis: x=0 is left, x=1000 right, y=0 top, y=1000 bottom. The image center is x=500,y=500. Do NOT output pixel coordinates. The controller converts normalized positions to pixels without adding any perception or strategy.")
    response_schema = copy.deepcopy(SCHEMA)
    for name, limit in (("x", 1000 if args.coordinates == "normalized1000" else WIDTH-1),
                        ("y", 1000 if args.coordinates == "normalized1000" else HEIGHT-1)):
        response_schema["properties"]["actions"]["items"]["properties"][name].update(minimum=0, maximum=limit)
    manifest = {"status": "development_smoke", "official_eligible": False,
                "track": "visual-realtime-primitive", "model": model,
                "fixture_hashes": hashes(fixture), "source_hashes": hashes(Path(__file__).parent),
                "calls_limit": args.calls, "wall_seconds_limit": args.seconds,
                "primitive_actions_limit": 512, "total_tokens_limit": 250000,
                "output_tokens_per_call": budget.output_ceiling,
                "history": "current image, model-authored notes, previous four action batches",
                "coordinate_system": args.coordinates,
                "system_prompt": system_prompt, "response_schema": response_schema,
                "key_source": "remote Hermes; credential never persisted",
                "tmodloader_sha256": hashlib.sha256((Path.home()/".local/share/Steam/steamapps/common/tModLoader/tModLoader.dll").read_bytes()).hexdigest(),
                "started_unix": time.time()}
    dump(root / "manifest.json", manifest)
    pid, game, calls, primitives = None, None, 0, 0
    notes, history, invalid = "", [], 0
    stop = "not_started"
    try:
        pid = launch(profile, root / "client.log", telemetry, skipselect=True)
        dump(root / "game.json", {"pid": pid, "profile": str(profile)})
        deadline = time.monotonic() + 100
        while not list(telemetry.glob("*.jsonl")):
            if time.monotonic() > deadline:
                raise RuntimeError("world/observer startup timeout")
            time.sleep(.5)
        game = GameControl(pid, root / "inputs.jsonl")
        game.setup_window()
        start = time.monotonic()
        stop = "model_call_limit"
        for step in range(args.calls):
            # Evaluator termination only; checkpoint data never enters model input.
            journals = sorted(telemetry.glob("*.jsonl"))
            if journals:
                facts = score(read_journal(journals[-1]))["first_unlocks"]
                if {"wood_25", "possess_workbench"} <= facts.keys():
                    stop = "smoke_objective_observed"
                    break
            if time.monotonic() - start >= args.seconds:
                stop = "wall_limit"
                break
            if primitives >= 512 or budget.tokens >= 250000:
                stop = "action_or_token_limit"
                break
            frame = root / "frames" / f"{step:05d}.png"
            capture = game.capture(frame)
            context = {"step": step, "notes": notes, "previous_actions": history[-4:],
                       "elapsed_seconds": round(time.monotonic() - start, 2)}
            payload = {"model": args.model, "stream": False, "temperature": .2,
                       "max_tokens": budget.output_ceiling, "reasoning": {"effort": "low"},
                       "provider": {"allow_fallbacks": False, "require_parameters": True},
                       "response_format": {"type": "json_schema", "json_schema": {"name": "terraria_inputs", "strict": False, "schema": response_schema}},
                       "messages": [{"role": "system", "content": system_prompt},
                                    {"role": "user", "content": [
                                        {"type": "text", "text": json.dumps(context)},
                                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(frame.read_bytes()).decode()}}]}]}
            # Archive image references and exact text, never Authorization headers.
            dump(root / f"request-{step:03d}.json", {"context": context, "capture": capture,
                 "frame_sha256": hashlib.sha256(frame.read_bytes()).hexdigest(),
                 "model": args.model, "generation": {k: v for k, v in payload.items() if k != "messages"}})
            budget.reserve()
            began = time.monotonic()
            calls += 1
            response = request("/chat/completions", key=key, payload=payload,
                               timeout=min(60, max(1, args.seconds - (time.monotonic() - start))))
            dump(root / f"response-{step:03d}.json", response)
            budget.reconcile(response.get("usage"))
            dump(root / "accounting.json", budget.summary())
            if response.get("model") != args.model:
                raise RuntimeError("returned model differs from requested model")
            if time.monotonic() - start >= args.seconds:
                stop = "wall_limit_after_response"
                break
            try:
                content = response["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if not isinstance(parsed, dict) or set(parsed) != {"notes", "actions"}:
                    raise ValueError("wrong response fields")
                if not isinstance(parsed["notes"], str) or len(parsed["notes"]) > 2000:
                    raise ValueError("invalid notes")
                actions = pixel_actions(parsed["actions"], args.coordinates)
                if primitives + len(actions) > 512:
                    stop = "primitive_action_limit"
                    break
                # An atomic batch must fit both budgets before input dispatch.
                if time.monotonic() - start + sum(a.get("ms", 100)/1000 + .15 for a in actions) > args.seconds:
                    stop = "wall_limit_before_batch"
                    break
                game.act(actions)
                notes = parsed["notes"]
                history.append(parsed["actions"])
                primitives += len(actions)
            except (ValueError, KeyError, IndexError, TypeError) as error:
                dump(root / f"invalid-{step:03d}.json", {"error": str(error), "policy": "100ms noop; third invalid output stops run"})
                invalid += 1
                game.act([{"ms": 100}])
                primitives += 1
                notes = notes[:1800] + " Previous response was invalid; return bounded JSON actions."
                if invalid >= 3:
                    stop = "invalid_output_limit"
                    break
            print(json.dumps({"step": step, "latency_seconds": round(time.monotonic()-began, 2),
                              "actions": primitives, "usd": str(budget.spent)}), flush=True)
        game.capture(root / "final.png")
    except Exception as error:
        # Sanitized exception messages only; never print locals/request headers.
        stop = type(error).__name__ + ": " + str(error).replace(key, "[redacted]")
    finally:
        if game:
            game.close()
        if pid:
            try:
                # Process launched by this attempt only; no shared process-name kills.
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        result = {"official_eligible": False, "stop_reason": stop, "calls": calls,
                  "primitive_actions": primitives, "invalid_outputs": invalid, "accounting": budget.summary()}
        for journal in sorted(telemetry.glob("*.jsonl")) if telemetry.exists() else []:
            try:
                result["observed_progress"] = score(read_journal(journal))
            except ValueError as error:
                result["journal_error"] = str(error)
        dump(root / "result.json", result)
        from .report import render
        render(root)
        print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="google/gemini-3.8-flash")
    parser.add_argument("--calls", type=int, default=24)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--usd", type=float, default=1)
    parser.add_argument("--coordinates", choices=("pixels", "normalized1000"), default="pixels")
    result = run(parser.parse_args())
    if result["stop_reason"].startswith(("RuntimeError", "ValueError")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
