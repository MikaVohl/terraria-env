"""Build an evidence pack for one run (single-model reference_live or combo): timeline, summary, contact sheet.

    python tools/run_evidence.py runs/pilot-30min/<run>

Writes <run>/evidence/{timeline.md, summary.json, contact-sheet.png}. Read-only with respect to the run.
"""
import json
import os
import statistics as st
import subprocess
import sys
from pathlib import Path

# Item ids seen in early game (Terraria 1.4.4). Unknown ids are shown as "item N".
ITEMS = {2: "Dirt Block", 3: "Stone Block", 8: "Torch", 9: "Wood", 11: "Iron Ore", 12: "Copper Ore", 13: "Gold Ore",
         14: "Silver Ore", 19: "Gold Bar", 20: "Copper Bar", 21: "Silver Bar", 22: "Iron Bar", 23: "Gel", 27: "Acorn",
         28: "Lesser Healing Potion", 29: "Life Crystal", 33: "Furnace", 35: "Iron Anvil", 36: "Work Bench",
         40: "Wooden Arrow", 71: "Copper Coin", 72: "Silver Coin", 73: "Gold Coin", 75: "Fallen Star", 133: "Clay Block",
         150: "Cobweb", 166: "Bomb", 176: "Mud Block", 282: "Glowstick", 424: "Silt Block", 699: "Tin Ore", 700: "Lead Ore",
         701: "Tungsten Ore", 702: "Platinum Ore", 703: "Tin Bar", 704: "Lead Bar", 705: "Tungsten Bar", 706: "Platinum Bar",
         727: "Wood Helmet", 728: "Wood Breastplate", 729: "Wood Greaves", 965: "Rope", 3506: "Copper Axe",
         3507: "Copper Shortsword", 3509: "Copper Pickaxe", 1725: "Pumpkin"}
TILE, SURFACE_Y = 16, None


def name(i):
    return ITEMS.get(i, f"item {i}")


def inv(beat):
    out = {}
    for it in beat.get("inventory") or []:
        out[name(it["type"])] = out.get(name(it["type"]), 0) + it["stack"]
    return out


def main(run):
    run = Path(run)
    res = json.loads((run / "result.json").read_text())
    man = json.loads((run / "manifest.json").read_text())
    combo = str(res.get("protocol", "")).startswith("combo-")
    t0 = res["evaluation_end_unix"] - res["active_wall_seconds"] - (res.get("provider_outage_seconds") or 0) - (res.get("think_frozen_seconds") or 0)
    tel = [json.loads(l) for f in sorted((run / "telemetry").glob("*.jsonl")) for l in open(f)]
    beats = [e for e in tel if e.get("event") == "heartbeat"]
    y0 = beats[0]["position"][1] if beats else 0
    x0 = beats[0]["position"][0] if beats else 0
    ev = []
    if combo:
        for d in (json.loads(l) for l in open(run / "decisions.jsonl")):
            t = d["unix"] - t0
            if d["role"] == "planner" and "objective" in d:
                ev.append((t, "PLAN", f'{d["objective"]} (replan {d["replan_seconds"]}s, ui {d["ui_actions"]}, {d["latency"]:.1f}s)'))
            elif d["role"] == "planner_ui":
                ev.append((t, "PLANNER-UI", f'{len(d["actions"])} clicks'))
            elif d["role"] == "executor" and "summary" in d:
                ev.append((t, "EXEC", f'{d["summary"]} [{d.get("status")}] {d["latency"]:.2f}s'))
            elif "error" in d or "fatal" in d:
                ev.append((t, "ERROR", f'{d["role"]}: {d.get("error") or d.get("fatal")}'))
    else:
        for f in sorted(run.glob("response-*.json")):
            r = json.loads(f.read_text())
            m = r["choices"][0]["message"]
            calls = []
            for c in m.get("tool_calls") or []:
                a = c["function"]["arguments"]
                try:
                    acts = json.loads(a).get("actions")
                    if acts:
                        a = "; ".join(f'{"+".join(x.get("keys", []))}{(" " + x["mouse"]) if x.get("mouse") else ""}'
                                      f'{"@%d,%d" % (x["x"], x["y"]) if "x" in x else ""} {x.get("ms", 100)}ms' for x in acts)
                except (ValueError, AttributeError):
                    pass
                calls.append(f'{c["function"]["name"]}({a})' if a not in ("{}", "") else c["function"]["name"])
            text = " ".join((m.get("content") or "").split())
            think = " ".join((m.get("reasoning") or "").split())
            ev.append((os.path.getmtime(f) - t0, f"CALL {f.stem[-3:]}", " | ".join(x for x in (
                f"SAY: {text[:600]}" if text else "", f"THINK: {think[:500]}" if think else "",
                f"DO: {' || '.join(calls)}" if calls else "") if x)))
        if (run / "continuations.jsonl").exists():
            for l in open(run / "continuations.jsonl"):
                ev.append((json.loads(l)["unix_seconds"] - t0, "CONTINUE", ""))
    last = -999
    deaths, was_dead, max_depth = 0, False, 0
    for e in tel:
        if e.get("event") == "checkpoint":
            ev.append((e["unix_seconds"] - t0 if "unix_seconds" in e else e["elapsed_seconds"], "MILESTONE", f'{e["milestone"]} ({e["category"]})'))
        elif e.get("event") == "heartbeat":
            dead = bool(e.get("dead"))
            if dead and not was_dead:
                deaths += 1
                ev.append((e["unix_seconds"] - t0, "DEATH", f'at depth {(e["position"][1] - y0) / TILE:.0f} tiles'))
            was_dead = dead
            depth = (e["position"][1] - y0) / TILE
            max_depth = max(max_depth, depth)
            if e["unix_seconds"] - last >= 60:
                last = e["unix_seconds"]
                ev.append((e["unix_seconds"] - t0, "STATE", f'dx {(e["position"][0] - x0) / TILE:+.0f} depth {depth:.0f} tiles, life {e.get("life")}, '
                                                            f'inv {inv(e)}'))
    ev.sort(key=lambda x: x[0])
    out = run / "evidence"
    out.mkdir(exist_ok=True)
    head = (f"# {run.name}\nconfig: {json.dumps(man.get('config') or {k: man.get(k) for k in ('clock', 'pve_enabled', 'interface_card')})}\n"
            f"model: {res.get('model') or man['config'].get('planner_model')} | stop: {res['stop_reason']} | played {res['active_wall_seconds']:.0f}s\n\n")
    (out / "timeline.md").write_text(head + "\n".join(f"[{t:7.1f}s] {k}: {s}" for t, k, s in ev) + "\n")
    # summary
    if combo:
        usd = {k: r["accounting"]["reported_usd"] for k, r in res["roles"].items()}
        lat = {k: r["latency_median"] for k, r in res["roles"].items()}
    else:
        usd, lat = res["accounting"]["reported_usd"], st.median(json.loads(f.read_text())["latency_seconds"] for f in run.glob("response-*.json"))
    summary = {"run": run.name, "stop": res["stop_reason"], "played_s": round(res["active_wall_seconds"]),
               "think_frozen_s": round(res.get("think_frozen_seconds") or 0), "score": res["score"]["agency_score"],
               "milestones_s": {k: round(v["elapsed_seconds"]) for k, v in res["score"].get("first_unlocks", {}).items()},
               "diagnostics": res["score"].get("diagnostics_not_scored"), "deaths": deaths, "max_depth_tiles": round(max_depth),
               "final_inventory": inv(beats[-1]) if beats else {}, "frames": res["frames"], "inputs": res.get("input_commands"),
               "continuations": res.get("continuations"), "latency_median_s": lat, "usd": usd,
               "screenshot_age_median_s": None}
    # screenshot age at the first input of each action batch
    try:
        caps = sorted(os.path.getmtime(f) for f in (run / "frames").glob("*.png"))
        rec = [json.loads(l) for l in open(run / "inputs.jsonl")]
        firsts, prev = [], 0
        for r in rec:
            if r["started_unix"] - prev > 0.5:
                firsts.append(r["started_unix"])
            prev = r["ended_unix"]
        ages = [s - max(c for c in caps if c <= s) for s in firsts if any(c <= s for c in caps)]
        summary["screenshot_age_median_s"] = round(st.median(ages), 2) if ages else None
    except (OSError, ValueError):
        pass
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    # contact sheet: 12 evenly spaced frames, 4x3
    frames = sorted((run / "frames").glob("*.png"))
    if frames:
        step = max(1, len(frames) // 12)
        pick = frames[::step][:12]
        listfile = out / "frames.txt"
        listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in pick))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                        "-vf", "scale=320:320,tile=4x3", "-frames:v", "1", str(out / "contact-sheet.png")], check=False)
        listfile.unlink()
    print(json.dumps(summary))


if __name__ == "__main__":
    main(sys.argv[1])
