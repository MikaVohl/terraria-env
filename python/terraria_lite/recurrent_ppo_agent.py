"""Recurrent PPO for terraria-lite's deliberately partial observation.

This keeps the proven PPO update and adds a 256-unit LSTM after a compact
observation encoder. Training minibatches contain complete per-environment
rollout sequences, and hidden state is reset at every autoreset boundary.

    uv run python -m terraria_lite.recurrent_ppo_agent --steps 2000000 \
        --progress-coef 0.5 --progress-anneal
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

from terraria_lite import SPEC
from terraria_lite.ppo_agent import (ProgressShaper, VecTerraria, compute_gae,
                                     layer_init)


@dataclass
class Config:
    total_steps: int = 1_000_000
    num_envs: int = 16
    rollout: int = 128
    epochs: int = 4
    minibatches: int = 4       # split by environment, never by time
    encoder: int = 256
    hidden: int = 256
    lr: float = 3e-4
    gamma: float = 0.999
    gae_lambda: float = 0.95
    clip_coef: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    target_kl: float | None = 0.03
    progress_coef: float = 0.0
    progress_anneal: bool = False
    seed: int = 1
    device: str = "cpu"
    save: str = "recurrent_ppo_terraria.pt"
    quiet: bool = False

    @property
    def batch(self):
        return self.num_envs * self.rollout


class RecurrentActorCritic(nn.Module):
    def __init__(self, obs_size: int, n_actions: int,
                 encoder: int = 256, hidden: int = 256):
        super().__init__()
        self.encoder_size = encoder
        self.hidden_size = hidden
        self.encoder = nn.Sequential(
            layer_init(nn.Linear(obs_size, encoder)), nn.Tanh())
        self.lstm = nn.LSTM(encoder, hidden)
        # Orthogonal recurrent blocks start with well-conditioned dynamics;
        # zero biases avoid imposing a preselected gate regime.
        for name, param in self.lstm.named_parameters():
            if "bias" in name:
                nn.init.constant_(param, 0.0)
            elif "weight_hh" in name:
                for block in param.chunk(4, 0):
                    nn.init.orthogonal_(block)
            else:
                nn.init.xavier_uniform_(param)
        self.actor = layer_init(nn.Linear(hidden, n_actions), std=0.01)
        self.critic = layer_init(nn.Linear(hidden, 1), std=1.0)

    def initial_state(self, batch: int, device) -> tuple[torch.Tensor, torch.Tensor]:
        z = torch.zeros((1, batch, self.hidden_size), device=device)
        return z, z.clone()

    @staticmethod
    def _reset(state, done):
        keep = (1.0 - done).view(1, -1, 1)
        return state[0] * keep, state[1] * keep

    def core_step(self, obs, state, done):
        state = self._reset(state, done)
        z = self.encoder(obs).unsqueeze(0)
        out, state = self.lstm(z, state)
        return out.squeeze(0), state

    def act_step(self, obs, state, done, action=None, mask=None):
        h, state = self.core_step(obs, state, done)
        logits = self.actor(h)
        if mask is not None:
            logits = logits.masked_fill(~mask, float("-inf"))
        dist = Categorical(logits=logits)
        if action is None:
            action = dist.sample()
        return (action, dist.log_prob(action), dist.entropy(),
                self.critic(h).squeeze(-1), state)

    def value_step(self, obs, state, done):
        h, state = self.core_step(obs, state, done)
        return self.critic(h).squeeze(-1), state

    def sequence(self, obs, state, done):
        """Process (T,B,obs) efficiently while respecting lane resets.

        Episode boundaries are rare relative to a 128-step rollout. Split only
        at timesteps where at least one lane resets, using the optimized fused
        LSTM for the usually-long segments between them.
        """
        z = self.encoder(obs)
        pieces, start = [], 0
        cuts = torch.nonzero(done.any(dim=1), as_tuple=False).flatten().tolist()
        for cut in cuts:
            if cut > start:
                out, state = self.lstm(z[start:cut], state)
                pieces.append(out)
            state = self._reset(state, done[cut])
            start = cut
        if start < len(z):
            out, state = self.lstm(z[start:], state)
            pieces.append(out)
        return torch.cat(pieces, dim=0), state


def _bootstrap_truncation(cfg, agent, rewards, term, trunc, final_obs,
                          state, t, device):
    cut = np.logical_and(trunc, np.logical_not(term))
    if not cut.any():
        return
    pick = torch.as_tensor(cut, device=device)
    sliced = (state[0][:, pick].contiguous(), state[1][:, pick].contiguous())
    with torch.no_grad():
        value, _ = agent.value_step(
            torch.as_tensor(final_obs[cut], device=device), sliced,
            torch.zeros(int(cut.sum()), device=device))
    rewards[t, pick] += cfg.gamma * value


def train(cfg: Config) -> dict:
    if cfg.num_envs % cfg.minibatches:
        raise ValueError("num_envs must be divisible by recurrent minibatches")
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    device = torch.device(cfg.device)
    envs = VecTerraria(cfg.num_envs, seed=cfg.seed)
    agent = RecurrentActorCritic(SPEC.obs_size, SPEC.n_actions,
                                 cfg.encoder, cfg.hidden).to(device)
    opt = torch.optim.Adam(agent.parameters(), lr=cfg.lr, eps=1e-5)

    T, N = cfg.rollout, cfg.num_envs
    obs_b = torch.zeros((T, N, SPEC.obs_size), device=device)
    act_b = torch.zeros((T, N), dtype=torch.long, device=device)
    logp_b = torch.zeros((T, N), device=device)
    rew_b = torch.zeros((T, N), device=device)
    done_b = torch.zeros((T, N), device=device)
    val_b = torch.zeros((T, N), device=device)
    msk_b = torch.zeros((T, N, SPEC.n_actions), dtype=torch.bool, device=device)

    o0, m0 = envs.reset()
    next_obs = torch.as_tensor(o0, device=device)
    next_mask = torch.as_tensor(m0, device=device)
    next_done = torch.zeros(N, device=device)
    state = agent.initial_state(N, device)
    shaper = ProgressShaper(N) if cfg.progress_coef else None
    if shaper is not None:
        shaper.reset(o0)

    n_iters = cfg.total_steps // cfg.batch
    ep_returns, ep_ach, ep_lengths, ep_deaths, ep_masks = [], [], [], [], []
    step_count, start_time = 0, time.perf_counter()

    if not cfg.quiet:
        print(f"recurrent PPO: {N} envs x {T} steps, {n_iters} iterations")

    for it in range(1, n_iters + 1):
        lr_frac = 1.0 - (it - 1.0) / n_iters
        for group in opt.param_groups:
            group["lr"] = cfg.lr * lr_frac
        progress_coef = cfg.progress_coef * (lr_frac if cfg.progress_anneal else 1.0)
        initial_state = (state[0].detach().clone(), state[1].detach().clone())

        for t in range(T):
            obs_b[t], done_b[t], msk_b[t] = next_obs, next_done, next_mask
            with torch.no_grad():
                a, logp, _, value, state = agent.act_step(
                    next_obs, state, next_done, mask=next_mask)
            act_b[t], logp_b[t], val_b[t] = a, logp, value
            obs, mask, reward, term, trunc, final, finished = envs.step(a.cpu().numpy())
            if shaper is not None:
                reward = reward + progress_coef * shaper.step(
                    obs, final, term, trunc)
            rew_b[t] = torch.as_tensor(reward, device=device)
            _bootstrap_truncation(cfg, agent, rew_b, term, trunc, final,
                                  state, t, device)
            next_obs = torch.as_tensor(obs, device=device)
            next_mask = torch.as_tensor(mask, device=device)
            boundary = np.logical_or(term, trunc)
            next_done = torch.as_tensor(boundary.astype(np.float32), device=device)
            step_count += N
            for _, info in finished:
                ep_returns.append(info["episode_return"])
                ep_ach.append(info["achievements"])
                ep_lengths.append(info["steps"])
                ep_deaths.append(info["health"] <= 0)
                ep_masks.append(info["achievement_mask"])

        with torch.no_grad():
            next_value, _ = agent.value_step(next_obs, state, next_done)
            adv = compute_gae(rew_b, done_b, val_b, next_value, next_done,
                              cfg.gamma, cfg.gae_lambda)
            ret = adv + val_b

        env_idx = np.arange(N)
        approx_kl = torch.tensor(0.0)
        for _ in range(cfg.epochs):
            np.random.shuffle(env_idx)
            for start in range(0, N, N // cfg.minibatches):
                lanes = env_idx[start:start + N // cfg.minibatches]
                lane_t = torch.as_tensor(lanes, device=device)
                mb_state = (initial_state[0][:, lane_t].contiguous(),
                            initial_state[1][:, lane_t].contiguous())
                core, _ = agent.sequence(obs_b[:, lane_t], mb_state,
                                         done_b[:, lane_t])
                logits = agent.actor(core).masked_fill(
                    ~msk_b[:, lane_t], float("-inf"))
                dist = Categorical(logits=logits)
                newlogp = dist.log_prob(act_b[:, lane_t])
                entropy = dist.entropy()
                newval = agent.critic(core).squeeze(-1)
                logratio = newlogp - logp_b[:, lane_t]
                ratio = logratio.exp()
                with torch.no_grad():
                    approx_kl = ((ratio - 1.0) - logratio).mean()
                mb_adv = adv[:, lane_t]
                mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)
                pg = torch.max(-mb_adv * ratio,
                               -mb_adv * torch.clamp(ratio, 1 - cfg.clip_coef,
                                                     1 + cfg.clip_coef)).mean()
                oldval = val_b[:, lane_t]
                target = ret[:, lane_t]
                v_unclipped = (newval - target) ** 2
                v_clipped = (oldval + torch.clamp(newval - oldval,
                                                   -cfg.clip_coef, cfg.clip_coef)
                             - target) ** 2
                v_loss = 0.5 * torch.max(v_unclipped, v_clipped).mean()
                loss = pg - cfg.ent_coef * entropy.mean() + cfg.vf_coef * v_loss
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), cfg.max_grad_norm)
                opt.step()
            if cfg.target_kl is not None and approx_kl > cfg.target_kl:
                break

        if not cfg.quiet and (it == 1 or it % 10 == 0):
            tail = slice(-50, None)
            sps = step_count / (time.perf_counter() - start_time)
            print(f"{it:4d} {step_count:9,d} ach "
                  f"{np.mean(ep_ach[tail]) if ep_ach else 0:5.2f} "
                  f"death {100*np.mean(ep_deaths[tail]) if ep_deaths else 0:5.1f}% "
                  f"kl {approx_kl.item():.4f} {sps:,.0f} sps")

    envs.close()
    sps = step_count / (time.perf_counter() - start_time)
    tail = ep_masks[-200:]
    summary = {
        "agent": "recurrent_ppo", "seed": cfg.seed, "steps": cfg.total_steps,
        "progress_coef": cfg.progress_coef,
        "progress_anneal": cfg.progress_anneal, "sps": round(sps),
        "n_ep": len(ep_ach),
        "ach": float(np.mean(ep_ach[-50:])) if ep_ach else 0.0,
        "ret": float(np.mean(ep_returns[-50:])) if ep_returns else 0.0,
        "died": float(np.mean(ep_deaths[-50:])) if ep_deaths else 0.0,
        "hits": {SPEC.achievement_names[i]: sum((bits >> i) & 1 for bits in tail)
                 for i in range(SPEC.n_achievements)
                 if any((bits >> i) & 1 for bits in tail)},
    }
    if cfg.save:
        torch.save({"model": agent.state_dict(), "architecture": "lstm",
                    "encoder": cfg.encoder, "hidden": cfg.hidden}, cfg.save)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--steps", type=int, default=Config.total_steps)
    p.add_argument("--envs", type=int, default=Config.num_envs)
    p.add_argument("--rollout", type=int, default=Config.rollout)
    p.add_argument("--lr", type=float, default=Config.lr)
    p.add_argument("--ent-coef", type=float, default=Config.ent_coef)
    p.add_argument("--progress-coef", type=float, default=Config.progress_coef)
    p.add_argument("--progress-anneal", action="store_true")
    p.add_argument("--seed", type=int, default=Config.seed)
    p.add_argument("--device", default=Config.device)
    p.add_argument("--save", default=Config.save)
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    result = train(Config(total_steps=a.steps, num_envs=a.envs,
                          rollout=a.rollout, lr=a.lr, ent_coef=a.ent_coef,
                          progress_coef=a.progress_coef,
                          progress_anneal=a.progress_anneal, seed=a.seed,
                          device=a.device, save=a.save, quiet=a.quiet))
    if a.json or a.quiet:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
