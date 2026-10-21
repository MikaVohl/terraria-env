"""Summarise perf/runs/<arm>-s<seed>/curve.json validation results per arm.

    python perf/summarize_learning.py [perf/runs]
"""
import json, statistics, sys
from collections import defaultdict
from pathlib import Path


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "perf/runs")
    arms = defaultdict(dict)
    for curve in sorted(root.glob("*-s*/curve.json")):
        arm, seed = curve.parent.name.rsplit("-s", 1)
        rows = json.loads(curve.read_text())
        summary = json.loads((curve.parent / "summary.json").read_text()) if (curve.parent / "summary.json").exists() else {}
        arms[arm][int(seed)] = {"final": rows[-1]["evaluation"]["mean_achievements"], "steps": rows[-1]["steps"],
                                "curve": [round(r["evaluation"]["mean_achievements"], 3) for r in rows],
                                "death": rows[-1]["evaluation"]["death_rate"],
                                "train_sps": summary.get("sps")}
    out = {}
    for arm, seeds in sorted(arms.items()):
        finals = [s["final"] for s in seeds.values()]
        out[arm] = {"seeds": sorted(seeds), "final_mean_achievements": [round(f, 3) for f in finals],
                    "mean": round(statistics.mean(finals), 3),
                    "sd": round(statistics.stdev(finals), 3) if len(finals) > 1 else None,
                    "curves": {k: v["curve"] for k, v in sorted(seeds.items())},
                    "train_sps": {k: v["train_sps"] for k, v in sorted(seeds.items())}}
        print(f"{arm:10s} n={len(finals)} final validation achievements/32: mean {out[arm]['mean']:.3f} "
              f"sd {out[arm]['sd']}  per seed {out[arm]['final_mean_achievements']}")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
