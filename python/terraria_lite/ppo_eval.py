"""Reproducible holdout evaluation for terraria-lite PPO checkpoints.

Training summaries report the last episodes encountered during collection. That
is useful telemetry, but it is a biased and noisy model-selection signal. This
module evaluates a frozen policy on an explicit seed range, with no autoreset
and no writes:

    uv run python -m terraria_lite.ppo_eval ppo_terraria.pt --episodes 256
    uv run python -m terraria_lite.ppo_eval ppo_terraria.pt --greedy
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import torch

from terraria_lite import SPEC, TerrariaLite
from terraria_lite.ppo_agent import ActorCritic


def load_agent(path: str | Path, device: str = "cpu"):
    raw = torch.load(Path(path), map_location=device, weights_only=True)
    # Keep compatibility with both the original plain state_dict checkpoints
    # and richer experiment checkpoints if those are introduced later.
    state = raw.get("model", raw) if isinstance(raw, dict) else raw
    if isinstance(raw, dict) and raw.get("architecture") == "lstm":
        from terraria_lite.recurrent_ppo_agent import RecurrentActorCritic
        agent = RecurrentActorCritic(SPEC.obs_size, SPEC.n_actions,
                                     encoder=int(raw["encoder"]),
                                     hidden=int(raw["hidden"])).to(device)
        agent.load_state_dict(state)
        agent.eval()
        return agent
    hidden = int(state["trunk.0.weight"].shape[0])
    agent = ActorCritic(SPEC.obs_size, SPEC.n_actions, hidden=hidden).to(device)
    agent.load_state_dict(state)
    agent.eval()
    return agent


@torch.no_grad()
def evaluate(agent: ActorCritic, seeds: list[int], *, num_envs: int = 64,
             greedy: bool = False, sample_seed: int = 12345,
             device: str = "cpu") -> dict:
    """Evaluate exactly one episode per seed and return aggregate metrics."""
    torch.manual_seed(sample_seed)
    records: list[dict] = []

    recurrent = hasattr(agent, "initial_state")
    for base in range(0, len(seeds), num_envs):
        batch_seeds = seeds[base:base + num_envs]
        envs = [TerrariaLite() for _ in batch_seeds]
        try:
            obs = np.stack([e.reset(seed=s)[0] for e, s in zip(envs, batch_seeds)])
            mask = np.stack([e.action_mask() for e in envs])
            active = np.ones(len(envs), dtype=bool)
            if recurrent:
                state = agent.initial_state(len(envs), device)
                done = torch.zeros(len(envs), device=device)

            while active.any():
                x = torch.as_tensor(obs, device=device)
                m = torch.as_tensor(mask, device=device)
                if recurrent:
                    h, state = agent.core_step(x, state, done)
                    logits = agent.actor(h).masked_fill(~m, float("-inf"))
                else:
                    h = agent.trunk(x)
                    logits = agent.actor(h).masked_fill(~m, float("-inf"))
                actions = (logits.argmax(-1) if greedy else
                           torch.distributions.Categorical(logits=logits).sample())

                for i, e in enumerate(envs):
                    if not active[i]:
                        continue
                    o, _, term, trunc, info = e.step(int(actions[i]))
                    obs[i] = o
                    if term or trunc:
                        active[i] = False
                        records.append({"seed": batch_seeds[i], **info,
                                        "died": info["health"] <= 0})
                    else:
                        mask[i] = e.action_mask()
        finally:
            for e in envs:
                e.close()

    achievements = np.asarray([r["achievements"] for r in records], dtype=float)
    returns = np.asarray([r["episode_return"] for r in records], dtype=float)
    lengths = np.asarray([r["steps"] for r in records], dtype=float)
    masks = [int(r["achievement_mask"]) for r in records]
    hits = Counter()
    for bits in masks:
        for i, name in enumerate(SPEC.achievement_names):
            if (bits >> i) & 1:
                hits[name] += 1

    return {
        "episodes": len(records),
        "mean_achievements": float(achievements.mean()),
        "std_achievements": float(achievements.std()),
        "median_achievements": float(np.median(achievements)),
        "p90_achievements": float(np.percentile(achievements, 90)),
        "max_achievements": int(achievements.max()),
        "mean_return": float(returns.mean()),
        "mean_length": float(lengths.mean()),
        "death_rate": float(np.mean([r["died"] for r in records])),
        "hits": {name: hits[name] for name in SPEC.achievement_names if hits[name]},
        "records": records,
    }


def print_report(result: dict, label: str, greedy: bool) -> None:
    n = result["episodes"]
    mode = "greedy" if greedy else "sampled"
    print(f"{label} ({mode}, {n} holdout episodes)")
    print(f"  achievements  {result['mean_achievements']:.3f} +/- "
          f"{result['std_achievements']:.3f}  "
          f"median {result['median_achievements']:.1f}  "
          f"p90 {result['p90_achievements']:.1f}  max {result['max_achievements']}")
    print(f"  return        {result['mean_return']:+.3f}")
    print(f"  episode       {result['mean_length']:.0f} steps")
    print(f"  died          {100 * result['death_rate']:.1f}%")
    print("  achievement hit rate:")
    for name, count in result["hits"].items():
        print(f"    {name:<18} {100 * count / n:6.2f}% ({count}/{n})")
    never = [name for name in SPEC.achievement_names if name not in result["hits"]]
    if never:
        print(f"  first never reached: {never[0]}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("checkpoint")
    p.add_argument("--episodes", type=int, default=256)
    p.add_argument("--seed-start", type=int, default=10001)
    p.add_argument("--envs", type=int, default=64)
    p.add_argument("--sample-seed", type=int, default=12345)
    p.add_argument("--greedy", action="store_true")
    p.add_argument("--device", default="cpu")
    a = p.parse_args()
    seeds = list(range(a.seed_start, a.seed_start + a.episodes))
    agent = load_agent(a.checkpoint, a.device)
    result = evaluate(agent, seeds, num_envs=a.envs, greedy=a.greedy,
                      sample_seed=a.sample_seed, device=a.device)
    print_report(result, Path(a.checkpoint).name, a.greedy)


if __name__ == "__main__":
    main()
