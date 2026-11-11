# timeout: 300
# Step 3: torches at the work bench (the carried one, else a new one), then carry the bench underground.
import tb
from lib.botlib import say, make_torches, wait_alive

wait_alive()
make_torches(keep_wood=16)
say("torches", tb.count("Torch"), "wood", tb.count("Wood"), "gel", tb.count("Gel"), "carrying bench:",
    tb.count("Work Bench"), tb.time().clock)
