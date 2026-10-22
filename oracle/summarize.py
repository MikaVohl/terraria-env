#!/usr/bin/env python3
"""Summarise oracle results JSONL: score distribution and per-achievement stats."""
import json
import statistics as st
import sys

NAMES = ["collect wood", "collect stone", "place block", "craft workbench", "craft furnace",
         "craft anvil", "place torch", "place platform", "collect copper", "collect iron",
         "collect silver", "collect gold", "smelt copper", "smelt iron", "smelt silver", "smelt gold",
         "defeat Blue Slime", "defeat Cave Bat", "open chest", "craft wooden sword",
         "craft metal sword", "craft wood breastplate", "craft iron chainmail",
         "heal with food or potion", "use life crystal", "double jump", "descend deep",
         "return to surface", "explore 30 columns", "climb rope", "craft iron pickaxe",
         "craft gold pickaxe"]

for path in sys.argv[1:]:
    rs = [json.loads(l) for l in open(path) if l.strip()]
    sc = [r["score"] for r in rs]
    print(f"== {path}: {len(rs)} worlds  mean {st.mean(sc):.2f}  median {st.median(sc)}  "
          f"min {min(sc)}  max {max(sc)}  32/32: {sum(s == 32 for s in sc)}  died {sum(r['died'] for r in rs)}  "
          f"illegal {sum(r['illegal'] for r in rs)}")
    hist = {}
    for s in sc:
        hist[s] = hist.get(s, 0) + 1
    print("   hist", " ".join(f"{k}:{v}" for k, v in sorted(hist.items())))
    for i, n in enumerate(NAMES):
        s = [r["ach_step"][i] for r in rs if r["ach_step"][i] >= 0]
        med = st.median(s) if s else -1
        print(f"   {n:26s} {len(s):4d}/{len(rs)}  median {med:7.0f}  max {max(s) if s else -1:6d}")
