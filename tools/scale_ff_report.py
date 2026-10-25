"""Compact results for the feed-forward size study (SCALE_FF_2026_10.md).

Reads explore_screen run directories (protocol.json, curve.json, summary.json)
and optional policy_diagnostics outputs (<run>/diagnostics.json) and writes one
compact JSON: per-run curves (steps, checkpoint wall-clock, score), final
achievement rates, death rate, idle tail, inventory peaks and craft
opportunities, plus per-arm aggregates at matched step budgets.

    python tools/scale_ff_report.py experiments/sff-*/runs --out SCALE_FF_2026_10.json
"""
import argparse
import json
from pathlib import Path
import statistics

ACHIEVEMENTS = ["craft anvil", "craft metal sword", "craft iron pickaxe", "craft gold pickaxe",
                "craft iron chainmail", "craft wood breastplate", "return to surface"]
ITEMS = ["wood", "iron bar", "gold bar"]
CRAFTS = ["craft anvil", "craft iron pickaxe", "craft gold pickaxe", "craft iron chainmail",
          "craft wood breastplate"]
MATCHED = [128 << 20, 256 << 20, 512 << 20, 1 << 30, 2 << 30, 4 << 30]


def run_record(directory):
    protocol = json.loads((directory/"protocol.json").read_text())
    curve_path = directory/"curve.json"
    curve = json.loads(curve_path.read_text()) if curve_path.exists() else []
    if not curve:
        return None
    cfg = protocol["config"]
    finished = (directory/"summary.json").exists()
    log = directory.parent.parent/"logs"/f"{directory.name}.log"
    status = "finished" if finished else (
        "non-finite loss" if log.exists() and "FloatingPointError" in log.read_text() else "stopped")
    last = curve[-1]["evaluation"]
    episodes = last["episodes"]
    record = {
        "run": directory.name, "arm": directory.name.rsplit("-", 1)[0], "seed": cfg["seed"],
        "architecture": cfg["architecture"], "hidden": cfg.get("hidden", 0) or {"targets": 128, "mlp": 512}[cfg["architecture"]],
        "depth": cfg.get("depth", 2), "cell_width": cfg.get("cell_width", 32) if cfg["architecture"] == "targets" else None,
        "lr": cfg["lr"], "parameters": protocol.get("parameters"),
        "requested_steps": protocol["actual_steps"], "finished": finished, "status": status,
        "curve": [[row["steps"], round(row.get("checkpoint_elapsed_seconds", row["elapsed_seconds"]), 1),
                   round(row["evaluation"]["mean_achievements"], 4)] for row in curve],
        # Learner telemetry at each checkpoint (runs from cb73159 on): entropy, approx KL of
        # the last minibatch, clip fraction, value explained variance.
        "learner": [[row["steps"], *(round(row["profile"][k], 4) if row["profile"].get(k) is not None else None
                                     for k in ("policy_entropy", "approx_kl", "clip_fraction", "explained_variance"))]
                    for row in curve],
        "final": {"steps": curve[-1]["steps"], "score": last["mean_achievements"],
                  "death_rate": last["death_rate"],
                  "idle_tail_steps": last.get("mean_steps_after_last_achievement"),
                  "rates": {name: last["hits"].get(name, 0)/episodes for name in ACHIEVEMENTS}},
    }
    if finished:
        record["wall_seconds_including_validation"] = json.loads((directory/"summary.json").read_text())[
            "wall_seconds_including_validation"]
    diagnostics = directory/"diagnostics.json"
    if diagnostics.exists():
        d = json.loads(diagnostics.read_text())
        peaks = [r["inventory_peak"] for r in d["records"]]
        from terraria_lite import SPEC
        index = {name: SPEC.item_names.index(name) for name in ITEMS}
        record["diagnostics"] = {
            "checkpoint_steps": record["final"]["steps"],
            "inventory_peak": {name: {**d["inventory_peak"][name],
                                      **({"episodes_ge_10": sum(p[index[name]] >= 10 for p in peaks)} if name != "wood"
                                         else {"episodes_ge_30": sum(p[index[name]] >= 30 for p in peaks)})}
                               for name in ITEMS},
            "craft_opportunity_episodes": {name: d["actions"][name]["episodes_with_opportunity"] for name in CRAFTS},
            "episodes": d["episodes"]}
    return record


def score_at(curve, steps):
    rows = [score for s, _, score in curve if s == steps]
    return rows[0] if rows else None


def aggregate(runs):
    arms = {}
    for r in runs:
        arms.setdefault(r["arm"], []).append(r)
    out = {}
    for arm, rs in sorted(arms.items()):
        entry = {"seeds": sorted(r["seed"] for r in rs), "parameters": rs[0]["parameters"],
                 "architecture": rs[0]["architecture"], "hidden": rs[0]["hidden"], "depth": rs[0]["depth"],
                 "cell_width": rs[0]["cell_width"], "lr": rs[0]["lr"], "at_steps": {}}
        for steps in MATCHED:
            scores = [s for s in (score_at(r["curve"], steps) for r in rs) if s is not None]
            if scores:
                entry["at_steps"][str(steps)] = {"n": len(scores), "mean": statistics.mean(scores),
                                                 "scores": scores}
        finished = [r for r in rs if r["finished"]]
        if finished:
            entry["finished_runs"] = len(finished)
            entry["final_mean"] = statistics.mean(r["final"]["score"] for r in finished)
            entry["mean_seconds_per_billion_steps"] = statistics.mean(
                r["curve"][-1][1]/r["curve"][-1][0]*1e9 for r in finished)
        out[arm] = entry
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("roots", nargs="+", type=Path, help="explore_screen runs/ directories")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--extra", type=Path, help="JSON merged into the output (throughput, notes)")
    a = p.parse_args()
    runs = []
    for root in a.roots:
        for directory in sorted(root.iterdir()):
            if (directory/"protocol.json").exists() and ".interrupted-" not in directory.name:
                record = run_record(directory)
                if record is not None:
                    record["study"] = root.parent.name
                    runs.append(record)
    result = {"runs": runs, "arms": aggregate(runs)}
    if a.extra:
        result.update(json.loads(a.extra.read_text()))
    a.out.write_text(json.dumps(result, indent=1)+"\n")
    for arm, e in result["arms"].items():
        cells = " ".join(f"{int(s)>>20}M={v['mean']:.2f}(n{v['n']})" for s, v in e["at_steps"].items())
        print(f"{arm:28s} p={e['parameters']:>10,} {cells}")


if __name__ == "__main__":
    main()
