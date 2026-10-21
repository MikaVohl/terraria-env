"""Compact observations: the raw C `Obs` rows (uint8 tile ids, uint8 light,
float32 status; 2144 bytes) instead of the 2963-float one-hot encoding
(11852 bytes). The trainer moves and stores these and expands them on the
learner device into exactly the float32 input the binding's flat encoding
produces (same one-hot, same light/15 rounding, bit-identical status).

A compact batch is a C-contiguous uint8 array of shape (..., RAW_BYTES). The
obs helpers in `cells` accept either representation.
"""
from __future__ import annotations

import ctypes as C

import numpy as np

from terraria_lite import SPEC, _lib

_lib.tl_obs_bytes.restype = C.c_int
RAW_BYTES = int(_lib.tl_obs_bytes())
_STATUS_OFFSET = RAW_BYTES - 4 * SPEC.status_len
# struct { uint8_t tile[cells], light[cells]; float status[status_len]; }
RAW_DTYPE = np.dtype({"names": ["tile", "light", "status"],
                      "formats": [(np.uint8, SPEC.cells), (np.uint8, SPEC.cells), (np.float32, SPEC.status_len)],
                      "offsets": [0, SPEC.cells, _STATUS_OFFSET], "itemsize": RAW_BYTES})
assert _STATUS_OFFSET >= 2 * SPEC.cells and _STATUS_OFFSET % 4 == 0
# float32((double)light / 15): the C flat encoder and NumPy's uint8 / 15.0.
LIGHT_LUT = (np.arange(16, dtype=np.float64) / 15.0).astype(np.float32)   # light levels 0..15


def is_compact(obs) -> bool:
    return getattr(obs, "dtype", None) == np.uint8 and obs.shape[-1] == RAW_BYTES


def fields(obs: np.ndarray):
    """(tile, light, status) views of a compact batch (no copies)."""
    rec = np.ascontiguousarray(obs).view(RAW_DTYPE)[..., 0]
    return rec["tile"], rec["light"], rec["status"]


def to_flat(obs: np.ndarray) -> np.ndarray:
    """NumPy float32 flat encoding, identical to tl_batch_step_flat's."""
    tile, light, status = fields(obs)
    lead = tile.shape[:-1]
    out = np.zeros((*lead, SPEC.obs_size), dtype=np.float32)
    onehot = out[..., :SPEC.cells * SPEC.tile_kinds].reshape(*lead, SPEC.cells, SPEC.tile_kinds)
    np.put_along_axis(onehot, tile[..., None].astype(np.intp), 1.0, axis=-1)
    out[..., SPEC.cells * SPEC.tile_kinds:SPEC.cells * (SPEC.tile_kinds + 1)] = LIGHT_LUT[light]
    out[..., SPEC.cells * (SPEC.tile_kinds + 1):] = status
    return out


class Expander:
    """Torch-side expansion of compact uint8 rows to the flat float32 input."""

    def __init__(self, device):
        import torch
        self.torch = torch
        self.kinds = torch.arange(SPEC.tile_kinds, dtype=torch.uint8, device=device)
        self.lut = torch.as_tensor(LIGHT_LUT, device=device)

    def __call__(self, raw):
        t = self.torch
        n = raw.shape[0]
        if n == 0:
            return t.empty((0, SPEC.obs_size), dtype=t.float32, device=raw.device)
        tile = raw[:, :SPEC.cells]
        onehot = (tile.unsqueeze(-1) == self.kinds).to(t.float32).reshape(n, SPEC.cells * SPEC.tile_kinds)
        light = self.lut[raw[:, SPEC.cells:2 * SPEC.cells].long()]
        status = raw[:, _STATUS_OFFSET:].contiguous().view(t.float32)
        return t.cat((onehot, light, status), dim=1)
