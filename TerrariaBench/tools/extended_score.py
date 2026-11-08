"""Extended milestone catalog for one run, alongside the published-subset checkpoint score.

    python tools/extended_score.py <run> [<run> ...]      # prints one JSON line per run, writes <run>/extended-score.json

Facts come from the observer journal only (heartbeats once per game second: position, inventory, life;
observer >= 0.7 also journals `crafted` and `placed` events) and the run's own world header (surface and
cavern layer lines). Times are game seconds (game_updates / 60), comparable across real-time and frozen runs.
Possession facts can come from loot; `*_crafted` / `*_placed` facts need observer 0.7 and are reported as
unavailable (null) for older runs. Unweighted: `extended_count` is the number of catalog facts reached.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.reference_scoring import reference_score  # noqa: E402
from terrariabench.worldfile import read_header  # noqa: E402

BARS = {20, 703, 22, 704, 21, 705, 19, 706}
METALS = ("Copper", "Tin", "Iron", "Lead", "Silver", "Tungsten", "Gold", "Platinum")
ARMOR_WORDS = ("Helmet", "Breastplate", "Greaves", "Chainmail", "Mail", "Leggings", "Hat", "Shirt", "Pants")
# (id, description, kind). kind: possession (heartbeat inventory), layer, crafted, placed.
CATALOG = [
    ("gel_1", "holds gel (slime drop)", "possession"),
    ("torch_crafted", "crafted torches", "crafted"),
    ("workbench_placed", "placed a work bench", "placed"),
    ("wood_armor_crafted", "crafted a wooden armour piece", "crafted"),
    ("layer_underground", "entered the underground layer (below the world surface line)", "layer"),
    ("layer_cavern", "entered the cavern layer", "layer"),
    ("ore_copper_tin", "holds copper or tin ore", "possession"),
    ("ore_iron_lead", "holds iron or lead ore", "possession"),
    ("ore_silver_gold_tier", "holds silver/tungsten/gold/platinum ore", "possession"),
    ("furnace_crafted", "crafted a furnace", "crafted"),
    ("furnace_placed", "placed a furnace", "placed"),
    ("bar_smelted", "smelted a metal bar", "crafted"),
    ("bar_5", "holds 5+ metal bars", "possession"),
    ("anvil_held", "holds an iron or lead anvil", "possession"),
    ("anvil_placed", "placed an anvil", "placed"),
    ("metal_gear_crafted", "crafted a metal tool, weapon or armour piece", "crafted"),
    ("life_crystal", "holds a life crystal", "possession"),
    ("eoc_summon_or_lens", "holds a lens or Suspicious Looking Eye (Eye of Cthulhu prep)", "possession"),
    ("boss_eye_of_cthulhu", "defeated the Eye of Cthulhu (published flag)", "published"),
]


def count(beat, *types):
    return sum(i["stack"] for i in beat.get("inventory") or [] if i["type"] in types)


def possession(fact, beat):
    return {"gel_1": count(beat, 23) >= 1, "ore_copper_tin": count(beat, 12, 699) >= 1,
            "ore_iron_lead": count(beat, 11, 700) >= 1, "ore_silver_gold_tier": count(beat, 14, 701, 13, 702) >= 1,
            "bar_5": count(beat, *BARS) >= 5, "anvil_held": count(beat, 35, 716) >= 1,
            "life_crystal": count(beat, 29) >= 1, "eoc_summon_or_lens": count(beat, 38, 43) >= 1}[fact]


def crafted(fact, event):
    item, name = event.get("item_type"), event.get("name") or ""
    return {"torch_crafted": item == 8,
            "wood_armor_crafted": item in (727, 728, 729),
            "furnace_crafted": item == 33, "bar_smelted": item in BARS,
            "metal_gear_crafted": name.startswith(METALS) and not name.endswith(("Bar", "Ore", "Brick", "Chandelier",
                                                                                  "Candle", "Candelabra", "Watch", "Coin"))}[fact]


def placed(fact, event):
    return event.get("tile_type") == {"workbench_placed": 18, "furnace_placed": 17, "anvil_placed": 16}[fact]


def score(run, write=True):
    run = Path(run)
    telemetry = [json.loads(line) for f in sorted((run / "telemetry").glob("*.jsonl")) for line in open(f)]
    start = next((e for e in telemetry if e.get("event") == "start"), {})
    version = float(start.get("observer_version", "0"))
    header = read_header(next((run / "tml/Worlds").glob("*.wld")))
    surface, rock = header["surface_tile"], header["rock_layer_tile"]
    beats = [e for e in telemetry if e.get("event") == "heartbeat"]
    first, deaths, was_dead, deepest = {}, 0, False, 0.0
    y0 = beats[0]["position"][1] if beats else 0
    for e in telemetry:
        t = round(e.get("game_updates", 0) / 60, 1)
        kind = e.get("event")
        if kind == "heartbeat":
            tile_y = (e["position"][1] + 21) / 16  # player centre (42 px tall)
            deepest = max(deepest, (e["position"][1] - y0) / 16)
            if e.get("dead") and not was_dead:
                deaths += 1
            was_dead = bool(e.get("dead"))
            if not e.get("dead"):
                if tile_y > surface:
                    first.setdefault("layer_underground", t)
                if tile_y > rock:
                    first.setdefault("layer_cavern", t)
            for fact, _, k in CATALOG:
                if k == "possession" and fact not in first and possession(fact, e):
                    first[fact] = t
        elif kind == "crafted":
            for fact, _, k in CATALOG:
                if k == "crafted" and fact not in first and crafted(fact, e):
                    first[fact] = t
        elif kind == "placed":
            for fact, _, k in CATALOG:
                if k == "placed" and fact not in first and placed(fact, e):
                    first[fact] = t
        elif kind == "checkpoint" and e.get("milestone") == "boss_eye_of_cthulhu_defeated":
            first.setdefault("boss_eye_of_cthulhu", t)
    unavailable = [f for f, _, k in CATALOG if k in ("crafted", "placed") and version < 0.7]
    receipts = run / "inputs.jsonl"
    actions = [json.loads(s) for s in receipts.read_text().splitlines()] if receipts.exists() else []
    published = reference_score(telemetry, actions=actions)
    crafts = {}
    for e in telemetry:
        if e.get("event") == "crafted":
            crafts[e.get("name")] = crafts.get(e.get("name"), 0) + (e.get("stack") or 1)
    places = {}
    for e in telemetry:
        if e.get("event") == "placed":
            places[str(e.get("tile_type"))] = places.get(str(e.get("tile_type")), 0) + 1
    result = {"run": run.name, "observer_version": start.get("observer_version"),
              "published_score": published["agency_score"],
              "published_milestones_game_s": {m: round(v.get("game_updates", 0) / 60, 1)
                                              for m, v in published["first_unlocks"].items()},
              "extended_count": sum(1 for f, _, _ in CATALOG if f in first),
              "extended_available": len(CATALOG) - len(unavailable),
              "extended_game_s": {f: first[f] for f, _, _ in CATALOG if f in first},
              "extended_unavailable": unavailable,
              "deaths": deaths, "max_depth_tiles": round(deepest),
              "world": {"seed": header["seed"], "evil": header["evil"], "surface_tile": surface, "rock_layer_tile": rock},
              "crafted": crafts, "placed_tile_types": places,
              "game_seconds": round((beats[-1]["game_updates"] if beats else 0) / 60)}
    if write:
        (run / "extended-score.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    # --no-write: print only (re-scoring older campaigns without adding files to their runs)
    write = "--no-write" not in sys.argv
    for path in (a for a in sys.argv[1:] if a != "--no-write"):
        print(json.dumps(score(path, write)), flush=True)
