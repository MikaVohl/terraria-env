"""In-game pathfinder checks (run by `run.py live-test --extra tools/terrabot/path_live.py`). Writes <run>/path-live.json.

Each case records success, wall seconds and game ticks: surface walks over natural terrain (both directions),
digging down, pillaring back up, climbing over a 3-high wall built from placed blocks, and an unreachable goal.
"""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "terrariabench"))
import tb  # noqa: E402

out = []


def surface_row(x, around):
    g = tb.tiles(x, around - 30, x, around + 30)
    for y in range(around - 30, around + 30):
        if g.known(x, y) and g.solid(x, y + 1) and all(g.empty(x, yy) for yy in range(y - 2, y + 1)):
            return y
    return None


def case(name, fn):
    t0, k0 = time.time(), tb.me().tick
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: {e}"
    p = tb.me()
    out.append({"case": name, "ok": bool(ok), "wall_s": round(time.time() - t0, 1), "game_ticks": p.tick - k0,
                "end": [p.tile_x, p.foot_y], "life": p.life, "detail": detail})
    print(json.dumps(out[-1]), flush=True)
    tb.stop()


home = tb.me()
hx, hy = home.tile_x, home.foot_y


def walk(dx):
    def f():
        x = hx + dx
        y = surface_row(x, hy)
        if y is None:
            return False, f"no revealed surface at column {x}"
        return tb.goto(x, y, near=1, timeout=60, dig=False, place=False), {"goal": [x, y]}
    return f


case("walk_right_25", walk(25))
case("walk_back_home", lambda: (tb.goto(hx, surface_row(hx, hy), near=1, timeout=60, dig=False, place=False), None))
case("walk_left_25", walk(-25))
case("walk_back_home_2", lambda: (tb.goto(hx, surface_row(hx, hy), near=1, timeout=60, dig=False, place=False), None))

start = tb.me()
case("dig_down_8", lambda: (tb.goto(start.tile_x, start.foot_y + 8, near=0, timeout=90, dig=True, place=False),
                            {"blocks": [(i.name, i.stack) for i in tb.inventory() if i.place_tile]}))
case("pillar_up_8", lambda: (tb.goto(start.tile_x, start.foot_y, near=1, timeout=120, dig=True, place=True), None))


def wall():
    p = tb.me()
    x = p.tile_x + 3
    y = surface_row(x, p.foot_y)
    if y is None:
        return False, "no surface for wall"
    blocks = [i for i in tb.inventory() if i.place_tile and i.name.endswith("Block")]
    if not blocks or blocks[0].stack < 3:
        return False, "not enough blocks"
    for yy in (y, y - 1, y - 2):
        tb.place(blocks[0].name, x, yy)
    g = tb.tiles(x, y - 2, x, y)
    built = sum(g.solid(x, yy) for yy in range(y - 2, y + 1))
    goal_x = x + 4
    gy = surface_row(goal_x, y)
    return tb.goto(goal_x, gy, near=1, timeout=60, dig=False, place=False), {"wall_height": built, "goal": [goal_x, gy]}


case("over_3_high_wall", wall)
case("unreachable_without_dig", lambda: (not tb.goto(hx, hy + 30, near=0, timeout=20, dig=False, place=False),
                                         "expected False"))
(Path(sys.argv[1]) / "path-live.json").write_text(json.dumps(out, indent=1))
print(json.dumps({"passed": sum(c["ok"] for c in out), "total": len(out)}))
