"""Declared macro track: observation-driven controllers that expand into primitive actions.

Every controller reads only the symbolic packet (tiles, scalars, legal mask) after each
tick and emits ONE primitive action at a time; the harness executes, journals and
replays those primitives exactly like model-chosen ones. Controllers never see hidden
terrain: unlit cells are treated as diggable attempts, as the action mask allows.
"""
import re

from terraria_lite import SPEC

SOLID = {"dirt", "grass", "stone", "wood", "copper ore", "iron ore", "gold ore", "bedrock", "silver ore"}
SOLID_BLOCKS = ("stone", "dirt", "wood")  # placeables usable as steps
MACROS = ("walk left", "walk right", "dig left", "dig right", "dig down", "stairs up-left", "stairs up-right")
MACRO_HELP = ("MACROS (declared macro track; each expands into primitive ticks chosen from the current observation every tick, "
              "and stops early when blocked or when an interrupt event happens): "
              "'walk left N'/'walk right N' walk N columns (jumps over 1-2 tile obstacles when possible); "
              "'dig left N'/'dig right N' tunnel N columns sideways (mines the 3 cells beside your body, then steps); "
              "'dig down N' digs a 2-wide shaft N rows down and drops into it; "
              "'stairs up-left N'/'stairs up-right N' dig a staircase N rows upward (needs a solid block - stone, dirt or wood - "
              "in inventory to fill missing steps). Mining inside macros waits out the pickaxe cooldown automatically. "
              "Macros count against the per-call action limit by the primitive ticks they use.")
MACRO_RE = re.compile(r"^(walk left|walk right|dig left|dig right|dig down|stairs up-left|stairs up-right)\s*(?:x\s*)?(\d+)?$")


class Stuck(Exception):
    """A controller cannot make progress; the message is shown to the model."""


def parse_macro(text):
    match = MACRO_RE.match(text.strip().lower())
    if not match:
        return None
    return match[1], int(match[2] or 1)


class View:
    def __init__(self, packet):
        self.p = packet
        self.ax, self.ay = SPEC.view_w//2, SPEC.view_h//2
        self.legal = set(packet["legal_actions"])
        s = packet["scalars"]
        self.x = round(s["horizontal_fraction"]*(SPEC.world_w-1))
        self.y = round(s["depth_fraction"]*(SPEC.world_h-1))
        self.mine_cd = round(s["mine_cooldown"]*3)

    def tile(self, dx, dy):
        r, c = self.ay+dy, self.ax+dx
        if not (0 <= r < SPEC.view_h and 0 <= c < SPEC.view_w):
            return None
        t = self.p["tiles"][r][c]
        return None if t == SPEC.unknown_tile else SPEC.tile_names[t]

    def needs_mining(self, dx, dy):
        t = self.tile(dx, dy)
        return t is None or t in SOLID

    def solid(self, dx, dy):
        return self.tile(dx, dy) in SOLID


def action(name):
    return SPEC.action_names.index(name)


def mine_name(dx, dy):
    i = SPEC.reach_offsets.index((dx, dy))
    return SPEC.action_names[SPEC.mine_first+i]


def place_name(dx, dy):
    i = SPEC.reach_offsets.index((dx, dy))
    return SPEC.action_names[SPEC.place_first+i]


class Controller:
    """Base: next_action(view) -> primitive id, or None when finished. Raises Stuck."""
    def __init__(self, name, n):
        self.name, self.n = name, n
        self.start = None
        self.idle = 0
        self.last = None

    def progress_guard(self, v, key):
        if key == self.last:
            self.idle += 1
            if self.idle > 12:
                raise Stuck("no progress")
        else:
            self.idle, self.last = 0, key

    def mine(self, v, dx, dy):
        a = action(mine_name(dx, dy))
        if v.mine_cd:
            return 0
        if a not in v.legal:
            why = " (it supports a tree trunk: cut the trunk first)" if v.tile(dx, dy-1) == "log" else ""
            raise Stuck(f"cannot mine {v.tile(dx, dy) or 'unlit cell'} at ({dx:+d},{dy:+d}){why}")
        return a


class Walk(Controller):
    jumps = 0

    def next_action(self, v):
        d = -1 if self.name.endswith("left") else 1
        if self.start is None:
            self.start = v.x
        if (v.x - self.start)*d >= self.n:
            return None
        if v.x != getattr(self, "jump_x", None):
            self.jumps, self.jump_x = 0, v.x
        self.progress_guard(v, (v.x, v.y))
        move = action("left" if d < 0 else "right")
        if move in v.legal:
            return move
        if action("jump") in v.legal and self.jumps < 2:
            self.jumps += 1
            return action("jump")
        if self.jumps < 2 or self.idle < 3:
            return 0  # airborne: wait for apex/landing before steering again
        raise Stuck("path blocked")


class Prim(Controller):
    """One primitive action; optionally waits out mining/attack cooldowns with noops first."""
    def __init__(self, a, wait):
        super().__init__(SPEC.action_names[a], 1)
        self.a, self.wait, self.done = a, wait, False

    def next_action(self, v):
        if self.done:
            return None
        if self.wait and self.idle < 4:
            busy = (SPEC.mine_first <= self.a < SPEC.mine_first+SPEC.reach_count and v.mine_cd) or \
                   (self.a == action("attack") and round(v.p["scalars"]["attack_cooldown"]*3))
            if busy:
                self.idle += 1
                return 0
        self.done = True
        return self.a
        raise Stuck("path blocked")


class DigSide(Controller):
    def next_action(self, v):
        d = -1 if self.name.endswith("left") else 1
        if self.start is None:
            self.start = v.x
        if (v.x - self.start)*d >= self.n:
            return None
        self.progress_guard(v, (v.x, v.y, v.mine_cd, tuple(map(tuple, v.p["tiles"]))))
        side = -1 if d < 0 else 2
        for dy in (0, -1, -2):
            if v.needs_mining(side, dy):
                return self.mine(v, side, dy)
        move = action("left" if d < 0 else "right")
        if move in v.legal:
            return move
        if not v.solid(0, 1) and not v.solid(1, 1):
            return 0  # falling
        raise Stuck("cannot step sideways")


class DigDown(Controller):
    def next_action(self, v):
        if self.start is None:
            self.start = v.y
        if v.y - self.start >= self.n:
            return None
        self.progress_guard(v, (v.y, v.mine_cd, tuple(map(tuple, v.p["tiles"]))))
        for dx in (0, 1):
            if v.needs_mining(dx, 1):
                if v.tile(dx, 1) == "bedrock":
                    raise Stuck("bedrock below")
                return self.mine(v, dx, 1)
        if v.tile(0, 1) == "wood platform" or v.tile(1, 1) == "wood platform":
            drop = action("drop through platform")
            if drop in v.legal:
                return drop
        return 0  # falling into the shaft


class Stairs(Controller):
    def next_action(self, v):
        d = -1 if self.name.endswith("left") else 1
        if self.start is None:
            self.start = v.y
        if self.start - v.y >= self.n:
            return None
        self.progress_guard(v, (v.x, v.y, v.mine_cd, tuple(map(tuple, v.p["tiles"])), v.p["v9"]["selected_slot_one_hot"] if "v9" in v.p else None))
        side = -1 if d < 0 else 2
        # Headroom above the current body, then the 3 cells of the next column one row up.
        for dx, dy in ((0, -3), (1, -3), (side, -3), (side, -2), (side, -1)):
            if v.needs_mining(dx, dy):
                return self.mine(v, dx, dy)
        if not v.solid(side, 0):
            # Need a step: place a solid block at foot level on that side.
            place = action(place_name(side, 0))
            if place in v.legal and self.selected_solid(v):
                return place
            for block in SOLID_BLOCKS:
                if v.p["inventory"].get(block, 0) > 0 and not self.selected_solid(v):
                    return action(f"select {block}")
            if v.tile(side, 0) not in (None, "air"):
                return self.mine(v, side, 0)
            raise Stuck("no solid block to build a step")
        move = action("left" if d < 0 else "right")
        if move in v.legal:
            return move
        raise Stuck("cannot step up")

    @staticmethod
    def selected_solid(v):
        slots = v.p.get("v9", {}).get("selected_slot_one_hot")
        if not slots:
            return False
        from terraria_lite.llm_text import PLACEABLES
        chosen = [PLACEABLES[i] for i, x in enumerate(slots) if x > .5]
        return bool(chosen) and chosen[0] in SOLID_BLOCKS and v.p["inventory"].get(chosen[0], 0) > 0


def make(name, n):
    cls = {"walk": Walk, "dig": DigDown if name == "dig down" else DigSide, "stairs": Stairs}[name.split()[0]]
    return cls(name, n)
