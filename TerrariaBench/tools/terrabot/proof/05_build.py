# timeout: 900
# Step 5: carve a small room where we are (never opening a cell next to liquid), place the bench, craft and place a
# furnace, smelt bars, craft and place an anvil. If a station cannot be placed down here, climb back to the surface
# start point (pathfinder with digging and pillaring) and build there.
import tb
from lib.botlib import place_station, say, collect, light_here, fight

p = tb.me()
if p.dead:
    tb.sleep(p.respawn_ticks + 30)
    p = tb.me()
g = tb.tiles(p.tile_x - 6, p.foot_y - 4, p.tile_x + 6, p.foot_y + 2)


def wet_near(x, y):
    return any(g.liquid(xx, yy) for xx in range(x - 1, x + 2) for yy in range(y - 1, y + 2))


# A room 13 wide and 3 tall with a solid floor (holes filled with blocks) leaves space for three stations.
for x in range(p.tile_x - 6, p.tile_x + 7):
    for y in range(p.foot_y - 2, p.foot_y + 1):
        if g.known(x, y) and g.solid(x, y) and not wet_near(x, y):
            tb.mine(x, y)
collect(radius=8)
floor = tb.tiles(p.tile_x - 6, p.foot_y + 1, p.tile_x + 6, p.foot_y + 1)
for x in range(p.tile_x - 6, p.tile_x + 7):
    if not floor.solid(x, p.foot_y + 1) and not wet_near(x, p.foot_y + 1):
        block = "Stone Block" if tb.count("Stone Block") > 22 else "Dirt Block"
        if tb.count(block):
            tb.place(block, x, p.foot_y + 1)
light_here()
fight()


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
    anvil = "Iron Anvil" if tb.count("Iron Anvil") or tb.count("Iron Ore") >= tb.count("Lead Ore") else "Lead Anvil"
    if not tb.count(anvil):
        tb.craft(anvil.replace("Anvil", "Bar"), 5)
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
