"""Exactness check for the shaping fast paths: tl_cells_decode (cells.decode /
cell_keys on compact rows), the memoised RecipePotential (all modes) and the
vectorised CellNovelty, against the NumPy definitions and the plain per-lane
loops of main d397bda (copied below). Everything must match bit for bit.

Sources: a live uniform-legal rollout with autoresets (compact rows, plus the
flat rows of a twin batch), and optionally recorded traces
(perf/shaping_trace.py) of a trained policy.

    PYTHONPATH=python python perf/check_shaping.py --envs 1024 --steps 1500 [--trace /tmp/trace.npz ...]
"""
import argparse
import time

import numpy as np

from terraria_lite import SPEC


# ---- references: main d397bda -------------------------------------------------

def ref_cell_keys(obs):
    """cells.cell_keys (NumPy, either representation)."""
    from terraria_lite.cells import cell_parts
    obs = np.atleast_2d(obs)
    p = cell_parts(obs)
    h = p["achievements"].astype(np.uint64)
    mult = np.uint64(0x9E3779B97F4A7C15)
    for col in np.concatenate((p["inventory_bins"], p["stations"].astype(np.int64),
                               p["depth"][:, None]), axis=1).T:
        h = (h * mult) ^ col.astype(np.uint64)
    return h.view(np.int64)


class RefNovelty:
    """count_novelty.CellNovelty (per-lane dict loop)."""

    def __init__(self, initial_obs):
        self.counts = {}
        self.seen = [set() for _ in range(len(initial_obs))]
        self._enter(np.arange(len(initial_obs)), ref_cell_keys(initial_obs))
        self.paid = 0

    def _enter(self, lanes, keys):
        for lane, key in zip(lanes.tolist(), keys.tolist()):
            self.seen[lane] = {key}
            self.counts[key] = self.counts.get(key, 0) + 1

    def step(self, next_obs, final_obs, ended):
        reached = next_obs.copy() if ended.any() else next_obs
        if ended.any():
            reached[ended] = final_obs[ended]
        keys = ref_cell_keys(reached).tolist()
        bonus = np.zeros(len(keys), dtype=np.float32)
        counts = self.counts
        for lane, key in enumerate(keys):
            n = counts.get(key, 0) + 1
            counts[key] = n
            if key not in self.seen[lane]:
                self.seen[lane].add(key)
                bonus[lane] = n ** -0.5
        restarted = np.flatnonzero(ended)
        if len(restarted):
            self._enter(restarted, ref_cell_keys(next_obs[restarted]))
        self.paid += int((bonus > 0).sum())
        return bonus

    def stats(self):
        return {"novelty_cells": len(self.counts), "novelty_paid": self.paid}


class RefPotential:
    """potential.RecipePotential evaluated densely (no memo) from the NumPy cells functions."""

    def __init__(self, fast, initial_obs):
        self.f = fast   # recipe tables and constants only
        self.previous = self.phi(initial_obs)

    def phi(self, obs):
        from terraria_lite.cells import achievements, depth_rows, inventory, stations_visible
        from terraria_lite.potential import DEEP_Y, SURFACE_BASE
        f = self.f
        inv = inventory(obs).astype(np.float64)
        vis = stations_visible(obs)
        held = np.where(f.need > 0, np.minimum(inv[:, None, :] / np.maximum(f.need, 1), 1.0), 0.0).sum(-1)
        has_station = f.station >= 0
        held[:, has_station] += vis[:, f.station[has_station]]
        if f.mode == "mean":
            return f.coef * (held / f.terms).mean(-1)
        ach = achievements(obs)
        prog = held / f.terms
        open_ = (f.ach >= 0) & ((ach[:, None] >> np.maximum(f.ach, 0)) & 1 == 0)
        if f.mode == "frontier_surface":
            y = depth_rows(obs)
            deep = (ach >> f._deep) & 1 == 1
            climb = np.where(deep, np.clip((DEEP_Y - y) / (DEEP_Y - SURFACE_BASE), 0.0, 1.0), 0.0)
            prog = np.concatenate((prog, climb[:, None]), 1)
            open_ = np.concatenate((open_, ((ach >> f._back) & 1 == 0)[:, None]), 1)
        n = open_.sum(-1)
        return f.coef * np.where(n > 0, (prog * open_).sum(-1) / np.maximum(n, 1), 0.0)

    def step(self, next_obs, final_obs, ended):
        reached = self.phi(np.where(ended[:, None], final_obs, next_obs) if ended.any() else next_obs)
        reached[ended] = 0.0
        shaping = self.f.gamma * reached - self.previous
        self.previous = self.phi(next_obs) if ended.any() else reached
        return shaping.astype(np.float32)


# ---- checks -------------------------------------------------------------------

MODES = ("mean", "frontier", "frontier_surface")


class Pair:
    """Fast and reference shaping side by side on one observation stream."""

    def __init__(self, first, coef):
        from terraria_lite.count_novelty import CellNovelty
        from terraria_lite.potential import RecipePotential
        self.pot = {m: RecipePotential(first, .999, coef, m) for m in MODES}
        self.ref = {m: RefPotential(RecipePotential(first, .999, coef, m), first) for m in MODES}
        self.nov, self.ref_nov = CellNovelty(first), RefNovelty(first)
        self.nonzero = {m: 0 for m in MODES}
        self.bonus = 0
        self.t_fast = self.t_ref = 0.0

    def step(self, obs, final, ended, where):
        from terraria_lite.cells import achievements, decode, depth_rows, inventory, stations_visible
        for rows in (obs, final[ended]):
            d = decode(rows, keys=True)
            assert np.array_equal(d["inventory"], inventory(rows)), where
            assert np.array_equal(d["stations"], stations_visible(rows)), where
            assert np.array_equal(d["achievements"], achievements(rows)), where
            assert np.array_equal(d["depth_rows"], depth_rows(rows)), where
            assert np.array_equal(d["keys"], ref_cell_keys(rows)), where
        for m in MODES:
            t0 = time.perf_counter()
            got = self.pot[m].step(obs, final, ended)
            t1 = time.perf_counter()
            want = self.ref[m].step(obs, final, ended)
            self.t_fast += t1 - t0; self.t_ref += time.perf_counter() - t1
            assert np.array_equal(got.view(np.uint32), want.view(np.uint32)), (where, m)
            self.nonzero[m] += int(np.count_nonzero(want))
        t0 = time.perf_counter()
        got = self.nov.step(obs, final, ended)
        t1 = time.perf_counter()
        want = self.ref_nov.step(obs, final, ended)
        self.t_fast += t1 - t0; self.t_ref += time.perf_counter() - t1
        assert np.array_equal(got.view(np.uint32), want.view(np.uint32)), (where, "novelty")
        assert self.nov.stats() == self.ref_nov.stats(), (where, self.nov.stats(), self.ref_nov.stats())
        self.bonus += int(np.count_nonzero(want))

    def report(self, label, steps, envs, ends):
        print(f"OK {label}: {envs} envs x {steps} steps, {ends} episode ends; nonzero shaping "
              f"{self.nonzero}; novelty bonuses {self.bonus}, {self.nov.stats()}; "
              f"shaping time fast {self.t_fast:.1f}s vs reference {self.t_ref:.1f}s", flush=True)


def live(envs, steps, coef):
    from terraria_lite.ppo_agent import VecTerraria
    comp = VecTerraria(envs, seed=901 * 10_000_000, workers=16, native_autoreset=True, compact=True)
    flat = VecTerraria(envs, seed=901 * 10_000_000, workers=16)
    oc, _ = comp.reset(); of, _ = flat.reset()
    pc, pf = Pair(oc, coef), Pair(of, coef)
    rng = np.random.default_rng(3)
    ends = 0
    for t in range(steps):
        act = np.array([rng.choice(np.flatnonzero(m)) for m in comp.mask], dtype=np.int64)
        oc, _, _, tc, uc, fc, _ = comp.step(act)
        of, _, _, tf, uf, ff, _ = flat.step(act)
        assert np.array_equal(tc | uc, tf | uf)
        ends += int((tc | uc).sum())
        pc.step(oc, fc, tc | uc, ("live compact", t))
        pf.step(of, ff, tf | uf, ("live flat", t))
    pc.report("live compact", steps, envs, ends)
    pf.report("live flat", steps, envs, ends)


def trace(path, coef):
    z = np.load(path)
    obs, ended, rows, counts = z["obs"], z["ended"], z["final"], z["final_counts"]
    offs = np.concatenate(([0], np.cumsum(counts)))
    p = Pair(z["first"], coef)
    for t in range(len(obs)):
        final = np.zeros_like(obs[t])
        final[ended[t]] = rows[offs[t]:offs[t + 1]]
        p.step(obs[t], final, ended[t], (path, t))
    p.report(path, len(obs), obs.shape[1], int(counts.sum()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--envs", type=int, default=1024)
    p.add_argument("--steps", type=int, default=1500)
    p.add_argument("--coef", type=float, default=3.0)
    p.add_argument("--trace", nargs="*", default=[])
    a = p.parse_args()
    if a.steps:
        live(a.envs, a.steps, a.coef)
    for path in a.trace:
        trace(path, a.coef)


if __name__ == "__main__":
    main()
