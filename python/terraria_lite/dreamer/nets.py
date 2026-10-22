"""DreamerV3-style networks: RSSM world model, heads and actor-critic.

Shapes: time-major (T, B, ...). `feat` is the concatenation [h, z] of the
deterministic GRU state h (deter) and the flattened one-hot stochastic latent z
(stoch * classes).
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from terraria_lite import SPEC
from terraria_lite.compact import RAW_BYTES

_STATUS_OFFSET = RAW_BYTES - 4 * SPEC.status_len
LIGHT_LEVELS = 16
_INV = slice(SPEC.status_inv0, SPEC.status_inv0 + SPEC.n_items)


def symlog(x):
    return torch.sign(x) * torch.log1p(x.abs())


def symexp(x):
    return torch.sign(x) * torch.expm1(x.abs())


class TwoHot(nn.Module):
    """Two-hot distribution over symlog-spaced bins (DreamerV3)."""

    def __init__(self, bins: int = 255, low: float = -20.0, high: float = 20.0):
        super().__init__()
        self.register_buffer("bins", torch.linspace(low, high, bins), persistent=False)

    def mean(self, logits):
        return symexp((logits.float().softmax(-1) * self.bins).sum(-1))

    def nll(self, logits, target):
        """-log p(target) under the two-hot encoding of symlog(target)."""
        b = self.bins
        y = symlog(target.float()).clamp(b[0], b[-1])
        hi = torch.bucketize(y.contiguous(), b).clamp(1, len(b) - 1)
        lo = hi - 1
        w_hi = (y - b[lo]) / (b[hi] - b[lo])
        logp = logits.float().log_softmax(-1)
        return -((1 - w_hi) * logp.gather(-1, lo[..., None])[..., 0] + w_hi * logp.gather(-1, hi[..., None])[..., 0])


def mlp(inp: int, units: int, layers: int) -> nn.Sequential:
    mods: list[nn.Module] = []
    for i in range(layers):
        mods += [nn.Linear(inp if i == 0 else units, units, bias=False), nn.LayerNorm(units), nn.SiLU()]
    return nn.Sequential(*mods)


def head(inp: int, units: int, layers: int, out: int, scale: float = 1.0) -> nn.Sequential:
    net = mlp(inp, units, layers)
    last = nn.Linear(units, out)
    if scale == 0.0:
        nn.init.zeros_(last.weight)
    else:
        last.weight.data.mul_(scale)
    nn.init.zeros_(last.bias)
    net.append(last)
    return net


def onehot(idx, n: int):
    """One-hot by comparison (no device sync; out-of-range ids, e.g. -1, give zeros)."""
    return (idx[..., None] == torch.arange(n, device=idx.device)).float()


def onehot_action(a, n: int = SPEC.n_actions):
    """One-hot previous actions; -1 (episode start) is the zero vector."""
    return onehot(a.long(), n)


def masked_policy(logits, mask, unimix: float):
    """Log-probs of softmax(logits) over legal actions, mixed with unimix of
    the uniform distribution over the same legal set. Illegal: -inf."""
    logits = logits.float().masked_fill(~mask, float("-inf"))
    probs = logits.softmax(-1)
    legal = mask.float()
    probs = (1 - unimix) * probs + unimix * legal / legal.sum(-1, keepdim=True)
    return torch.where(mask, probs.clamp_min(1e-30).log(), torch.full_like(probs, float("-inf")))


def sample_logp(logp):
    """Gumbel-max sample from log-probs (-inf entries are never chosen)."""
    u = torch.rand_like(logp).clamp_(1e-20, 1.0)
    return (logp - torch.log(-torch.log(u))).argmax(-1)


def targets_from_raw(raw):
    """Decoder targets from compact uint8 rows (..., RAW_BYTES): tile ids, light
    levels, and the status vector with inventory as counts; all symlog'd later."""
    tiles = raw[..., :SPEC.cells].long()
    light = raw[..., SPEC.cells:2 * SPEC.cells].long()
    status = raw[..., _STATUS_OFFSET:].contiguous().view(torch.float32).clone()
    inv = status[..., _INV]
    status[..., _INV] = torch.round(inv * inv * SPEC.inventory_clip)
    return tiles, light, symlog(status)


class RSSM(nn.Module):
    def __init__(self, embed: int, deter: int, stoch: int, classes: int, units: int, unimix: float):
        super().__init__()
        self.deter, self.stoch, self.classes, self.unimix = deter, stoch, classes, unimix
        self.img_in = mlp(stoch * classes + SPEC.n_actions, units, 1)
        self.gru = nn.Linear(units + deter, 3 * deter, bias=False)
        self.gru_norm = nn.LayerNorm(3 * deter)
        self.prior_net = head(deter, units, 1, stoch * classes)
        self.post_net = head(deter + embed, units, 1, stoch * classes)

    @property
    def zsize(self) -> int:
        return self.stoch * self.classes

    def initial(self, n: int, device):
        return (torch.zeros(n, self.deter, device=device), torch.zeros(n, self.zsize, device=device))

    def gru_step(self, h, z, a1h):
        x = self.img_in(torch.cat((z, a1h), -1))
        parts = self.gru_norm(self.gru(torch.cat((x, h), -1))).float()
        reset, cand, update = parts.chunk(3, -1)
        cand = torch.tanh(torch.sigmoid(reset) * cand)
        update = torch.sigmoid(update - 1.0)
        return update * cand + (1 - update) * h

    def dist(self, raw):
        """Unimix log-probs (..., stoch, classes) from raw logits."""
        logits = raw.float().view(*raw.shape[:-1], self.stoch, self.classes)
        probs = (1 - self.unimix) * logits.softmax(-1) + self.unimix / self.classes
        return probs.log()

    def sample(self, logp):
        """Straight-through one-hot sample, flattened to (..., stoch*classes)."""
        idx = sample_logp(logp)
        onehot_z = onehot(idx, self.classes)
        probs = logp.exp()
        return (onehot_z + probs - probs.detach()).flatten(-2)

    def prior(self, h):
        return self.dist(self.prior_net(h))

    def posterior(self, h, embed):
        return self.dist(self.post_net(torch.cat((h, embed), -1)))


def kl_categorical(lp, lq):
    """KL(p || q) for log-probs (..., stoch, classes), summed over latents."""
    return (lp.exp() * (lp - lq)).sum((-2, -1))


class WorldModel(nn.Module):
    def __init__(self, deter=1024, stoch=32, classes=32, units=640, layers=3, unimix=0.01, bins=255,
                 shaping: bool = False):
        super().__init__()
        self.encoder = mlp(SPEC.obs_size, units, layers)
        self.rssm = RSSM(units, deter, stoch, classes, units, unimix)
        feat = deter + stoch * classes
        self.feat_size = feat
        self.dec_sizes = (SPEC.cells * SPEC.tile_kinds, SPEC.cells * LIGHT_LEVELS, SPEC.status_len)
        self.decoder = head(feat, units, layers, sum(self.dec_sizes))
        self.mask_head = head(feat, units, 2, SPEC.n_actions)
        self.reward_head = head(feat, units, 2, bins, scale=0.0)
        # Training-only shaping reward gets its own head, so imagined returns can
        # be split into extrinsic and shaping parts.
        self.shape_head = head(feat, units, 2, bins, scale=0.0) if shaping else None
        self.cont_head = head(feat, units, 2, 1)
        self.twohot = TwoHot(bins)
        self._status0 = SPEC.cells * (SPEC.tile_kinds + 1)

    def encode(self, x):
        """x: flat float32 observations (..., obs_size), PPO's input encoding."""
        x = torch.cat((x[..., :self._status0], symlog(x[..., self._status0:])), -1)
        return self.encoder(x)

    def decode_loss(self, feat, raw):
        tiles, light, status = targets_from_raw(raw)
        out = self.decoder(feat).float()
        t_log, l_log, s_pred = out.split(self.dec_sizes, -1)
        t_log = t_log.reshape(*t_log.shape[:-1], SPEC.cells, SPEC.tile_kinds)
        l_log = l_log.reshape(*l_log.shape[:-1], SPEC.cells, LIGHT_LEVELS)
        tile_loss = -t_log.log_softmax(-1).gather(-1, tiles[..., None])[..., 0].sum(-1)
        light_loss = -l_log.log_softmax(-1).gather(-1, light[..., None])[..., 0].sum(-1)
        status_loss = (s_pred - status).square().sum(-1)
        return tile_loss, light_loss, status_loss

    def mask_logits(self, feat):
        return self.mask_head(feat).float()

    def predicted_mask(self, feat):
        m = self.mask_logits(feat) > 0
        m[..., 0] |= ~m.any(-1)   # noop when nothing is predicted legal
        return m

    def reward(self, feat):
        return self.twohot.mean(self.reward_head(feat))

    def shaping(self, feat):
        return self.twohot.mean(self.shape_head(feat))

    def cont(self, feat):
        return torch.sigmoid(self.cont_head(feat).float()[..., 0])


class ActorCritic(nn.Module):
    def __init__(self, feat: int, units=640, layers=3, bins=255, unimix=0.01):
        super().__init__()
        self.unimix = unimix
        self.actor = head(feat, units, layers, SPEC.n_actions, scale=0.01)
        self.critic = head(feat, units, layers, bins, scale=0.0)
        self.slow_critic = head(feat, units, layers, bins, scale=0.0)
        self.slow_critic.load_state_dict(self.critic.state_dict())
        for p in self.slow_critic.parameters():
            p.requires_grad_(False)
        self.twohot = TwoHot(bins)

    def policy(self, feat, mask):
        return masked_policy(self.actor(feat), mask, self.unimix)

    @torch.no_grad()
    def update_slow(self, rate: float):
        for s, p in zip(self.slow_critic.parameters(), self.critic.parameters()):
            s.lerp_(p, rate)
