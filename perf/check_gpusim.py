"""Exactness check: terraria_lite.gpusim.GpuVec against VecTerraria (C
autoreset), same actions, compact and flat observations: obs, mask, reward,
ends, final rows of finished lanes, infos and seed counter.

    HIP_VISIBLE_DEVICES=7 PYTHONPATH=python python perf/check_gpusim.py --envs 1024 --steps 3000
"""
import argparse

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--envs", type=int, default=1024)
    p.add_argument("--steps", type=int, default=3000)
    a = p.parse_args()
    from terraria_lite.gpusim import GpuVec
    from terraria_lite.ppo_agent import VecTerraria
    pairs = {c: (VecTerraria(a.envs, seed=901 * 10_000_000, workers=16, native_autoreset=True, compact=c),
                 GpuVec(a.envs, seed=901 * 10_000_000, compact=c)) for c in (True, False)}
    for cpu, gpu in pairs.values():
        oc, mc = cpu.reset(); og, mg = gpu.reset()
        assert np.array_equal(oc.view(np.uint8), og.view(np.uint8)) and np.array_equal(mc, mg)
    rng = np.random.default_rng(11)
    episodes = 0
    for t in range(a.steps):
        cpu0 = pairs[True][0]
        act = np.array([rng.choice(np.flatnonzero(m)) for m in cpu0.mask], dtype=np.int64)
        for c, (cpu, gpu) in pairs.items():
            rc, rg = cpu.step(act), gpu.step(act)
            for k, name in enumerate(("obs", "mask", "reward", "terminated", "truncated")):
                assert np.array_equal(np.asarray(rc[k]).view(np.uint8), np.asarray(rg[k]).view(np.uint8)), (c, t, name)
            ended = rc[3] | rc[4]
            assert np.array_equal(rc[5][ended].view(np.uint8), rg[5][ended].view(np.uint8)), (c, t, "final")
            assert rc[6] == rg[6], (c, t, "infos")
            assert cpu._next_seed == gpu._next_seed, (c, t, "seed")
        episodes += int(ended.sum())
    print(f"OK: {a.envs} envs x {a.steps} steps, {episodes} resets; GPU backend (compact and flat) identical to "
          f"VecTerraria (obs, mask, reward, ends, final rows, infos, seeds)")


if __name__ == "__main__":
    main()
