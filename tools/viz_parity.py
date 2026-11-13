"""Parity: viz/terraria.wasm against the native v8-default library.

Hashes full Env bytes, Obs bytes and action masks over 80 fresh worlds and
four random-legal-action episodes (up to 3,000 steps each), in both builds,
with the same LCG action rule as tools/viz_parity.mjs. Equal digests mean the
browser runs the same game, bit for bit.

    make -C perf/v7 V7=$PWD/variants/v8 BUILD=mac-v8-plain   # full-light native build
    uv run python tools/viz_parity.py [native-lib] [wasm]

Compare against a build without LIGHT_WINDOW: that patch leaves Env.light stale
outside the observation window (observations agree, whole-state bytes do not).
"""
import ctypes, hashlib, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lib_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "perf/v7/mac-v8-plain/libterraria.so"
wasm = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "viz/terraria.wasm"
L = ctypes.CDLL(str(lib_path))
L.tl_create.restype = ctypes.c_void_p
for name, args in {"tl_reset": [ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
                   "tl_save_state": [ctypes.c_void_p, ctypes.c_void_p],
                   "tl_observe": [ctypes.c_void_p] * 4, "tl_action_mask": [ctypes.c_void_p] * 2,
                   "tl_step": [ctypes.c_void_p, ctypes.c_int] + [ctypes.c_void_p] * 6}.items():
    getattr(L, name).argtypes = args
cells, status_len, acts = L.tl_view_cells(), L.tl_status_len(), L.tl_action_count()
env_bytes = L.tl_state_bytes()
env = L.tl_create(0)
state = ctypes.create_string_buffer(env_bytes)
tile, light = ctypes.create_string_buffer(cells), ctypes.create_string_buffer(cells)
status = (ctypes.c_float * status_len)()
mask = ctypes.create_string_buffer(acts)
pad = b"\0" * (-(2 * cells) % 4)          # Obs: tile[], light[], padding, float status[]
term, trunc = ctypes.c_int(), ctypes.c_int()
h = hashlib.sha256()


def digest():
    L.tl_save_state(env, state); L.tl_observe(env, tile, light, status); L.tl_action_mask(env, mask)
    h.update(state.raw); h.update(tile.raw + light.raw + pad + bytes(status)); h.update(mask.raw)


for s in list(range(64)) + list(range(23000001, 23000017)):
    L.tl_reset(env, s, None, None, None); digest()
x = 12345
for ep in range(4):
    L.tl_reset(env, 500 + ep, None, None, None)
    for t in range(3000):
        L.tl_action_mask(env, mask)
        legal = [a for a in range(acts) if mask.raw[a]]
        x = (x * 1664525 + 1013904223) & 0xFFFFFFFF
        L.tl_step(env, legal[x % len(legal)], None, None, None, None, ctypes.byref(term), ctypes.byref(trunc))
        digest()
        if term.value or trunc.value:
            break
native = h.hexdigest()
web = subprocess.run(["node", str(ROOT / "tools/viz_parity.mjs"), str(wasm)], capture_output=True, text=True,
                     check=True).stdout.strip()
print(f"native {native[:16]}  wasm {web[:16]}  env_bytes {env_bytes}")
sys.exit(0 if native == web else 1)
