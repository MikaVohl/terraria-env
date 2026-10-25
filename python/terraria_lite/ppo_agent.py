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
import copy
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
    # Speed only; neither changes the losses or the sampling distribution.
    # collect_device: "" samples on `device`; e.g. "cpu" with device="mps"
    # samples batch-N rollouts on CPU with a synchronised policy copy and
    # learns on MPS (float rounding then differs from an all-CPU run).
    collect_device: str = ""
    # collect_threads: torch intra-op threads while sampling, 0 = unchanged.
    # Batch-N forwards are latency-bound; 1 is fastest for targets/cnn and
    # was bit-identical to the unchanged run at 4 and 6 threads (targets).
    collect_threads: int = 0
    # sim_workers: C threads stepping the environment batch. Results never
    # depend on it; pick it for throughput (more for large batches, 1 when
    # many runs share the CPU).
    sim_workers: int = 4
    quiet: bool = False              # suppress per-iteration lines when sweeping
    save: str = "ppo_terraria.pt"    # "" to skip, so parallel sweeps don't collide
    init: str = ""                    # optional actor/critic state_dict warm start
    architecture: str = "mlp"         # general spatial CNN is an optional control
    # Model size (feed-forward): hidden 0 = the architecture's default width;
    # depth = global trunk layers ('targets', 'mlp'); cell_width = per-cell
    # MLP width ('targets'). Defaults build the original networks exactly.
    hidden: int = 0
    depth: int = 2
    cell_width: int = 32
    curiosity_coef: float = 0.0       # generic learned novelty; extrinsic eval unchanged
    curiosity_anneal: bool = True
    curiosity_balanced: bool = False
    bootstrap_time_limit: bool = False  # legacy/control only for the inherent deadline
    achievement_reward: str = "equal"  # optional fixed sparse weighting; evaluation unchanged
    # Training-only exploration aids; all off by default, evaluation unchanged.
    archive_start_prob: float = 0.0   # Go-Explore start states (archive.py)
    archive_capacity: int = 4096
    sil_minibatches: int = 0          # self-imitation updates per iteration
    sil_value_coef: float = 0.01
    novelty_coef: float = 0.0         # count-based progress-cell novelty
    potential_coef: float = 0.0       # potential-based recipe shaping (prior knowledge)
    potential_mode: str = "mean"      # "frontier": average only over not-yet-earned recipes
    memory_features: str = ""         # "stations_v1": observed station memory inputs
    aux_coef: float = 0.0             # predictive inventory/unlock auxiliary loss
    # Performance options, all off by default (default training is unchanged).
    # Exact (identical rollouts and updates):
    native_autoreset: bool = False    # reset finished lanes in C, not a Python loop
    compact_obs: bool = False         # move/store raw uint8 obs rows, one-hot on the learner device
    sim_backend: str = "cpu"          # "gpu": simulate on the collect device (terraria_lite.gpusim)
    # Episode step limit for training lanes; 0 = the game's default (3000).
    # Changes the task (and the status time fraction, steps / limit).
    episode_steps: int = 0
    # Change floating-point rounding (see perf/REPORT.md for learning checks):
    compile: bool = False             # torch.compile the policy for sampling and the update
    bf16: bool = False                # bfloat16 autocast in the PPO update
    fused_adam: bool = False          # single fused Adam kernel
    compile_all: bool = False         # torch.compile the whole sampling forward and minibatch loss too

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


def tanh_mlp(width: int, hidden: int, depth: int) -> nn.Sequential:
    """`depth` Linear+Tanh layers, the first from `width` to `hidden`."""
    if depth < 1:
        raise ValueError("depth must be at least 1")
    layers = []
    for i in range(depth):
        layers += [layer_init(nn.Linear(width if i == 0 else hidden, hidden)), nn.Tanh()]
    return nn.Sequential(*layers)


class ActorCritic(nn.Module):
    """Parameter-efficient baseline: shared features, separate policy/value heads.

    Sharing is a design choice, not an assumption that the two objectives always
    want identical features. SeparateActorCritic tests that alternative.
    """

    def __init__(self, obs_size: int, n_actions: int, hidden: int = 512, depth: int = 2):
        super().__init__()
        self.trunk = tanh_mlp(obs_size, hidden, depth)
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
        # validate_args=False: the checks only raise, and each costs a host
        # sync on GPU (two per call). Non-finite losses are still caught in
        # the update; outputs and the sampling stream are unchanged.
        dist = Categorical(logits=logits, validate_args=False)
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

    native_autoreset=True steps and resets finished lanes inside one C call
    (tl_batch_step_autoreset) with the same seed order, final observations and
    infos as the Python loop below. compact=True keeps observations as raw C
    rows (terraria_lite.compact) instead of the float32 one-hot encoding.
    pin_memory=True places the obs/mask arrays in page-locked memory, so they
    can be copied to a GPU without staging or a host sync.
    """

    def __init__(self, n: int, seed: int = 1, restart=None, workers: int = 4,
                 native_autoreset: bool = False, compact: bool = False, pin_memory: bool = False,
                 max_steps: int = 0):
        self.envs = [TerrariaLite(max_steps=max_steps or None) for _ in range(n)]
        self.n = n
        self._next_seed = seed
        self.compact = compact

        def host(shape, dtype):
            return torch.zeros(shape, dtype=dtype, pin_memory=pin_memory).numpy()
        if compact:
            from terraria_lite.compact import RAW_BYTES
            self.obs = host((n, RAW_BYTES), torch.uint8)
        else:
            self.obs = host((n, SPEC.obs_size), torch.float32)
        self.mask = host((n, SPEC.n_actions), torch.bool)
        # Optional training-only start-state hook: restart(lane, env) returns
        # (obs, info) after restoring some state, or None for a fresh world.
        # `restored[i]` says whether lane i's current episode came from it.
        self.restart = restart
        if restart is not None and (native_autoreset or compact):
            raise ValueError("start-state restarts need the Python reset loop with flat observations")
        self.native_autoreset = native_autoreset
        self.restored = np.zeros(n, dtype=bool)
        from terraria_lite.batch import NativeBatch
        self.native = NativeBatch(self.envs, workers=workers)

    def _fresh_seed(self) -> int:
        s = self._next_seed
        self._next_seed += 1
        return s

    def _reset_lane(self, i: int, e) -> None:
        flat = e.reset(seed=self._fresh_seed())[0]
        if self.compact:
            from terraria_lite.compact import fields
            tile, light, status = fields(self.obs[i])
            tile[:], light[:], status[:] = e._tile, e._light, e._status
        else:
            self.obs[i] = flat

    def reset(self) -> tuple[np.ndarray, np.ndarray]:
        for i, e in enumerate(self.envs):
            self._reset_lane(i, e)
            self.mask[i] = e.action_mask()
        return self.obs, self.mask

    def step(self, actions):
        """Returns (obs, mask, reward, terminated, truncated, final_obs, infos).

        `obs`/`mask` are what to act from next -- already reset where an
        episode ended. `final_obs` holds the real terminal observation for
        those lanes, for diagnostics or an explicit external-truncation control;
        its other rows are zero.
        """
        if self.native_autoreset:
            return self._step_native(actions)
        if self.compact:
            rew, term, trunc = self.native.step_raw(actions, self.obs)
            self.mask[:] = self.native.masks
        else:
            rew, term, trunc = self.native.step(actions, self.obs, self.mask)
        final = np.zeros(self.obs.shape, self.obs.dtype)   # calloc: untouched rows cost nothing
        finished = []

        for i in np.flatnonzero(term | trunc):
            e = self.envs[i]
            final[i] = self.obs[i]
            info = e._info()
            info["restored_start"] = bool(self.restored[i])
            finished.append((int(i), info))
            started = self.restart(int(i), e) if self.restart is not None else None
            self.restored[i] = started is not None
            if started is not None:
                self.obs[i] = started[0]
            else:
                self._reset_lane(int(i), e)
            self.mask[i] = e.action_mask()
        return self.obs, self.mask, rew, term, trunc, final, finished

    def _step_native(self, actions):
        final = np.zeros(self.obs.shape, self.obs.dtype)   # calloc: untouched rows cost nothing
        seed0 = self._next_seed
        lanes = self.native.step_autoreset(actions, self.obs, final, seed0)
        self.mask[:] = self.native.masks
        ends = self.native.ends
        finished = []
        for k, i in enumerate(lanes.tolist()):
            steps, health, depth, ach = self.native.info[i].tolist()
            ach &= 0xFFFFFFFF
            finished.append((i, {"steps": steps, "episode_return": float(self.native.info_return[i]),
                                 "health": health, "depth": depth, "achievements": bin(ach).count("1"),
                                 "achievement_mask": ach, "restored_start": bool(self.restored[i])}))
            self.restored[i] = False
            self.envs[i]._seed = seed0 + k
        self._next_seed = seed0 + len(lanes)
        return self.obs, self.mask, self.native.rewards.copy(), ends == 1, ends == 2, final, finished

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

class _Uploader:
    """Host arrays -> persistent tensors on `device`, one per name, each
    overwritten by that name's next upload (in stream order, so earlier
    consumers of the previous value are unaffected). On a GPU the copies are
    non-blocking from page-locked memory -- staged through a pinned buffer
    unless the array already is pinned -- so they never stall the host the
    way a pageable copy does. The caller must not rewrite a host array before
    the copy ran: in the rollout loop every step's action fetch synchronises
    the stream before the simulator writes again."""

    def __init__(self, device):
        self.device, self.gpu = device, device.type == "cuda"
        self.host, self.dev = {}, {}

    def __call__(self, name, array):
        if not self.gpu or isinstance(array, torch.Tensor):
            return torch.as_tensor(array, device=self.device)
        src = torch.from_numpy(np.ascontiguousarray(array))
        if not src.is_pinned():
            staged = self.host.get(name)
            if staged is None or staged.shape != src.shape or staged.dtype != src.dtype:
                staged = self.host[name] = torch.empty_like(src, pin_memory=True)
            src = staged.copy_(src)
        out = self.dev.get(name)
        if out is None or out.shape != src.shape or out.dtype != src.dtype:
            out = self.dev[name] = torch.empty(src.shape, dtype=src.dtype, device=self.device)
        return out.copy_(src, non_blocking=True)


def _absorb_truncation(cfg, agent, rewards, term, trunc, final_obs, t, device, expand=None):
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
        x = torch.as_tensor(final_obs[cut], device=device)
        v = agent.value(expand(x) if expand is not None else x)
    rewards[t, torch.as_tensor(cut, device=device)] += cfg.gamma * v


def _score_bf16(agent, x, action, mask):
    """agent.act's update-time outputs with the network under bfloat16
    autocast; the masked distribution, log-probs and values stay float32."""
    with torch.autocast(device_type=x.device.type, dtype=torch.bfloat16):
        h = agent.trunk(x)
        logits, value = agent.actor(h), agent.critic(h)
    logits = logits.float().masked_fill(~mask, float("-inf"))
    dist = Categorical(logits=logits, validate_args=False)   # see ActorCritic.act
    return dist.log_prob(action), dist.entropy(), value.float().squeeze(-1)


def _sample_heads(agent, x, mask, expand=None):
    """Rollout-time policy heads (compile_all): normalised masked logits (as
    Categorical stores them), their probabilities and the value."""
    h = agent.trunk(expand(x) if expand is not None else x)
    logits = agent.actor(h).masked_fill(~mask, float("-inf"))
    logits = logits - logits.logsumexp(-1, keepdim=True)
    return logits, logits.softmax(-1), agent.critic(h).squeeze(-1)


def _ppo_loss(agent, obs, action, mask, old_logp, adv, ret, old_value, *, expand, bf16,
              clip_coef, clip_vloss, ent_coef, vf_coef):
    """One minibatch: clipped policy loss with per-minibatch advantage
    normalisation, (clipped) value loss and entropy bonus. Returns the loss,
    the approximate KL, the clip fraction and the per-sample entropy."""
    x = expand(obs) if expand is not None else obs
    if bf16:
        newlogp, entropy, newval = _score_bf16(agent, x, action, mask)
    else:
        _, newlogp, entropy, newval = agent.act(x, action, mask=mask)
    logratio = newlogp - old_logp
    ratio = logratio.exp()

    with torch.no_grad():
        # Schulman's low-variance KL estimator; also the early-stop signal.
        approx_kl = ((ratio - 1) - logratio).mean()
        clipfrac = ((ratio - 1.0).abs() > clip_coef).float().mean()

    # Normalise advantages per minibatch, not per batch.
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)

    pg = torch.max(-adv * ratio, -adv * torch.clamp(ratio, 1 - clip_coef, 1 + clip_coef)).mean()

    if clip_vloss:
        v_unclipped = (newval - ret) ** 2
        v_clipped = (old_value + torch.clamp(newval - old_value, -clip_coef, clip_coef) - ret) ** 2
        v_loss = 0.5 * torch.max(v_unclipped, v_clipped).mean()
    else:
        v_loss = 0.5 * ((newval - ret) ** 2).mean()

    loss = pg - ent_coef * entropy.mean() + vf_coef * v_loss
    return loss, approx_kl, clipfrac, entropy


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
    if cfg.achievement_reward not in ("equal", "difficulty"):
        raise ValueError("Unknown achievement reward scheme")
    if cfg.memory_features and cfg.bootstrap_time_limit:
        raise ValueError("Truncation bootstrap does not track memory features")
    if cfg.compact_obs:
        unsupported = {"memory_features": cfg.memory_features, "sil_minibatches": cfg.sil_minibatches,
                       "curiosity_coef": cfg.curiosity_coef, "progress_coef": cfg.progress_coef,
                       "archive_start_prob": cfg.archive_start_prob, "aux_coef": cfg.aux_coef,
                       "achievement_reward=difficulty": cfg.achievement_reward != "equal"}
        used = [k for k, v in unsupported.items() if v]
        if used:
            raise ValueError(f"compact_obs supports potential/novelty shaping only, not {', '.join(used)}")
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    device = torch.device(cfg.device)
    collect_device = torch.device(cfg.collect_device or cfg.device)

    archive = None
    if cfg.archive_start_prob:
        from terraria_lite.archive import StartArchive
        archive = StartArchive(cfg.archive_capacity, cfg.archive_start_prob, seed=cfg.seed)
    env_seed = cfg.seed*10_000_000 if SPEC.version>=2 else cfg.seed
    if cfg.sim_backend == "gpu":
        if archive is not None:
            raise ValueError("the GPU simulator backend does not support archive restarts")
        if cfg.episode_steps:
            raise ValueError("the GPU simulator backend uses the default episode limit")
        from terraria_lite.gpusim import GpuVec
        envs = GpuVec(cfg.num_envs, seed=env_seed, device=collect_device, compact=cfg.compact_obs)
    elif cfg.sim_backend == "cpu":
        envs = VecTerraria(cfg.num_envs, seed=env_seed,
                           restart=archive.restart if archive is not None else None,
                           workers=cfg.sim_workers, native_autoreset=cfg.native_autoreset,
                           compact=cfg.compact_obs, pin_memory=collect_device.type == "cuda",
                           max_steps=cfg.episode_steps)
    else:
        raise ValueError(f"unknown sim_backend {cfg.sim_backend!r}")
    memory = None
    if cfg.memory_features:
        from terraria_lite.memory_features import PolicyFeatures
        memory = PolicyFeatures(cfg.memory_features, cfg.num_envs)
    width = SPEC.obs_size + (memory.N_FEATURES if memory is not None else 0)
    from terraria_lite.spatial_agent import build_agent
    agent = build_agent(cfg.architecture, cfg.hidden, width - SPEC.obs_size,
                        depth=cfg.depth, cell_width=cfg.cell_width).to(device)
    if memory is not None:
        agent.memory_features = cfg.memory_features
    if cfg.init:
        raw = torch.load(cfg.init, map_location=device, weights_only=True)
        from terraria_lite.checkpoints import validate_checkpoint
        validate_checkpoint(raw)
        agent.load_state_dict(raw.get("model", raw) if isinstance(raw, dict) else raw)
    aux = None
    if cfg.aux_coef:
        from terraria_lite.predictive_aux import PredictiveAux
        aux = PredictiveAux(agent.actor.in_features).to(device)
    opt = torch.optim.Adam(list(agent.parameters()) + (list(aux.parameters()) if aux is not None else []),
                           lr=cfg.lr, eps=1e-5, **({"fused": True} if cfg.fused_adam else {}))
    # Rollout policy: the learner itself, or a copy re-synchronised after every
    # update, so collection always samples from the current parameters.
    actor = agent if collect_device == device else copy.deepcopy(agent).to(collect_device)
    if cfg.compile:
        # In place, so state_dict keys (checkpoints, evaluation) are unchanged.
        for model in {id(agent): agent, id(actor): actor}.values():
            model.trunk.compile(dynamic=False)
            model.actor.compile(dynamic=False)
    # Compact observations: uint8 rows on the host, in transfer and in the
    # rollout buffer; `expand` rebuilds the exact float32 policy input.
    expand_collect = expand_learn = None
    if cfg.compact_obs:
        from terraria_lite.compact import RAW_BYTES, Expander
        expand_collect, expand_learn = Expander(collect_device), Expander(device)
    # compile_all: one graph each for the sampling forward (expansion through
    # log-softmax and value; sampling itself stays eager) and the minibatch loss.
    ppo_loss = torch.compile(_ppo_loss, dynamic=False) if cfg.compile_all else _ppo_loss
    sample_heads = torch.compile(_sample_heads, dynamic=False) if cfg.compile_all else None

    T, N = cfg.rollout, cfg.num_envs
    # Rollout buffers live where they are written; the update moves them to the
    # learner once per iteration (a no-op when the devices coincide).
    if cfg.compact_obs:
        obs_b = torch.zeros((T, N, RAW_BYTES), dtype=torch.uint8, device=collect_device)
    else:
        obs_b = torch.zeros((T, N, width), device=collect_device)
    act_b = torch.zeros((T, N), dtype=torch.long, device=collect_device)
    logp_b = torch.zeros((T, N), device=collect_device)
    rew_b = torch.zeros((T, N), device=collect_device)
    done_b = torch.zeros((T, N), device=collect_device)
    val_b = torch.zeros((T, N), device=collect_device)
    # Stored, not recomputed: the update pass must score actions under the same
    # support they were sampled from, or the ratio is against a distribution
    # that never existed.
    msk_b = torch.zeros((T, N, SPEC.n_actions), dtype=torch.bool, device=collect_device)
    from terraria_lite.curiosity import RND
    curiosity=RND(SPEC.obs_size,device,balanced=cfg.curiosity_balanced) if cfg.curiosity_coef else None
    novelty_b=torch.empty((T, N, SPEC.obs_size), device=collect_device) if curiosity is not None else None

    o0, m0 = envs.reset()
    achievement_rewards = None
    if cfg.achievement_reward != "equal":
        from terraria_lite.achievement_rewards import AchievementRewards
        achievement_rewards = AchievementRewards(o0, cfg.achievement_reward)
    shaper = ProgressShaper(N) if cfg.progress_coef else None
    if shaper is not None:
        shaper.reset(o0)
    from terraria_lite.cells import cell_keys
    novelty = potential = sil = None
    if cfg.novelty_coef:
        from terraria_lite.count_novelty import CellNovelty
        novelty = CellNovelty(o0)
    if cfg.potential_coef:
        from terraria_lite.potential import RecipePotential
        potential = RecipePotential(o0, cfg.gamma, cfg.potential_coef, cfg.potential_mode)
    if cfg.sil_minibatches:
        from terraria_lite.self_imitation import SelfImitation
        sil = SelfImitation(N, cfg.gamma, device=device, value_coef=cfg.sil_value_coef, seed=cfg.seed)
    if archive is not None:
        archive.observe(envs.envs, o0, cell_keys(o0))

    def policy_input(raw, mask):
        """Agent input for the obs the policy acts from (raw plus feature sets)."""
        return raw if memory is None else np.concatenate((raw, memory.update(raw, mask)), 1)

    upload = _Uploader(collect_device)
    current = policy_input(o0, m0)
    next_obs = upload("obs", current)
    if cfg.compact_obs:
        next_raw, next_obs = next_obs, expand_collect(next_obs)
    next_mask = upload("mask", m0)
    next_done = torch.zeros(N, device=collect_device)
    extrinsic_episodes = restored_episodes = 0
    sil_stats: dict = {}

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
        threads = torch.get_num_threads()
        if cfg.collect_threads:
            torch.set_num_threads(cfg.collect_threads)
        for t in range(T):
            obs_b[t] = next_raw if cfg.compact_obs else next_obs
            done_b[t] = next_done
            msk_b[t] = next_mask
            with torch.inference_mode():
                if sample_heads is None:
                    a, logp, _, v = actor.act(next_obs, mask=next_mask)
                else:
                    logits, probs, v = sample_heads(actor, next_raw if cfg.compact_obs else next_obs, next_mask,
                                                    expand_collect)
                    a = torch.multinomial(probs, 1, True).squeeze(-1)   # as Categorical.sample
                    logp = logits.gather(-1, a[:, None]).squeeze(-1)
            act_b[t], logp_b[t], val_b[t] = a, logp, v

            obs, msk, r, term, trunc, final, finished = envs.step(a.cpu().numpy())
            ended = term | trunc
            if sil is not None:
                sil.add_step(obs_b[t].cpu().numpy(), act_b[t].cpu().numpy(),
                             msk_b[t].cpu().numpy(), r, ended)
            if achievement_rewards is not None:
                r = achievement_rewards.step(r, obs, final, ended)
            if novelty_b is not None:
                novelty_b[t]=torch.as_tensor(obs,device=collect_device)
                ended_lanes=np.flatnonzero(ended)
                if len(ended_lanes): novelty_b[t,torch.as_tensor(ended_lanes,device=collect_device)]=torch.as_tensor(final[ended_lanes],device=collect_device)
            if shaper is not None:
                r = r + progress_coef * shaper.step(obs, final, term, trunc)
            if novelty is not None:
                r = r + cfg.novelty_coef * novelty.step(obs, final, ended)
            if potential is not None:
                r = r + potential.step(obs, final, ended)
            if archive is not None:
                archive.observe(envs.envs, obs, cell_keys(obs))
            rew_b[t] = upload("reward", r)
            _absorb_truncation(cfg, actor, rew_b, term, trunc, final, t, collect_device, expand_collect)

            if memory is not None:
                memory.reset(np.flatnonzero(ended))
            next_obs = upload("obs", policy_input(obs, msk))
            if cfg.compact_obs:
                # compile_all expands inside the sampling graph; the float
                # rows are then only built for the bootstrap value below.
                next_raw, next_obs = next_obs, expand_collect(next_obs) if sample_heads is None else None
            next_mask = upload("mask", msk)
            # Autoreset makes both kinds episode boundaries. An explicitly
            # enabled external bootstrap was folded into rew_b above; using
            # only `term` here would add V(reset_obs) as well and carry GAE from
            # an unrelated fresh world across the boundary.
            boundary = np.logical_or(term, trunc)
            next_done = upload("done", boundary.astype(np.float32))
            step_count += N

            for _, info in finished:
                # Restored starts are training curriculum, not fresh-world
                # performance; keep them out of the episode telemetry.
                if info["restored_start"]:
                    restored_episodes += 1
                    continue
                extrinsic_episodes += 1
                ep_returns.append(info["episode_return"])
                ep_achievements.append(info["achievements"])
                ep_lengths.append(info["steps"])
                ep_deaths.append(1.0 if info["health"] <= 0 else 0.0)
                ep_masks.append(info["achievement_mask"])

        torch.set_num_threads(threads)
        collection_seconds += time.perf_counter() - phase_start
        phase_start = time.perf_counter()
        # ---- GAE ---------------------------------------------------------
        novelty_error=0.0
        if curiosity is not None:
            bonus,novelty_error=curiosity.bonus_and_update(novelty_b.reshape(-1,SPEC.obs_size).to(device))
            scale=cfg.curiosity_coef
            if cfg.curiosity_anneal:
                scale*=max(0.,1.-2.*(it-1)/n_iters)
            rew_b+=scale*bonus.reshape(T,N).to(collect_device)
        if next_obs is None:
            next_obs = expand_collect(next_raw)
        with torch.no_grad():
            next_value = actor.value(next_obs)
            adv = compute_gae(rew_b, done_b, val_b, next_value, next_done,
                              cfg.gamma, cfg.gae_lambda)
            ret = adv + val_b

        b_obs = obs_b.reshape(-1, obs_b.shape[-1]).to(device)
        b_act = act_b.reshape(-1).to(device)
        b_logp = logp_b.reshape(-1).to(device)
        b_adv = adv.reshape(-1).to(device)
        b_ret = ret.reshape(-1).to(device)
        b_val = val_b.reshape(-1).to(device)
        b_msk = msk_b.reshape(-1, SPEC.n_actions).to(device)
        if aux is not None:
            delta, unlock, valid = PredictiveAux.targets(obs_b, next_obs, done_b, next_done)
            b_delta = delta.reshape(-1, SPEC.n_items).to(device)
            b_unlock = unlock.reshape(-1, SPEC.n_achievements).to(device)
            b_valid = valid.reshape(-1).to(device)

        # ---- optimise ----------------------------------------------------
        idx = np.arange(cfg.batch)
        clipfracs, approx_kl = [], torch.tensor(0.0)
        for _ in range(cfg.epochs):
            np.random.shuffle(idx)
            # One index upload and one gather per tensor per epoch; minibatches
            # are then contiguous slices (the same rows, values and layout as
            # gathering each minibatch).
            perm = torch.as_tensor(idx, device=device)
            e_obs, e_act, e_logp, e_adv, e_ret, e_val, e_msk = (
                x[perm] for x in (b_obs, b_act, b_logp, b_adv, b_ret, b_val, b_msk))
            if aux is not None:
                e_delta, e_unlock, e_valid = b_delta[perm], b_unlock[perm], b_valid[perm]
            for s in range(0, cfg.batch, cfg.minibatch):
                mb = slice(s, s + cfg.minibatch)
                loss, approx_kl, clipfrac, entropy = ppo_loss(
                    agent, e_obs[mb], e_act[mb], e_msk[mb], e_logp[mb], e_adv[mb], e_ret[mb], e_val[mb],
                    expand=expand_learn, bf16=cfg.bf16, clip_coef=cfg.clip_coef, clip_vloss=cfg.clip_vloss,
                    ent_coef=cfg.ent_coef, vf_coef=cfg.vf_coef)
                clipfracs.append(clipfrac)
                if aux is not None:
                    loss = loss + cfg.aux_coef * aux.loss(agent, e_obs[mb], e_act[mb], e_delta[mb],
                                                          e_unlock[mb], e_valid[mb])
                if not torch.isfinite(loss):
                    raise FloatingPointError("Non-finite PPO loss; preserve this run without retrying")

                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), cfg.max_grad_norm)
                opt.step()

            if cfg.target_kl is not None and approx_kl > cfg.target_kl:
                break
        if sil is not None:
            sil_stats = sil.update(agent, opt, cfg.sil_minibatches, cfg.max_grad_norm)
        if actor is not agent:
            actor.load_state_dict(agent.state_dict())

        optimisation_seconds += time.perf_counter() - phase_start
        y = ret.cpu().numpy().ravel()
        yhat = val_b.cpu().numpy().ravel()
        var = np.var(y)
        ev = np.nan if var == 0 else 1 - np.var(y - yhat) / var
        if checkpoint_callback is not None:
            checkpoint_callback(agent, step_count, {
                "collection_seconds": collection_seconds,
                "optimisation_seconds": optimisation_seconds,
                "novelty_error": novelty_error,
                "policy_entropy": float(entropy.detach().mean()),
                # Last minibatch's approx KL, the iteration's mean clip
                # fraction and the rollout's value explained variance.
                "approx_kl": float(approx_kl), "clip_fraction": float(torch.stack(clipfracs).mean()),
                "explained_variance": float(ev),
                "fresh_episodes": extrinsic_episodes,
                "restored_episodes": restored_episodes,
                **({"archive": archive.stats()} if archive is not None else {}),
                **(novelty.stats() if novelty is not None else {}),
                **({"sil": sil_stats} if sil is not None else {}),
            })
        # ---- report ------------------------------------------------------
        sps = step_count / (time.perf_counter() - start)
        w = slice(-50, None)          # trailing window of finished episodes
        if not cfg.quiet:
            print(f"{it:5d} {step_count:9,} "
                  f"{np.mean(ep_returns[w]) if ep_returns else 0:8.2f} "
                  f"{np.mean(ep_achievements[w]) if ep_achievements else 0:6.2f} "
                  f"{np.mean(ep_lengths[w]) if ep_lengths else 0:6.0f} "
                  f"{100 * np.mean(ep_deaths[w]) if ep_deaths else 0:7.0f} "
                  f"{entropy.mean().item():8.3f} {approx_kl.item():7.4f} "
                  f"{torch.stack(clipfracs).mean().item():6.3f} {ev:6.2f} {sps:7,.0f}")

    envs.close()

    tail = ep_masks[-200:]
    summary = {
        "agent": "ppo",
        "gamma": cfg.gamma, "seed": cfg.seed, "ent_coef": cfg.ent_coef,
        "progress_coef": cfg.progress_coef,
        "progress_anneal": cfg.progress_anneal,
        "lr": cfg.lr, "envs": cfg.num_envs, "steps": step_count,
        "architecture": cfg.architecture,"curiosity_coef": cfg.curiosity_coef,
        "hidden": cfg.hidden, "depth": cfg.depth, "cell_width": cfg.cell_width,
        "parameters": sum(p.numel() for p in agent.parameters()),
        "achievement_reward": cfg.achievement_reward,
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
        "exploration": {"archive_start_prob": cfg.archive_start_prob, "sil_minibatches": cfg.sil_minibatches,
                        "novelty_coef": cfg.novelty_coef, "potential_coef": cfg.potential_coef,
                        "memory_features": cfg.memory_features, "restored_episodes": restored_episodes,
                        **({"archive": archive.stats()} if archive is not None else {}),
                        **(novelty.stats() if novelty is not None else {}),
                        **({"sil": sil_stats} if sil is not None else {})},
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
                    "obs_size": SPEC.obs_size, "n_actions": SPEC.n_actions,
                    **({"memory_features": cfg.memory_features, "extra": width - SPEC.obs_size}
                       if memory is not None else {})}, cfg.save)
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
            "See docs/reports/ITERATION_2026_10.md for current evidence.\n"
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
    p.add_argument("--hidden", type=int, default=Config.hidden,
                   help="global trunk width, 0 = architecture default")
    p.add_argument("--depth", type=int, default=Config.depth,
                   help="global trunk layers (targets, mlp)")
    p.add_argument("--cell-width", type=int, default=Config.cell_width,
                   help="per-cell MLP width (targets)")
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
    p.add_argument("--collect-device", type=str, default=Config.collect_device,
                   help='rollout sampling device, "" = --device; cpu with --device mps')
    p.add_argument("--collect-threads", type=int, default=Config.collect_threads,
                   help="torch threads while sampling, 0 = --threads")
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
                     collect_device=a.collect_device, collect_threads=a.collect_threads,
                     save=a.save, init=a.init, quiet=a.quiet,architecture=a.architecture,
                     hidden=a.hidden, depth=a.depth, cell_width=a.cell_width,
                     gae_lambda=a.gae_lambda,bootstrap_time_limit=a.bootstrap_time_limit,curiosity_coef=a.curiosity_coef,
                     curiosity_balanced=a.balanced_curiosity))
    if a.json:
        print(json.dumps(s))
