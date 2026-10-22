"""Record a compact-observation rollout for shaping benchmarks and parity checks.

Rolls VecTerraria (native autoreset, compact rows) with a policy checkpoint
(or uniform legal actions without one) and saves, per step, the next
observations plus the terminal rows of lanes that ended, so the shaping
modules can be replayed on realistic late-training states.

    HIP_VISIBLE_DEVICES=0 PYTHONPATH=python python perf/shaping_trace.py --policy step.pt --out /tmp/trace.npz
"""
import argparse

import numpy as np
import torch


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--policy", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--envs", type=int, default=1024)
    p.add_argument("--warmup", type=int, default=1500, help="steps before recording (episodes desynchronise)")
    p.add_argument("--steps", type=int, default=1000)
    p.add_argument("--seed", type=int, default=901)
    a = p.parse_args()
    torch.manual_seed(a.seed)
    from terraria_lite.compact import Expander
    from terraria_lite.ppo_agent import VecTerraria
    from terraria_lite.ppo_eval import load_agent
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    agent = load_agent(a.policy, str(dev)) if a.policy else None
    expand = Expander(dev)
    envs = VecTerraria(a.envs, seed=a.seed * 10_000_000, workers=16, native_autoreset=True, compact=True)
    obs, mask = envs.reset()
    rng = np.random.default_rng(a.seed)
    first = obs.copy()
    rec_obs, rec_ended, rec_final = [], [], []
    for t in range(a.warmup + a.steps):
        if agent is None:
            act = np.array([rng.choice(np.flatnonzero(m)) for m in mask], dtype=np.int64)
        else:
            with torch.inference_mode():
                act = agent.act(expand(torch.as_tensor(obs, device=dev)),
                                mask=torch.as_tensor(mask, device=dev))[0].cpu().numpy()
        obs, mask, _, term, trunc, final, _ = envs.step(act)
        if t == a.warmup - 1:
            first = obs.copy()
        if t >= a.warmup:
            ended = term | trunc
            rec_obs.append(obs.copy())
            rec_ended.append(ended)
            rec_final.append(final[ended])
    envs.close()
    counts = np.array([len(f) for f in rec_final])
    np.savez(a.out, first=first, obs=np.stack(rec_obs), ended=np.stack(rec_ended),
             final=np.concatenate(rec_final), final_counts=counts)
    print(f"saved {a.out}: {a.steps} steps x {a.envs} envs, {counts.sum()} episode ends")


if __name__ == "__main__":
    main()
