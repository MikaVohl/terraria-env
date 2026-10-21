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

mode="frontier" averages only over recipes whose achievement is not yet
earned in the episode (read from the observed achievement bits). The plain
mean dilutes each recipe's pull by the 19-recipe average, so late, large
recipes (30-wood breastplate, 25-bar chainmail, pickaxes) contribute almost
nothing; the frontier keeps the pull on what is still unearned. Phi is still a
function of the state alone, so the shaping remains potential-based.
mode="frontier_surface" adds one more frontier goal, "return to surface":
after "descend deep" its progress is the climb fraction from the deep row to
the nominal surface (observed depth), until the achievement is earned.
"""
from __future__ import annotations

import numpy as np

from terraria_lite import SPEC
from terraria_lite.cells import achievements, depth_rows, inventory, stations_visible, STATION_TILES
from terraria_lite.rules import player_knowledge

_STATION_INDEX = {SPEC.tile_names[t]: i for i, t in enumerate(STATION_TILES)}
# Recipe -> achievement it unlocks (None: no achievement), by the game's names.
_RECIPE_ACH = {"workbench": "craft workbench", "furnace": "craft furnace", "torch x3": None,
               "campfire": None, "platform x2": None, "copper bar": "smelt copper", "iron bar": "smelt iron",
               "silver bar": "smelt silver", "gold bar": "smelt gold", "anvil": "craft anvil",
               "iron pickaxe": "craft iron pickaxe", "gold pickaxe": "craft gold pickaxe",
               "wooden sword": "craft wooden sword", "copper sword": "craft metal sword",
               "iron sword": "craft metal sword", "silver sword": "craft metal sword",
               "gold sword": "craft metal sword", "wood breastplate": "craft wood breastplate",
               "iron chainmail": "craft iron chainmail"}
# include/env.h (v4 and v7): "descend deep" at row >= DEEP_Y; "return to surface"
# needs that achievement and the player above the surface (SURFACE_BASE nominal).
DEEP_Y, SURFACE_BASE = 70, 30


class RecipePotential:
    def __init__(self, initial_obs: np.ndarray, gamma: float, coef: float = 1.0, mode: str = "mean"):
        if mode not in ("mean", "frontier", "frontier_surface"):
            raise ValueError(f"unknown potential mode {mode!r}")
        recipes = player_knowledge()["recipes"]
        self.gamma, self.coef, self.mode = gamma, coef, mode
        if mode != "mean":
            # Every recipe name must be mapped, so a renamed recipe fails loudly.
            self.ach = np.array([-1 if _RECIPE_ACH[r["name"]] is None
                                 else SPEC.achievement_names.index(_RECIPE_ACH[r["name"]]) for r in recipes])
            self._deep = SPEC.achievement_names.index("descend deep")
            self._back = SPEC.achievement_names.index("return to surface")
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

    def _phi_rows(self, inv: np.ndarray, vis: np.ndarray, ach=None, y=None) -> np.ndarray:
        held = np.where(self.need > 0, np.minimum(inv[:, None, :] / np.maximum(self.need, 1), 1.0), 0.0).sum(-1)
        has_station = self.station >= 0
        held[:, has_station] += vis[:, self.station[has_station]]
        if self.mode == "mean":
            return self.coef * (held / self.terms).mean(-1)
        prog = held / self.terms
        open_ = (self.ach >= 0) & ((ach[:, None] >> np.maximum(self.ach, 0)) & 1 == 0)
        if y is not None:
            # One more frontier goal: climb fraction from DEEP_Y to the nominal
            # surface, counted only after "descend deep" (0 before, so earning
            # it is continuous), open until "return to surface" is earned.
            deep = (ach >> self._deep) & 1 == 1
            climb = np.where(deep, np.clip((DEEP_Y - y) / (DEEP_Y - SURFACE_BASE), 0.0, 1.0), 0.0)
            prog = np.concatenate((prog, climb[:, None]), 1)
            open_ = np.concatenate((open_, ((ach >> self._back) & 1 == 0)[:, None]), 1)
        n = open_.sum(-1)
        return self.coef * np.where(n > 0, (prog * open_).sum(-1) / np.maximum(n, 1), 0.0)

    def _inputs(self, obs: np.ndarray):
        inputs = (inventory(obs).astype(np.float64), stations_visible(obs))
        if self.mode != "mean":
            inputs += (achievements(obs),)
        if self.mode == "frontier_surface":
            inputs += (depth_rows(obs),)
        return inputs

    def _phi_from(self, inv: np.ndarray, vis: np.ndarray, *extra) -> np.ndarray:
        key = np.concatenate((inv[:, self._items], vis) + tuple(x[:, None] for x in extra), 1)
        if self._key is None or len(self._key) != len(key):
            self._key, self._val = key, self._phi_rows(inv, vis, *extra)
            return self._val.copy()
        stale = np.flatnonzero((key != self._key).any(1))
        if len(stale):
            self._val[stale] = self._phi_rows(inv[stale], vis[stale], *(x[stale] for x in extra))
            self._key[stale] = key[stale]
        return self._val.copy()

    def phi(self, obs: np.ndarray) -> np.ndarray:
        return self._phi_from(*self._inputs(obs))

    def step(self, next_obs: np.ndarray, final_obs: np.ndarray, ended: np.ndarray) -> np.ndarray:
        """phi of each lane's reached state (the terminal observation where the
        episode ended), without materialising the mixed observation batch."""
        inputs = self._inputs(next_obs)
        if ended.any():
            reached_inputs = tuple(x.copy() for x in inputs)
            for x, f in zip(reached_inputs, self._inputs(final_obs[ended])):
                x[ended] = f
            reached = self._phi_from(*reached_inputs)
        else:
            reached = self._phi_from(*inputs)
        reached[ended] = 0.0
        shaping = self.gamma * reached - self.previous
        self.previous = self._phi_from(*inputs) if ended.any() else reached
        return shaping.astype(np.float32)
