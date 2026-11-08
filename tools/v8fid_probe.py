"""v8fid gates on built libraries: v8-parity hashes, determinism, save/load.

For each library (each run in its own process, so several builds can be
compared): the v8_probe world hash (save_state + first observation for seeds
0-255 and 23,000,001-23,000,128), then a long random rollout (8 lanes,
uniform legal actions from numpy default_rng(0), resets with seed
10000 + t*8 + lane) hashing every observation, reward, end flag and action
mask, plus the full state every 1000 steps. Determinism reruns the rollout in
the same process; save/load snapshots lane 0 at several steps, continues 500
steps, restores the snapshot into a fresh env and replays the same actions.

    PYTHONPATH=python uv run python tools/v8fid_probe.py [--steps N] LIB...

Two libraries with equal world and rollout hashes are behaviourally identical
over the probe (v8fid-off against v8 o3t2-inv is the parity gate).
"""
import argparse, ctypes as C, hashlib, json, subprocess, sys
import numpy as np


def load(path):
    lib = C.CDLL(path)
    vp, i, u8p, fp = C.c_void_p, C.c_int, C.POINTER(C.c_uint8), C.POINTER(C.c_float)
    lib.tl_create.restype = vp; lib.tl_create.argtypes = [i]
    lib.tl_destroy.argtypes = [vp]
    lib.tl_reset.argtypes = [vp, C.c_ulonglong, u8p, u8p, fp]
    lib.tl_step.argtypes = [vp, i, u8p, u8p, fp, fp, C.POINTER(i), C.POINTER(i)]
    lib.tl_action_mask.argtypes = [vp, u8p]
    lib.tl_save_state.argtypes = [vp, C.c_void_p]
    lib.tl_load_state.argtypes = [vp, C.c_void_p]
    return lib


class Lane:
    def __init__(self, lib):
        self.lib = lib
        self.h = lib.tl_create(0)
        cells, status = lib.tl_view_cells(), lib.tl_status_len()
        self.tile = np.zeros(cells, np.uint8); self.light = np.zeros(cells, np.uint8)
        self.status = np.zeros(status, np.float32); self.mask = np.zeros(lib.tl_action_count(), np.uint8)
        self.state = np.zeros(lib.tl_state_bytes(), np.uint8)
        self.r = C.c_float(); self.te = C.c_int(); self.tr = C.c_int()

    def ptr(self, a, t):
        return a.ctypes.data_as(C.POINTER(t))

    def obs(self):
        return self.tile.tobytes() + self.light.tobytes() + self.status.tobytes()

    def reset(self, seed):
        self.lib.tl_reset(self.h, seed, self.ptr(self.tile, C.c_uint8), self.ptr(self.light, C.c_uint8), self.ptr(self.status, C.c_float))
        self.lib.tl_action_mask(self.h, self.ptr(self.mask, C.c_uint8))

    def step(self, a):
        self.lib.tl_step(self.h, a, self.ptr(self.tile, C.c_uint8), self.ptr(self.light, C.c_uint8), self.ptr(self.status, C.c_float),
                         C.byref(self.r), C.byref(self.te), C.byref(self.tr))
        self.lib.tl_action_mask(self.h, self.ptr(self.mask, C.c_uint8))
        return self.r.value, self.te.value, self.tr.value

    def save(self):
        self.lib.tl_save_state(self.h, self.state.ctypes.data)
        return self.state.copy()

    def load(self, blob):
        self.lib.tl_load_state(self.h, blob.ctypes.data)
        self.lib.tl_action_mask(self.h, self.ptr(self.mask, C.c_uint8))


def world_hash(lib):
    h, lane = hashlib.sha256(), Lane(lib)
    for s in list(range(256)) + list(range(23000001, 23000129)):
        lane.reset(s); h.update(lane.save().tobytes()); h.update(lane.obs())
    return h.hexdigest()[:16]


def rollout(lib, steps, lanes=8):
    h, rng = hashlib.sha256(), np.random.default_rng(0)
    envs = [Lane(lib) for _ in range(lanes)]
    for k, e in enumerate(envs): e.reset(500 + k)
    episodes = 0
    for t in range(steps):
        for k, e in enumerate(envs):
            a = int(rng.choice(np.flatnonzero(e.mask)))
            r, te, tr = e.step(a)
            h.update(e.obs()); h.update(np.float32(r).tobytes()); h.update(bytes((te, tr))); h.update(e.mask.tobytes())
            if t % 1000 == 999: h.update(e.save().tobytes())
            if te or tr: e.reset(10000 + t * lanes + k); episodes += 1
    return h.hexdigest()[:16], episodes


def save_load(lib, checkpoints=(1, 137, 777, 2400), follow=500):
    """Snapshot at each checkpoint, continue, restore into a fresh env, replay."""
    failures = []
    for cp in checkpoints:
        rng = np.random.default_rng(cp)
        a_env = Lane(lib); a_env.reset(4242)
        for _ in range(cp):
            a_env.step(int(rng.choice(np.flatnonzero(a_env.mask))))
            if a_env.te.value or a_env.tr.value: break
        blob = a_env.save()
        acts, trace = [], []
        for _ in range(follow):
            a = int(rng.choice(np.flatnonzero(a_env.mask))); acts.append(a)
            r, te, tr = a_env.step(a); trace.append((a_env.obs(), r, te, tr, a_env.mask.tobytes()))
            if te or tr: break
        b_env = Lane(lib); b_env.reset(1)   # unrelated world, overwritten by the snapshot
        b_env.load(blob)
        if not np.array_equal(b_env.save(), blob): failures.append(f"cp{cp}: save(load(x)) != x")
        for j, a in enumerate(acts):
            r, te, tr = b_env.step(a)
            if (b_env.obs(), r, te, tr, b_env.mask.tobytes()) != trace[j]:
                failures.append(f"cp{cp}: diverged at +{j}"); break
    return failures


def one(path, steps):
    lib = load(path)
    out = {"lib": path, "state_bytes": lib.tl_state_bytes(), "status_len": lib.tl_status_len(),
           "world_hash": world_hash(lib)}
    out["rollout_hash"], out["episodes"] = rollout(lib, steps)
    again, _ = rollout(lib, steps)
    out["deterministic"] = again == out["rollout_hash"]
    out["save_load_failures"] = save_load(lib)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--steps", type=int, default=25000, help="rollout steps per lane (8 lanes)")
    p.add_argument("--one", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("libs", nargs="+")
    a = p.parse_args()
    if a.one:
        print(json.dumps(one(a.libs[0], a.steps))); return
    rows = []
    for path in a.libs:
        res = subprocess.run([sys.executable, __file__, "--one", "--steps", str(a.steps), path],
                             capture_output=True, text=True, check=True)
        rows.append(json.loads(res.stdout)); print(res.stdout.strip(), flush=True)
    base = rows[0]
    for r in rows[1:]:
        same = r["world_hash"] == base["world_hash"] and r["rollout_hash"] == base["rollout_hash"]
        print(f"{r['lib']} vs {base['lib']}: {'IDENTICAL' if same else 'different'}")


if __name__ == "__main__":
    main()
