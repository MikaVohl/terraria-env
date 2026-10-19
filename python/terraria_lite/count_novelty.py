"""Count-based novelty over coarse progress cells (see cells.py).

RND over raw observations rewarded terrain novelty and never reached the
furnace. Here novelty is measured on the compact progress cell instead: a bonus
is paid the first time an episode enters a cell, scaled by 1/sqrt(global visits
of that cell). Holding more of any item, seeing a station, unlocking anything or
reaching a new depth band can therefore pay once per episode, fading as the
cell becomes familiar across training. No recipe or goal is encoded.

Training-only: the simulator reward and every evaluation remain extrinsic.
"""
from __future__ import annotations

import numpy as np

from terraria_lite.cells import cell_keys


class CellNovelty:
    def __init__(self, initial_obs: np.ndarray):
        self.counts: dict[int, int] = {}
        self.seen = [set() for _ in range(len(initial_obs))]
        self._enter(np.arange(len(initial_obs)), cell_keys(initial_obs))
        self.paid = 0

    def _enter(self, lanes, keys):
        for lane, key in zip(lanes.tolist(), keys.tolist()):
            self.seen[lane] = {key}
            self.counts[key] = self.counts.get(key, 0) + 1

    def step(self, next_obs: np.ndarray, final_obs: np.ndarray, ended: np.ndarray) -> np.ndarray:
        """Bonus for the transition just taken; `next_obs` is already autoreset."""
        reached = next_obs.copy() if ended.any() else next_obs
        if ended.any():
            reached[ended] = final_obs[ended]
        keys = cell_keys(reached).tolist()
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
            self._enter(restarted, cell_keys(next_obs[restarted]))
        self.paid += int((bonus > 0).sum())
        return bonus

    def stats(self) -> dict:
        return {"novelty_cells": len(self.counts), "novelty_paid": self.paid}
