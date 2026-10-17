"""PPO with native vector rollouts and explicit episode-boundary handling.

Default training uses a general MLP, legal masks and achievement rewards.
Spatial CNN and shared-cell encoders are experiment options. Optional Random
Network Distillation supplies learned novelty during training; it is disabled
by default and never changes evaluation rewards or physical action legality.

    uv run python -m terraria_lite.ppo_agent --steps 4194304 --envs 64

Rollouts preserve true final observations. Death and the benchmark's finite
action deadline cut GAE with zero future value. External truncation bootstrap
is an explicit option, not the default for this finite-horizon benchmark.
Policy updates reuse the masks that defined their original sampling support.
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
    total_steps: int = 4_194_304
    num_envs: int = 64
    rollout: int = 128          # steps per env per iteration -> default batch 8192
    epochs: int = 4
    minibatches: int = 4
    lr: float = 3e-4
    anneal_lr: bool = True
    # Episodes run to 3000 steps and the payoffs are sparse and one-shot, so
    # the usual 0.99 (69-step half-life) discounts the entire tech tree to
    # noise. Historical v1 evidence over 3 seeds at 600k: 0.99 -> 3.86 and
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
    device: str = "cpu"              # benchmark device/batch together; CNN can benefit from MPS
    quiet: bool = False              # suppress per-iteration lines when sweeping
    save: str = "ppo_terraria.pt"    # "" to skip, so parallel sweeps don't collide
    init: str = ""                    # optional actor/critic state_dict warm start
    architecture: str = "mlp"         # general spatial CNN is an optional control
    curiosity_coef: float = 0.0       # generic learned novelty; extrinsic eval unchanged
    curiosity_anneal: bool = True
    curiosity_balanced: bool = False
    bootstrap_time_limit: bool = False  # legacy/control only for the inherent deadline

    @property
    def batch(self) -> int:
        return self.num_envs * self.rollout

    @property
    def minibatch(self) -> int:
        return self.batch // self.minibatches


# ----------------------------------------------------------------- model ---

def sample_categorical(dist, mask=None):
    """Same distribution, with CPU sampling for the known MPS multinomial bug."""
    if dist.logits.device.type == "mps":
        probs=dist.probs.detach().cpu()
        action=torch.multinomial(probs,1).squeeze(-1)
        if mask is not None and not bool(mask.detach().cpu().gather(-1,action[:,None]).all()):
            raise RuntimeError("categorical sampler selected an illegal action")
        return action.to(dist.logits.device)
    return dist.sample()

def layer_init(layer: nn.Linear, std: float = np.sqrt(2), bias: float = 0.0):
    """Orthogonal init. The head gains matter: 0.01 on the policy keeps the
    initial distribution near-uniform (so early exploration is real), 1.0 on
    the value head keeps early value estimates small."""
    nn.init.orthogonal_(layer.weight, std)
    nn.init.constant_(layer.bias, bias)
    return layer


class ActorCritic(nn.Module):
    """Parameter-efficient baseline: shared features, separate policy/value heads.

    Sharing is a design choice, not an assumption that the two objectives always
    want identical features. SeparateActorCritic tests that alternative.
    """

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
            action = sample_categorical(dist,mask)
        return action, dist.log_prob(action), dist.entropy(), self.critic(h).squeeze(-1)


# ------------------------------------------------------------ vectorised ---

class VecTerraria:
    """Synchronous vector of environments with explicit autoreset.

    Rolled by hand rather than using gymnasium's vector API for one reason:
        when an episode ends we retain its true final observation rather than
        confuse it with the autoreset observation. External truncation controls
        can bootstrap it; the benchmark's inherent action deadline does not.
    """

    def __init__(self, n: int, seed: int = 1):
        self.envs = [TerrariaLite() for _ in range(n)]
        self.n = n
        self._next_seed = seed
        self.obs = np.zeros((n, SPEC.obs_size), dtype=np.float32)
        self.mask = np.zeros((n, SPEC.n_actions), dtype=bool)
        from terraria_lite.batch import NativeBatch
        self.native = NativeBatch(self.envs)

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
        those lanes, for diagnostics or an explicit external-truncation control.
        """
        rew, term, trunc = self.native.step(actions, self.obs, self.mask)
        final = np.zeros((self.n, SPEC.obs_size), dtype=np.float32)
        finished = []

        for i in np.flatnonzero(term | trunc):
            e = self.envs[i]
            final[i] = self.obs[i]
            finished.append((int(i), e._info()))
            self.obs[i] = e.reset(seed=self._fresh_seed())[0]
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
    """Bootstrap external truncations only, never the finite benchmark deadline.

    Autoreset means the observation after a boundary belongs to a fresh world.
    Both termination and truncation must therefore cut GAE recurrence; otherwise
    an advantage leaks into the next episode. Our C API labels the action budget
    as truncated, but it is an inherent finite-horizon endpoint: there is no
    reward after it. Keep the old bootstrap behind an explicit control flag so
    the mismatch can be measured without changing game mechanics or old runs.
    """
    if not cfg.bootstrap_time_limit:
        return
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
    if SPEC.version >= 2 and cfg.progress_coef:
        raise ValueError("v2 uses achievement rewards only; v1 shaping is incompatible")
    if cfg.num_envs < 1 or cfg.rollout < 1 or cfg.total_steps < cfg.batch:
        raise ValueError("training requires positive dimensions and at least one batch")
    if cfg.minibatches < 1 or cfg.batch % cfg.minibatches:
        raise ValueError("rollout batch must be divisible by positive minibatches")
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    device = torch.device(cfg.device)

    envs = VecTerraria(cfg.num_envs, seed=cfg.seed*10_000_000 if SPEC.version>=2 else cfg.seed)
    from terraria_lite.spatial_agent import build_agent
    agent = build_agent(cfg.architecture).to(device)
    if cfg.init:
        raw = torch.load(cfg.init, map_location=device, weights_only=True)
        from terraria_lite.checkpoints import validate_checkpoint
        validate_checkpoint(raw)
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
    from terraria_lite.curiosity import RND
    curiosity=RND(SPEC.obs_size,device,balanced=cfg.curiosity_balanced) if cfg.curiosity_coef else None
    novelty_b=torch.empty_like(obs_b) if curiosity is not None else None

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
            if novelty_b is not None:
                novelty_b[t]=torch.as_tensor(obs,device=device)
                ended=np.flatnonzero(term|trunc)
                if len(ended): novelty_b[t,torch.as_tensor(ended,device=device)]=torch.as_tensor(final[ended],device=device)
            if shaper is not None:
                r = r + progress_coef * shaper.step(obs, final, term, trunc)
            rew_b[t] = torch.as_tensor(r, device=device)
            _absorb_truncation(cfg, agent, rew_b, term, trunc, final, t, device)

            next_obs = torch.as_tensor(obs, device=device)
            next_mask = torch.as_tensor(msk, device=device)
            # Autoreset makes both kinds episode boundaries. An explicitly
            # enabled external bootstrap was folded into rew_b above; using
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
        novelty_error=0.0
        if curiosity is not None:
            bonus,novelty_error=curiosity.bonus_and_update(novelty_b.reshape(-1,SPEC.obs_size))
            scale=cfg.curiosity_coef
            if cfg.curiosity_anneal:
                scale*=max(0.,1.-2.*(it-1)/n_iters)
            rew_b+=scale*bonus.reshape(T,N)
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
                "novelty_error": novelty_error,
                "policy_entropy": float(entropy.detach().mean()),
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
        "architecture": cfg.architecture,"curiosity_coef": cfg.curiosity_coef,
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
        print("Compare with a fresh uniform-legal control on the same validation worlds.\n")

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
        torch.save({"model": agent.state_dict(), "architecture": cfg.architecture,
                    "environment_version": SPEC.version,
                    "obs_size": SPEC.obs_size, "n_actions": SPEC.n_actions}, cfg.save)
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
            "steps. There is no positional argument -- use --steps."
        ),
        epilog=(
            "examples:\n"
            "  --steps 100000\n"
            "      short unshaped smoke run\n"
            "  --steps 4194304 --envs 64 --seed 101\n"
            "      sparse-reward baseline\n"
            "See ITERATION_2026_10.md for current evidence.\n"
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
    p.add_argument("--gae-lambda",type=float,default=Config.gae_lambda)
    p.add_argument("--bootstrap-time-limit",action="store_true",
                   help="legacy/external-truncation control; incompatible with the finite benchmark objective")
    p.add_argument("--architecture",choices=["mlp","cnn","tokens","separate","targets"],default=Config.architecture)
    p.add_argument("--curiosity-coef",type=float,default=0.,help="optional learned novelty; experimental")
    p.add_argument("--balanced-curiosity",action="store_true")
    p.add_argument("--threads",type=int,default=6)
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
    torch.set_num_threads(a.threads)
    s = train(Config(total_steps=a.steps, num_envs=a.envs, rollout=a.rollout,
                     lr=a.lr, gamma=a.gamma, ent_coef=a.ent_coef, seed=a.seed,
                     progress_coef=a.progress_coef,
                     progress_anneal=a.progress_anneal, device=a.device,
                     save=a.save, init=a.init, quiet=a.quiet,architecture=a.architecture,
                     gae_lambda=a.gae_lambda,bootstrap_time_limit=a.bootstrap_time_limit,curiosity_coef=a.curiosity_coef,
                     curiosity_balanced=a.balanced_curiosity))
    if a.json:
        print(json.dumps(s))
