# timeout: 900
# Step 5: carve a room where we are (never opening a cell next to liquid), place the bench, craft and place a
# furnace, smelt bars, craft and place an anvil. If a station cannot be placed down here, climb back to the surface
# start point (pathfinder with digging and pillaring) and build there.
import tb
from lib.botlib import place_station, say, collect, light_here, fight

p = tb.me()
if p.dead:
    tb.sleep(p.respawn_ticks + 30)
    p = tb.me()
X, Y = p.tile_x, p.foot_y
HALF = 8  # room columns X-8..X+8, rows Y-2..Y (3 tall), solid floor in row Y+1


def wet_near(g, x, y):
    return any(g.liquid(xx, yy) for xx in range(x - 1, x + 2) for yy in range(y - 1, y + 2))


def carve():
    """Mine the room outward from the middle, one column at a time, walking along and lighting it so that cells
    become revealed before they are mined (tb.mine refuses unrevealed tiles); stop a side at liquid."""
    light_here()
    for side in (-1, 1):
        for dx in range(1, HALF + 1):
            x = X + side * dx
            if dx % 3 == 0:
                tb.goto(x - side * 2, Y, near=1, dig=True, place=False, timeout=15)
                light_here()
            g = tb.tiles(x - 1, Y - 3, x + 1, Y + 2)
            if any(wet_near(g, x, y) for y in range(Y - 2, Y + 1)):
                break
            for y in range(Y - 2, Y + 1):
                if g.known(x, y) and g.solid(x, y):
                    tb.mine(x, y)
        tb.goto(X, Y, near=1, dig=True, place=False, timeout=20)
    collect(radius=10)
    floor = tb.tiles(X - HALF, Y + 1, X + HALF, Y + 1)
    for x in range(X - HALF, X + HALF + 1):
        if floor.known(x, Y + 1) and not floor.solid(x, Y + 1) and not floor.liquid(x, Y + 1):
            block = "Stone Block" if tb.count("Stone Block") > 22 else "Dirt Block"
            if tb.count(block):
                tb.place(block, x, Y + 1)
    light_here()
    fight()


def anvil_kind():
    """The anvil this run can make: one already held, else the metal with 5 bars, else the ore with more (>= 15)."""
    for metal in ("Iron", "Lead"):
        if tb.count(f"{metal} Anvil"):
            return metal
    for metal in ("Iron", "Lead"):
        if tb.count(f"{metal} Bar") >= 5:
            return metal
    return "Iron" if tb.count("Iron Ore") >= tb.count("Lead Ore") else "Lead"


carve()

def build():
    if not [s for s in tb.me().stations_near if s == "WorkBenches"]:
        if not tb.count("Work Bench"):
            tb.craft("Work Bench")
        bx, by = place_station("Work Bench", 2, 2)
        tb.goto(bx, by, near=1, timeout=10, dig=False, place=False)
    if "Furnaces" not in tb.me().stations_near:
        if not tb.count("Furnace"):
            tb.craft("Furnace")
        fx, fy = place_station("Furnace", 3, 2)
        tb.goto(fx, fy, near=1, timeout=10, dig=False, place=False)
        say("furnace at", fx, fy, tb.me().stations_near)
    metal = anvil_kind()
    anvil = f"{metal} Anvil"
    if not tb.count(anvil):
        if tb.count(f"{metal} Bar") < 5:
            tb.craft(f"{metal} Bar", 5 - tb.count(f"{metal} Bar"))
        if "WorkBenches" not in tb.me().stations_near:
            b = tb.find_tiles("WorkBenches", radius=12, limit=1)
            if b:
                tb.goto(b[0][0], b[0][1], near=1, timeout=10, dig=False, place=False)
        tb.craft(anvil)
    ax, ay = place_station(anvil, 2, 2)
    say("anvil placed at", ax, ay, "stations", tb.me().stations_near, tb.time().clock)


try:
    build()
except tb.TbError as e:
    say("underground build failed:", e)
    home = tb.store.get("home")
    say("climbing to", home, tb.goto(home[0], home[1], near=3, dig=True, place=True, timeout=400))
    build()
