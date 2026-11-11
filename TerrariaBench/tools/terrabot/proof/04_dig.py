# timeout: 2500
# Step 4: dig by hand (direct mining, no pathfinder): a 2-wide shaft ~35 rows down, then 3-tall horizontal tunnels
# left and right, deeper in steps. Torches every few tiles; never opens a cell next to liquid; mines iron/lead ore
# that becomes visible; retreats when the head is under water.
import time
import tb
from tb.path import node_of
from lib.botlib import fight, collect, say, light_here

ORE = ("Iron", "Lead")
t0 = time.time()


def ore_count():
    return max(tb.count("Iron Ore"), tb.count("Lead Ore"))


def dry_column():
    p = tb.me()
    g = tb.tiles(p.tile_x - 40, p.foot_y - 10, p.tile_x + 40, p.foot_y + 25)
    best = None
    for x in range(p.tile_x - 30, p.tile_x + 31):
        top = next((y for y in range(p.foot_y - 10, p.foot_y + 12) if g.solid(x, y + 1) and g.solid(x + 1, y + 1)
                    and g.empty(x, y) and g.empty(x + 1, y)), None)
        if top is None:
            continue
        wet = any(g.liquid(xx, yy) for xx in range(x - 8, x + 10) for yy in range(top - 2, top + 25))
        trees = any(g.kind(xx, yy) == "Trees" for xx in (x, x + 1) for yy in range(top - 3, top + 1))
        if not wet and not trees:
            d = abs(x - p.tile_x)
            if best is None or d < best[0]:
                best = (d, x, top)
    return best[1:] if best else None


def clear(cells):
    """Mine the given cells if solid; refuse (return False) if any is unknown or next to liquid."""
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    g = tb.tiles(min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1)
    for x, y in cells:
        if not g.known(x, y):
            return "dark"
        if g.liquid(x, y) or any(g.liquid(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            return "wet"
    for x, y in cells:
        if g.solid(x, y) or g.kind(x, y) not in ("Empty", "Torches"):
            if g.kind(x, y) == "Torches":
                continue
            if not tb.mine(x, y):
                return "hard"
    return "ok"


def mine_visible_ore(radius=16):
    p = tb.me()
    cells = [c for k in ORE for c in tb.find_tiles(k, radius=radius, limit=60)]
    cells.sort(key=lambda c: abs(c[0] - p.x) + abs(c[1] - p.y))
    got = 0
    for (x, y) in cells[:20]:
        p = tb.me()
        if abs(x - p.x) > 4 or abs(y - p.y) > 3:
            if not tb.goto(x, y, near=2, dig=True, place=True, timeout=20):
                continue
        got += bool(tb.mine(x, y))
        if ore_count() >= 15:
            break
    collect(radius=8)
    return got


spot = dry_column()
say("shaft at", spot)
if spot:
    tb.goto(spot[0], spot[1], near=0, timeout=40, dig=False, place=False)
start = tb.me()
home_x, top_y = node_of(start)
legs = [(lvl, side) for lvl in (60, 90, 120, 150, 180) for side in (-1, 1)]
leg, last_light, last_dry, stuck, tried_ore = 0, None, None, 0, set()
while time.time() - t0 < 2400 and leg < len(legs):
    p = tb.me()
    if p.dead:
        tb.sleep(p.respawn_ticks + 30)
        say("died; respawned at", tb.me().tile_x, tb.me().foot_y)
        break
    fight()
    if ore_count() >= 15 and tb.count("Stone Block") >= 25:
        break
    x, y = node_of(p)
    if p.breath < p.breath_max:
        say("head under water at", x, y, "-> back to", last_dry)
        tb.hold(["jump"], 20)
        if last_dry:
            tb.goto(*last_dry, near=1, dig=True, place=True, timeout=30)
        leg += 1
        continue
    if p.on_ground:
        last_dry = (x, y)
    if last_light is None or abs(x - last_light[0]) + abs(y - last_light[1]) >= 7:
        if light_here():
            last_light = (x, y)
    visible = {c for k in ORE for c in tb.find_tiles(k, radius=16, limit=40)} - tried_ore
    if visible:
        tried_ore |= visible
        mine_visible_ore()
        continue
    level, side = legs[leg]
    if y - top_y < level:                       # shaft down
        r = clear([(x, y + 1), (x + 1, y + 1)])
        if r == "ok":
            tb.sleep(10)
            stuck = stuck + 1 if node_of(tb.me())[1] == y else 0
            if stuck > 6:
                tb.hold(["left"] if side < 0 else ["right"], 4)
                stuck = 0
            continue
        say("shaft", r, "at", x, y)
        if r == "dark":
            if light_here():
                continue
            leg += 1  # no light left for this direction
            continue
        # sidestep 3 columns and continue the shaft there
        for _ in range(3):
            nx = x + 2 if side > 0 else x - 1
            if clear([(nx, y), (nx, y - 1), (nx, y - 2)]) != "ok":
                break
            tb.hold("right" if side > 0 else "left", 8)
            x, y = node_of(tb.me())
        side = -side
        continue
    if abs(x - home_x) >= 45 and (x - home_x) * side > 0:
        leg += 1
        say("leg done", level, side, "at", x, y, "stone", tb.count("Stone Block"), "ore", ore_count(), round(time.time() - t0))
        continue
    nx = x + 2 if side > 0 else x - 1          # tunnel sideways: the 3 cells in front of the body
    r = clear([(nx, y), (nx, y - 1), (nx, y - 2)])
    if r == "ok":
        tb.hold("right" if side > 0 else "left", 8)
        continue
    say("tunnel", r, "at", x, y, "side", side)
    if r == "dark" and light_here():
        continue
    leg += 1
    if r == "dark" and tb.count("Torch") <= 3:
        say("out of torches")
        break
collect(radius=8)
say("depth", tb.me().foot_y - start.foot_y, "stone", tb.count("Stone Block"), "iron", tb.count("Iron Ore"),
    "lead", tb.count("Lead Ore"), "torches", tb.count("Torch"), "life", tb.me().life, round(time.time() - t0), "s",
    tb.time().clock)
