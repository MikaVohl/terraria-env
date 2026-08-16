"""Random-policy baseline, driven through the Python binding.

This is the end-to-end check on the binding: the same statistics measured in C
should come back out through ctypes. If they do, observations, rewards and the
episode flags are all crossing the boundary intact.

It is also the number any learner has to beat. A policy that cannot clear the
random baseline is not learning, it is decorating.

    make lib && python3 python/random_agent.py [episodes]
"""

import sys
import time
from collections import Counter

import numpy as np

from terraria_lite import SPEC, TerrariaLite


def run(episodes: int = 200, seed0: int = 1) -> None:
    env = TerrariaLite()
    rng = np.random.default_rng(0)

    got = np.zeros(SPEC.n_achievements, dtype=np.int64)
    totals, lengths, returns = [], [], []
    deaths = 0
    first_steps = []

    t0 = time.perf_counter()
    steps = 0
    for ep in range(episodes):
        obs, info = env.reset(seed=seed0 + ep)
        assert obs.shape == (SPEC.obs_size,), obs.shape
        first = None
        while True:
            obs, r, terminated, truncated, info = env.step(
                int(rng.integers(SPEC.n_actions)))
            steps += 1
            if first is None and info["achievements"]:
                first = info["steps"]
            if terminated or truncated:
                break
        deaths += terminated
        totals.append(info["achievements"])
        lengths.append(info["steps"])
        returns.append(info["episode_return"])
        if first is not None:
            first_steps.append(first)
        mask = info["achievement_mask"]
        for i in range(SPEC.n_achievements):
            got[i] += (mask >> i) & 1
    dt = time.perf_counter() - t0

    print(f"{SPEC}\n")
    print(f"random policy, {episodes} episodes")
    print(f"  mean achievements   {np.mean(totals):.2f} / {SPEC.n_achievements}")
    print(f"  mean return         {np.mean(returns):+.2f}")
    print(f"  mean episode        {np.mean(lengths):.0f} steps")
    print(f"  died                {100 * deaths // episodes}%")
    if first_steps:
        print(f"  first achievement   {np.mean(first_steps):.0f} steps "
              f"(in {100 * len(first_steps) // episodes}% of episodes)")
    print(f"  throughput          {steps / dt:,.0f} steps/s through ctypes\n")

    print("  achievement hit rate:")
    for i, n in enumerate(got):
        if n:
            print(f"    {SPEC.achievement_names[i]:<18} {100 * n // episodes:3d}%")
    walls = [SPEC.achievement_names[i] for i, n in enumerate(got) if not n]
    print(f"\n  never reached ({len(walls)}): {walls[0] if walls else '-'} "
          f"is the first wall")

    print("\n  what the agent actually sees at spawn "
          "(blank = unlit, and therefore unknown):")
    env.reset(seed=seed0)
    for line in env.render_ascii().splitlines():
        print("   |" + line + "|")
    env.close()


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
