"""Helper library of the scripted proof agent. Uses only the public tb API (tb-api-1.0); nothing here is part of
the frozen library, it is what an agent could write for itself."""
import tb

WEAPON_SKIP = ("Pickaxe", "Axe", "Hammer")


def say(*a):
    print(*a, flush=True)


def best_weapon():
    inv = tb.inventory()
    w = [i for i in inv if i.damage > 0 and i.pick == 0 and i.axe == 0 and i.hammer == 0 and not i.ammo and i.slot < 50]
    if not w:
        w = [i for i in inv if i.pick > 0]
    return max(w, key=lambda i: i.damage) if w else None


def hostiles(radius=12):
    return [n for n in tb.npcs(radius) if n.hostile]


def fight(radius=6, max_rounds=60):
    """Swing at hostile NPCs that come within `radius` tiles until none is left. Returns kills seen."""
    kills = 0
    for _ in range(max_rounds):
        near = hostiles(radius)
        if not near:
            break
        w = best_weapon()
        if w and (tb.me().held or {}).get("slot") != w.slot:
            tb.select(w.slot if w.slot < 50 else w.name)
        p = tb.me()
        n = min(near, key=lambda n: abs(n.x - p.x) + abs(n.y - p.y))
        if abs(n.x - p.x) > 1.8:
            tb.hold("right" if n.x > p.x else "left", 6)
        r = tb.swing_at(n)
        if r is None:
            kills += 1
    return kills


def collect(radius=14, names=None, timeout=20):
    """Walk over visible dropped items (optionally only some names)."""
    got = 0
    for _ in range(12):
        items = [i for i in tb.items_near(radius) if names is None or i.name in names]
        if not items:
            break
        p = tb.me()
        it = min(items, key=lambda i: abs(i.x - p.x) + abs(i.y - p.y))
        tb.goto(int(it.x), int(it.y), near=1, timeout=timeout / 3, dig=False, place=False)
        tb.sleep(10)
        got += 1
    return got


def tree_bases(radius=60):
    """Lowest trunk tile of each revealed tree column that stands on a solid tile, nearest first."""
    cells = tb.find_tiles("Trees", radius=radius, limit=500)
    cols = {}
    for x, y in cells:
        if x not in cols or y > cols[x]:
            cols[x] = y
    bases = []
    p = tb.me()
    for x, y in cols.items():
        g = tb.tiles(x, y - 4, x, y + 1)
        if g.solid(x, y + 1) and all(g.kind(x, yy) == "Trees" for yy in range(y - 3, y + 1)):
            bases.append((x, y))
    bases.sort(key=lambda b: abs(b[0] - p.x) + 2 * abs(b[1] - p.y))
    return bases


def chop(base):
    x, y = base
    for side in (-2, 2, -3, 3):
        if tb.goto(x + side, y, near=1, timeout=20, dig=False, place=False):
            break
    else:
        return False
    fight()
    ok = tb.mine(x, y)
    tb.sleep(30)
    collect(radius=16, names={"Wood", "Acorn"})
    return ok


def gather_wood(n, radius=80, max_trees=25):
    for _ in range(max_trees):
        if tb.count("Wood") >= n:
            return True
        bases = tree_bases(radius)
        if not bases:
            p = tb.me()
            tb.goto(int(p.x) + 25, int(p.foot_y), near=4, timeout=15, dig=False, place=False)
            continue
        fight()
        chop(bases[0])
        say("wood", tb.count("Wood"))
    return tb.count("Wood") >= n


def flat_spots(width=3, height=3, radius=8):
    """[(x, y)] nearest first: `width` solid floor cells at row y+1 and empty cells x..x+width-1, rows
    y-height+1..y."""
    p = tb.me()
    g = tb.tiles(p.tile_x - radius, p.foot_y - radius, p.tile_x + radius, p.foot_y + radius)
    found = []
    for y in range(p.foot_y - radius + height, p.foot_y + radius):
        for x in range(p.tile_x - radius, p.tile_x + radius - width):
            if all(g.solid(xx, y + 1) for xx in range(x, x + width)) and all(
                    g.empty(xx, yy) and g.kind(xx, yy) == "Empty" for xx in range(x, x + width) for yy in range(y - height + 1, y + 1)):
                found.append((abs(x + width / 2 - p.x) + abs(y - p.foot_y), x, y))
    return [(x, y) for _, x, y in sorted(found)]


def place_station(item, width, height):
    """Place a crafting station on flat ground near the player; returns the placed tile (x, y)."""
    tried = []
    for x, y in flat_spots(width, height)[:6]:
        p = tb.me()
        if abs(x - p.x) > 3 or abs(y - p.foot_y) > 2:
            tb.goto(x + width // 2, y, near=2, timeout=10, dig=False, place=False)
        tb.events()
        for dx in range(width):
            tb.place(item, x + dx, y)
            placed = [e for e in tb.events() if e.event == "placed"]
            if placed:
                return placed[-1].x, placed[-1].y
        tried.append((x, y))
    raise tb.TbError(f"could not place {item}; tried {tried}")


def light_here(reserve=3):
    """Place a torch at the player's feet cell if the area is dark and torches are available."""
    if tb.count("Torch") <= reserve:
        return False
    p = tb.me()
    for x in (p.tile_x, p.tile_x - 1, p.tile_x + 1):
        if tb.place("Torch", x, p.foot_y - 1):
            return True
    return False
