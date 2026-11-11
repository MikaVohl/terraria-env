"""Tile grid returned by tb.tiles(): only cells revealed on the player's map (or lit on screen) are known."""
from collections import namedtuple

SOLID, PLATFORM, WATER, LAVA, HONEY, WALL, HALF, SLOPE, ACTUATED = 1, 2, 4, 8, 16, 32, 64, 128, 256
UNKNOWN, EMPTY = -2, -1

Cell = namedtuple("Cell", "x y known type kind solid platform liquid wall")
Cell.__doc__ = ("One tile. known=False: never revealed (type -2, kind 'Unknown'). type -1 / kind 'Empty': no tile. "
                "solid: blocks movement. platform: standable from above, passable from below. liquid: None/'water'/'lava'/'honey'.")


class Grid:
    """Rectangle of tiles [x0, x0+w) x [y0, y0+h). Cells outside the rectangle are unknown."""

    def __init__(self, x0, y0, w, h, types, flags, names):
        self.x0, self.y0, self.w, self.h = x0, y0, w, h
        self.types, self.flags = types, flags
        self.names = {int(k): v for k, v in names.items()}

    @classmethod
    def from_reply(cls, r):
        return cls(r["x0"], r["y0"], r["w"], r["h"], r["t"], r["f"], r.get("names", {}))

    def inside(self, x, y):
        return self.x0 <= x < self.x0 + self.w and self.y0 <= y < self.y0 + self.h

    def _k(self, x, y):
        return (y - self.y0) * self.w + (x - self.x0)

    def type(self, x, y):
        return self.types[self._k(x, y)] if self.inside(x, y) else UNKNOWN

    def flag(self, x, y):
        return self.flags[self._k(x, y)] if self.inside(x, y) else 0

    def known(self, x, y):
        return self.type(x, y) != UNKNOWN

    def solid(self, x, y):
        return bool(self.flag(x, y) & SOLID)

    def platform(self, x, y):
        return bool(self.flag(x, y) & PLATFORM)

    def empty(self, x, y):
        """Known and passable for the player's body (no solid tile; platforms, trees, plants, liquids are passable)."""
        return self.known(x, y) and not self.solid(x, y)

    def liquid(self, x, y):
        f = self.flag(x, y)
        return "lava" if f & LAVA else "honey" if f & HONEY else "water" if f & WATER else None

    def kind(self, x, y):
        t = self.type(x, y)
        return "Unknown" if t == UNKNOWN else "Empty" if t == EMPTY else self.names.get(t, str(t))

    def at(self, x, y):
        f = self.flag(x, y)
        return Cell(x, y, self.known(x, y), self.type(x, y), self.kind(x, y), bool(f & SOLID), bool(f & PLATFORM),
                    self.liquid(x, y), bool(f & WALL))

    def find(self, kind):
        """[(x, y)] of known cells whose kind matches (case-insensitive)."""
        kind = kind.lower()
        return [(self.x0 + k % self.w, self.y0 + k // self.w) for k, t in enumerate(self.types)
                if t >= 0 and self.names.get(t, "").lower() == kind]

    def render(self, marks=None):
        """ASCII view for printing: '#' solid, '-' platform, '.' empty, '?' unknown, '~' water, 'L' lava, 'T' tree,
        other non-solid tiles 't'. `marks` maps (x, y) -> character (e.g. the player '@')."""
        marks = marks or {}
        rows = []
        for y in range(self.y0, self.y0 + self.h):
            row = []
            for x in range(self.x0, self.x0 + self.w):
                if (x, y) in marks:
                    row.append(marks[(x, y)])
                    continue
                t, f = self.type(x, y), self.flag(x, y)
                row.append("?" if t == UNKNOWN else "#" if f & SOLID else "-" if f & PLATFORM else "L" if f & LAVA
                           else "~" if f & (WATER | HONEY) else "." if t == EMPTY
                           else "T" if self.names.get(t) == "Trees" else "t")
            rows.append("".join(row))
        return "\n".join(rows)
