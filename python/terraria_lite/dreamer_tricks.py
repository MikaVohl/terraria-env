"""DreamerV3-inspired PPO options (Hafner et al. 2023, "Mastering Diverse
Domains through World Models"); all off by default, training-only.

- PercentileScale (`return_norm="percentile"`): advantages are divided by
  max(1, P95 - P5) of the batch's lambda-returns, each percentile tracked by an
  EMA with decay .99 (zero-initialised, no debiasing, as DreamerV3's retnorm).
  This REPLACES PPO's per-minibatch advantage standardisation (no centering,
  no division by the minibatch std): small advantages stay small, so the
  entropy bonus wins where returns carry no signal.
- TwoHotCritic (`value_head="twohot"`): the critic outputs logits over 255
  bins evenly spaced in symlog space on [-20, 20], trained by cross-entropy
  against two-hot encoded symlog(returns); value = symexp(E[bin]). The output
  layer is zero-initialised (value 0 at start), as in DreamerV3.
- unimix_logits (`unimix=eps`): the masked policy becomes
  (1-eps) * softmax(masked logits) + eps * uniform(legal actions); illegal
  actions keep exactly zero probability. Used for sampling, log-probs and
  entropy during training. Evaluation (ppo_eval, policy_diagnostics) is frozen
  and samples from the plain masked logits.
"""
from __future__ import annotations

import math

import torch
from torch import nn
from torch.distributions import Categorical


def symlog(x):
    return torch.sign(x) * torch.log1p(x.abs())


def symexp(x):
    return torch.sign(x) * torch.expm1(x.abs())


def unimix_logits(logits, mask, eps: float):
    """Log-probabilities of (1-eps)*softmax(logits) + eps*uniform over legal
    actions. `logits` must already be -inf on illegal actions. Computed in
    log space so illegal entries never see log(0) gradients."""
    logp = torch.log_softmax(logits.float(), -1)
    if mask is None:
        uniform = torch.full_like(logp, math.log(eps) - math.log(logp.shape[-1]))
    else:
        uniform = (math.log(eps) - mask.sum(-1, keepdim=True).float().log()).expand_as(logp)
    mixed = torch.logaddexp(logp + math.log1p(-eps), uniform)
    return mixed if mask is None else mixed.masked_fill(~mask, float("-inf"))


class TwoHotCritic(nn.Module):
    """Categorical symlog critic replacing a linear (N, 1) value head.

    forward() returns the decoded value with the old (N, 1) shape, so
    ActorCritic.act/value and GAE are unchanged; logits()/loss() serve the
    update.
    """

    def __init__(self, base: nn.Module, bins: int = 255, low: float = -20.0, high: float = 20.0):
        super().__init__()
        if not isinstance(base, nn.Linear) or base.out_features != 1:
            raise ValueError("twohot value head needs a linear (hidden -> 1) critic")
        # Same class (e.g. targets' GlobalCritic, which reads a slice of h).
        self.head = type(base)(base.in_features, bins)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)
        self.register_buffer("bins", torch.linspace(low, high, bins), persistent=False)

    def logits(self, h):
        return self.head(h)

    def decode(self, logits):
        return symexp((logits.float().softmax(-1) * self.bins).sum(-1, keepdim=True))

    def forward(self, h):
        return self.decode(self.head(h))

    def twohot(self, target):
        y = symlog(target.float()).clamp(self.bins[0], self.bins[-1])
        k = len(self.bins)
        above = torch.bucketize(y, self.bins, right=True).clamp(1, k - 1)
        below = above - 1
        lo, hi = self.bins[below], self.bins[above]
        w = ((y - lo) / (hi - lo)).clamp(0.0, 1.0)
        out = torch.zeros(*y.shape, k, device=y.device)
        out.scatter_(-1, below[..., None], (1.0 - w)[..., None])
        out.scatter_add_(-1, above[..., None], w[..., None])
        return out

    def loss(self, logits, target):
        return -(self.twohot(target) * torch.log_softmax(logits.float(), -1)).sum(-1).mean()


def install_value_head(agent: nn.Module, kind: str) -> nn.Module:
    """Swap the agent's critic in place; "scalar" leaves the agent untouched."""
    if kind == "scalar":
        return agent
    if kind != "twohot":
        raise ValueError(f"unknown value head {kind!r}")
    device = next(agent.parameters()).device
    agent.critic = TwoHotCritic(agent.critic).to(device)
    return agent


def score(agent, x, action, mask, *, bf16: bool, unimix: float):
    """Update-time policy log-prob/entropy and critic logits for the twohot
    head (the default paths are agent.act and ppo_agent._score_bf16)."""
    if bf16:
        with torch.autocast(device_type=x.device.type, dtype=torch.bfloat16):
            h = agent.trunk(x)
            logits, value_logits = agent.actor(h), agent.critic.logits(h)
    else:
        h = agent.trunk(x)
        logits, value_logits = agent.actor(h), agent.critic.logits(h)
    logits = logits.float().masked_fill(~mask, float("-inf"))
    if unimix:
        logits = unimix_logits(logits, mask, unimix)
    dist = Categorical(logits=logits)
    return dist.log_prob(action), dist.entropy(), value_logits.float()


class PercentileScale:
    """EMA of the 5th/95th return percentiles; scale = max(1, high - low)."""

    def __init__(self, decay: float = 0.99, low: float = 0.05, high: float = 0.95):
        self.decay, self.q = decay, (low, high)
        self.low = self.high = 0.0

    def update(self, returns) -> float:
        r = returns.detach().float().flatten()
        lo, hi = torch.quantile(r, torch.tensor(self.q, device=r.device)).tolist()
        self.low = self.decay * self.low + (1 - self.decay) * lo
        self.high = self.decay * self.high + (1 - self.decay) * hi
        return max(1.0, self.high - self.low)

    def stats(self) -> dict:
        return {"p5_ema": self.low, "p95_ema": self.high, "scale": max(1.0, self.high - self.low)}
