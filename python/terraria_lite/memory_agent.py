"""Memory cores for the fast PPO trainer: GRU, LSTM or a causal transformer.

The policy otherwise sees one 11x9 window and carries no state between steps.
A memory agent wraps an existing feed-forward encoder (`targets` by default)
and feeds its global features through a learned core; the actor and critic
heads then read cat(global features, core output, per-target context), so the
feed-forward path stays intact and the core can only add information. No game
knowledge enters: the core sees exactly the encoder's features.

Cores (`memory`):
  gru / lstm    one recurrent layer of width `memory_size`. Rollouts step it
                with an explicit cell (compile-friendly, same weights); the
                update runs the fused nn.GRU/nn.LSTM over each env's 128-step
                sequence from the stored rollout-start state (truncated BPTT),
                as one packed call over the lanes' episode segments.
  transformer   2 pre-LN causal self-attention layers (width `memory_size`,
                64-wide heads) over the last `memory_len` steps of the current
                episode. Rollouts keep a per-layer K/V ring buffer; a learned
                per-head bias on the step offset is the only position signal.
                Updates recompute K/V for the rollout's own steps and reuse the
                stored (detached) K/V of the `memory_len - 1` steps before it,
                as in Transformer-XL, so the first update pass reproduces the
                rollout's outputs.

State protocol (ppo_eval.evaluate, tools/policy_diagnostics.py, the trainer):
  initial_state(n, device)      fresh state for n lanes
  core_step(x, state, done)     (heads input, new state); `done[i]` = 1 means
                                x[i] starts a new episode (state reset first)
  snapshot(state)               detached copy of what an update needs to
                                replay the next rollout from this state
  select(snapshot, lanes)       the snapshot restricted to some lanes
  sequence(x, snapshot, done)   heads input for a (T*B, obs) time-major batch
                                (T, B lanes), replaying from the snapshot
"""
from __future__ import annotations

import math

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

from terraria_lite import SPEC
from terraria_lite.ppo_agent import layer_init

MEMORIES = ("gru", "lstm", "transformer")
DEFAULT_SIZE = 256
DEFAULT_LEN = 64
LAYERS = 2
HEAD_WIDTH = 64


class MemoryActorCritic(nn.Module):
    def __init__(self, memory: str, memory_size: int = 0, memory_len: int = 0,
                 architecture: str = "targets", hidden: int = 0, extra: int = 0, **encoder):
        super().__init__()
        if memory not in MEMORIES:
            raise ValueError(f"Unknown memory {memory!r}; choose from {', '.join(MEMORIES)}")
        from terraria_lite.spatial_agent import build_agent
        from terraria_lite.target_agent import GlobalCritic, TargetActor
        base = build_agent(architecture, hidden or None, extra, **encoder)
        if type(base.critic) not in (nn.Linear, GlobalCritic) or type(base.actor) not in (nn.Linear, TargetActor):
            raise ValueError(f"memory does not support architecture {architecture!r}")
        self.memory, self.size = memory, memory_size or DEFAULT_SIZE
        self.length = (memory_len or DEFAULT_LEN) if memory == "transformer" else 0
        self.width = base.critic.in_features            # encoder global features
        self.trunk = base.trunk
        heads_in = self.width + self.size
        self.actor = (TargetActor(heads_in) if type(base.actor) is TargetActor else
                      layer_init(nn.Linear(heads_in, SPEC.n_actions), std=.01))
        self.critic = layer_init(GlobalCritic(heads_in, 1), std=1.)
        if memory == "transformer":
            self.core = CausalMemory(self.width, self.size, self.length)
        else:
            rnn = (nn.GRU if memory == "gru" else nn.LSTM)(self.width, self.size)
            gates = 3 if memory == "gru" else 4
            # As recurrent_ppo_agent: orthogonal recurrent blocks, zero biases.
            for name, param in rnn.named_parameters():
                if "bias" in name:
                    nn.init.zeros_(param)
                elif "weight_hh" in name:
                    for block in param.chunk(gates, 0):
                        nn.init.orthogonal_(block)
                else:
                    nn.init.xavier_uniform_(param)
            self.core = rnn
        self.memory_config = {"memory": memory, "memory_size": self.size, "memory_len": self.length,
                              "architecture": architecture, "hidden": hidden, "extra": extra, **encoder}

    # ---------------------------------------------------------------- state --
    def initial_state(self, n: int, device) -> tuple:
        if self.memory == "transformer":
            return self.core.initial_state(n, device)
        z = torch.zeros((1, n, self.size), device=device)
        return (z,) if self.memory == "gru" else (z, z.clone())

    def snapshot(self, state) -> tuple:
        if self.memory == "transformer":
            return self.core.snapshot(state)
        return tuple(s.detach().clone() for s in state)

    def select(self, snapshot, lanes) -> tuple:
        if self.memory == "transformer":
            return snapshot[0][:, lanes], snapshot[1][lanes]
        return tuple(s[:, lanes] for s in snapshot)

    # ------------------------------------------------------------- forward ---
    def _join(self, encoded, memory):
        return torch.cat((encoded[:, :self.width], memory, encoded[:, self.width:]), dim=-1)

    def core_step(self, x, state, done):
        encoded = self.trunk(x)
        g = encoded[:, :self.width]
        if self.memory == "transformer":
            m, state = self.core.step(g, state, done)
        else:
            keep = (1.0 - done)[:, None]
            w_ih, w_hh = self.core.weight_ih_l0, self.core.weight_hh_l0
            gi = F.linear(g, w_ih, self.core.bias_ih_l0)
            h = state[0][0] * keep
            gh = F.linear(h, w_hh, self.core.bias_hh_l0)
            if self.memory == "gru":      # torch.nn.GRU gate order r, z, n
                ir, iz, i_n = gi.chunk(3, -1)
                hr, hz, h_n = gh.chunk(3, -1)
                r, z = torch.sigmoid(ir + hr), torch.sigmoid(iz + hz)
                m = torch.lerp(torch.tanh(i_n + r * h_n), h, z)   # (1-z)*n + z*h
                state = (m[None],)
            else:                         # torch.nn.LSTM gate order i, f, g, o
                i, f, c_in, o = (gi + gh).chunk(4, -1)
                c = torch.sigmoid(f) * (state[1][0] * keep) + torch.sigmoid(i) * torch.tanh(c_in)
                m = torch.sigmoid(o) * torch.tanh(c)
                state = (m[None], c[None])
        return self._join(encoded, m), state

    def encode(self, x):
        """Encoder output for flat rows (the update runs it separately so it can
        use autocast/compilation independently of the core)."""
        return self.trunk(x)

    def recur(self, encoded, snapshot, done, plan=None):
        """Core over time-major (T*B) encoder output; returns the heads input.
        `plan` (RNNs only): rnn_plan of `done`, precomputed host-side so the
        update never waits on the device."""
        t, b = done.shape
        g = encoded[:, :self.width].float().reshape(t, b, self.width)
        if self.memory == "transformer":
            m = self.core.sequence(g, snapshot, done)
        else:
            m = self._rnn_sequence(g, snapshot, plan if plan is not None else
                                   rnn_plan(done.detach().cpu().numpy(), g.device))
        return self._join(encoded.float(), m.reshape(t * b, self.size))

    def sequence(self, x, snapshot, done):
        return self.recur(self.encode(x), snapshot, done)

    def _rnn_sequence(self, g, state, plan):
        # Every lane's rollout splits into episode segments; all segments run
        # as one packed fused-RNN call, each from its lane's snapshot state or,
        # after an episode start, from zeros. Same recurrence as core_step.
        t, b, width = g.shape
        fwd, inv, lane, keep, lengths = plan
        x = g.reshape(t * b, width)[fwd].reshape(t, len(lengths), width)
        state = tuple(s[:, lane] * keep[None, :, None] for s in state)
        out, _ = self.core(pack_padded_sequence(x, lengths), state[0] if self.memory == "gru" else state)
        out = pad_packed_sequence(out, total_length=t)[0]
        return out.reshape(-1, self.size)[inv].reshape(t, b, self.size)


def rnn_plan(done: np.ndarray, device) -> tuple:
    """Packing of a (T, B) rollout into episode segments for the fused RNN:
    gather index into the flat (T*B) steps for the padded (T, S) segment
    batch (segments longest first), the inverse index back, each segment's
    lane, whether it continues the lane's snapshot state (else it starts an
    episode, from zeros), and the segment lengths (on the host)."""
    t, b = done.shape
    start = done.astype(bool)
    first = start.copy()
    first[0] = True                                     # every lane's first segment starts at step 0
    lane, step = np.nonzero(first.T)                    # segments by lane, then time
    following = np.append(step[1:], t)
    following[np.append(lane[1:] != lane[:-1], True)] = t
    lengths = following - step
    order = np.argsort(-lengths, kind="stable")
    lane, step, lengths = lane[order], step[order], lengths[order]
    s = len(lengths)
    segment = np.repeat(np.arange(s), lengths)
    offset = np.arange(t * b) - np.repeat(np.cumsum(lengths) - lengths, lengths)
    source = (np.repeat(step, lengths) + offset) * b + np.repeat(lane, lengths)
    padded = offset * s + segment
    fwd = np.zeros(t * s, np.int64)
    fwd[padded] = source
    inv = np.empty(t * b, np.int64)
    inv[source] = padded
    keep = ~start[step, lane]
    up = lambda a: torch.from_numpy(a).pin_memory().to(device, non_blocking=True) if device.type == "cuda" \
        else torch.from_numpy(a).to(device)
    return up(fwd), up(inv), up(lane.astype(np.int64)), up(keep.astype(np.float32)), torch.from_numpy(lengths)


class CausalMemory(nn.Module):
    """Pre-LN causal self-attention over the last `length` steps of an episode."""

    def __init__(self, width: int, size: int, length: int, layers: int = LAYERS):
        super().__init__()
        if length < 2:
            raise ValueError("transformer memory_len must be at least 2")
        self.size, self.length, self.n_layers = size, length, layers
        self.heads = max(1, size // HEAD_WIDTH)
        if size % self.heads:
            raise ValueError(f"memory_size {size} must be a multiple of {HEAD_WIDTH} (or smaller than it)")
        self.token = nn.Linear(width, size)
        self.ln1 = nn.ModuleList(nn.LayerNorm(size) for _ in range(layers))
        self.qkv = nn.ModuleList(nn.Linear(size, 3 * size) for _ in range(layers))
        self.out = nn.ModuleList(nn.Linear(size, size) for _ in range(layers))
        self.ln2 = nn.ModuleList(nn.LayerNorm(size) for _ in range(layers))
        self.mlp = nn.ModuleList(nn.Sequential(nn.Linear(size, 4 * size), nn.GELU(), nn.Linear(4 * size, size))
                                 for _ in range(layers))
        self.ln_f = nn.LayerNorm(size)
        # Learned bias per head and step offset 0..length-1: the only position signal.
        self.offset_bias = nn.Parameter(torch.zeros(layers, self.heads, length))
        # Residual branches start closed: initially the memory is a function of
        # the current step only, and attention opens up as it learns.
        for layer in (*self.out, *(m[2] for m in self.mlp)):
            nn.init.zeros_(layer.weight)
            nn.init.zeros_(layer.bias)

    # state = (kv ring (layers, n, length, 2*size), episode position of the next
    #          step (n,) long, ring write slot () long). All lanes step together.
    def initial_state(self, n, device):
        return (torch.zeros((self.n_layers, n, self.length, 2 * self.size), device=device),
                torch.zeros(n, dtype=torch.long, device=device),
                torch.zeros((), dtype=torch.long, device=device))

    def snapshot(self, state):
        """K/V of the length-1 steps before the next one, oldest first, and the
        next step's episode position before any reset."""
        ring, position, slot = state
        order = (slot + 1 + torch.arange(self.length - 1, device=ring.device)) % self.length
        return ring[:, :, order].detach().clone(), position.detach().clone()

    def _attend(self, q, k, v, bias):
        # q (n, H, Q, d), k/v (n, H, K, d), bias (n or 1, H, Q, K) with -inf masked
        scores = q @ k.transpose(-1, -2) / math.sqrt(q.shape[-1]) + bias
        return scores.softmax(-1) @ v

    def _split(self, x):          # (..., size) -> (..., H, d)
        return x.unflatten(-1, (self.heads, self.size // self.heads))

    def step(self, g, state, done):
        ring, position, slot = state
        n = g.shape[0]
        position = position * (1 - done.long())
        # Offset of each ring slot from the step being written; usable iff it
        # lies within this episode.
        offset = (slot - torch.arange(self.length, device=g.device)) % self.length       # (L,)
        valid = offset[None, :] <= position[:, None]                                       # (n, L)
        x = self.token(g)
        for l in range(self.n_layers):
            q, k, v = self.qkv[l](self.ln1[l](x)).chunk(3, -1)
            ring[l].index_copy_(1, slot[None], torch.cat((k, v), -1)[:, None])
            keys, values = ring[l].chunk(2, -1)                                            # (n, L, size)
            bias = self.offset_bias[l][:, offset][None].expand(n, -1, -1)                  # (n, H, L)
            bias = bias.masked_fill(~valid[:, None, :], float("-inf"))
            a = self._attend(self._split(q)[:, :, None], self._split(keys).transpose(1, 2),
                             self._split(values).transpose(1, 2), bias[:, :, None])         # (n, H, 1, d)
            x = x + self.out[l](a.flatten(1))
            x = x + self.mlp[l](self.ln2[l](x))
        return self.ln_f(x), (ring, position + 1, (slot + 1) % self.length)

    def sequence(self, g, snapshot, done):
        prefix, position0 = snapshot                       # (layers, B, P, 2*size), (B,)
        t, b, _ = g.shape
        p = self.length - 1
        steps = torch.arange(t, device=g.device)
        # Episode position of every step: steps since the last start in this
        # rollout, else continuing from the snapshot's position.
        last = torch.where(done.bool(), steps[:, None], -1).cummax(0).values                 # (T, B)
        position = torch.where(last >= 0, steps[:, None] - last, position0[None] + steps[:, None]).T  # (B, T)
        distance = (p + steps)[:, None] - torch.arange(p + t, device=g.device)[None]          # (T, P+T)
        valid = (distance >= 0) & (distance < self.length)
        valid = valid[None] & (distance[None] <= position[:, :, None])                        # (B, T, P+T)
        index = distance.clamp(0, self.length - 1)
        x = self.token(g.transpose(0, 1))                                                   # (B, T, size)
        for l in range(self.n_layers):
            q, k, v = self.qkv[l](self.ln1[l](x)).chunk(3, -1)
            keys = torch.cat((prefix[l, ..., :self.size], k), 1)
            values = torch.cat((prefix[l, ..., self.size:], v), 1)
            bias = self.offset_bias[l][:, index][None]                                      # (1, H, T, P+T)
            bias = bias.masked_fill(~valid[:, None], float("-inf"))
            a = self._attend(self._split(q).transpose(1, 2), self._split(keys).transpose(1, 2),
                             self._split(values).transpose(1, 2), bias)                     # (B, H, T, d)
            x = x + self.out[l](a.transpose(1, 2).flatten(2))
            x = x + self.mlp[l](self.ln2[l](x))
        return self.ln_f(x).transpose(0, 1)                                                 # (T, B, size)
