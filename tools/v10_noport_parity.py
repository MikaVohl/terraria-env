"""Parity gate for the v10 control build: build-v10-noport (all FID_* ports,
both tile rules and the tool/wall knobs off) must play exactly like v9. Both libraries step the
same seeds with the same uniform legal actions (drawn from v9's mask); every
step compares the masks, tile and light windows, the status vector outside
the achievement block, the achievement bits by name, termination and the
reward net of v10's two D24 stepping stones (find a Demon Altar, hold 6
lenses). Build the control as (variants/v10/README.md):

    make -C perf/v7 V7=$PWD/variants/v10 BUILD=build-v10-noport VARIANT="-DINV_LOG=1 \\
        -DFID_MOBS=0 -DFID_COMBAT=0 -DFID_PHYSICS=0 -DFID_MINING=0 -DFID_TREES=0 \\
        -DTREE_LEAF_VISUAL=0 -DSUPPORT_RULES=0 -DEXPLICIT_TOOLS=0 -DTOOL_DAMAGE=0 -DBG_WALLS=0"
    PYTHONPATH=python .venv/bin/python tools/v10_noport_parity.py \
        perf/v7/build-v9/libterraria.so perf/v7/build-v10-noport/libterraria.so [lanes] [steps]
"""
import ctypes
import sys

import numpy as np

P_U8 = ctypes.POINTER(ctypes.c_uint8)
P_F32 = ctypes.POINTER(ctypes.c_float)
D24 = ("find a Demon Altar", "hold 6 lenses")


class Lib:
    def __init__(self, path):
        lib = self.lib = ctypes.CDLL(path)
        for name in ("tl_view_cells", "tl_status_len", "tl_action_count", "tl_ach_count", "tl_status_ach0", "tl_env_version"):
            getattr(lib, name).restype = ctypes.c_int
        lib.tl_create.restype = ctypes.c_void_p
        lib.tl_create.argtypes = [ctypes.c_int]
        lib.tl_reset.argtypes = [ctypes.c_void_p, ctypes.c_ulonglong, P_U8, P_U8, P_F32]
        lib.tl_step.argtypes = [ctypes.c_void_p, ctypes.c_int, P_U8, P_U8, P_F32, P_F32,
                                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        lib.tl_action_mask.argtypes = [ctypes.c_void_p, P_U8]
        lib.tl_achievements64.restype = ctypes.c_ulonglong
        lib.tl_achievements64.argtypes = [ctypes.c_void_p]
        lib.tl_ach_name.restype = ctypes.c_char_p
        lib.tl_ach_name.argtypes = [ctypes.c_int]
        self.version = lib.tl_env_version()
        self.cells, self.status_len = lib.tl_view_cells(), lib.tl_status_len()
        self.n_actions, self.n_ach, self.ach0 = lib.tl_action_count(), lib.tl_ach_count(), lib.tl_status_ach0()
        self.names = [lib.tl_ach_name(i).decode() for i in range(self.n_ach)]
        self.tile = np.zeros(self.cells, np.uint8)
        self.light = np.zeros(self.cells, np.uint8)
        self.status = np.zeros(self.status_len, np.float32)
        self.mask = np.zeros(self.n_actions, np.uint8)
        self.r, self.term, self.trunc = ctypes.c_float(), ctypes.c_int(), ctypes.c_int()

    def ptrs(self):
        return (self.tile.ctypes.data_as(P_U8), self.light.ctypes.data_as(P_U8), self.status.ctypes.data_as(P_F32))

    def reset(self, h, seed):
        self.lib.tl_reset(h, seed, *self.ptrs())

    def step(self, h, a):
        self.lib.tl_step(h, a, *self.ptrs(), ctypes.byref(self.r), ctypes.byref(self.term), ctypes.byref(self.trunc))

    def get_mask(self, h):
        self.lib.tl_action_mask(h, self.mask.ctypes.data_as(P_U8))
        return self.mask.copy()

    def ach(self, h):
        bits = self.lib.tl_achievements64(h)
        return {n for i, n in enumerate(self.names) if bits >> i & 1}

    def status_outside_ach(self):
        return np.concatenate([self.status[:self.ach0], self.status[self.ach0 + self.n_ach:]])


def main():
    v9, v10 = Lib(sys.argv[1]), Lib(sys.argv[2])
    lanes = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    steps = int(sys.argv[4]) if len(sys.argv) > 4 else 20000
    assert v9.version == 9 and v10.version == 10, (v9.version, v10.version)
    assert set(v10.names) - set(v9.names) == set(D24) and len(v10.names) == len(v9.names) + 2
    rng = np.random.default_rng(12345)
    total, d24_unlocks = 0, 0
    for lane in range(lanes):
        h9, h10 = v9.lib.tl_create(0), v10.lib.tl_create(0)
        seed = 17_000_001 + lane
        v9.reset(h9, seed); v10.reset(h10, seed)
        for t in range(steps):
            m9, m10 = v9.get_mask(h9), v10.get_mask(h10)
            assert (m9 == m10).all(), f"lane {lane} step {t}: masks differ"
            a = int(rng.choice(np.flatnonzero(m9)))
            before = v10.ach(h10)
            v9.step(h9, a); v10.step(h10, a)
            new_d24 = len((v10.ach(h10) - before) & set(D24))
            d24_unlocks += new_d24
            assert (v9.tile == v10.tile).all() and (v9.light == v10.light).all(), f"lane {lane} step {t}: view differs"
            s9, s10 = v9.status_outside_ach(), v10.status_outside_ach()
            assert np.array_equal(s9, s10), f"lane {lane} step {t}: status differs at {np.flatnonzero(s9 != s10)[:8]} {s9[s9 != s10][:4]} {s10[s9 != s10][:4]} (ach0 {v9.ach0})"
            assert v9.ach(h9) == v10.ach(h10) - set(D24), f"lane {lane} step {t}: achievements differ"
            assert abs(v9.r.value - (v10.r.value - new_d24)) < 1e-6, f"lane {lane} step {t}: reward differs"
            assert (v9.term.value, v9.trunc.value) == (v10.term.value, v10.trunc.value), f"lane {lane} step {t}: end differs"
            total += 1
            if v9.term.value or v9.trunc.value:
                seed += 1000
                v9.reset(h9, seed); v10.reset(h10, seed)
    print(f"v9 == v10-noport: {total} steps over {lanes} lanes identical "
          f"(views, masks, status outside achievements, achievements, rewards net of {d24_unlocks} D24 unlocks)")


if __name__ == "__main__":
    main()
