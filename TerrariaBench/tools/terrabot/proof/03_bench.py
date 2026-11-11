# timeout: 300
# Step 3: torches at the work bench; pick the bench up again to carry it underground.
import tb
from lib.botlib import place_station, say, collect

if not tb.count("Work Bench"):
    tb.craft("Work Bench")
bx, by = place_station("Work Bench", 2, 2)
tb.craft("Torch", tb.count("Gel"))
say("torches", tb.count("Torch"), "wood", tb.count("Wood"), "stations", tb.me().stations_near)
tb.mine(bx, by)
for _ in range(3):
    tb.sleep(30)
    collect(radius=8, names={"Work Bench"})
    if tb.count("Work Bench"):
        break
say("carrying bench:", tb.count("Work Bench"))
