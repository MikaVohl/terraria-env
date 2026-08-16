import argparse
import json
import time
from collections import Counter, deque
import random
import copy

import numpy as np
import torch
import torch.nn as nn

from terraria_lite import SPEC, TerrariaLite


# ---- hyperparameters ------------------------------------------------------
GAMMA       = 0.999   # 0.99 has a 69-step half-life against 3000-step episodes,
                      # which discounts the whole tech tree to nothing
LR          = 1e-4
# Two knobs that must move together. What matters for learning is the replay
# ratio, BATCH / TRAIN_EVERY = 32 gradient samples per env step; what matters
# for wall clock is how many torch ops launch per env step. Batching 4x bigger
# 4x less often holds the ratio and doubles throughput.
BATCH       = 512
TRAIN_EVERY = 16
BUFFER      = 100_000   # 100k x 1836 floats x 4 bytes x 2 (s and s2) = ~1.5 GB
LEARN_START = 5_000    # collect before training on it
# In env steps, so it scales with TRAIN_EVERY: 8000/16 = 500 gradient updates
# per sync, the same target staleness as the old 2000/4.
TARGET_SYNC = 8_000
EPS_START, EPS_END, EPS_DECAY = 1.0, 0.05, 400_000
# One-step TD walks a reward backwards one state per target sync, so a payoff
# 500 steps away needs ~500 syncs to reach the start. Dense penalties (fall
# damage) propagate instantly because they are everywhere; the sparse
# achievement payoffs do not. That asymmetry is why raising GAMMA alone made
# the agent MORE timid -- it scaled up the only half the bootstrap could see.
# n-step closes the gap n times faster.
NSTEP       = 10

# A 1.2M-parameter MLP at batch 128 is small enough that MPS kernel-launch
# overhead usually loses to plain CPU here. Measure before believing otherwise.
DEVICE = torch.device("cpu")


class Replay:
    """Ring buffer of transitions.

    DQN is off-policy for a reason: consecutive steps in one episode are nearly
    identical, and training on them in order diverges. Storing them and
    sampling uniformly breaks that correlation."""

    def __init__(self, cap, obs_size, n_actions):
        self.s    = np.zeros((cap, obs_size), dtype=np.float32)
        self.s2   = np.zeros((cap, obs_size), dtype=np.float32)
        self.a    = np.zeros(cap, dtype=np.int64)
        self.r    = np.zeros(cap, dtype=np.float32)
        self.done = np.zeros(cap, dtype=np.float32)
        # Per-transition discount: gamma**n for a full window, gamma**k for the
        # short tails flushed at an episode end. Storing it keeps `update` from
        # having to care which kind it drew.
        self.g    = np.zeros(cap, dtype=np.float32)
        # The bootstrap is a max over the NEXT state's legal actions, so the
        # next state's mask has to travel with the transition. 36 bytes a row.
        self.m2   = np.zeros((cap, n_actions), dtype=bool)
        self.cap, self.i, self.n = cap, 0, 0

    def push(self, s, a, r, s2, done, g, m2):
        i = self.i
        self.s[i], self.a[i], self.r[i], self.s2[i] = s, a, r, s2
        self.done[i], self.g[i], self.m2[i] = done, g, m2
        self.i = (i + 1) % self.cap
        self.n = min(self.n + 1, self.cap)

    def sample(self, batch):
        k = np.random.randint(0, self.n, size=batch)
        pick = lambda x: torch.from_numpy(x[k]).to(DEVICE)
        return (pick(self.s), pick(self.a), pick(self.r), pick(self.s2),
                pick(self.done), pick(self.g), pick(self.m2))


class NStep:
    """Folds NSTEP transitions into one before they reach the replay buffer.

    Emits (s_t, a_t, sum_k gamma^k r_{t+k}, s_{t+n}, done, gamma^n). A terminal
    inside the window truncates it, and the leftover suffixes are flushed when
    the episode ends, so no transition is lost and none bootstraps past a
    death."""

    def __init__(self, n, gamma, sink):
        self.n, self.gamma, self.sink = n, gamma, sink
        self.buf: deque = deque()

    def push(self, s, a, r, s2, done, m2):
        self.buf.append((s, a, r, s2, done, m2))
        if len(self.buf) >= self.n:
            self._emit()
            self.buf.popleft()
        if done:
            while self.buf:
                self._emit()
                self.buf.popleft()

    def _emit(self):
        ret, g, last = 0.0, 1.0, len(self.buf) - 1
        for j, (_, _, r, _, d, _) in enumerate(self.buf):
            ret += g * r
            g *= self.gamma
            if d:
                last = j
                break
        s, a = self.buf[0][0], self.buf[0][1]
        s2, done, m2 = self.buf[last][3], self.buf[last][4], self.buf[last][5]
        self.sink(s, a, ret, s2, done, g, m2)


def update(Q, Q_target, opt, batch) -> float:
    """One gradient step on the Bellman residual."""
    s, a, r, s2, done, g, m2 = batch

    # Q(s, a) for the action actually taken: one column per row.
    q = Q(s).gather(1, a.unsqueeze(1)).squeeze(1)

    # The target is a constant, not something to differentiate through, and it
    # comes from the frozen copy. Regressing toward a target that moves every
    # step is the classic way to make this diverge.
    with torch.no_grad():
        # max over what is actually available in s2. Bootstrapping through an
        # action the agent could never take inflates every value upstream of
        # it. -inf is safe here only because the C side always leaves `noop`
        # legal, so no row is empty and the max is never -inf.
        q2 = Q_target(s2).masked_fill(~m2, float("-inf")).max(1).values
        y = r + g * (1.0 - done) * q2

    loss = nn.functional.smooth_l1_loss(q, y)   # Huber: tolerant of outlier targets
    opt.zero_grad()
    loss.backward()
    nn.utils.clip_grad_norm_(Q.parameters(), 10.0)
    opt.step()
    return loss.item()

def run(episodes: int = 200, seed0: int = 1, quiet: bool = False,
        save: str = "dqn_terraria.pt") -> dict:
    # The world seed alone is not the run seed: network init, epsilon-greedy
    # draws and replay sampling all pull from torch/random/numpy. Leaving
    # those unseeded made two "identical" runs differ by 0.4 achievements.
    torch.manual_seed(seed0)
    random.seed(seed0)
    np.random.seed(seed0)
    if not quiet:
        print("Running", episodes, "episodes")
    env = TerrariaLite()
    totals, lengths, returns = [], [], []
    first_steps = []
    # Per-episode, not running totals: a whole-run average blends the
    # random-epsilon phase into the result and hides what the policy
    # actually converged to.
    masks: list[int] = []
    died: list[int] = []

    # initialize deep Q network
    # observations are in a struct {tile, light, status}

    Q = nn.Sequential(
        nn.Linear(SPEC.obs_size, 512),
        nn.ReLU(),
        nn.Linear(512, 512),
        nn.ReLU(),
        nn.Linear(512, SPEC.n_actions)
    )
    Q.to(DEVICE)

    # The frozen copy that produces the bootstrap target. A deep copy tracks
    # whatever you change Q to, which a hand-rebuilt net would not.
    Q_target = copy.deepcopy(Q).to(DEVICE)
    Q_target.load_state_dict(Q.state_dict())
    opt = torch.optim.Adam(Q.parameters(), lr=LR)
    buf = Replay(BUFFER, SPEC.obs_size, SPEC.n_actions)
    nstep = NStep(NSTEP, GAMMA, buf.push)

    steps = 0
    t0 = time.perf_counter()
    for ep in range(episodes):
        if ep % 25 == 0 and not quiet:
            print("Episode", ep)
        obs, info = env.reset(seed=seed0 + ep)
        mask = env.action_mask()
        assert obs.shape == (SPEC.obs_size,), obs.shape
        first = None
        while True:
            # Linear anneal: mostly random early, mostly greedy later. Without
            # this, argmax over a fresh net is one fixed action forever.
            eps = max(EPS_END,
                      EPS_START - (EPS_START - EPS_END) * steps / EPS_DECAY)

            # Both branches respect the mask. Exploring into inert actions is
            # not exploration, and an argmax that can pick one wastes the step
            # AND trains on a transition that teaches nothing.
            if random.random() < eps:
                a = int(np.random.choice(np.flatnonzero(mask)))
            else:
                with torch.no_grad():     # choosing is not part of the gradient
                    q = Q(torch.from_numpy(obs).to(DEVICE))
                    a = int(q.masked_fill(~torch.from_numpy(mask), float("-inf"))
                             .argmax())

            next_obs, r, terminated, truncated, info = env.step(a)
            next_mask = env.action_mask()

            # `terminated` alone, never `terminated or truncated`. Dying means
            # there is no future to bootstrap from; running out of steps does
            # not -- the world was still going. Conflating them teaches the
            # agent that the world ends at 3000 steps.
            nstep.push(obs, a, r, next_obs, float(terminated), next_mask)
            obs, mask = next_obs, next_mask
            steps += 1

            if buf.n >= LEARN_START and steps % TRAIN_EVERY == 0:
                update(Q, Q_target, opt, buf.sample(BATCH))
            if steps % TARGET_SYNC == 0:
                Q_target.load_state_dict(Q.state_dict())

            if first is None and info["achievements"]:
                first = info["steps"]
            if terminated or truncated:
                break
        died.append(1 if terminated else 0)
        totals.append(info["achievements"])
        lengths.append(info["steps"])
        returns.append(info["episode_return"])
        if first is not None:
            first_steps.append(first)
        masks.append(info["achievement_mask"])

    dt = time.perf_counter() - t0

    # The trailing window is the honest number. Everything before epsilon
    # reaches its floor is a random policy wearing a DQN costume.
    w = max(1, min(100, episodes // 2))

    def block(label, tot, ret, ln, dd, ms):
        print(f"  {label}")
        print(f"    mean achievements {np.mean(tot):.2f} / {SPEC.n_achievements}")
        print(f"    mean return       {np.mean(ret):+.2f}")
        print(f"    mean episode      {np.mean(ln):.0f} steps")
        print(f"    died              {100 * np.mean(dd):.0f}%")
        for i in range(SPEC.n_achievements):
            hits = sum((m >> i) & 1 for m in ms)
            if hits:
                print(f"      {SPEC.achievement_names[i]:<18} "
                      f"{100 * hits / len(ms):5.1f}%  ({hits}/{len(ms)})")

    print(f"{SPEC}\n")
    print(f"DQN, {episodes} episodes, final eps {eps:.2f}, "
          f"{steps:,} env steps, {steps / dt:,.0f} steps/s")
    if first_steps:
        print(f"  first achievement   {np.mean(first_steps):.0f} steps "
              f"(in {100 * len(first_steps) // episodes}% of episodes)")
    print()
    block(f"last {w} episodes (what the policy converged to):",
          totals[-w:], returns[-w:], lengths[-w:], died[-w:], masks[-w:])
    print()
    block(f"all {episodes} episodes (blended with the epsilon ramp):",
          totals, returns, lengths, died, masks)

    walls = [SPEC.achievement_names[i] for i in range(SPEC.n_achievements)
             if not any((m >> i) & 1 for m in masks[-w:])]
    print(f"\n  never reached in the last {w} ({len(walls)}): "
          f"{walls[0] if walls else '-'} is the first wall")

    if save:
        # Plain Sequential state dict; terraria_lite.watch sniffs the keys to
        # tell it apart from a PPO ActorCritic.
        torch.save(Q.state_dict(), save)
        if not quiet:
            print(f"\n  saved {save}")

    summary = {
        "agent": "dqn", "seed": seed0, "gamma": GAMMA, "nstep": NSTEP,
        "episodes": episodes, "env_steps": steps, "sps": round(steps / dt),
        "window": w,
        "ach": float(np.mean(totals[-w:])), "ret": float(np.mean(returns[-w:])),
        "len": float(np.mean(lengths[-w:])), "died": float(np.mean(died[-w:])),
        "hits": {SPEC.achievement_names[i]: sum((m >> i) & 1 for m in masks[-w:])
                 for i in range(SPEC.n_achievements)
                 if any((m >> i) & 1 for m in masks[-w:])},
    }

    if not quiet:
        print("\n  what the agent actually sees at spawn "
              "(blank = unlit, and therefore unknown):")
        env.reset(seed=seed0)
        for line in env.render_ascii().splitlines():
            print("   |" + line + "|")
    env.close()
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="DQN for terraria-lite. Work is measured in EPISODES; "
                    "epsilon needs ~160 of them to reach its floor, so fewer "
                    "than that measures a random policy. This agent is masked, "
                    "so the baseline to beat is masked-random: 4.18 / 24 "
                    "achievements, +3.41 return (unmasked random is 3.91).")
    p.add_argument("episodes", nargs="?", type=int, default=200)
    p.add_argument("--seed", type=int, default=1,
                   help="world/torch seed; sweep it before trusting a delta")
    p.add_argument("--json", action="store_true",
                   help="emit the trailing-window summary as one JSON line")
    p.add_argument("--save", type=str, default="dqn_terraria.pt",
                   help='checkpoint path, "" to skip; '
                        "terraria_lite.watch replays one")
    a = p.parse_args()
    s = run(a.episodes, seed0=a.seed, quiet=a.json, save=a.save)
    if a.json:
        print(json.dumps(s))
