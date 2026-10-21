"""Exactness check: memoised RecipePotential (flat and compact observations)
against the original dense implementation (copied verbatim below), over a
random-action rollout with autoresets. Shaping rewards must match bit for bit.

    PYTHONPATH=python python perf/check_potential.py --envs 1024 --steps 2000
"""
import argparse

import numpy as np


class ReferencePotential:
    """potential.RecipePotential as of main 5e0f125 (dense phi every call)."""

    def __init__(self, initial_obs, gamma, coef, need, terms, station):
        from terraria_lite.cells import inventory, stations_visible
        self.inventory, self.stations_visible = inventory, stations_visible
        self.gamma, self.coef, self.need, self.terms, self.station = gamma, coef, need, terms, station
        self.previous = self.phi(initial_obs)

    def phi(self, obs):
        inv = self.inventory(obs).astype(np.float64)
        held = np.where(self.need > 0, np.minimum(inv[:, None, :] / np.maximum(self.need, 1), 1.0), 0.0).sum(-1)
        vis = self.stations_visible(obs)
        has_station = self.station >= 0
        held[:, has_station] += vis[:, self.station[has_station]]
        return self.coef * (held / self.terms).mean(-1)

    def step(self, next_obs, final_obs, ended):
        reached = self.phi(np.where(ended[:, None], final_obs, next_obs) if ended.any() else next_obs)
        reached[ended] = 0.0
        shaping = self.gamma * reached - self.previous
        self.previous = self.phi(next_obs) if ended.any() else reached
        return shaping.astype(np.float32)


def reference_stations_visible(obs):
    """cells.stations_visible as of main 5e0f125 (flat observations)."""
    from terraria_lite import SPEC
    from terraria_lite.cells import STATION_TILES
    tiles = obs[..., :SPEC.cells * SPEC.tile_kinds].reshape(*obs.shape[:-1], SPEC.cells, SPEC.tile_kinds)
    return tiles[..., list(STATION_TILES)].max(-2) > 0.5


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--envs", type=int, default=1024)
    p.add_argument("--steps", type=int, default=2000)
    a = p.parse_args()
    from terraria_lite.cells import stations_visible
    from terraria_lite.compact import to_flat
    from terraria_lite.potential import RecipePotential
    from terraria_lite.ppo_agent import VecTerraria
    flat = VecTerraria(a.envs, seed=901 * 10_000_000, workers=16)
    comp = VecTerraria(a.envs, seed=901 * 10_000_000, workers=16, native_autoreset=True, compact=True)
    of, _ = flat.reset(); oc, _ = comp.reset()
    pf, pc = RecipePotential(of, .999, 3.0), RecipePotential(oc, .999, 3.0)
    ref = ReferencePotential(of, .999, 3.0, pf.need, pf.terms, pf.station)
    ref.stations_visible = reference_stations_visible
    ref.previous = ref.phi(of)
    rng = np.random.default_rng(3)
    nonzero = 0
    for t in range(a.steps):
        act = np.array([rng.choice(np.flatnonzero(m)) for m in flat.mask], dtype=np.int64)
        of, _, _, tf, uf, ff, _ = flat.step(act)
        oc, _, _, tc, uc, fc, _ = comp.step(act)
        ended = tf | uf
        assert np.array_equal(stations_visible(of), reference_stations_visible(of))
        assert np.array_equal(stations_visible(oc), reference_stations_visible(to_flat(oc)))
        want = ref.step(of, ff, ended)
        for got in (pf.step(of, ff, ended), pc.step(oc, fc, tc | uc)):
            assert np.array_equal(got.view(np.uint32), want.view(np.uint32)), t
        nonzero += int((want != 0).sum())
    print(f"OK: {a.envs} envs x {a.steps} steps; memoised potential (flat and compact) bit-identical to the "
          f"dense reference; {nonzero} nonzero shaping rewards checked")


if __name__ == "__main__":
    main()
