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
from terraria_lite.ppo_agent import ActorCritic, sample_categorical


def load_agent(path: str | Path, device: str = "cpu"):
    raw = torch.load(Path(path), map_location=device, weights_only=True)
    from terraria_lite.checkpoints import validate_checkpoint
    validate_checkpoint(raw)
    state = raw.get("model", raw) if isinstance(raw, dict) else raw
    if raw.get("architecture") == "double_dqn":
        from terraria_lite.replay_agent import ReplayQ
        agent=ReplayQ(int(raw.get("hidden",512))).to(device)
        agent.load_state_dict(state);agent.eval();return agent
    if isinstance(raw, dict) and raw.get("architecture") in ("lstm", "lstm_targets"):
        from terraria_lite.recurrent_ppo_agent import build_recurrent_agent
        agent = build_recurrent_agent(raw["architecture"], encoder=int(raw["encoder"]),
                                     hidden=int(raw["hidden"])).to(device)
        agent.load_state_dict(state)
        agent.eval()
        return agent
    if raw.get("memory"):
        from terraria_lite.memory_agent import MemoryActorCritic
        agent = MemoryActorCritic(raw["memory"], int(raw["memory_size"]), int(raw["memory_len"]),
                                  raw.get("architecture", "targets"), int(raw.get("hidden", 0)),
                                  int(raw.get("extra", 0)), depth=int(raw.get("depth", 2)),
                                  cell_width=int(raw.get("cell_width", 32))).to(device)
        agent.load_state_dict(state)
        agent.eval()
        return agent
    from terraria_lite.spatial_agent import agent_size, build_agent
    architecture=raw.get("architecture","mlp")
    agent = build_agent(architecture,extra=int(raw.get("extra",0)),**agent_size(architecture,state)).to(device)
    if raw.get("memory_features") is not None:
        agent.memory_features = raw["memory_features"]   # read by evaluate()
    agent.load_state_dict(state)
    agent.eval()
    return agent

def evaluate_checkpoint(path: str | Path, device: str, seeds: list[int], *, num_envs: int = 64,
                        sample_seed: int = 12345, threads: int = 0, max_steps: int = 0) -> dict:
    """evaluate(load_agent(path, device), ...) for a worker process; `threads`
    sets torch's intra-op threads first (the caller's count, so the CPU
    kernels and therefore the results are the same as evaluating in the
    caller)."""
    if threads:
        torch.set_num_threads(threads)
    return evaluate(load_agent(path, device), seeds, num_envs=num_envs, sample_seed=sample_seed, device=device,
                    max_steps=max_steps)



@torch.no_grad()
def evaluate(agent: ActorCritic, seeds: list[int], *, num_envs: int = 64,
             greedy: bool = False, sample_seed: int = 12345,
             device: str = "cpu", max_steps: int = 0) -> dict:
    """Evaluate exactly one episode per seed and return aggregate metrics.

    An agent with a `memory_features` attribute (set by load_agent from the
    checkpoint) acts from obs concatenated with that feature set, recomputed
    per lane from its own observations starting at episode start.
    """
    memory_name = getattr(agent, "memory_features", None)
    if memory_name is not None:
        from terraria_lite.memory_features import PolicyFeatures
        PolicyFeatures(memory_name, 1)   # validates the name before any episode
    torch.manual_seed(sample_seed)
    records: list[dict] = []

    recurrent = hasattr(agent, "initial_state")
    for base in range(0, len(seeds), num_envs):
        batch_seeds = seeds[base:base + num_envs]
        envs = [TerrariaLite(max_steps=max_steps or None) for _ in batch_seeds]
        try:
            obs = np.stack([e.reset(seed=s)[0] for e, s in zip(envs, batch_seeds)])
            mask = np.stack([e.action_mask() for e in envs])
            active = np.ones(len(envs), dtype=bool)
            # Fresh memory per batch: every lane starts its only episode here.
            memory = PolicyFeatures(memory_name, len(envs)) if memory_name is not None else None
            from terraria_lite.batch import NativeBatch
            native=NativeBatch(envs,workers=4)
            status_start=SPEC.cells*(SPEC.tile_kinds+1)
            depth_index=status_start+SPEC.status_depth
            ach_index=status_start+SPEC.status_ach0
            peak_depth=np.rint(obs[:,depth_index]*(SPEC.world_h-1)).astype(np.int32)
            first_steps=np.zeros((len(envs),SPEC.n_achievements),np.int32)
            last_achievement=np.zeros(len(envs),np.int32)
            tick=0
            if recurrent:
                state = agent.initial_state(len(envs), device)
                done = torch.zeros(len(envs), device=device)

            while active.any():
                x = torch.as_tensor(obs if memory is None else
                                    np.concatenate((obs, memory.update(obs, mask)), 1), device=device)
                m = torch.as_tensor(mask, device=device)
                if recurrent:
                    h, state = agent.core_step(x, state, done)
                    logits = agent.actor(h).masked_fill(~m, float("-inf"))
                else:
                    h = agent.trunk(x)
                    logits = agent.actor(h).masked_fill(~m, float("-inf"))
                actions = (logits.argmax(-1) if greedy else
                           sample_categorical(torch.distributions.Categorical(logits=logits),m))

                _,term,trunc=native.step(actions.cpu().numpy(),obs,mask)
                tick+=1
                peak_depth[active]=np.maximum(peak_depth[active],np.rint(obs[active,depth_index]*(SPEC.world_h-1)).astype(np.int32))
                new=(first_steps==0)&(obs[:,ach_index:ach_index+SPEC.n_achievements]>.5)&active[:,None]
                first_steps[new]=tick
                last_achievement[new.any(axis=1)]=tick
                for i in np.flatnonzero(active & (term | trunc)):
                    active[i]=False; info=envs[i]._info()
                    records.append({"seed":batch_seeds[i],**info,"died":info["health"]<=0,
                        "peak_depth":int(peak_depth[i]),"last_achievement_step":int(last_achievement[i]),
                        "first_achievement_steps":{name:int(first_steps[i,j]) for j,name in enumerate(SPEC.achievement_names) if first_steps[i,j]>0}})
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
        "mean_peak_depth":float(np.mean([r["peak_depth"] for r in records])),
        "mean_steps_after_last_achievement":float(np.mean([r["steps"]-r["last_achievement_step"] for r in records])),
        "first_achievement_steps":{name:{"episodes":len(times),"mean":float(np.mean(times)),"median":float(np.median(times))}
            for name in SPEC.achievement_names if (times:=[r["first_achievement_steps"][name] for r in records if name in r["first_achievement_steps"]])},
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
    p.add_argument("--max-steps", type=int, default=0, help="episode step limit; 0 = game default")
    a = p.parse_args()
    seeds = list(range(a.seed_start, a.seed_start + a.episodes))
    agent = load_agent(a.checkpoint, a.device)
    result = evaluate(agent, seeds, num_envs=a.envs, greedy=a.greedy,
                      sample_seed=a.sample_seed, device=a.device, max_steps=a.max_steps)
    print_report(result, Path(a.checkpoint).name, a.greedy)


if __name__ == "__main__":
    main()
