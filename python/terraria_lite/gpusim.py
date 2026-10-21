"""GPU simulator backend: VecTerraria's interface, simulated on a HIP device.

The simulator core (src/) compiled for the GPU by perf/gpusim (`make -C
perf/gpusim libgpusim.so`, needs ROCm/hipcc). One environment per GPU thread,
all state in device memory. Finished lanes are reset from a pool of worlds
generated on the device for the same consecutive seeds VecTerraria uses, so
observations, masks, rewards, final observations and episode infos are those
of the CPU simulator (bit-identical; see perf/gpusim/REPORT.md for parity).

Observations come back to the host each step as NumPy arrays so every
trainer extra keeps working; compact rows (terraria_lite.compact) move 5.5x
fewer bytes than the float32 encoding. The library path can be overridden
with TERRARIA_GPUSIM_LIB.
"""
from __future__ import annotations

import ctypes as C
import os
from pathlib import Path

import numpy as np
import torch

from terraria_lite import SPEC
from terraria_lite.compact import RAW_BYTES

_DEFAULT_LIB = Path(__file__).resolve().parents[2] / "perf" / "gpusim" / "libgpusim.so"


def _load(path: str | os.PathLike):
    lib = C.CDLL(str(path))
    for name in ("gs_init", "gs_reset", "gs_step", "gs_reset_from_pool", "gs_capture", "gs_encode",
                 "gs_state_bytes", "gs_obs_bytes", "gs_flat_size", "gs_act_count"):
        getattr(lib, name).restype = C.c_int
    lib.gs_encode.argtypes = [C.c_void_p, C.c_longlong, C.c_void_p, C.c_void_p]
    if lib.gs_obs_bytes() != RAW_BYTES or lib.gs_flat_size() != SPEC.obs_size or lib.gs_act_count() != SPEC.n_actions:
        raise RuntimeError(f"{path} was built for another observation layout; rebuild perf/gpusim")
    return lib


def _p(t: torch.Tensor):
    return C.c_void_p(t.data_ptr())


class GpuVec:
    def __init__(self, n: int, seed: int = 1, device: str | torch.device = "cuda", compact: bool = False,
                 pool: int = 0, lib: str | None = None):
        self.L = _load(lib or os.environ.get("TERRARIA_GPUSIM_LIB", _DEFAULT_LIB))
        self.n, self.compact = n, compact
        self.device = torch.device(device)
        self._next_seed = seed
        self.pool_n = pool or max(4096, 2 * n)
        sb = self.L.gs_state_bytes()
        u8 = dict(dtype=torch.uint8, device=self.device)
        self.d_env = torch.empty(n * sb, **u8)
        self.d_pool = torch.empty(self.pool_n * sb, **u8)
        self.d_raw = torch.zeros((n, RAW_BYTES), **u8)
        self.d_final = torch.zeros((n, RAW_BYTES), **u8)
        self.d_mask = torch.zeros((n, SPEC.n_actions), **u8)
        self.d_rew = torch.zeros(n, dtype=torch.float32, device=self.device)
        self.d_ends = torch.zeros(n, dtype=torch.int32, device=self.device)
        self.d_info = torch.zeros((n, 4), dtype=torch.int32, device=self.device)
        self.d_ret = torch.zeros(n, dtype=torch.float32, device=self.device)
        self.d_cursor = torch.zeros((), dtype=torch.int64, device=self.device)
        width = RAW_BYTES if compact else SPEC.obs_size
        self.d_flat = None if compact else torch.zeros((n, SPEC.obs_size), dtype=torch.float32, device=self.device)
        pin = dict(pin_memory=True)
        self.h_obs = torch.zeros((n, width), dtype=torch.uint8 if compact else torch.float32, **pin)
        self.h_mask = torch.zeros((n, SPEC.n_actions), dtype=torch.uint8, **pin)
        self.h_rew = torch.zeros(n, dtype=torch.float32, **pin)
        self.h_ends = torch.zeros(n, dtype=torch.int32, **pin)
        self.obs = self.h_obs.numpy()
        self.mask = np.zeros((n, SPEC.n_actions), dtype=bool)
        self.restored = np.zeros(n, dtype=bool)
        self.restart = None
        self._consumed = self._generated = 0
        self._check(self.L.gs_init(_p(self.d_env), n, SPEC.default_steps, self._stream()))
        self._check(self.L.gs_init(_p(self.d_pool), self.pool_n, SPEC.default_steps, self._stream()))

    # -- plumbing -----------------------------------------------------------
    def _stream(self):
        return C.c_void_p(torch.cuda.current_stream(self.device).cuda_stream)

    @staticmethod
    def _check(code):
        if code:
            raise RuntimeError(f"HIP error {code} in the GPU simulator")

    def _refill(self):
        """Keep at least one batch of not-yet-used pool worlds ahead of the
        consumer; world k (seed: first-reset seed + k) lives in slot k % pool."""
        want = self._consumed + self.pool_n
        if self._generated - self._consumed >= max(self.n, self.pool_n // 2):
            return
        k = torch.arange(self._generated, want, dtype=torch.int64, device=self.device)
        idx = (k % self.pool_n).to(torch.int32)
        seeds = self._pool_seed0 + k
        self._check(self.L.gs_reset(_p(self.d_pool), _p(idx), _p(seeds), len(k), None, None, self._stream()))
        self._generated = want

    def _download(self):
        if self.compact:
            self.h_obs.copy_(self.d_raw, non_blocking=True)
        else:
            self._check(self.L.gs_encode(_p(self.d_raw), self.n, _p(self.d_flat), self._stream()))
            self.h_obs.copy_(self.d_flat, non_blocking=True)
        self.h_mask.copy_(self.d_mask, non_blocking=True)

    # -- VecTerraria interface ----------------------------------------------
    def reset(self):
        seeds = torch.arange(self._next_seed, self._next_seed + self.n, dtype=torch.int64, device=self.device)
        self._next_seed += self.n
        self._pool_seed0 = self._next_seed
        self._check(self.L.gs_reset(_p(self.d_env), None, _p(seeds), self.n, _p(self.d_raw), _p(self.d_mask),
                                    self._stream()))
        self._refill()
        self._download()
        torch.cuda.current_stream(self.device).synchronize()
        self.mask[:] = self.h_mask.numpy()
        return self.obs, self.mask

    def step(self, actions):
        st = self._stream()
        a = torch.as_tensor(np.asarray(actions, dtype=np.int32)).to(self.device, non_blocking=False)
        self._check(self.L.gs_step(_p(self.d_env), self.n, _p(a), _p(self.d_raw), _p(self.d_mask),
                                   _p(self.d_rew), _p(self.d_ends), st))
        self._check(self.L.gs_capture(_p(self.d_env), self.n, _p(self.d_ends), _p(self.d_raw), _p(self.d_final),
                                      _p(self.d_info), _p(self.d_ret), st))
        done = self.d_ends != 0
        csum = torch.cumsum(done, 0)
        slot = self.d_cursor + csum - 1
        self._check(self.L.gs_reset_from_pool(_p(self.d_env), self.n, _p(self.d_ends), _p(slot), _p(self.d_pool),
                                              self.pool_n, _p(self.d_raw), _p(self.d_mask), st))
        self.d_cursor += csum[-1]
        self.h_rew.copy_(self.d_rew, non_blocking=True)
        self.h_ends.copy_(self.d_ends, non_blocking=True)
        self._download()
        torch.cuda.current_stream(self.device).synchronize()
        ends = self.h_ends.numpy()
        lanes = np.flatnonzero(ends)
        final = np.zeros(self.obs.shape, self.obs.dtype)
        finished = []
        if len(lanes):
            li = torch.as_tensor(lanes, device=self.device)
            rows = self.d_final[li]
            if not self.compact:
                flat = torch.empty((len(lanes), SPEC.obs_size), dtype=torch.float32, device=self.device)
                self._check(self.L.gs_encode(_p(rows), len(lanes), _p(flat), st))
                rows = flat
            final[lanes] = rows.cpu().numpy()
            info, ret = self.d_info[li].cpu().numpy(), self.d_ret[li].cpu().numpy()
            for k, i in enumerate(lanes.tolist()):
                steps, health, depth, ach = info[k].tolist()
                ach &= 0xFFFFFFFF
                finished.append((i, {"steps": steps, "episode_return": float(ret[k]), "health": health,
                                     "depth": depth, "achievements": bin(ach).count("1"),
                                     "achievement_mask": ach, "restored_start": False}))
            self._consumed += len(lanes)
            self._next_seed += len(lanes)
            self._refill()
        self.mask[:] = self.h_mask.numpy()
        return self.obs, self.mask, self.h_rew.numpy().copy(), ends == 1, ends == 2, final, finished

    def close(self):
        pass
