#!/usr/bin/env python3
"""Build the ceiling report tables from results/*.jsonl.

Prints markdown tables and writes results/summary.json. Inputs: h3000/h6000/
h12000 planner records (validation worlds), lower_bounds.jsonl, optionally
extra_h3000.jsonl and portfolio_h3000.jsonl."""
import json
import os
import statistics as st

here = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(here, "results")
NAMES = ["collect wood", "collect stone", "place block", "craft workbench", "craft furnace",
         "craft anvil", "place torch", "place platform", "collect copper", "collect iron",
         "collect silver", "collect gold", "smelt copper", "smelt iron", "smelt silver", "smelt gold",
         "defeat Blue Slime", "defeat Cave Bat", "open chest", "craft wooden sword",
         "craft metal sword", "craft wood breastplate", "craft iron chainmail",
         "heal with food or potion", "use life crystal", "double jump", "descend deep",
         "return to surface", "explore 30 columns", "climb rope", "craft iron pickaxe",
         "craft gold pickaxe"]
HARD = ["craft anvil", "craft metal sword", "craft iron pickaxe", "craft gold pickaxe",
        "craft iron chainmail", "craft wood breastplate", "return to surface"]


def load(name):
    p = os.path.join(R, name)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else None


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def score_stats(rs):
    sc = [r["score"] for r in rs]
    hist = {}
    for s in sc:
        hist[s] = hist.get(s, 0) + 1
    return {"n": len(rs), "mean": round(st.mean(sc), 3), "median": st.median(sc), "min": min(sc),
            "max": max(sc), "perfect": sum(s == 32 for s in sc), "died": sum(r["died"] for r in rs),
            "hist": dict(sorted(hist.items()))}


def ach_stats(rs):
    out = {}
    for i, n in enumerate(NAMES):
        s = [r["ach_step"][i] for r in rs if r["ach_step"][i] >= 0]
        out[n] = {"earned": len(s), "median": st.median(s) if s else None, "max": max(s) if s else None}
    return out


summary = {}
runs = {h: load(f"h{h}.jsonl") for h in (3000, 6000, 12000)}
lbs = {r["seed"]: r for r in load("lower_bounds.jsonl")}
for h, rs in runs.items():
    summary[f"h{h}"] = {"scores": score_stats(rs), "achievements": ach_stats(rs)}

print("## Scores")
print("| horizon | worlds | mean /32 | median | min | max | 32/32 worlds | deaths | histogram |")
print("|---|---|---|---|---|---|---|---|---|")
for key, label in [("h3000", "3,000"), ("h6000", "6,000"), ("h12000", "12,000")]:
    s = summary[key]["scores"]
    print(f"| {label} | {s['n']} | {s['mean']:.2f} | {s['median']} | {s['min']} | {s['max']} | {s['perfect']} | {s['died']} | "
          + ", ".join(f"{k}:{v}" for k, v in s["hist"].items()) + " |")
for extra, label in [("extra_h3000.jsonl", "3,000 (extra seeds 24000001-24000256)"),
                     ("portfolio_h3000.jsonl", "3,000 (best of 6 planner configs)")]:
    rs = load(extra)
    if rs:
        s = score_stats(rs)
        summary[extra.replace(".jsonl", "")] = {"scores": s, "achievements": ach_stats(rs)}
        print(f"| {label} | {s['n']} | {s['mean']:.2f} | {s['median']} | {s['min']} | {s['max']} | {s['perfect']} | {s['died']} | "
              + ", ".join(f"{k}:{v}" for k, v in s["hist"].items()) + " |")

print("\n## Per achievement, 3,000 steps (128 validation worlds)")
print("| achievement | earned /128 | median step | max step |")
print("|---|---|---|---|")
for n in NAMES:
    a = summary["h3000"]["achievements"][n]
    print(f"| {n} | {a['earned']} | {a['median'] if a['median'] is not None else '-'} | {a['max'] if a['max'] is not None else '-'} |")

print("\n## Hard tier: 3,000-step success, failure classification, time needed")
print("| achievement | earned @3000 | earned @6000 | earned @12000 | lower bound median (max) | "
      "failures @3000 with LB>3000 | failures @3000 planner ran out | steps needed (12k run) median / p90 / max |")
print("|---|---|---|---|---|---|---|---|")
hard = {}
for n in HARD:
    i = NAMES.index(n)
    e3 = [r for r in runs[3000] if r["ach_step"][i] >= 0]
    fail = [r for r in runs[3000] if r["ach_step"][i] < 0]
    lb = [lbs[r["seed"]]["lb"][n] for r in runs[3000]]
    infeasible = [r for r in fail if lbs[r["seed"]]["lb"][n] > 3000]
    t12 = [r["ach_step"][i] for r in runs[12000] if r["ach_step"][i] >= 0]
    e6 = sum(r["ach_step"][i] >= 0 for r in runs[6000])
    hard[n] = {"earned_3000": len(e3), "earned_6000": e6, "earned_12000": len(t12),
               "lb_median": st.median(lb), "lb_max": max(lb), "fail_provably_infeasible": len(infeasible),
               "fail_planner_ran_out": len(fail) - len(infeasible),
               "steps_12000": {"median": st.median(t12), "p90": pct(t12, 0.9), "max": max(t12)}}
    h = hard[n]
    print(f"| {n} | {h['earned_3000']}/128 | {h['earned_6000']}/128 | {h['earned_12000']}/128 | {h['lb_median']} ({h['lb_max']}) | "
          f"{h['fail_provably_infeasible']} | {h['fail_planner_ran_out']} | {h['steps_12000']['median']} / {h['steps_12000']['p90']} / {h['steps_12000']['max']} |")
summary["hard"] = hard

# Lower bounds of the whole hard set and consistency (LB <= achieved step).
allhard = [lbs[s]["lb"]["all hard"] for s in lbs]
viol = 0
for r in runs[12000]:
    for n in HARD:
        t = r["ach_step"][NAMES.index(n)]
        if t >= 0 and t < lbs[r["seed"]]["lb"][n]:
            viol += 1
done12 = [max(r["ach_step"]) for r in runs[12000]]
hard_done12 = [max(r["ach_step"][NAMES.index(n)] for n in HARD) for r in runs[12000]]
summary["lower_bound_all_hard"] = {"median": st.median(allhard), "max": max(allhard), "min": min(allhard),
                                   "worlds_over_3000": sum(v > 3000 for v in allhard),
                                   "violations_lb_above_achieved": viol}
summary["completion_12000"] = {"all32_median": st.median(done12), "all32_p90": pct(done12, 0.9),
                               "all32_max": max(done12), "worlds_all32_within_3000": sum(d <= 3000 for d in done12),
                               "hard7_median": st.median(hard_done12), "hard7_max": max(hard_done12)}
print(f"\nall-hard lower bound: median {st.median(allhard)}, min {min(allhard)}, max {max(allhard)}; "
      f"worlds with LB > 3000: {sum(v > 3000 for v in allhard)}; LB-above-achieved violations: {viol}")
print("12k run: step of 32nd achievement median %s p90 %s max %s; worlds finishing all 32 within 3000: %d" % (
    st.median(done12), pct(done12, 0.9), max(done12), sum(d <= 3000 for d in done12)))

acts = runs[3000][0]["acts"].keys()
summary["acts_h3000_median"] = {k: st.median(r["acts"][k] for r in runs[3000]) for k in acts}
print("median action mix @3000:", summary["acts_h3000_median"])
ores = [lbs[s]["ore"] for s in lbs]
summary["world_resources"] = {k: {"min": min(o[k] for o in ores), "median": st.median(o[k] for o in ores),
                                  "max": max(o[k] for o in ores)} for k in ("iron", "gold", "copper", "silver")}
summary["world_resources"]["wood"] = {"min": min(lbs[s]["wood_available"] for s in lbs),
                                      "median": st.median(lbs[s]["wood_available"] for s in lbs),
                                      "max": max(lbs[s]["wood_available"] for s in lbs)}
print("resources:", summary["world_resources"])
fails = []
for r in runs[3000]:
    miss = [NAMES[i] for i in range(32) if r["ach_step"][i] < 0]
    if miss:
        fails.append({"seed": r["seed"], "score": r["score"], "missing": miss, "got": r["got"]})
summary["h3000_failures"] = fails
print("3000-step failures:", fails)
json.dump(summary, open(os.path.join(R, "summary.json"), "w"), indent=1)
