"""tb: the TerrariaBench programmatic-track bot library (API contract tb-api-1.0, draft; see CONTRACT.md).

Coordinates are tiles (1 tile = 16 px); x grows right, y grows DOWN. Time is game updates ("ticks", 60 per second).
Every action goes through the player's own controls or the game's real item-use / crafting / equip / chest code.
World reads only return what the player has seen: tiles revealed on its map or lit on screen, NPCs and dropped items
on screen. Errors the game reports raise tb.TbError.
"""
import json
import math
import os
import sys
import time as _time

from ._rpc import TbError, call
from .grid import Cell, Grid

API_VERSION = "tb-api-1.0"
TICKS_PER_SECOND = 60
__all__ = ["me", "inventory", "time", "world", "tiles", "find_tiles", "npcs", "items_near", "events", "recipes", "chest",
           "hold", "walk", "jump", "stop", "sleep", "face", "goto", "path_to", "select", "use_at", "mine", "place",
           "swing_at", "craft", "equip", "open_chest", "take", "put", "close_chest", "screenshot", "log", "store",
           "count", "has", "TbError", "Grid", "Cell", "API_VERSION"]


class Obj(dict):
    """dict with attribute access: me().x == me()["x"]."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k) from None


def _obj(v):
    if isinstance(v, dict):
        return Obj({k: _obj(x) for k, x in v.items()})
    if isinstance(v, list):
        return [_obj(x) for x in v]
    return v


# ---------------------------------------------------------------- read
def me():
    """Player state: x, y (centre, tiles), tile_x, foot_y (row the feet are in), left, top, width, height, vx, vy
    (px/tick), on_ground, dir (-1/1), fall_tiles, life, life_max, mana, mana_max, defense, dead, respawn_ticks, breath,
    wet, lava, immune_ticks, potion_sickness_ticks, held (item or None), selected_slot, item_busy_ticks, reach_tiles
    [x, y], buffs, armor, accessories, layer, biomes, stations_near, chest_open, inventory_open, spawn, tick."""
    return _obj(call("me"))


def inventory():
    """Items in slots 0-57 (0-9 hotbar, 10-49 main, 50-53 coins, 54-57 ammo): slot, name, type, stack, pick, axe,
    hammer, damage, place_tile (tile name or None), place_solid (True if placing it makes a full solid block),
    place_wall, consumable, heal_life, use_time, use_animation, tile_boost, auto_reuse, ammo, armor, accessory,
    max_stack."""
    return _obj(call("inventory"))


def count(item):
    """Total stack of an item (by name, case-insensitive) in the inventory."""
    return sum(i.stack for i in inventory() if i.name.lower() == item.lower())


def has(item, n=1):
    return count(item) >= n


def time():
    """day, clock ("HH:MM"), ticks_into_phase, phase_length, moon_phase, blood_moon, eclipse, game_updates."""
    return _obj(call("time"))


def world():
    """api, size [w, h] in tiles, spawn [x, y], screen_tiles [w, h], hardmode, eye_of_cthulhu_defeated, difficulty."""
    return _obj(call("world"))


def tiles(x0, y0, x1, y1):
    """Grid of the rectangle (inclusive corners, at most 40000 cells). Unrevealed cells are Unknown."""
    return Grid.from_reply(call("tiles", x0=int(x0), y0=int(y0), x1=int(x1), y1=int(y1)))


def find_tiles(kind, radius=60, limit=50):
    """[(x, y)] of revealed tiles of a kind (TileID name such as 'Trees', 'Copper', 'Tin', 'Iron', 'Lead', 'Stone',
    'Containers', 'Heart', 'DemonAltar', 'WorkBenches') within radius tiles, nearest first."""
    return [tuple(p) for p in call("find_tiles", kind=str(kind), radius=int(radius), limit=int(limit))]


def npcs(radius=100):
    """Visible NPCs: id, name, type, x, y (centre), width, height, life, life_max, hostile, boss, town."""
    return _obj(call("npcs", radius=radius))


def items_near(radius=100):
    """Visible dropped items: name, type, stack, x, y."""
    return _obj(call("items", radius=radius))


_last_event = 0


def events(since=None):
    """Game events after `since` (default: since the previous events() call in this program): hurt, death, respawn,
    killed, pickup, tile_broken, placed, crafted, boss_awoke, dawn, dusk. Each has seq, event, tick."""
    global _last_event
    out = _obj(call("events", since=_last_event if since is None else since))
    if out:
        _last_event = max(_last_event, out[-1]["seq"])
    return out


def recipes(item=None, available=True):
    """Recipes craftable now (ingredients in inventory, stations in range); available=False with item= lists every
    recipe for that item. Each: item, stack, ingredients [[name, n]], stations, conditions."""
    return _obj(call("recipes", item=item, available=available))


def chest():
    """Contents of the chest the player has open (index, items), or None."""
    return _obj(call("chest"))


# ---------------------------------------------------------------- move
def hold(keys, ticks=15, aim=None):
    """Hold keys for `ticks` game updates, then release. keys: any of left, right, up, down, jump, use, use_tile,
    quick_heal, quick_mana, quick_buff, hook. aim: cursor (x, y) in tiles (fractional; tile centre is x+0.5).
    Returns a short state (x, y, vx, vy, life, dead, tick, ticks)."""
    keys = [keys] if isinstance(keys, str) else list(keys)
    args = {"keys": keys, "ticks": int(ticks)}
    if aim is not None:
        args["aim"] = [float(aim[0]), float(aim[1])]
    return _obj(call("input", **args))


def walk(direction, ticks=15):
    """direction: -1/'left' or 1/'right'."""
    return hold("left" if direction in (-1, "left") else "right", ticks)


def jump(ticks=15, direction=0):
    """Jump (holding jump longer = higher, up to ~15 ticks), optionally moving left (-1) or right (1)."""
    keys = ["jump"] + (["left"] if direction < 0 else ["right"] if direction > 0 else [])
    return hold(keys, ticks)


def stop():
    """Release every key now."""
    return _obj(call("stop"))


def sleep(ticks):
    """Do nothing for `ticks` game updates."""
    return _obj(call("wait", ticks=int(ticks)))


def face(x):
    """Turn toward column x (one tick of movement input)."""
    p = me()
    return hold("left" if x < p.x else "right", 1)


def goto(x, y, dig=True, place=True, near=0, timeout=60.0):
    """Walk to stand with feet in row y at column x (within `near` tiles) using the pathfinder: walking, auto step-up,
    jumps, falls, platforms, ropes, and, if allowed, digging through blocks (dig) and pillaring up (place). Returns
    True on arrival, False if no path or not reached in `timeout` wall seconds. See tb.path for capabilities."""
    from . import path
    return path.goto(x, y, dig=dig, place=place, near=near, timeout=timeout)


def path_to(x, y, dig=True, place=True, near=0):
    """Plan only: the list of path steps the pathfinder would take (or None)."""
    from . import path
    return path.plan_to(x, y, dig=dig, place=place, near=near)


# ---------------------------------------------------------------- use
def _close_ui():
    p = me()
    if p.chest_open or p.inventory_open:
        close_chest()


def select(item):
    """Hold an item: name (case-insensitive) or inventory slot number. Items outside the hotbar move to slot 9."""
    args = {"slot": item} if isinstance(item, int) else {"item": str(item)}
    return _obj(call("select", **args))


def use_at(x, y, ticks=None):
    """Use the held item with the cursor on tile (x, y) for `ticks` (default: one use animation). Mining, chopping,
    placing, swinging and consuming all follow the game's own rules (reach, tool power, placement rules)."""
    _close_ui()
    if ticks is None:
        h = me().held
        ticks = (h.use_animation if h else 15) or 15
    return hold("use", ticks, aim=(x + 0.5, y + 0.5))


def _tool_for(kind):
    inv = inventory()
    key = "axe" if kind in ("Trees", "PalmTree", "MushroomTrees", "Cactus", "VanityTreeSakura", "VanityTreeYellowWillow",
                            "TreeAsh") else "hammer" if kind in ("DemonAltar",) else "pick"
    tools = [i for i in inv if i.get(key, 0) > 0]
    return max(tools, key=lambda i: i[key]) if tools else None


def _tile(x, y):
    return tiles(x, y, x, y).at(x, y)


def mine(x, y, timeout_ticks=600):
    """Break the tile at (x, y) with the best pickaxe (axe for trees, hammer for altars) in the inventory.
    Must be within reach. Returns True when the tile is gone (for a tree: when the trunk above it has fallen; a
    stump may stay). False if it did not break within timeout_ticks or the player died."""
    cell = _tile(x, y)
    if not cell.known:
        raise TbError(f"mine({x}, {y}): tile not revealed")
    if cell.type < 0:
        return True
    tree = cell.kind == "Trees"

    def done():
        if _tile(x, y).type < 0:
            return True
        return tree and _tile(x, y - 1).kind != "Trees"

    if tree and done():
        return True
    tool = _tool_for(cell.kind)
    if tool is None:
        raise TbError(f"mine({x}, {y}): no suitable tool for {cell.kind}")
    held = me().held
    if not held or held.slot != tool.slot:
        select(tool.slot if tool.slot < 50 else tool.name)
    spent = 0
    while spent < timeout_ticks:
        step = max(tool.use_animation or 15, 10)
        use_at(x, y, step)
        spent += step
        if done():
            return True
        if me().dead:
            return False
    return False


def place(item, x, y, ticks=None):
    """Place a block/furniture/torch item at (x, y) (bottom-left/anchor tile for furniture). True if a tile appears."""
    select(item)
    for _ in range(3):
        use_at(x, y, ticks)
        if _tile(x, y).type >= 0:
            return True
    return _tile(x, y).type >= 0


def swing_at(npc):
    """Aim at an NPC (dict from npcs() or its id) and use the held weapon once. Returns the NPC's new state or None
    if it is gone/not visible."""
    nid = npc["id"] if isinstance(npc, dict) else int(npc)
    target = next((n for n in npcs() if n.id == nid), None)
    if target is None:
        return None
    h = me().held
    _close_ui()
    hold("use", (h.use_animation if h else 20) or 20, aim=(target.x, target.y))
    return next((n for n in npcs() if n.id == nid), None)


# ---------------------------------------------------------------- craft & containers
def craft(item, n=1):
    """Craft `item` n times with the real recipe rules (ingredients in inventory, required stations in range)."""
    return _obj(call("craft", item=str(item), n=int(n)))


def equip(item):
    """Equip armour or an accessory from the inventory (same as right-clicking it in the inventory)."""
    args = {"slot": item} if isinstance(item, int) else {"item": str(item)}
    return _obj(call("equip", **args))


def open_chest(x, y):
    """Open the chest whose tile is at (x, y) by interacting with it (must be within reach). Returns chest()."""
    hold("use_tile", 2, aim=(x + 0.5, y + 0.5))
    sleep(2)
    c = chest()
    if c is None:
        raise TbError(f"open_chest({x}, {y}): no chest opened (out of reach or not a chest)")
    return c


def take(item=None, n=None):
    """Move items from the open chest to the inventory: one item by name (n of them, default all) or, with no item,
    everything (Loot All)."""
    args = {} if item is None else {"item": str(item)}
    if n is not None:
        args["n"] = int(n)
    return _obj(call("take", **args))


def put(item, n=None):
    """Move items by name from the inventory into the open chest."""
    args = {"item": str(item)}
    if n is not None:
        args["n"] = int(n)
    return _obj(call("put", **args))


def close_chest():
    """Close the chest / inventory UI (Escape)."""
    return _obj(call("close_chest"))


# ---------------------------------------------------------------- meta
def screenshot():
    """Save a screenshot of the game window into the workspace; returns its path (the agent sees the latest one)."""
    return call("screenshot")


def log(*parts):
    """Print a line to the program output (same as print, flushed)."""
    print(*parts, flush=True)


class _Store(dict):
    """Persistent key-value store shared by all programs of a run (JSON values). Writes through on every change."""

    def __init__(self, path):
        self._path = path
        data = {}
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
        super().__init__(data)

    def _save(self):
        if self._path:
            tmp = self._path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self, f)
            os.replace(tmp, self._path)

    def __setitem__(self, k, v):
        json.dumps(v)  # values must be JSON-serialisable
        super().__setitem__(k, v)
        self._save()

    def __delitem__(self, k):
        super().__delitem__(k)
        self._save()

    def update(self, *a, **kw):
        super().update(*a, **kw)
        self._save()

    def pop(self, *a):
        v = super().pop(*a)
        self._save()
        return v

    def setdefault(self, k, v=None):
        if k not in self:
            self[k] = v
        return self[k]


store = _Store(os.environ.get("TB_STORE", "store.json"))
