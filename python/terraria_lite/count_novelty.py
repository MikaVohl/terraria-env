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

import ctypes as C

import numpy as np

from terraria_lite import _lib
from terraria_lite.cells import cell_keys

_lib.tl_novelty_create.restype = C.c_void_p
_lib.tl_novelty_create.argtypes = [C.c_int]
_lib.tl_novelty_destroy.restype = None
_lib.tl_novelty_destroy.argtypes = [C.c_void_p]
_lib.tl_novelty_cells.restype = C.c_longlong
_lib.tl_novelty_cells.argtypes = [C.c_void_p]
_lib.tl_novelty_step.restype = C.c_int
_lib.tl_novelty_step.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p]
_lib.tl_novelty_enter.restype = C.c_int
_lib.tl_novelty_enter.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_int]


class CellNovelty:
    """Every step each lane visits its reached cell once (global counts, lane
    order); a lane is paid visits ** -0.5 the first time its episode enters
    the cell. The counts and per-episode cell sets live in C
    (tl_novelty_*); perf/check_shaping.py checks them bit for bit against the
    plain dict-and-set loop."""

    def __init__(self, initial_obs: np.ndarray):
        self.n = len(initial_obs)
        self._h = _lib.tl_novelty_create(self.n)
        if not self._h:
            raise MemoryError("tl_novelty_create failed")
        self._enter(np.arange(self.n), cell_keys(initial_obs))
        self.paid = 0

    _destroy = _lib.tl_novelty_destroy   # bound now: module globals may be gone at exit

    def __del__(self):
        if getattr(self, "_h", None):
            self._destroy(self._h)
            self._h = None

    def _enter(self, lanes, keys):
        lanes = np.ascontiguousarray(lanes, dtype=np.int32)
        keys = np.ascontiguousarray(keys, dtype=np.int64)
        if _lib.tl_novelty_enter(self._h, lanes.ctypes.data, keys.ctypes.data, len(lanes)):
            raise MemoryError("tl_novelty_enter failed")

    def step(self, next_obs: np.ndarray, final_obs: np.ndarray, ended: np.ndarray) -> np.ndarray:
        """Bonus for the transition just taken; `next_obs` is already autoreset."""
        next_keys = cell_keys(next_obs)
        restarted = np.flatnonzero(ended)
        reached = next_keys
        if len(restarted):
            reached = next_keys.copy()
            reached[restarted] = cell_keys(final_obs[restarted])
        reached = np.ascontiguousarray(reached, dtype=np.int64)
        bonus = np.empty(self.n, dtype=np.float32)
        paid = _lib.tl_novelty_step(self._h, reached.ctypes.data, bonus.ctypes.data)
        if paid < 0:
            raise MemoryError("tl_novelty_step failed")
        if len(restarted):
            self._enter(restarted, next_keys[restarted])
        self.paid += paid
        return bonus

    def stats(self) -> dict:
        return {"novelty_cells": int(_lib.tl_novelty_cells(self._h)), "novelty_paid": self.paid}
