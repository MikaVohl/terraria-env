"""Potential-based shaping over recipe ingredient progress (Ng et al. 1999).

Unlike the other training aids this one encodes game knowledge: the potential
is the mean, over all recipes read from the C recipe table, of how much of each
recipe's ingredient list is held (each ingredient capped at its quantity) plus,
for station recipes, whether that station is visible. Shaping is
F = gamma * Phi(s') - Phi(s) with Phi = 0 at every episode end (death and the
finite deadline alike, matching the zero future value both have in training),
so the optimal policy of the original objective is unchanged. It is a disclosed
prior-knowledge control, not a neutral learner improvement.

Training-only: simulator rewards and evaluations stay extrinsic.
"""
from __future__ import annotations

import numpy as np

from terraria_lite import SPEC
from terraria_lite.cells import inventory, stations_visible, STATION_TILES
from terraria_lite.rules import player_knowledge

_STATION_INDEX = {SPEC.tile_names[t]: i for i, t in enumerate(STATION_TILES)}


class RecipePotential:
    def __init__(self, initial_obs: np.ndarray, gamma: float, coef: float = 1.0):
        recipes = player_knowledge()["recipes"]
        self.gamma, self.coef = gamma, coef
        self.need = np.zeros((len(recipes), SPEC.n_items), dtype=np.float64)
        self.terms = np.zeros(len(recipes))
        self.station = np.full(len(recipes), -1)
        for r, recipe in enumerate(recipes):
            for name, qty in recipe["ingredients"].items():
                self.need[r, SPEC.item_names.index(name)] = qty
            self.terms[r] = len(recipe["ingredients"])
            if recipe["station"] != "air":
                self.station[r] = _STATION_INDEX[recipe["station"]]
                self.terms[r] += 1
        # phi depends only on the held ingredient counts and visible stations.
        # Remember both per lane with the value computed from them, and only
        # re-evaluate rows whose inputs changed (rare: most steps change
        # neither). Each row is still computed by the same dense formula, so
        # every value is bit-identical to evaluating the whole batch.
        self._items = np.flatnonzero(self.need.any(0))
        self._key = self._val = None
        self.previous = self.phi(initial_obs)

    def _phi_rows(self, inv: np.ndarray, vis: np.ndarray) -> np.ndarray:
        held = np.where(self.need > 0, np.minimum(inv[:, None, :] / np.maximum(self.need, 1), 1.0), 0.0).sum(-1)
        has_station = self.station >= 0
        held[:, has_station] += vis[:, self.station[has_station]]
        return self.coef * (held / self.terms).mean(-1)

    def _inputs(self, obs: np.ndarray):
        return inventory(obs).astype(np.float64), stations_visible(obs)

    def _phi_from(self, inv: np.ndarray, vis: np.ndarray) -> np.ndarray:
        key = np.concatenate((inv[:, self._items], vis), 1)
        if self._key is None or len(self._key) != len(key):
            self._key, self._val = key, self._phi_rows(inv, vis)
            return self._val.copy()
        stale = np.flatnonzero((key != self._key).any(1))
        if len(stale):
            self._val[stale] = self._phi_rows(inv[stale], vis[stale])
            self._key[stale] = key[stale]
        return self._val.copy()

    def phi(self, obs: np.ndarray) -> np.ndarray:
        return self._phi_from(*self._inputs(obs))

    def step(self, next_obs: np.ndarray, final_obs: np.ndarray, ended: np.ndarray) -> np.ndarray:
        """phi of each lane's reached state (the terminal observation where the
        episode ended), without materialising the mixed observation batch."""
        inv, vis = self._inputs(next_obs)
        if ended.any():
            reached_inv, reached_vis = inv.copy(), vis.copy()
            reached_inv[ended], reached_vis[ended] = self._inputs(final_obs[ended])
            reached = self._phi_from(reached_inv, reached_vis)
        else:
            reached = self._phi_from(inv, vis)
        reached[ended] = 0.0
        shaping = self.gamma * reached - self.previous
        self.previous = self._phi_from(inv, vis) if ended.any() else reached
        return shaping.astype(np.float32)
