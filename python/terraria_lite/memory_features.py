"""Per-lane spatial memory of crafting stations, built only from observations.

The policy's 11x9 window forgets a placed workbench as soon as the player walks
five tiles away, so joint prerequisites such as "stone, torches and a station in
range" rarely coincide. This module gives the policy an egocentric pointer back
to stations it has itself seen. Everything is decoded from the observation the
policy acts on: the player's world position from status[OBS_ACROSS] and
status[OBS_DEPTH], and station tiles / darkness from the tile one-hot. No
simulator state is read, so the features are the agent's own memory, not a map.

    memory = StationMemory(num_envs)       # NAME = "stations_v1", N_FEATURES = 12
    memory.reset(lanes)                    # lanes whose episode (re)started
    features = memory.update(obs)          # (N, obs_size) -> (N, 12) float32

Call `update` on every observation the policy acts from, after `reset` for the
lanes whose obs is the first of a new episode (autoreset, archive restart).
Features per station (workbench, furnace, anvil), station-major:
    known      1 if a location is remembered
    dx, dy     remembered tile minus the player's feet-left cell, clipped to
               +/-CLIP tiles and scaled to [-1, 1]; 0 when unknown
    in_view    1 if a station of this kind is visible in the current window
Update rule: a remembered location is forgotten once its cell is visible (lit)
and no longer holds that station; whenever stations of a kind are visible, the
nearest one to the player's body centre (squared Euclidean, first in row-major
order on ties) replaces the memory.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from terraria_lite import SPEC

NAME = "stations_v1"
# include/env.h WORLD_W; the C API exposes only WORLD_H. Checked against the
# header when the source tree is present so a resized world cannot silently
# skew every decoded x coordinate.
WORLD_W = 128
_ENV_H = Path(__file__).resolve().parents[2] / "include" / "env.h"
if _ENV_H.exists():
    _m = re.search(r"#define\s+WORLD_W\s+(\d+)", _ENV_H.read_text())
    assert _m and int(_m.group(1)) == WORLD_W, "memory_features.WORLD_W disagrees with include/env.h"

_TILES_END = SPEC.cells * SPEC.tile_kinds
_STATUS0 = _TILES_END + SPEC.cells
_DEPTH = _STATUS0 + SPEC.status_depth   # OBS_DEPTH = py/(WORLD_H-1)
_ACROSS = _DEPTH + 1                    # OBS_ACROSS = px/(WORLD_W-1), env.h
STATION_TILES = tuple(SPEC.tile_names.index(n) for n in ("workbench", "furnace", "anvil"))
CLIP = 64


class StationMemory:
    N_FEATURES = 4 * len(STATION_TILES)

    def __init__(self, num_envs: int):
        self.num_envs = num_envs
        self.known = np.zeros((num_envs, len(STATION_TILES)), bool)
        self.pos = np.zeros((num_envs, len(STATION_TILES), 2), np.int64)   # world (x, y)
        cells = np.arange(SPEC.cells)
        self._station_cols = cells[:, None] * SPEC.tile_kinds + np.array(STATION_TILES)
        self._unknown_cols = cells * SPEC.tile_kinds + SPEC.unknown_tile
        # src/obs.c: cell (row, col) is world (px - VIEW_W/2 + col, py - VIEW_H/2 + row).
        self._col, self._row = cells % SPEC.view_w, cells // SPEC.view_w
        cx = SPEC.view_w // 2 + (SPEC.player_w - 1) / 2
        cy = SPEC.view_h // 2 - (SPEC.player_h - 1) / 2
        self._d2 = (self._col - cx) ** 2 + (self._row - cy) ** 2
        self._lanes = np.arange(num_envs)[:, None]
        self._kinds = np.arange(len(STATION_TILES))[None, :]

    def reset(self, lanes) -> None:
        self.known[lanes] = False

    def update(self, obs: np.ndarray) -> np.ndarray:
        assert obs.shape == (self.num_envs, SPEC.obs_size)
        station = obs[:, self._station_cols] > .5                 # (N, cells, kinds)
        lit = obs[:, self._unknown_cols] < .5                     # (N, cells)
        px = np.rint(obs[:, _ACROSS] * (WORLD_W - 1)).astype(np.int64)
        py = np.rint(obs[:, _DEPTH] * (SPEC.world_h - 1)).astype(np.int64)
        x0, y0 = px - SPEC.view_w // 2, py - SPEC.view_h // 2

        # Forget remembered cells that are now seen without their station.
        col = self.pos[..., 0] - x0[:, None]
        row = self.pos[..., 1] - y0[:, None]
        inside = self.known & (col >= 0) & (col < SPEC.view_w) & (row >= 0) & (row < SPEC.view_h)
        k = np.where(inside, row * SPEC.view_w + col, 0)
        self.known &= ~(inside & lit[self._lanes, k] & ~station[self._lanes, k, self._kinds])

        # Any visible station of a kind overrides memory with the nearest one.
        visible = station.any(1)                                  # (N, kinds)
        nearest = np.where(station, self._d2[None, :, None], np.inf).argmin(1)
        self.pos[..., 0] = np.where(visible, x0[:, None] + self._col[nearest], self.pos[..., 0])
        self.pos[..., 1] = np.where(visible, y0[:, None] + self._row[nearest], self.pos[..., 1])
        self.known |= visible

        out = np.empty((self.num_envs, len(STATION_TILES), 4), np.float32)
        out[..., 0] = self.known
        out[..., 1] = np.clip(self.pos[..., 0] - px[:, None], -CLIP, CLIP) / CLIP
        out[..., 2] = np.clip(self.pos[..., 1] - py[:, None], -CLIP, CLIP) / CLIP
        out[..., 1:3] *= self.known[..., None]
        out[..., 3] = visible
        return out.reshape(self.num_envs, self.N_FEATURES)


CRAFTABLE = "craftable_v1"


class CraftableNow:
    """Terraria's crafting menu: which recipes are craftable right now.

    Exactly the craft-action entries of the legal-action mask (ingredients held
    and required station in range), which the game UI lists for a human player.
    The policy already cannot pick an uncraftable recipe; this makes the same
    fact an input, so the value function and encoder can use it too.
    """
    def __init__(self, num_envs: int):
        from terraria_lite.rules import player_knowledge
        self.actions = np.array([r["action"] for r in player_knowledge()["recipes"]])
        self.N_FEATURES = len(self.actions)

    def reset(self, lanes) -> None:
        pass

    def update(self, obs: np.ndarray, mask: np.ndarray) -> np.ndarray:
        return mask[:, self.actions].astype(np.float32)


class PolicyFeatures:
    """Named feature sets joined with '+', e.g. "stations_v1+craftable_v1"."""
    def __init__(self, name: str, num_envs: int):
        parts = {NAME: StationMemory, CRAFTABLE: CraftableNow}
        if not name or any(p not in parts for p in name.split("+")):
            raise ValueError(f"Unknown policy feature set {name!r}")
        self.parts = [parts[p](num_envs) for p in name.split("+")]
        self.N_FEATURES = sum(p.N_FEATURES for p in self.parts)

    def reset(self, lanes) -> None:
        for p in self.parts:
            p.reset(lanes)

    def update(self, obs: np.ndarray, mask: np.ndarray) -> np.ndarray:
        return np.concatenate([p.update(obs, mask) if isinstance(p, CraftableNow) else p.update(obs)
                               for p in self.parts], 1)
