"""Arms x seeds table for PPO_IDEAS_2026_10.md: final validation score, wall
achievement worlds (out of 128) and policy_diagnostics inventory peaks.

    python3 tools/ppo_ideas_table.py --runs <screen>/runs ... --diag <diag dir> --json out.json
"""
import argparse
import json
from pathlib import Path

WALL = {"anvil": "craft anvil", "metal sword": "craft metal sword", "iron pick": "craft iron pickaxe",
        "gold pick": "craft gold pickaxe", "chainmail": "craft iron chainmail",
        "breastplate": "craft wood breastplate", "surface": "return to surface"}
PEAKS = ("iron bar", "gold bar", "wood")


def row(run: Path, diag: Path):
    curve = json.loads((run / "curve.json").read_text())
    final = curve[-1]
    ev = final["evaluation"]
    out = {"run": run.name, "steps": final["steps"], "score": ev["mean_achievements"],
           "worlds": {k: ev["hits"].get(v, 0) for k, v in WALL.items()},
           "policy_entropy": final["profile"].get("policy_entropy")}
    if "return_norm" in final["profile"]:
        out["return_norm"] = final["profile"]["return_norm"]
    d = diag / f"{run.name}.json"
    if d.exists():
        peaks = json.loads(d.read_text())["inventory_peak"]
        out["peaks"] = {k: {"median": peaks[k]["median"], "mean": round(peaks[k]["mean"], 2), "max": peaks[k]["max"]}
                        for k in PEAKS}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runs", nargs="+", type=Path, required=True)
    p.add_argument("--diag", type=Path, required=True)
    p.add_argument("--json", type=Path)
    a = p.parse_args()
    rows = [row(r, a.diag) for d in a.runs for r in sorted(d.iterdir())
            if (r / "summary.json").exists()]
    head = ["run", "score", *WALL, *(f"{k} peak med/max" for k in PEAKS)]
    print("| " + " | ".join(head) + " |\n|" + "---|" * len(head))
    for r in rows:
        pk = [f"{r['peaks'][k]['median']:g}/{r['peaks'][k]['max']}" if "peaks" in r else "-" for k in PEAKS]
        print("| " + " | ".join([r["run"], f"{r['score']:.3f}", *(str(r["worlds"][k]) for k in WALL), *pk]) + " |")
    if a.json:
        a.json.write_text(json.dumps(rows, indent=1) + "\n")


if __name__ == "__main__":
    main()
