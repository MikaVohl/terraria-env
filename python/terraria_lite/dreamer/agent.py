"""DreamerV3-style agent for terraria-lite: world-model learning on replayed
real sequences, actor-critic learning in imagination, and the collection loop.

See DREAMER_2026_10.md for the design and its justification.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import time

import numpy as np
import torch
import torch.nn.functional as F

from terraria_lite import SPEC
from terraria_lite.compact import Expander
from terraria_lite.dreamer.nets import (ActorCritic, WorldModel, kl_categorical, onehot_action,
                                        sample_logp)
from terraria_lite.dreamer.replay import Replay


@dataclass
class Config:
    total_steps: int = 1_000_000      # env steps
    seed: int = 1
    envs: int = 256
    sim_workers: int = 4
    device: str = "cpu"
    # replay / batches
    capacity: int = 2_000_000         # rows (device-resident)
    batch: int = 64                   # sequences per update
    seq_len: int = 64
    train_ratio: float = 32.0         # replayed steps per env step
    prefill: int = 64                 # env steps per lane before the first update
    # world model
    deter: int = 1024
    stoch: int = 32
    classes: int = 32
    units: int = 640
    layers: int = 3
    unimix: float = 0.01
    free_bits: float = 1.0
    dyn_scale: float = 0.5
    rep_scale: float = 0.1
    model_lr: float = 1e-4
    model_eps: float = 1e-8
    model_clip: float = 1000.0
    # actor-critic
    horizon: int = 15
    gamma: float = 0.997
    lam: float = 0.95
    entropy: float = 3e-4
    actor_lr: float = 3e-5
    critic_lr: float = 3e-5
    ac_eps: float = 1e-5
    ac_clip: float = 100.0
    slow_rate: float = 0.02
    slow_reg: float = 1.0
    retnorm_decay: float = 0.99
    # training-only reward (disclosed; evaluation is extrinsic)
    potential: float = 0.0
    potential_mode: str = "mean"
    novelty: float = 0.0
    # performance
    bf16: bool = False
    compile: bool = False
    compile_observe: bool = False     # compile the whole unrolled T-step filter instead of one step


class Dreamer:
    def __init__(self, cfg: Config, device=None):
        self.cfg = cfg
        self.device = torch.device(device or cfg.device)
        shaping = bool(cfg.potential or cfg.novelty)
        self.wm = WorldModel(cfg.deter, cfg.stoch, cfg.classes, cfg.units, cfg.layers, cfg.unimix,
                             shaping=shaping).to(self.device)
        self.ac = ActorCritic(self.wm.feat_size, cfg.units, cfg.layers, unimix=cfg.unimix).to(self.device)
        self.expand = Expander(self.device)
        self.wm_opt = torch.optim.Adam(self.wm.parameters(), lr=cfg.model_lr, eps=cfg.model_eps)
        self.actor_opt = torch.optim.Adam(self.ac.actor.parameters(), lr=cfg.actor_lr, eps=cfg.ac_eps)
        self.critic_opt = torch.optim.Adam(self.ac.critic.parameters(), lr=cfg.critic_lr, eps=cfg.ac_eps)
        self.retnorm = torch.zeros((), device=self.device)   # EMA of the 5-95 percentile range
        self.updates = 0
        self._obs_step = self._img_step = None
        self._observe = None
        if cfg.compile:
            self._obs_step = torch.compile(self.obs_step)
            self._img_step = torch.compile(self.img_step)
            if cfg.compile_observe:
                self._observe, self._obs_step = torch.compile(self.observe), None

    # ------------------------------------------------------------ helpers ---
    def autocast(self):
        return torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cfg.bf16)

    def obs_step(self, h, z, a1h, keep, embed):
        rssm = self.wm.rssm
        h = rssm.gru_step(h * keep, z * keep, a1h)
        prior = rssm.prior(h)
        post = rssm.posterior(h, embed)
        return h, rssm.sample(post), post, prior

    def img_step(self, h, z, mask):
        """One imagined step: act on [h, z] under `mask`, then predict."""
        rssm = self.wm.rssm
        feat = torch.cat((h, z), -1)
        a = sample_logp(self.ac.policy(feat, mask))
        h = rssm.gru_step(h, z, onehot_action(a))
        z = rssm.sample(rssm.prior(h))
        nfeat = torch.cat((h, z), -1)
        return a, h, z, self.wm.predicted_mask(nfeat)

    def observe(self, embed, prev_action, first):
        T, B = first.shape
        step = self._obs_step or self.obs_step
        h, z = self.wm.rssm.initial(B, embed.device)
        a1h = onehot_action(prev_action)
        keep = (~first).float()[..., None]
        out = []
        for t in range(T):
            h, z, post, prior = step(h, z, a1h[t], keep[t], embed[t])
            out.append((h, z, post, prior))
        return tuple(torch.stack(x) for x in zip(*out))

    @torch.no_grad()
    def imagine(self, h, z, mask0, horizon: int):
        """Roll the actor out in the world model from (h, z) for `horizon`
        steps. Step 0 acts under mask0 (real); later steps under the predicted
        mask. Returns feats (H+1, N, F), masks (H+1, N, A), actions (H, N)."""
        step = self._img_step or self.img_step
        feats, masks, acts = [torch.cat((h, z), -1)], [mask0], []
        mk = mask0
        for _ in range(horizon):
            a, h, z, mk = step(h, z, mk)
            feats.append(torch.cat((h, z), -1)); masks.append(mk); acts.append(a)
        return torch.stack(feats), torch.stack(masks), torch.stack(acts)

    # ------------------------------------------------------------- acting ---
    def initial_state(self, n: int):
        h, z = self.wm.rssm.initial(n, self.device)
        return h, z, torch.full((n,), -1, dtype=torch.long, device=self.device)

    @torch.no_grad()
    def policy_logp(self, x, mask, state, first):
        """Filter one real step and return the masked policy's log-probs.
        x: flat float32 obs (n, obs_size); mask: bool (n, A); first: bool (n,)
        marks lanes whose episode starts at x. Returns (logp, (h, z))."""
        h, z, a = state
        with self.autocast():
            a = torch.where(first, torch.full_like(a, -1), a)
            h, z, _, _ = self.obs_step(h, z, onehot_action(a), (~first).float()[:, None], self.wm.encode(x))
            logp = self.ac.policy(torch.cat((h, z), -1), mask)
        return logp, (h, z.detach())

    @torch.no_grad()
    def act(self, x, mask, state, first, greedy: bool = False):
        """Sample actions; the returned state carries them as previous actions."""
        logp, (h, z) = self.policy_logp(x, mask, state, first)
        action = logp.argmax(-1) if greedy else sample_logp(logp)
        return action, (h, z, action)

    # ------------------------------------------------------------ learning ---
    def update(self, batch: dict) -> dict:
        cfg, wm, ac = self.cfg, self.wm, self.ac
        raw = batch["obs"]
        T, B = raw.shape[:2]
        cont = batch["cont"].float()
        # ---- world model ----
        with self.autocast():
            x = self.expand(raw.reshape(T * B, -1)).reshape(T, B, -1)
            embed = wm.encode(x)
            h, z, post, prior = (self._observe or self.observe)(embed, batch["act"], batch["first"])
            feat = torch.cat((h, z), -1)
            tile, light, status = wm.decode_loss(feat, raw)
            mask_logits = wm.mask_logits(feat)
            rew_logits = wm.reward_head(feat)
            cont_logits = wm.cont_head(feat).float()[..., 0]
            shape_logits = wm.shape_head(feat) if wm.shape_head is not None else None
        real_mask = batch["mask"]
        mask_loss = F.binary_cross_entropy_with_logits(mask_logits, real_mask.float(), reduction="none").sum(-1) * cont
        rew_loss = wm.twohot.nll(rew_logits, batch["rew"])
        shape_loss = wm.twohot.nll(shape_logits, batch["shape"]) if shape_logits is not None else torch.zeros_like(rew_loss)
        cont_loss = F.binary_cross_entropy_with_logits(cont_logits, cont, reduction="none")
        dyn = kl_categorical(post.detach(), prior)
        rep = kl_categorical(post, prior.detach())
        kl_loss = cfg.dyn_scale * dyn.clamp(min=cfg.free_bits) + cfg.rep_scale * rep.clamp(min=cfg.free_bits)
        model_loss = (tile + light + status + mask_loss + rew_loss + shape_loss + cont_loss + kl_loss).mean()
        self.wm_opt.zero_grad(set_to_none=True)
        model_loss.backward()
        model_norm = torch.nn.utils.clip_grad_norm_(wm.parameters(), cfg.model_clip)
        self.wm_opt.step()
        with torch.no_grad():
            pred = mask_logits > 0
            valid = batch["cont"][..., None]
            false_legal = (pred & ~real_mask & valid).sum() / (pred & valid).sum().clamp(min=1)
            false_illegal = (~pred & real_mask & valid).sum() / (real_mask & valid).sum().clamp(min=1)

        # ---- imagination (no gradient: REINFORCE for discrete actions) ----
        N = T * B
        H = cfg.horizon
        with torch.no_grad(), self.autocast():
            # Start mask: the exact mask stored with each replayed state.
            feats, masks, acts = self.imagine(h.detach().reshape(N, -1), z.detach().reshape(N, -1),
                                              real_mask.reshape(N, -1), H)
            r_ext = wm.reward(feats[1:])
            r_shape = wm.shaping(feats[1:]) if wm.shape_head is not None else torch.zeros_like(r_ext)
            c = wm.cont(feats[1:])
            value = ac.twohot.mean(ac.slow_critic(feats))
            disc = cfg.gamma * c
            rets = [value[-1]]
            for k in reversed(range(H)):
                rets.append(r_ext[k] + r_shape[k] + disc[k] * ((1 - cfg.lam) * value[k + 1] + cfg.lam * rets[-1]))
            ret = torch.stack(rets[::-1][:-1])               # (H, N)
            weight = torch.cumprod(torch.cat((cont.reshape(1, N), c[:-1])), 0)
            ordered = ret.flatten().sort().values          # sort-based percentiles: no host sync
            n = ordered.numel() - 1
            lo, hi = ordered[round(.05 * n)], ordered[round(.95 * n)]
            if self.updates:
                self.retnorm.lerp_(hi - lo, 1 - cfg.retnorm_decay)
            else:
                self.retnorm.copy_(hi - lo)
            adv = (ret - value[:-1]) / self.retnorm.clamp(min=1.0)

        # ---- actor ----
        with self.autocast():
            logp = ac.policy(feats[:-1], masks[:-1])
        logp_a = logp.gather(-1, acts[..., None])[..., 0]
        entropy = -(logp.exp() * logp.masked_fill(~masks[:-1], 0.0)).sum(-1)
        actor_loss = -(weight * (logp_a * adv + cfg.entropy * entropy)).mean()
        self.actor_opt.zero_grad(set_to_none=True)
        actor_loss.backward()
        actor_norm = torch.nn.utils.clip_grad_norm_(ac.actor.parameters(), cfg.ac_clip)
        self.actor_opt.step()
        # ---- critic ----
        with self.autocast():
            v_logits = ac.critic(feats[:-1])
        critic_loss = (weight * (ac.twohot.nll(v_logits, ret) + cfg.slow_reg * ac.twohot.nll(v_logits, value[:-1]))).mean()
        self.critic_opt.zero_grad(set_to_none=True)
        critic_loss.backward()
        critic_norm = torch.nn.utils.clip_grad_norm_(ac.critic.parameters(), cfg.ac_clip)
        self.critic_opt.step()
        ac.update_slow(cfg.slow_rate)
        self.updates += 1
        # Tensors only (no host sync); converted when logged.
        return {"model_loss": model_loss.detach(), "tile_loss": tile.mean().detach(), "light_loss": light.mean().detach(),
                "status_loss": status.mean().detach(), "mask_loss": mask_loss.mean().detach(),
                "reward_loss": rew_loss.mean().detach(), "shape_loss": shape_loss.mean().detach(),
                "cont_loss": cont_loss.mean().detach(), "dyn_kl": dyn.mean().detach(), "rep_kl": rep.mean().detach(),
                "mask_false_legal": false_legal, "mask_false_illegal": false_illegal,
                "model_grad_norm": model_norm, "actor_loss": actor_loss.detach(), "critic_loss": critic_loss.detach(),
                "actor_grad_norm": actor_norm, "critic_grad_norm": critic_norm,
                "policy_entropy": (weight * entropy).sum().detach() / weight.sum(),
                "imag_reward_ext": r_ext.mean(), "imag_reward_shape": r_shape.mean(),
                "imag_return": ret.mean(), "imag_value": value.mean(), "imag_cont": c.mean(),
                "retnorm": self.retnorm.clone(), "replay_reward": batch["rew"].mean(),
                "replay_reward_pred": wm.twohot.mean(rew_logits.detach()).mean()}

    # -------------------------------------------------------- checkpoints ---
    def state_dict(self) -> dict:
        return {"architecture": "dreamer", "config": asdict(self.cfg), "world_model": self.wm.state_dict(),
                "actor_critic": self.ac.state_dict(), "retnorm": float(self.retnorm), "updates": self.updates,
                "environment_version": SPEC.version, "obs_size": SPEC.obs_size, "n_actions": SPEC.n_actions}

    def save(self, path, optimizers: bool = False) -> None:
        data = self.state_dict()
        if optimizers:
            data["optimizers"] = {"wm": self.wm_opt.state_dict(), "actor": self.actor_opt.state_dict(),
                                  "critic": self.critic_opt.state_dict()}
        torch.save(data, path)


def load_dreamer(path, device="cpu", training: bool = False) -> Dreamer:
    raw = torch.load(path, map_location=device, weights_only=True)
    if raw.get("architecture") != "dreamer":
        raise ValueError(f"{path} is not a Dreamer checkpoint")
    if raw["environment_version"] != SPEC.version or raw["obs_size"] != SPEC.obs_size or raw["n_actions"] != SPEC.n_actions:
        raise ValueError("checkpoint was trained on a different environment version/interface")
    cfg = Config(**{**raw["config"], "compile": False, "compile_observe": False, "device": str(device)})
    agent = Dreamer(cfg, device)
    agent.wm.load_state_dict(raw["world_model"])
    agent.ac.load_state_dict(raw["actor_critic"])
    agent.retnorm.fill_(raw["retnorm"])
    agent.updates = raw["updates"]
    if training and "optimizers" in raw:
        agent.wm_opt.load_state_dict(raw["optimizers"]["wm"])
        agent.actor_opt.load_state_dict(raw["optimizers"]["actor"])
        agent.critic_opt.load_state_dict(raw["optimizers"]["critic"])
    agent.wm.eval(); agent.ac.eval()
    return agent


# ------------------------------------------------------------------ train ---
def train(cfg: Config, callback=None, log_every: float = 60.0, log=print) -> dict:
    """Collect with the current actor and update so replayed/env steps ==
    train_ratio. callback(agent, env_steps, profile) runs after every update
    round; it decides itself when to checkpoint/evaluate."""
    from terraria_lite.ppo_agent import VecTerraria
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    device = torch.device(cfg.device)
    agent = Dreamer(cfg, device)
    N = cfg.envs
    envs = VecTerraria(N, seed=cfg.seed * 10_000_000, workers=cfg.sim_workers, native_autoreset=True, compact=True)
    replay = Replay(N, cfg.capacity, device, seed=cfg.seed)
    if replay.length < cfg.seq_len + 2:
        raise ValueError("replay capacity per lane must exceed the sequence length")
    obs, mask = envs.reset()
    potential = novelty = None
    if cfg.potential:
        from terraria_lite.potential import RecipePotential
        potential = RecipePotential(obs, cfg.gamma, cfg.potential, cfg.potential_mode)
    if cfg.novelty:
        from terraria_lite.count_novelty import CellNovelty
        novelty = CellNovelty(obs)
    all_lanes = torch.arange(N, device=device)
    zeros = torch.zeros(N, device=device)
    obs_t = torch.as_tensor(obs, device=device)
    mask_t = torch.as_tensor(mask, device=device)
    replay.add(all_lanes, obs_t, mask_t, torch.full((N,), -1, device=device), zeros, zeros,
               torch.ones(N, dtype=torch.bool, device=device), torch.ones(N, dtype=torch.bool, device=device))
    state = agent.initial_state(N)
    first = torch.ones(N, dtype=torch.bool, device=device)
    per_update = cfg.batch * cfg.seq_len
    credit = 0.0
    env_steps = 0
    episodes: deque = deque(maxlen=512)
    n_episodes = 0
    collect_s = train_s = 0.0
    metrics_sum: dict = {}
    n_metrics = 0
    start = last_log = time.perf_counter()
    profile: dict = {}
    while env_steps < cfg.total_steps:
        t0 = time.perf_counter()
        x = agent.expand(obs_t)
        action, state = agent.act(x, mask_t, state, first)
        a_np = action.cpu().numpy()
        t1 = time.perf_counter()
        # Updates are queued on the device; the C step runs on the CPU meanwhile.
        if env_steps >= cfg.prefill * N and replay.ready(cfg.seq_len):
            while credit >= 1.0:
                credit -= 1.0
                m = agent.update(replay.sample(cfg.batch, cfg.seq_len))
                for k, v in m.items():
                    metrics_sum[k] = metrics_sum.get(k, 0) + v
                n_metrics += 1
        t2 = time.perf_counter()
        obs, mask, rew, term, trunc, final, finished = envs.step(a_np)
        ended = term | trunc
        shape = np.zeros(N, np.float32)
        if potential is not None:
            shape += potential.step(obs, final, ended)
        if novelty is not None:
            shape += cfg.novelty * novelty.step(obs, final, ended)
        lanes_end = np.flatnonzero(ended)
        row = obs
        row_mask = mask
        if len(lanes_end):
            row = obs.copy(); row[lanes_end] = final[lanes_end]
            row_mask = mask.copy(); row_mask[lanes_end] = True    # terminal rows: placeholder, not trained
        replay.add(all_lanes, torch.as_tensor(row, device=device), torch.as_tensor(row_mask, device=device),
                   action, torch.as_tensor(rew, device=device), torch.as_tensor(shape, device=device),
                   torch.zeros(N, dtype=torch.bool, device=device), torch.as_tensor(~ended, device=device))
        obs_t = torch.as_tensor(obs, device=device)
        mask_t = torch.as_tensor(mask, device=device)
        first = torch.as_tensor(ended, device=device)
        if len(lanes_end):
            li = torch.as_tensor(lanes_end, device=device)
            k = len(lanes_end)
            zk = torch.zeros(k, device=device)
            replay.add(li, obs_t[li], mask_t[li], torch.full((k,), -1, device=device), zk, zk,
                       torch.ones(k, dtype=torch.bool, device=device), torch.ones(k, dtype=torch.bool, device=device))
        for _, info in finished:
            n_episodes += 1
            episodes.append((info["achievements"], info["episode_return"], info["health"] <= 0))
        env_steps += N
        if env_steps > cfg.prefill * N:
            credit += N * cfg.train_ratio / per_update
        t3 = time.perf_counter()
        collect_s += (t1 - t0) + (t3 - t2)
        train_s += t2 - t1
        now = time.perf_counter()
        if now - last_log >= log_every or env_steps >= cfg.total_steps:
            last_log = now
            ms = {k: float(v) / max(1, n_metrics) for k, v in metrics_sum.items()}
            metrics_sum, n_metrics = {}, 0
            ach = np.mean([e[0] for e in episodes]) if episodes else float("nan")
            profile = {"env_steps": env_steps, "updates": agent.updates, "elapsed": now - start,
                       "env_sps": env_steps / (now - start), "replayed_sps": agent.updates * per_update / (now - start),
                       "collect_seconds": collect_s, "train_seconds": train_s, "episodes": n_episodes,
                       "train_ach_recent": float(ach),
                       "train_death_recent": float(np.mean([e[2] for e in episodes])) if episodes else float("nan"),
                       "replay_rows": replay.rows, **ms}
            log(f"steps {env_steps:,} upd {agent.updates} ach {ach:.2f} eps {n_episodes} "
                f"sps {profile['env_sps']:,.0f} rsps {profile['replayed_sps']:,.0f} "
                f"model {ms.get('model_loss', float('nan')):.2f} kl {ms.get('dyn_kl', float('nan')):.2f} "
                f"ret {ms.get('imag_return', float('nan')):.3f} ext {ms.get('imag_reward_ext', float('nan')):.4f} "
                f"shp {ms.get('imag_reward_shape', float('nan')):.4f} ent {ms.get('policy_entropy', float('nan')):.2f} "
                f"fl {ms.get('mask_false_legal', float('nan')):.4f} fi {ms.get('mask_false_illegal', float('nan')):.4f}")
        if callback is not None:
            callback(agent, env_steps, profile)
    envs.close()
    return {"env_steps": env_steps, "updates": agent.updates, "episodes": n_episodes,
            "wall_seconds": time.perf_counter() - start, "collect_seconds": collect_s, "train_seconds": train_s,
            "final_profile": profile, "config": asdict(cfg)}
