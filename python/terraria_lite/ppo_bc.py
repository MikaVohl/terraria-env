"""Warm-start PPO by cloning the repository's scripted expert.

The expert is intentionally privileged: it searches the full world for ore.
Behavior cloning is therefore an aggressive experiment, not a fair replacement
for PPO-from-scratch. The policy still receives only its ordinary partial
observation, and all final evaluation uses unmodified environment rewards.

    uv run python -m terraria_lite.ppo_bc --seeds 128 --epochs 6
    uv run python -m terraria_lite.ppo_agent --init ppo_bc.pt --steps 2000000
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import torch

from terraria_lite import SPEC, TerrariaLite
from terraria_lite.ppo_agent import ActorCritic


KEYS = {
    "s": 0, "a": 1, "d": 2, "w": 3,
    **{k: 4 + i for i, k in enumerate("yuihknm,./")},
    **{k: 14 + i for i, k in enumerate("YUIHKNM<>?")},
    "e": 24,
    **{k: 25 + i for i, k in enumerate("1234567890-")},
}


def expert_actions(seed: int, selftest: Path) -> np.ndarray:
    run = subprocess.run([str(selftest), "--record", str(seed)], check=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    tape = run.stdout.strip()
    try:
        return np.fromiter((KEYS[k] for k in tape), dtype=np.int64)
    except KeyError as exc:
        raise ValueError(f"unknown expert tape key {exc.args[0]!r}") from exc


def collect(seeds: range, selftest: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    observations, masks, actions = [], [], []
    illegal = 0
    for seed in seeds:
        tape = expert_actions(seed, selftest)
        env = TerrariaLite(max_steps=max(SPEC.default_steps, len(tape) + 1))
        try:
            obs, _ = env.reset(seed=seed)
            for action in tape:
                mask = env.action_mask()
                # The expert sometimes names a mining/movement action that is
                # observationally equivalent to noop while physics advances.
                # Such a label has probability zero under the runtime action
                # mask, so cloning it would produce infinite loss. Step it to
                # preserve the trajectory but omit it from supervised data.
                valid = bool(mask[action])
                illegal += int(not valid)
                if valid:
                    observations.append(obs.astype(np.float16))
                    masks.append(mask)
                    actions.append(action)
                obs, _, term, trunc, _ = env.step(int(action))
                if term or trunc:
                    break
        finally:
            env.close()
    print(f"collected {len(actions):,} valid transitions from {len(seeds)} seeds "
          f"({illegal} masked-inert labels omitted)")
    return (np.stack(observations), np.stack(masks),
            np.asarray(actions, dtype=np.int64))


def pretrain(agent: ActorCritic, obs: np.ndarray, mask: np.ndarray,
             action: np.ndarray, *, epochs: int, batch: int, lr: float,
             device: str, seed: int) -> None:
    rng = np.random.default_rng(seed)
    opt = torch.optim.Adam(agent.parameters(), lr=lr, eps=1e-5)
    idx = np.arange(len(action))
    agent.train()

    for epoch in range(1, epochs + 1):
        rng.shuffle(idx)
        losses, correct = [], 0
        for start in range(0, len(idx), batch):
            pick = idx[start:start + batch]
            x = torch.as_tensor(obs[pick].astype(np.float32), device=device)
            m = torch.as_tensor(mask[pick], device=device)
            y = torch.as_tensor(action[pick], device=device)
            _, logp, entropy, _ = agent.act(x, action=y, mask=m)
            # A small entropy term avoids producing a brittle, nearly
            # deterministic clone before PPO has seen a single on-policy step.
            loss = -logp.mean() - 0.001 * entropy.mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(agent.parameters(), 1.0)
            opt.step()
            losses.append(loss.item())
            with torch.no_grad():
                logits = agent.actor(agent.trunk(x)).masked_fill(~m, float("-inf"))
                correct += int((logits.argmax(-1) == y).sum())
        print(f"epoch {epoch:2d}: loss {np.mean(losses):.4f}, "
              f"train accuracy {100 * correct / len(idx):.2f}%")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=int, default=128)
    p.add_argument("--seed-start", type=int, default=1)
    p.add_argument("--epochs", type=int, default=6)
    p.add_argument("--batch", type=int, default=512)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--device", default="cpu")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--selftest", type=Path, default=Path("./selftest"))
    p.add_argument("--save", type=Path, default=Path("ppo_bc.pt"))
    a = p.parse_args()

    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    obs, mask, action = collect(range(a.seed_start, a.seed_start + a.seeds),
                                a.selftest.resolve())
    agent = ActorCritic(SPEC.obs_size, SPEC.n_actions).to(a.device)
    pretrain(agent, obs, mask, action, epochs=a.epochs, batch=a.batch,
             lr=a.lr, device=a.device, seed=a.seed)
    torch.save(agent.state_dict(), a.save)
    print(f"saved {a.save}")


if __name__ == "__main__":
    main()
