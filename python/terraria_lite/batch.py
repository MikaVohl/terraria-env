"""Native vector stepping, bit-identical to scalar stepping, no autoreset."""
import ctypes as C
import numpy as np
from terraria_lite import SPEC, _lib

class RawObs(C.Structure):
    _fields_ = [("tile", C.c_uint8 * SPEC.cells),
                ("light", C.c_uint8 * SPEC.cells),
                ("status", C.c_float * SPEC.status_len)]

_lib.tl_obs_bytes.restype = C.c_int
_lib.tl_batch_step.restype = None
_lib.tl_batch_step.argtypes = [C.c_void_p, C.c_int, C.c_void_p, C.c_void_p,
                              C.c_void_p, C.c_void_p, C.c_void_p, C.c_int]
_lib.tl_batch_step_flat.restype=None
_lib.tl_batch_step_flat.argtypes=_lib.tl_batch_step.argtypes
assert _lib.tl_obs_bytes() == C.sizeof(RawObs)

class NativeBatch:
    """Encode directly in C by default. Raw debug views require encoded=False."""
    def __init__(self, envs, workers=4, encoded=True):
        self.envs = list(envs)  # keep owners alive, not just dangling C pointers
        self.n = len(self.envs)
        if not self.n:
            raise ValueError("a native batch needs at least one environment")
        if any(not e._h for e in self.envs):
            raise ValueError("a native batch cannot contain closed environments")
        if len({e._h for e in self.envs}) != self.n:
            raise ValueError("batch lanes must own distinct environments")
        self.workers = workers
        self.encoded=encoded
        self.handles = (C.c_void_p * self.n)(*[e._h for e in self.envs])
        self.raw = (RawObs * self.n)()
        stride = C.sizeof(RawObs)
        self.tiles = np.ndarray((self.n, SPEC.cells), np.uint8, buffer=self.raw,
                                strides=(stride, 1))
        self.light = np.ndarray((self.n, SPEC.cells), np.uint8, buffer=self.raw,
                                offset=RawObs.light.offset, strides=(stride, 1))
        self.status = np.ndarray((self.n, SPEC.status_len), np.float32, buffer=self.raw,
                                 offset=RawObs.status.offset, strides=(stride, 4))
        self.masks = np.zeros((self.n, SPEC.n_actions), np.uint8)
        self.rewards = np.zeros(self.n, np.float32)
        self.ends = np.zeros(self.n, np.int32)

    def step(self, actions, obs, mask):
        if any(not e._h for e in self.envs):
            raise RuntimeError("cannot step a batch containing a closed environment")
        actions = np.ascontiguousarray(actions, dtype=np.int32)
        if actions.shape != (self.n,):
            raise ValueError(f"expected {self.n} actions")
        if obs.shape!=(self.n,SPEC.obs_size) or obs.dtype!=np.float32 or not obs.flags.c_contiguous:
            raise ValueError("obs must be a contiguous float32 batch with the current observation dimensions")
        if mask.shape!=(self.n,SPEC.n_actions):
            raise ValueError("mask dimensions do not match the batch")
        if self.encoded:
            _lib.tl_batch_step_flat(self.handles,self.n,actions.ctypes.data,obs.ctypes.data,
                                   self.masks.ctypes.data,self.rewards.ctypes.data,
                                   self.ends.ctypes.data,self.workers)
            mask[:]=self.masks
            return self.rewards.copy(),self.ends==1,self.ends==2
        _lib.tl_batch_step(self.handles, self.n, actions.ctypes.data, self.raw,
                           self.masks.ctypes.data, self.rewards.ctypes.data,
                           self.ends.ctypes.data, self.workers)
        obs.fill(0)
        onehot = obs[:, :SPEC.cells * SPEC.tile_kinds].reshape(self.n, SPEC.cells, SPEC.tile_kinds)
        onehot[np.arange(self.n)[:, None], np.arange(SPEC.cells), self.tiles] = 1
        np.divide(self.light, 15, out=obs[:, SPEC.cells * SPEC.tile_kinds:
                                       SPEC.cells * (SPEC.tile_kinds + 1)], casting="unsafe")
        obs[:, SPEC.cells * (SPEC.tile_kinds + 1):] = self.status
        mask[:] = self.masks
        return self.rewards.copy(), self.ends == 1, self.ends == 2
