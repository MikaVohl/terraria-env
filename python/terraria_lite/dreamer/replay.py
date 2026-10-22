"""Device-resident replay of real sequences: one ring buffer per env lane.

Row t of a lane holds (obs_t, mask_t, prev_action_t, reward_t, shaping_t,
first_t, cont_t). An episode end writes two rows on its lane: the terminal
observation (cont=0, all-true mask placeholder, excluded from the mask loss) and
the reset observation (first=1, prev_action=-1). Sequences never cross a lane's
write position, so every sampled sequence is a contiguous piece of one lane's
stream; `first` marks episode starts inside it.
"""
from __future__ import annotations

import torch

from terraria_lite import SPEC
from terraria_lite.compact import RAW_BYTES


class Replay:
    def __init__(self, lanes: int, capacity: int, device, seed: int = 0):
        self.lanes, self.length = lanes, max(1, capacity // lanes)
        L, d = self.length, device
        self.device = torch.device(device)
        self.obs = torch.zeros((lanes, L, RAW_BYTES), dtype=torch.uint8, device=d)
        self.mask = torch.zeros((lanes, L, SPEC.n_actions), dtype=torch.bool, device=d)
        self.act = torch.full((lanes, L), -1, dtype=torch.int16, device=d)
        self.rew = torch.zeros((lanes, L), dtype=torch.float32, device=d)
        self.shape = torch.zeros((lanes, L), dtype=torch.float32, device=d)
        self.first = torch.zeros((lanes, L), dtype=torch.bool, device=d)
        self.cont = torch.zeros((lanes, L), dtype=torch.bool, device=d)
        self.count = torch.zeros(lanes, dtype=torch.long, device=d)   # rows ever written per lane
        self.gen = torch.Generator(device=d)
        self.gen.manual_seed(seed)

    @property
    def rows(self) -> int:
        return int(self.count.clamp(max=self.length).sum())

    def add(self, lanes, obs, mask, act, rew, shape, first, cont):
        """Append one row to each lane in `lanes` (a long tensor, unique)."""
        pos = self.count[lanes] % self.length
        self.obs[lanes, pos] = obs
        self.mask[lanes, pos] = mask
        self.act[lanes, pos] = act.to(torch.int16)
        self.rew[lanes, pos] = rew
        self.shape[lanes, pos] = shape
        self.first[lanes, pos] = first
        self.cont[lanes, pos] = cont
        self.count[lanes] += 1

    def ready(self, T: int) -> bool:
        return bool((self.count >= T).all())

    def sample(self, B: int, T: int) -> dict:
        """B uniformly random length-T sequences, time-major (T, B, ...)."""
        lane = torch.randint(0, self.lanes, (B,), device=self.device, generator=self.gen)
        count = self.count[lane]
        filled = count.clamp(max=self.length)
        u = (torch.rand(B, device=self.device, generator=self.gen) * (filled - T + 1)).long()
        start = count - filled + u
        idx = (start[:, None] + torch.arange(T, device=self.device)) % self.length   # (B, T)
        li = lane[:, None]
        out = {"obs": self.obs[li, idx], "mask": self.mask[li, idx], "act": self.act[li, idx],
               "rew": self.rew[li, idx], "shape": self.shape[li, idx],
               "first": self.first[li, idx], "cont": self.cont[li, idx]}
        return {k: v.transpose(0, 1) for k, v in out.items()}
