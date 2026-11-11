"""PPO update microbenchmark: the trainer's minibatch step (production v10 arm: targets model,
compiled trunk/actor, bf16 scorer, fused Adam, unimix .01, 4 epochs x 16 minibatches of 8,192
compact rows) run eagerly as in ppo_agent.train, and the same step captured once in a HIP/CUDA
graph and replayed. Reports ms per minibatch for both and whether parameters, optimiser state
and losses stay bit-identical over the measured steps (both start from the same weights).

    HIP_VISIBLE_DEVICES=4 TERRARIA_LITE_LIB=... PYTHONPATH=python python perf/v10/update_probe.py [--steps 64]
"""
import argparse
import copy
import time

import numpy as np
import torch
from torch import nn

from terraria_lite import SPEC
from terraria_lite.compact import RAW_BYTES, Expander
from terraria_lite.ppo_agent import _ppo_loss
from terraria_lite.spatial_agent import build_agent

p = argparse.ArgumentParser()
p.add_argument("--steps", type=int, default=64)
p.add_argument("--mb", type=int, default=8192)
p.add_argument("--no-compile", action="store_true")
p.add_argument("--lr-tensor", action="store_true", help="eager side also uses a float32 tensor lr")
a = p.parse_args()
dev = torch.device("cuda")
torch.manual_seed(0)
kw = dict(expand=Expander(dev), bf16=True, clip_coef=.2, clip_vloss=True, ent_coef=.03, vf_coef=.5)


def make(capturable):
    torch.manual_seed(0)
    agent = build_agent("targets", 0, 0, depth=2, cell_width=32).to(dev)
    agent.unimix = .01
    if not a.no_compile:
        agent.trunk.compile(dynamic=False)
        agent.actor.compile(dynamic=False)
    lr = torch.tensor(3e-4, dtype=torch.float32, device=dev) if (capturable or a.lr_tensor) else 3e-4
    opt = torch.optim.Adam(agent.parameters(), lr=lr, eps=1e-5, fused=True,
                           **({"capturable": True} if capturable else {}))
    return agent, opt


# realistic-enough rows: valid tile ids / light levels, status from a real reset
from terraria_lite.ppo_agent import VecTerraria
v = VecTerraria(64, seed=1, workers=4, native_autoreset=True, compact=True)
o, m = v.reset()
o, m = np.asarray(o), np.asarray(m)
rng = np.random.default_rng(0)
n = a.mb * 4
rows = np.ascontiguousarray(o[rng.integers(0, 64, n)])
rows[:, :SPEC.cells] = rng.integers(0, SPEC.tile_kinds, (n, SPEC.cells))
masks = m[rng.integers(0, 64, n)].astype(bool)
acts = np.array([rng.choice(np.flatnonzero(r)) for r in masks])
data = [torch.as_tensor(x, device=dev) for x in (rows, acts, masks)]
data += [torch.randn(n, device=dev) * s for s in (.5, 1.0, 1.0, 1.0)]   # old_logp, adv, ret, old_value
data[3] = -data[3].abs() - 1.0
B = [data[0], data[1], data[2], data[3], data[4], data[5], data[6]]


def batch(i):
    s = (i % 4) * a.mb
    return [x[s:s + a.mb] for x in B]


def eager_step(agent, opt, mb):
    loss, kl, cf, ent = _ppo_loss(agent, *mb, **kw)
    if not torch.isfinite(loss):
        raise FloatingPointError
    opt.zero_grad()
    loss.backward()
    nn.utils.clip_grad_norm_(agent.parameters(), .5)
    opt.step()
    return loss.detach()


agent_e, opt_e = make(False)
agent_g, opt_g = make(True)
agent_g.load_state_dict(agent_e.state_dict())
# warm both (compile, autotune, optimizer state) on the same first steps, on a side
# stream as graph capture requires
s = torch.cuda.Stream()
s.wait_stream(torch.cuda.current_stream())
with torch.cuda.stream(s):
    for i in range(3):
        eager_step(agent_e, opt_e, batch(i))
        eager_step(agent_g, opt_g, batch(i))
torch.cuda.current_stream().wait_stream(s)
torch.cuda.synchronize()
same0 = all(torch.equal(x, y) for x, y in zip(agent_e.state_dict().values(), agent_g.state_dict().values()))
print("after 3 eager warm steps, capturable optimizer identical:", same0)

# graph: static inputs, one capture of loss + backward + clip + Adam
static = [x.clone() for x in batch(0)]
g = torch.cuda.CUDAGraph()
opt_g.zero_grad(set_to_none=True)
with torch.cuda.graph(g):
    loss_s, kl_s, cf_s, ent_s = _ppo_loss(agent_g, *static, **kw)
    loss_s.backward()
    nn.utils.clip_grad_norm_(agent_g.parameters(), .5)
    opt_g.step()
torch.cuda.synchronize()
print("captured")
# capture does not run the kernels: both models are still at the warm state
losses_e, losses_g = [], []
torch.cuda.synchronize(); t0 = time.perf_counter()
for i in range(3, 3 + a.steps):
    losses_e.append(eager_step(agent_e, opt_e, batch(i)))
torch.cuda.synchronize(); te = time.perf_counter() - t0
t0 = time.perf_counter()
for i in range(3, 3 + a.steps):
    for dst, src in zip(static, batch(i)):
        dst.copy_(src)
    g.replay()
    if not torch.isfinite(loss_s):
        raise FloatingPointError
    losses_g.append(loss_s.clone())
torch.cuda.synchronize(); tg = time.perf_counter() - t0
same = all(torch.equal(x, y) for x, y in zip(agent_e.state_dict().values(), agent_g.state_dict().values()))
same_l = all(torch.equal(x, y) for x, y in zip(losses_e, losses_g))
st_e, st_g = opt_e.state_dict()["state"], opt_g.state_dict()["state"]
same_o = all(torch.equal(st_e[k][f].float(), st_g[k][f].float()) for k in st_e for f in ("exp_avg", "exp_avg_sq"))
print(f"eager {1e3 * te / a.steps:.3f} ms/minibatch, graph {1e3 * tg / a.steps:.3f} ms/minibatch; "
      f"params identical {same}, losses identical {same_l}, adam state identical {same_o}")
