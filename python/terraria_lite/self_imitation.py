"""Self-Imitation Learning (Oh et al. 2018) as an add-on loss for masked PPO.

    sil = SelfImitation(num_envs, gamma)
    # every vector step, with the obs/mask the action was chosen from (before
    # the env step's next obs replaces them) and the *extrinsic* reward:
    sil.add_step(obs, actions, masks, rewards, term | trunc)
    # once per iteration, after the PPO epochs, with the PPO optimiser:
    stats = sil.update(agent, opt, n_minibatches, max_grad_norm)
    # stats: n_valid (mean count per minibatch with R > V), mean_adv, loss
    # (both minibatch means), buffer_steps, buffer_episodes, min_return

All arguments to `add_step` are numpy arrays over the N lanes; `agent` is any
module with the `ActorCritic.act(obs, action, mask=mask)` signature. Use the
PPO optimiser rather than a fresh one: Adam's step size is set by its second
moments, so `value_coef` only scales the one-sided value push relative to the
PPO gradients Adam has seen. Under a fresh Adam fed only SIL gradients the
clamped value term drives V(s) above every R within a dozen minibatches.

Loss. For a sampled step with Monte-Carlo return-to-go R and value V(s):

    L = -log pi(a|s, mask) * clamp(R - V, 0).detach()
        + value_coef * 0.5 * clamp(R - V, 0)^2,          averaged over the batch

so only actions that turned out better than the critic expected are imitated,
and the critic is only ever pulled *up* toward returns that were achieved.
log pi uses the action mask stored with the step, i.e. the support the action
was sampled from; the stored action is legal under it, so log pi is finite.

Returns. R_t = sum_k gamma^(k-t) r_k over the rest of the lane's episode, with
no bootstrap at either termination or truncation: the time limit is part of
the observation (status steps/max_steps), so a truncated return is the true
finite-horizon return. Rewards are the extrinsic task reward only -- never a
curiosity bonus or shaping term -- so SIL imitates what actually earned
achievements. (The critic it compares against may additionally have learned
intrinsic value; the clamp makes that a conservative, not a wrong, baseline.)
An episode that starts from an archive restart is simply a shorter episode
whose returns-to-go are measured from the restart state.

Buffer policy. Episodes enter only whole and only if their undiscounted
extrinsic return exceeds `min_return` (default: the median of the last
`median_window` finished episodes, including those finishing this step, so
SIL stays focused on above-average experience; with identical returns nothing
qualifies and SIL idles). When over `capacity_steps`, the lowest-return
episodes are evicted, oldest first among equal returns: the buffer holds the
best episodes ever seen, as in SIL, while ties favour the current policy.
Stale episodes cost little: once V(s) >= R their steps carry zero advantage
and, through the priority, are almost never sampled again.

Priority. Steps are sampled with replacement with probability proportional to
max(clamp(R - V, 0), 1e-6)^alpha (prioritised replay, alpha = 0.6 as in the
paper). V is the value seen when the step was last sampled; new steps get the
largest priority seen so far so each is looked at soon after insertion. As the
loss is a plain mean, no importance-sampling correction is applied.

Storage. Per step: tile ids uint8 (argmax of the exact one-hot), light uint8
(round(light * 15); decoded through the same double-precision /15 the binding
and the C encoder use), the trailing status block float32 (status_len plus
any feature columns appended after it), action uint8, mask np.packbits,
return-to-go and priority float32: 2161 bytes instead of 11844 for the float
obs. Decoding reproduces the original float32 observation bit for bit. The
in-progress per-lane episodes use the same compact layout (plus a float32
reward); their arrays are np.zeros, so untouched pages cost no memory.
At 64 lanes x 3000 steps plus 200k stored steps this is ~0.79 GiB.
"""
from __future__ import annotations

from collections import deque

import numpy as np
import torch
from torch import nn

from terraria_lite import SPEC

_TILES_END = SPEC.cells * SPEC.tile_kinds
_STATUS0 = _TILES_END + SPEC.cells
_MASK_BYTES = (SPEC.n_actions + 7) // 8
# Bit-identical to both encoders: NumPy's uint8 / 15.0 and capi.c's
# (float)((double)light / 15.) round the same double quotient to float32.
_LIGHT = (np.arange(256) / 15.0).astype(np.float32)
_PRIORITY_FLOOR = 1e-6
assert SPEC.n_actions <= 256, "actions are stored as uint8"


def encode(obs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(N, W >= obs_size) float32 -> tile ids, light codes, trailing float32."""
    n = obs.shape[0]
    tiles = obs[:, :_TILES_END].reshape(n, SPEC.cells, SPEC.tile_kinds).argmax(-1).astype(np.uint8)
    light = np.rint(obs[:, _TILES_END:_STATUS0] * 15).astype(np.uint8)
    return tiles, light, obs[:, _STATUS0:]


def decode(tiles: np.ndarray, light: np.ndarray, rest: np.ndarray) -> np.ndarray:
    """Inverse of `encode`: the exact float32 observation."""
    n = tiles.shape[0]
    out = np.zeros((n, _STATUS0 + rest.shape[1]), np.float32)
    out[np.arange(n)[:, None], np.arange(SPEC.cells) * SPEC.tile_kinds + tiles] = 1.0
    out[:, _TILES_END:_STATUS0] = _LIGHT[light]
    out[:, _STATUS0:] = rest
    return out


def returns_to_go(rewards: np.ndarray, gamma: float) -> np.ndarray:
    """Discounted Monte-Carlo return from each step to the episode's end."""
    out = np.empty(len(rewards), np.float32)
    g = 0.0
    for t, r in zip(range(len(rewards) - 1, -1, -1), rewards[::-1].tolist()):
        g = r + gamma * g
        out[t] = g
    return out


class _Episode:
    __slots__ = ("tiles", "light", "rest", "act", "mask", "ret", "prio", "score", "serial")


class SelfImitation:
    def __init__(self, num_envs: int, gamma: float, capacity_steps: int = 200_000,
                 batch_size: int = 512, device="cpu", value_coef: float = 0.01,
                 seed: int = 0, min_return: float | None = None,
                 alpha: float = 0.6, median_window: int = 256):
        self.num_envs, self.gamma = num_envs, gamma
        self.capacity, self.batch_size = capacity_steps, batch_size
        self.device, self.value_coef = torch.device(device), value_coef
        self.min_return, self.alpha = min_return, alpha
        self.rng = np.random.default_rng(seed)
        self.recent = deque(maxlen=median_window)    # all finished episode returns
        self.episodes: list[_Episode] = []
        self.serial = 0
        self.max_prio = 1.0
        self.prio = np.zeros(0, np.float32)          # flat; episodes hold views
        self.starts = np.zeros(1, np.int64)          # cumulative lengths
        self.threshold = -np.inf
        self.lanes = None                            # allocated on first add_step
        self.length = np.zeros(num_envs, np.int64)

    # -- collection ----------------------------------------------------------

    def _allocate(self, width: int, steps: int):
        n, old = self.num_envs, self.lanes
        self.lanes = {"tiles": np.zeros((n, steps, SPEC.cells), np.uint8),
                      "light": np.zeros((n, steps, SPEC.cells), np.uint8),
                      "rest": np.zeros((n, steps, width - _STATUS0), np.float32),
                      "act": np.zeros((n, steps), np.uint8),
                      "mask": np.zeros((n, steps, _MASK_BYTES), np.uint8),
                      "reward": np.zeros((n, steps), np.float32)}
        if old is not None:
            for k, v in old.items():
                self.lanes[k][:, :v.shape[1]] = v

    def add_step(self, obs: np.ndarray, actions: np.ndarray, masks: np.ndarray,
                 rewards: np.ndarray, ended: np.ndarray) -> None:
        obs = np.asarray(obs, np.float32)
        if obs.shape[0] != self.num_envs or obs.shape[1] < SPEC.obs_size:
            raise ValueError("obs must be (num_envs, >= obs_size)")
        if self.lanes is None:
            self._allocate(obs.shape[1], SPEC.default_steps)
        elif obs.shape[1] - _STATUS0 != self.lanes["rest"].shape[2]:
            raise ValueError("observation width changed")
        if self.length.max() >= self.lanes["act"].shape[1]:
            self._allocate(obs.shape[1], 2 * self.lanes["act"].shape[1])
        lane, t, L = np.arange(self.num_envs), self.length, self.lanes
        L["tiles"][lane, t], L["light"][lane, t], L["rest"][lane, t] = encode(obs)
        L["act"][lane, t] = actions
        L["mask"][lane, t] = np.packbits(np.asarray(masks, bool), axis=1)
        L["reward"][lane, t] = rewards
        self.length += 1

        done = np.flatnonzero(ended)
        if not len(done):
            return
        scores = [float(L["reward"][i, :self.length[i]].sum(dtype=np.float64)) for i in done]
        self.recent.extend(scores)
        self.threshold = (self.min_return if self.min_return is not None
                          else float(np.median(self.recent)))
        changed = False
        for i, score in zip(done, scores):
            if score > self.threshold:
                self._insert(i, score)
                changed = True
            self.length[i] = 0
        if changed:
            self._evict()

    def _insert(self, lane: int, score: float):
        n, L, e = self.length[lane], self.lanes, _Episode()
        e.tiles, e.light = L["tiles"][lane, :n].copy(), L["light"][lane, :n].copy()
        e.rest, e.act = L["rest"][lane, :n].copy(), L["act"][lane, :n].copy()
        e.mask = L["mask"][lane, :n].copy()
        e.ret = returns_to_go(L["reward"][lane, :n], self.gamma)
        e.prio = np.full(n, self.max_prio, np.float32)
        e.score, e.serial = score, self.serial
        self.serial += 1
        self.episodes.append(e)

    def _evict(self):
        total = sum(len(e.ret) for e in self.episodes)
        if total > self.capacity:
            self.episodes.sort(key=lambda e: (e.score, e.serial), reverse=True)
            while total > self.capacity:
                total -= len(self.episodes.pop().ret)
        # Rebuild the flat priority array and re-point every episode at its
        # slice, so priority updates write through to the episode records.
        self.prio = (np.concatenate([e.prio for e in self.episodes])
                     if self.episodes else np.zeros(0, np.float32))
        self.starts = np.zeros(len(self.episodes) + 1, np.int64)
        np.cumsum([len(e.ret) for e in self.episodes], out=self.starts[1:])
        for e, a, b in zip(self.episodes, self.starts[:-1], self.starts[1:]):
            e.prio = self.prio[a:b]

    # -- learning ------------------------------------------------------------

    @property
    def steps(self) -> int:
        return int(self.starts[-1])

    @property
    def bytes_per_step(self) -> int:
        """Stored bytes per buffered step (0 before the first add_step)."""
        if self.lanes is None:
            return 0
        return 2 * SPEC.cells + 4 * self.lanes["rest"].shape[2] + 1 + _MASK_BYTES + 4 + 4

    def nbytes(self) -> int:
        """Bytes held by stored episodes plus the (lazily touched) lane buffers."""
        lanes = sum(v.nbytes for v in self.lanes.values()) if self.lanes else 0
        return self.steps * self.bytes_per_step + lanes

    def sample(self) -> np.ndarray:
        """Flat step indices drawn by priority ** alpha, with replacement."""
        cdf = np.cumsum(np.maximum(self.prio, _PRIORITY_FLOOR).astype(np.float64) ** self.alpha)
        idx = np.searchsorted(cdf, self.rng.random(self.batch_size) * cdf[-1], side="right")
        return np.minimum(idx, len(cdf) - 1)

    def batch(self, idx: np.ndarray):
        """Decoded (obs float32, action, mask bool, return) numpy arrays for `idx`."""
        ep = np.searchsorted(self.starts, idx, side="right") - 1
        t = idx - self.starts[ep]
        e0 = self.episodes[0]
        tiles = np.empty((len(idx), SPEC.cells), np.uint8)
        light = np.empty_like(tiles)
        rest = np.empty((len(idx), e0.rest.shape[1]), np.float32)
        act = np.empty(len(idx), np.int64)
        mask = np.empty((len(idx), _MASK_BYTES), np.uint8)
        ret = np.empty(len(idx), np.float32)
        for k in np.unique(ep):
            rows = np.flatnonzero(ep == k)
            e, s = self.episodes[k], t[rows]
            tiles[rows], light[rows], rest[rows] = e.tiles[s], e.light[s], e.rest[s]
            act[rows], mask[rows], ret[rows] = e.act[s], e.mask[s], e.ret[s]
        mask = np.unpackbits(mask, axis=1, count=SPEC.n_actions).astype(bool)
        return decode(tiles, light, rest), act, mask, ret

    def update(self, agent, optimizer, n_minibatches: int, max_grad_norm: float) -> dict:
        stats = {"n_valid": 0.0, "mean_adv": 0.0, "loss": 0.0, "buffer_steps": self.steps,
                 "buffer_episodes": len(self.episodes), "min_return": self.threshold}
        if not self.steps:
            return stats
        dev = self.device
        for _ in range(n_minibatches):
            idx = self.sample()
            obs, act, mask, ret = self.batch(idx)
            _, logp, _, value = agent.act(torch.from_numpy(obs).to(dev), torch.from_numpy(act).to(dev),
                                          mask=torch.from_numpy(mask).to(dev))
            clipped = (torch.from_numpy(ret).to(dev) - value).clamp(min=0)
            adv = clipped.detach()
            loss = -(logp * adv).mean() + self.value_coef * 0.5 * (clipped ** 2).mean()
            if not torch.isfinite(loss):
                raise FloatingPointError("Non-finite SIL loss; preserve this run without retrying")
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(agent.parameters(), max_grad_norm)
            optimizer.step()
            adv = adv.cpu().numpy()
            self.prio[idx] = adv
            self.max_prio = max(self.max_prio, float(adv.max()))
            stats["n_valid"] += float((adv > 0).sum()) / n_minibatches
            stats["mean_adv"] += float(adv.mean()) / n_minibatches
            stats["loss"] += loss.item() / n_minibatches
        return stats
