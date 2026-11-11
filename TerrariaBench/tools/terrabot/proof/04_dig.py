# timeout: 2600
# Step 4: dig by hand (direct mining, no pathfinder for the digging itself): a 2-wide shaft straight down until the
# player is below the surface layer (iron and lead veins are mostly in the underground layer; surface enemies such as
# zombies do not spawn there), then a zigzag of 3-tall tunnels 32 columns each way, 9 rows apart. Torches every
# 8 tiles (more are crafted from gel at the carried bench); never opens a cell next to liquid; mines every revealed
# iron/lead ore within reach of the tunnels; rests when hurt; leaves water when the head is under it. Stops at 15
# ore of one anvil metal and enough stone for a furnace.
import time
import tb
from tb.path import node_of
from lib.botlib import fight, collect, say, light_here, metal_ore, recover, make_torches, wait_alive

ORE = ("Iron", "Lead")
NEED = 15
BUDGET = 2400
t0 = time.time()


class Died(Exception):
    pass


class Done(Exception):
    pass


def ready():
    return metal_ore()[1] >= NEED and tb.count("Stone Block") >= 22


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
        trees = any(g.kind(xx, yy) == "Trees" for xx in (x - 1, x, x + 1, x + 2) for yy in range(top - 3, top + 1))
        if not wet and not trees:
            d = abs(x - p.tile_x)
            if best is None or d < best[0]:
                best = (d, x, top)
    return best[1:] if best else None


def clear(cells):
    """Mine the given cells if solid; refuse if any is unknown ("dark") or next to liquid ("wet"); "hard" if a
    cell does not break."""
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    g = tb.tiles(min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1)
    for x, y in cells:
        if not g.known(x, y):
            return "dark"
        if any(g.liquid(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            return "wet"
    for x, y in cells:
        if g.kind(x, y) in ("Empty", "Torches"):
            continue
        try:
            if not tb.mine(x, y):
                return "hard"
        except tb.TbError as e:
            say("mine", x, y, e)
            return "hard"
    return "ok"


bad_ore = set()


def wet_near(x, y):
    g = tb.tiles(x - 1, y - 1, x + 1, y + 1)
    return any(g.liquid(xx, yy) for xx in (x - 1, x, x + 1) for yy in (y - 1, y, y + 1))


def mine_visible_ore(radius=14):
    """Mine revealed iron/lead ore around the player, nearest first, walking (digging) to cells out of reach."""
    got = 0
    for _ in range(60):
        if metal_ore()[1] >= NEED + 2:
            break
        p = tb.me()
        cells = [c for k in ORE for c in tb.find_tiles(k, radius=radius, limit=60) if c not in bad_ore]
        if not cells:
            break
        x, y = min(cells, key=lambda c: abs(c[0] + 0.5 - p.x) + abs(c[1] + 0.5 - p.y))
        if wet_near(x, y):
            bad_ore.add((x, y))
            continue
        if abs(x + 0.5 - p.x) > 4 or abs(y + 0.5 - p.y) > 3.5:
            tb.goto(x, y + 1, near=2, dig=True, place=True, timeout=20)
            check()
            p = tb.me()
            if abs(x + 0.5 - p.x) > 4.5 or abs(y + 0.5 - p.y) > 4:
                bad_ore.add((x, y))
                continue
        try:
            ok = tb.mine(x, y)
        except tb.TbError as e:
            say("ore", x, y, e)
            ok = False
        if ok:
            got += 1
        else:
            bad_ore.add((x, y))
    if got:
        tb.sleep(20)
        collect(radius=10)
        say("ore mined", got, "->", metal_ore(), "iron", tb.count("Iron Ore"), "lead", tb.count("Lead Ore"),
            "at", node_of(tb.me()), round(time.time() - t0), "s")
    return got


last_light, last_dry = None, None


def check(light_every=16):
    """Survival and bookkeeping between digging moves. Torches are placed where darkness stops the digging and,
    in tunnels, every `light_every` tiles (ore in the walls shows only where light reaches)."""
    global last_light, last_dry
    p = tb.me()
    if p.dead:
        wait_alive()
        raise Died()
    if time.time() - t0 > BUDGET:
        raise Done("time")
    fight()
    p = tb.me()
    x, y = node_of(p)
    if p.breath < p.breath_max and p.submerged:
        say("head under water at", x, y, "-> back to", last_dry)
        tb.hold(["jump"], 20)
        if last_dry:
            tb.goto(*last_dry, near=1, dig=True, place=True, timeout=30)
        raise Wet()
    if p.on_ground and not p.wet:
        last_dry = (x, y)
    if p.life < 45:
        say("resting at life", p.life)
        recover(80, max_ticks=2400)
    if tb.count("Torch") <= 5 and tb.count("Gel"):
        say("torches", tb.count("Torch"), "->", make_torches(keep_wood=16))
    if light_every and (last_light is None or abs(x - last_light[0]) + abs(y - last_light[1]) >= light_every):
        if light_here(reserve=4):
            last_light = (x, y)


class Wet(Exception):
    pass


def dig_down(rows_or_pred, side):
    """Dig the 2-wide shaft down until the predicate (or row count) is met; sidesteps up to 3 columns at hard/wet
    cells (either side). Returns False if it cannot continue (no light, or blocked 4 times)."""
    stuck = blocked = 0
    start_y = tb.me().foot_y
    pred = rows_or_pred if callable(rows_or_pred) else (lambda p: p.foot_y - start_y >= rows_or_pred)
    while not pred(tb.me()):
        check(light_every=0)
        if mine_visible_ore():
            continue
        if ready():
            raise Done("ore")
        p = tb.me()
        x, y = node_of(p)
        r = clear([(x, y + 1), (x + 1, y + 1)])
        if r == "ok":
            tb.sleep(10)
            stuck = stuck + 1 if node_of(tb.me())[1] == y else 0
            if stuck > 6:
                tb.hold("left" if side < 0 else "right", 4)
                stuck = 0
            continue
        say("shaft", r, "at", x, y)
        if r == "dark":
            if light_here(reserve=0):
                globals()["last_light"] = (x, y)
                continue
            return False
        blocked += 1
        if blocked > 4:
            return False
        moved = False
        for _ in range(3):
            nx = x + 2 if side > 0 else x - 1
            if clear([(nx, y), (nx, y - 1), (nx, y - 2)]) != "ok":
                break
            tb.hold("right" if side > 0 else "left", 8)
            x, y = node_of(tb.me())
            moved = True
        if not moved:
            side = -side
    return True


def tunnel_to(tx):
    """Dig a 3-tall tunnel along the current row to column tx. At hard/wet cells drop 4 rows and go on."""
    drops = 0
    side = 1 if tx > node_of(tb.me())[0] else -1
    while True:
        check()
        if mine_visible_ore():
            continue
        if ready():
            raise Done("ore")
        p = tb.me()
        x, y = node_of(p)
        if (tx - x) * side <= 0:
            return True
        nx = x + 2 if side > 0 else x - 1
        r = clear([(nx, y), (nx, y - 1), (nx, y - 2)])
        if r == "ok":
            tb.hold("right" if side > 0 else "left", 8)
            if node_of(tb.me()) == (x, y):
                tb.hold(["jump", "right" if side > 0 else "left"], 10)
            continue
        say("tunnel", r, "at", x, y, "side", side)
        if r == "dark" and light_here(reserve=0):
            globals()["last_light"] = (x, y)
            continue
        if r in ("dark", "wet") or drops >= 3:
            return False
        drops += 1
        if not dig_down(4, side):
            return False


def run():
    spot = dry_column()
    say("shaft at", spot, "layer", tb.me().layer, tb.time().clock)
    if spot:
        tb.goto(spot[0], spot[1], near=0, timeout=40, dig=False, place=False)
    home_x, top_y = node_of(tb.me())
    crossed = []

    def deep_enough(p):
        if p.layer != "surface" and not crossed:
            crossed.append(p.foot_y)
            say("underground layer at row", p.foot_y, "depth", p.foot_y - top_y, round(time.time() - t0), "s",
                tb.time().clock)
        return (crossed and p.foot_y - crossed[0] >= 5) or p.foot_y - top_y > 200

    if not dig_down(deep_enough, 1):
        say("no light for the shaft")
        return
    base, stalled = tb.me().foot_y, 0
    for k in range(20):
        side = -1 if k % 2 == 0 else 1
        level = base + 9 * k
        if tb.me().foot_y < level and not dig_down(lambda p: p.foot_y >= level, side):
            say("cannot go down at", node_of(tb.me()))
        x0 = node_of(tb.me())[0]
        ok = tunnel_to(home_x + side * 32)
        stalled = stalled + 1 if abs(node_of(tb.me())[0] - x0) < 3 else 0
        if stalled >= 3:
            say("stalled three legs")
            return
        collect(radius=10)
        say("leg", k, "done" if ok else "stopped", "at", node_of(tb.me()), "ore", metal_ore(), "stone",
            tb.count("Stone Block"), "torches", tb.count("Torch"), "life", tb.me().life, round(time.time() - t0), "s",
            tb.time().clock)
        if not ok and tb.count("Torch") <= 1:
            return


for attempt in range(3):
    try:
        run()
        break
    except Done as e:
        say("done:", e)
        break
    except Wet:
        say("left the water; new shaft")
    except Died:
        say("died; ore", metal_ore())
        if ready():
            break
    if time.time() - t0 > BUDGET:
        break
collect(radius=8)
say("end at", node_of(tb.me()), "layer", tb.me().layer, "stone", tb.count("Stone Block"), "iron",
    tb.count("Iron Ore"), "lead", tb.count("Lead Ore"), "torches", tb.count("Torch"), "gel", tb.count("Gel"),
    "wood", tb.count("Wood"), "bench", tb.count("Work Bench"), "life", tb.me().life, round(time.time() - t0), "s",
    tb.time().clock)
