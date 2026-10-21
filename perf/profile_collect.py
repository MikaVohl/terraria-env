"""Per-phase timing of ppo_agent.train's collection step (synchronising after
each phase, so phases do not overlap as they partly do in the real loop).

    HIP_VISIBLE_DEVICES=7 PYTHONPATH=python python perf/profile_collect.py --envs 1024 [--native --compact]
"""
import argparse, json, time

import numpy as np
import torch


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--envs", type=int, default=1024)
    p.add_argument("--steps", type=int, default=256)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--native", action="store_true")
    p.add_argument("--compact", action="store_true")
    p.add_argument("--compile", action="store_true")
    p.add_argument("--no-validate", action="store_true", help="Categorical(validate_args=False)")
    a = p.parse_args()
    torch.set_num_threads(4)
    from terraria_lite.ppo_agent import VecTerraria
    from terraria_lite.potential import RecipePotential
    from terraria_lite.spatial_agent import build_agent
    if a.no_validate:
        torch.distributions.Distribution.set_default_validate_args(False)
    dev = torch.device("cuda")
    torch.manual_seed(1)
    agent = build_agent("targets").to(dev)
    if a.compile:
        agent.trunk.compile(dynamic=False); agent.actor.compile(dynamic=False)
    envs = VecTerraria(a.envs, seed=901 * 10_000_000, workers=a.workers, native_autoreset=a.native, compact=a.compact)
    o, m = envs.reset()
    pot = RecipePotential(o, .999, 3.0)
    expand = None
    if a.compact:
        from terraria_lite.compact import Expander
        expand = Expander(dev)
    to_dev = lambda x: torch.as_tensor(x, device=dev)  # noqa: E731
    nxt = to_dev(o); nxt = expand(nxt) if expand else nxt
    msk = to_dev(m)
    T = {k: 0.0 for k in ("act", "d2h_actions", "env_step", "potential", "h2d", "buffers")}
    obs_b = torch.zeros((a.envs, nxt.shape[1]), device=dev)

    def tick(k, t0):
        torch.cuda.synchronize(); t1 = time.perf_counter(); T[k] += t1 - t0; return t1

    for s in range(a.steps + 20):
        if s == 20:
            T = {k: 0.0 for k in T}
        torch.cuda.synchronize(); t = time.perf_counter()
        obs_b.copy_(nxt)
        t = tick("buffers", t)
        with torch.inference_mode():
            act, logp, _, v = agent.act(nxt, mask=msk)
        t = tick("act", t)
        acts = act.cpu().numpy()
        t = tick("d2h_actions", t)
        o, m, r, term, trunc, final, fin = envs.step(acts)
        t = tick("env_step", t)
        r = r + pot.step(o, final, term | trunc)
        t = tick("potential", t)
        rr = to_dev(r); nxt = to_dev(o); nxt = expand(nxt) if expand else nxt; msk = to_dev(m)
        dn = to_dev((term | trunc).astype(np.float32))
        t = tick("h2d", t)
    per = {k: round(1e3 * v / a.steps, 3) for k, v in T.items()}
    print(json.dumps({"envs": a.envs, "native": a.native, "compact": a.compact, "compile": a.compile,
                      "no_validate": a.no_validate, "ms_per_step": per, "total_ms": round(sum(per.values()), 3)}))


if __name__ == "__main__":
    main()
