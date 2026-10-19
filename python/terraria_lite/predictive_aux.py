"""Generic predictive auxiliary task: what will this action do to my inventory?

A small world-model-flavoured head on the shared encoder predicts, for the
transition (s, a), the sign of every item's count change (-/0/+) and which
achievements unlock next step. Targets are read from consecutive observations
in the PPO rollout; transitions that cross an episode boundary are masked.
Every item and achievement is treated alike: no recipe, goal or reward weight
is encoded. Only the encoder learns from it; the PPO objective is unchanged
and the head is training-only (never saved, never used to act).
"""
from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

from terraria_lite import SPEC
from terraria_lite.ppo_agent import layer_init

_INV0 = SPEC.cells * (SPEC.tile_kinds + 1) + SPEC.status_inv0
_ACH0 = SPEC.cells * (SPEC.tile_kinds + 1) + SPEC.status_ach0


def _counts(obs):
    enc = obs[..., _INV0:_INV0 + SPEC.n_items]
    return torch.round(enc * enc * SPEC.inventory_clip)


class PredictiveAux(nn.Module):
    def __init__(self, hidden: int):
        super().__init__()
        self.hidden = hidden
        self.net = nn.Sequential(layer_init(nn.Linear(hidden + SPEC.n_actions, 128)), nn.Tanh(),
                                 layer_init(nn.Linear(128, SPEC.n_items * 3 + SPEC.n_achievements), std=.01))

    @staticmethod
    def targets(obs_b, next_obs, done_b, next_done):
        """(T,N,·) rollout -> item-change classes (T,N,items), unlock bits, valid mask."""
        nxt = torch.cat((obs_b[1:], next_obs[None]), 0)
        boundary = torch.cat((done_b[1:], next_done[None]), 0)
        delta = torch.sign(_counts(nxt[..., :SPEC.obs_size]) - _counts(obs_b[..., :SPEC.obs_size])).long() + 1
        ach_now = obs_b[..., _ACH0:_ACH0 + SPEC.n_achievements] > .5
        ach_next = nxt[..., _ACH0:_ACH0 + SPEC.n_achievements] > .5
        return delta, (ach_next & ~ach_now).float(), boundary < .5

    def loss(self, agent, obs, actions, delta, unlock, valid):
        h = agent.trunk(obs)[:, :self.hidden]
        out = self.net(torch.cat((h, F.one_hot(actions, SPEC.n_actions).float()), -1))
        logits = out[:, :SPEC.n_items * 3].reshape(-1, SPEC.n_items, 3)
        item = F.cross_entropy(logits.transpose(1, 2), delta, reduction="none").mean(-1)
        ach = F.binary_cross_entropy_with_logits(out[:, SPEC.n_items * 3:], unlock, reduction="none").mean(-1)
        w = valid.float()
        return ((item + ach) * w).sum() / w.sum().clamp(min=1)
