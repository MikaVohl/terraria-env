"""In-game tests of tb-api-1.0-rc1 against a TerraBot session started in test mode (TERRABOT_TEST=1 enables the
privileged truth_* ops used only here as ground truth; benchmark runs never have them).

    TB_SOCKET=<run>/agent.sock python tools/terrabot/live_tests.py <run>   # writes <run>/live-tests.json

Covers: no X-ray (tiles/find_tiles/npcs vs ground truth), NPC field whitelist, real recipe rules (missing ingredients
and missing stations refused), reach limits on mining, real mining/pickup/placement with events, movement speed and
jump height within vanilla limits, unknown ops refused by the proxy, map memory for off-screen cells (no live leak),
action journal entries for scoring.
"""
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "terrariabench"))
import tb  # noqa: E402
from tb._rpc import call  # noqa: E402

ORES = {"Copper", "Tin", "Iron", "Lead", "Silver", "Tungsten", "Gold", "Platinum"}
results = []


def check(name):
    def wrap(fn):
        t0 = time.time()
        try:
            detail = fn()
            results.append({"test": name, "ok": True, "detail": detail, "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa: BLE001
            results.append({"test": name, "ok": False, "error": f"{type(e).__name__}: {e}",
                            "trace": traceback.format_exc()[-800:], "s": round(time.time() - t0, 2)})
        print(json.dumps(results[-1])[:400], flush=True)
        return fn
    return wrap


def truth(x0, y0, x1, y1):
    return tb.Grid.from_reply(call("truth_tiles", x0=x0, y0=y0, x1=x1, y1=y1))


@check("basics")
def _():
    w, p, inv = tb.world(), tb.me(), tb.inventory()
    names = sorted(i.name for i in inv)
    assert w.api == "tb-api-1.0-rc1" and w.test_mode is True
    assert names == ["Copper Axe", "Copper Pickaxe", "Copper Shortsword"], names
    assert p.life == 100 and not p.dead
    return {"spawn": w.spawn, "me": [p.x, p.y, p.foot_y], "inventory": names, "time": tb.time()}


@check("no_xray_tiles")
def _():
    p = tb.me()
    x0, y0, x1, y1 = p.tile_x - 100, p.foot_y - 60, p.tile_x + 99, p.foot_y + 139
    api, real = tb.tiles(x0, y0, x1, y1), truth(x0, y0, x1, y1)
    known = mism = deep_known = deep_real_solid = remembered = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if api.known(x, y):
                known += 1
                if api.remembered(x, y):  # map memory (may differ from truth: tested in map_memory_no_leak)
                    remembered += 1
                else:  # lit on screen: exactly the live tile
                    mism += api.type(x, y) != real.type(x, y) or api.flag(x, y) != real.flag(x, y)
                deep_known += y > p.foot_y + 40
            deep_real_solid += y > p.foot_y + 40 and real.solid(x, y)
    total = api.w * api.h
    assert mism == 0, f"{mism} lit on-screen cells differ from truth"
    assert known < total * 0.4, f"{known}/{total} cells known at spawn"
    assert deep_real_solid > 1000 and deep_known == 0, (deep_real_solid, deep_known)
    return {"rect": [x0, y0, x1, y1], "known": known, "remembered": remembered, "total": total,
            "deep_solid_truth": deep_real_solid, "deep_known": deep_known}


@check("no_xray_find_tiles")
def _():
    p = tb.me()
    x0, y0, x1, y1 = p.tile_x - 100, p.foot_y - 60, p.tile_x + 100, p.foot_y + 138
    real = truth(x0, y0, x1, y1)
    truth_ores = sum(len(real.find(k)) for k in ORES)
    api_ores = {k: tb.find_tiles(k, radius=100, limit=500) for k in ORES}
    api_count = sum(len(v) for v in api_ores.values())
    api_grid = tb.tiles(x0, y0, x1, y1)
    for k, cells in api_ores.items():
        for (x, y) in cells:
            if api_grid.inside(x, y):
                assert api_grid.known(x, y), f"find_tiles returned unrevealed {k} at {(x, y)}"
    assert truth_ores > 20, truth_ores
    assert api_count < truth_ores * 0.2, (api_count, truth_ores)
    return {"ore_cells_truth": truth_ores, "ore_cells_api": api_count}


@check("no_xray_npcs")
def _():
    real, api = call("truth_npcs", radius=300), tb.npcs(300)
    ids_api = {n.id for n in api}
    assert ids_api <= {n["id"] for n in real}
    for n in api:
        assert set(n) == {"id", "name", "type", "x", "y", "width", "height", "life", "life_max", "hostile", "boss", "town"}, set(n)
    sw = tb.world().screen_tiles
    p = tb.me()
    far = [n for n in real if abs(n["x"] - p.x) > sw[0] / 2 + 6 or abs(n["y"] - p.y) > sw[1] / 2 + 6]
    leaked = [n for n in far if n["id"] in ids_api]
    assert not leaked, leaked
    return {"truth": len(real), "api": len(api), "far_truth": len(far)}


@check("recipes_real_rules")
def _():
    try:
        tb.craft("Work Bench")
        raise AssertionError("crafted a work bench with no wood")
    except tb.TbError as e:
        msg1 = str(e)
        assert "Wood 0/10" in msg1, msg1
    try:
        tb.craft("Furnace")
        raise AssertionError("crafted a furnace with nothing")
    except tb.TbError as e:
        msg2 = str(e)
        assert "station" in msg2, msg2
    allr = tb.recipes("Furnace", available=False)
    assert allr and "WorkBenches" in allr[0].stations, allr
    return {"work_bench_refusal": msg1, "furnace_refusal": msg2[:200], "furnace_recipe": allr[0]}


@check("mining_reach_and_pickup")
def _():
    p = tb.me()
    g = tb.tiles(p.tile_x - 15, p.foot_y - 5, p.tile_x + 15, p.foot_y + 6)
    far = next(((x, y) for y in range(p.foot_y + 1, p.foot_y + 4) for x in range(p.tile_x + 14, p.tile_x + 9, -1)
                if g.solid(x, y)), None)
    detail = {}
    if far:
        tb.select("Copper Pickaxe")
        tb.use_at(*far, ticks=90)
        assert tb.tiles(*far, *far).type(*far) == g.type(*far), "mined a tile out of reach"
        detail["out_of_reach_tile_kept"] = far
    tb.events()
    below = (p.tile_x, p.foot_y + 1)
    kind = g.kind(*below)
    before = {i.name: i.stack for i in tb.inventory()}
    assert tb.mine(*below), f"could not mine {kind} below feet"
    tb.sleep(60)
    ev = tb.events()
    after = {i.name: i.stack for i in tb.inventory()}
    gained = {k: after[k] - before.get(k, 0) for k in after if after[k] > before.get(k, 0)}
    assert any(e.event == "tile_broken" for e in ev), ev
    assert gained, "nothing picked up"
    detail.update(mined=below, kind=kind, gained=gained, events=[e.event for e in ev])
    return detail


@check("placement")
def _():
    p = tb.me()
    blocks = [i for i in tb.inventory() if i.place_tile and i.name.endswith("Block")]
    assert blocks, "no block to place"
    g = tb.tiles(p.tile_x - 4, p.foot_y - 4, p.tile_x + 4, p.foot_y + 2)
    spot = next(((x, y) for y in (p.foot_y, p.foot_y + 1, p.foot_y - 1) for x in
                 (p.tile_x + 2, p.tile_x - 2, p.tile_x + 3, p.tile_x - 3, p.tile_x + 4, p.tile_x - 4)
                 if g.type(x, y) == -1 and not g.liquid(x, y) and
                 (g.solid(x, y + 1) or g.solid(x - 1, y) or g.solid(x + 1, y))), None)
    assert spot, g.render()
    ok = tb.place(blocks[0].name, *spot)
    assert ok, "placement failed"
    return {"placed": blocks[0].name, "at": spot}


@check("movement_limits")
def _():
    vmax, x0 = 0, tb.me().x
    for _ in range(12):
        s = tb.hold("right", 5)
        vmax = max(vmax, abs(s.vx))
    x1 = tb.me().x
    for _ in range(12):
        tb.hold("left", 5)
    assert vmax <= 3.1, vmax
    tb.sleep(30)
    def jump(chunks):
        tb.sleep(40)
        y0, peak = tb.me().y, 1e9
        for n in chunks:
            peak = min(peak, tb.hold("jump", n).y)
        for _ in range(20):
            peak = min(peak, tb.hold([], 2).y)
        return round(y0 - peak, 2)
    single, chunked = jump([15]), jump([3] * 5)
    assert 5 <= single <= 7.5, single
    assert abs(single - chunked) < 0.6, (single, chunked)  # consecutive holds leave no released-key gap
    return {"max_vx": vmax, "moved_tiles": round(x1 - x0, 2), "jump_rise_single_hold": single,
            "jump_rise_5x3_holds": chunked}


@check("proxy_rejects_unknown_ops")
def _():
    for op in ("teleport", "spawn_item", "set_tile"):
        try:
            call(op)
            raise AssertionError(f"{op} accepted")
        except tb.TbError as e:
            assert "not part of tb-api-1.0-rc1" in str(e), e
    return "teleport/spawn_item/set_tile refused"


@check("map_memory_no_leak")
def _():
    """Change revealed cells behind the player's back (test op, no TileFrame: no map update, as an unseen change);
    off screen tb.tiles must keep the remembered state, back on screen it must show the change."""
    p0 = tb.me()
    hx, hy = p0.tile_x, p0.foot_y
    g0 = tb.tiles(hx - 12, hy - 12, hx + 12, hy + 6)
    air = next((x, y) for y in range(hy - 10, hy - 4) for x in range(hx - 8, hx + 9)
               if g0.known(x, y) and g0.type(x, y) == -1 and not g0.liquid(x, y) and g0.known(x, y + 1))
    solid = next((x, y) for y in range(hy - 3, hy + 4) for x in [*range(hx - 9, hx - 3), *range(hx + 4, hx + 10)]
                 if g0.solid(x, y) and g0.kind(x, y) in ("Dirt", "Stone", "Grass") and g0.type(x, y - 1) == -1)
    wet = next((x, y) for y in range(hy - 10, hy - 4) for x in range(hx - 8, hx + 9)
               if (x, y) != air and g0.known(x, y) and g0.type(x, y) == -1 and not g0.liquid(x, y))
    sw = tb.world().screen_tiles
    far_x = max(air[0], solid[0], wet[0])
    for _ in range(12):  # walk right (revealing new ground on the way) until the edited cells are off screen
        p = tb.me()
        if p.x - far_x > sw[0] / 2 + 6:
            break
        tb.goto(p.tile_x + 30, p.foot_y, near=12, dig=True, place=True, timeout=30)
    p = tb.me()
    assert p.x - far_x > sw[0] / 2 + 2, "edited cells still on screen"
    old = [call("truth_edit", x=air[0], y=air[1], type=0), call("truth_edit", x=solid[0], y=solid[1], type=-1),
           call("truth_edit", x=wet[0], y=wet[1], liquid=255)]
    try:
        far = {c: tb.tiles(*c, *c).at(*c) for c in (air, solid, wet)}
        real = {c: truth(*c, *c).at(*c) for c in (air, solid, wet)}
        assert real[air].solid and not real[solid].solid and real[wet].liquid == "water", real
        assert far[air].remembered and far[air].type == -1 and not far[air].solid, far[air]
        assert far[solid].remembered and far[solid].solid, far[solid]
        assert far[wet].remembered and far[wet].liquid is None, far[wet]
        found = tb.find_tiles("Dirt", radius=100, limit=500)
        assert air not in [tuple(f) for f in found], "find_tiles saw the unseen dirt"
        assert tb.goto(hx, hy, near=2, dig=False, place=False, timeout=90), tb.path.last_error
        tb.sleep(30)
        near = {c: tb.tiles(*c, *c).at(*c) for c in (air, solid)}
        assert not near[air].remembered and near[air].solid, near[air]
        assert not near[solid].remembered and not near[solid].solid, near[solid]
    finally:
        for c, o in zip((air, solid, wet), old):
            call("truth_edit", x=c[0], y=c[1], type=o["type"], liquid=o["liquid"])
    return {"cells": {"air->dirt": air, "dirt->air": solid, "air->water": wet},
            "off_screen_reads": {str(k): [v.type, v.solid, v.liquid, v.remembered] for k, v in far.items()},
            "back_on_screen": {str(k): [v.type, v.solid, v.remembered] for k, v in near.items()}}


def main():
    run = Path(sys.argv[1])
    time.sleep(1)
    actions = [json.loads(l) for l in (run / "inputs.jsonl").read_text().splitlines()]
    results.append({"test": "inputs_journal", "ok": bool(actions) and all(a["actor"] == "agent" for a in actions),
                    "detail": {"actions": len(actions), "ops": sorted({a["op"] for a in actions})}})
    (run / "live-tests.json").write_text(json.dumps(results, indent=1))
    print(json.dumps({"passed": sum(r["ok"] for r in results), "total": len(results)}))


if __name__ == "__main__":
    main()
