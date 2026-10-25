"""Compact results for the memory-architecture study (MEMORY_ARCH_2026_10.md).

    PYTHONPATH=python python tools/memory_report.py experiments/memarch-v7-* --out MEMORY_ARCH_2026_10.json

Reads every <screen>/runs/<arm>-<seed>/ (protocol.json, curve.json,
summary.json, diagnostics.json from tools/policy_diagnostics.py) and writes one
JSON row per run: validation score curve (steps, wall seconds, score), final
and best score, achievement rates for the wall (anvil, metal sword, pickaxes,
chainmail, breastplate, return to surface), deaths, idle tail, throughput,
parameter count, the replay check (first-minibatch KL) and stockpiling
diagnostics (inventory peaks, legal opportunities for the big crafts). Prints
markdown tables of arm means.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

WALL = ["craft anvil", "craft metal sword", "craft iron pickaxe", "craft gold pickaxe", "craft iron chainmail",
        "craft wood breastplate", "return to surface", "collect iron", "smelt iron", "collect gold", "smelt gold"]
CRAFTS = ["craft anvil", "craft iron pickaxe", "craft gold pickaxe", "craft iron chainmail", "craft wood breastplate"]
ITEMS = {"wood": (13, 30), "iron ore": (None, None), "iron bar": (5, 10), "gold ore": (None, None),
         "gold bar": (None, 10)}
NEED = {"iron bar >= 10": ("iron bar", 10), "iron bar >= 25": ("iron bar", 25), "gold bar >= 10": ("gold bar", 10),
        "wood >= 30": ("wood", 30)}


def run_row(run: Path) -> dict | None:
    if not (run / "summary.json").exists():
        return None
    protocol = json.loads((run / "protocol.json").read_text())
    curve = json.loads((run / "curve.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    cfg = protocol["config"]
    final = curve[-1]["evaluation"]
    n = final["episodes"]
    arm, seed = run.name.rsplit("-", 1)
    train_seconds = summary["collection_seconds"] + summary["optimisation_seconds"]
    row = {
        "arm": arm, "seed": int(seed), "memory": cfg.get("memory", ""), "memory_size": summary.get("memory_size", 0),
        "memory_len": summary.get("memory_len", 0), "hidden": cfg.get("hidden", 0),
        "parameters": summary.get("parameters", protocol.get("parameters")), "steps": summary["steps"],
        "train_seconds": round(train_seconds), "sps": round(summary["steps"] / train_seconds),
        "wall_seconds": round(summary["wall_seconds_including_validation"]),
        "final": final["mean_achievements"], "best": max(r["evaluation"]["mean_achievements"] for r in curve),
        "final_std": final["std_achievements"], "death_rate": final["death_rate"],
        "idle_tail_steps": final["mean_steps_after_last_achievement"],
        "rates": {k: final["hits"].get(k, 0) / n for k in WALL},
        "curve": [[r["steps"], round(r.get("checkpoint_elapsed_seconds") or r["elapsed_seconds"]),
                   round(r["evaluation"]["mean_achievements"], 3)] for r in curve],
        "first_minibatch_kl_max": max((abs(r["profile"]["first_minibatch_kl"]) for r in curve
                                       if "first_minibatch_kl" in r["profile"]), default=None),
    }
    diag = run / "diagnostics.json"
    if diag.exists():
        d = json.loads(diag.read_text())
        peaks = {name: [r["inventory_peak"][i] for r in d["records"]] for i, name in
                 enumerate(d["inventory_peak"]) if name in ITEMS}
        row["diagnostics"] = {
            "episodes": d["episodes"],
            "peak_mean": {k: float(np.mean(v)) for k, v in peaks.items()},
            "peak_max": {k: int(np.max(v)) for k, v in peaks.items()},
            "episodes_reaching": {label: int(sum(p >= x for p in peaks[item])) for label, (item, x) in NEED.items()},
            "craft_opportunity_episodes": {k: d["actions"][k]["episodes_with_opportunity"] for k in CRAFTS},
            "craft_chosen": {k: d["actions"][k]["chosen"] for k in CRAFTS},
        }
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("screens", nargs="+", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rows = [r for s in a.screens for run in sorted((s / "runs").iterdir()) if run.is_dir() and "." not in run.name
            if (r := run_row(run)) is not None]
    a.out.write_text(json.dumps({"runs": rows}, indent=1) + "\n")
    arms = defaultdict(list)
    for r in rows:
        arms[r["arm"]].append(r)
    print("| arm | params | seeds | final | best | sps | train h | death | idle | anvil | metal sword | "
          "iron pick | gold pick | chainmail | breastplate | surface |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm, rs in sorted(arms.items(), key=lambda kv: -np.mean([r["final"] for r in kv[1]])):
        m = lambda k: np.mean([r[k] for r in rs])
        rate = lambda k: f"{100 * np.mean([r['rates'][k] for r in rs]):.0f}%"
        seeds = ", ".join(f"{r['final']:.2f}" for r in rs)
        print(f"| {arm} | {rs[0]['parameters']:,} | {len(rs)} | {m('final'):.2f} ({seeds}) "
              f"| {m('best'):.2f} | {m('sps') / 1e3:.0f}k | {m('train_seconds') / 3600:.2f} | {100 * m('death_rate'):.0f}% "
              f"| {m('idle_tail_steps'):.0f} | {rate('craft anvil')} | {rate('craft metal sword')} | "
              f"{rate('craft iron pickaxe')} | {rate('craft gold pickaxe')} | {rate('craft iron chainmail')} | "
              f"{rate('craft wood breastplate')} | {rate('return to surface')} |")
    print("\n| arm | wood peak | iron ore peak | iron bar peak | gold bar peak | iron bar>=10 | wood>=30 | "
          "gold bar>=10 | iron-pick legal | gold-pick legal | chainmail legal | breastplate legal |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm, rs in sorted(arms.items()):
        ds = [r["diagnostics"] for r in rs if "diagnostics" in r]
        if not ds:
            continue
        pk = lambda k: f"{np.mean([d['peak_mean'][k] for d in ds]):.1f}"
        ep = lambda k: f"{np.mean([d['episodes_reaching'][k] for d in ds]):.1f}"
        op = lambda k: f"{np.mean([d['craft_opportunity_episodes'][k] for d in ds]):.1f}"
        print(f"| {arm} | {pk('wood')} | {pk('iron ore')} | {pk('iron bar')} | {pk('gold bar')} | "
              f"{ep('iron bar >= 10')} | {ep('wood >= 30')} | {ep('gold bar >= 10')} | {op('craft iron pickaxe')} | "
              f"{op('craft gold pickaxe')} | {op('craft iron chainmail')} | {op('craft wood breastplate')} |")


if __name__ == "__main__":
    main()
