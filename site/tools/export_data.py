"""Export the real Terraria-Lite results the site shows into site/data/.

Reads only local, gitignored experiment artifacts and writes small JSON files:

  site/data/rl.json    v8 PPO runs (eg15): catalogue, learning curves, final-config
                       statistics (IQM, bootstrap 95% CIs, test worlds), one-dimension
                       comparisons, per-achievement hit counts and first-unlock steps.
                       Logic follows notebooks/v8_env_results_2026_10_31.ipynb exactly
                       (same filters, same numpy RNG seed and call order for the CIs).
  site/data/llm.json   every audited LLM attempt on Terraria-Lite v7 (Sol smoke, Luna
                       batch, Luna harness study), with per-attempt cost, actions,
                       illegal attempts, first-unlock steps and the native final state.
  site/data/tapes/     the attempts' action tapes, replayed in the browser by replay.html.

Run from the repository root:

  uv run --no-project --with pandas,numpy python site/tools/export_data.py
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "data"
DATA = ROOT / "experiments" / "eg15"

# ---- notebook constants (notebooks/v8_env_results_2026_10_31.ipynb, cell 1) ----
STUDIES = {
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
ACHIEVEMENTS = ["collect wood", "collect stone", "place block", "craft workbench", "craft furnace", "craft anvil",
                "place torch", "place platform", "collect copper", "collect iron", "collect silver", "collect gold",
                "smelt copper", "smelt iron", "smelt silver", "smelt gold", "defeat Blue Slime", "defeat Cave Bat",
                "open chest", "craft wooden sword", "craft metal sword", "craft wood breastplate",
                "craft iron chainmail", "heal with food or potion", "use life crystal", "double jump", "descend deep",
                "return to surface", "explore 30 columns", "climb rope", "craft iron pickaxe", "craft gold pickaxe"]
HARD = ["craft anvil", "craft metal sword", "craft iron pickaxe", "craft gold pickaxe",
        "craft iron chainmail", "craft wood breastplate", "return to surface"]
JOB_LIB = {j["name"]: j["lib"] for q in (ROOT / "tools").glob("*queue*.json") for j in json.loads(q.read_text())}
JOB_LIB["view21_4B-g7"] = "build-v8-view21"


def lib_of(group_dir: str) -> str:
    if group_dir in JOB_LIB:
        return JOB_LIB[group_dir]
    head, _, tail = group_dir.rpartition("-")
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
    shaping = "no shaping" if not c["potential_coef"] else \
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
    rates = [100 * hits.get(n, 0) / episodes for n in ACHIEVEMENTS]
    return math.exp(sum(math.log1p(r) for r in rates) / len(rates)) - 1


def budget(steps: int) -> str:
    return f"{steps / 2**30:.0f}B" if steps >= 2**30 else f"{steps / 2**20:.0f}M"


def load_runs():
    rows, curves, evals = [], {}, {}
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
            rid = f"{sub}/{run.parent.parent.name}/{run.name}"
            row = dict(key, id=rid, run=f"{run.parent.parent.name}/{run.name}", lib=lib, **knobs,
                       potential=cfg["potential_coef"], potential_mode=cfg["potential_mode"] if cfg["potential_coef"] else "-",
                       novelty=cfg["novelty_coef"], unimix=cfg.get("unimix", 0), go_explore=cfg.get("archive_start_prob", 0),
                       memory=cfg.get("memory") or "-", hidden=cfg.get("hidden") or 128, lr=cfg["lr"], gamma=cfg["gamma"],
                       episode_steps=proto.get("episode_steps", 3000), params=proto.get("parameters"),
                       steps=curve[-1]["steps"], steps_B=curve[-1]["steps"] / 2**30,
                       hours=curve[-1]["elapsed_seconds"] / 3600,
                       finished=(run / "summary.json").exists(),
                       score=ev["mean_achievements"], best=max(c["evaluation"]["mean_achievements"] for c in curve),
                       crafter_score=crafter_score(ev["hits"], ev["episodes"]),
                       deaths=ev["death_rate"], idle_steps=ev["mean_steps_after_last_achievement"],
                       **{h: ev["hits"].get(h, 0) for h in HARD})
            if (run / "summary.json").exists():
                row["sps"] = json.loads((run / "summary.json").read_text()).get("sps")
            test = None
            if (run / "test.json").exists():
                test = json.loads((run / "test.json").read_text())
                row.update(test_score=test["mean_achievements"],
                           test_crafter_score=crafter_score(test["hits"], test["episodes"]))
            if (run / "diag.json").exists():
                diag = json.loads((run / "diag.json").read_text())
                peak, acts = diag["inventory_peak"], diag["actions"]
                row.update(iron_bars_med=peak["iron bar"]["median"], iron_bars_max=peak["iron bar"]["max"],
                           gold_bars_med=peak["gold bar"]["median"], wood_med=peak["wood"]["median"],
                           iron_bars_smelted_per_ep=acts["smelt iron"]["chosen"] / diag["episodes"],
                           breastplate_legal_eps=acts["craft wood breastplate"]["episodes_with_opportunity"],
                           iron_pick_legal_eps=acts["craft iron pickaxe"]["episodes_with_opportunity"],
                           anvils_crafted_per_ep=acts["craft anvil"]["chosen"] / diag["episodes"],
                           anvil_peak_med=peak.get("anvil", {}).get("median"),
                           anvil_peak_max=peak.get("anvil", {}).get("max"))
            rows.append(row)
            curves[rid] = [[round(c["steps"] / 2**30, 4), round(c["evaluation"]["mean_achievements"], 4),
                            round(c["evaluation"]["death_rate"], 4)] for c in curve]
            evals[rid] = dict(
                validation=dict(episodes=ev["episodes"], hits=ev["hits"], records=ev.get("records") or []),
                test=dict(episodes=test["episodes"], hits=test["hits"], mean=test["mean_achievements"]) if test else None)
    return pd.DataFrame(rows), curves, evals


GRID = list(range(0, 3001, 50))


def progress(records):
    """Mean number of achievements unlocked by each step of GRID, over episodes."""
    if not records:
        return None
    out = []
    for t in GRID:
        out.append(sum(sum(1 for s in r["first_achievement_steps"].values() if s <= t) for r in records) / len(records))
    return [round(x, 4) for x in out]


def episode_stats(records):
    """Pooled per-episode statistics: median first-unlock step per achievement (episodes that unlocked it),
    mean cumulative achievements on GRID, and the distribution of achievements per episode."""
    fu = {}
    for a in ACHIEVEMENTS:
        vals = [r["first_achievement_steps"][a] for r in records if a in r["first_achievement_steps"]]
        fu[a] = float(np.median(vals)) if vals else None
    counts = [r["achievements"] for r in records]
    return dict(episodes_pooled=len(records), first_unlock_median=fu, progress=progress(records), progress_grid=GRID,
                score_hist={str(k): counts.count(k) for k in sorted(set(counts))},
                deaths_pooled=sum(1 for r in records if r.get("died")))


def main():
    runs, curves, evals = load_runs()
    v = runs
    std = (v.potential == 3) & (v.potential_mode == "mean") & (v.novelty == 0) & (v.unimix == 0) & (v.go_explore == 0) \
        & (v.memory == "-") & (v.hidden == 128) & (v.gamma == 0.999) & (v.lr == 3e-4)
    std3k = std & (v.episode_steps == 3000)
    base_env = (v.view == "11x9") & (v.world == "128x96") & ~v["log inventory"].astype(bool)
    o3t2 = (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.view == "11x9") & (v.world == "128x96") & (v.budget == "2B") \
        & (v.gamma == 0.999) & (v.memory == "-") & (v.episode_steps == 3000) & (v.go_explore == 0)
    h128 = v.hidden == 128
    inv = v["log inventory"].astype(bool)
    best_arm = inv & (v.potential == 3) & (v.potential_mode == "frontier") & (v.unimix > 0) & (v.hidden == 128) & (v.go_explore == 0)
    gen_arm = ~inv & (v.potential == 0) & (v.novelty > 0) & (v.unimix > 0) & (v.hidden == 128) & (v.go_explore == 0)
    cond = (v["ore %"] == 300) & (v.world == "128x96") & (v.view == "11x9") & (v.budget == "2B") & (v.memory == "-")

    # One dimension at a time (notebook cells 15-21). Each entry: dimension, question, reference, settings.
    dims = [
        ("supply", "Resource supply at 512M", "v8 default", {
            "v8 default": std3k & base_env & (v["ore %"] == 100) & (v["trunk %"] == 100) & (v.budget == "512M"),
            "ore 2x": std3k & base_env & (v["ore %"] == 200) & (v["trunk %"] == 100) & (v.budget == "512M"),
            "ore 3x": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 100) & (v.budget == "512M"),
            "trees 2x": std3k & base_env & (v["ore %"] == 100) & (v["trunk %"] == 200) & (v.budget == "512M"),
            "ore 3x + trees 2x": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "512M"),
        }),
        ("supply", "Resource supply at 2B", "v8 default", {
            "v8 default": std3k & base_env & (v["ore %"] == 100) & (v.budget == "2B"),
            "ore 3x + trees 2x": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "2B"),
        }),
        ("shaping", "Reward shaping and exploration aids (ore 3x + trees 2x, 2B)", "pot 3 mean (standard)", {
            "pot 3 mean (standard)": o3t2 & ~inv & std,
            "no shaping": o3t2 & ~inv & h128 & (v.potential == 0) & (v.novelty == 0) & (v.unimix == 0),
            "no shaping + novelty + unimix": o3t2 & ~inv & h128 & (v.potential == 0) & (v.novelty > 0) & (v.unimix > 0),
            "pot 3 mean + unimix": o3t2 & ~inv & h128 & (v.potential == 3) & (v.potential_mode == "mean") & (v.unimix > 0),
            "frontier + novelty": o3t2 & ~inv & h128 & (v.potential_mode == "frontier") & (v.unimix == 0),
            "log inv + pot 3 mean": o3t2 & inv & std,
            "log inv + frontier + novelty + unimix": o3t2 & inv & h128 & (v.potential == 3) & (v.potential_mode == "frontier") & (v.unimix > 0),
            "log inv + frontier coef 10": o3t2 & inv & h128 & (v.potential == 10),
            "log inv + frontier_surface": o3t2 & inv & h128 & (v.potential_mode == "frontier_surface"),
        }),
        ("discount", "Discount horizon, best shaped arm (2B)", "gamma 0.999",
         {f"gamma {g:g}": cond & best_arm & (v.gamma == g) for g in (0.999, 0.9995, 0.9998)}),
        ("discount", "Discount horizon, generic arm (2B)", "gamma 0.999",
         {f"gamma {g:g}": cond & gen_arm & (v.gamma == g) for g in (0.999, 0.9995, 0.9998)}),
        ("capacity", "Model capacity and memory (ore 3x + trees 2x, 2B)", "standard (hidden 128)", {
            "standard (hidden 128)": o3t2 & ~inv & std,
            "hidden 1024, lr 1e-4": o3t2 & ~inv & (v.potential == 3) & (v.potential_mode == "mean") & (v.hidden == 1024),
            "LSTM 256": (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "2B") & (v.memory == "lstm"),
            "generic arm, hidden 128": o3t2 & gen_arm,
            "generic arm, hidden 1024": o3t2 & ~inv & (v.potential == 0) & (v.hidden == 1024),
            "best shaped arm, hidden 128": o3t2 & best_arm,
            "best shaped arm, hidden 1024": o3t2 & inv & (v.potential_mode == "frontier") & (v.hidden == 1024),
        }),
        ("world", "Larger world", "128x96, standard, 2B", {
            "128x96, standard, 2B": std3k & base_env & (v["ore %"] == 100) & (v.budget == "2B"),
            "256x96, standard, 2B": std3k & (v.world == "256x96") & (v["ore %"] == 100),
            "256x96, standard, 6000 steps/ep, 2B": std & (v.world == "256x96") & (v["ore %"] == 100) & (v.episode_steps == 6000),
            "256x96, generic arm, 6000 steps/ep, 4B": (v.world == "256x96") & (v["ore %"] == 100) & (v.potential == 0) & (v.memory == "-") & (v.go_explore == 0),
            "256x96, frontier arm, 6000 steps/ep, 4B": (v.world == "256x96") & (v["ore %"] == 100) & (v.potential_mode == "frontier"),
            "256x96, generic + LSTM, 6000 steps/ep, 2B": (v.world == "256x96") & (v.memory == "lstm"),
            "256x96, generic + Go-Explore": (v.world == "256x96") & (v.go_explore > 0),
            "256x96 + ore 3x + trees 2x, 6000 steps/ep, 2B": (v.world == "256x96") & (v["ore %"] == 300),
        }),
        ("view", "Larger view (default supply)", "11x9, standard, 2B", {
            "11x9, standard, 2B": std3k & base_env & (v["ore %"] == 100) & (v.budget == "2B"),
            "21x15, standard, 2B": std3k & (v.view == "21x15") & (v["ore %"] == 100) & (v.budget == "2B"),
            "21x15, standard, 4B": std3k & (v.view == "21x15") & (v["ore %"] == 100) & (v.budget == "4B"),
            "21x15, hidden 512, 2B": (v.view == "21x15") & (v["ore %"] == 100) & (v.hidden == 512) & (v.potential == 3),
            "21x15, generic arm, 4B": (v.view == "21x15") & (v["ore %"] == 100) & (v.potential == 0) & (v.hidden == 128) & (v.go_explore == 0),
            "21x15, generic arm + hidden 512, 4B": (v.view == "21x15") & (v["ore %"] == 100) & (v.potential == 0) & (v.hidden == 512),
            "21x15, generic + Go-Explore, 4B": (v.view == "21x15") & (v.go_explore > 0),
        }),
        ("budget", "Training budget", "ore 3x + trees 2x, standard, 2B", {
            "ore 3x + trees 2x, standard, 512M": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "512M"),
            "ore 3x + trees 2x, standard, 2B": std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "2B"),
            "best shaped arm, 2B": cond & best_arm & (v.gamma == 0.999),
            "best shaped arm, 4B": (v["ore %"] == 300) & best_arm & (v.budget == "4B") & (v.gamma == 0.999),
        }),
        ("exploration", "Go-Explore restarts (20% of training episodes)", "generic arm, ore 3x + trees 2x", {
            "generic arm, ore 3x + trees 2x": o3t2 & gen_arm & (v.gamma == 0.999),
            "generic arm + Go-Explore": (v["ore %"] == 300) & (v.world == "128x96") & ~inv & (v.potential == 0) & (v.go_explore > 0),
            "best shaped arm": cond & best_arm & (v.gamma == 0.999),
            "best shaped arm + Go-Explore": (v["ore %"] == 300) & inv & (v.potential_mode == "frontier") & (v.go_explore > 0),
        }),
    ]
    ablations = []
    for dim, title, ref, groups in dims:
        settings = []
        for label, mask in groups.items():
            g = runs[mask]
            if g.empty:
                continue
            settings.append(dict(
                label=label, runs=list(g.id), seeds=[dict(seed=int(s), score=round(float(x), 4), finished=bool(f))
                                                     for s, x, f in zip(g.seed, g.score, g.finished)],
                mean=float(g.score.mean()), sd=float(g.score.std(ddof=0)),
                anvil=float(g["craft anvil"].mean()), breastplate=float(g["craft wood breastplate"].mean()),
                surface=float(g["return to surface"].mean()), iron_pick=float(g["craft iron pickaxe"].mean()),
                deaths=float(g.deaths.mean()), hours=float(g.hours.mean())))
        refmean = next((s["mean"] for s in settings if s["label"] == ref), None)
        for s in settings:
            s["delta"] = None if refmean is None else s["mean"] - refmean
        ablations.append(dict(dimension=dim, title=title, reference=ref, settings=settings))

    # Final configurations (notebook cell 25): same RNG seed and call order as the notebook.
    rng = np.random.default_rng(0)

    def iqm(x):
        x = np.sort(np.asarray(x, float)); n = len(x)
        k = int(np.floor(0.25 * n))
        return x[k:n - k].mean() if n - 2 * k > 0 else x.mean()

    def boot_ci(x, n=10000):
        x = np.asarray(x, float)
        s = [iqm(rng.choice(x, len(x))) for _ in range(n)]
        return [float(p) for p in np.percentile(s, [2.5, 97.5])]

    final_masks = {
        "v8_default": ("v8 default (= v7), standard", std3k & base_env & (v["ore %"] == 100) & (v.budget == "2B")),
        "o3t2_standard": ("ore 3x + trees 2x, standard", std3k & base_env & (v["ore %"] == 300) & (v["trunk %"] == 200) & (v.budget == "2B")),
        "generic_g9998": ("ore 3x + trees 2x, generic, gamma .9998", (v["ore %"] == 300) & (v.world == "128x96") & (v.view == "11x9") & (v.budget == "2B") & gen_arm & (v.gamma == 0.9998)),
        "shaped_g9998": ("ore 3x + trees 2x + log inv, best shaped, gamma .9998", (v["ore %"] == 300) & (v.world == "128x96") & (v.view == "11x9") & (v.budget == "2B") & best_arm & (v.gamma == 0.9998)),
    }
    finals = {}
    for key, (name, mask) in final_masks.items():
        g = runs[mask & runs.finished]
        lo, hi = boot_ci(g.score)
        clo, chi = boot_ci(g.crafter_score)
        t = g.test_score.dropna()
        tlo, thi = boot_ci(t) if len(t) else (None, None)
        hits = {a: sum(evals[r]["validation"]["hits"].get(a, 0) for r in g.id) for a in ACHIEVEMENTS}
        eps = sum(evals[r]["validation"]["episodes"] for r in g.id)
        test_hits = {a: sum(evals[r]["test"]["hits"].get(a, 0) for r in g.id if evals[r]["test"]) for a in ACHIEVEMENTS}
        test_eps = sum(evals[r]["test"]["episodes"] for r in g.id if evals[r]["test"])
        recs = [rec for r in g.id for rec in evals[r]["validation"]["records"]]
        finals[key] = dict(
            name=name, runs=list(g.id), seeds=[int(s) for s in g.seed], scores=[float(x) for x in g.score],
            mean=float(g.score.mean()), iqm=float(iqm(g.score)), ci=[lo, hi],
            crafter=float(g.crafter_score.mean()), crafter_ci=[clo, chi],
            test_scores=[float(x) for x in t], test_iqm=float(iqm(t)) if len(t) else None, test_ci=[tlo, thi],
            test_crafter=float(g.test_crafter_score.mean()),
            deaths=float(g.deaths.mean()), hours=float(g.hours.mean()), steps=int(g.steps.iloc[0]),
            validation=dict(episodes=eps, hits=hits), test=dict(episodes=test_eps, hits=test_hits),
            **episode_stats(recs))

    def p_improve(x, y):
        x, y = np.asarray(x)[:, None], np.asarray(y)[None, :]
        return float((x > y).mean() + 0.5 * (x == y).mean())

    keys = list(finals)
    pimp = {a: {b: p_improve(finals[a]["scores"], finals[b]["scores"]) for b in keys if b != a} for a in keys}

    # Best single run (6B shaped, seed 2001) with full per-achievement detail.
    best = runs.sort_values("score", ascending=False).iloc[0]
    best_detail = dict(id=best.id, score=float(best.score), steps=int(best.steps), hours=float(best.hours),
                       validation=dict(episodes=evals[best.id]["validation"]["episodes"],
                                       hits=evals[best.id]["validation"]["hits"]),
                       test=evals[best.id]["test"], **episode_stats(evals[best.id]["validation"]["records"]))

    cols = ["id", "study", "variant", "arm", "budget", "seed", "lib", "ore %", "trunk %", "view", "world",
            "log inventory", "episode_steps", "potential", "potential_mode", "novelty", "unimix", "go_explore",
            "memory", "hidden", "lr", "gamma", "params", "steps", "hours", "finished", "score", "best",
            "crafter_score", "deaths", "idle_steps", *HARD, "test_score", "test_crafter_score", "sps",
            "iron_bars_med", "iron_bars_max", "wood_med", "breastplate_legal_eps", "iron_pick_legal_eps",
            "anvils_crafted_per_ep", "anvil_peak_med", "anvil_peak_max"]
    cat = runs[[c for c in cols if c in runs]].replace({np.nan: None})
    rl = dict(
        _source="experiments/eg15/*/runs/*/{curve,protocol,summary,diag,test}.json via site/tools/export_data.py; "
                "logic from notebooks/v8_env_results_2026_10_31.ipynb",
        environment="Terraria-Lite v8 preview (frozen v7 core + environment knobs), 32 achievements, 3,000 steps",
        validation_worlds=[23000001, 23000128], test_worlds=[25000001, 25000128],
        achievements=ACHIEVEMENTS, hard=HARD, studies=STUDIES,
        runs=json.loads(cat.to_json(orient="records")), curves=curves,
        final=finals, p_improve=pimp, ablations=ablations, best_run=best_detail)
    write(OUT / "rl.json", rl)
    export_llm()


def export_llm():
    E = ROOT / "experiments"
    attempts = []
    tapes = OUT / "tapes"
    if tapes.exists():
        shutil.rmtree(tapes)
    tapes.mkdir(parents=True)

    def add(result_path: Path, study, harness, version, model, actual_cost, extra=None):
        r = json.loads(result_path.read_text())
        tape = result_path.parent / "actions.tape"
        name = f"{study}-{r['seed']}-{harness}"
        if tape.exists():
            shutil.copyfile(tape, tapes / f"{name}.tape")
        attempts.append(dict(
            id=name, study=study, model=model, harness=harness, harness_version=version, world=r["seed"],
            score=r["score"], steps=r["steps"], status=r["status"], died=r["died"], calls=r["calls"],
            tokens=r["tokens"], illegal_attempts=r["illegal_attempts"], elapsed_seconds=r["elapsed_seconds"],
            accounted_cost_usd=r["accounted_cost_usd"], actual_cost_usd=actual_cost,
            achievements=r["achievements"], first_unlock=r["first_achievement_steps"], native=r["native_info"],
            tape=f"data/tapes/{name}.tape" if tape.exists() else None, source=str(result_path.relative_to(ROOT)),
            **(extra or {})))

    # Sol smoke: actual cost from docs/reports/LLM_EVALUATION.md ($0.2821147); 16 calls x 16 actions cap.
    add(E / "llm-eval-20261017.Ql1JZD/run/world-31000009-rep-0/result.json", "sol-smoke", "full16", "v0.1",
        "openai/gpt-6.1-sol (high)", 0.2821147)
    # Luna batch: per-world actual costs from docs/reports/LLM_LUNA_2026_10_17.md.
    for seed, cost in ((31000010, 0.408418315), (31000011, 0.437994920), (31000012, 0.049332795)):
        add(E / f"llm-luna-20261017.amwt1tz8/run/world-{seed}-rep-0/result.json", "luna-batch", "full16", "v0.1",
            "openai/gpt-6-luna (high)", cost)
    res = json.loads((E / "luna-harness-20261017.nhitzl0s/results.json").read_text())
    for rec in res["records"]:
        p = E / "luna-harness-20261017.nhitzl0s/runs" / rec["name"] / f"world-{rec['seed']}-rep-0/result.json"
        add(p, "luna-harness", rec["arm"], "v0.2", "openai/gpt-6-luna (high)", rec["provider_reported_cost_usd"],
            dict(score_at_action_budget=rec["score_at_action_budget"], prompt_tokens=rec["prompt_tokens"],
                 completion_tokens=rec["completion_tokens"], mean_call_seconds=rec["mean_call_seconds"],
                 interrupted_batches=rec.get("interrupted_batches", 0)))
    write(OUT / "llm.json", dict(
        _source="experiments/{llm-eval-20261017.Ql1JZD,llm-luna-20261017.amwt1tz8,luna-harness-20261017.nhitzl0s}; "
                "costs: docs/reports/LLM_EVALUATION.md, LLM_LUNA_2026_10_17.md, luna-harness results.json",
        environment="Terraria-Lite v7 (frozen), 32 achievements, 3,000 primitive actions",
        attempts=attempts))


def write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False, default=_default))
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KiB)")


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


if __name__ == "__main__":
    main()
