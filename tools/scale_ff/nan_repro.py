"""Throwaway: rerun an iterate_ppo command with gradient-norm tracing to locate a non-finite loss."""
import sys, math, faulthandler, os
import numpy as np
faulthandler.dump_traceback_later(180, repeat=False)
import torch
from torch import nn

history = []
orig = nn.utils.clip_grad_norm_


def traced(parameters, max_norm, *args, **kwargs):
    parameters = list(parameters)
    norm = orig(parameters, max_norm, *args, **kwargs)
    value = float(norm)
    history.append(value)
    if not math.isfinite(value) or value > 1e3:
        print(f"step {len(history)} grad norm {value}", flush=True)
    if len(history) % 1000 == 0 and os.environ.get("SFF_GRADLOG"):
        np.save(os.environ["SFF_GRADLOG"], np.asarray(history, dtype=np.float64))
    if len(history) % 2000 == 0:
        tail = history[-2000:]
        print(f"update {len(history)}: grad norm mean {sum(tail)/len(tail):.3f} max {max(tail):.3f}", flush=True)
    return norm


nn.utils.clip_grad_norm_ = traced
_agent = {}
_orig_step = torch.optim.Adam.step


def step(self, *a, **k):
    out = _orig_step(self, *a, **k)
    bad = [i for i, g in enumerate(self.param_groups[0]["params"]) if not torch.isfinite(g).all()]
    if bad:
        print("non-finite params after step", len(history), bad, flush=True)
    return out


torch.optim.Adam.step = step
_orig_multinomial = torch.multinomial
zero_draws = [0]


def multinomial(probs, n, replacement=False, **kwargs):
    a = _orig_multinomial(probs, n, replacement, **kwargs)
    bad = (probs.gather(-1, a) < 1e-8).squeeze(-1)
    if bool(bad.any()):
        zero_draws[0] += int(bad.sum())
        for r in torch.nonzero(bad).flatten()[:3].tolist():
            print(f"TINY-PROB DRAW #{zero_draws[0]}: action {int(a[r, 0])} p={float(probs[r, a[r, 0]]):.3g}, row max p {float(probs[r].max()):.6g}, "
                  f"nonzero {int((probs[r] > 0).sum())}, last nonzero index {int(torch.nonzero(probs[r]).max())}",
                  flush=True)
    return a


torch.multinomial = multinomial
if __name__ == "__main__":
  sys.argv = ["iterate_ppo.py", *sys.argv[1:]]
  sys.path.insert(0, "tools")
  import iterate_ppo
  try:
    iterate_ppo.main()
  finally:
    print("last 40 grad norms:", [round(x, 3) for x in history[-40:]], flush=True)
