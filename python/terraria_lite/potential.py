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
        self.previous = self.phi(initial_obs)

    def phi(self, obs: np.ndarray) -> np.ndarray:
        inv = inventory(obs).astype(np.float64)
        held = np.where(self.need > 0, np.minimum(inv[:, None, :] / np.maximum(self.need, 1), 1.0), 0.0).sum(-1)
        vis = stations_visible(obs)
        has_station = self.station >= 0
        held[:, has_station] += vis[:, self.station[has_station]]
        return self.coef * (held / self.terms).mean(-1)

    def step(self, next_obs: np.ndarray, final_obs: np.ndarray, ended: np.ndarray) -> np.ndarray:
        reached = self.phi(np.where(ended[:, None], final_obs, next_obs) if ended.any() else next_obs)
        reached[ended] = 0.0
        shaping = self.gamma * reached - self.previous
        self.previous = self.phi(next_obs) if ended.any() else reached
        return shaping.astype(np.float32)
