# timeout: 900
# Step 5: build where we are (underground): place the bench, craft and place a furnace, smelt bars, craft and place
# an anvil. The tunnels are 3 tall with a solid floor, which fits all three stations; if one cannot be placed, carve a
# 17x3 room here (never opening a cell next to liquid) and try again. Only in daylight, as a last resort, climb back
# to the surface start point (pathfinder with digging and pillaring) and build there.
import tb
from lib.botlib import (place_station, say, collect, light_here, fight, metal_ore, wait_alive, recover, clock_min,
                        flat_spots)

wait_alive()
fight()
if tb.me().life < 50:
    recover(80, max_ticks=1800)
p = tb.me()
X, Y = p.tile_x, p.foot_y
HALF = 8  # room columns X-8..X+8, rows Y-2..Y (3 tall), solid floor in row Y+1


def wet_near(g, x, y):
    return any(g.liquid(xx, yy) for xx in range(x - 1, x + 2) for yy in range(y - 1, y + 2))


def carve():
    """Mine the room outward from the middle, one column at a time, walking along and lighting it so that cells
    become revealed before they are mined (tb.mine refuses unrevealed tiles); stop a side at liquid."""
    say("carving a room at", X, Y)
    light_here(reserve=0)
    for side in (-1, 1):
        for dx in range(1, HALF + 1):
            x = X + side * dx
            g = tb.tiles(x - 1, Y - 3, x + 1, Y + 2)
            if not all(g.known(x, y) for y in range(Y - 2, Y + 2)):
                light_here(reserve=0)
                g = tb.tiles(x - 1, Y - 3, x + 1, Y + 2)
            if any(wet_near(g, x, y) for y in range(Y - 2, Y + 1)):
                break
            for y in range(Y - 2, Y + 1):
                kind = g.kind(x, y)
                if g.known(x, y) and kind != "Empty" and not (kind == "Torches" and y == Y - 2) and not g.liquid(x, y):
                    try:
                        tb.mine(x, y)
                    except tb.TbError as e:
                        say("carve", x, y, e)
            if dx >= 2:
                tb.goto(x - side, Y, near=0, dig=True, place=False, timeout=10)
        tb.goto(X, Y, near=1, dig=True, place=False, timeout=20)
    collect(radius=10)
    floor = tb.tiles(X - HALF, Y + 1, X + HALF, Y + 1)
    for x in range(X - HALF, X + HALF + 1):
        if floor.known(x, Y + 1) and not floor.solid(x, Y + 1) and not floor.liquid(x, Y + 1):
            block = "Stone Block" if tb.count("Stone Block") > 22 else "Dirt Block"
            if tb.count(block):
                tb.place(block, x, Y + 1)
    fight()


def near_station(kind, item):
    """Stand next to a placed station of this kind (the nearest within 20 tiles); True if it is in range."""
    if kind in tb.me().stations_near:
        return True
    s = tb.find_tiles(kind, radius=20, limit=1)
    if s:
        tb.goto(s[0][0], s[0][1], near=1, timeout=15, dig=False, place=False)
    return kind in tb.me().stations_near


def build():
    if not near_station("WorkBenches", "Work Bench"):
        if not tb.count("Work Bench"):
            tb.craft("Work Bench")
        bx, by = place_station("Work Bench", 2, 2)
        say("bench at", bx, by)
    if not near_station("Furnaces", "Furnace"):
        if not tb.count("Furnace"):
            tb.craft("Furnace")
        fx, fy = place_station("Furnace", 3, 2)
        say("furnace at", fx, fy, tb.me().stations_near)
    near_station("WorkBenches", "Work Bench")
    metal, ore = metal_ore()
    anvil = f"{metal} Anvil"
    bars = min(5 - tb.count(f"{metal} Bar"), tb.count(f"{metal} Ore") // 3)
    if bars > 0:
        tb.craft(f"{metal} Bar", bars)
    say(metal, "bars", tb.count(f"{metal} Bar"), "ore left", tb.count(f"{metal} Ore"), tb.me().stations_near)
    if tb.count(f"{metal} Bar") < 5:
        raise SystemExit(f"not enough {metal} for an anvil: {tb.count(f'{metal} Bar')} bars")
    if not near_station("WorkBenches", "Work Bench"):
        # the first bench may be out of walking reach (the furnace can land a few rows away): a new one from wood
        if not tb.count("Work Bench"):
            tb.craft("Work Bench")
        bx, by = place_station("Work Bench", 2, 2)
        say("second bench at", bx, by, tb.me().stations_near)
    tb.craft(anvil)
    ax, ay = place_station(anvil, 2, 2)
    say("anvil placed at", ax, ay, "stations", tb.me().stations_near, tb.time().clock)


say("building at", X, Y, "layer", p.layer, "ore", metal_ore(), "stone", tb.count("Stone Block"), "wood",
    tb.count("Wood"), "torches", tb.count("Torch"), tb.time().clock)
carved = False
if len(flat_spots(3, 2, radius=7)) < 3:  # e.g. the bottom of a 2-wide shaft: make the room first
    carve()
    carved = True
try:
    build()
except tb.TbError as e:
    say("build failed here:", e)
    if not carved:
        carve()
    try:
        build()
    except tb.TbError as e:
        say("build failed in the room:", e)
        home = tb.store.get("home")
        if not home or not 270 <= clock_min() <= 1110:
            raise
        say("climbing to", home, tb.goto(home[0], home[1], near=3, dig=True, place=True, timeout=400))
        build()
