"""Compare Dreamer validation curves with PPO v7 curves at equal env steps and
equal wall-clock (linear interpolation within each PPO run's evaluated range;
outside it: no value). All curves use validation worlds 23,000,001-23,000,128.

    python tools/dreamer_compare.py --dreamer RUN_DIR... --ppo GROUP=RUN_DIR,RUN_DIR ... --out cmp.json
"""
import argparse
import json
from pathlib import Path

import numpy as np


def load(run):
    c = json.loads((Path(run) / "curve.json").read_text())
    return [{"steps": r["steps"], "seconds": r["elapsed_seconds"], "mean": r["evaluation"]["mean_achievements"],
             "death": r["evaluation"]["death_rate"], "hits": r["evaluation"]["hits"]} for r in c]


def interp(curve, key, x):
    xs = [r[key] for r in curve]
    if not xs or x < xs[0] or x > xs[-1]:
        return None
    return float(np.interp(x, xs, [r["mean"] for r in curve]))


def group_at(runs, key, x):
    vals = [v for v in (interp(c, key, x) for c in runs) if v is not None]
    return (float(np.mean(vals)), len(vals)) if vals else (None, 0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dreamer", nargs="+", required=True)
    p.add_argument("--ppo", nargs="+", default=[], help="NAME=dir,dir,...")
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    ppo = {g.split("=")[0]: [load(d) for d in g.split("=")[1].split(",")] for g in a.ppo}
    out = {"dreamer": {}, "ppo_final": {}}
    for name, runs in ppo.items():
        finals = [c[-1] for c in runs]
        hits = {}
        for f in finals:
            for k, v in f["hits"].items():
                hits[k] = hits.get(k, 0) + v / len(finals)
        out["ppo_final"][name] = {"steps": [f["steps"] for f in finals], "seconds": [f["seconds"] for f in finals],
                                  "mean": float(np.mean([f["mean"] for f in finals])), "mean_hits": hits}
    for d in a.dreamer:
        rows = []
        for r in load(d):
            row = {"steps": r["steps"], "seconds": r["seconds"], "dreamer": r["mean"], "death": r["death"]}
            for name, runs in ppo.items():
                row[f"{name}@steps"], row[f"{name}@steps_n"] = group_at(runs, "steps", r["steps"])
                row[f"{name}@wall"], row[f"{name}@wall_n"] = group_at(runs, "seconds", r["seconds"])
            rows.append(row)
        out["dreamer"][Path(d).name] = rows
        print(f"== {Path(d).name}")
        names = list(ppo)
        print(f"{'steps(M)':>9} {'hours':>6} {'dreamer':>8} " + " ".join(f"{n+'@steps':>16} {n+'@wall':>16}" for n in names))
        for row in rows:
            cells = " ".join(f"{'-' if row[n+'@steps'] is None else round(row[n+'@steps'], 2):>16} "
                             f"{'-' if row[n+'@wall'] is None else round(row[n+'@wall'], 2):>16}" for n in names)
            print(f"{row['steps']/1e6:9.1f} {row['seconds']/3600:6.2f} {row['dreamer']:8.2f} {cells}")
    if a.out:
        a.out.write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
