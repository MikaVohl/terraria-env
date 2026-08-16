"""Python binding for terraria-lite.

Loads the C core through ctypes and exposes it with Gymnasium's signatures.
Gymnasium itself is optional: the plain `TerrariaLite` class needs nothing but
numpy, so the environment is runnable before you have decided on a trainer. If
gymnasium is installed, `TerrariaLiteEnv` wraps it as a real `gymnasium.Env`
and registers `TerrariaLite-v0`.

Build the library first:

    make lib

Layout constants are read from the library at import time rather than
duplicated here. That is deliberate -- the C headers are the single source of
truth for the observation layout, and a binding that hardcodes 11x9 is a
binding that silently lies the day the window changes.
"""

from __future__ import annotations

import ctypes
import os
import sys

import numpy as np

__all__ = ["TerrariaLite", "SPEC", "load_library"]


# ---------------------------------------------------------------- library ---

def load_library(path: str | None = None) -> ctypes.CDLL:
    """Load libterraria from `path`, $TERRARIA_LITE_LIB, or next to this file."""
    if path is None:
        path = os.environ.get("TERRARIA_LITE_LIB")
    if path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        for ext in ("dylib", "so", "dll"):
            cand = os.path.join(here, f"libterraria.{ext}")
            if os.path.exists(cand):
                path = cand
                break
    if path is None or not os.path.exists(path):
        raise FileNotFoundError(
            "libterraria not found. Build it with `make lib` from the repo root, "
            "or point $TERRARIA_LITE_LIB at it."
        )
    return ctypes.CDLL(path)


_lib = load_library()

_P_U8 = ctypes.POINTER(ctypes.c_uint8)
_P_F32 = ctypes.POINTER(ctypes.c_float)
_P_I32 = ctypes.POINTER(ctypes.c_int)

for _name in ("tl_view_w", "tl_view_h", "tl_view_cells", "tl_tile_kinds",
              "tl_status_len", "tl_action_count", "tl_ach_count",
              "tl_item_count", "tl_unknown_tile", "tl_default_steps"):
    getattr(_lib, _name).restype = ctypes.c_int
    getattr(_lib, _name).argtypes = []

_lib.tl_action_name.restype = ctypes.c_char_p
_lib.tl_action_name.argtypes = [ctypes.c_int]
_lib.tl_ach_name.restype = ctypes.c_char_p
_lib.tl_ach_name.argtypes = [ctypes.c_int]

_lib.tl_create.restype = ctypes.c_void_p
_lib.tl_create.argtypes = [ctypes.c_int]
_lib.tl_destroy.restype = None
_lib.tl_destroy.argtypes = [ctypes.c_void_p]

_lib.tl_reset.restype = None
_lib.tl_reset.argtypes = [ctypes.c_void_p, ctypes.c_ulonglong,
                          _P_U8, _P_U8, _P_F32]
_lib.tl_step.restype = None
_lib.tl_step.argtypes = [ctypes.c_void_p, ctypes.c_int,
                         _P_U8, _P_U8, _P_F32,
                         _P_F32, _P_I32, _P_I32]
_lib.tl_action_mask.restype = None
_lib.tl_action_mask.argtypes = [ctypes.c_void_p, _P_U8]

_lib.tl_steps.restype = ctypes.c_int
_lib.tl_return.restype = ctypes.c_float
_lib.tl_health.restype = ctypes.c_int
_lib.tl_depth.restype = ctypes.c_int
_lib.tl_tile_glyph.restype = ctypes.c_int
_lib.tl_tile_glyph.argtypes = [ctypes.c_int]
_lib.tl_achievements.restype = ctypes.c_uint
_lib.tl_message.restype = ctypes.c_char_p
for _name in ("tl_steps", "tl_return", "tl_health", "tl_depth",
              "tl_achievements", "tl_message"):
    getattr(_lib, _name).argtypes = [ctypes.c_void_p]


class _Spec:
    """Observation and action layout, read from the C library."""

    def __init__(self, lib):
        self.view_w = lib.tl_view_w()
        self.view_h = lib.tl_view_h()
        self.cells = lib.tl_view_cells()
        self.tile_kinds = lib.tl_tile_kinds()
        self.status_len = lib.tl_status_len()
        self.n_actions = lib.tl_action_count()
        self.n_achievements = lib.tl_ach_count()
        self.n_items = lib.tl_item_count()
        self.unknown_tile = lib.tl_unknown_tile()
        self.default_steps = lib.tl_default_steps()
        # one-hot tiles + normalised light + status
        self.obs_size = self.cells * self.tile_kinds + self.cells + self.status_len
        self.action_names = [lib.tl_action_name(i).decode() for i in range(self.n_actions)]
        self.achievement_names = [lib.tl_ach_name(i).decode()
                                  for i in range(self.n_achievements)]
        # Mirrors TILE_INFO rather than restating it, so a new tile cannot make
        # the text view lie. unknown_tile has no glyph; render_ascii blanks it.
        self.tile_glyphs = [chr(lib.tl_tile_glyph(t))
                            for t in range(self.tile_kinds - 1)]

    def __repr__(self):
        return (f"<terraria-lite {self.view_w}x{self.view_h} window, "
                f"{self.tile_kinds} tile kinds, {self.status_len} status, "
                f"obs={self.obs_size}, actions={self.n_actions}>")


SPEC = _Spec(_lib)


# -------------------------------------------------------------- environment --

class TerrariaLite:
    """One environment instance. Gymnasium's signatures, none of its imports.

    Observations are a flat float32 vector:

        [ tiles one-hot ]  cells * tile_kinds
        [ light         ]  cells,          normalised to 0..1
        [ status        ]  status_len,     already normalised in C

    The C side hands over raw tile *ids*; the one-hot happens here. Swapping it
    for an embedding is then a change to this file alone, and adding a tile to
    the game does not move the C-side layout at all.
    """

    metadata = {"render_modes": []}

    def __init__(self, max_steps: int | None = None, seed: int | None = None):
        self._h = _lib.tl_create(int(max_steps or SPEC.default_steps))
        if not self._h:
            raise MemoryError("tl_create failed")
        self._seed = 1 if seed is None else int(seed)

        # Reused across steps: the C side memcpy's into these, so there is no
        # per-step allocation on either side of the boundary.
        self._tile = np.zeros(SPEC.cells, dtype=np.uint8)
        self._light = np.zeros(SPEC.cells, dtype=np.uint8)
        self._status = np.zeros(SPEC.status_len, dtype=np.float32)
        self._obs = np.zeros(SPEC.obs_size, dtype=np.float32)
        self._onehot = self._obs[: SPEC.cells * SPEC.tile_kinds].reshape(
            SPEC.cells, SPEC.tile_kinds)
        self._light_view = self._obs[SPEC.cells * SPEC.tile_kinds:][: SPEC.cells]
        self._status_view = self._obs[SPEC.cells * SPEC.tile_kinds + SPEC.cells:]

        self._reward = ctypes.c_float(0.0)
        self._term = ctypes.c_int(0)
        self._trunc = ctypes.c_int(0)
        self._p_tile = self._tile.ctypes.data_as(_P_U8)
        self._p_light = self._light.ctypes.data_as(_P_U8)
        self._p_status = self._status.ctypes.data_as(_P_F32)
        # Reused like the obs buffers. Callers that never mask pay nothing:
        # the C side is only touched when action_mask() is actually called.
        self._mask = np.zeros(SPEC.n_actions, dtype=np.uint8)
        self._p_mask = self._mask.ctypes.data_as(_P_U8)

    # -- lifecycle ---------------------------------------------------------

    def close(self):
        if getattr(self, "_h", None):
            _lib.tl_destroy(self._h)
            self._h = None

    def __del__(self):
        self.close()

    # -- observation -------------------------------------------------------

    def _encode(self) -> np.ndarray:
        self._onehot.fill(0.0)
        self._onehot[np.arange(SPEC.cells), self._tile] = 1.0
        np.divide(self._light, 15.0, out=self._light_view, casting="unsafe")
        self._status_view[:] = self._status
        return self._obs

    def _info(self) -> dict:
        mask = int(_lib.tl_achievements(self._h))
        return {
            "steps": _lib.tl_steps(self._h),
            "episode_return": _lib.tl_return(self._h),
            "health": _lib.tl_health(self._h),
            "depth": _lib.tl_depth(self._h),
            "achievements": bin(mask).count("1"),   # int.bit_count() is 3.10+
            "achievement_mask": mask,
        }

    # -- Gymnasium-shaped API ---------------------------------------------

    def reset(self, seed: int | None = None, options=None):
        if seed is not None:
            self._seed = int(seed)
        _lib.tl_reset(self._h, ctypes.c_ulonglong(self._seed),
                      self._p_tile, self._p_light, self._p_status)
        return self._encode().copy(), self._info()

    def step(self, action: int):
        _lib.tl_step(self._h, int(action),
                     self._p_tile, self._p_light, self._p_status,
                     ctypes.byref(self._reward),
                     ctypes.byref(self._term), ctypes.byref(self._trunc))
        return (self._encode().copy(), float(self._reward.value),
                bool(self._term.value), bool(self._trunc.value), self._info())

    def action_mask(self) -> np.ndarray:
        """Bool array over actions: True where the action would change state.

        About two thirds of the action space is inert in any given state --
        crafting without materials, placing without blocks, mining air -- and
        an unmasked policy spends most of its samples discovering that. Never
        all-False: `noop` is always available.
        """
        _lib.tl_action_mask(self._h, self._p_mask)
        return self._mask.astype(bool)

    # -- debugging ---------------------------------------------------------

    @property
    def message(self) -> str:
        return _lib.tl_message(self._h).decode()

    def view(self) -> np.ndarray:
        """The raw tile-id window, shaped (view_h, view_w). unknown_tile = unlit."""
        return self._tile.reshape(SPEC.view_h, SPEC.view_w).copy()

    def render_ascii(self) -> str:
        """The agent's actual view as text. Blank means unlit: not seen at all."""
        out = []
        for row in self.view():
            out.append("".join(" " if t == SPEC.unknown_tile else SPEC.tile_glyphs[t]
                               for t in row))
        return "\n".join(out)


# --------------------------------------------------------------- gymnasium --

try:  # optional
    import gymnasium as gym
    from gymnasium import spaces

    class TerrariaLiteEnv(gym.Env):
        """Gymnasium wrapper. Flat Box observation, Discrete action."""

        metadata = {"render_modes": ["ansi"]}

        def __init__(self, max_steps: int | None = None, render_mode=None):
            super().__init__()
            self._env = TerrariaLite(max_steps=max_steps)
            self.observation_space = spaces.Box(
                low=0.0, high=1.0, shape=(SPEC.obs_size,), dtype=np.float32)
            self.action_space = spaces.Discrete(SPEC.n_actions)
            self.render_mode = render_mode

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            if seed is None:                      # keep episodes varied
                seed = int(self.np_random.integers(0, 2**31 - 1))
            return self._env.reset(seed=seed)

        def step(self, action):
            return self._env.step(action)

        def render(self):
            if self.render_mode == "ansi":
                return self._env.render_ascii()

        def close(self):
            self._env.close()

    gym.register(id="TerrariaLite-v0",
                 entry_point="terraria_lite:TerrariaLiteEnv")

    __all__ += ["TerrariaLiteEnv"]

except ImportError:  # pragma: no cover - gymnasium is optional
    TerrariaLiteEnv = None


if __name__ == "__main__":
    print(SPEC)
    print("gymnasium:", "yes" if TerrariaLiteEnv else "not installed (optional)")
    sys.exit(0)
