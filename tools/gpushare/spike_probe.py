"""Run tools/iterate_ppo.py with an in-situ check of every gradient-norm spike.

Usage (same arguments as iterate_ppo.py):
  GSB_OUT=<dir> GSB_THRESH=100 python tools/gpushare/spike_probe.py <iterate_ppo args>

Every clip_grad_norm_ total norm is logged (<GSB_OUT>/gradnorms.npy, the same
format as ScaleFF's SFF_GRADLOG). When a norm exceeds GSB_THRESH (or is
non-finite) the minibatch that produced it is re-evaluated immediately on the
GPU, with unchanged parameters:
  same   -- the trainer's own loss function again (compiled/bf16 as configured)
  fp32   -- the eager float32 loss
and the rollout-time log-probabilities are recomputed from the parameters the
rollout was sampled with (snapshot taken when GAE runs). One JSON line per spike
goes to stdout ("SPIKE {...}") and the inputs are saved to
<GSB_OUT>/spike-<n>.pt (first GSB_DUMPS spikes) for an offline float64 check.
The gradients the trainer applies are left exactly as the trainer computed
them, so the run continues on its own trajectory.
"""
import json
import math
import os
import sys

import numpy as np
import torch
from torch import nn

THRESH = float(os.environ.get("GSB_THRESH", "100"))
OUT = os.environ.get("GSB_OUT", ".")
DUMPS = int(os.environ.get("GSB_DUMPS", "20"))
os.makedirs(OUT, exist_ok=True)

from terraria_lite import ppo_agent  # noqa: E402

S = dict(last=None, agent=None, snap=None, spikes=0, norms=[])
_orig_loss = ppo_agent._ppo_loss
_orig_compile = torch.compile
_orig_clip = nn.utils.clip_grad_norm_
_orig_gae = ppo_agent.compute_gae


def _recorder(impl):
    def rec(*args, **kw):
        S["last"], S["impl"], S["agent"] = (args, kw), impl, args[0]
        if S["snap"] is None:
            S["snap"] = {k: v.detach().clone() for k, v in args[0].state_dict().items()}
        out = impl(*args, **kw)
        S["out"] = out          # the trainer's own forward results (loss, approx_kl, clipfrac, entropy)
        return out
    rec._gsb_impl = impl
    return rec


ppo_agent._ppo_loss = _recorder(_orig_loss)


def _compile(model=None, *a, **k):
    if getattr(model, "_gsb_impl", None) is _orig_loss:
        return _recorder(_orig_compile(_orig_loss, *a, **k))
    return _orig_compile(model, *a, **k)


torch.compile = _compile


def _gae(*a, **k):
    # Runs after the rollout and before the update: parameters = rollout policy.
    if S["agent"] is not None:
        S["snap"] = {k2: v.detach().clone() for k2, v in S["agent"].state_dict().items()}
    return _orig_gae(*a, **k)


ppo_agent.compute_gae = _gae


def _total(params):
    gs = [p.grad.detach().float().norm() for p in params if p.grad is not None]
    return float(torch.linalg.vector_norm(torch.stack(gs))) if gs else 0.0


def _per_param(params):
    return [round(float(p.grad.detach().float().norm()), 4) if p.grad is not None else None for p in params]


def _grad_diff(raw, ref):
    """Where the trainer's raw gradients differ from a clean recompute (CPU, float64)."""
    out = []
    for i, (g, r) in enumerate(zip(raw, ref)):
        if g is None or r is None:
            continue
        g, r = g.double().cpu().flatten(), r.double().cpu().flatten()
        bad = (~torch.isfinite(g)) | ((g - r).abs() > 1e-2 * r.abs().max() + 1e-6)
        if bool(bad.any()):
            idx = torch.nonzero(bad).flatten()
            out.append(dict(param=i, numel=g.numel(), bad=int(bad.sum()), first=idx[:8].tolist(),
                            last=int(idx[-1]), raw_absmax=float(g[torch.isfinite(g)].abs().max()) if
                            bool(torch.isfinite(g).any()) else None, nonfinite=int((~torch.isfinite(g)).sum()),
                            ref_absmax=float(r.abs().max()), vals=g[idx[:4]].tolist(), refs=r[idx[:4]].tolist()))
    return out


def _probe(params, norm, raw):
    (args, kw), impl, agent = S["last"], S["impl"], S["agent"]
    agent_obs, action, mask, old_logp, adv, ret, old_value = args[1:8]
    expand = kw["expand"]
    applied = [None if p.grad is None else p.grad.detach().clone() for p in params]
    rec = dict(n=S["spikes"], update=len(S["norms"]), norm=norm)
    raw64 = [g.double().cpu() for g in raw if g is not None]
    rec["raw_cpu_norm"] = float(torch.linalg.vector_norm(torch.stack([g.norm() for g in raw64])))
    rec["raw_gpu_norm_again"] = float(torch.linalg.vector_norm(torch.stack(torch._foreach_norm(
        [g for g in raw if g is not None]))))
    same_grads = []
    try:
        for p in params:
            p.grad = None
        orig = [t.detach().clone() for t in S["out"]]
        again = impl(*args, **kw)
        loss = again[0]
        loss.backward()
        rec["same"], rec["same_loss"] = _total(params), float(loss)
        # Forward results of the spiking call vs the recompute: equal means the
        # corruption happened in the backward pass.
        rec["orig_fwd"] = [float(orig[0]), float(orig[1]), float(orig[2]), float(orig[3].float().mean())]
        rec["same_fwd"] = [float(again[0]), float(again[1]), float(again[2]), float(again[3].float().mean())]
        rec["entropy_rows_differ"] = int((orig[3] != again[3].detach()).sum())
        same_grads = [None if p.grad is None else p.grad.detach().clone() for p in params]
        rec["raw_vs_same"] = _grad_diff(raw, same_grads)
        for p in params:
            p.grad = None
        loss = _orig_loss(*args, **{**kw, "bf16": False})[0]
        loss.backward()
        rec["fp32"], rec["fp32_loss"] = _total(params), float(loss)
        rec["fp32_per_param"] = _per_param(params)
        with torch.no_grad():
            x = expand(agent_obs) if expand is not None else agent_obs
            rec["x_nonfinite"] = int((~torch.isfinite(x)).sum())
            rec["x_absmax"] = float(x.abs().max())
            _, newlogp, _, newval = agent.act(x, action, mask=mask)
            lr = newlogp - old_logp
            rec["logratio_max"], rec["logratio_min"] = float(lr.max()), float(lr.min())
            rec["old_logp_min"], rec["newlogp_min"] = float(old_logp.min()), float(newlogp.min())
            rec["adv_min"], rec["adv_max"], rec["adv_std"] = float(adv.min()), float(adv.max()), float(adv.std())
            rec["ret_absmax"], rec["newval_absmax"] = float(ret.abs().max()), float(newval.abs().max())
            rec["illegal_action"] = int((~mask.gather(-1, action[:, None])).sum())
            if S["snap"] is not None:
                live = {k: v.detach().clone() for k, v in agent.state_dict().items()}
                agent.load_state_dict(S["snap"])
                _, roll_logp, _, roll_val = agent.act(x, action, mask=mask)
                agent.load_state_dict(live)
                d = (roll_logp - old_logp).abs()
                rec["rollout_logp_err_max"] = float(d.max())
                rec["rollout_logp_err_rows"] = int((d > 1e-2).sum())
                rec["rollout_val_err_max"] = float((roll_val - old_value).abs().max())
            top = torch.topk(lr, 3)
            rec["top_rows"] = [dict(row=int(i), logratio=float(v), old_logp=float(old_logp[i]),
                                    newlogp=float(newlogp[i]), adv=float(adv[i]), action=int(action[i]))
                               for v, i in zip(top.values, top.indices)]
    finally:
        for p, g in zip(params, applied):
            p.grad = g
    if S["spikes"] < DUMPS:
        torch.save(dict(args=[a.detach().cpu() if torch.is_tensor(a) else a for a in args[1:8]],
                        kw={k: v for k, v in kw.items() if k != "expand"},
                        compact=expand is not None, params={k: v.cpu() for k, v in agent.state_dict().items()},
                        snap={k: v.cpu() for k, v in (S["snap"] or {}).items()}, rec=rec,
                        raw=[None if g is None else g.cpu() for g in raw],
                        same=[None if g is None else g.cpu() for g in same_grads]),
                   f"{OUT}/spike-{S['spikes']}.pt")
    S["spikes"] += 1
    print("SPIKE " + json.dumps(rec), flush=True)


def _clip(parameters, max_norm, *a, **k):
    params = list(parameters)
    # The raw gradients (a plain copy, no reduction) to tell a wrong backward
    # from a wrong norm.
    raw = [None if p.grad is None else p.grad.detach().clone() for p in params]
    norm = _orig_clip(params, max_norm, *a, **k)
    value = float(norm)
    S["norms"].append(value)
    if not math.isfinite(value) or value > THRESH:
        _probe(params, value, raw)
    if len(S["norms"]) % 1000 == 0:
        np.save(f"{OUT}/gradnorms.npy", np.asarray(S["norms"], dtype=np.float64))
    return norm


nn.utils.clip_grad_norm_ = _clip

if __name__ == "__main__":
    sys.argv = ["iterate_ppo.py", *sys.argv[1:]]
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import iterate_ppo
    try:
        iterate_ppo.main()
    finally:
        np.save(f"{OUT}/gradnorms.npy", np.asarray(S["norms"], dtype=np.float64))
        print(f"GSB done: {len(S['norms'])} updates, {S['spikes']} spikes > {THRESH}", flush=True)
