"""Compact results for the memory-architecture study (MEMORY_ARCH_2026_10.md).

    PYTHONPATH=python python tools/memory_report.py experiments/memarch-v7-20261025=shared \
        experiments/memarch-solo-v7-20261025=solo --stopped shared/mem_lstm512-1901 ... --out MEMORY_ARCH_2026_10.json

Each screen carries a label (here: whether runs shared their GPU). Runs named
in --stopped were deliberately stopped and keep their partial curves.

Reads every <screen>/runs/<arm>-<seed>/ (protocol.json, curve.json,
summary.json, diag.json from tools/policy_diagnostics.py) and writes one JSON
row per run: status (completed, or died with a non-finite loss), validation
score curve (steps, seconds since start, score), final and best score,
achievement rates for the wall (anvil, metal sword, pickaxes, chainmail,
breastplate, return to surface), deaths, idle tail, throughput, parameter
count, the replay check (first-minibatch KL) and stockpiling diagnostics
(inventory peaks, legal opportunities for the big crafts). Died runs keep their
partial curve and, if run, diagnostics of their last checkpoint
(diag-step-<steps>.json). Prints markdown tables.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

WALL = ["craft anvil", "craft metal sword", "craft iron pickaxe", "craft gold pickaxe", "craft iron chainmail",
        "craft wood breastplate", "return to surface", "collect iron", "smelt iron", "collect gold", "smelt gold"]
CRAFTS = ["craft anvil", "craft iron pickaxe", "craft gold pickaxe", "craft iron chainmail", "craft wood breastplate"]
ITEMS = ["wood", "iron ore", "iron bar", "gold ore", "gold bar"]
NEED = {"iron bar >= 10": ("iron bar", 10), "iron bar >= 25": ("iron bar", 25), "gold bar >= 10": ("gold bar", 10),
        "wood >= 30": ("wood", 30)}
MATCHED = [2 ** 26, 2 ** 27, 2 ** 28, 3 * 2 ** 27, 2 ** 29, 2 ** 30, 2 ** 31]
WALL_CLOCK = [600, 1200, 1800, 2700, 3600, 5400, 7200, 10800, 16200]   # seconds since the run started


def diagnostics(path: Path) -> dict:
    d = json.loads(path.read_text())
    names = list(d["inventory_peak"])
    peaks = {k: [r["inventory_peak"][names.index(k)] for r in d["records"]] for k in ITEMS}
    return {
        "checkpoint_steps": int(path.stem.split("-")[-1]) if path.stem.startswith("diag-step") else None,
        "episodes": d["episodes"],
        "peak_median": {k: float(np.median(v)) for k, v in peaks.items()},
        "peak_mean": {k: float(np.mean(v)) for k, v in peaks.items()},
        "peak_max": {k: int(np.max(v)) for k, v in peaks.items()},
        "episodes_reaching": {label: int(sum(p >= x for p in peaks[item])) for label, (item, x) in NEED.items()},
        "craft_opportunity_episodes": {k: d["actions"][k]["episodes_with_opportunity"] for k in CRAFTS},
        "craft_chosen": {k: d["actions"][k]["chosen"] for k in CRAFTS},
    }


def run_row(run: Path, label: str, stopped: set) -> dict | None:
    if not (run / "curve.json").exists():
        return None
    protocol = json.loads((run / "protocol.json").read_text())
    curve = json.loads((run / "curve.json").read_text())
    done = (run / "summary.json").exists()
    log = run.parent.parent / "logs" / f"{run.name}.log"
    died = not done and log.exists() and "FloatingPointError" in log.read_text()
    halted = not (done or died) and f"{label}/{run.name}" in stopped
    if not (done or died or halted):
        return None                      # still running
    cfg = protocol["config"]
    final = curve[-1]["evaluation"]
    n = final["episodes"]
    arm, seed = run.name.rsplit("-", 1)
    elapsed = lambda r: r.get("checkpoint_elapsed_seconds") or r["elapsed_seconds"]
    if done:
        summary = json.loads((run / "summary.json").read_text())
        steps, train_seconds = summary["steps"], summary["collection_seconds"] + summary["optimisation_seconds"]
    else:                                # up to the last recorded checkpoint
        last = curve[-1]["profile"]
        steps, train_seconds = curve[-1]["steps"], last["collection_seconds"] + last["optimisation_seconds"]
    row = {
        "arm": arm, "seed": int(seed), "screen": label,
        "status": "completed" if done else "died (non-finite loss)" if died else "stopped",
        "memory": cfg.get("memory", ""), "memory_size": cfg.get("memory_size", 0) or (256 if cfg.get("memory") else 0),
        "memory_len": cfg.get("memory_len", 0) or (64 if cfg.get("memory") == "transformer" else 0),
        "hidden": cfg.get("hidden", 0) or 128, "parameters": protocol.get("parameters"),
        "steps": steps, "train_seconds": round(train_seconds), "sps": round(steps / train_seconds),
        "final": final["mean_achievements"], "best": max(r["evaluation"]["mean_achievements"] for r in curve),
        "final_std": final["std_achievements"], "death_rate": final["death_rate"],
        "idle_tail_steps": final["mean_steps_after_last_achievement"],
        "rates": {k: final["hits"].get(k, 0) / n for k in WALL},
        "curve": [[r["steps"], round(elapsed(r)), round(r["evaluation"]["mean_achievements"], 3)] for r in curve],
        "first_minibatch_kl_max": max((abs(r["profile"]["first_minibatch_kl"]) for r in curve
                                       if "first_minibatch_kl" in r["profile"]), default=None),
    }
    if done:
        row["wall_seconds"] = round(summary["wall_seconds_including_validation"])
    diag = run / "diag.json"
    if not diag.exists():
        partial = sorted(run.glob("diag-step-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
        diag = partial[-1] if partial else None
    if diag is not None:
        row["diagnostics"] = diagnostics(diag)
    return row


def at(row, steps):
    for s, _, score in row["curve"]:
        if s == steps:
            return score
    return None


def by_time(row, seconds):
    """Score of the last checkpoint taken within `seconds` of the run's start."""
    scores = [score for _, t, score in row["curve"] if t <= seconds]
    return scores[-1] if scores else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("screens", nargs="+", help="SCREEN_DIR=LABEL")
    p.add_argument("--stopped", nargs="*", default=[], help="LABEL/RUN of runs stopped on purpose")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rows = [r for screen in a.screens for s, label in [screen.split("=", 1)]
            for run in sorted((Path(s) / "runs").iterdir()) if run.is_dir() and "." not in run.name
            if (r := run_row(run, label, set(a.stopped))) is not None]
    a.out.write_text(json.dumps({"runs": rows}, indent=1) + "\n")
    arms = defaultdict(list)
    for r in rows:
        arms[f"{r['arm']} [{r['screen']}]"].append(r)
    order = sorted(arms, key=lambda k: (arms[k][0]["memory"], arms[k][0]["memory_size"], k))

    print("| arm | params | runs (not completed) | final per seed | sps | death | idle | anvil | metal sword | "
          "iron pick | gold pick | chainmail | breastplate | surface |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm in order:
        rs = arms[arm]
        m = lambda k: np.mean([r[k] for r in rs])
        rate = lambda k: f"{100 * np.mean([r['rates'][k] for r in rs]):.0f}%"
        seeds = ", ".join(f"{r['seed']}: {r['final']:.2f}" + ("" if r["status"] == "completed" else
                          f" ({r['status'].split()[0]} {r['steps'] / 2 ** 20:.0f}Mi)") for r in rs)
        print(f"| {arm} | {rs[0]['parameters']:,} | {len(rs)} ({sum(r['status'] != 'completed' for r in rs)}) | "
              f"{seeds} | {m('sps') / 1e3:.0f}k | {100 * m('death_rate'):.0f}% | {m('idle_tail_steps'):.0f} | "
              f"{rate('craft anvil')} | {rate('craft metal sword')} | {rate('craft iron pickaxe')} | "
              f"{rate('craft gold pickaxe')} | {rate('craft iron chainmail')} | {rate('craft wood breastplate')} | "
              f"{rate('return to surface')} |")

    print("\nMatched steps (mean over runs that reached the step; n in brackets):\n")
    print("| arm | " + " | ".join(f"{s / 2 ** 20:.0f}Mi" for s in MATCHED) + " |")
    print("|---|" + "---|" * len(MATCHED))
    for arm in order:
        cells = []
        for s in MATCHED:
            v = [x for r in arms[arm] if (x := at(r, s)) is not None]
            cells.append(f"{np.mean(v):.2f} [{len(v)}]" if v else "")
        print(f"| {arm} | " + " | ".join(cells) + " |")

    print("\nEqual wall-clock (score of the last checkpoint within the budget; only completed solo-comparable runs):\n")
    print("| arm | " + " | ".join(f"{w / 60:.0f} min" for w in WALL_CLOCK) + " |")
    print("|---|" + "---|" * len(WALL_CLOCK))
    for arm in order:
        cells = []
        for w in WALL_CLOCK:
            v = [x for r in arms[arm] if r["status"] == "completed" if (x := by_time(r, w)) is not None]
            cells.append(f"{np.mean(v):.2f} [{len(v)}]" if v else "")
        print(f"| {arm} | " + " | ".join(cells) + " |")

    print("\n| run | diag ckpt | wood peak med/max | iron ore med | iron bar med/max | gold bar med/max | "
          "iron bar>=10 | wood>=30 | gold bar>=10 | legal: anvil | iron pick | gold pick | chainmail | breastplate |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm in order:
        for r in arms[arm]:
            d = r.get("diagnostics")
            if d is None:
                continue
            md, mx, op = d["peak_median"], d["peak_max"], d["craft_opportunity_episodes"]
            ck = d["checkpoint_steps"] or r["steps"]
            print(f"| {arm} {r['seed']} | {ck / 2 ** 20:.0f}Mi | {md['wood']:.0f}/{mx['wood']} | {md['iron ore']:.0f} | "
                  f"{md['iron bar']:.0f}/{mx['iron bar']} | {md['gold bar']:.0f}/{mx['gold bar']} | "
                  f"{d['episodes_reaching']['iron bar >= 10']} | {d['episodes_reaching']['wood >= 30']} | "
                  f"{d['episodes_reaching']['gold bar >= 10']} | {op['craft anvil']} | {op['craft iron pickaxe']} | "
                  f"{op['craft gold pickaxe']} | {op['craft iron chainmail']} | {op['craft wood breastplate']} |")


if __name__ == "__main__":
    main()
