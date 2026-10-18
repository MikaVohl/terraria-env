"""Live side panel for watching runs over Moonlight. Read-only: tails the files a run writes.

Finds the most recently active run under runs/ (one with a live game.json and recent
inputs/decisions) and streams the agent's decisions and inputs:

  hybrid runs   planner goals, executor choices (latency, observation age, Jev confidence), actions
  single runs   each model response: reasoning excerpt, tool calls (look/act) and their inputs
  status line   condition, task, game seconds, HP, wood, target HP, cost so far

Run inside a terminal placed beside the game window: python tools/live_panel.py
"""
import json
import os
from pathlib import Path
import shutil
import sys
import textwrap
import time

ROOT = Path(__file__).resolve().parents[1] / "runs"
DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"
COLOR = {"planner": "\033[35m", "executor": "\033[36m", "input": "\033[33m", "model": "\033[32m", "error": "\033[31m", "status": "\033[34m"}


def width():
    return shutil.get_terminal_size((120, 40)).columns


def say(kind, text):
    text = " ".join(str(text).split())
    lines = textwrap.wrap(text, width=max(40, width() - 1), subsequent_indent="    ") or [""]
    print(COLOR.get(kind, "") + "\n".join(lines) + RESET, flush=True)


def active_run():
    """Newest run directory whose game is still alive."""
    best = None
    for game in ROOT.glob("*/*/game.json"):
        run = game.parent
        if (run / "result.json").exists():
            continue
        try:
            pid = json.loads(game.read_text())["pid"]
        except (OSError, ValueError, KeyError):
            continue
        cmdline = Path(f"/proc/{pid}/cmdline")
        # Owned game processes carry their run's profile path; reject reused PIDs.
        if not cmdline.exists() or str(run.resolve() / "tml").encode() not in cmdline.read_bytes():
            continue
        mtime = max((p.stat().st_mtime for p in (run / "inputs.jsonl", run / "decisions.jsonl", game) if p.exists()), default=0)
        if best is None or mtime > best[0]:
            best = (mtime, run)
    return best[1] if best else None


def fmt_actions(actions):
    parts = []
    for a in actions or []:
        bits = []
        if a.get("keys"):
            bits.append("+".join(a["keys"]))
        if a.get("mouse"):
            bits.append(f'{a["mouse"]}@{a.get("x")},{a.get("y")}')
        parts.append(f'{"/".join(bits) or "-"} {a.get("ms", 100)}ms')
    return "; ".join(parts) or "(no input)"


class Tail:
    def __init__(self, path):
        self.path, self.pos = path, 0

    def lines(self):
        if not self.path.exists():
            return []
        with self.path.open() as f:
            f.seek(self.pos)
            data = f.read()
        complete = data[: data.rfind("\n") + 1]
        self.pos += len(complete.encode())
        return [json.loads(s) for s in complete.splitlines() if s.strip()]


def status(run, manifest, started):
    parts = [run.name]
    cfg = manifest.get("config", {})
    parts.append(cfg.get("condition") or f'single {manifest.get("model", {}).get("id", "")}')
    parts.append(cfg.get("scenario", ""))
    state_path = run / "agent-state.json"
    heartbeats = []
    tel = list((run / "telemetry").glob("*.jsonl"))
    if tel:
        try:
            heartbeats = [json.loads(s) for s in tel[0].read_text().splitlines() if '"heartbeat"' in s]
        except (OSError, ValueError):
            pass
    if heartbeats:
        hb = heartbeats[-1]
        t = hb.get("target") or {}
        wood = sum(i["stack"] for i in hb.get("inventory", []) if i.get("name") == "Wood")
        parts += [f'game {(hb["game_updates"] - heartbeats[0]["game_updates"]) / 60:.0f}s', f'HP {hb["life"]}', f"wood {wood}"]
        if t.get("slot", -1) >= 0:
            parts.append(f'target {"KILLED" if t.get("killed") else str(t.get("life")) + "HP"}')
    elif state_path.exists():
        parts.append("starting")
    cost = 0.0
    for acc in [run / "accounting.json"]:
        if acc.exists():
            try:
                cost = float(json.loads(acc.read_text())["reported_usd"])
            except (OSError, ValueError, KeyError):
                pass
    calls = run / "calls"
    if calls.exists():
        for p in calls.glob("*-response.json"):
            try:
                cost += float((json.loads(p.read_text()).get("usage") or {}).get("cost") or 0)
            except (OSError, ValueError):
                pass
    parts.append(f"${cost:.4f}")
    parts.append(f"wall {time.time() - started:.0f}s")
    return " | ".join(p for p in parts if p)


def follow(run):
    print("\033[2J\033[H", end="")
    say("status", f"{BOLD}watching {run}{RESET}")
    try:
        manifest = json.loads((run / "manifest.json").read_text())
    except (OSError, ValueError):
        manifest = {}
    decisions, inputs, tools = Tail(run / "decisions.jsonl"), Tail(run / "inputs.jsonl"), Tail(run / "tool-results.jsonl")
    shown_responses = set()
    started, last_status = time.time(), 0
    hybrid = (run / "calls").exists()
    while not (run / "result.json").exists() and active_run() == run:
        for d in decisions.lines():
            role = d.get("role")
            if "error" in d or "fatal" in d:
                say("error", f'[{role}] {d.get("error") or d.get("fatal")}')
            elif role == "planner":
                say("planner", f'[planner {d["latency"]:.1f}s] GOAL: {d["goal"]}' + (f' (+{d["ui_actions"]} UI actions)' if d.get("ui_actions") else ""))
            elif role == "planner_ui":
                say("planner", f'[planner UI] {fmt_actions(d["actions"])}')
            elif role == "executor":
                age = d["first_input_unix"] - d["observed_unix"] if d.get("first_input_unix") else None
                conf = f' conf {d["confidence"]:.2f}' if d.get("confidence") is not None else ""
                sub = f' sub={d["subgoal"]}' if d.get("subgoal") else ""
                say("executor", f'[exec {d["latency"]:.2f}s' + (f' age {age:.2f}s' if age is not None else "") +
                    f'] {d["choice"]}{conf}{sub} -> {fmt_actions(d["actions"])}')
        if not hybrid:
            for p in sorted(run.glob("response-*.json")):
                if p.name in shown_responses:
                    continue
                try:
                    msg = json.loads(p.read_text())["choices"][0]["message"]
                except (OSError, ValueError, KeyError, IndexError):
                    continue
                shown_responses.add(p.name)
                reasoning = (msg.get("reasoning") or msg.get("content") or "").strip()
                if reasoning:
                    say("model", f'[{p.stem}] {reasoning[:400]}')
                for call in msg.get("tool_calls") or []:
                    try:
                        args = json.loads(call["function"]["arguments"])
                    except (ValueError, KeyError):
                        args = {}
                    say("model", f'  -> {call["function"]["name"]} {fmt_actions(args.get("actions")) if args.get("actions") else ""}')
            for t in tools.lines():
                if "error" in t.get("result", {}):
                    say("error", f'  tool error: {t["result"]["error"]}')
        if not hybrid:
            for r in inputs.lines():
                say("input", f'  input {fmt_actions([r["action"]])}')
        else:
            inputs.lines()
        if time.time() - last_status > 2:
            say("status", f"{DIM}{status(run, manifest, started)}{RESET}")
            last_status = time.time()
        time.sleep(.25)
    if (run / "result.json").exists():
        try:
            result = json.loads((run / "result.json").read_text())
            m = result["metrics"]
            say("status", f'{BOLD}DONE {run.name}: {result["stop_reason"]} | milestones {m["public_subset_score"]["milestones"]} | '
                          f'target dmg {m["player_damage_to_target"]} killed {m["target_killed"]} | deaths {m["deaths"]}{RESET}')
        except (OSError, ValueError, KeyError):
            pass


def main():
    os.environ.setdefault("TERM", "xterm-256color")
    say("status", f"Live panel: waiting for an active run under {ROOT}")
    while True:
        run = active_run()
        if run:
            follow(run)
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
