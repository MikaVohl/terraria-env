"""Would double-buffered env halves speed up collection? Times the trainer's
collection step (policy act, C step with native autoreset + compact rows,
potential shaping, host<->device copies) two ways:

  serial:  act(all) -> step(all) -> shape(all) -> upload(all)
  overlap: two halves; the C step of one half runs in a worker thread (ctypes
           releases the GIL) while the main thread samples and shapes the other.

Synchronous-PPO semantics are kept (every lane steps once per t with the same
policy); only the timing is measured here.

    HIP_VISIBLE_DEVICES=7 PYTHONPATH=python python perf/overlap_probe.py --envs 4096
"""
import argparse, json, threading, time

import numpy as np
import torch


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--envs", type=int, default=4096)
    p.add_argument("--steps", type=int, default=200)
    p.add_argument("--workers", type=int, default=16)
    a = p.parse_args()
    torch.set_num_threads(4)
    from terraria_lite.compact import Expander
    from terraria_lite.potential import RecipePotential
    from terraria_lite.ppo_agent import VecTerraria
    from terraria_lite.spatial_agent import build_agent
    dev = torch.device("cuda")
    torch.manual_seed(1)
    agent = build_agent("targets").to(dev)
    expand = Expander(dev)
    half = a.envs // 2

    def make(n, seed):
        v = VecTerraria(n, seed=seed, workers=a.workers, native_autoreset=True, compact=True)
        o, m = v.reset()
        return v, RecipePotential(o, .999, 3.0), torch.as_tensor(o, device=dev), torch.as_tensor(m, device=dev)

    def act(x, m):
        with torch.inference_mode():
            return agent.act(expand(x), mask=m)[0].cpu().numpy()

    def finish(pot, res):
        o, m, r, te, tr, f, fin = res
        r = r + pot.step(o, f, te | tr)
        return torch.as_tensor(o, device=dev), torch.as_tensor(m, device=dev), torch.as_tensor(r, device=dev)

    # serial
    v, pot, x, m = make(a.envs, 1)
    for s in range(a.steps + 20):
        if s == 20:
            torch.cuda.synchronize(); t0 = time.perf_counter()
        x, m, _ = finish(pot, v.step(act(x, m)))
    torch.cuda.synchronize(); serial = (time.perf_counter() - t0) / a.steps

    # overlapped halves
    A, B = make(half, 1), make(half, 10**9)
    out = {}

    def step_async(key, vec, actions):
        th = threading.Thread(target=lambda: out.__setitem__(key, vec.step(actions)))
        th.start()
        return th

    (va, pa, xa, ma), (vb, pb, xb, mb) = A, B
    th_a = step_async("a", va, act(xa, ma))
    for s in range(a.steps + 20):
        if s == 20:
            torch.cuda.synchronize(); t0 = time.perf_counter()
        actions_b = act(xb, mb)                 # overlaps the C step of half A
        th_a.join()
        th_b = step_async("b", vb, actions_b)
        xa, ma, _ = finish(pa, out["a"])        # shape A while B steps
        actions_a = act(xa, ma)
        th_b.join()
        th_a = step_async("a", va, actions_a)
        xb, mb, _ = finish(pb, out["b"])
    th_a.join()
    torch.cuda.synchronize(); overlap = (time.perf_counter() - t0) / a.steps
    print(json.dumps({"envs": a.envs, "serial_ms_per_step": round(1e3 * serial, 3),
                      "overlap_ms_per_step": round(1e3 * overlap, 3),
                      "collection_speedup": round(serial / overlap, 3)}))


if __name__ == "__main__":
    main()
