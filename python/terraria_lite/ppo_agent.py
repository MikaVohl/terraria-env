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

Known next lever, deliberately not taken: the environment is partially
observable by design -- roughly 80% of the underground view reads as unlit --
so an LSTM over the trunk is where the next real gain is. The rollout buffer is
laid out (T, N, ...) so adding recurrence does not mean rewriting this.
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
    seed: int = 1
    device: str = "cpu"              # a 1.5M MLP at batch 2048 loses to MPS overhead
    quiet: bool = False              # suppress per-iteration lines when sweeping
    save: str = "ppo_terraria.pt"    # "" to skip, so parallel sweeps don't collide

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


# ------------------------------------------------------------------ train ---

def _absorb_truncation(cfg, agent, rewards, term, trunc, final_obs, t, device):
    """Fold the bootstrap for truncated episodes into the reward.

    GAE below masks the future with `1 - done`. If `done` included truncation,
    a cut-off episode would be treated as though the world genuinely ended and
    its tail value thrown away. Instead: truncated lanes keep `done = False`
    for the value target and have gamma * V(final_obs) added to their reward,
    which is exactly the missing bootstrap. Terminated lanes get nothing --
    death really is the end.
    """
    cut = np.logical_and(trunc, np.logical_not(term))
    if not cut.any():
        return
    with torch.no_grad():
        v = agent.value(torch.as_tensor(final_obs[cut], device=device))
    rewards[t, torch.as_tensor(cut, device=device)] += cfg.gamma * v


def train(cfg: Config):
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    device = torch.device(cfg.device)

    envs = VecTerraria(cfg.num_envs, seed=cfg.seed)
    agent = ActorCritic(SPEC.obs_size, SPEC.n_actions).to(device)
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
    next_obs = torch.as_tensor(o0, device=device)
    next_mask = torch.as_tensor(m0, device=device)
    next_done = torch.zeros(N, device=device)

    n_iters = cfg.total_steps // cfg.batch
    ep_returns, ep_achievements, ep_lengths, ep_deaths = [], [], [], []
    ep_masks: list[int] = []          # which achievements, not just how many
    start = time.perf_counter()
    step_count = 0

    print(f"{SPEC}")
    print(f"PPO: {N} envs x {T} steps = batch {cfg.batch}, "
          f"{n_iters} iterations, {cfg.total_steps:,} env steps\n")
    print(f"{'iter':>5} {'steps':>9} {'return':>8} {'ach':>6} {'len':>6} "
          f"{'death%':>7} {'entropy':>8} {'kl':>7} {'clip':>6} {'ev':>6} {'sps':>7}")

    for it in range(1, n_iters + 1):
        if cfg.anneal_lr:
            for g in opt.param_groups:
                g["lr"] = cfg.lr * (1.0 - (it - 1.0) / n_iters)

        # ---- collect ----------------------------------------------------
        for t in range(T):
            obs_b[t] = next_obs
            done_b[t] = next_done
            msk_b[t] = next_mask
            with torch.no_grad():
                a, logp, _, v = agent.act(next_obs, mask=next_mask)
            act_b[t], logp_b[t], val_b[t] = a, logp, v

            obs, msk, r, term, trunc, final, finished = envs.step(a.cpu().numpy())
            rew_b[t] = torch.as_tensor(r, device=device)
            _absorb_truncation(cfg, agent, rew_b, term, trunc, final, t, device)

            next_obs = torch.as_tensor(obs, device=device)
            next_mask = torch.as_tensor(msk, device=device)
            # Only true termination cuts the value bootstrap.
            next_done = torch.as_tensor(term.astype(np.float32), device=device)
            step_count += N

            for _, info in finished:
                ep_returns.append(info["episode_return"])
                ep_achievements.append(info["achievements"])
                ep_lengths.append(info["steps"])
                ep_deaths.append(1.0 if info["health"] <= 0 else 0.0)
                ep_masks.append(info["achievement_mask"])

        # ---- GAE ---------------------------------------------------------
        with torch.no_grad():
            next_value = agent.value(next_obs)
            adv = torch.zeros_like(rew_b)
            last = 0.0
            for t in reversed(range(T)):
                if t == T - 1:
                    nonterminal, next_val = 1.0 - next_done, next_value
                else:
                    nonterminal, next_val = 1.0 - done_b[t + 1], val_b[t + 1]
                delta = rew_b[t] + cfg.gamma * next_val * nonterminal - val_b[t]
                last = delta + cfg.gamma * cfg.gae_lambda * nonterminal * last
                adv[t] = last
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
        "lr": cfg.lr, "envs": cfg.num_envs, "steps": cfg.total_steps,
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
            "examples (3-seed means at the current defaults):\n"
            "  --steps 100000     ~7s   sanity check that it clears random\n"
            "  --steps 600000    ~40s   5.18 ach; workbench crafted in 22%\n"
            "  --steps 2000000    ~2m   5.28 ach; plateaus at 'craft furnace'\n"
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
    p.add_argument("--seed", type=int, default=Config.seed,
                   help="torch/numpy/env seed; sweep it before trusting a delta")
    p.add_argument("--device", type=str, default=Config.device,
                   help="cpu or mps; cpu usually wins for a net this small")
    p.add_argument("--save", type=str, default=Config.save,
                   help='checkpoint path, "" to skip')
    p.add_argument("--quiet", action="store_true",
                   help="only the final summary; for parallel sweeps")
    p.add_argument("--json", action="store_true",
                   help="emit the summary as one JSON line on stdout")
    a = p.parse_args()
    s = train(Config(total_steps=a.steps, num_envs=a.envs, rollout=a.rollout,
                     lr=a.lr, gamma=a.gamma, ent_coef=a.ent_coef, seed=a.seed,
                     device=a.device, save=a.save, quiet=a.quiet))
    if a.json:
        print(json.dumps(s))
