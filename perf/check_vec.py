"""Exactness check for VecTerraria options against the default Python loop.

Steps four VecTerraria instances with identical actions (uniform over legal,
plus 10% uniform over all actions) and asserts every returned value matches the
default (flat, Python autoreset): obs, mask, reward, terminated, truncated,
final_obs, finished infos, and the seed counter. Compact rows are compared via
their exact flat expansion (NumPy and torch expanders).

    PYTHONPATH=python python perf/check_vec.py --envs 512 --steps 4000
"""
import argparse

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--envs", type=int, default=512)
    p.add_argument("--steps", type=int, default=4000)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--torch-device", default="", help="also check the torch Expander on this device")
    a = p.parse_args()
    from terraria_lite import SPEC
    from terraria_lite.compact import to_flat
    from terraria_lite.ppo_agent import VecTerraria
    variants = {"default": {}, "native": dict(native_autoreset=True), "compact": dict(compact=True),
                "native+compact": dict(native_autoreset=True, compact=True)}
    vecs = {k: VecTerraria(a.envs, seed=901 * 10_000_000, workers=a.workers, **kw) for k, kw in variants.items()}
    expander = None
    if a.torch_device:
        import torch
        from terraria_lite.compact import Expander
        expander = Expander(torch.device(a.torch_device))

    def flat(name, x):
        if not vecs[name].compact:
            return x
        f = to_flat(x)
        if expander is not None:
            t = expander(torch.as_tensor(x, device=a.torch_device)).cpu().numpy()
            assert np.array_equal(t.view(np.uint32), f.view(np.uint32)), "torch expansion differs"
        return f

    first = {k: v.reset() for k, v in vecs.items()}
    for k in variants:
        assert np.array_equal(flat(k, first[k][0]).view(np.uint32), first["default"][0].view(np.uint32)), k
        assert np.array_equal(first[k][1], first["default"][1]), k
    rng = np.random.default_rng(5)
    episodes = 0
    for t in range(a.steps):
        mask = vecs["default"].mask
        act = np.array([rng.choice(np.flatnonzero(m)) for m in mask], dtype=np.int64)
        wild = rng.random(a.envs) < 0.1
        act[wild] = rng.integers(0, SPEC.n_actions, wild.sum())
        out = {k: v.step(act) for k, v in vecs.items()}
        ref = out["default"]
        for k, got in out.items():
            obs, msk, rew, term, trunc, final, finished = got
            assert np.array_equal(flat(k, obs).view(np.uint32), ref[0].view(np.uint32)), (k, t, "obs")
            assert np.array_equal(msk, ref[1]) and msk.dtype == ref[1].dtype, (k, t, "mask")
            assert np.array_equal(rew.view(np.uint32), ref[2].view(np.uint32)), (k, t, "reward")
            assert np.array_equal(term, ref[3]) and np.array_equal(trunc, ref[4]), (k, t, "ends")
            ended = term | trunc
            if vecs[k].compact:   # zero raw rows of unfinished lanes carry no meaning
                assert not final[~ended].any(), (k, t, "final rows of running lanes")
                assert np.array_equal(flat(k, final[ended]).view(np.uint32), ref[5][ended].view(np.uint32)), (k, t, "final")
            else:
                assert np.array_equal(final.view(np.uint32), ref[5].view(np.uint32)), (k, t, "final")
            assert finished == ref[6], (k, t, "infos", finished[:2], ref[6][:2])
            assert vecs[k]._next_seed == vecs["default"]._next_seed, (k, t, "seed")
        episodes += len(ref[6])
    print(f"OK: {a.envs} envs x {a.steps} steps, {episodes} episode resets; native/compact/native+compact "
          f"identical to the Python loop (obs, mask, reward, ends, final_obs, infos, seeds)"
          + (f"; torch expansion on {a.torch_device} bit-identical" if expander else ""))


if __name__ == "__main__":
    main()
