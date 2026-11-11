"""Host-side collection costs without a policy: VecTerraria.step (C batch step + wrapper),
RecipePotential.step and CellNovelty.step on random legal actions, ms per batch step.

    TERRARIA_LITE_LIB=... PYTHONPATH=python python perf/v10/collect_probe.py [--envs 1024] [--steps 300]
        [--workers 12] [--cprofile potential|novelty|sim]
"""
import argparse
import cProfile
import pstats
import time

import numpy as np

from terraria_lite.ppo_agent import VecTerraria
from terraria_lite.potential import RecipePotential
from terraria_lite.count_novelty import CellNovelty

p = argparse.ArgumentParser()
p.add_argument("--envs", type=int, default=1024)
p.add_argument("--steps", type=int, default=300)
p.add_argument("--warmup", type=int, default=200)
p.add_argument("--workers", type=int, default=12)
p.add_argument("--cprofile", default="")
a = p.parse_args()
envs = VecTerraria(a.envs, seed=1, workers=a.workers, native_autoreset=True, compact=True)
obs, mask = envs.reset()
obs, mask = np.asarray(obs), np.asarray(mask)
pot = RecipePotential(obs, .9999, 3.0, "frontier")
nov = CellNovelty(obs)
rng = np.random.default_rng(0)
T = {"sim": 0.0, "potential": 0.0, "novelty": 0.0}
prof = cProfile.Profile() if a.cprofile else None
for t in range(a.warmup + a.steps):
    act = np.array([rng.choice(np.flatnonzero(m)) for m in mask])
    timed = t >= a.warmup
    if timed and prof and a.cprofile == "sim":
        prof.enable()
    t0 = time.perf_counter()
    o, m, r, term, trunc, final, fin = envs.step(act)
    t1 = time.perf_counter()
    if prof and a.cprofile == "sim":
        prof.disable()
    o, m, final = np.asarray(o), np.asarray(m), np.asarray(final)
    ended = term | trunc
    if timed and prof and a.cprofile == "novelty":
        prof.enable()
    t2 = time.perf_counter()
    nov.step(o, final, ended)
    t3 = time.perf_counter()
    if prof:
        prof.disable()
    if timed and prof and a.cprofile == "potential":
        prof.enable()
    pot.step(o, final, ended)
    t4 = time.perf_counter()
    if prof:
        prof.disable()
    mask = m
    if timed:
        T["sim"] += t1 - t0; T["novelty"] += t3 - t2; T["potential"] += t4 - t3
print({k: round(1e3 * v / a.steps, 3) for k, v in T.items()}, "ms per batch step")
if prof:
    pstats.Stats(prof).sort_stats("tottime").print_stats(18)
