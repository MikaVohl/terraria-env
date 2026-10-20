"""Markdown results table for a campaign directory, from each run's evidence/summary.json and manifest.

    python tools/pilot_table.py runs/pilot-30min [run ...]

Smoke and aborted runs are skipped unless named explicitly. Milestone times are mm:ss of game time (60 updates/s).
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

ORDER = ("wood_1", "wood_25", "wood_100", "workbench_1", "torch_10", "furnace_1")


def mmss(s):
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def setup(run):
    man = json.loads((run / "manifest.json").read_text())
    if str(man.get("protocol", "")).startswith("combo-"):
        c = man["config"]
        return (f'{c["planner_model"].split("-")[1].title()} planner + {c["executor"].title()} '
                f'({man["protocol"]}{", PvE off" if not c["pve"] else ""})')
    cfg = man["model"]["id"].split("-")[1].title()
    bits = [man.get("clock", "realtime")]
    if not man.get("pve_enabled", True):
        bits.append("PvE off")
    if not man.get("interface_card"):
        bits.append("no card")
    elif man["interface_card"] == "v2":
        bits.append("card v2")
    return f"{cfg} ({', '.join(bits)})"


def usd(summary):
    u = summary["usd"]
    return sum(Decimal(v) for v in u.values()) if isinstance(u, dict) else Decimal(u)


def main(root, names):
    root = Path(root)
    runs = [root / n for n in names] if names else sorted(
        p for p in root.iterdir() if (p / "evidence/summary.json").exists() and not p.name.startswith("smoke") and "aborted" not in p.name)
    print("| Run | Setup | Score | " + " | ".join(ORDER) + " | Deaths | Depth | Continuations | Shot age (s) | USD |")
    print("|" + "---|" * (len(ORDER) + 9))
    for run in runs:
        s = json.loads((run / "evidence/summary.json").read_text())
        ms = s["milestones_game_s"]
        print(f'| {run.name} | {setup(run)} | {s["score"]} | ' + " | ".join(mmss(ms[k]) if k in ms else "–" for k in ORDER) +
              f' | {s["deaths"]} | {s["max_depth_tiles"]} | {s["continuations"] if s["continuations"] is not None else "–"} | '
              f'{s["screenshot_age_median_s"]} | {usd(s):.2f} |')


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
