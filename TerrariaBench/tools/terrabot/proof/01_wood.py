# timeout: 600
# Scripted proof, step 1: wood from the nearest trees, then a work bench to make a wooden sword (tb API only).
import tb
from lib.botlib import gather_wood, say, fight, place_station, collect

fight()
ok = gather_wood(50)
say("wood", tb.count("Wood"), "ok" if ok else "short", "at", tb.me().x, tb.me().y, tb.time().clock)
tb.store["home"] = [tb.me().tile_x, tb.me().foot_y]
tb.craft("Work Bench")
bx, by = place_station("Work Bench", 2, 2)
tb.craft("Wooden Sword")
say("bench at", bx, by, "sword:", tb.count("Wooden Sword"), "stations", tb.me().stations_near)
tb.mine(bx, by)
for _ in range(3):
    tb.sleep(30)
    collect(radius=8, names={"Work Bench"})
    if tb.count("Work Bench"):
        break
say("carrying bench:", tb.count("Work Bench"), "wood", tb.count("Wood"))
