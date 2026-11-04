"""Generates notebooks/v8_env_results_2026_10_31.ipynb (run, then execute the notebook)."""
import json, textwrap
from pathlib import Path
def md(s): return {"cell_type":"markdown","metadata":{},"source":textwrap.dedent(s).strip("\n").splitlines(True)}
def code(s): return {"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":textwrap.dedent(s).strip("\n").splitlines(True)}
cells=[
md("""
# v8 environment-option results (Oct 31 - Nov 1, 2026)

All eg15 PPO runs on the v8 preview (frozen v7 core plus environment knobs, `variants/v8`):

| Study | Launched | What it tests |
|---|---|---|
| 512M wave | Oct 31 evening | one environment factor at a time (ore, trees, view, episode length) |
| 2B wave | Oct 31 night | best variants at 2B; width, LSTM, frontier shaping; larger world |
| overnight | Nov 1 night | 1% uniform mixing, log-scale inventory, frontier combinations, more seeds, 4B |
| Nov 1 morning | Nov 1 07:20 EST | frontier coefficient 10, frontier-surface, no-shaping controls, larger world / view |
| discount | Nov 1 10:00 EST | gamma .9995 / .9998 on the best shaped and best generic arms |
| long runs | Nov 1 10:00 EST | larger world (default ore) and view 21x15 at 4B, larger-world LSTM |
| Go-Explore | Nov 1 13:35 EST | archive restarts from the policy's own states |
| final 5 seeds | Nov 1 15:10 EST | seeds 2003-2005 for the final configurations (5 seeds each) |
| gamma .9998 at 4B | Nov 1 17:25 EST | best shaped and generic arms at 4B (first iron pickaxe: best shaped, seed 2001) |
| gamma .9999 | Nov 1 ~19:00 EST | generic arm at gamma .9999, 2B |
| pickaxe follow-ups | Nov 3 17:43 EST | best shaped gamma .9998 at 6B and two more 4B seeds; both arms at gamma .9999, 4B; frontier-surface at gamma .9998, 4B |

The final configurations were also evaluated once on the reserved test worlds (25,000,001-25,000,128):
`test.json` next to each run's `curve.json` (Part 3).

Each run directory holds `curve.json` (validation at every checkpoint), `summary.json`, `protocol.json`
(full training config) and `diag.json` (stockpiling diagnostic on the final checkpoint). All evaluations
use the same 128 validation worlds (23,000,001-23,000,128); scores are achievements out of 32.
Unfinished runs show their latest checkpoint.

Open from the repo root with pandas and matplotlib, e.g.

    uv run --no-project --with pandas,matplotlib,jupyterlab jupyter lab notebooks/v8_env_results_2026_10_31.ipynb

Refresh data from eg15 (curves, summaries, protocols, diagnostics only), per study directory:

    rsync -a -e "ssh -J decidueye" --include='*/' --include='curve.json' --include='summary.json' \\
      --include='protocol.json' --include='diag.json' --exclude='*' \\
      mvohl@cv350-rck-g03-c01-08.rck.dcgpu:Projects/RL/experiments/<study>/ experiments/eg15/<study>/
"""),
code("""
import json
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
pd.set_option("display.max_columns", 60)
pd.set_option("display.width", 250)

ROOT = Path("..") if Path("../experiments/eg15").exists() else Path(".")
DATA = ROOT / "experiments/eg15"
STUDIES = {  # label -> directory under DATA; add new studies here
    "512M wave": "eg15-envopt-v7-20261027",
    "2B wave": "eg15-envopt2b-v8-20261101",
    "overnight": "eg15-overnight-v8-20261101",
    "Nov 1 morning": "eg15-queue-v8-20261101b",
    "discount": "eg15-gamma-v8-20261101c",
    "long runs": "eg15-long-v8-20261101c",
    "Go-Explore": "eg15-goexplore-v8-20261101e",
    "final 5 seeds": "eg15-final5-v8-20261101f",
    "gamma .9998 at 4B": "eg15-4b-v8-20261101g",
    "gamma .9999": "eg15-g9999-v8-20261101g",
    "pickaxe follow-ups": "eg15-pickaxe-v8-20261103",
}
# Environment knobs per library build (variants/v8/README.md). Defaults reproduce v7.
LIBS = {
    "build-v8":                {"ore %": 100, "trunk %": 100, "view": "11x9",  "world": "128x96", "log inventory": False},
    "build-v8-ore200":         {"ore %": 200, "trunk %": 100, "view": "11x9",  "world": "128x96", "log inventory": False},
    "build-v8-ore300":         {"ore %": 300, "trunk %": 100, "view": "11x9",  "world": "128x96", "log inventory": False},
    "build-v8-tree200":        {"ore %": 100, "trunk %": 200, "view": "11x9",  "world": "128x96", "log inventory": False},
    "build-v8-ore300-tree200": {"ore %": 300, "trunk %": 200, "view": "11x9",  "world": "128x96", "log inventory": False},
    "build-v8-view21":         {"ore %": 100, "trunk %": 100, "view": "21x15", "world": "128x96", "log inventory": False},
    "build-v8-real":           {"ore %": 300, "trunk %": 200, "view": "21x15", "world": "128x96", "log inventory": False},
    "build-v8-o3t2-inv":       {"ore %": 300, "trunk %": 200, "view": "11x9",  "world": "128x96", "log inventory": True},
    "build-v8-real-inv":       {"ore %": 300, "trunk %": 200, "view": "21x15", "world": "128x96", "log inventory": True},
    "build-v8-w256":           {"ore %": 100, "trunk %": 100, "view": "11x9",  "world": "256x96", "log inventory": False},
    "build-v8-w256-o3t2":      {"ore %": 300, "trunk %": 200, "view": "11x9",  "world": "256x96", "log inventory": False},
}
ACHIEVEMENTS = ["collect wood", "collect stone", "place block", "craft workbench", "craft furnace", "craft anvil", "place torch", "place platform", "collect copper", "collect iron", "collect silver", "collect gold", "smelt copper", "smelt iron", "smelt silver", "smelt gold", "defeat Blue Slime", "defeat Cave Bat", "open chest", "craft wooden sword", "craft metal sword", "craft wood breastplate", "craft iron chainmail", "heal with food or potion", "use life crystal", "double jump", "descend deep", "return to surface", "explore 30 columns", "climb rope", "craft iron pickaxe", "craft gold pickaxe"]  # SPEC.achievement_names (v7/v8)
HARD = ["craft anvil", "craft metal sword", "craft iron pickaxe", "craft gold pickaxe",
        "craft iron chainmail", "craft wood breastplate", "return to surface"]
# Queue files map job names to library builds (runs launched by tools/gpu_queue.py).
JOB_LIB = {j["name"]: j["lib"] for q in (ROOT / "tools").glob("*queue*.json") for j in json.loads(q.read_text())}
JOB_LIB["view21_4B-g7"] = "build-v8-view21"   # launched by hand next to the Nov 1 morning queue
"""),
code("""
def lib_of(group_dir: str) -> str:
    if group_dir in JOB_LIB:
        return JOB_LIB[group_dir]
    head, _, tail = group_dir.rpartition("-")          # wave dirs: build-v8-xxx or build-v8-xxx-g3
    return head if tail.startswith("g") and tail[1:].isdigit() else group_dir

def variant_label(k: dict) -> str:
    parts = []
    if k["world"] != "128x96": parts.append(f"world {k['world']}")
    if k["ore %"] != 100: parts.append(f"ore {k['ore %'] // 100}x")
    if k["trunk %"] != 100: parts.append(f"trees {k['trunk %'] // 100}x")
    if k["view"] != "11x9": parts.append(f"view {k['view']}")
    if k["log inventory"]: parts.append("log inventory")
    return " + ".join(parts) or "v8 default (= v7)"

def arm_label(c: dict) -> str:
    shaping = "no shaping" if not c["potential_coef"] else \\
        f"pot {c['potential_coef']:g}" + (f" {c['potential_mode']}" if c["potential_mode"] != "mean" else "")
    parts = [shaping]
    if c.get("novelty_coef"): parts.append(f"novelty {c['novelty_coef']:g}")
    if c.get("unimix"): parts.append(f"unimix {c['unimix']:g}")
    if c.get("archive_start_prob"): parts.append(f"Go-Explore {c['archive_start_prob']:g}")
    if c.get("memory"): parts.append(f"{c['memory']} {c.get('memory_size') or 256}")
    if c.get("hidden"): parts.append(f"hidden {c['hidden']}")
    if c.get("lr") != 3e-4: parts.append(f"lr {c['lr']:g}")
    if c.get("gamma") != 0.999: parts.append(f"gamma {c['gamma']:g}")
    if c.get("episode_steps"): parts.append(f"{c['episode_steps']} steps/ep")
    return ", ".join(parts)

def crafter_score(hits: dict, episodes: int) -> float:
    \"\"\"Crafter's headline metric: geometric mean of per-achievement success rates (in %),
    S = exp(mean(ln(1 + s_i))) - 1 over all achievements (Hafner 2021).\"\"\"
    import math
    rates = [100 * hits.get(n, 0) / episodes for n in ACHIEVEMENTS]
    return math.exp(sum(math.log1p(r) for r in rates) / len(rates)) - 1

def budget(steps: int) -> str:
    return f"{steps / 2**30:.0f}B" if steps >= 2**30 else f"{steps / 2**20:.0f}M"

rows, curves = [], []
for study, sub in STUDIES.items():
    for run in sorted((DATA / sub).glob("*/runs/*")):
        if not (run / "curve.json").exists():
            continue
        curve = json.loads((run / "curve.json").read_text())
        proto = json.loads((run / "protocol.json").read_text())
        cfg = proto["config"]
        lib = lib_of(run.parent.parent.name)
        knobs = LIBS.get(lib, {"ore %": None, "trunk %": None, "view": "?", "world": "?", "log inventory": None})
        ev = curve[-1]["evaluation"]
        key = dict(study=study, variant=variant_label(knobs) if lib in LIBS else lib, arm=arm_label(cfg),
                   budget=budget(proto["actual_steps"]), seed=int(run.name.rsplit("-", 1)[1]))
        row = dict(key, run=f"{run.parent.parent.name}/{run.name}", lib=lib, **knobs,
                   potential=cfg["potential_coef"], potential_mode=cfg["potential_mode"] if cfg["potential_coef"] else "-",
                   novelty=cfg["novelty_coef"], unimix=cfg.get("unimix", 0), go_explore=cfg.get("archive_start_prob", 0),
                   memory=cfg.get("memory") or "-", hidden=cfg.get("hidden") or 128, lr=cfg["lr"], gamma=cfg["gamma"],
                   episode_steps=proto.get("episode_steps", 3000), params=proto.get("parameters"),
                   steps_B=curve[-1]["steps"] / 2**30, hours=curve[-1]["elapsed_seconds"] / 3600,
                   finished=(run / "summary.json").exists(),
                   score=ev["mean_achievements"], best=max(c["evaluation"]["mean_achievements"] for c in curve),
                   crafter_score=crafter_score(ev["hits"], ev["episodes"]),
                   deaths=ev["death_rate"], idle_steps=ev["mean_steps_after_last_achievement"],
                   **{h: ev["hits"].get(h, 0) for h in HARD})
        if (run / "test.json").exists():
            test = json.loads((run / "test.json").read_text())
            row.update(test_score=test["mean_achievements"], test_crafter_score=crafter_score(test["hits"], test["episodes"]))
        if (run / "diag.json").exists():
            diag = json.loads((run / "diag.json").read_text())
            peak, acts = diag["inventory_peak"], diag["actions"]
            row.update(iron_bars_med=peak["iron bar"]["median"], iron_bars_max=peak["iron bar"]["max"],
                       gold_bars_med=peak["gold bar"]["median"], wood_med=peak["wood"]["median"],
                       iron_bars_smelted_per_ep=acts["smelt iron"]["chosen"] / diag["episodes"],
                       breastplate_legal_eps=acts["craft wood breastplate"]["episodes_with_opportunity"],
                       iron_pick_legal_eps=acts["craft iron pickaxe"]["episodes_with_opportunity"])
        rows.append(row)
        curves += [dict(key, steps_B=c["steps"] / 2**30, score=c["evaluation"]["mean_achievements"]) for c in curve]

runs = pd.DataFrame(rows)
curves = pd.DataFrame(curves)
print(f"{len(runs)} runs, {runs.finished.sum()} finished, {runs.iron_bars_med.notna().sum()} with diagnostics")
runs[["study", "variant", "arm", "budget", "seed", "steps_B", "finished", "score", "best", *HARD]].sort_values(
    ["study", "variant", "arm", "seed"]).reset_index(drop=True)
"""),
md("""
## Summary per study, variant and arm

Means over seeds. Hard-tier columns are validation worlds out of 128; `*_med` are median per-episode
peaks of items held at once (stockpiling); `*_legal_eps` count episodes where the craft was ever possible.
"""),
code("""
cols = ["score", "best", "deaths", *HARD, "iron_bars_med", "wood_med", "breastplate_legal_eps", "iron_pick_legal_eps"]
summary = (runs.groupby(["study", "variant", "arm", "budget"])
               .agg(seeds=("seed", "count"), done=("finished", "sum"), **{c: (c, "mean") for c in cols})
               .round(2).sort_values(["study", "score"], ascending=[True, False]))
summary
"""),
md("## Learning curves (mean over seeds)"),
code("""
def plot(study, ax):
    sub = curves[curves.study == study]
    for (variant, arm, b), g in sub.groupby(["variant", "arm", "budget"]):
        m = g.groupby("steps_B").score.mean()
        ax.plot(m.index, m.values, marker=".", label=f"{variant} | {arm} ({b})")
    ax.set(title=study, xlabel="env steps (billions)", ylabel="validation score /32")
    ax.grid(alpha=.3)
    ax.legend(fontsize=6.5, loc="lower right")

ncols = 2
nrows = -(-len(STUDIES) // ncols)
fig, axes = plt.subplots(nrows, ncols, figsize=(9 * ncols, 6 * nrows), squeeze=False)
for study, ax in zip(STUDIES, axes.flat):
    plot(study, ax)
for ax in axes.flat[len(STUDIES):]:
    ax.set_visible(False)
plt.tight_layout()
"""),
md("## Hard achievements of the best arms (worlds out of 128, mean over seeds)"),
code("""
top = summary.reset_index().sort_values("score", ascending=False).head(12)
top = top.assign(label=top.variant + " | " + top.arm + " (" + top.budget + ", " + top.study + ")").set_index("label")
top[HARD].plot.barh(figsize=(11, 8), width=.8)
plt.xlabel("worlds out of 128")
plt.gca().invert_yaxis()
plt.tight_layout()
"""),
md("## Per-seed detail for one variant\n\nChange `VARIANT` to inspect seed variance (return to surface differs a lot between seeds)."),
code("""
VARIANT = "ore 3x + trees 2x + log inventory"
runs[runs.variant == VARIANT].sort_values(["study", "arm", "seed"])[
    ["study", "arm", "budget", "seed", "steps_B", "score", *HARD, "iron_bars_med", "wood_med"]]
"""),
md("""
# Part 2: run catalogue and comparisons

## Every run and exactly how it differs

One row per run. Environment columns come from the library build (`variants/v8` knobs); training columns
come from the run's own `protocol.json`. Fixed for every run unless listed: PPO on the max-speed path,
1,024 envs x 128-step rollouts, 16 minibatches, entropy .03, GAE lambda .99, `targets` architecture
(per-cell MLP width 32, depth 2), bf16 + compile, 128 validation worlds.
"""),
code("""
catalogue_cols = ["study", "run", "seed", "budget", "steps_B", "hours", "finished",
                  # environment
                  "world", "ore %", "trunk %", "view", "log inventory", "episode_steps",
                  # training
                  "potential", "potential_mode", "novelty", "unimix", "go_explore", "gamma", "lr", "hidden", "memory", "params",
                  # results
                  "score", "best", "deaths", "idle_steps", *HARD,
                  "iron_bars_med", "iron_bars_max", "iron_bars_smelted_per_ep", "gold_bars_med", "wood_med",
                  "breastplate_legal_eps", "iron_pick_legal_eps"]
catalogue = runs[catalogue_cols].sort_values(["study", "world", "ore %", "view", "potential", "seed"]).reset_index(drop=True)
catalogue
"""),
md("""
## Comparisons along each dimension

Each table compares runs that differ in **one** dimension, holding the others as fixed as the data allows
(same budget, same arm or same environment). `delta` is the mean difference to the reference row.
Seeds are listed so seed noise (often 0.3-0.5 points) can be judged against the delta.
"""),
code("""
def compare(title, groups, ref):
    \"\"\"groups: {label: boolean mask over runs}. Mean/std/seeds and key outcomes per label.
    Unfinished runs are included at their latest checkpoint (done < runs; their seeds are marked *).\"\"\"
    out = []
    for label, mask in groups.items():
        g = runs[mask]
        if g.empty:
            continue
        out.append(dict(setting=label, runs=len(g), done=int(g.finished.sum()),
                        seeds=", ".join(f"{s:.2f}" + ("" if f else "*") for s, f in zip(g.score, g.finished)),
                        score=g.score.mean(), score_sd=g.score.std(ddof=0), anvil=g["craft anvil"].mean(),
                        breastplate=g["craft wood breastplate"].mean(), surface=g["return to surface"].mean(),
                        iron_pick=g["craft iron pickaxe"].mean(), iron_bars_med=g.iron_bars_med.mean(),
                        wood_med=g.wood_med.mean(), deaths=g.deaths.mean(), hours=g.hours.mean()))
    t = pd.DataFrame(out).set_index("setting")
    if ref in t.index:
        t.insert(4, "delta", t.score - t.loc[ref, "score"])
    print(title)
    return t.round(2)

v = runs
std = (v.potential == 3) & (v.potential_mode == "mean") & (v.novelty == 0) & (v.unimix == 0) & (v.go_explore == 0) \\
      & (v.memory == "-") & (v.hidden == 128) & (v.gamma == 0.999) & (v.lr == 3e-4)
std3k = std & (v.episode_steps == 3000)
"""),
code("""
# 1. Resource supply (standard arm, 3,000-step episodes, 11x9 view, 128-wide world)
base_env = (v.view == "11x9") & (v.world == "128x96") & ~v["log inventory"].astype(bool)
display(compare("Supply at 512M", {
    "v8 default": std3k & base_env & (v["ore %"] == 100) & (v["trunk %"] == 100) & (v.budget == "512M"),
    "ore 2x": std3k & base_env & (v["ore %"] == 200) & (v["trunk %"] == 100) & (v.budget == "512M"),
    "ore 3x": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 100) & (v.budget == "512M"),
    "trees 2x": std3k & base_env & (v["ore %"] == 100) & (v["trunk %"] == 200) & (v.budget == "512M"),
    "ore 3x + trees 2x": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "512M"),
}, ref="v8 default"))
display(compare("Supply at 2B", {
    "v8 default": std3k & base_env & (v["ore %"] == 100) & (v.budget == "2B"),
    "ore 3x + trees 2x": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "2B"),
}, ref="v8 default"))
"""),
code("""
# 2. Reward shaping and generic exploration on ore 3x + trees 2x (2B, gamma .999, 128 hidden, no memory)
o3t2 = (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.view == "11x9") & (v.world == "128x96") & (v.budget == "2B") \\
       & (v.gamma == 0.999) & (v.memory == "-") & (v.episode_steps == 3000) & (v.go_explore == 0)
h128 = v.hidden == 128
inv = v["log inventory"].astype(bool)
display(compare("Shaping / exploration aids (ore 3x + trees 2x, 2B)", {
    "pot 3 mean (standard)": o3t2 & ~inv & std,
    "no shaping": o3t2 & ~inv & h128 & (v.potential == 0) & (v.novelty == 0) & (v.unimix == 0),
    "no shaping + novelty + unimix": o3t2 & ~inv & h128 & (v.potential == 0) & (v.novelty > 0) & (v.unimix > 0),
    "pot 3 mean + unimix": o3t2 & ~inv & h128 & (v.potential == 3) & (v.potential_mode == "mean") & (v.unimix > 0),
    "frontier + novelty": o3t2 & ~inv & h128 & (v.potential_mode == "frontier") & (v.unimix == 0),
    "log inv + pot 3 mean": o3t2 & inv & std,
    "log inv + frontier + novelty + unimix": o3t2 & inv & h128 & (v.potential == 3) & (v.potential_mode == "frontier") & (v.unimix > 0),
    "log inv + frontier coef 10": o3t2 & inv & h128 & (v.potential == 10),
    "log inv + frontier_surface": o3t2 & inv & h128 & (v.potential_mode == "frontier_surface"),
}, ref="pot 3 mean (standard)"))
"""),
code("""
# 3. Discount horizon (ore 3x + trees 2x, 2B)
best_arm = inv & (v.potential == 3) & (v.potential_mode == "frontier") & (v.unimix > 0) & (v.hidden == 128) & (v.go_explore == 0)
gen_arm = ~inv & (v.potential == 0) & (v.novelty > 0) & (v.unimix > 0) & (v.hidden == 128) & (v.go_explore == 0)
cond = (v["ore %"] == 300) & (v.world == "128x96") & (v.view == "11x9") & (v.budget == "2B") & (v.memory == "-")
display(compare("Discount: best shaped arm", {f"gamma {g:g}": cond & best_arm & (v.gamma == g) for g in (0.999, 0.9995, 0.9998)},
                ref="gamma 0.999"))
display(compare("Discount: generic arm (no shaping)", {f"gamma {g:g}": cond & gen_arm & (v.gamma == g) for g in (0.999, 0.9995, 0.9998)},
                ref="gamma 0.999"))
"""),
code("""
# 4. Model capacity and memory
display(compare("Capacity / memory on ore 3x + trees 2x (2B)", {
    "standard (hidden 128)": o3t2 & ~inv & std,
    "hidden 1024, lr 1e-4": o3t2 & ~inv & (v.potential == 3) & (v.potential_mode == "mean") & (v.hidden == 1024),
    "LSTM 256": (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "2B") & (v.memory == "lstm"),
    "generic arm, hidden 128": o3t2 & gen_arm,
    "generic arm, hidden 1024": o3t2 & ~inv & (v.potential == 0) & (v.hidden == 1024),
    "best shaped arm, hidden 128": o3t2 & best_arm,
    "best shaped arm, hidden 1024": o3t2 & inv & (v.potential_mode == "frontier") & (v.hidden == 1024),
}, ref="standard (hidden 128)"))
"""),
code("""
# 5. Larger world and larger view (all budgets; default supply unless stated)
display(compare("Larger world", {
    "128x96, standard, 2B": std3k & base_env & (v["ore %"] == 100) & (v.budget == "2B"),
    "256x96, standard, 2B": std3k & (v.world == "256x96") & (v["ore %"] == 100),
    "256x96, standard, 6000 steps/ep, 2B": std & (v.world == "256x96") & (v["ore %"] == 100) & (v.episode_steps == 6000),
    "256x96, generic arm, 6000 steps/ep, 4B": (v.world == "256x96") & (v["ore %"] == 100) & (v.potential == 0) & (v.memory == "-") & (v.go_explore == 0),
    "256x96, frontier arm, 6000 steps/ep, 4B": (v.world == "256x96") & (v["ore %"] == 100) & (v.potential_mode == "frontier"),
    "256x96, generic + LSTM, 6000 steps/ep, 2B": (v.world == "256x96") & (v.memory == "lstm"),
    "256x96, generic + Go-Explore": (v.world == "256x96") & (v.go_explore > 0),
    "256x96 + ore 3x + trees 2x, 6000 steps/ep, 2B": (v.world == "256x96") & (v["ore %"] == 300),
}, ref="128x96, standard, 2B"))
display(compare("Larger view (default supply)", {
    "11x9, standard, 2B": std3k & base_env & (v["ore %"] == 100) & (v.budget == "2B"),
    "21x15, standard, 2B": std3k & (v.view == "21x15") & (v["ore %"] == 100) & (v.budget == "2B"),
    "21x15, standard, 4B": std3k & (v.view == "21x15") & (v["ore %"] == 100) & (v.budget == "4B"),
    "21x15, hidden 512, 2B": (v.view == "21x15") & (v["ore %"] == 100) & (v.hidden == 512) & (v.potential == 3),
    "21x15, generic arm, 4B": (v.view == "21x15") & (v["ore %"] == 100) & (v.potential == 0) & (v.hidden == 128) & (v.go_explore == 0),
    "21x15, generic arm + hidden 512, 4B": (v.view == "21x15") & (v["ore %"] == 100) & (v.potential == 0) & (v.hidden == 512),
    "21x15, generic + Go-Explore, 4B": (v.view == "21x15") & (v.go_explore > 0),
}, ref="11x9, standard, 2B"))
"""),
code("""
# 6. Training budget: same arm at 512M / 2B / 4B
display(compare("Budget", {
    "ore 3x + trees 2x, standard, 512M": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "512M"),
    "ore 3x + trees 2x, standard, 2B": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "2B"),
    "best shaped arm, 2B": cond & best_arm & (v.gamma == 0.999),
    "best shaped arm, 4B": (v["ore %"] == 300) & best_arm & (v.budget == "4B") & (v.gamma == 0.999),
}, ref="ore 3x + trees 2x, standard, 2B"))
"""),
code("""
# 7. Go-Explore vs the same arm without it (in progress)
display(compare("Go-Explore restarts (20% of training episodes)", {
    "generic arm, ore 3x + trees 2x": o3t2 & gen_arm & (v.gamma == 0.999),
    "generic arm + Go-Explore": (v["ore %"] == 300) & (v.world == "128x96") & ~inv & (v.potential == 0) & (v.go_explore > 0),
    "best shaped arm": cond & best_arm & (v.gamma == 0.999),
    "best shaped arm + Go-Explore": (v["ore %"] == 300) & inv & (v.potential_mode == "frontier") & (v.go_explore > 0),
}, ref="generic arm, ore 3x + trees 2x"))
"""),
md("## Training health by discount factor\n\nPPO does not log its loss values; each checkpoint records the last update's policy entropy, approximate\nKL, clip fraction and value explained variance (`curve.json` -> `profile`). One line per seed."),
code('metrics = [("score", "validation score /32"), ("policy_entropy", "policy entropy"), ("approx_kl", "approx KL (log)"),\n           ("clip_fraction", "clip fraction"), ("explained_variance", "value explained variance")]\ncolors = {0.999: "tab:gray", 0.9995: "tab:blue", 0.9998: "tab:red"}\ngmask = (v["ore %"] == 300) & (v.world == "128x96") & (v.view == "11x9") & (v.budget == "2B") & (v.memory == "-") & (v.go_explore == 0)\nfig, axes = plt.subplots(2, len(metrics), figsize=(5 * len(metrics), 8))\nfor row, (arm, mask) in enumerate({"generic": gmask & gen_arm, "best shaped": gmask & best_arm}.items()):\n    for _, r in runs[mask].iterrows():\n        study_dir = DATA / STUDIES[r.study]\n        group, name = r.run.split("/")\n        curve = json.loads((study_dir / group / "runs" / name / "curve.json").read_text())\n        x = [c["steps"] / 2**30 for c in curve]\n        for col, (m, label) in enumerate(metrics):\n            y = [c["evaluation"]["mean_achievements"] if m == "score" else c["profile"][m] for c in curve]\n            axes[row, col].plot(x, y, color=colors.get(r.gamma, "k"), alpha=.8, lw=1.2)\n    for col, (m, label) in enumerate(metrics):\n        ax = axes[row, col]\n        ax.set_title(f"{arm}: {label}", fontsize=10); ax.grid(alpha=.3); ax.set_xlabel("env steps (B)")\n        if m == "approx_kl": ax.set_yscale("log")\n        if m == "explained_variance": ax.set_ylim(0.98, 1.0)\n    for g, c in colors.items():\n        axes[row, 0].plot([], [], color=c, label=f"gamma {g}")\n    axes[row, 0].legend(fontsize=8)\nplt.tight_layout()'),
md("""
# Part 3: statistics for the final configurations

Convention for deep-RL comparisons (Agarwal et al. 2021, `rliable`): report the interquartile mean (IQM)
over seeds with a bootstrapped 95% confidence interval, plus the probability of improvement
P(X > Y) = chance a random seed of X beats a random seed of Y. Final checkpoints only; validation worlds.
The Crafter score is Crafter's geometric-mean metric over all 32 achievements, which rewards rare
achievements much more than the mean count.
"""),
code("""
import numpy as np
rng = np.random.default_rng(0)

def iqm(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    k = int(np.floor(0.25 * n))
    return x[k:n - k].mean() if n - 2 * k > 0 else x.mean()

def boot_ci(x, stat=iqm, n=10000):
    x = np.asarray(x, float)
    s = [stat(rng.choice(x, len(x))) for _ in range(n)]
    return np.percentile(s, [2.5, 97.5])

def p_improve(x, y):
    x, y = np.asarray(x)[:, None], np.asarray(y)[None, :]
    return float((x > y).mean() + 0.5 * (x == y).mean())

FINAL = {
    "v8 default (= v7), standard": std3k & base_env & (v["ore %"] == 100) & (v.budget == "2B"),
    "ore 3x + trees 2x, standard": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "2B"),
    "ore 3x + trees 2x, generic, gamma .9998": (v["ore %"] == 300) & (v.world == "128x96") & (v.view == "11x9") & (v.budget == "2B") & gen_arm & (v.gamma == 0.9998),
    "ore 3x + trees 2x + log inv, best shaped, gamma .9998": (v["ore %"] == 300) & (v.world == "128x96") & (v.view == "11x9") & (v.budget == "2B") & best_arm & (v.gamma == 0.9998),
}
table = []
for name, mask in FINAL.items():
    g = runs[mask & runs.finished]
    if g.empty:
        continue
    lo, hi = boot_ci(g.score)
    clo, chi = boot_ci(g.crafter_score)
    t = g.test_score.dropna() if "test_score" in g else pd.Series(dtype=float)
    tlo, thi = boot_ci(t) if len(t) else (np.nan, np.nan)
    table.append(dict(config=name, seeds=len(g), scores=", ".join(f"{s:.2f}" for s in sorted(g.score)),
                      mean=g.score.mean(), IQM=iqm(g.score), ci_low=lo, ci_high=hi,
                      crafter_score=g.crafter_score.mean(), crafter_ci=f"[{clo:.1f}, {chi:.1f}]",
                      surface_runs_over_100=int((g["return to surface"] > 100).sum()),
                      test_seeds=len(t), test_IQM=iqm(t) if len(t) else np.nan, test_ci_low=tlo, test_ci_high=thi,
                      test_crafter=g.test_crafter_score.mean() if "test_crafter_score" in g else np.nan))
final_table = pd.DataFrame(table).set_index("config").round(2)
final_table
"""),
code("""
names = list(FINAL)
groups = {n: runs[FINAL[n] & runs.finished].score.values for n in names}
pairs = [(a, b) for a in names for b in names if a != b and len(groups[a]) and len(groups[b])]
pd.DataFrame([dict(X=a, Y=b, P_X_beats_Y=round(p_improve(groups[a], groups[b]), 2)) for a, b in pairs]).pivot(index="X", columns="Y", values="P_X_beats_Y")
"""),
md("## Score against compute (GPU-hours per run; 2 runs shared a GPU unless noted in the study)"),
code("""
fin = runs[runs.finished]
fig, ax = plt.subplots(figsize=(10, 6))
for study, g in fin.groupby("study"):
    ax.scatter(g.hours, g.score, label=study, alpha=.75)
ax.set(xlabel="wall-clock hours per run", ylabel="final score /32", title="Score vs wall-clock")
ax.grid(alpha=.3); ax.legend(fontsize=8)
plt.tight_layout()
"""),
]
nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python"}},"nbformat":4,"nbformat_minor":5}
Path(__file__).resolve().parents[1].joinpath('notebooks/v8_env_results_2026_10_31.ipynb').write_text(json.dumps(nb,indent=1)+"\n"); print("written")
