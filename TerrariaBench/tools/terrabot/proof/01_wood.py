# timeout: 600
# Scripted proof, step 1: wood from the nearest trees (enough for bench, sword, furnace, torches and a spare bench),
# then a work bench to make a wooden sword; pick the bench up again (tb API only).
import tb
from lib.botlib import gather_wood, say, fight, place_station, pick_up_station

fight()
ok = gather_wood(85)
say("wood", tb.count("Wood"), "ok" if ok else "short", "at", tb.me().x, tb.me().y, tb.time().clock)
tb.store["home"] = [tb.me().tile_x, tb.me().foot_y]
tb.craft("Work Bench")
bx, by = place_station("Work Bench", 2, 2)
tb.craft("Wooden Sword")
say("bench at", bx, by, "sword:", tb.count("Wooden Sword"), "stations", tb.me().stations_near)
say("carrying bench:", pick_up_station(bx, by, "Work Bench", "WorkBenches"), "wood", tb.count("Wood"))
