"""Offline tests for tb.path: the A* planner on ASCII grids and the executor against a small fake game."""
import math
import unittest

import terrariabench.tb as tb
from terrariabench.tb import path
from terrariabench.tb.grid import LAVA, PLATFORM, SOLID, WATER, Grid

# '#' solid, '.' air, '-' platform, '?' unknown, 'H' rope, '~' water, 'L' lava, 'D' closed door, 'T' tree and
# 't' other non-solid tile (both passable), '@' start (feet cell of the start node's left column), 'G' goal tile
NAMES = {0: "Dirt", 3: "Plants", 5: "Trees", 10: "ClosedDoor", 19: "Platforms", 213: "Rope"}
CELLS = {"#": (0, SOLID), ".": (-1, 0), "-": (19, PLATFORM), "?": (-2, 0), "H": (213, 0), "~": (-1, WATER),
         "L": (-1, LAVA), "D": (10, SOLID), "T": (5, 0), "t": (3, 0), "@": (-1, 0), "G": (-1, 0)}


def sky(n, w):
    return ["." * w] * n


def grid_of(rows, x0=0, y0=0):
    w, h = max(map(len, rows)), len(rows)
    types, flags, start, goal = [], [], None, None
    for y, row in enumerate(rows):
        for x, ch in enumerate(row.ljust(w, "#")):
            t, f = CELLS[ch]
            types.append(t)
            flags.append(f)
            if ch == "@":
                start = (x0 + x, y0 + y)
            elif ch == "G":
                goal = (x0 + x, y0 + y)
    return Grid(x0, y0, w, h, types, flags, {str(k): v for k, v in NAMES.items()}), start, goal


def kinds(steps):
    return [s.kind for s in steps]


def plan(rows, **kw):
    g, s, goal = grid_of(rows)
    return path.plan(g, s, kw.pop("goal", goal), **kw)


def reaches(steps, goal, near=0):
    """Does the path end at `goal` (a tile, or the rows of a fixture with a 'G')?"""
    if not isinstance(goal, tuple):
        goal = grid_of(goal)[2]
    x, y = steps[-1].to
    gx, gy = goal
    dx = 0 if x <= gx <= x + 1 else min(abs(gx - x), abs(gx - x - 1))
    return max(dx, abs(y - gy)) <= near


class PlannerTests(unittest.TestCase):
    def test_flat_walk(self):
        rows = sky(3, 12) + [".@.......G..", "############"]
        steps = plan(rows, dig=False, place=False)
        self.assertEqual(set(kinds(steps)), {"walk"})
        self.assertTrue(reaches(steps, rows))

    def test_already_there(self):
        rows = sky(3, 6) + [".@G...", "######"]
        self.assertEqual(plan(rows), [])

    def test_step_up(self):
        rows = sky(4, 11) + ["........G..", ".@....#####", "###########"]
        steps = plan(rows, dig=False, place=False)
        self.assertIn("step", kinds(steps))
        self.assertNotIn("jump", kinds(steps))
        self.assertTrue(reaches(steps, rows))

    @staticmethod
    def wall(height, h=14):
        """Start on the floor (feet row h-1), goal on top of a `height`-row wall."""
        rows = sky(h, 14)
        for y in range(h - height, h):
            rows[y] = rows[y][:7] + "#" * 7
        rows[h - height - 1] = "." * 9 + "G" + "." * 4
        rows[h - 1] = ".@" + rows[h - 1][2:]
        return rows + ["#" * 14]

    def test_jump_up_four(self):
        rows = self.wall(4)
        steps = plan(rows, dig=False, place=False)
        jumps = [s for s in steps if s.kind == "jump"]
        self.assertEqual(len(jumps), 1)
        self.assertEqual(jumps[0].to[1] - jumps[0].frm[1], -4)
        self.assertTrue(reaches(steps, rows))
        self.assertIsNone(plan(self.wall(5), dig=False, place=False))  # 5 rows: beyond the planned jump height

    def test_jump_up_seven_needs_pillar(self):
        rows = self.wall(7)
        self.assertIsNone(plan(rows, dig=False, place=False))
        self.assertIsNone(plan(rows, dig=False, place=True, blocks=0))
        self.assertIsNone(plan(rows, dig=False, place=True, blocks=2))
        steps = plan(rows, dig=False, place=True, blocks=10)
        self.assertEqual(kinds(steps).count("pillar"), 3)
        for s in steps:
            if s.kind == "pillar":
                self.assertEqual(s.to, (s.frm[0], s.frm[1] - 1))
                self.assertIn(s.place[0], (s.frm[0], s.frm[0] + 1))
                self.assertEqual(s.place[1], s.frm[1])
        self.assertTrue(reaches(steps, rows))

    def test_gap_jump_over_lava(self):
        rows = sky(8, 14) + [".@.........G..", "####...#######", "####LLL#######", "##############"]
        steps = plan(rows, dig=False, place=False)
        self.assertIn("jump", kinds(steps))
        self.assertNotIn("fall", kinds(steps))
        for s in steps:  # never stands with both columns over the lava pit (columns 4-6)
            self.assertFalse(s.to[0] >= 4 and s.to[0] + 1 <= 6)
        self.assertTrue(reaches(steps, rows))

    def test_fall(self):
        rows = sky(3, 10) + [".@........", "####......", "####......", "####......", "####...G..", "##########"]
        steps = plan(rows, dig=False, place=False)
        self.assertIn("fall", kinds(steps))
        self.assertTrue(reaches(steps, rows))

    @staticmethod
    def cliff(rope):
        """A 33-row cliff; optionally a rope hangs down beside it."""
        w, depth = 24, 32
        rows = sky(4, w) + ["#" * 10 + "." * (w - 10)]
        rows[3] = ".@" + rows[3][2:]
        rows += ["#" * 10 + "." * (w - 10) for _ in range(depth)]
        rows[-1] = rows[-1][:18] + "G" + rows[-1][19:]
        if rope:
            for y in range(2, len(rows)):
                rows[y] = rows[y][:10] + "H" + rows[y][11:]
        return rows + ["#" * w]

    def test_deep_fall_only_without_alternative(self):
        rows = self.cliff(rope=False)
        steps = plan(rows, dig=False, place=False)
        falls = [s.to[1] - s.frm[1] for s in steps if s.kind == "fall"]
        self.assertTrue(falls and max(falls) > 25)
        self.assertTrue(reaches(steps, rows))
        rows = self.cliff(rope=True)
        steps = plan(rows, dig=False, place=False)
        self.assertIn("climb", kinds(steps))
        self.assertTrue(all(s.to[1] - s.frm[1] <= 25 for s in steps))
        self.assertTrue(reaches(steps, rows))

    def test_platform_jump_through_and_drop(self):
        rows = sky(4, 12) + ["....G.......", "...------...", "............", "............", ".@..........",
                             "############"]
        steps = plan(rows, dig=False, place=False)
        self.assertIn("jump", kinds(steps))
        self.assertTrue(reaches(steps, rows))
        rows = sky(4, 12) + [".....@......", "...------...", "............", "............", "........G...",
                             "############"]
        steps = plan(rows, dig=False, place=False)
        self.assertIn("drop", kinds(steps))
        self.assertTrue(reaches(steps, rows))

    @staticmethod
    def tunnel(wall):
        return ["############", "#....." + wall + "...#", "#....." + wall + "...#", "#.@..." + wall + ".G.#",
                "############"]

    def test_dig_through_wall(self):
        rows = self.tunnel("##")
        self.assertIsNone(plan(rows, dig=False))
        steps = plan(rows, dig=True)
        mined = {c for s in steps for c in s.mine}
        self.assertEqual(mined, {(6, 1), (6, 2), (6, 3), (7, 1), (7, 2), (7, 3)})
        self.assertIn("dig", kinds(steps))
        self.assertTrue(reaches(steps, rows))

    def test_unknown_blocks_without_dig(self):
        rows = self.tunnel("??")
        self.assertIsNone(plan(rows, dig=False))
        steps = plan(rows, dig=True)
        self.assertEqual(len({c for s in steps for c in s.mine}), 6)
        self.assertTrue(reaches(steps, rows))

    def test_lava_never_entered(self):
        rows = ["############", "#..........#", "#..........#", "#.@......G.#", "#####LL#####", "############"]
        self.assertIsNone(plan(rows, dig=False, place=False))

    # real-game grid (x0=2061, y0=243): spawn '@' at (2101, 258) beside a 12-wide pond; the pond is ~14 rows deep
    POND = [
        "???????...................................................................???????",
        "???????....T..............................................................???????",
        "???????....T...T..........................................................???????",
        "???????....T...T..........................................................???????",
        "???????...TT...T..........................................................???????",
        "???????....T...T..........................................................???????",
        "???????T..TTT..T.......................T..................................???????",
        "???????T...T...T......................TTT.................................???????",
        "???????T...TT..T.......................T...............T..................???????",
        "???????T...T..TTT......................T...............T..................???????",
        "???????T...T...T..................T....T...............T..................???????",
        "???????T...T...T..................T...TTT..............T..................???????",
        "???????T...T...T....T....T........T....T..............TT..................???????",
        "???????TT..T...T....T...TTT.......T....T...............T..................???????",
        "???????T...T..TTT...T....T........T....T...............TTttttttt..........???????",
        "???????TT..TT..T....TT...T.......tTTttTT@............t###########tttttt...???????",
        "???????TTttTTttTTttTT....T...ttt#########~~~~~~~~~~~~###################tt???????",
        "???????###############ttTTTt#############~~~~~~~~~~~######################???????",
        "???????##################################~~~~~~~~~~~######################???????",
        "???????#################################~~~~~~~~~~~~######################???????",
    ] + ["???????#################################~~~~~~~~~~~~######################???????"] * 10 + [
        "???????" + "#" * 67 + "???????"]

    @staticmethod
    def head_wet(grid, node):
        x, y = node
        return any(grid.liquid(x + i, y - j) == "water" for i in (0, 1) for j in (1, 2))

    def test_pond_crossed_by_surface_swim(self):
        g, s, _ = grid_of(self.POND, 2061, 243)
        self.assertEqual(s, (2101, 258))
        for dig in (False, True):
            steps = path.plan(g, s, (2127, 258), dig=dig, place=True, blocks=20)
            self.assertIsNotNone(steps)
            self.assertEqual(kinds(steps).count("swim"), 1)
            self.assertTrue(reaches(steps, (2127, 258)))
            for st in steps:
                self.assertFalse(self.head_wet(g, st.to), st)
                self.assertFalse(any(g.liquid(*c) or g.liquid(c[0], c[1] - 1) for c in st.mine), st)

    def test_pond_left_goal_is_plain(self):
        g, s, _ = grid_of(self.POND, 2061, 243)
        steps = path.plan(g, s, (2077, 259), dig=True, place=True, blocks=20)
        self.assertTrue(set(kinds(steps)) <= {"walk", "step", "jump", "fall"}, kinds(steps))
        self.assertTrue(reaches(steps, (2077, 259)))

    def test_water_too_wide_or_deep_never_entered(self):
        rows = sky(4, 32) + [".@............................G.", "####" + "~" * 24 + "####"] + \
            ["####" + "~" * 24 + "####"] * 5 + ["#" * 32]
        self.assertIsNone(plan(rows, dig=False, place=False))

    def test_shallow_water_is_waded(self):
        rows = sky(3, 12) + [".@........G.", "###~~~~#####", "############"]
        steps = plan(rows, dig=False, place=False)
        self.assertNotIn("swim", kinds(steps))
        self.assertTrue(reaches(steps, rows))

    def test_door(self):
        rows = self.tunnel(".D")
        steps = plan(rows, dig=False)
        self.assertIn("door", kinds(steps))
        self.assertEqual({c for s in steps for c in s.doors}, {(7, 1), (7, 2), (7, 3)})
        self.assertTrue(reaches(steps, rows))

    ROPE = ["..............",
            "..............",
            ".......H......",
            "..G....H......"] + ["######.H......"] * 10 + [
            "######.H@.....",
            "##############"]

    def test_rope_climb_up(self):
        self.assertIsNone(plan([r.replace("H", ".") for r in self.ROPE], dig=False, place=False))
        steps = plan(self.ROPE, dig=False, place=False)
        self.assertIn("climb", kinds(steps))
        self.assertTrue(reaches(steps, self.ROPE))

    def test_near_tolerance(self):
        rows = sky(3, 12) + [".@..........", "############", "############", "############"]
        g, s, _ = grid_of(rows)
        self.assertIsNone(path.plan(g, s, (8, 5), dig=False))
        self.assertIsNone(path.plan(g, s, (8, 5), dig=False, near=1))
        steps = path.plan(g, s, (8, 5), dig=False, near=2)
        self.assertTrue(reaches(steps, (8, 5), near=2))

    def test_node_of(self):
        self.assertEqual(path.node_of({"left": (16 * 5 + 6) / 16, "foot_y": 9}), (5, 9))
        self.assertEqual(path.node_of({"left": (16 * 5 + 13) / 16, "foot_y": 9}), (5, 9))
        self.assertEqual(path.node_of({"left": (16 * 5 + 14) / 16, "foot_y": 9}), (6, 9))
        self.assertEqual(path.node_of({"left": (16 * 7 - 2) / 16, "foot_y": 3}), (7, 3))  # on a rope at column 7


# ---------------------------------------------------------------- fake game for the executor
def _hstep(v, d, air):
    if d:
        if v * d < 0:
            v += d * 0.2
        return max(-3.0, min(3.0, v + d * 0.08))
    s = 0.1 if air else 0.2
    return 0.0 if abs(v) <= s else v - math.copysign(s, v)


class FakeGame:
    """Kinematic stand-in for the TerraBot RPC: 20x42 px hitbox, run 3 px/tick (accel 0.08), jump 5.01 px/tick for
    up to 15 ticks, gravity 0.4, max fall 10, auto step-up, platforms, ropes, doors, mining and block placing."""

    def __init__(self, rows, blocks=0):
        self.w, self.h = max(map(len, rows)), len(rows)
        self.cells = {}
        for y, row in enumerate(rows):
            for x, ch in enumerate(row.ljust(self.w, "#")):
                self.cells[(x, y)] = CELLS[ch]
                if ch == "@":
                    sx, sy = x, y
                elif ch == "G":
                    self.goal = (x, y)
        self.left, self.top = sx * 16 + 6.0, (sy + 1) * 16 - 42.0
        self.vx = self.vy = 0.0
        self.on_ground, self.jumpcnt, self.prev_jump, self.rope = True, 0, False, None
        self.life, self.dead, self.tick, self.fall_top, self.breath = 100, False, 0, self.top, 200
        self.progress = {}
        self.items = [{"slot": 0, "name": "Copper Pickaxe", "type": 3509, "stack": 1, "pick": 35, "axe": 0,
                       "hammer": 0, "damage": 4, "place_tile": None, "place_solid": False, "use_animation": 15}]
        if blocks:
            self.items.append({"slot": 1, "name": "Dirt Block", "type": 2, "stack": blocks, "pick": 0, "axe": 0,
                               "hammer": 0, "damage": 0, "place_tile": "Dirt", "place_solid": True,
                               "use_animation": 15})
        self.items.append({"slot": 2, "name": "Torch", "type": 8, "stack": 5, "pick": 0, "axe": 0, "hammer": 0,
                           "damage": 0, "place_tile": "Torches", "place_solid": False, "use_animation": 15})
        self.held = 0

    # ---- world
    def cell(self, x, y):
        return self.cells.get((x, y), (0, SOLID))

    def solid(self, x, y):
        return bool(self.cell(x, y)[1] & SOLID)

    def box(self, left, top):
        return [(c, r) for c in range(math.floor(left / 16), math.floor((left + 20 - 1e-6) / 16) + 1)
                for r in range(math.floor(top / 16), math.floor((top + 42 - 1e-6) / 16) + 1)]

    def collide(self, left, top):
        return any(self.solid(c, r) for c, r in self.box(left, top))

    def cols(self):
        return range(math.floor(self.left / 16), math.floor((self.left + 20 - 1e-6) / 16) + 1)

    def standable(self, c, r, down):
        t, f = self.cell(c, r)
        return bool(f & SOLID) or (bool(f & PLATFORM) and not down)

    # ---- physics
    def step(self, keys, aim, first):
        L, R, U, Dn, J = (k in keys for k in ("left", "right", "up", "down", "jump"))
        jump_new = J and not self.prev_jump
        self.prev_jump = J
        cx, cy = self.left + 10, self.top + 21
        if self.rope is None and (U or (Dn and not self.on_ground)) and not jump_new:
            col = int(cx // 16)
            if self.cell(col, int(cy // 16))[0] == 213:
                self.rope, self.vx, self.vy, self.jumpcnt = col, 0.0, 0.0, 0
        from_rope = False
        if self.rope is not None:
            if jump_new:
                self.rope, from_rope = None, True
            else:
                nl = self.rope * 16 + 8 - 10
                if not self.collide(nl, self.top):
                    self.left = nl
                self.vx = self.vy = 0.0
                dv = -3.0 if U else 3.0 if Dn else 0.0
                nt = self.top + dv
                if dv < 0 and self.cell(self.rope, int((nt + 21) // 16))[0] != 213:
                    nt = self.top  # top of the rope
                if not self.collide(self.left, nt):
                    self.top = nt
                if self.cell(self.rope, int((self.top + 21) // 16))[0] != 213:
                    self.rope, self.vy = None, dv
                self.ground(Dn)
                if self.rope is not None:
                    self.use(keys, aim, first)
                    return
        wet = self.wet()
        self.vx = _hstep(self.vx, (1 if R else 0) - (1 if L else 0), not self.on_ground)
        if wet:  # water: half run speed, half gravity, slow sinking, jump (tap) again while wet to swim up
            self.vx = max(-1.5, min(1.5, self.vx))
        lift = -4.0 if wet else -5.01 + 0.4
        if jump_new and (self.on_ground or from_rope or wet):
            # a 15-tick hold lifts for 13 ticks (vy -5.01, +0.4 gravity in the same tick): rises ~84 px
            self.vy, self.jumpcnt, self.on_ground = lift, (3 if wet else 12), False
        elif J and self.jumpcnt > 0:
            self.vy = lift
            self.jumpcnt -= 1
        else:
            if not J:
                self.jumpcnt = 0
            self.vy = min(self.vy + 0.2, 3.0) if wet else min(self.vy + 0.4, 10.0)
        if self.vx:
            nl = self.left + self.vx
            if not self.collide(nl, self.top):
                self.left = nl
            elif self.on_ground and not self.collide(nl, self.top - 16):
                self.left, self.top = nl, self.top - 16  # auto step-up
            else:
                if self.vx > 0:
                    self.left = math.floor((nl + 20 - 1e-6) / 16) * 16 - 20.0
                else:
                    self.left = (math.floor(nl / 16) + 1) * 16.0
                self.vx = 0.0
        was_air = not self.on_ground
        nt = self.top + self.vy
        if self.vy > 0:
            ob, nb = self.top + 42, nt + 42
            r, landed = math.ceil(ob / 16 - 1e-9), False
            while r * 16 < nb and not landed:
                if any(self.standable(c, r, Dn) for c in self.cols()):
                    self.top, self.vy, landed = r * 16 - 42.0, 0.0, True
                r += 1
            if not landed:
                self.top = nt
        elif self.vy < 0:
            r, bonk = math.ceil(self.top / 16 - 1e-9) - 1, False
            while (r + 1) * 16 > nt and not bonk:
                if any(self.solid(c, r) for c in self.cols()):
                    self.top, self.vy, self.jumpcnt, bonk = (r + 1) * 16.0, 0.0, 0, True
                r -= 1
            if not bonk:
                self.top = nt
        self.ground(Dn)
        if self.vy < 0 or (not self.on_ground and self.top < self.fall_top):
            self.fall_top = self.top
        if self.on_ground:
            if was_air and (self.top - self.fall_top) / 16 > 25:
                self.life -= int(10 * ((self.top - self.fall_top) / 16 - 25))
            self.fall_top = self.top
        if wet:
            self.fall_top = self.top  # water breaks falls
        head = self.cell(int((self.left + 10) // 16), int((self.top + 4) // 16))
        self.breath = self.breath - 1 if head[1] & WATER else min(200, self.breath + 3)
        if self.breath <= 0:
            self.life -= 2  # drowning
        if any(self.cell(c, r)[1] & LAVA for c, r in self.box(self.left, self.top)) or self.life <= 0:
            self.dead = True
        self.use(keys, aim, first)

    def wet(self):
        return bool(self.cell(int((self.left + 10) // 16), int((self.top + 21) // 16))[1] & WATER)

    def ground(self, down):
        b = self.top + 42
        self.on_ground = abs(b / 16 - round(b / 16)) < 1e-9 and \
            any(self.standable(c, round(b / 16), down) for c in self.cols())
        if self.on_ground and self.vy > 0:
            self.vy = 0.0

    def use(self, keys, aim, first):
        if aim is None:
            return
        ax, ay = int(math.floor(aim[0])), int(math.floor(aim[1]))
        cx, cy = (self.left + 10) / 16, (self.top + 21) / 16
        reach = abs(ax + 0.5 - cx) <= 6.5 and abs(ay + 0.5 - cy) <= 5.5
        it = self.items[self.held]
        if "use" in keys and reach:
            if it["pick"] > 0 and self.solid(ax, ay):
                self.progress[(ax, ay)] = self.progress.get((ax, ay), 0) + 1
                if self.progress[(ax, ay)] >= 20:
                    self.cells[(ax, ay)] = (-1, 0)
            elif first and it["place_solid"] and it["stack"] > 0 and self.cell(ax, ay)[0] == -1 and \
                    (ax, ay) not in self.box(self.left, self.top) and \
                    any(self.cell(ax + i, ay + j)[0] >= 0 for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                self.cells[(ax, ay)] = (0, SOLID)
                it["stack"] -= 1
        if "use_tile" in keys and reach and self.cell(ax, ay)[0] == 10:
            y = ay
            while self.cell(ax, y - 1)[0] == 10:
                y -= 1
            while self.cell(ax, y)[0] == 10:
                self.cells[(ax, y)] = (-1, 0)
                y += 1

    # ---- RPC
    def state(self, ticks=0):
        return {"x": (self.left + 10) / 16, "y": (self.top + 21) / 16, "vx": self.vx, "vy": self.vy,
                "life": self.life, "dead": self.dead, "tick": self.tick, "ticks": ticks}

    def call(self, op, **a):
        if op == "me":
            held = dict(self.items[self.held])
            return {**self.state(), "left": self.left / 16, "top": self.top / 16, "width": 1.25, "height": 2.625,
                    "tile_x": int((self.left + 10) // 16), "foot_y": int((self.top + 41) // 16),
                    "on_ground": self.on_ground, "dir": 1, "fall_tiles": 0, "life_max": 100, "held": held,
                    "selected_slot": self.held, "reach_tiles": [5, 4], "chest_open": False,
                    "inventory_open": False, "wet": self.wet(), "breath": self.breath}
        if op == "inventory":
            return [dict(i) for i in self.items if i["stack"] > 0]
        if op == "world":
            return {"size": [self.w, self.h]}
        if op == "tiles":
            x0, y0, x1, y1 = a["x0"], a["y0"], a["x1"], a["y1"]
            t, f = [], []
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    ct, cf = self.cell(x, y)
                    t.append(ct)
                    f.append(cf)
            return {"x0": x0, "y0": y0, "w": x1 - x0 + 1, "h": y1 - y0 + 1, "t": t, "f": f,
                    "names": {str(k): v for k, v in NAMES.items()}}
        if op in ("input", "wait"):
            keys = a.get("keys", [])
            for i in range(a["ticks"]):
                if self.dead:
                    break
                self.step(keys, a.get("aim"), i == 0)
                self.tick += 1
            self.prev_jump = False  # keys are released after the burst
            return self.state(a["ticks"])
        if op == "stop":
            self.prev_jump = False
            return {}
        if op == "select":
            if "slot" in a:
                self.held = a["slot"]
            else:
                self.held = next(i for i, it in enumerate(self.items) if it["name"].lower() == a["item"].lower())
            return {"slot": self.held}
        raise tb.TbError(f"{op}: unsupported in FakeGame")

    def node(self):
        return path.node_of(self.call("me"))


class ExecutorTests(unittest.TestCase):
    def run_game(self, rows, blocks=0, **kw):
        game = FakeGame(rows, blocks)
        orig = tb.call
        tb.call = game.call
        try:
            steps = tb.path_to(*game.goal, **kw)
            ok = tb.goto(*game.goal, timeout=20, **kw)
        finally:
            tb.call = orig
        return game, steps, ok

    def assert_at_goal(self, game):
        x, y = game.node()
        gx, gy = game.goal
        self.assertEqual(y, gy)
        self.assertIn(gx, (x, x + 1))
        self.assertFalse(game.dead)

    def test_walk_jump_fall(self):
        w = 34
        rows = sky(8, w) + [
            "..........#####...................",
            "..........#####...................",
            "..........#####...................",
            ".@........#####...................",
            "######################............",
            "######################............",
            "######################............",
            "######################.......G....",
            "#" * w]
        game, steps, ok = self.run_game(rows, dig=False, place=False)
        self.assertTrue({"walk", "jump", "fall"} <= set(kinds(steps)), kinds(steps))
        self.assertTrue(ok)
        self.assert_at_goal(game)

    def test_gap_jump(self):
        rows = sky(8, 20) + ["..@............G....", "#######...##########", "#######LLL##########", "#" * 20]
        game, steps, ok = self.run_game(rows, dig=False, place=False)
        self.assertIn("jump", kinds(steps))
        self.assertTrue(ok)
        self.assert_at_goal(game)

    def test_dig_through_wall(self):
        rows = ["##############", "#.......##...#", "#.......##...#", "#.@.....##.G.#", "##############"]
        game, steps, ok = self.run_game(rows, dig=True, place=False)
        self.assertIn("dig", kinds(steps))
        self.assertTrue(ok)
        self.assert_at_goal(game)
        self.assertEqual(game.cell(8, 2)[0], -1)

    def test_dig_down(self):
        rows = ["#........#",
                "#........#",
                "#..@.....#",
                "####G#####",
                "##########",
                "##########",
                "##########"]
        game, steps, ok = self.run_game(rows, dig=True, place=False)
        self.assertEqual(kinds(steps), ["dig"])
        self.assertTrue(ok)
        self.assert_at_goal(game)

    def test_pillar_out_of_pit(self):
        rows = sky(9, 20) + ["...............G...."] + ["########....########"] * 8 + [
            "########.@..########",
            "####################"]
        game, steps, ok = self.run_game(rows, blocks=20, dig=False, place=True)
        self.assertIn("pillar", kinds(steps))
        self.assertTrue(ok)
        self.assert_at_goal(game)
        self.assertLess(game.items[1]["stack"], 20)

    def test_rope_and_door(self):
        rows = ["................",
                "................",
                ".......H........",
                "..G....H........",
                "######.H........",
                "######.H........",
                "######.H........",
                "######.H........",
                "######.H........",
                "######.H........",
                "######.H....####",
                "######.H....D...",
                "######.H....D...",
                "######.H....D.@.",
                "################"]
        game, steps, ok = self.run_game(rows, dig=False, place=False)
        self.assertTrue({"door", "climb", "jump"} <= set(kinds(steps)), kinds(steps))
        self.assertTrue(ok)
        self.assert_at_goal(game)

    def test_no_path_returns_false(self):
        rows = ["##########", "#........#", "#........#", "#.@....G.#", "####LL####", "##########"]
        game, steps, ok = self.run_game(rows, dig=False, place=False)
        self.assertIsNone(steps)
        self.assertFalse(ok)
        self.assertFalse(game.dead)

    def test_far_goal_window_is_capped(self):
        ex = path._Exec(True, True, 1.0)
        ex.world = (8400, 2400)
        x0, y0, x1, y1 = ex.window((1000, 300), (3000, 900))
        self.assertLessEqual((x1 - x0 + 1) * (y1 - y0 + 1), 40000)
        self.assertTrue(x0 <= 1000 - path.MARGIN and y0 <= 300 - path.MARGIN)
        self.assertTrue(x1 > 1100 and y1 > 350)  # the cut keeps the start's side and extends toward the goal

    def test_placeable_blocks(self):
        inv = [{"name": "Dirt Block", "stack": 30, "place_tile": "Dirt", "place_solid": True},
               {"name": "Torch", "stack": 9, "place_tile": "Torches", "place_solid": False},
               {"name": "Wood", "stack": 5, "place_tile": "WoodBlock", "place_solid": True},
               {"name": "Wooden Chair", "stack": 1, "place_tile": "Chairs", "place_solid": False},
               {"name": "Sand Block", "stack": 50, "place_tile": "Sand", "place_solid": True},
               {"name": "Copper Ore", "stack": 50, "place_tile": "Copper", "place_solid": True},
               {"name": "Copper Pickaxe", "stack": 1, "place_tile": None, "place_solid": False}]
        self.assertEqual(path.placeable_blocks(inv), {"Dirt Block": 30, "Wood": 5, "Sand Block": 50,
                                                      "Copper Ore": 50})
        self.assertEqual(path._pick_block(inv), "Dirt Block")
        self.assertEqual(path._pick_block(inv[2:]), "Wood")

    def test_swim_across_pond(self):
        rows = sky(6, 18) + ["..@............G..",
                             "####~~~~~~~~######",
                             "####~~~~~~~~######",
                             "####~~~~~~~~######",
                             "####~~~~~~~~######",
                             "##################"]
        game, steps, ok = self.run_game(rows, dig=True, place=False)
        self.assertIn("swim", kinds(steps))
        self.assertTrue(ok)
        self.assert_at_goal(game)
        self.assertGreater(game.life, 50)


if __name__ == "__main__":
    unittest.main()
