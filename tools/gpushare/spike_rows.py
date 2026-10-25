"""Which minibatch rows carry the corrupted policy-head gradient of a spike dump?

  HIP_VISIBLE_DEVICES= PYTHONPATH=python TERRARIA_LITE_LIB=... python tools/gpushare/spike_rows.py <dir>/spike-*.pt

The 'other' action head is a Linear on the global features g, so the
difference between the trainer's weight gradient and a clean recompute is
dW = D^T g with D the per-row logit-gradient error. Its rank and the rows of g
it aligns with show how many minibatch rows were corrupted and which.
"""
import sys

import torch

from terraria_lite.compact import Expander
from terraria_lite.spatial_agent import build_agent

torch.set_grad_enabled(False)
for path in sys.argv[1:]:
    d = torch.load(path, weights_only=False)
    names = list(d["params"].keys())
    params = [n for n in names if not n.endswith("neighborhoods") and not n.endswith("coordinates")]
    raw, same = d["raw"], d["same"]
    wi = params.index("actor.weight")
    dW = (raw[wi] - same[wi]).double()
    if float(dW.abs().max()) == 0:
        print(path, "actor.weight unaffected")
        continue
    hidden = d["params"]["trunk.global_features.0.weight"].shape[0]
    agent = build_agent("targets", hidden=hidden).double()
    agent.load_state_dict({k: v.double() if v.is_floating_point() else v for k, v in d["params"].items()})
    obs = d["args"][0]
    x = Expander("cpu")(obs).double() if d["compact"] else obs.double()
    g = agent.trunk(x)[:, :hidden]
    s = torch.linalg.svdvals(dW)
    # Least-squares D (rows x actions) restricted to the best-aligned rows.
    gn = g / g.norm(dim=1, keepdim=True)
    u, sv, vh = torch.linalg.svd(dW, full_matrices=False)
    cos = (gn @ vh[0]).abs()
    top = torch.topk(cos, 5)
    r = int(top.indices[0])
    cols = torch.nonzero(dW.abs().amax(1) > 1e-3 * dW.abs().max()).flatten().tolist()
    from terraria_lite import SPEC
    to_logit = lambda c: c if c < SPEC.mine_first else c + 2 * SPEC.reach_count   # 'other' column -> logit index
    action, mask = d["args"][1], d["args"][2]
    _, logp, _, _ = agent.act(x[r:r + 1], action[r:r + 1], mask=mask[r:r + 1])
    full = agent.actor(agent.trunk(x[r:r + 1])).masked_fill(~mask[r:r + 1], float("-inf")).log_softmax(-1)[0]
    print(path, f"|dW| {float(dW.norm()):.3g}, sv {[f'{float(v):.2g}' for v in s[:3]]}, "
          f"row {r} (cos {float(top.values[0]):.6f}, next {float(top.values[1]):.3f}), "
          f"bad logit {[to_logit(c) for c in cols]}, taken action {int(action[r])} "
          f"p(taken) {float(logp.exp()):.3g}, p(bad) {[round(float(full[to_logit(c)].exp()), 4) for c in cols]}, "
          f"legal {int(mask[r].sum())}, old_logp {float(d['args'][3][r]):.3f}")
