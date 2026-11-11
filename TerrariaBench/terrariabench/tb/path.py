"""tb.path: tile-grid pathfinder (pure A* planner) and the closed-loop executor behind tb.goto / tb.path_to.

Node (x, y)
    The player's body occupies the 2 columns x, x+1 and the 3 rows y-2..y (feet in row y) and stands on row y+1.
    The 20x42 px hitbox fits in 2x3 cells; at the node's canonical position the hitbox is centred on the boundary
    between columns x and x+1 (left = 16*x + 6 px, centre x = x + 1.0 tiles) with its bottom on the top of row y+1.
    node_of(me) = (floor((16*left - 6)/16 + 0.5), foot_y): the node whose canonical left edge is nearest to the
    player's (it may differ from the real one by up to 8 px; the 20 px hitbox then pokes up to 2 px into a
    neighbour column). On a rope the player is centred on the rope column r and node_of gives x = r.
Goal (gx, gy)
    A tile: column gx, feet row gy. A node is at distance max(dx, |y - gy|) from it, where dx = 0 if gx is one of
    the node's columns x, x+1, else the column distance to the nearer of them. Reached when distance <= near.

Step kinds (Step.kind; Step.frm / Step.to are nodes, Step.cost in game ticks):
    walk    move one column on the same row (also across 1-wide holes: one of the two columns always supports)
    step    auto step-up onto a 1-row ledge while walking (the cell in front of the feet is solid)
    jump    jump arc: up to 4 rows up / 6 down, up to 4 columns sideways, or straight up through platforms;
            Step.jump = (J, D, off): hold jump J ticks, start steering toward the target at tick D, start
            offset off px (-8 when jumping off a rope)
    fall    walk off an edge (frm.x != to.x) or let go at the bottom end of a rope (frm.x == to.x), fall to the
            first floor; up to 25 rows normally, deeper only at a large cost (fall damage)
    drop    hold down on a platform and fall through it to the first floor below
    climb   one row up/down a rope (Rope, Chain, VineRope, SilkRope, WebRope), or (frm.y == to.y) walk sideways
            off a ledge onto a rope hanging beside it and grab it
    door    walk one column through a closed door, opening it first (Step.doors)
    dig     walk / step-up / move down after mining Step.mine (solid or unrevealed cells) with the best pickaxe
    pillar  jump and place a block under the feet (Step.place) to rise one row; may mine Step.mine above first
    swim    walk off a bank into water and cross it at the surface (head above water) to the first dry standing
            node at most 4 rows above the surface, at most 20 columns away

Water: no node may have water in its head rows (y-2, y-1); water in the feet row is fine (shallow wading). Falls
    must not end with the head under water, jump arcs never cross water, and cells next to water or lava are never
    mined (they would flood the tunnel). Deep water is only crossed by `swim`.

Costs (ticks, roughly the time the move takes): walk 6, step 9, jump = simulated air time + 8, fall
    sqrt(80*rows) + 6 (+400 + 60/row beyond 25 rows), drop 10 + fall time, climb 8/row, door +30, mining +40 per
    cell, pillar 70 (+ mining), swim 150 + 20/column. Heuristic: max(columns*16/3, rows up*16/5.01,
    rows down*16/10) (top run / jump / fall speeds), which no move beats, so A* is admissible.
"""
from __future__ import annotations

import heapq
import itertools
import math
import sys
import time as _time
from dataclasses import dataclass
from typing import Optional

from .grid import HONEY, LAVA, PLATFORM, SOLID, UNKNOWN, WATER

tb = sys.modules[__package__]  # the tb package (always initialised before this submodule is imported)

CAPABILITIES = """tb.goto / tb.path_to pathfinder (tb.path):
DOES
- A* over 2x3-cell player nodes on the revealed tile grid (tb.tiles), costs in game ticks, admissible heuristic.
- walk, auto step-up over 1-row ledges, walking across 1-wide holes.
- jumps: up to 4 rows up, up to 6 rows down, up to 4 columns sideways (gaps up to ~3 tiles wide), checked
  against a simulated vanilla jump arc (no accessories: run 3 px/tick, accel 0.08, jump 5.01 px/tick, gravity
  0.4, calibrated so a 15-tick jump hold rises ~5.25 tiles as measured in game); straight-up jumps through
  platforms onto platforms; no landing on a platform crossed mid-arc.
- falls off edges to the first floor (<= 25 rows; deeper only if nothing else works, at a high cost), dropping
  through platforms (hold down), ropes: grabbing one (from the floor under it or by walking off a ledge onto it),
  climbing up/down, jumping off it, or falling off its bottom end. The player is assumed to hang centred on the
  rope column with the same body size; a rope right next to a wall may not be usable.
- closed doors: opened with use_tile and walked through (walk moves only).
- dig=True: mines solid or unrevealed cells in the way (sideways, diagonal step-up, straight down) with the best
  pickaxe via tb.mine; cells it fails to mine are remembered for the rest of the goto and avoided on replanning.
  Unrevealed cells count as solid: standable, and passable only by digging.
- place=True: pillars straight up by jumping and placing a solid block (inventory items with place_solid: dirt,
  stone, wood, bricks...; sand-like blocks and ores last) under the feet, one row per block, up to the number of
  such blocks in the inventory.
- lava is never entered. Water: the head (top two body rows) is never planned under water; wading with only the
  feet in water is fine; ponds up to 20 columns wide are crossed by a surface swim (walk in, tap jump while
  wet to keep the head up, climb out onto a bank at most 4 rows above the surface); cells next to water or lava
  are never mined.
- closed-loop execution: short input bursts, aligns before jumps/climbs/pillars, keeps running across
  consecutive walk steps, replans after any deviation, failure or stall (~1.5 s without progress), up to a budget;
  far goals (window > 40000 cells) are approached by planning to the nearest reachable point and replanning.
- returns False on timeout, no path, death or exhausted replans; releases all keys on exit.
DOES NOT
- dive, swim through underwater passages, or manage breath beyond keeping the head up while surface swimming;
  use grappling hooks, mounts, wings, rocket boots or any movement accessory.
- place ropes or platforms, build bridges over gaps, or place blocks anywhere except straight under the feet.
- dig while jumping, dig diagonally downward, or dig through tiles it knows need high pickaxe power (dungeon
  and lihzahrd bricks, altars, ebonstone/crimstone/pearlstone, hellstone, obsidian, meteorite, hardmode ores).
- treat half blocks / slopes specially (they count as full solid blocks), or stand on solid-top furniture
  (tables, work benches) unless the tile carries the PLATFORM flag.
- avoid enemies, traps, falling sand, or liquid that reaches a dug tunnel from further away; model fall damage
  beyond 'more than 25 rows hurts'; account for tiles it placed or mined earlier in the same plan.
- see unrevealed tiles: plans assume they are solid and replan as they are revealed.
"""

# ---------------------------------------------------------------- physics (vanilla player, no accessories)
RUN_MAX, ACC, SLOW_GROUND, SLOW_AIR = 3.0, 0.08, 0.2, 0.1
GRAV, MAX_FALL_V, JUMP_V, JUMP_TICKS = 0.4, 10.0, 5.01, 15
W_PX, H_PX = 20, 42
SAFE_FALL = 25

# ---------------------------------------------------------------- costs (ticks)
WALK, STEP, CLIMB, PILLAR, DOOR, MINE = 6.0, 9.0, 8.0, 70.0, 30.0, 40.0
JUMP_EXTRA, DROP_EXTRA, DEEP_FALL, DEEP_FALL_ROW = 8.0, 10.0, 400.0, 60.0
MAX_FALL_ROWS = 150
MAX_UP, MAX_DOWN, MAX_SIDE = 4, 6, 4
SWIM, SWIM_COL, MAX_SWIM_COLS = 150.0, 20.0, 20  # surface swim: base cost, per column, widest crossing
# jump model: a J-tick hold keeps vy = -5.01 (+0.4 gravity in the same tick) for J - JUMP_LAG ticks, then gravity;
# calibrated on the real game: hold 15 rises 84 px = 5.25 tiles (measured 5.22)
JUMP_LAG = 2

# ---------------------------------------------------------------- cell classes
AIR, PLAT, SOLID_C, UNK, LAVA_C, DOOR_C, WATER_C, ROPE_C, HARD, OUT = range(10)
PASS = frozenset((AIR, PLAT, WATER_C, ROPE_C))          # body may occupy without digging
JUMPABLE = frozenset((AIR, PLAT, ROPE_C))               # jump arcs may cross
STAND = frozenset((PLAT, SOLID_C, UNK, DOOR_C, HARD))   # supports feet
DIGGABLE = frozenset((SOLID_C, UNK))

ROPE_KINDS = frozenset(("Rope", "Chain", "VineRope", "SilkRope", "WebRope"))
DOOR_KINDS = frozenset(("ClosedDoor", "TallGateClosed"))
HARD_KINDS = frozenset((
    "BlueDungeonBrick", "GreenDungeonBrick", "PinkDungeonBrick", "LihzahrdBrick", "DemonAltar", "LihzahrdAltar",
    "Ebonstone", "Crimstone", "Pearlstone", "Hellstone", "Obsidian", "Meteorite", "Demonite", "Crimtane",
    "Cobalt", "Palladium", "Mythril", "Orichalcum", "Adamantite", "Titanium", "Chlorophyte", "Containers",
    "Containers2", "Heart", "ShadowOrbs"))


@dataclass(frozen=True)
class Step:
    kind: str
    frm: tuple
    to: tuple
    cost: float
    mine: tuple = ()
    doors: tuple = ()
    place: Optional[tuple] = None
    jump: Optional[tuple] = None


def node_of(p):
    """Node (x, y) of a me() reading: x = floor((16*left - 6)/16 + 0.5), y = foot_y. See module docstring."""
    return int(math.floor((p["left"] * 16 - 6) / 16 + 0.5)), int(p["foot_y"])


def _sign(v):
    return (v > 0) - (v < 0)


def _hstep(v, d, air):
    """One tick of horizontal velocity: d = -1/0/1 input."""
    if d:
        if v * d < 0:
            v += d * SLOW_GROUND
        v += d * ACC
        return max(-RUN_MAX, min(RUN_MAX, v))
    s = SLOW_AIR if air else SLOW_GROUND
    return 0.0 if abs(v) <= s else v - s * _sign(v)


def _hcontrol(err, v):
    """Steering law shared by the jump simulation and the executor: err = target - position (px), v px/tick."""
    if abs(err) < 1.0 and abs(v) < 0.3:
        return 0
    if v * err > 0 and v * v / (2 * (SLOW_GROUND + ACC)) >= abs(err) - 0.5:
        return -_sign(v)
    if abs(err) >= 1.0:
        return _sign(err)
    return 0


def _fall_cost(rows):
    c = math.sqrt(80.0 * rows)
    if rows > SAFE_FALL:
        c += DEEP_FALL + DEEP_FALL_ROW * (rows - SAFE_FALL)
    return c


# ---------------------------------------------------------------- jump templates
JUMP_HOLDS = (JUMP_TICKS, 12, 9, 6, 3)  # jump-key hold lengths tried (shorter = lower arc)
_TEMPLATES = None


def _box(x, b):
    """Cells (relative to the start node) overlapped by a hitbox with left x px and bottom b px."""
    c0, c1 = math.floor(x / 16), math.floor((x + W_PX - 1e-6) / 16)
    r0, r1 = math.floor((b - H_PX) / 16), math.floor((b - 1e-6) / 16)
    return [(c, r) for c in range(c0, c1 + 1) for r in range(r0, r1 + 1)]


def _cols(x):
    return range(math.floor(x / 16), math.floor((x + W_PX - 1e-6) / 16) + 1)


def _sim(J, D, x, tx, sgn):
    """Simulate one jump (no obstacles); yield (dy, ticks, swept cells, catch cells) for every landing row."""
    v = vy = 0.0
    b = 16.0
    cells, catch = set(_box(x, b)), set()
    for t in range(240):
        if t < J:
            d = sgn if D == 0 else 0
        elif t < D:
            d = 0
        else:
            d = _hcontrol(tx - x, v)
        v = _hstep(v, d, True)
        vy = -JUMP_V + GRAV if t < max(1, J - JUMP_LAG) else min(vy + GRAV, MAX_FALL_V)
        nx, nb = x + v, b + vy
        if vy > 0:
            r = math.floor(b / 16) + 1
            while r * 16 <= nb:
                dy = r - 1
                if -MAX_UP <= dy <= MAX_DOWN and abs(nx - tx) <= 4:
                    yield dy, t + 1, frozenset(cells.union(_box(nx, r * 16))), frozenset(catch)
                catch.update((c, r) for c in _cols(nx))
                r += 1
        x, b = nx, nb
        cells.update(_box(x, b))
        if b > (MAX_DOWN + 2) * 16:
            return


def _build(off):
    raw = {}
    sx = 6.0 + off
    for dx in range(-MAX_SIDE, MAX_SIDE + 1):
        tx = 6.0 + 16 * dx
        sgn = _sign(tx - sx)
        for J in JUMP_HOLDS:
            for D in ((0, J, J + 8, J + 16) if sgn else (J,)):
                for dy, T, sweep, catch in _sim(J, D, sx, tx, sgn):
                    if (dx, dy) != (0, 0) or off:
                        raw.setdefault((dx, dy), []).append((T, J, D, sweep, catch))
    out = {}
    for key, cands in raw.items():
        cands.sort(key=lambda c: (c[0], len(c[3])))
        kept = []
        for c in cands:
            if not any(k[3] <= c[3] and k[4] <= c[4] for k in kept):
                kept.append(c)
        out[key] = [(T, J, D, tuple(sw), tuple(ca)) for T, J, D, sw, ca in kept[:8]]
    return out


def _templates():
    global _TEMPLATES
    if _TEMPLATES is None:
        _TEMPLATES = {off: _build(off) for off in (0, -8)}
    return _TEMPLATES


# ---------------------------------------------------------------- planner
class _Map:
    def __init__(self, grid, dig, no_dig, start):
        self.x0, self.y0, self.w, self.h = grid.x0, grid.y0, grid.w, grid.h
        self.dig = dig
        self.no_dig = {tuple(c) for c in no_dig}
        self.start = start
        names = grid.names
        codes = bytearray(self.w * self.h)
        for k, (t, f) in enumerate(zip(grid.types, grid.flags)):
            if t == UNKNOWN:
                c = UNK
            elif f & SOLID:
                n = names.get(t, "")
                c = DOOR_C if n in DOOR_KINDS else HARD if n in HARD_KINDS else SOLID_C
            elif f & LAVA:
                c = LAVA_C
            elif f & PLATFORM:
                c = PLAT
            elif t >= 0 and names.get(t, "") in ROPE_KINDS:
                c = ROPE_C
            elif f & (WATER | HONEY):
                c = WATER_C
            else:
                c = AIR
            codes[k] = c
        self.codes = codes
        self._clear, self._sup = {}, {}

    def code(self, x, y):
        x -= self.x0
        y -= self.y0
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.codes[y * self.w + x]
        return OUT

    def clear(self, x, y):
        """Body cells passable without digging, and the head (rows y-2, y-1) out of water."""
        k = (x, y)
        v = self._clear.get(k)
        if v is None:
            v = all(self.code(x + c, y - r) in PASS for c in (0, 1) for r in (0, 1, 2)) and \
                self.dry(((x, y - 1), (x + 1, y - 1), (x, y - 2), (x + 1, y - 2)))
            self._clear[k] = v
        return v

    def dry(self, cells):
        return all(self.code(*c) != WATER_C for c in cells)

    def near_liquid(self, c):
        x, y = c
        return any(self.code(x + i, y + j) in (WATER_C, LAVA_C) for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1)))

    def rope(self, x, y):
        return self.code(x, y - 1) == ROPE_C

    def supported(self, x, y, pc=None):
        if pc is not None and x <= pc <= x + 1:
            return True
        k = (x, y)
        v = self._sup.get(k)
        if v is None:
            v = self.code(x, y + 1) in STAND or self.code(x + 1, y + 1) in STAND
            if not v and k == self.start and not self.rope(x, y):
                v = True  # the caller says the player stands there (it only plans when on the ground/rope)
            self._sup[k] = v
        return v

    def classify(self, cells):
        mine, doors = [], []
        for c in cells:
            k = self.code(*c)
            if k in PASS:
                continue
            if k == DOOR_C:
                doors.append(c)
            elif self.dig and k in DIGGABLE and c not in self.no_dig and not self.near_liquid(c):
                mine.append(c)
            else:
                return None
        return ("dig" if mine else "door" if doors else "clear"), tuple(mine), tuple(doors)

    def descend(self, x, y):
        """First supported row at or below y for a body falling straight down from (x, y); None if the fall is
        blocked, too long, or ends with the head under water."""
        yy = y
        while not self.supported(x, yy):
            if yy - y >= MAX_FALL_ROWS:
                return None
            if self.code(x, yy + 1) not in PASS or self.code(x + 1, yy + 1) not in PASS:
                return None
            yy += 1
        return yy if self.dry(((x, yy - 1), (x + 1, yy - 1), (x, yy - 2), (x + 1, yy - 2))) else None

    def swim(self, x, y, d):
        """Surface crossing of a body of water: walk off (x, y) in direction d, fall onto the water surface, swim
        along it with the head above water and climb out onto the first dry standing node, at most 4 rows above the
        surface. Returns (exit node, columns swum) or None."""
        nx = x + d
        if not self.clear(nx, y) or self.supported(nx, y):
            return None
        s = y + 1
        while WATER_C not in (self.code(nx, s), self.code(nx + 1, s)):
            a, b = self.code(nx, s), self.code(nx + 1, s)
            if a not in PASS or b not in PASS or a in STAND or b in STAND or s - y > MAX_DOWN:
                return None
            s += 1
        c = nx
        for n in range(1, MAX_SWIM_COLS + 1):
            # swimming position: feet in the surface row s, head rows s-2, s-1 in the air
            if not all(self.code(c + i, s - j) in PASS for i in (0, 1) for j in (0, 1, 2)) or \
                    not self.dry(((c, s - 1), (c + 1, s - 1), (c, s - 2), (c + 1, s - 2))) or \
                    WATER_C not in (self.code(c, s), self.code(c + 1, s)):
                return None
            c2 = c + d
            for yy in range(s, s - 4, -1):
                if self.clear(c2, yy) and self.supported(c2, yy):
                    return (c2, yy), n
            c = c2
        return None


def _moves(m, s, can_pillar, tmpl):
    x, y, u, pc = s
    sup = m.supported(x, y, pc)
    rope = m.rope(x, y)
    here = (x, y)
    if sup:
        for d in (-1, 1):
            nx = x + d
            lead = x + 2 if d > 0 else x - 1
            r = m.classify(((lead, y - 2), (lead, y - 1), (lead, y)))
            if r is not None and m.dry(((lead, y - 2), (lead, y - 1))):
                status, mine, doors = r
                npc = pc if pc is not None and nx <= pc <= nx + 1 else None
                if m.supported(nx, y, npc):
                    kind = "walk" if status == "clear" else status
                    cost = WALK + MINE * len(mine) + (DOOR if doors else 0.0)
                    yield cost, (nx, y, u, npc), Step(kind, here, (nx, y), cost, mine, doors)
                elif status == "clear" and m.rope(nx, y):
                    # walk sideways onto a rope hanging next to the ledge and grab it (hold up)
                    yield WALK + CLIMB, (nx, y, u, None), Step("climb", here, (nx, y), WALK + CLIMB)
                elif status == "clear":
                    ty = m.descend(nx, y)
                    if ty is not None and ty > y:
                        cost = WALK + _fall_cost(ty - y)
                        yield cost, (nx, ty, u, None), Step("fall", here, (nx, ty), cost)
            if pc is None:
                sw = m.swim(x, y, d)
                if sw is not None:
                    (tx, ty), cols = sw
                    cost = SWIM + SWIM_COL * cols
                    yield cost, (tx, ty, u, None), Step("swim", here, (tx, ty), cost)
            # auto step-up onto a 1-row ledge
            front = (x + 2, y) if d > 0 else (x - 1, y)
            if m.code(*front) in (SOLID_C, HARD, UNK):
                cells = [(x, y - 3), (x + 1, y - 3), (lead, y - 3), (lead, y - 2), (lead, y - 1)]
                r = m.classify(cells)
                if r is not None and r[0] != "door" and m.dry(cells[:4]):
                    status, mine, _ = r
                    cost = STEP + MINE * len(mine)
                    yield cost, (nx, y - 1, u, None), Step("step" if status == "clear" else "dig", here,
                                                            (nx, y - 1), cost, mine)
        if pc is None:
            floor = ((x, y + 1), (x + 1, y + 1))
            codes = [m.code(*c) for c in floor]
            if PLAT in codes and all(c in PASS for c in codes):
                ty = m.descend(x, y + 1)
                if ty is not None:
                    cost = DROP_EXTRA + _fall_cost(ty - y)
                    yield cost, (x, ty, u, None), Step("drop", here, (x, ty), cost)
            elif m.dig and PLAT not in codes and any(c in DIGGABLE for c in codes):
                mine = tuple(c for c, k in zip(floor, codes) if k in DIGGABLE)
                if all(k in PASS or k in DIGGABLE for k in codes) and not m.no_dig.intersection(mine) and \
                        not any(m.near_liquid(c) for c in mine):
                    ty = m.descend(x, y + 1)
                    if ty is not None:
                        cost = DROP_EXTRA + MINE * len(mine) + _fall_cost(ty - y)
                        yield cost, (x, ty, u, None), Step("dig", here, (x, ty), cost, mine)
        if can_pillar:
            c = pc if pc is not None else (x if m.code(x, y + 1) in STAND else x + 1)
            if m.code(c, y) in (AIR, WATER_C):
                r = m.classify(((x, y - 3), (x + 1, y - 3)))
                if r is not None and r[0] != "door" and m.dry(((x, y - 3), (x + 1, y - 3))):
                    cost = PILLAR + MINE * len(r[1])
                    yield cost, (x, y - 1, u + 1, c), Step("pillar", here, (x, y - 1), cost, r[1], place=(c, y))
    if rope:
        if m.rope(x, y - 1) and m.clear(x, y - 1):
            yield CLIMB, (x, y - 1, u, None), Step("climb", here, (x, y - 1), CLIMB)
        if m.code(x, y) == ROPE_C:
            if m.clear(x, y + 1):
                yield CLIMB, (x, y + 1, u, None), Step("climb", here, (x, y + 1), CLIMB)
        elif not sup and m.clear(x, y):
            ty = m.descend(x, y)
            if ty is not None and ty > y:
                cost = DROP_EXTRA + _fall_cost(ty - y)
                yield cost, (x, ty, u, None), Step("fall", here, (x, ty), cost)
    if sup or rope:
        off = 0 if sup else -8
        for (dx, dy), cands in tmpl[off].items():
            if sup and dy == 0 and abs(dx) <= 1:
                continue
            nx, ny = x + dx, y + dy
            if not m.clear(nx, ny) or not m.supported(nx, ny):
                continue
            for T, J, D, sweep, catch in cands:
                if all(m.code(x + cx, y + cy) in JUMPABLE for cx, cy in sweep) and \
                        not any(m.code(x + cx, y + cy) in STAND for cx, cy in catch):
                    cost = T + JUMP_EXTRA
                    yield cost, (nx, ny, u, None), Step("jump", here, (nx, ny), cost, jump=(J, D, off))
                    break


def plan(grid, start, goal, *, dig=True, place=True, near=0, blocks=0, max_nodes=60000, no_dig=(),
         partial=False):
    """A* from node `start` (see node_of) to goal tile `goal` = (column, feet row) on `grid`.

    Returns the list of Steps ([] if already there) or None. dig: mine solid/unrevealed cells; place and
    blocks > 0: pillar up with at most `blocks` blocks; near: Chebyshev tolerance; no_dig: cells never to mine;
    partial: if the goal is unreachable, return the path to the explored node nearest to it (None if that is
    the start)."""
    sx, sy = int(start[0]), int(start[1])
    gx, gy = int(goal[0]), int(goal[1])
    m = _Map(grid, dig, no_dig, (sx, sy))
    tmpl = _templates()
    max_u = blocks if place else 0

    def dist(x, y):
        dx = 0 if x <= gx <= x + 1 else (gx - x - 1 if gx > x + 1 else x - gx)
        return max(dx, abs(y - gy))

    def h(x, y):
        dx = 0 if x <= gx <= x + 1 else (gx - x - 1 if gx > x + 1 else x - gx)
        dx = max(0, dx - near)
        up = max(0, y - gy - near)
        down = max(0, gy - y - near)
        return max(dx * 16 / RUN_MAX, up * 16 / JUMP_V, down * 16 / MAX_FALL_V)

    s0 = (sx, sy, 0, None)
    d0 = dist(sx, sy)
    if d0 <= near:
        return []
    cnt = itertools.count()
    openh = [(h(sx, sy), 0.0, next(cnt), s0)]
    best_g = {s0: 0.0}
    came = {}
    fronts = {(sx, sy, None): [(0.0, 0)]}
    best = (d0, 0.0, s0)
    expanded = 0
    while openh:
        _, g, _, s = heapq.heappop(openh)
        if g > best_g.get(s, math.inf):
            continue
        d = dist(s[0], s[1])
        if d <= near:
            return _path(came, s)
        if (d, g) < best[:2]:
            best = (d, g, s)
        expanded += 1
        if expanded > max_nodes:
            break
        for cost, t, step in _moves(m, s, s[2] < max_u, tmpl):
            ng = g + cost
            if ng >= best_g.get(t, math.inf):
                continue
            fr = fronts.setdefault((t[0], t[1], t[3]), [])
            if any(g2 <= ng and u2 <= t[2] for g2, u2 in fr):
                continue
            fr.append((ng, t[2]))
            best_g[t] = ng
            came[t] = (s, step)
            heapq.heappush(openh, (ng + h(t[0], t[1]), ng, next(cnt), t))
    if partial and best[2] != s0:
        return _path(came, best[2])
    return None


def _path(came, s):
    out = []
    while s in came:
        s, step = came[s]
        out.append(step)
    out.reverse()
    return out


# ---------------------------------------------------------------- blocks for pillaring
_WOODS = frozenset(("Wood", "Ebonwood", "Shadewood", "Pearlwood", "Rich Mahogany", "Boreal Wood", "Palm Wood",
                    "Ash Wood", "Dynasty Wood", "Spooky Wood"))
_BLOCK_PREF = ("Dirt Block", "Stone Block", "Mud Block", "Clay Block", "Ash Block", "Snow Block", "Ice Block")
_FALLING = frozenset(("Sand Block", "Ebonsand Block", "Crimsand Block", "Pearlsand Block", "Silt Block",
                      "Slush Block"))


def _is_block(it):
    """Placing the item creates a full solid block (inventory field place_solid)."""
    return bool(it.get("place_solid")) and it.get("stack", 0) > 0


def placeable_blocks(inv=None):
    """{name: count} of items whose placement makes a full solid block (place_solid: blocks, bricks, wood, ores...;
    never furniture, torches or platforms)."""
    out = {}
    for it in tb.inventory() if inv is None else inv:
        if _is_block(it):
            out[it["name"]] = out.get(it["name"], 0) + it["stack"]
    return out


def _pick_block(inv=None):
    blocks = placeable_blocks(inv)
    if not blocks:
        return None

    def rank(n):  # common blocks first; wood, then ores (valuable), then sand-like blocks (fall) last
        pref = _BLOCK_PREF.index(n) if n in _BLOCK_PREF else len(_BLOCK_PREF) + (1 if n in _WOODS else 0)
        return (n in _FALLING, n.endswith(" Ore"), pref, -blocks[n])
    return min(blocks, key=rank)


# ---------------------------------------------------------------- executor
MAX_FAILS = 15        # replans after failures/deviations per goto
STALL_TICKS = 90      # ~1.5 s without progress
GRID_CELLS = 40000
MARGIN = 12


class _Fail(Exception):
    """The step did not go as planned: replan from where the player is."""


class _Dead(Exception):
    pass


def _goal_dist(n, goal):
    x, y = n
    gx, gy = goal
    dx = 0 if x <= gx <= x + 1 else (gx - x - 1 if gx > x + 1 else x - gx)
    return max(dx, abs(y - gy))


def _key(d):
    return ["right"] if d > 0 else ["left"] if d < 0 else []


def _foot(yc):
    """foot_y from a centre y in tiles (as returned by tb.hold)."""
    return int((yc * 16 + H_PX / 2 - 1) // 16)


def _state():
    p = tb.me()
    if p.get("dead"):
        raise _Dead()
    return p


def _hold(keys, ticks, aim=None):
    s = tb.hold(list(keys), max(1, int(ticks)), aim=aim)
    if s.get("dead"):
        raise _Dead()
    return s


def _ground_tap(err, v):
    """(direction, ticks): hold that direction for that many ticks (0..15) on the ground so that, after coasting to
    a stop, the player ends nearest err px away; v is the current velocity."""
    best, best_d, best_k = math.inf, 0, 0
    for d in (-1, 1):
        for k in range(16):
            x, vv = 0.0, v
            for _ in range(k):
                vv = _hstep(vv, d, False)
                x += vv
            while vv:
                vv = _hstep(vv, 0, False)
                x += vv
            if abs(err - x) < best - 0.25:
                best, best_d, best_k = abs(err - x), d, k
    return best_d, best_k


def _align(tx, tol=2.5):
    """Stand still with the centre within tol px of tile x-coordinate tx (on the ground)."""
    last, stuck = None, 0
    for _ in range(40):
        p = _state()
        err, v = (tx - p["x"]) * 16, p["vx"]
        if abs(err) <= tol and abs(v) < 0.3:
            return p
        if last is not None and abs(p["x"] - last) < 0.01:
            stuck += 1
            if stuck >= 3:
                raise _Fail("align blocked")
        else:
            stuck = 0
        last = p["x"]
        d, k = _ground_tap(err, v)
        if k:
            _hold(_key(d), k)
        else:
            _hold([], max(2, int(abs(v) / SLOW_GROUND) + 1))  # coasting gets there
    raise _Fail("align")


def _land(tx, min_foot=None, budget=400):
    """Steer toward centre tx while airborne; return me() once standing (with foot_y >= min_foot)."""
    s = _state()
    t = 0
    while t < budget:
        k = _hcontrol((tx - s["x"]) * 16, s["vx"])
        s = _hold(_key(k), 2)
        t += 2
        if s["vy"] == 0:
            p = _state()
            if p["on_ground"] and (min_foot is None or p["foot_y"] >= min_foot):
                return p
            if min_foot is not None and p["on_ground"] and t >= STALL_TICKS:
                raise _Fail("did not fall")
    raise _Fail("no landing")


def _run(frm, nodes):
    """Walk (with auto step-ups) through consecutive nodes in one direction without stopping, then align."""
    d = _sign(nodes[-1][0] - frm[0])
    tx = nodes[-1][0] + 1.0
    ys = [frm[1]] + [n[1] for n in nodes]
    lo, hi = min(ys), max(ys)
    s = _state()
    best, idle = s["x"] * d, 0
    while True:
        err, v = (tx - s["x"]) * 16 * d, s["vx"] * d
        if err <= max(v, 0.0) ** 2 / (2 * (SLOW_GROUND + ACC)) + 1:
            break
        s = _hold(_key(d), 4)
        f = _foot(s["y"])
        if f > hi or f < lo - 1:
            raise _Fail("left the walkway")
        if s["x"] * d > best + 0.05:
            best, idle = s["x"] * d, 0
        else:
            idle += 4
            if idle >= STALL_TICKS:
                raise _Fail("walk stalled")
    _align(tx)


def _jump(step):
    J, D, off = step.jump
    tx = step.to[0] + 1.0
    if off == 0:
        _align(step.frm[0] + 1.0)
    s = _state()
    d = _sign(round((tx - s["x"]) * 16))
    s = _hold(["jump"] + (_key(d) if D == 0 else []), J)
    t = J
    while t < 300:
        if t < D:
            n = min(2, D - t)
            s = _hold([], n)
        else:
            n = 2
            s = _hold(_key(_hcontrol((tx - s["x"]) * 16, s["vx"])), n)
        t += n
        if s["vy"] == 0 and _state()["on_ground"]:
            return
    raise _Fail("jump never landed")


def _fall(step):
    fx, fy = step.frm
    tx = step.to[0] + 1.0
    s = _state()
    t = 0
    while _foot(s["y"]) <= fy:  # walk toward the hole until falling
        k = _hcontrol((tx - s["x"]) * 16, s["vx"]) or _sign(tx - s["x"])
        s = _hold(_key(k), 2)
        t += 2
        if t >= STALL_TICKS:
            raise _Fail("did not fall")
    _land(tx, fy + 1)


def _drop(step, rope_end):
    fx, fy = step.frm
    s = _state()
    t = 0
    # platform: release once the feet are below the platform top; rope: once the centre is past the rope's end
    while _foot(s["y"]) <= fy or (rope_end and s["y"] < fy):
        s = _hold(["down"], 2)
        t += 2
        if t >= STALL_TICKS:
            raise _Fail("could not drop")
    _land(step.to[0] + 1.0, fy + 1)


def _grab(step):
    r = step.to[0]
    s = _state()
    for _ in range(STALL_TICKS // 2):
        err = (r + 0.5 - s["x"]) * 16
        if abs(err) < 1.5 and s["vy"] == 0 and abs(s["vx"]) < 0.05 and not _state()["on_ground"]:
            return
        s = _hold(_key(_sign(err) if abs(err) >= 1.5 else 0) + ["up"], 2)
    raise _Fail("could not grab the rope")


def _swim(step):
    """Cross water at the surface: hold the direction, tap jump (hold 6, release 2) while wet to keep the head up,
    and jump out onto the target bank."""
    tx, ty = step.to[0] + 1.0, step.to[1]
    best, idle, t = math.inf, 0, 0
    while t < 1800:
        p = _state()
        err = (tx - p["x"]) * 16
        if p["on_ground"] and p["foot_y"] <= ty and abs(err) < 12:
            return
        keys = _key(_sign(err) if abs(err) >= 4 else 0)
        if p["on_ground"] and not p.get("wet") and (t == 0 or abs(p["vx"]) >= 0.3):
            _hold(keys, 4)  # on dry ground (near bank, or out on the far one): walk
            t += 4
        else:
            _hold(keys + ["jump"], 6)
            _hold(keys, 2)  # release so the next press jumps again
            t += 8
        dist = abs(err) + 16 * max(0, p["foot_y"] - ty)
        if dist < best - 1:
            best, idle = dist, 0
        else:
            idle += 8
            if idle >= 3 * STALL_TICKS:
                raise _Fail("swim stalled")
    raise _Fail("swim timed out")


def _climb(frm, ty):
    r, fy = frm
    up = ty < fy
    p = _state()
    if p["on_ground"]:
        _align(r + 0.5, tol=4)
    s, t, idle, last = p, 0, 0, p["y"]
    target = (ty + 1) * 16
    while True:
        diff = s["y"] * 16 + H_PX / 2 - target   # > 0: feet below the target row bottom
        if (up and diff <= 0) or (not up and diff >= -2):
            return
        n = max(1, min(4, int(abs(diff) / 3)))
        s = _hold(["up" if up else "down"], n)
        if abs(s["y"] - last) > 0.01:
            last, idle = s["y"], 0
        else:
            idle += n
            if idle >= 30:
                if not up and _state()["on_ground"]:
                    return
                raise _Fail("climb stalled")


class _Exec:
    def __init__(self, dig, place, timeout):
        self.dig, self.place = dig, place
        self.deadline = _time.monotonic() + timeout
        self.no_dig = set()
        self.world = None

    # ---- planning
    def window(self, s, goal):
        (sx, sy), (gx, gy) = s, goal
        x0, x1 = min(sx, gx) - MARGIN, max(sx + 1, gx) + MARGIN
        y0, y1 = min(sy, gy) - MARGIN - 3, max(sy, gy) + MARGIN
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if w * h > GRID_CELLS:  # far goal: keep the start's surroundings, cut the far side
            f = math.sqrt(GRID_CELLS / (w * h))
            nw = max(2 * MARGIN + 2, int(w * f))
            nh = max(2 * MARGIN + 4, min(h, GRID_CELLS // nw))
            nw = min(w, GRID_CELLS // nh)
            nh = min(h, GRID_CELLS // nw)
            if gx >= sx:
                x1 = x0 + nw - 1
            else:
                x0 = x1 - nw + 1
            if gy >= sy:
                y1 = y0 + nh - 1
            else:
                y0 = y1 - nh + 1
        if self.world is None:
            try:
                self.world = tuple(tb.world()["size"])
            except Exception:
                self.world = (1 << 30, 1 << 30)
        ww, wh = self.world
        return max(0, x0), max(0, y0), min(ww - 1, x1), min(wh - 1, y1)

    def plan(self, p, goal, near, partial):
        s = node_of(p)
        x0, y0, x1, y1 = self.window(s, goal)
        grid = tb.tiles(x0, y0, x1, y1)
        blocks = sum(placeable_blocks().values()) if self.place else 0
        gx, gy = goal
        if x0 <= gx <= x1 and y0 <= gy <= y1:
            return plan(grid, s, goal, dig=self.dig, place=self.place, near=near, blocks=blocks,
                        no_dig=self.no_dig, partial=partial)
        # goal outside the window: head for the nearest point inside it, then replan from there
        proxy = (min(max(gx, x0 + 2), x1 - 2), min(max(gy, y0 + 3), y1 - 2))
        return plan(grid, s, proxy, dig=self.dig, place=self.place, near=max(near, 6), blocks=blocks,
                    no_dig=self.no_dig, partial=True)

    # ---- steps
    def mine_cell(self, c):
        try:
            ok = tb.mine(*c)
        except tb.TbError:
            ok = False
        if ok:
            return
        cell = tb.tiles(c[0], c[1], c[0], c[1]).at(*c)
        if cell.known and cell.solid:
            self.no_dig.add(tuple(c))
            raise _Fail(f"could not mine {c}")

    def open_door(self, c):
        """use_tile on a closed door cell (cells of an already opened door are skipped: using them would close it)."""
        if not tb.tiles(c[0], c[1], c[0], c[1]).at(*c).solid:
            return
        tb.hold("use_tile", 2, aim=(c[0] + 0.5, c[1] + 0.5))
        if tb.tiles(c[0], c[1], c[0], c[1]).at(*c).solid:
            raise _Fail(f"door at {c} did not open")

    def pillar(self, step):
        for c in step.mine:
            self.mine_cell(c)
        item = _pick_block()
        if item is None:
            raise _Fail("no blocks")
        (fx, fy), (cx, cy) = step.frm, step.place
        for _ in range(3):
            _align(fx + 1.0)
            tb.select(item)
            _hold(["jump"], 12)
            try:
                tb.place(item, cx, cy, ticks=3)
            except tb.TbError:
                pass
            p = _land(fx + 1.0)
            if p["foot_y"] <= fy - 1:
                return
        raise _Fail("pillar block not placed")

    def dig_step(self, step):
        for c in step.mine:
            self.mine_cell(c)
        for c in step.doors:
            self.open_door(c)
        if step.to[0] != step.frm[0]:
            _run(step.frm, [step.to])
        else:
            _land(step.to[0] + 1.0, step.frm[1] + 1)

    def check(self, target):
        p = _state()
        n = node_of(p)
        if n != target and p["on_ground"] and n[1] == target[1] and abs(n[0] - target[0]) <= 1:
            _align(target[0] + 1.0)
            n = node_of(_state())
        if n != target:
            raise _Fail(f"at {n}, expected {target}")

    def execute(self, steps):
        i = 0
        while i < len(steps):
            if _time.monotonic() > self.deadline:
                return
            st, j = steps[i], i
            if st.kind in ("walk", "step"):
                d = _sign(st.to[0] - st.frm[0])
                while j + 1 < len(steps) and steps[j + 1].kind in ("walk", "step") and \
                        _sign(steps[j + 1].to[0] - steps[j + 1].frm[0]) == d:
                    j += 1
                _run(st.frm, [s.to for s in steps[i:j + 1]])
            elif st.kind == "climb":
                d = _sign(st.to[1] - st.frm[1])
                while j + 1 < len(steps) and steps[j + 1].kind == "climb" and \
                        _sign(steps[j + 1].to[1] - steps[j + 1].frm[1]) == d:
                    j += 1
                if st.to[1] == st.frm[1]:
                    _grab(st)
                else:
                    _climb(st.frm, steps[j].to[1])
            elif st.kind == "jump":
                _jump(st)
            elif st.kind == "fall":
                if st.to[0] == st.frm[0]:
                    _drop(st, rope_end=True)
                else:
                    _fall(st)
            elif st.kind == "drop":
                _drop(st, rope_end=False)
            elif st.kind == "swim":
                _swim(st)
            elif st.kind == "pillar":
                self.pillar(st)
            else:  # dig, door
                self.dig_step(st)
            self.check(steps[j].to)
            i = j + 1

    def settle(self):
        for _ in range(60):
            p = _state()
            if p["on_ground"] or (abs(p["vy"]) < 1e-6 and abs(p["vx"]) < 0.05):
                return p
            _hold([], 4)
        return _state()

    def goto(self, goal, near):
        fails = 0
        last_start = None
        while _time.monotonic() < self.deadline and fails <= MAX_FAILS:
            p = self.settle()
            s = node_of(p)
            if _goal_dist(s, goal) <= near:
                return True
            if s == last_start:
                fails += 1
            last_start = s
            steps = self.plan(p, goal, near, partial=True)
            if not steps:
                return False
            try:
                self.execute(steps)
            except _Fail:
                fails += 1
        return False


def goto(x, y, *, dig=True, place=True, near=0, timeout=60.0):
    """Move the player to stand with feet in row y with column x inside its body (within `near` tiles).
    True on arrival; False on no path, timeout, death or too many failed replans. See CAPABILITIES."""
    ex = _Exec(dig, place, timeout)
    try:
        return ex.goto((int(x), int(y)), int(near))
    except _Dead:
        return False
    finally:
        try:
            tb.stop()
        except Exception:
            pass


def plan_to(x, y, *, dig=True, place=True, near=0):
    """The steps goto would take from the player's current position (a first leg only for far goals), or None."""
    ex = _Exec(dig, place, 0.0)
    return ex.plan(tb.me(), (int(x), int(y)), int(near), partial=False)
