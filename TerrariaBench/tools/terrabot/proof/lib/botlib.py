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
    """Swing at hostile NPCs that come within `radius` tiles until none is left (gives up on one that 8 swings do
    not hurt, e.g. behind a wall). Returns kills seen."""
    kills, swings, ignored = 0, {}, set()
    for _ in range(max_rounds):
        near = [n for n in hostiles(radius) if n.id not in ignored]
        if not near:
            break
        p = tb.me()
        if p.dead:
            break
        w = best_weapon()
        if w and (p.held or {}).get("slot") != w.slot:
            try:
                tb.select(w.slot if w.slot < 50 else w.name)
            except tb.TbError:
                tb.sleep(5)
        n = min(near, key=lambda n: abs(n.x - p.x) + abs(n.y - p.y))
        if abs(n.x - p.x) > 1.8:
            tb.hold("right" if n.x > p.x else "left", 6)
        r = tb.swing_at(n)
        if r is None:
            kills += 1
        elif r.life >= n.life:
            swings[n.id] = swings.get(n.id, 0) + 1
            if swings[n.id] >= 8:
                ignored.add(n.id)
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


def player_cells(margin=0):
    p = tb.me()
    x0, x1 = int(p.left) - margin, int(p.left + p.width - 0.01) + margin
    y0, y1 = int(p.top) - margin, int(p.top + p.height - 0.01) + margin
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


def flat_spots(width=3, height=3, radius=8):
    """[(x, y)] nearest first: `width` solid floor cells at row y+1 and empty cells x..x+width-1, rows
    y-height+1..y, not overlapping the player's body."""
    p = tb.me()
    body = player_cells()
    g = tb.tiles(p.tile_x - radius, p.foot_y - radius, p.tile_x + radius, p.foot_y + radius)
    found = []
    for y in range(p.foot_y - radius + height, p.foot_y + radius):
        for x in range(p.tile_x - radius, p.tile_x + radius - width):
            cells = [(xx, yy) for xx in range(x, x + width) for yy in range(y - height + 1, y + 1)]
            if all(g.solid(xx, y + 1) for xx in range(x, x + width)) and all(
                    g.empty(xx, yy) and (g.kind(xx, yy) == "Empty" or "Plants" in g.kind(xx, yy)) for xx, yy in cells) \
                    and not body & set(cells):
                found.append((abs(x + width / 2 - p.x) + abs(y - p.foot_y), x, y))
    return [(x, y) for _, x, y in sorted(found)]


def wait_alive():
    """If dead, wait for the respawn. True if the player was dead."""
    p = tb.me()
    if p.dead:
        tb.sleep(p.respawn_ticks + 30)
        say("respawned at", tb.me().tile_x, tb.me().foot_y)
        return True
    return False


def place_station(item, width, height):
    """Place a crafting station on flat ground near the player; returns the placed tile (x, y). Walks around to
    find flat ground if there is none nearby."""
    tried = []
    for attempt in range(5):
        wait_alive()
        fight()
        spots = flat_spots(width, height, radius=8) or flat_spots(width, height, radius=16)
        for x, y in [s for s in spots if s not in tried][:5]:
            p = tb.me()
            if abs(x + width / 2 - p.x) > 4 or abs(y - p.foot_y) > 2:
                tb.goto(x + width + 1 if p.x > x else x - 2, y, near=1, timeout=10, dig=False, place=False)
            tb.events()
            for dx in range(-1, width + 1):
                tb.place(item, x + dx, y)
                placed = [e for e in tb.events() if e.event == "placed" and e.get("item") == item]
                if placed:
                    return placed[-1].x, placed[-1].y
            tried.append((x, y))
        p = tb.me()
        tb.goto(p.tile_x + (12 if attempt % 2 == 0 else -24), p.foot_y, near=4, timeout=10, dig=False, place=False)
    p = tb.me()
    say("place_station failed near", p.tile_x, p.foot_y, "held", (p.held or {}).get("name"), "dead", p.dead)
    say(tb.tiles(p.tile_x - 10, p.foot_y - 5, p.tile_x + 10, p.foot_y + 2).render({(p.tile_x, p.foot_y): "@"}))
    raise tb.TbError(f"could not place {item}; tried {tried}")


def pick_up_station(x, y, item, kind):
    """Mine a placed station at (x, y) and collect its item; True if one more is in the inventory."""
    have = tb.count(item)
    for _ in range(3):
        if (x, y) in tb.find_tiles(kind, radius=10, limit=10):
            p = tb.me()
            if abs(x - p.x) > 3 or abs(y - p.foot_y) > 2:
                tb.goto(x, y, near=2, timeout=10, dig=False, place=False)
            try:
                tb.mine(x, y)
            except tb.TbError as e:
                say("pick up", item, e)
        tb.sleep(20)
        collect(radius=8, names={item})
        if tb.count(item) > have:
            return True
    return False


def light_here(reserve=2):
    """Place a torch next to the player's head if torches are available."""
    if tb.count("Torch") <= reserve:
        return False
    p = tb.me()
    for y in (p.foot_y - 2, p.foot_y - 1):  # head row first: 2-tall stations still fit under a torch
        for x in (p.tile_x, p.tile_x - 1, p.tile_x + 1):
            if tb.tiles(x, y, x, y).at(x, y).kind == "Torches":
                return True
            if tb.place("Torch", x, y) and tb.tiles(x, y, x, y).at(x, y).kind == "Torches":
                return True
    return False


def metal_ore():
    """(metal, ore equivalent) of the better anvil metal, Iron or Lead: ore + 3 per bar."""
    best = max(("Iron", "Lead"), key=lambda m: tb.count(f"{m} Ore") + 3 * tb.count(f"{m} Bar"))
    return best, tb.count(f"{best} Ore") + 3 * tb.count(f"{best} Bar")


def clock_min():
    """Game clock in minutes after midnight."""
    h, m = tb.time().clock.split(":")
    return int(h) * 60 + int(m)


def recover(min_life=70, max_ticks=3600):
    """Fight what comes close and otherwise stand still until life is back to `min_life`."""
    spent = 0
    while tb.me().life < min_life and spent < max_ticks and not tb.me().dead:
        if hostiles(5):
            fight(radius=5, max_rounds=10)
        else:
            tb.sleep(60)
        spent += 60
    return tb.me().life


def make_torches(keep_wood=16):
    """Craft torches from all gel at a work bench (one in range, the carried one, or a new one from 10 wood),
    picking a placed bench up again. Returns the torch count."""
    if min(tb.count("Gel"), tb.count("Wood") - keep_wood) <= 0:
        return tb.count("Torch")
    bench = None
    if "WorkBenches" not in tb.me().stations_near:
        if not tb.count("Work Bench"):
            tb.craft("Work Bench")
        bench = place_station("Work Bench", 2, 2)
    n = min(tb.count("Gel"), tb.count("Wood") - keep_wood)
    if n > 0:
        tb.craft("Torch", n)
    if bench:
        say("bench picked up again:", pick_up_station(*bench, "Work Bench", "WorkBenches"))
    return tb.count("Torch")
