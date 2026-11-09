"""Results table + compact summary rows for a campaign, from each run's manifest, result, evidence and extended score.

    python tools/campaign_table.py runs/<campaign> [--json summary.json]

Needs tools/run_evidence.py and tools/extended_score.py to have run on each run. Smoke and failed runs
(names starting with "smoke" or containing "failed"/"aborted") are skipped. Times are game mm:ss.
"""
import argparse
import json
from decimal import Decimal
from pathlib import Path

PUBLISHED = ("wood_1", "wood_25", "wood_100", "workbench_1", "torch_10", "furnace_1", "early_bar_5")
EXTENDED = ("gel_1", "torch_crafted", "workbench_placed", "layer_underground", "layer_cavern", "ore_copper_tin",
            "ore_iron_lead", "furnace_placed", "bar_smelted", "anvil_placed", "metal_gear_crafted")


def mmss(s):
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def short(model):
    return {"claude-haiku-5-5": "Haiku", "claude-sonnet-5-5": "Sonnet", "claude-opus-5-5": "Opus", "gpt-5.6-luna": "Luna",
            "gpt-5.6-terra": "Terra", "gpt-5.6-sol": "Sol", "typesafe/jev-1.14": "Jev"}.get(model, model)


DEFAULT_SETTINGS = {"window": [1024, 1024], "zoom": 1.0, "ui_scale": 0.9, "lighting": "color", "smart_cursor": "off",
                    "minimap": "frame"}


def settings_label(man):
    s = man.get("display_settings") or {}
    return ", ".join(f"{k} {'x'.join(map(str, s[k])) if isinstance(s[k], list) else s[k]}" for k, v in DEFAULT_SETTINGS.items()
                     if k in s and s[k] != v)


def setup(man):
    if (man.get("profile_id") or (man.get("profile") or {}).get("profile_id")) in ("default-v1", "default-v2"):
        if str(man.get("protocol", "")).startswith("combo-"):
            c = man["config"]
            head = f'{short(c["planner_model"])} ({c["planner_reasoning"]}) planner + {short(c["executor_model"])} executor'
            clock = c["clock"]
        else:
            head, clock = short(man["model"]["id"]) + f' ({man.get("reasoning_effort")})', man["clock"]
            choice = (man.get("no_action_policy") or {}).get("tool_choice")
            if "no_action_policy" in man:
                head += ", forced" if choice not in (None, "auto") else ", unforced"
        return ", ".join(x for x in (head, clock, settings_label(man)) if x)
    if str(man.get("protocol", "")).startswith("combo-"):
        c = man["config"]
        bits = [f'{short(c["planner_model"])} planner + {short(c["executor_model"])} executor', "realtime"]
        pve = c.get("pve")
        damage = c.get("hostile_contact_damage", "on")
    else:
        bits = [short(man["model"]["id"]) + f' ({man.get("reasoning_effort")})', man.get("clock", "realtime")]
        pve, damage = man.get("pve_enabled"), man.get("hostile_contact_damage", "on")
        if not man.get("interface_card"):
            bits.append("no card")
        elif man["interface_card"] != "v1":
            bits.append(f'card {man["interface_card"]}')
        if man.get("information_policy", {}).get("checkpoint_log", "published") != "published":
            bits.append("ext. log")
        if not man.get("information_policy", {}).get("screenshot_after_act"):
            bits.append("no shot-after-act")
        if man.get("observation_encoding", {}).get("format") == "png":
            bits.append("PNG")
    bits.append("PvE off" if not pve else "PvE gentle" if damage == "off" else "PvE normal")
    return ", ".join(bits)


def row(run):
    man = json.loads((run / "manifest.json").read_text())
    res = json.loads((run / "result.json").read_text())
    ev = json.loads((run / "evidence/summary.json").read_text())
    ext = json.loads((run / "extended-score.json").read_text())
    combo = "roles" in res
    usd = (sum(Decimal(r["accounting"]["reported_usd"]) for r in res["roles"].values()) if combo
           else Decimal(res["accounting"]["reported_usd"]))
    calls = sum(r["calls"] for r in res["roles"].values()) if combo else res["calls"]
    clock = json.loads((run / "evidence/clock.json").read_text()) if (run / "evidence/clock.json").exists() else {}
    return {"run": run.name, "setup": setup(man), "campaign_profile": man.get("campaign_profile") or man.get("config", {}).get("campaign_profile"),
            "display_settings": man.get("display_settings"), "clock": man.get("clock") or man.get("config", {}).get("clock"),
            "world_seed": ext["world"]["seed"], "game_s": ext["game_seconds"], "wall_s": round(res["active_wall_seconds"]),
            "wall_total_s": round(clock["wall_span_s"]) if clock else None,
            "stop": res["stop_reason"], "published_score": ext["published_score"],
            "published_game_s": ext["published_milestones_game_s"], "extended_count": ext["extended_count"],
            "extended_game_s": ext["extended_game_s"], "crafted": ext["crafted"], "placed_tile_types": ext["placed_tile_types"],
            "deaths": ext["deaths"], "max_depth_tiles": ext["max_depth_tiles"], "continuations": res.get("continuations"),
            "no_action_turns": res.get("no_action_turns"), "censored": res.get("censored"),
            "calls": calls, "calls_by_role": {k: r["calls"] for k, r in res["roles"].items()} if combo else None,
            "inputs": res.get("input_commands"), "latency_median_s": ev["latency_median_s"],
            "screenshot_age_median_s": clock.get("screenshot_age_wall_median_s", ev["screenshot_age_median_s"]),
            "screenshot_age_game_median_s": clock.get("screenshot_age_game_median_s"),
            "hz_median": (clock.get("hz_unfrozen_intervals") or {}).get("median"),
            "updates_per_running_s": clock.get("updates_per_running_second_overall"),
            "usd_reported": f"{usd:.4f}",
            "usd_by_role": {k: r["accounting"]["reported_usd"] for k, r in res["roles"].items()} if combo else None,
            "final_inventory": ev["final_inventory"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("campaign", type=Path)
    p.add_argument("--json", type=Path)
    p.add_argument("--prefix", nargs="*", default=None, help="only runs whose name starts with one of these")
    args = p.parse_args()
    runs = sorted((r for r in args.campaign.iterdir() if (r / "extended-score.json").exists() and (r / "evidence/summary.json").exists()
                   and not r.name.startswith(("smoke", "dryrun")) and "failed" not in r.name and "aborted" not in r.name
                   and (args.prefix is None or r.name.startswith(tuple(args.prefix)))),
                  key=lambda r: json.loads((r / "manifest.json").read_text())["started_unix"])
    rows = [row(r) for r in runs]
    print("| Run | Setup | World | Game min | Pub. score | " + " | ".join(PUBLISHED) + " | Ext. count | " +
          " | ".join(EXTENDED) + " | Deaths | Depth | Contin. | No-action | Calls | Lat. (s) | Shot age (s) | Shot age game (s) | Hz | "
          "Wall min | USD |")
    print("|" + "---|" * (len(PUBLISHED) + len(EXTENDED) + 18))
    for r in rows:
        lat = r["latency_median_s"]
        lat = "/".join(f"{v:.1f}" for v in lat.values() if v) if isinstance(lat, dict) else f"{lat:.1f}"
        print(f'| {r["run"]} | {r["setup"]} | {r["world_seed"][-3:]} | {r["game_s"] / 60:.1f} | {r["published_score"]} | ' +
              " | ".join(mmss(r["published_game_s"][k]) if k in r["published_game_s"] else "–" for k in PUBLISHED) +
              f' | {r["extended_count"]} | ' +
              " | ".join(mmss(r["extended_game_s"][k]) if k in r["extended_game_s"] else "–" for k in EXTENDED) +
              f' | {r["deaths"]} | {r["max_depth_tiles"]} | {r["continuations"] if r["continuations"] is not None else "–"} | '
              f'{r["no_action_turns"] if r["no_action_turns"] is not None else "–"} | '
              f'{r["calls"]} | {lat} | {r["screenshot_age_median_s"]} | {r["screenshot_age_game_median_s"]} | {r["hz_median"]} | '
              f'{round(r["wall_total_s"] / 60, 1) if r["wall_total_s"] else "–"} | {r["usd_reported"]} |')
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1) + "\n")


if __name__ == "__main__":
    main()
