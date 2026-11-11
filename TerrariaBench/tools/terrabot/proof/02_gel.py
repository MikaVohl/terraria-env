# timeout: 900
# Step 2: gel from slimes (torches need it). Patrol the surface near home (turn back at corruption/crimson or
# after 40 columns), fight what comes, pick up drops.
import time
import tb
from lib.botlib import fight, collect, say, gather_wood

t0, direction = time.time(), 1
home = tb.store.get("home") or [tb.me().tile_x, tb.me().foot_y]
while tb.count("Gel") < 12 and time.time() - t0 < 840:
    p = tb.me()
    if p.dead:
        tb.sleep(60)
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
say("gel", tb.count("Gel"), "wood", tb.count("Wood"), tb.time().clock)
if tb.count("Wood") < 25:
    gather_wood(30)
