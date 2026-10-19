"""Go-Explore-style start-state archive for *training* episode starts.

Interface (called from `ppo_agent.train`):

    archive = StartArchive(capacity=4096, start_prob=0.25, seed=cfg.seed)
    # after every vector step, on the post-step (already autoreset) batch:
    archive.observe(envs.envs, obs, cells.cell_keys(obs))
    # in VecTerraria's autoreset, per finished lane:
    out = archive.restart(i, env)     # (obs, info) with info["archive_start"]
    if out is None: obs = env.reset(seed=fresh)[0]   # ordinary fresh world
    archive.stats()                   # telemetry dict

Invariant: the archive only ever replaces *training* autoresets. Evaluation
(`ppo_eval`, validation seeds) always starts from fresh seeded worlds and must
never be handed an archive; the archive is a curriculum over where training
episodes begin, not a change to the task being measured. A restored state is
the exact simulator snapshot, step counter included, so an archive-started
episode simply has less of the fixed horizon left -- the game is unchanged.

What is stored: one representative snapshot per coarse progress cell
(`cells.cell_keys`: achievement bits, log-binned inventory, visible stations,
depth band). A lane's current state becomes the representative when its cell
is new, or when it reaches a known cell at an earlier time (smaller
`status[OBS_TIME]`, i.e. more remaining budget). States later than
`max_time_frac` of the horizon are never stored: too little time is left to
build anything from them.

Selection (Go-Explore): cell c is drawn with weight

    w_c = (1/sqrt(1 + chosen_c) + 1/sqrt(1 + visits_c)) * progress_base ** (ach_c - ach_max)

`chosen_c` counts restarts from c, `visits_c` counts lane-steps spent in c,
`ach_c` is the cell's achievement count and `ach_max` the archive maximum. The
first factor favours rarely tried / rarely reached cells; the second keeps the
mass on the progress frontier while still giving cells one or two
achievements behind it a geometric share (with the default base 2: half, a
quarter, ...). Within a frontier level, cells differ by inventory/stations, and
novelty decides among them.

Eviction (capacity reached, new cell arrives): the victim is the least
promising non-frontier cell -- lowest achievement count, then most visited.
Frontier cells (`ach == ach_max`) are never evicted; a newcomer is rejected
instead when it has fewer achievements than the victim, or when no
non-frontier cell is left (archive saturated by the frontier). Evicted and
rejected keys are remembered (8 bytes each) and never re-admitted, so common
low-progress cells cannot churn the archive by being rediscovered every few
steps. The admission floor only rises, so a rejected key would mostly be
rejected again anyway.

Cost: `observe` is vectorised lookups (`searchsorted` over the sorted key
index) plus one `save_state` (~38.7 KB memcpy) per new or improved cell; the
index is rebuilt only when cells are added or removed. Memory is
capacity * 38.7 KB (4096 -> ~160 MB).
"""
from __future__ import annotations

import numpy as np

from terraria_lite import SPEC

# status[OBS_TIME] = steps / max_steps (include/env.h); not exported in SPEC.
_OBS_TIME = 7
_TIME = SPEC.cells * SPEC.tile_kinds + SPEC.cells + _OBS_TIME
_ACH0 = SPEC.cells * SPEC.tile_kinds + SPEC.cells + SPEC.status_ach0


def from_obs_time(obs: np.ndarray) -> np.ndarray:
    """Fraction of the episode horizon already spent, read from the observation."""
    return obs[..., _TIME]


def _achievement_counts(obs: np.ndarray) -> np.ndarray:
    return (obs[..., _ACH0:_ACH0 + SPEC.n_achievements] > 0.5).sum(-1)


class StartArchive:
    def __init__(self, capacity: int = 4096, start_prob: float = 0.25, seed: int = 0,
                 max_time_frac: float = 0.8, progress_base: float = 2.0):
        if capacity < 1:
            raise ValueError("archive capacity must be positive")
        self.capacity = capacity
        self.start_prob = float(start_prob)
        self.max_time_frac = float(max_time_frac)
        self.progress_base = float(progress_base)
        self._rng = np.random.default_rng(seed)
        # Slot storage; slots [0, n) are live, compacted on eviction by moving
        # the last slot into the hole.
        self.n = 0
        self.ach_max = 0          # highest stored achievement count = the frontier
        self._key = np.zeros(capacity, np.int64)
        self._time = np.zeros(capacity, np.float32)
        self._ach = np.zeros(capacity, np.int64)
        self._visits = np.zeros(capacity, np.int64)
        self._chosen = np.zeros(capacity, np.int64)
        self._blob: list[bytes | None] = [None] * capacity
        # Sorted lookup index over live and dead keys; slot -1 marks dead.
        self._ix_key = np.zeros(0, np.int64)
        self._ix_slot = np.zeros(0, np.int64)
        self._dead: list[int] = []
        self.snapshots = self.restarts = self.evicted = self.rejected = 0

    # -- bookkeeping ------------------------------------------------------

    def _reindex(self) -> None:
        keys = np.concatenate((self._key[:self.n], np.asarray(self._dead, np.int64)))
        slots = np.concatenate((np.arange(self.n), np.full(len(self._dead), -1)))
        order = np.argsort(keys, kind="stable")
        self._ix_key, self._ix_slot = keys[order], slots[order]

    def _lookup(self, keys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(known, slot): known covers dead keys too; slot is -1 for dead."""
        if not len(self._ix_key):
            return np.zeros(len(keys), bool), np.full(len(keys), -1)
        pos = np.minimum(np.searchsorted(self._ix_key, keys), len(self._ix_key) - 1)
        known = self._ix_key[pos] == keys
        return known, np.where(known, self._ix_slot[pos], -1)

    def _victims(self) -> list[tuple[int, int]]:
        """(slot, key) of non-frontier cells, least promising first (fewest
        achievements, then most visited). Computed at most once per observe
        call; entries are re-validated by key because eviction moves slots."""
        ach = self._ach[:self.n]
        cand = np.flatnonzero(ach < self.ach_max)
        cand = cand[np.lexsort((-self._visits[cand], ach[cand]))]
        return list(zip(cand.tolist(), self._key[cand].tolist()))[::-1]

    def _remove(self, slot: int) -> None:
        last = self.n - 1
        self._dead.append(int(self._key[slot]))
        for a in (self._key, self._time, self._ach, self._visits, self._chosen):
            a[slot] = a[last]
        self._blob[slot], self._blob[last] = self._blob[last], None
        self.n = last
        self.evicted += 1

    def _store(self, slot: int, env, key: int, t: float, ach: int) -> None:
        self._key[slot], self._time[slot], self._ach[slot] = key, t, ach
        self._blob[slot] = env.save_state()
        self.ach_max = max(self.ach_max, ach)   # monotone: frontier is never evicted
        self.snapshots += 1

    # -- interface --------------------------------------------------------

    def observe(self, envs: list, obs: np.ndarray, keys: np.ndarray) -> None:
        """Feed the post-step, already-autoreset batch and its `cell_keys`."""
        t = from_obs_time(obs)
        known, slot = self._lookup(keys)
        live = slot >= 0
        np.add.at(self._visits, slot[live], 1)
        ok = t <= self.max_time_frac

        # Earlier arrival at a stored cell: replace its representative. Lanes
        # are processed earliest-first so duplicates within a step resolve to
        # the best one.
        better = np.flatnonzero(live & ok & (t < self._time[np.maximum(slot, 0)]))
        for i in better[np.argsort(t[better], kind="stable")].tolist():
            s = slot[i]
            if t[i] < self._time[s]:
                self._store(s, envs[i], int(keys[i]), float(t[i]), int(self._ach[s]))

        new = np.flatnonzero(~known & ok)
        if not len(new):
            return
        # One candidate per new key: its earliest lane.
        new = new[np.lexsort((t[new], keys[new]))]
        new = new[np.unique(keys[new], return_index=True)[1]]
        ach = _achievement_counts(obs[new])
        victims = None
        # Highest-progress newcomers first so a full archive admits them before
        # deciding on weaker ones.
        for j in np.argsort(-ach, kind="stable").tolist():
            i, a = int(new[j]), int(ach[j])
            if self.n == self.capacity:
                if a > self.ach_max:            # newcomer moves the frontier
                    self.ach_max, victims = a, None
                if victims is None:
                    victims = self._victims()
                v = None
                while victims:
                    s, k = victims.pop()
                    if s < self.n and self._key[s] == k:
                        v = s
                        break
                if v is None or self._ach[v] > a:
                    self._dead.append(int(keys[i]))
                    self.rejected += 1
                    if v is not None:
                        victims.append((v, int(self._key[v])))
                    continue
                self._remove(v)
            s = self.n
            self.n += 1
            self._visits[s], self._chosen[s] = 1, 0
            self._store(s, envs[i], int(keys[i]), float(t[i]), a)
        self._reindex()

    def _weights(self) -> np.ndarray:
        n = self.n
        novelty = 1.0 / np.sqrt(1.0 + self._chosen[:n]) + 1.0 / np.sqrt(1.0 + self._visits[:n])
        return novelty * self.progress_base ** (self._ach[:n] - self.ach_max).astype(np.float64)

    def restart(self, lane: int, env) -> tuple | None:
        """With probability start_prob restore a sampled cell into `env` and
        return (obs, info) with info["archive_start"] = True; else None, and the
        caller resets to a fresh seeded world. `lane` is accepted for callers'
        bookkeeping; selection does not depend on it."""
        if self.n == 0 or self._rng.random() >= self.start_prob:
            return None
        c = np.cumsum(self._weights())
        s = min(int(np.searchsorted(c, self._rng.random() * c[-1], side="right")), self.n - 1)
        self._chosen[s] += 1
        self.restarts += 1
        obs, info = env.load_state(self._blob[s])
        info["archive_start"] = True
        info["archive_cell"] = int(self._key[s])
        return obs, info

    def stats(self) -> dict:
        n = self.n
        if n == 0:
            return {"cells": 0, "snapshots": self.snapshots, "restarts": self.restarts,
                    "evicted": self.evicted, "rejected": self.rejected}
        ach = self._ach[:n]
        w = self._weights()
        return {"cells": n, "snapshots": self.snapshots, "restarts": self.restarts,
                "evicted": self.evicted, "rejected": self.rejected,
                "mean_achievements": float(ach.mean()),
                "max_achievements": self.ach_max,
                "frontier_cells": int((ach == self.ach_max).sum()),
                "mean_start_time": float(self._time[:n].mean()),
                "expected_start_achievements": float((w * ach).sum() / w.sum()),
                "memory_mb": n * len(self._blob[0]) / 2**20}
