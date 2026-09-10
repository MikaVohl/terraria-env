"""PPO for terraria-lite.

Feedforward, synchronous-vectorised, single file. Not optimised -- the point is
that every part is correct and legible, so that when it is optimised later the
baseline it is being compared against is trustworthy.

    uv run python -m terraria_lite.ppo_agent --steps 500000

Three things here are specific to this environment rather than boilerplate, and
they are the ones worth reading:

1.  Truncation is bootstrapped, termination is not. Dying means there is no
    future; hitting the 3000-step limit means the world carried on without us.
    This env keeps `terminated` and `truncated` separate precisely so that
    distinction is expressible, and collapsing them teaches the agent that the
    world ends at 3000 steps. See `_absorb_truncation`.

2.  The environment is cheap (~58k steps/s through ctypes) and the network is
    small, so the gradient step dominates, not the simulator. That argues for
    many parallel envs and big batches rather than a faster env, which is why
    NUM_ENVS is high and why there is no C-side batching yet.

3.  Observations already live in [0, 1] (env_obs normalises them), so there is
    no observation normaliser here. One less thing to get subtly wrong.

The environment is partially observable by design -- roughly 80% of the
underground view reads as unlit. `recurrent_ppo_agent.py` tests the natural LSTM
extension while preserving the (T, N, ...) rollout layout. At 600k steps it was
slower and worse than the feed-forward progression-shaped agent: memory alone
did not solve the hierarchical credit problem. See PPO_EXPERIMENTS.md.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Categorical

from terraria_lite import SPEC, TerrariaLite


# ---------------------------------------------------------------- config ---

@dataclass
class Config:
    total_steps: int = 500_000
    num_envs: int = 16
    rollout: int = 128          # steps per env per iteration -> batch 2048
    epochs: int = 4
    minibatches: int = 4
    lr: float = 3e-4
    anneal_lr: bool = True
    # Episodes run to 3000 steps and the payoffs are sparse and one-shot, so
    # the usual 0.99 (69-step half-life) discounts the entire tech tree to
    # noise. Measured over 3 seeds at 600k steps: 0.99 -> 3.86 achievements and
    # the workbench never once crafted; 0.999 -> 5.18 and 22% workbench rate.
    # 0.9995 overshoots (4.33) -- the horizon stops helping before 1.0.
    gamma: float = 0.999
    gae_lambda: float = 0.95
    clip_coef: float = 0.2
    clip_vloss: bool = True
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    target_kl: float | None = 0.03   # early-stop an epoch that moves too far
    # Optional dense training-only feedback for progress toward the next
    # crafting prerequisites. Environment returns and evaluation remain purely
    # extrinsic, so this knob can be compared honestly against vanilla PPO.
    progress_coef: float = 0.0
    progress_anneal: bool = False
    seed: int = 1
    device: str = "cpu"              # a 1.5M MLP at batch 2048 loses to MPS overhead
    quiet: bool = False              # suppress per-iteration lines when sweeping
    save: str = "ppo_terraria.pt"    # "" to skip, so parallel sweeps don't collide
    init: str = ""                    # optional actor/critic state_dict warm start

    @property
    def batch(self) -> int:
        return self.num_envs * self.rollout

    @property
    def minibatch(self) -> int:
        return self.batch // self.minibatches


# ----------------------------------------------------------------- model ---

def layer_init(layer: nn.Linear, std: float = np.sqrt(2), bias: float = 0.0):
    """Orthogonal init. The head gains matter: 0.01 on the policy keeps the
    initial distribution near-uniform (so early exploration is real), 1.0 on
    the value head keeps early value estimates small."""
    nn.init.orthogonal_(layer.weight, std)
    nn.init.constant_(layer.bias, bias)
    return layer


class ActorCritic(nn.Module):
    """Shared trunk, separate heads. The trunk is shared because the features
    that predict value are the features that pick actions here; the heads are
    separate because their output scales are nothing alike."""

    def __init__(self, obs_size: int, n_actions: int, hidden: int = 512):
        super().__init__()
        self.trunk = nn.Sequential(
            layer_init(nn.Linear(obs_size, hidden)), nn.Tanh(),
            layer_init(nn.Linear(hidden, hidden)), nn.Tanh(),
        )
        self.actor = layer_init(nn.Linear(hidden, n_actions), std=0.01)
        self.critic = layer_init(nn.Linear(hidden, 1), std=1.0)

    def value(self, x):
        return self.critic(self.trunk(x)).squeeze(-1)

    def act(self, x, action=None, mask=None):
        h = self.trunk(x)
        logits = self.actor(h)
        if mask is not None:
            # -inf, not a large negative: softmax then puts exactly zero mass on
            # invalid actions, and their gradient is exactly zero too. The C side
            # guarantees at least `noop` survives, so no row is all -inf.
            logits = logits.masked_fill(~mask, float("-inf"))
        dist = Categorical(logits=logits)
        if action is None:
            action = dist.sample()
        return action, dist.log_prob(action), dist.entropy(), self.critic(h).squeeze(-1)


# ------------------------------------------------------------ vectorised ---

class VecTerraria:
    """Synchronous vector of environments with explicit autoreset.

    Rolled by hand rather than using gymnasium's vector API for one reason:
    when an episode ends we need the *true* terminal observation to bootstrap
    a truncation, and owning the reset makes that unambiguous.
    """

    def __init__(self, n: int, seed: int = 1):
        self.envs = [TerrariaLite() for _ in range(n)]
        self.n = n
        self._next_seed = seed
        self.obs = np.zeros((n, SPEC.obs_size), dtype=np.float32)
        self.mask = np.zeros((n, SPEC.n_actions), dtype=bool)

    def _fresh_seed(self) -> int:
        s = self._next_seed
        self._next_seed += 1
        return s

    def reset(self) -> tuple[np.ndarray, np.ndarray]:
        for i, e in enumerate(self.envs):
            self.obs[i] = e.reset(seed=self._fresh_seed())[0]
            self.mask[i] = e.action_mask()
        return self.obs, self.mask

    def step(self, actions):
        """Returns (obs, mask, reward, terminated, truncated, final_obs, infos).

        `obs`/`mask` are what to act from next -- already reset where an
        episode ended. `final_obs` holds the real terminal observation for
        those lanes, which is what a truncated episode must bootstrap from.
        """
        rew = np.zeros(self.n, dtype=np.float32)
        term = np.zeros(self.n, dtype=bool)
        trunc = np.zeros(self.n, dtype=bool)
        final = np.zeros((self.n, SPEC.obs_size), dtype=np.float32)
        finished = []

        for i, e in enumerate(self.envs):
            o, r, te, tr, info = e.step(int(actions[i]))
            rew[i], term[i], trunc[i] = r, te, tr
            if te or tr:
                final[i] = o                      # before it is thrown away
                finished.append((i, info))
                o = e.reset(seed=self._fresh_seed())[0]
            self.obs[i] = o
            self.mask[i] = e.action_mask()
        return self.obs, self.mask, rew, term, trunc, final, finished

    def close(self):
        for e in self.envs:
            e.close()


class ProgressShaper:
    """Capped episodic feedback for making useful crafting progress.

    Sparse +1 achievements make gathering the eighth wood indistinguishable
    from wandering after the first. Each component below tracks readiness for
    one tech-tree milestone and pays only for a new per-episode maximum. That
    prevents mining/crafting cycles from farming shaping reward. This changes
    training reward only; reported episode returns remain the environment's.
    """

    def __init__(self, n: int):
        self.n = n
        self.best = np.zeros((n, 11), dtype=np.float32)
        self.status0 = SPEC.cells * SPEC.tile_kinds + SPEC.cells
        self.inv0 = self.status0 + SPEC.status_inv0
        self.ach0 = self.status0 + SPEC.status_ach0
        self.item = {name: i for i, name in enumerate(SPEC.item_names)}
        self.ach = {name: i for i, name in enumerate(SPEC.achievement_names)}

    def _features(self, obs: np.ndarray) -> np.ndarray:
        obs = np.atleast_2d(obs)
        inv = (obs[:, self.inv0:self.inv0 + SPEC.n_items]
               * float(SPEC.inventory_clip))
        ach = obs[:, self.ach0:self.ach0 + SPEC.n_achievements]
        item = lambda name: inv[:, self.item[name]]
        done = lambda name: ach[:, self.ach[name]]
        gate = lambda name: done(name) > 0.5
        ratio = lambda have, need: np.minimum(have / need, 1.0)
        ready = lambda *parts: np.minimum.reduce(parts)

        f = np.zeros((len(obs), 11), dtype=np.float32)
        # A completed milestone pins its component at one. Before its immediate
        # prerequisite exists the component stays zero, so future-tier ore
        # cannot accidentally shape an exploit.
        f[:, 0] = np.where(gate("craft workbench"), 1.0, ratio(item("wood"), 8))
        wb = gate("craft workbench")
        f[:, 1] = np.where(gate("craft furnace"), 1.0,
                           np.where(wb, ratio(item("stone"), 12), 0.0))
        f[:, 2] = np.where(gate("craft stone pick"), 1.0,
                           np.where(wb, ready(ratio(item("wood"), 3),
                                             ratio(item("stone"), 5)), 0.0))
        stone_pick = gate("craft stone pick")
        f[:, 3] = np.where(gate("smelt copper"), 1.0,
                           np.where(stone_pick, ratio(item("copper ore"), 3), 0.0))
        smelt_copper = gate("smelt copper")
        f[:, 4] = np.where(gate("craft torch"), 1.0,
                           np.where(smelt_copper,
                                    ready(ratio(item("copper bar"), 1),
                                          ratio(item("wood"), 2)), 0.0))
        f[:, 5] = np.where(gate("craft copper pick"), 1.0,
                           np.where(smelt_copper,
                                    ready(ratio(item("copper bar"), 2),
                                          ratio(item("wood"), 3)), 0.0))
        copper_pick = gate("craft copper pick")
        f[:, 6] = np.where(gate("smelt iron"), 1.0,
                           np.where(copper_pick, ratio(item("iron ore"), 3), 0.0))
        smelt_iron = gate("smelt iron")
        f[:, 7] = np.where(gate("craft anvil"), 1.0,
                           np.where(smelt_iron, ratio(item("iron bar"), 5), 0.0))
        anvil = gate("craft anvil")
        f[:, 8] = np.where(gate("craft iron pick"), 1.0,
                           np.where(anvil,
                                    ready(ratio(item("iron bar"), 2),
                                          ratio(item("wood"), 3)), 0.0))
        iron_pick = gate("craft iron pick")
        f[:, 9] = np.where(gate("smelt gold"), 1.0,
                           np.where(iron_pick, ratio(item("gold ore"), 3), 0.0))
        smelt_gold = gate("smelt gold")
        f[:, 10] = np.where(gate("craft lantern"), 1.0,
                            np.where(smelt_gold,
                                     ready(ratio(item("gold bar"), 1),
                                           ratio(item("wood"), 3)), 0.0))
        return f

    def reset(self, obs: np.ndarray) -> None:
        self.best[:] = self._features(obs)

    def step(self, obs: np.ndarray, final_obs: np.ndarray,
             term: np.ndarray, trunc: np.ndarray) -> np.ndarray:
        boundary = np.logical_or(term, trunc)
        state = obs.copy()
        state[boundary] = final_obs[boundary]
        current = self._features(state)
        gain = np.maximum(current - self.best, 0.0).sum(axis=1)
        self.best = np.maximum(self.best, current)
        # `obs` is already the reset state in boundary lanes.
        if boundary.any():
            self.best[boundary] = self._features(obs[boundary])
        return gain


# ------------------------------------------------------------------ train ---

def _absorb_truncation(cfg, agent, rewards, term, trunc, final_obs, t, device):
    """Fold the bootstrap for truncated episodes into the reward.

    Autoreset means the observation after a boundary belongs to a fresh world.
    Both termination and truncation must therefore cut GAE recurrence; otherwise
    an advantage leaks into the next episode. A truncation still has a future
    value, though, so gamma * V(final_obs) is folded into its reward before that
    cut. A true termination gets no such bootstrap -- death really is the end.
    """
    cut = np.logical_and(trunc, np.logical_not(term))
    if not cut.any():
        return
    with torch.no_grad():
        v = agent.value(torch.as_tensor(final_obs[cut], device=device))
    rewards[t, torch.as_tensor(cut, device=device)] += cfg.gamma * v


def compute_gae(rewards, dones, values, next_value, next_done,
                gamma: float, gae_lambda: float):
    """Generalized advantages for a (T,N) rollout.

    `dones[t]` means obs[t] starts a new episode. `next_done` applies to the
    observation immediately after the rollout. Keeping this small and pure
    makes the autoreset-boundary convention directly testable.
    """
    advantages = torch.zeros_like(rewards)
    last = torch.zeros_like(next_value)
    for t in reversed(range(len(rewards))):
        if t == len(rewards) - 1:
            nonterminal, next_val = 1.0 - next_done, next_value
        else:
            nonterminal, next_val = 1.0 - dones[t + 1], values[t + 1]
        delta = rewards[t] + gamma * next_val * nonterminal - values[t]
        last = delta + gamma * gae_lambda * nonterminal * last
        advantages[t] = last
    return advantages


def train(cfg: Config, checkpoint_callback=None):
    if cfg.num_envs < 1 or cfg.rollout < 1 or cfg.total_steps < cfg.batch:
        raise ValueError("training requires positive dimensions and at least one batch")
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    device = torch.device(cfg.device)

    envs = VecTerraria(cfg.num_envs, seed=cfg.seed)
    agent = ActorCritic(SPEC.obs_size, SPEC.n_actions).to(device)
    if cfg.init:
        raw = torch.load(cfg.init, map_location=device, weights_only=True)
        agent.load_state_dict(raw.get("model", raw) if isinstance(raw, dict) else raw)
    opt = torch.optim.Adam(agent.parameters(), lr=cfg.lr, eps=1e-5)

    T, N = cfg.rollout, cfg.num_envs
    obs_b = torch.zeros((T, N, SPEC.obs_size), device=device)
    act_b = torch.zeros((T, N), dtype=torch.long, device=device)
    logp_b = torch.zeros((T, N), device=device)
    rew_b = torch.zeros((T, N), device=device)
    done_b = torch.zeros((T, N), device=device)
    val_b = torch.zeros((T, N), device=device)
    # Stored, not recomputed: the update pass must score actions under the same
    # support they were sampled from, or the ratio is against a distribution
    # that never existed.
    msk_b = torch.zeros((T, N, SPEC.n_actions), dtype=torch.bool, device=device)

    o0, m0 = envs.reset()
    shaper = ProgressShaper(N) if cfg.progress_coef else None
    if shaper is not None:
        shaper.reset(o0)
    next_obs = torch.as_tensor(o0, device=device)
    next_mask = torch.as_tensor(m0, device=device)
    next_done = torch.zeros(N, device=device)

    n_iters = cfg.total_steps // cfg.batch
    ep_returns, ep_achievements, ep_lengths, ep_deaths = [], [], [], []
    ep_masks: list[int] = []          # which achievements, not just how many
    start = time.perf_counter()
    step_count = 0
    collection_seconds = optimisation_seconds = 0.0

    print(f"{SPEC}")
    print(f"PPO: {N} envs x {T} steps = batch {cfg.batch}, "
          f"{n_iters} iterations, {cfg.total_steps:,} env steps\n")
    print(f"{'iter':>5} {'steps':>9} {'return':>8} {'ach':>6} {'len':>6} "
          f"{'death%':>7} {'entropy':>8} {'kl':>7} {'clip':>6} {'ev':>6} {'sps':>7}")

    for it in range(1, n_iters + 1):
        if cfg.anneal_lr:
            for g in opt.param_groups:
                g["lr"] = cfg.lr * (1.0 - (it - 1.0) / n_iters)
        progress_coef = cfg.progress_coef
        if cfg.progress_anneal:
            progress_coef *= 1.0 - (it - 1.0) / n_iters

        # ---- collect ----------------------------------------------------
        phase_start = time.perf_counter()
        for t in range(T):
            obs_b[t] = next_obs
            done_b[t] = next_done
            msk_b[t] = next_mask
            with torch.no_grad():
                a, logp, _, v = agent.act(next_obs, mask=next_mask)
            act_b[t], logp_b[t], val_b[t] = a, logp, v

            obs, msk, r, term, trunc, final, finished = envs.step(a.cpu().numpy())
            if shaper is not None:
                r = r + progress_coef * shaper.step(obs, final, term, trunc)
            rew_b[t] = torch.as_tensor(r, device=device)
            _absorb_truncation(cfg, agent, rew_b, term, trunc, final, t, device)

            next_obs = torch.as_tensor(obs, device=device)
            next_mask = torch.as_tensor(msk, device=device)
            # Autoreset makes both kinds episode boundaries. Truncation's true
            # final-state bootstrap was already folded into rew_b above; using
            # only `term` here would add V(reset_obs) as well and carry GAE from
            # an unrelated fresh world across the boundary.
            boundary = np.logical_or(term, trunc)
            next_done = torch.as_tensor(boundary.astype(np.float32), device=device)
            step_count += N

            for _, info in finished:
                ep_returns.append(info["episode_return"])
                ep_achievements.append(info["achievements"])
                ep_lengths.append(info["steps"])
                ep_deaths.append(1.0 if info["health"] <= 0 else 0.0)
                ep_masks.append(info["achievement_mask"])

        collection_seconds += time.perf_counter() - phase_start
        phase_start = time.perf_counter()
        # ---- GAE ---------------------------------------------------------
        with torch.no_grad():
            next_value = agent.value(next_obs)
            adv = compute_gae(rew_b, done_b, val_b, next_value, next_done,
                              cfg.gamma, cfg.gae_lambda)
            ret = adv + val_b

        b_obs = obs_b.reshape(-1, SPEC.obs_size)
        b_act = act_b.reshape(-1)
        b_logp = logp_b.reshape(-1)
        b_adv = adv.reshape(-1)
        b_ret = ret.reshape(-1)
        b_val = val_b.reshape(-1)
        b_msk = msk_b.reshape(-1, SPEC.n_actions)

        # ---- optimise ----------------------------------------------------
        idx = np.arange(cfg.batch)
        clipfracs, approx_kl = [], torch.tensor(0.0)
        for _ in range(cfg.epochs):
            np.random.shuffle(idx)
            for s in range(0, cfg.batch, cfg.minibatch):
                mb = idx[s: s + cfg.minibatch]
                _, newlogp, entropy, newval = agent.act(b_obs[mb], b_act[mb],
                                                        mask=b_msk[mb])
                logratio = newlogp - b_logp[mb]
                ratio = logratio.exp()

                with torch.no_grad():
                    # Schulman's low-variance KL estimator; also the early-stop signal.
                    approx_kl = ((ratio - 1) - logratio).mean()
                    clipfracs.append(
                        ((ratio - 1.0).abs() > cfg.clip_coef).float().mean().item())

                # Normalise advantages per minibatch, not per batch.
                mb_adv = b_adv[mb]
                mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)

                pg = torch.max(-mb_adv * ratio,
                               -mb_adv * torch.clamp(ratio, 1 - cfg.clip_coef,
                                                     1 + cfg.clip_coef)).mean()

                if cfg.clip_vloss:
                    v_unclipped = (newval - b_ret[mb]) ** 2
                    v_clipped = (b_val[mb] + torch.clamp(
                        newval - b_val[mb], -cfg.clip_coef, cfg.clip_coef)
                        - b_ret[mb]) ** 2
                    v_loss = 0.5 * torch.max(v_unclipped, v_clipped).mean()
                else:
                    v_loss = 0.5 * ((newval - b_ret[mb]) ** 2).mean()

                loss = pg - cfg.ent_coef * entropy.mean() + cfg.vf_coef * v_loss

                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), cfg.max_grad_norm)
                opt.step()

            if cfg.target_kl is not None and approx_kl > cfg.target_kl:
                break

        optimisation_seconds += time.perf_counter() - phase_start
        if checkpoint_callback is not None:
            checkpoint_callback(agent, step_count, {
                "collection_seconds": collection_seconds,
                "optimisation_seconds": optimisation_seconds,
            })
        # ---- report ------------------------------------------------------
        y = b_ret.cpu().numpy()
        yhat = b_val.cpu().numpy()
        var = np.var(y)
        ev = np.nan if var == 0 else 1 - np.var(y - yhat) / var
        sps = step_count / (time.perf_counter() - start)
        w = slice(-50, None)          # trailing window of finished episodes
        if not cfg.quiet:
            print(f"{it:5d} {step_count:9,} "
                  f"{np.mean(ep_returns[w]) if ep_returns else 0:8.2f} "
                  f"{np.mean(ep_achievements[w]) if ep_achievements else 0:6.2f} "
                  f"{np.mean(ep_lengths[w]) if ep_lengths else 0:6.0f} "
                  f"{100 * np.mean(ep_deaths[w]) if ep_deaths else 0:7.0f} "
                  f"{entropy.mean().item():8.3f} {approx_kl.item():7.4f} "
                  f"{np.mean(clipfracs):6.3f} {ev:6.2f} {sps:7,.0f}")

    envs.close()

    tail = ep_masks[-200:]
    summary = {
        "agent": "ppo",
        "gamma": cfg.gamma, "seed": cfg.seed, "ent_coef": cfg.ent_coef,
        "progress_coef": cfg.progress_coef,
        "progress_anneal": cfg.progress_anneal,
        "lr": cfg.lr, "envs": cfg.num_envs, "steps": step_count,
        "requested_steps": cfg.total_steps,
        "collection_seconds": collection_seconds,
        "optimisation_seconds": optimisation_seconds,
        "sps": round(sps), "n_ep": len(ep_returns), "window": len(tail),
        "ach": float(np.mean(ep_achievements[-50:])) if ep_achievements else 0.0,
        "ret": float(np.mean(ep_returns[-50:])) if ep_returns else 0.0,
        "len": float(np.mean(ep_lengths[-50:])) if ep_lengths else 0.0,
        "died": float(np.mean(ep_deaths[-50:])) if ep_deaths else 0.0,
        "hits": {SPEC.achievement_names[i]: sum((m >> i) & 1 for m in tail)
                 for i in range(SPEC.n_achievements)
                 if any((m >> i) & 1 for m in tail)},
    }

    if ep_achievements and not cfg.quiet:
        print(f"\nfinal 50 episodes: {summary['ach']:.2f} / "
              f"{SPEC.n_achievements} achievements, "
              f"return {summary['ret']:+.2f}")
        # MASKED random, because this agent is masked -- comparing against an
        # unmasked baseline flatters it by the +0.27 that masking alone buys.
        # Re-measure whenever a reward weight changes; it has moved twice.
        print(f"masked-random:     4.18 / {SPEC.n_achievements} achievements, "
              f"return +3.41\n")

        # Counts, not just a rounded percentage: once the agent starts cracking
        # a wall it does so a handful of times in hundreds of episodes, and
        # integer-division would print those breakthroughs as a flat "0%".
        print(f"  hit rate over the last {len(tail)} episodes:")
        for name, hits in summary["hits"].items():
            print(f"    {name:<18} {100 * hits / len(tail):5.1f}%  "
                  f"({hits}/{len(tail)})")
        walls = [SPEC.achievement_names[i] for i in range(SPEC.n_achievements)
                 if not any((m >> i) & 1 for m in tail)]
        if walls:
            print(f"\n  still never reached ({len(walls)}): "
                  f"{walls[0]} is the wall")

    if cfg.save:
        torch.save(agent.state_dict(), cfg.save)
        if not cfg.quiet:
            print(f"\nsaved {cfg.save}")
    return summary


class _Fmt(argparse.ArgumentDefaultsHelpFormatter,
           argparse.RawDescriptionHelpFormatter):
    """Show defaults, and keep the hand-wrapped description and examples."""


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        formatter_class=_Fmt,
        description=(
            "PPO for terraria-lite.\n\n"
            "Work is measured in environment STEPS, not episodes: PPO's unit is\n"
            "the rollout batch, and episodes here run anywhere from ~300 to 3000\n"
            "steps. There is no positional argument -- use --steps.\n\n"
            "Baselines: masked-random 4.18 / 24 achievements, unmasked 3.91."
        ),
        epilog=(
            "examples:\n"
            "  --steps 100000\n"
            "      short unshaped smoke run\n"
            "  --steps 4000000 --seed 71 --progress-coef 0.5 --progress-anneal\n"
            "      best tested from-scratch recipe: 10.75/24 on 256 holdouts\n"
            "See PPO_EXPERIMENTS.md for ablations and evaluation protocol.\n"
        ),
    )
    p.add_argument("--steps", type=int, default=Config.total_steps,
                   help="total environment steps to train for")
    p.add_argument("--envs", type=int, default=Config.num_envs,
                   help="parallel environments; batch = envs * rollout")
    p.add_argument("--rollout", type=int, default=Config.rollout,
                   help="steps collected per env per iteration")
    p.add_argument("--lr", type=float, default=Config.lr,
                   help="Adam learning rate, annealed to 0 over the run")
    p.add_argument("--gamma", type=float, default=Config.gamma,
                   help="discount; 0.99 has a 69-step half-life against "
                        "3000-step episodes")
    p.add_argument("--ent-coef", type=float, default=Config.ent_coef,
                   help="entropy bonus; raise it to delay premature convergence")
    p.add_argument("--progress-coef", type=float, default=Config.progress_coef,
                   help="training-only capped prerequisite-progress feedback")
    p.add_argument("--progress-anneal", action="store_true",
                   help="linearly anneal prerequisite feedback to zero")
    p.add_argument("--seed", type=int, default=Config.seed,
                   help="torch/numpy/env seed; sweep it before trusting a delta")
    p.add_argument("--device", type=str, default=Config.device,
                   help="cpu or mps; cpu usually wins for a net this small")
    p.add_argument("--save", type=str, default=Config.save,
                   help='checkpoint path, "" to skip')
    p.add_argument("--init", type=str, default=Config.init,
                   help="optional state_dict checkpoint to warm-start from")
    p.add_argument("--quiet", action="store_true",
                   help="only the final summary; for parallel sweeps")
    p.add_argument("--json", action="store_true",
                   help="emit the summary as one JSON line on stdout")
    a = p.parse_args()
    s = train(Config(total_steps=a.steps, num_envs=a.envs, rollout=a.rollout,
                     lr=a.lr, gamma=a.gamma, ent_coef=a.ent_coef, seed=a.seed,
                     progress_coef=a.progress_coef,
                     progress_anneal=a.progress_anneal, device=a.device,
                     save=a.save, init=a.init, quiet=a.quiet))
    if a.json:
        print(json.dumps(s))
