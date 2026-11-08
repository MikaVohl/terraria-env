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
after "descend deep" (v9: "reach the caverns") its progress is the climb
fraction from the deep row to the nominal surface (observed depth), until the
achievement is earned.

v9 (docs/ENV_V9_DESIGN.md): the recipe table includes the Suspicious Looking
Eye (6 lenses at a Demon Altar, so lens collection is its ingredient progress)
and gold chainmail. Both frontier modes add the rest of the boss chain as two
goals, open until earned: "summon the Eye of Cthulhu", progress
0.5 * holding the eye + 0.5 * holding it at night; and "defeat the Eye of
Cthulhu", progress (after the summon) boss present * (0.25 + 0.75 * damage
dealt fraction). Both read only observed status (inventory, night bit, boss
present / HP fraction).

v10 adds two tier-4 stepping stones as frontier goals (both frontier modes,
only when the library has the achievement, so older libraries are unchanged),
open until earned: "hold 6 lenses", progress min(lens / need, 1) with need the
Suspicious Looking Eye's lens quantity (EYE_LENSES), the same capped-count
form as recipe ingredients; and "find a Demon Altar", progress
0.5 * descent + 0.5 * altar visible. Altars only generate in the caverns, so
descent is the fraction from the nominal surface to the deep/cavern row
(observed depth), held at 1 once "reach the caverns" is earned (continuous at
the unlock, and no downward pull that would fight the climb goal afterwards);
"altar visible" is the demon-altar station bit of the view (the achievement
itself needs the altar within crafting range, a subset of the view).
"""
from __future__ import annotations

import numpy as np

from terraria_lite import SPEC
from terraria_lite.cells import decode, STATION_TILES, _status
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
               "iron chainmail": "craft iron chainmail",
               # v9
               "gold chainmail": None, "suspicious looking eye": "craft Suspicious Looking Eye"}
# "descend deep" (v4-v8, DEEP_Y 70) / "reach the caverns" (v9, the cavern row):
# "return to surface" needs it and the player above the surface (SURFACE_BASE nominal).
DEEP_Y, SURFACE_BASE = SPEC.deep_row, SPEC.surface_base
_DEEP_NAME = "descend deep" if "descend deep" in SPEC.achievement_names else "reach the caverns"
BOSS_GOALS = SPEC.status_boss is not None and "defeat the Eye of Cthulhu" in SPEC.achievement_names
LENS_GOAL = "hold 6 lenses" in SPEC.achievement_names                    # v10
ALTAR_GOAL = "find a Demon Altar" in SPEC.achievement_names and "demon altar" in _STATION_INDEX


class RecipePotential:
    def __init__(self, initial_obs: np.ndarray, gamma: float, coef: float = 1.0, mode: str = "mean"):
        if mode not in ("mean", "frontier", "frontier_surface"):
            raise ValueError(f"unknown potential mode {mode!r}")
        recipes = player_knowledge()["recipes"]
        self.gamma, self.coef, self.mode = gamma, coef, mode
        self.boss = BOSS_GOALS and mode != "mean"
        self.lens = LENS_GOAL and mode != "mean"
        self.altar = ALTAR_GOAL and mode != "mean"
        if mode != "mean":
            # Every recipe name must be mapped, so a renamed recipe fails loudly.
            self.ach = np.array([-1 if _RECIPE_ACH[r["name"]] is None
                                 else SPEC.achievement_names.index(_RECIPE_ACH[r["name"]]) for r in recipes])
            self._deep = SPEC.achievement_names.index(_DEEP_NAME)
            self._back = SPEC.achievement_names.index("return to surface")
        if self.boss:
            self._summon = SPEC.achievement_names.index("summon the Eye of Cthulhu")
            self._defeat = SPEC.achievement_names.index("defeat the Eye of Cthulhu")
            self._eye = SPEC.item_names.index("Suspicious Looking Eye")
        if self.lens:
            self._hold = SPEC.achievement_names.index("hold 6 lenses")
            self._lens = SPEC.item_names.index("lens")
        if self.altar:
            self._found = SPEC.achievement_names.index("find a Demon Altar")
            self._altar_vis = _STATION_INDEX["demon altar"]
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
        if self.lens:   # the eye recipe's lens quantity (EYE_LENSES) is the goal's count
            self._lens_need = self.need[:, self._lens].max()
            assert self._lens_need > 0, "hold 6 lenses without a lens recipe"
        # phi depends only on the held ingredient counts and visible stations.
        # Remember both per lane with the value computed from them, and only
        # re-evaluate rows whose inputs changed (rare: most steps change
        # neither). Each row is still computed by the same dense formula, so
        # every value is bit-identical to evaluating the whole batch. The key
        # drops what cannot change phi: counts above an item's largest need
        # (every min(count / need, 1) term is already exactly 1) and, for
        # frontier_surface, the row while the climb goal is not open (its
        # term is then exactly 0).
        self._items = np.flatnonzero(self.need.any(0))
        self._cap = self.need[:, self._items].max(0)
        if self.boss:   # the eye count also drives the summon goal (capped at 1)
            self._cap[self._items == self._eye] = np.maximum(self._cap[self._items == self._eye], 1)
            if self._eye not in self._items:
                self._items, self._cap = np.append(self._items, self._eye), np.append(self._cap, 1)
        self._key = self._val = None
        self.previous = self.phi(initial_obs)

    def _phi_rows(self, inv, vis, ach=None, y=None, boss=None) -> np.ndarray:
        held = np.where(self.need > 0, np.minimum(inv[:, None, :] / np.maximum(self.need, 1), 1.0), 0.0).sum(-1)
        has_station = self.station >= 0
        held[:, has_station] += vis[:, self.station[has_station]]
        if self.mode == "mean":
            return self.coef * (held / self.terms).mean(-1)
        prog = held / self.terms
        open_ = (self.ach >= 0) & ((ach[:, None] >> np.maximum(self.ach, 0)) & 1 == 0)
        if self.mode == "frontier_surface":
            # One more frontier goal: climb fraction from DEEP_Y to the nominal
            # surface, counted only after the deep achievement (0 before, so
            # earning it is continuous), open until "return to surface" is earned.
            deep = (ach >> self._deep) & 1 == 1
            climb = np.where(deep, np.clip((DEEP_Y - y) / (DEEP_Y - SURFACE_BASE), 0.0, 1.0), 0.0)
            prog = np.concatenate((prog, climb[:, None]), 1)
            open_ = np.concatenate((open_, ((ach >> self._back) & 1 == 0)[:, None]), 1)
        if boss is not None:
            night, present, hp = boss[:, 0], boss[:, 1], boss[:, 2]
            eye = np.minimum(inv[:, self._eye], 1.0)
            summoned = (ach >> self._summon) & 1 == 1
            summon = eye * (0.5 + 0.5 * night)
            defeat = np.where(summoned, present * (0.25 + 0.75 * (1.0 - hp)), 0.0)
            prog = np.concatenate((prog, summon[:, None], defeat[:, None]), 1)
            open_ = np.concatenate((open_, (~summoned)[:, None], ((ach >> self._defeat) & 1 == 0)[:, None]), 1)
        if self.lens:
            hold = np.minimum(inv[:, self._lens] / self._lens_need, 1.0)
            prog = np.concatenate((prog, hold[:, None]), 1)
            open_ = np.concatenate((open_, ((ach >> self._hold) & 1 == 0)[:, None]), 1)
        if self.altar:
            deep = (ach >> self._deep) & 1 == 1
            descent = np.where(deep, 1.0, np.clip((y - SURFACE_BASE) / (DEEP_Y - SURFACE_BASE), 0.0, 1.0))
            found = 0.5 * descent + 0.5 * vis[:, self._altar_vis]
            prog = np.concatenate((prog, found[:, None]), 1)
            open_ = np.concatenate((open_, ((ach >> self._found) & 1 == 0)[:, None]), 1)
        n = open_.sum(-1)
        return self.coef * np.where(n > 0, (prog * open_).sum(-1) / np.maximum(n, 1), 0.0)

    def _inputs(self, obs: np.ndarray):
        d = decode(obs)
        inputs = {"inv": d["inventory"].astype(np.float64), "vis": d["stations"]}
        if self.mode != "mean":
            inputs["ach"] = d["achievements"]
        if self.mode == "frontier_surface" or self.altar:
            inputs["y"] = d["depth_rows"]
        if self.boss:
            s = _status(np.atleast_2d(obs)).astype(np.float64)
            inputs["boss"] = np.stack((s[:, SPEC.status_night], s[:, SPEC.status_boss], s[:, SPEC.status_boss + 1]), 1)
        return inputs

    def _phi_from(self, inputs: dict) -> np.ndarray:
        inv, vis = inputs["inv"], inputs["vis"]
        memo = []
        if "ach" in inputs:
            memo.append(inputs["ach"][:, None])
        if "y" in inputs:
            ach, y = inputs["ach"], inputs["y"]
            # y matters only while climbing (frontier_surface) or descending
            # toward the caverns for the open altar goal.
            deep = (ach >> self._deep) & 1 == 1
            uses_y = np.zeros(len(ach), bool)
            if self.mode == "frontier_surface":
                uses_y |= deep & ((ach >> self._back) & 1 == 0)
            if self.altar:
                uses_y |= ~deep & ((ach >> self._found) & 1 == 0)
            memo.append(np.where(uses_y, y, -1)[:, None])
        if "boss" in inputs:
            memo.append(inputs["boss"])
        key = np.concatenate([np.minimum(inv[:, self._items], self._cap), vis] + memo, 1)
        extra = {k: v for k, v in inputs.items() if k not in ("inv", "vis")}
        if self._key is None or len(self._key) != len(key):
            self._key, self._val = key, self._phi_rows(inv, vis, **extra)
            return self._val.copy()
        stale = np.flatnonzero((key != self._key).any(1))
        if len(stale):
            self._val[stale] = self._phi_rows(inv[stale], vis[stale], **{k: v[stale] for k, v in extra.items()})
            self._key[stale] = key[stale]
        return self._val.copy()

    def phi(self, obs: np.ndarray) -> np.ndarray:
        return self._phi_from(self._inputs(obs))

    def step(self, next_obs: np.ndarray, final_obs: np.ndarray, ended: np.ndarray) -> np.ndarray:
        """phi of each lane's reached state (the terminal observation where the
        episode ended), without materialising the mixed observation batch."""
        inputs = self._inputs(next_obs)
        if ended.any():
            reached_inputs = {k: x.copy() for k, x in inputs.items()}
            for k, f in self._inputs(final_obs[ended]).items():
                reached_inputs[k][ended] = f
            reached = self._phi_from(reached_inputs)
        else:
            reached = self._phi_from(inputs)
        reached[ended] = 0.0
        shaping = self.gamma * reached - self.previous
        self.previous = self._phi_from(inputs) if ended.any() else reached
        return shaping.astype(np.float32)
