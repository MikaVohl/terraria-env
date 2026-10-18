"""Audit and summarize planner/executor runs against single-model baselines.

Audit per hybrid run: the executed inputs (inputs.jsonl) must equal, in order, the actions
logged by executor decisions and planner UI batches; every logged model call must have a
stored request and response. Writes summary.json/summary.csv in the campaign directory.
"""
import argparse
import csv
import json
from pathlib import Path
import statistics


def jsonl(path):
    return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []


def audit_hybrid(run):
    receipts = jsonl(run / "inputs.jsonl")
    decisions = jsonl(run / "decisions.jsonl")
    expected = [a for d in decisions if d.get("role") in ("executor", "planner_ui") and "actions" in d for a in d["actions"]]
    assert [r["action"] for r in receipts] == expected, "inputs differ from logged decisions"
    assert all(r["actor"] == "agent" for r in receipts)
    result = json.loads((run / "result.json").read_text())
    for role, info in result["roles"].items():
        stored = len(list((run / "calls").glob(f"{role}-*-response.json")))
        assert stored == info["calls"] - info["failures"], f"{role}: responses {stored} != calls {info['calls']} - failures {info['failures']}"
    return True


def kill_seconds(events):
    hb = [e for e in events if e.get("event") == "heartbeat"]
    start = hb[0]["game_updates"] if hb else 0
    killed = next((e for e in hb if (e.get("target") or {}).get("killed")), None)
    return round((killed["game_updates"] - start) / 60, 1) if killed else None


def row(run, kind):
    result = json.loads((run / "result.json").read_text())
    m = result["metrics"]
    events = json.loads((run / "evaluation-events.json").read_text())
    milestones = m["public_subset_score"]["milestones"]
    base = {"run": run.name, "kind": kind, "stop": result["stop_reason"], "game_s": round(m["game_updates_during_agent"] / 60, 1),
            "wood_max": m["inventory_stack_maxima"].get("Wood", 0), "wood_25": "wood_25" in milestones,
            "workbench": "workbench_1" in milestones, "deaths": m["deaths"], "damage_received": m["damage_received"],
            "target_damage": m["player_damage_to_target"], "target_killed": m["target_killed"], "kill_game_s": kill_seconds(events)}
    if kind == "hybrid":
        c = result["config"]
        t = result["timing"]
        base |= {"condition": c["condition"], "scenario": c["scenario"],
                 "usd": round(sum(float(r["accounting"]["reported_usd"]) for r in result["roles"].values()), 6),
                 "uncertain_usd": round(sum(float(r["accounting"]["uncertain_reserved_usd"]) for r in result["roles"].values()), 6),
                 "executor_decisions": t["executor_decisions"], "executor_errors": t["executor_errors"],
                 "planner_updates": t["planner_updates"], "obs_age_median": t["observation_age_median"],
                 "held_fraction": t["input_held_fraction"],
                 "executor_latency_median": (result["roles"].get("executor") or {}).get("latency_median"),
                 "audit": "pass" if audit_hybrid(run) else "fail"}
    else:
        c = result["config"]
        base |= {"condition": "single-haiku", "scenario": c["scenario"], "usd": float(result["accounting"]["reported_usd"]),
                 "uncertain_usd": float(result["accounting"]["uncertain_reserved_usd"]), "executor_decisions": result["calls"],
                 "executor_errors": result["invalid_outputs"], "planner_updates": None, "obs_age_median": None,
                 "held_fraction": result["metrics"]["input_hold_seconds"] / result["agent_wall_seconds"] if result["agent_wall_seconds"] else None,
                 "executor_latency_median": statistics.median(result["latencies"]) if result["latencies"] else None, "audit": "see analyze_experiments"}
    return base


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("campaign", type=Path)
    p.add_argument("--baseline", type=Path, action="append", default=[], help="extra single-model run directories")
    a = p.parse_args()
    rows = []
    for result in sorted(a.campaign.glob("P-*/result.json")):
        if "." in result.parent.name:
            continue  # archived runs (.infra-failed-N, .excluded-*) are evidence, not samples
        rows.append(row(result.parent, "hybrid" if "roles" in json.loads(result.read_text()) else "single"))
    for run in a.baseline:
        rows.append(row(run, "single"))
    (a.campaign / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    with (a.campaign / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    groups = {}
    for r in rows:
        groups.setdefault((r["scenario"], r["condition"]), []).append(r)
    for (scen, cond), rs in sorted(groups.items()):
        ages = [r["obs_age_median"] for r in rs if r["obs_age_median"] is not None]
        print(json.dumps({"scenario": scen, "condition": cond, "n": len(rs),
                          "wood_max": [r["wood_max"] for r in rs], "wood_25": sum(r["wood_25"] for r in rs),
                          "workbench": sum(r["workbench"] for r in rs), "deaths": sum(r["deaths"] for r in rs),
                          "kills": sum(r["target_killed"] for r in rs), "target_damage": [r["target_damage"] for r in rs],
                          "kill_game_s": [r["kill_game_s"] for r in rs], "damage_received": [r["damage_received"] for r in rs],
                          "obs_age_median": round(statistics.median(ages), 2) if ages else None,
                          "usd": round(sum(r["usd"] for r in rs), 4)}))


if __name__ == "__main__":
    main()
