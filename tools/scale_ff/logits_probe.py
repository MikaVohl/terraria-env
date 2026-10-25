"""Throwaway: magnitude of the policy's legal logits on real states, and bf16 log-prob error."""
import sys, numpy as np, torch
from torch.distributions import Categorical
from terraria_lite import SPEC, TerrariaLite
from terraria_lite.ppo_eval import load_agent

torch.set_num_threads(8)
for path in sys.argv[1:]:
    agent = load_agent(path, "cpu")
    envs = [TerrariaLite() for _ in range(32)]
    obs = np.stack([e.reset(seed=23000001+i)[0] for i, e in enumerate(envs)])
    xs, ms = [], []
    for t in range(1500):
        mask = np.stack([e.action_mask() for e in envs])
        x, m = torch.from_numpy(obs), torch.from_numpy(mask)
        if t % 10 == 0:
            xs.append(x.clone()); ms.append(m.clone())
        with torch.no_grad():
            a = Categorical(logits=agent.actor(agent.trunk(x)).masked_fill(~m, float("-inf"))).sample().numpy()
        for i, e in enumerate(envs):
            o, r, te, tr, _ = e.step(int(a[i]))
            obs[i] = e.reset()[0] if (te or tr) else o
    x, m = torch.cat(xs), torch.cat(ms)
    with torch.no_grad():
        logits = agent.actor(agent.trunk(x))
        with torch.autocast("cpu", dtype=torch.bfloat16):
            lb = agent.actor(agent.trunk(x)).float()
    legal = logits.masked_fill(~m, float("nan"))
    lp = torch.log_softmax(logits.masked_fill(~m, float("-inf")), -1)
    lpb = torch.log_softmax(lb.masked_fill(~m, float("-inf")), -1)
    err = (lp - lpb).abs().masked_fill(~m, 0)
    print(path.split("/")[-2:], f"legal logit mean {np.nanmean(legal.numpy()):.1f} abs max {np.nanmax(np.abs(legal.numpy())):.1f}",
          f"| bf16 |dlogp| over legal actions: median {err[m].median():.3g} max {err.max():.3g}", flush=True)
