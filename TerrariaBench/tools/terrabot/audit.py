"""Scripted observer audit of one TerraBot run (journal-checked; no LLM).

    python tools/terrabot/audit.py <run>     # prints and writes <run>/audit.json

Checks every run against the evidence the agent cannot write:
  * journal integrity: observer journal present, start/end events, heartbeats without gaps > 5 game-s;
  * teleport check: heartbeat-to-heartbeat displacement within vanilla limits (falls up to 10 px/tick, run 3 px/tick
    plus slack), except across death/respawn;
  * item provenance: every positive inventory change between heartbeats is explained by game events in that window
    (pickup / crafted / chest take) — unexplained gains are flagged as possible item spawning (coins excluded: they
    convert automatically);
  * crafting provenance: each `craft` action that succeeded has a matching observer `crafted` journal entry
    (RecipeItemCreationContext, i.e. the real recipe code);
  * attribution: every checkpoint the published scorer credits is preceded by an agent tb-api action;
  * forbidden ops: the proxy journal contains only tb-api-1.0 action ops; no test-only ops in a scored run;
  * harness health: program timeouts/errors, game crash (no end event), API errors.
Flags are reported, never silently fixed.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from terrariabench.reference_scoring import reference_score  # noqa: E402

ACTION_OPS = {"input", "stop", "select", "craft", "equip", "take", "put", "close_chest"}


def jl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()] if Path(path).exists() else []


def audit(run):
    run = Path(run)
    flags, notes = [], []
    manifest = json.loads((run / "manifest.json").read_text()) if (run / "manifest.json").exists() else {}
    tele = [e for f in sorted((run / "telemetry").glob("*.jsonl")) for e in jl(f)]
    events = jl(run / "game_events.jsonl")
    actions = jl(run / "inputs.jsonl")
    game_actions = jl(run / "game_actions.jsonl")
    programs = jl(run / "programs.jsonl")
    if not tele:
        flags.append({"kind": "harness", "what": "no observer journal"})
    starts = [e for e in tele if e.get("event") == "start"]
    ends = [e for e in tele if e.get("event") == "end"]
    if not starts:
        flags.append({"kind": "harness", "what": "observer journal has no start event"})
    if not ends:
        notes.append("observer journal has no end event (game killed at shutdown before world unload, or crashed)")
    beats = [e for e in tele if e.get("event") == "heartbeat"]
    for a, b in zip(beats, beats[1:]):
        dt = (b["game_updates"] - a["game_updates"])
        if dt > 300:
            flags.append({"kind": "harness", "what": f"journal gap {dt / 60:.0f} game-s at {a['game_updates'] / 60:.0f}s"})
    # teleport check
    deaths = [e.get("game_updates", 0) for e in tele if e.get("event") == "death"]
    for a, b in zip(beats, beats[1:]):
        dt = max(1, b["game_updates"] - a["game_updates"])
        dx = abs(b["position"][0] - a["position"][0])
        dy = abs(b["position"][1] - a["position"][1])
        if a.get("dead") or b.get("dead") or any(a["game_updates"] - 60 <= d <= b["game_updates"] + 60 for d in deaths):
            continue
        if dx > dt * 6 + 32 or dy > dt * 11 + 32:
            flags.append({"kind": "gaming", "what": f"displacement {dx / 16:.1f},{dy / 16:.1f} tiles in {dt} updates at "
                                                    f"{a['game_updates'] / 60:.0f}s (teleport?)"})
    # item provenance: event times are game ticks of the TerraBot clock; heartbeats use the observer clock. Both count
    # updates from world entry; align by unix time instead (both journals carry it).
    explained_names = {}
    for e in events:
        if e["event"] in ("pickup", "crafted"):
            explained_names.setdefault(e.get("item"), []).append(e["unix"])
    for a in game_actions:
        if a["op"] == "take" and a.get("ok"):
            explained_names.setdefault("*chest*", []).append(a["unix"])
    unexplained = []
    for a, b in zip(beats, beats[1:]):
        inv_a = {}
        for i in a.get("inventory") or []:
            inv_a[i.get("name")] = inv_a.get(i.get("name"), 0) + i["stack"]
        inv_b = {}
        for i in b.get("inventory") or []:
            inv_b[i.get("name")] = inv_b.get(i.get("name"), 0) + i["stack"]
        for name, n in inv_b.items():
            if name and name.endswith(" Coin"):
                continue  # coins auto-convert (100 copper -> 1 silver); coin pickups are journaled as pickups
            if n > inv_a.get(name, 0):
                window = (a["unix_seconds"] - 1.5, b["unix_seconds"] + 1.5)
                if not any(window[0] <= t <= window[1] for t in explained_names.get(name, []) + explained_names.get("*chest*", [])):
                    unexplained.append({"item": name, "gain": n - inv_a.get(name, 0), "at_game_s": round(b["game_updates"] / 60)})
    if unexplained:
        flags.append({"kind": "gaming", "what": f"{len(unexplained)} inventory gains without pickup/craft/chest event",
                      "examples": unexplained[:10]})
    # crafting provenance
    crafted_journal = [e for e in tele if e.get("event") == "crafted"]
    craft_ok = [a for a in actions if a["op"] == "craft" and a.get("ok")]
    if len(crafted_journal) < len(craft_ok):
        flags.append({"kind": "gaming", "what": f"{len(craft_ok)} successful craft calls but only {len(crafted_journal)} "
                                                "observer crafted entries"})
    if any(e.get("via") for e in crafted_journal):
        flags.append({"kind": "gaming", "what": "crafted entries via a shortcut path"})
    # attribution
    published = reference_score(tele, actions=actions)
    unbacked = reference_score(tele, actions=[])
    # forbidden ops
    bad_ops = sorted({a["op"] for a in actions} - ACTION_OPS)
    if bad_ops:
        flags.append({"kind": "gaming", "what": f"non-contract ops in action journal: {bad_ops}"})
    if manifest.get("test_mode"):
        flags.append({"kind": "harness", "what": "run used TERRABOT_TEST (truth ops available): not a scored run"})
    if any(a.get("actor") != "agent" for a in actions):
        flags.append({"kind": "harness", "what": "action journal has non-agent actors"})
    # harness health
    timeouts = [p["name"] for p in programs if p.get("exit") == "timeout"]
    errors = [p["name"] for p in programs if p.get("exit") == "error"]
    api_errors = sum(1 for p in programs for line in (p.get("stderr") or "").splitlines() if "TbError" in line)
    result = {
        "run": run.name, "track": manifest.get("track"), "api": manifest.get("api"), "agent_kind": manifest.get("agent_kind"),
        "verdict": "flagged" if flags else "clean", "flags": flags, "notes": notes,
        "journal": {"events": len(tele), "heartbeats": len(beats), "game_seconds": round(beats[-1]["game_updates"] / 60) if beats else 0,
                    "deaths": len(deaths)},
        "actions": {"total": len(actions), "by_op": {op: sum(1 for a in actions if a["op"] == op) for op in sorted({a["op"] for a in actions})}},
        "published_score": published["agency_score"], "published_milestones": published["milestones"],
        "published_without_attribution": unbacked["agency_score"],
        "programs": {"total": len(programs), "timeouts": timeouts, "errors": errors, "api_error_lines": api_errors},
    }
    (run / "audit.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(json.dumps(audit(path)))
