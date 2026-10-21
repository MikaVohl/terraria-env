"""Coarse progress cells decoded from the agent's own observation.

Shared by the start-state archive, count-based novelty and diagnostics so all
three agree on what "a new kind of situation" means. Inputs are only fields the
policy already observes: achievement bits, inventory counts, visible crafting
stations and depth. Nothing here names a recipe or a goal; the inventory
buckets are generic logarithmic bins applied to every item alike.
"""
from __future__ import annotations

import numpy as np

from terraria_lite import SPEC
from terraria_lite.compact import fields, is_compact

_TILES_END = SPEC.cells * SPEC.tile_kinds
_STATUS0 = _TILES_END + SPEC.cells
STATION_TILES = tuple(SPEC.tile_names.index(n) for n in ("workbench", "furnace", "anvil"))
# Generic count bins: 0 | 1-3 | 4-9 | 10-19 | 20+.
BIN_EDGES = np.array([1, 4, 10, 20])
N_BINS = len(BIN_EDGES) + 1
DEPTH_BANDS = 4


def _status(obs: np.ndarray) -> np.ndarray:
    """Status vector of flat float32 or compact uint8 observations (see compact)."""
    if is_compact(obs):
        return fields(obs)[2]
    return obs[..., _STATUS0:]


def inventory(obs: np.ndarray) -> np.ndarray:
    """Exact item counts (N, n_items); the C side encodes sqrt(count / clip)."""
    enc = _status(obs)[..., SPEC.status_inv0:SPEC.status_inv0 + SPEC.n_items].astype(np.float64)
    return np.rint(enc * enc * SPEC.inventory_clip).astype(np.int64)


def achievements(obs: np.ndarray) -> np.ndarray:
    """Achievement bitmask (N,) as int64."""
    bits = _status(obs)[..., SPEC.status_ach0:SPEC.status_ach0 + SPEC.n_achievements] > 0.5
    return (bits.astype(np.int64) << np.arange(SPEC.n_achievements, dtype=np.int64)).sum(-1)


def stations_visible(obs: np.ndarray) -> np.ndarray:
    """(N, 3) bool: workbench / furnace / anvil tile anywhere in the view."""
    if is_compact(obs):
        tiles = obs[..., :SPEC.cells]
        return np.stack([(tiles == t).any(-1) for t in STATION_TILES], -1)
    tiles = obs[..., :_TILES_END].reshape(*obs.shape[:-1], SPEC.cells, SPEC.tile_kinds)
    return np.stack([(tiles[..., t] > 0.5).any(-1) for t in STATION_TILES], -1)


def depth_band(obs: np.ndarray) -> np.ndarray:
    return np.minimum((_status(obs)[..., SPEC.status_depth] * DEPTH_BANDS).astype(np.int64), DEPTH_BANDS - 1)


def depth_rows(obs: np.ndarray) -> np.ndarray:
    """Exact player row (N,) as int64; the C side encodes py / (world_h - 1)."""
    return np.rint(_status(obs)[..., SPEC.status_depth].astype(np.float64) * (SPEC.world_h - 1)).astype(np.int64)


def cell_parts(obs: np.ndarray) -> dict[str, np.ndarray]:
    return {"achievements": achievements(obs),
            "inventory_bins": np.searchsorted(BIN_EDGES, inventory(obs), side="right"),
            "stations": stations_visible(obs),
            "depth": depth_band(obs)}


def cell_keys(obs: np.ndarray) -> np.ndarray:
    """Stable int64 key per row; equal keys mean the same coarse progress cell."""
    obs = np.atleast_2d(obs)
    p = cell_parts(obs)
    # Polynomial hash over small integers; collisions are astronomically rare
    # at archive sizes and only merge two cells, never break correctness.
    h = p["achievements"].astype(np.uint64)
    mult = np.uint64(0x9E3779B97F4A7C15)
    for col in np.concatenate((p["inventory_bins"], p["stations"].astype(np.int64),
                               p["depth"][:, None]), axis=1).T:
        h = (h * mult) ^ col.astype(np.uint64)
    return h.view(np.int64)
