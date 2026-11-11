"""In-game pathfinder checks for long climbs and water (tb-api-1.0-rc1), against a test-mode session:

    TB_SOCKET=<run>/agent.sock python3 tools/terrabot/climb_water_live.py <run> climb [N] [DEPTH]
    TB_SOCKET=<run>/agent.sock python3 tools/terrabot/climb_water_live.py <run> water [N] [LEFT RIGHT SURFACE] [fixture]
    TB_SOCKET=<run>/agent.sock python3 tools/terrabot/climb_water_live.py <run> stranded BX BY GX GY [fixture]

climb: N times, dig a 2-wide shaft DEPTH rows straight down from the surface (tb.goto with dig, a Wood Platform placed
in the shaft every 15 rows when there is wood), close the shaft over the head with two blocks (a ceiling to dig), then
tb.goto back to the surface spot with dig=True, place=True (held pillar). Records success, rows, wall/game time,
blocks used, life, deaths, tb.path.last_error.
water: walk to the pond LEFT..RIGHT with surface row SURFACE (located beforehand with test-only truth_tiles), or else
the nearest pond found with truth. Case no_exit/pond_bottom: from the near bank, tb.path_to the pond bottom must be None
and tb.goto must return False without the player getting wet. Then N times cross the pond with goto (surface swim) and
back, sampling breath/submerged/wet/life on every executor state read (tb.path._state wrapped); then wade in, sink,
and read breath/submerged from me() while the head is under water.
stranded: walk to the dry bank (BX, BY), then the same no_exit check for the goal (GX, GY) (e.g. beyond a crossing
wider than 20 columns).
"fixture" labels every record as a test-built pond (truth_edit water) rather than a natural one.
Appends one JSON line per case to <run>/climb-water-live.jsonl.
"""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "terrariabench"))
import tb  # noqa: E402
from tb import path  # noqa: E402
from tb._rpc import call  # noqa: E402  (test-mode setup/truth ops)

RUN = Path(sys.argv[1])


def record(case, **kw):
    kw = {"case": case, "unix": round(time.time(), 1), **kw}
    with (RUN / "climb-water-live.jsonl").open("a") as f:
        f.write(json.dumps(kw) + "\n")
    print(json.dumps(kw), flush=True)


def surface_row(x, around, span=40):
    g = tb.tiles(x, around - span, x + 1, around + span)
    for y in range(around - span, around + span):
        if g.solid(x, y + 1) and g.solid(x + 1, y + 1) and all(g.empty(c, yy) for c in (x, x + 1)
                                                                  for yy in range(y - 2, y + 1)):
            return y
    return None


def deaths_since(seq):
    return sum(e.event == "death" for e in tb.events(since=seq))


def blocks():
    return sum(path.placeable_blocks().values())


def setup():
    """Test-mode setup (dev worlds only): morning, torches to light the shaft, platforms to put in its way."""
    call("truth_morning")
    for item, n in (("Torch", 99), ("Wood Platform", 20)):
        if tb.count(item) < n // 2:
            call("truth_give", item=item, n=n)
    tb.sleep(30)


SOFT = {"Dirt", "Stone", "Grass", "Clay", "Mud", "Sand", "Silt", "Copper", "Tin", "Iron", "Lead", "ClayBlock"}

def shaft_columns(depth, radius=None):
    """Test-only (truth): surface columns x where a 2-wide shaft x, x+1 down `depth` rows meets no liquid (one
    column either side included) and at most 2 open cells (no cave to fall into), nearest first, >= 4 apart. The
    test measures digging and climbing; staying out of flooded caves is the agent's job, not the pathfinder's."""
    radius = radius or min(150, 40000 // (depth + 72) // 2 - 1)  # truth_tiles reads at most 40000 cells
    p = tb.me()
    x0, y0 = p.tile_x - radius, p.foot_y - 40
    g = tb.Grid.from_reply(call("truth_tiles", x0=x0, y0=y0, x1=p.tile_x + radius, y1=p.foot_y + depth + 30))
    out = []
    for x in sorted(range(x0 + 3, p.tile_x + radius - 3), key=lambda c: abs(c - p.tile_x)):
        top = next((y for y in range(y0 + 3, p.foot_y + 20) if g.solid(x, y + 1) and g.solid(x + 1, y + 1)
                    and all(not g.solid(c, yy) for c in (x, x + 1) for yy in (y, y - 1, y - 2))), None)
        if top is None or any(abs(x - o[0]) < 4 for o in out):
            continue
        wet = any(g.liquid(c, y) for c in range(x - 2, x + 4) for y in range(top, top + depth + 4))
        holes = sum(not g.solid(c, y) for c in (x, x + 1) for y in range(top + 1, top + depth + 2))
        hard = any(g.solid(c, y) and g.kind(c, y) not in SOFT for c in (x, x + 1) for y in range(top + 1, top + depth + 2))
        if not wet and holes <= 2 and not hard:
            out.append((x, top))
    return out


def climb(n, depth):
    setup()
    cols = shaft_columns(depth)
    record("shaft_columns", candidates=cols)
    for i in range(n):
        seq = tb.events(since=0)[-1].seq if tb.events(since=0) else 0
        p = tb.me()
        if p.dead:
            tb.sleep(p.respawn_ticks + 30)
        x = None
        while cols and x is None:
            cx, sy = cols.pop(0)
            tb.goto(cx, sy, near=0, dig=True, place=True, timeout=90)
            q = tb.me()
            nx, ny = path.node_of(q)
            if q.on_ground and ny == sy and abs(nx - cx) <= 1:
                x = nx
        if x is None:
            record("climb", attempt=i, ok=False, detail="no dry surface column reached", at=list(path.node_of(tb.me())))
            continue
        top = sy
        t0 = time.time()
        torches = platforms = 0
        for seg in range(6, depth + 6, 6):  # dig down 6 rows at a time, light the shaft, a platform every 18 rows
            goal = top + min(seg, depth)
            if not tb.goto(x, goal, near=0, dig=True, place=False, timeout=90):
                break
            torches += bool(tb.place("Torch", x, goal - 1))
            if seg % 18 == 0 and goal < top + depth:
                platforms += bool(tb.place("Wood Platform", x, goal - 4))
        dig_s = round(time.time() - t0, 1)
        f = tb.me().foot_y
        if f - top < 50:
            record("climb", attempt=i, ok=False, detail=f"shaft only {f - top} rows ({path.last_error})", x=x)
            tb.goto(x, top, dig=True, place=True, timeout=200)
            continue
        ceiling = []
        for c in (x, x + 1):
            item = path._pick_block()
            if item and tb.place(item, c, f - 3):
                ceiling.append((c, f - 3))
        b0, k0, t1 = blocks(), tb.me().tick, time.time()
        life0 = tb.me().life
        ok = tb.goto(x, top, dig=True, place=True, timeout=400)
        q = tb.me()
        record("climb", attempt=i, ok=bool(ok), x=x, rows=f - top, dig_down_s=dig_s, climb_wall_s=round(time.time() - t1, 1),
               climb_game_s=round((q.tick - k0) / 60, 1), blocks_used=b0 - blocks(), blocks_left=blocks(),
               torches_in_shaft=torches, platforms_in_shaft=platforms, ceiling_blocks=ceiling,
               end=list(path.node_of(q)), goal=[x, top], life=[life0, q.life], deaths=deaths_since(seq),
               last_error=path.last_error)
        if not ok:
            tb.goto(x, top, dig=True, place=True, timeout=300)


def last_seq():
    ev = tb.events(since=0)
    return ev[-1].seq if ev else 0


def walk_to(x, y, near=4, legs=20):
    """goto a far surface spot leg by leg (each call approaches a far goal through its planning window)."""
    for _ in range(legs):
        if tb.me().dead:
            tb.sleep(tb.me().respawn_ticks + 30)
        if tb.goto(x, y, near=near, dig=False, place=False, timeout=120):
            return True
    return False


def pond(spec=None):
    """Test-only (truth): the pond spec = (left, right, surface row) (located with truth_tiles beforehand), or else
    the nearest surface pond >= 4 columns wide and >= 3 rows deep within 750 columns. Walk to it (revealing it);
    return (left, right, surface, depth, grid of what the player sees) or None."""
    p = tb.me()
    if spec:
        l, r, s = spec
        g = tb.Grid.from_reply(call("truth_tiles", x0=l - 40, y0=s - 30, x1=r + 40, y1=s + 40))
        found = _shape(g, l, s)
        offs = ()
    else:
        found, offs = None, (0, -300, 300, -600, 600)
    for off in offs:
        g = tb.Grid.from_reply(call("truth_tiles", x0=p.tile_x + off - 150, y0=p.foot_y - 30, x1=p.tile_x + off + 150,
                                    y1=p.foot_y + 40))
        found = _pond_in(g, p)
        if found:
            break
    if not found:
        return None
    l, r, s, depth = found
    walk_to(l - 4, s - 1)
    return l, r, s, depth, tb.tiles(l - 15, s - 15, r + 15, s + depth + 3)


def _shape(g, x, s):
    """(left, right, surface row, depth at the middle column) of the water surface run through (x, s) in grid g."""
    l, r = x, x
    while g.liquid(l - 1, s) == "water":
        l -= 1
    while g.liquid(r + 1, s) == "water":
        r += 1
    depth = 0
    while g.liquid((l + r) // 2, s + depth) == "water":
        depth += 1
    return l, r, s, depth


def _pond_in(g, p):
    """(left, right, surface row, depth) of the nearest pond >= 4 wide and >= 3 deep in truth grid g, or None."""
    cands = sorted((abs(x - p.tile_x), x, y) for y in range(g.y0 + 1, g.y0 + g.h) for x in range(g.x0, g.x0 + g.w)
                   if g.liquid(x, y) == "water" and not g.solid(x, y - 1) and not g.liquid(x, y - 1))
    for _, x, s in cands:
        l, r, _, depth = _shape(g, x, s)
        open_air = all(not g.solid(c, s - k) for c in range(l - 1, r + 2) for k in range(1, 6))
        if r - l + 1 >= 4 and depth >= 3 and open_air:
            return l, r, s, depth
    return None


class Samples:
    """Wraps tb.path._state (the executor's me() reads) to log (breath, submerged, wet, life) on every read."""
    def __init__(self):
        self.rows, self.orig = [], path._state

    def __enter__(self):
        def state():
            q = self.orig()
            self.rows.append((q["breath"], q["submerged"], q["wet"], q["life"]))
            return q
        path._state = state
        return self

    def __exit__(self, *exc):
        path._state = self.orig

    def summary(self):
        r = self.rows
        return dict(min_breath=min((x[0] for x in r), default=None), submerged_reads=sum(x[1] for x in r),
                    wet_reads=sum(x[2] for x in r), reads=len(r), life_min=min((x[3] for x in r), default=None))


def stranded(bank, goal, kind, label, sm):
    """Case 'no_exit': from dry `bank`, a goal reachable only through deep water with no dry exit: path_to must be
    None and goto False, and the player must not get wet (every executor read checked)."""
    tb.goto(*bank, near=0, dig=False, place=False, timeout=60)
    q0 = tb.me()
    if path._goal_dist(path.node_of(q0), bank) > 1:
        record("no_exit", kind=kind, fixture=label, ok=False, detail="bank not reached", bank=list(bank),
               at=list(path.node_of(q0)), last_error=path.last_error)
        return
    steps = tb.path_to(*goal, dig=False, place=False)
    sm.rows.clear()
    seq, t0 = last_seq(), time.time()
    ok = tb.goto(*goal, near=0, dig=False, place=False, timeout=60)
    q = tb.me()
    s = sm.summary()
    record("no_exit", kind=kind, fixture=label, ok=steps is None and not ok and not s["wet_reads"] and not q.wet,
           start=list(path.node_of(q0)), goal=list(goal), plan=None if steps is None else [st.kind for st in steps],
           goto=bool(ok), end=list(path.node_of(q)), end_wet=bool(q.wet), wall_s=round(time.time() - t0, 1),
           deaths=deaths_since(seq), last_error=path.last_error, **s)


def water(n=1, spec=None, label="natural"):
    """Case pond_bottom (no_exit), then n swim round trips over the pond, then breath fields while submerged."""
    call("truth_morning")
    tb.sleep(30)
    found = pond(spec)
    if not found:
        record("water", ok=False, detail="no revealed pond within 750 columns")
        return
    l, r, s, depth, g = found
    record("pond", left=l, right=r, surface=s, depth=depth, width=r - l + 1, fixture=label,
           at=list(path.node_of(tb.me())))
    banks = []
    for side, xs in ((-1, range(l - 2, l - 16, -1)), (1, range(r + 2, r + 16))):
        for x in xs:
            y = surface_row(x, s - 2, span=12)
            if y is not None and y <= s + 1:
                banks.append((x, y))
                break
    if len(banks) < 2:
        record("water", ok=False, detail=f"banks {banks}")
        return
    a, b = banks
    with Samples() as sm:
        stranded(a, ((l + r) // 2, s + depth - 1), "pond_bottom", label, sm)
        for rep in range(n):
            call("truth_morning")
            for name, (frm, to) in (("swim_across", (a, b)), ("swim_back", (b, a))):
                tb.goto(*frm, near=0, dig=False, place=False, timeout=60)
                steps = tb.path_to(*to, dig=False, place=False)
                heads = [] if steps is None else [st.to for st in steps
                                                  if any(g.liquid(st.to[0] + i, st.to[1] - j) for i in (0, 1) for j in (1, 2))]
                sm.rows.clear()
                q0 = tb.me()
                k0, t0, seq = q0.tick, time.time(), last_seq()
                ok = tb.goto(*to, near=1, dig=False, place=False, timeout=90)
                q = tb.me()
                record(name, rep=rep, fixture=label, ok=bool(ok), frm=list(frm), start=list(path.node_of(q0)), to=list(to),
                       end=list(path.node_of(q)), steps=None if steps is None else [st.kind for st in steps],
                       planned_head_wet=heads, wall_s=round(time.time() - t0, 1), game_s=round((q.tick - k0) / 60, 1),
                       life=[q0.life, q.life], deaths=deaths_since(seq), last_error=path.last_error, **sm.summary())
        # breath fields while the head is under water: walk in, hold down to sink, read me(), then goto out; goto
        # cannot start from deep water, so then the script does the agent's job: swim up toward the bank
        tb.goto(*a, near=0, dig=False, place=False, timeout=60)
        d = 1 if b[0] > a[0] else -1
        reads = []
        for _ in range(40):
            tb.hold(["right" if d > 0 else "left", "down"], 6)
            q = tb.me()
            reads.append((q.breath, q.breath_max, q.submerged, q.wet, q.life))
            if q.submerged and q.breath < q.breath_max - 15:
                break
        ok = tb.goto(*b, near=1, dig=False, place=False, timeout=60) or tb.goto(*a, near=1, dig=False, place=False, timeout=60)
        goto_err, swam_out = path.last_error, False
        if not ok:
            for _ in range(60):
                q = tb.me()
                if q.on_ground and not q.wet:
                    break
                tb.hold(["right" if d > 0 else "left", "jump"], 6)
                tb.hold(["right" if d > 0 else "left"], 2)
            swam_out = tb.goto(*b, near=1, dig=False, place=False, timeout=30)
        q = tb.me()
        record("breath_fields", fixture=label, ok=any(rr[2] for rr in reads) and min(rr[0] for rr in reads) < reads[0][1],
               reads=reads[-8:], first=reads[0], breath_ticks_per_point=q.breath_ticks_per_point, goto_out=bool(ok),
               goto_out_error=goto_err, script_swam_out=bool(swam_out), end=[q.breath, q.submerged, q.life])


if __name__ == "__main__":
    mode = sys.argv[2]
    nums = [int(v) for v in sys.argv[3:] if v.lstrip("-").isdigit()]
    label = "fixture" if "fixture" in sys.argv[3:] else "natural"
    if mode == "climb":
        climb(nums[0] if nums else 3, nums[1] if len(nums) > 1 else 55)
    elif mode == "stranded":
        call("truth_morning")
        walk_to(*nums[:2], near=0)
        with Samples() as sm:
            stranded(tuple(nums[:2]), tuple(nums[2:4]), "goal_beyond_deep_water", label, sm)
    else:
        water(nums[0] if nums else 1, spec=tuple(nums[1:4]) if len(nums) >= 4 else None, label=label)
