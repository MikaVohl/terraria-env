"""Export the official-Terraria (TerrariaBench) results the site shows into site/data/terrariabench.json.

Sources:
  landscape-2026-11-08 (profile default-v2, interim while it runs): the compact summary
      TerrariaBench/experiments/results/landscape-2026-11-08/summary.json if it exists, otherwise
      tools/campaign_table.py run on Omarchy over ssh; per-run death times (observer journal) and the
      game time of quoted model calls (clock.jsonl act steps) also come from Omarchy;
      per-run notes from TerrariaBench/experiments/landscape-2026-11-08.md.
  default-game-2026-11-08 (default-v1) and llm-campaign-2026-11-08 (camp-v2): local compact summaries.
  reference-gw: local compact summary. terrariabench.com published runs: as quoted in
      TerrariaBench/experiments/reference-gw.md.
  Harness card: TerrariaBench/prompts/default_v2.txt and Appendix B (tool schema) of
      TerrariaBench/experiments/default-game-2026-11-08.md (default-v2 uses the byte-identical schema).

Run from the repository root:

  python3 site/tools/export_terrariabench.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TB = ROOT / "TerrariaBench"
EXP = TB / "experiments"
OUT = ROOT / "site" / "data" / "terrariabench.json"
HOST = "mika@omarchy"
CAMPAIGN = "landscape-2026-11-08"

# Runs that ran but are not scored, with the reason (landscape report, per-run insights).
NOT_SCORED = {
    "b06-luna-pa-w403": "provider failure: the Responses endpoint timed out 4 times on one request at 0:21; re-run as b06r",
    "b08-terra-pa-w403": "harness gap: Save & Exit at 1:41 ended the observer journal while the harness kept calling the model; re-run as b08r",
}
# Pilot runs: same profile, run first to fix the Haiku request shape.
PILOTS = {"a1-haiku-think-pa-w401", "a2-haiku-forced-pa-w401", "a3-luna-pa-w401", "a4-terra-pa-w401"}

# Model calls quoted on the site: (run, act step). The text is copied from the run's evidence/timeline.md.
QUOTES = [
    ("b12-haiku-pa-w402", 15, "The workbench is placed. Next I'll switch to the pickaxe and start digging down to look for ore."),
    ("b15-haiku-rt-w403", 11, "The workbench is placed next to me and the Benched achievement unlocked. Next I'll chop the nearby trees for more wood to build with."),
    ("b14-haiku-pa-w403", 9, "The workbench is placed and I have a copper pickaxe. Next I'll mine the stone rock beside the workbench."),
    ("b11-haiku-rt-w401", 45, "I'm at 4:51 of 20 minutes. The character is still underground in the dark, with five hearts, a workbench placed in the tunnel, and about 22 wood and 87 stone."),
]

REMOTE = r"""
import json, sys
from pathlib import Path
camp = Path(sys.argv[1])
want = json.loads(sys.argv[2])
out = {}
for d in sorted(p for p in camp.iterdir() if p.is_dir()):
    deaths = []
    for f in sorted((d / "telemetry").glob("*.jsonl")) if (d / "telemetry").exists() else []:
        for line in f.open():
            e = json.loads(line)
            if e.get("event") == "death":
                deaths.append(round(e["game_updates"] / 60, 1))
    steps = {}
    if (d / "clock.jsonl").exists():
        for line in (d / "clock.jsonl").open():
            e = json.loads(line)
            if e.get("event") == "act" and [d.name, e["step"]] in want:
                steps[e["step"]] = round(e["updates_before"] / 60, 1)
    out[d.name] = {"deaths_game_s": sorted(deaths), "steps_game_s": steps}
print(json.dumps(out))
"""


def ssh(cmd: str) -> str:
    return subprocess.run(["ssh", HOST, cmd], check=True, capture_output=True, text=True).stdout


def clean(s: str) -> str:
    """Report prose to site prose: no markdown emphasis or code ticks, no em dashes."""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = s.replace("`", "")
    s = re.sub(r"\s+—\s+", "; ", s).replace("—", "-").replace("–", "-")
    return s.strip()


def landscape_rows() -> list[dict]:
    local = EXP / "results" / CAMPAIGN / "summary.json"
    if local.exists():
        return json.loads(local.read_text())
    campaign = TB / "runs" / CAMPAIGN
    output = Path(f"/tmp/site-{CAMPAIGN}.json")
    if campaign.is_dir():
        subprocess.run([sys.executable, str(TB / "tools/campaign_table.py"), str(campaign),
                        "--json", str(output)], check=True, capture_output=True, text=True)
        return json.loads(output.read_text())
    ssh(f"cd ~/Projects/terraria-lite/TerrariaBench && .venv/bin/python tools/campaign_table.py runs/{CAMPAIGN} --json {output} > /dev/null")
    return json.loads(ssh(f"cat {output}"))


def run_notes(md: Path) -> dict[str, str]:
    notes = {}
    for line in md.read_text().splitlines():
        m = re.match(r"- \*\*([a-z0-9-]+)\*\* \((.*?)\):\s*(.*)", line)
        if m:
            notes[m.group(1)] = clean(m.group(3))
    return notes


def profile_table(md: Path) -> list[list[str]]:
    rows, on = [], False
    for line in md.read_text().splitlines():
        if line.startswith("## Definition"):
            on = True
            continue
        if on and line.startswith("## "):
            break
        m = re.match(r"\| (.+?) \| (.+) \|$", line)
        if on and m and not set(m.group(1)) <= {"-", " "} and m.group(1).strip():
            rows.append([clean(m.group(1)), clean(m.group(2))])
    return rows


def tool_schema(md: Path) -> str:
    t = md.read_text()
    m = re.search(r"## Appendix B: tool schema\s+```json\n(.*?)```", t, re.S)
    return json.dumps(json.loads(m.group(1)), indent=1)


def short_model(setup: str) -> str:
    return setup.split(",")[0].strip()


def slim(r: dict, notes: dict, extra: dict) -> dict:
    keep = ("run", "setup", "clock", "world_seed", "game_s", "wall_total_s", "stop", "censored", "published_score", "published_game_s",
            "extended_count", "extended_game_s", "crafted", "deaths", "max_depth_tiles", "continuations", "no_action_turns", "calls",
            "calls_by_role", "latency_median_s", "screenshot_age_median_s", "screenshot_age_game_median_s", "hz_median", "usd_reported",
            "usd_by_role")
    o = {k: r.get(k) for k in keep if k in r}
    o["agent"] = "Opus + Jev" if "planner" in r.get("setup", "") else short_model(r["setup"]).split(" (")[0]
    o["world"] = int(str(r["world_seed"])[-3:])
    o["usd"] = float(r["usd_reported"]) if r.get("usd_reported") is not None else None
    if r["run"] in notes:
        o["note"] = notes[r["run"]]
    x = extra.get(r["run"], {})
    o["deaths_game_s"] = x.get("deaths_game_s", [])
    if r["run"] in NOT_SCORED:
        o["not_scored"] = NOT_SCORED[r["run"]]
    if r["run"] in PILOTS:
        o["pilot"] = True
    if r["run"].endswith("-40m"):
        o["long"] = True
    return o


def catalogs() -> dict:
    src = (TB / "tools" / "extended_score.py").read_text()
    ext = [{"id": a, "name": b, "kind": c} for a, b, c in re.findall(r'\("([a-z0-9_]+)", "([^"]+)", "([a-z]+)"\)', src)]
    lv = (TB / "terrariabench" / "reference_scoring.py").read_text()
    body = re.search(r"REFERENCE_LEVELS = \{(.*?)\}", lv, re.S).group(1)
    pub = [{"id": a, "level": int(b)} for a, b in re.findall(r'"([a-z0-9_]+)": (\d)', body)]
    return {"published": pub, "extended": ext}


def main():
    rows = landscape_rows()
    want = [[r, s] for r, s, _ in QUOTES]
    campaign = TB / "runs" / CAMPAIGN
    if campaign.is_dir():
        extra = json.loads(subprocess.run([sys.executable, "-c", REMOTE, str(campaign), json.dumps(want)],
                                          check=True, capture_output=True, text=True).stdout)
    else:
        extra = json.loads(ssh(f"python3 - ~/Projects/terraria-lite/TerrariaBench/runs/{CAMPAIGN} '{json.dumps(want)}' <<'EOF'\n{REMOTE}\nEOF"))
    notes = run_notes(EXP / f"{CAMPAIGN}.md")
    runs = [slim(r, notes, extra) for r in rows]

    v1 = json.loads((EXP / "results" / "default-game-2026-11-08" / "summary-main.json").read_text())
    v1notes = run_notes(EXP / "default-game-2026-11-08.md")
    v1runs = [slim(r, v1notes, {}) for r in v1]
    camp = json.loads((EXP / "results" / "llm-campaign-2026-11-08" / "summary.json").read_text())
    ref = json.loads((EXP / "results" / "reference-gw" / "summary.json").read_text())

    quotes = []
    for run, step, text in QUOTES:
        g = extra.get(run, {}).get("steps_game_s", {}).get(str(step))
        quotes.append({"run": run, "step": step, "game_s": g, "text": text})

    out = {
        "_note": "Generated by site/tools/export_terrariabench.py from TerrariaBench compact records and Omarchy run directories. "
                 "The landscape campaign was still running at export time: its section is interim.",
        "exported_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "interim": True,
        "campaign": CAMPAIGN,
        "report": f"TerrariaBench/experiments/{CAMPAIGN}.md",
        "profile": profile_table(EXP / f"{CAMPAIGN}.md"),
        "catalog": catalogs(),
        "runs": runs,
        "quotes": quotes,
        "harness": {
            "prompt": (TB / "prompts" / "default_v2.txt").read_text().strip(),
            "prompt_note": "{minutes} = 20 (40 for the long runs); {width}x{height} = 1024x1024. First user turn: 'Current game screenshot:' plus the opening screenshot.",
            "tool_schema": tool_schema(EXP / "default-game-2026-11-08.md"),
            "tool_result": '{"dispatched_commands": n, "game_time_played": "m:ss", "image_follows": true} followed by a fresh 1024x1024 JPEG (q85) screenshot',
            "no_action": "A reply without a valid act call is executed as 'wait 1000 ms' (the game advances 1 s in both clock modes) and the next user turn is a fresh screenshot introduced by 'No action was taken.'",
            "source": "TerrariaBench/prompts/default_v2.txt; tool schema: TerrariaBench/experiments/default-game-2026-11-08.md, Appendix B (default-v2 schema is byte-identical)",
        },
        "earlier": {
            "default_v1": {"report": "TerrariaBench/experiments/default-game-2026-11-08.md", "runs": v1runs},
            "camp_v2": {"report": "TerrariaBench/experiments/llm-campaign-2026-11-08.md",
                        "runs": [{k: r.get(k) for k in ("run", "setup", "game_s", "published_score", "extended_count", "deaths", "usd_reported")} for r in camp]},
            "reference_gw": {"report": "TerrariaBench/experiments/reference-gw.md",
                             "runs": [{k: r.get(k) for k in ("run", "model", "reasoning", "planned_s", "played_s", "score", "usd")} for r in ref]},
            "published": {
                "source": "https://terrariabench.com/runs/ (as summarised in TerrariaBench/experiments/reference-gw.md)",
                "text": "Seven published runs with 8-hour budgets (about 6.1 h of play), PvE off. Best: Gemini 3 Flash 4 (wood_100 at 2,819 s); Gemini 3.1 Flash Lite and Pro 3; the other four 0.",
                "runs": 7, "best": 4, "best_agent": "Gemini 3 Flash", "hours": 8,
            },
        },
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}: {len(runs)} landscape runs, {len(v1runs)} default-v1 runs")


if __name__ == "__main__":
    main()
