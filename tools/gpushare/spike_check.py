"""Offline float64 CPU re-evaluation of minibatches dumped by spike_probe.py.

  PYTHONPATH=python TERRARIA_LITE_LIB=... python tools/gpushare/spike_check.py <dir>/spike-*.pt

For each dump: the gradient norm of the trainer's PPO loss recomputed exactly
(float64, CPU) with the parameters the trainer used, next to the norm the GPU
produced; and the rollout log-probabilities recomputed from the rollout-time
parameters next to the stored ones. A large float64 norm means the minibatch
data itself drives the spike; a small one means the GPU computed it wrongly.
"""
import json
import sys

import torch

from terraria_lite import ppo_agent
from terraria_lite.compact import Expander
from terraria_lite.spatial_agent import build_agent


def norm(params):
    return float(torch.linalg.vector_norm(torch.stack([p.grad.norm() for p in params if p.grad is not None])))


def main():
    torch.set_default_dtype(torch.float64)
    for path in sys.argv[1:]:
        d = torch.load(path, weights_only=False)
        obs, action, mask, old_logp, adv, ret, old_value = d["args"]
        kw = dict(d["kw"], bf16=False)
        expand = Expander("cpu") if d["compact"] else None
        hidden = d["params"]["trunk.global_features.0.weight"].shape[0]
        agent = build_agent("targets", hidden=hidden).double()
        agent.load_state_dict({k: v.double() if v.is_floating_point() else v for k, v in d["params"].items()})
        params = list(agent.parameters())
        f64 = lambda t: t.double() if t.is_floating_point() else t
        loss, kl, clipfrac, _ = ppo_agent._ppo_loss(agent, obs, action, mask, f64(old_logp), f64(adv), f64(ret),
                                                   f64(old_value), expand=(lambda o: expand(o).double())
                                                   if expand else None, **kw)
        loss.backward()
        out = dict(file=path, gpu_norm=d["rec"]["norm"], gpu_same=d["rec"].get("same"),
                   gpu_fp32=d["rec"].get("fp32"), cpu64_norm=norm(params), cpu64_loss=float(loss.detach()),
                   approx_kl=float(kl), clipfrac=float(clipfrac))
        if d["snap"]:
            agent.load_state_dict({k: v.double() if v.is_floating_point() else v for k, v in d["snap"].items()})
            with torch.no_grad():
                x = expand(obs).double() if expand else obs.double()
                _, logp, _, val = agent.act(x, action, mask=mask)
            err = (logp - old_logp.double()).abs()
            out.update(rollout_logp_err_max=float(err.max()), rollout_logp_err_rows=int((err > 1e-3).sum()),
                       rollout_val_err_max=float((val - old_value.double()).abs().max()))
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
