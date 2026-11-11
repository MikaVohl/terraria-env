# timeout: 900
# Step 2: gel from slimes (torches need it). Patrol the surface near home (turn back at corruption/crimson or
# after 40 columns), fight what comes, pick up drops. Rest when hurt. Stop in time to be underground before dusk.
import time
import tb
from lib.botlib import fight, collect, say, gather_wood, recover, wait_alive, clock_min

t0, direction = time.time(), 1
home = tb.store.get("home") or [tb.me().tile_x, tb.me().foot_y]


def enough():
    gel, t, clock = tb.count("Gel"), time.time() - t0, clock_min()
    return gel >= 16 or t > 540 or clock >= 16 * 60 or (gel >= 8 and (t > 420 or clock >= 15 * 60))


while not enough():
    if wait_alive():
        continue
    p = tb.me()
    if p.life < 50:
        say("resting at life", p.life)
        recover(85, max_ticks=2400)
        continue
    slimes = [n for n in tb.npcs(40) if n.hostile and "Slime" in n.name]
    if slimes:
        s = min(slimes, key=lambda n: abs(n.x - p.x))
        if abs(s.x - p.x) > 2:
            tb.goto(int(s.x), int(s.y + s.height / 2) - 1, near=2, timeout=4, dig=False, place=False)
        fight(radius=5)
        collect(radius=10, names={"Gel"})
        say("gel", tb.count("Gel"), "life", tb.me().life)
        continue
    fight()
    if set(p.biomes) & {"corruption", "crimson"} or abs(p.tile_x - home[0]) > 40:
        direction = 1 if p.tile_x < home[0] else -1
    if not tb.goto(p.tile_x + 10 * direction, p.foot_y, near=3, timeout=6, dig=False, place=False):
        direction = -direction
    collect(radius=10)
say("gel", tb.count("Gel"), "wood", tb.count("Wood"), tb.time().clock, round(time.time() - t0), "s")
if tb.count("Wood") < 40:
    gather_wood(45)
