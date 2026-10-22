"""Holdout evaluation and inventory diagnostics for Dreamer checkpoints.

`evaluate` mirrors terraria_lite.ppo_eval.evaluate (one episode per seed,
cohorts of 64, NativeBatch flat stepping, torch.manual_seed(sample_seed),
categorical sampling from the masked policy, identical result keys), and
`diagnose` mirrors tools/policy_diagnostics.py, so numbers are comparable with
the PPO studies. The only difference is the policy call: Dreamer filters a
recurrent latent state and samples its stochastic latent from the same RNG.

    PYTHONPATH=python python -m terraria_lite.dreamer.evaluate CKPT --out eval.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from terraria_lite import SPEC, TerrariaLite
from terraria_lite.batch import NativeBatch
from terraria_lite.dreamer.nets import sample_logp


@torch.no_grad()
def evaluate(agent, seeds: list[int], *, num_envs: int = 64, greedy: bool = False,
             sample_seed: int = 12345, device: str | None = None) -> dict:
    device = agent.device
    torch.manual_seed(sample_seed)
    records: list[dict] = []
    for base in range(0, len(seeds), num_envs):
        batch_seeds = seeds[base:base + num_envs]
        envs = [TerrariaLite() for _ in batch_seeds]
        try:
            obs = np.stack([e.reset(seed=s)[0] for e, s in zip(envs, batch_seeds)])
            mask = np.stack([e.action_mask() for e in envs])
            active = np.ones(len(envs), dtype=bool)
            native = NativeBatch(envs, workers=4)
            status_start = SPEC.cells * (SPEC.tile_kinds + 1)
            depth_index = status_start + SPEC.status_depth
            ach_index = status_start + SPEC.status_ach0
            peak_depth = np.rint(obs[:, depth_index] * (SPEC.world_h - 1)).astype(np.int32)
            first_steps = np.zeros((len(envs), SPEC.n_achievements), np.int32)
            last_achievement = np.zeros(len(envs), np.int32)
            tick = 0
            state = agent.initial_state(len(envs))
            first = torch.ones(len(envs), dtype=torch.bool, device=device)
            not_first = torch.zeros_like(first)
            while active.any():
                x = torch.as_tensor(obs, device=device)
                m = torch.as_tensor(mask, device=device)
                actions, state = agent.act(x, m, state, first, greedy=greedy)
                first = not_first
                _, term, trunc = native.step(actions.cpu().numpy(), obs, mask)
                tick += 1
                peak_depth[active] = np.maximum(peak_depth[active], np.rint(obs[active, depth_index] * (SPEC.world_h - 1)).astype(np.int32))
                new = (first_steps == 0) & (obs[:, ach_index:ach_index + SPEC.n_achievements] > .5) & active[:, None]
                first_steps[new] = tick
                last_achievement[new.any(axis=1)] = tick
                for i in np.flatnonzero(active & (term | trunc)):
                    active[i] = False
                    info = envs[i]._info()
                    records.append({"seed": batch_seeds[i], **info, "died": info["health"] <= 0,
                                    "peak_depth": int(peak_depth[i]), "last_achievement_step": int(last_achievement[i]),
                                    "first_achievement_steps": {name: int(first_steps[i, j]) for j, name in enumerate(SPEC.achievement_names) if first_steps[i, j] > 0}})
        finally:
            for e in envs:
                e.close()

    achievements = np.asarray([r["achievements"] for r in records], dtype=float)
    returns = np.asarray([r["episode_return"] for r in records], dtype=float)
    lengths = np.asarray([r["steps"] for r in records], dtype=float)
    hits = Counter()
    for r in records:
        for i, name in enumerate(SPEC.achievement_names):
            if (int(r["achievement_mask"]) >> i) & 1:
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
        "mean_peak_depth": float(np.mean([r["peak_depth"] for r in records])),
        "mean_steps_after_last_achievement": float(np.mean([r["steps"] - r["last_achievement_step"] for r in records])),
        "first_achievement_steps": {name: {"episodes": len(times), "mean": float(np.mean(times)), "median": float(np.median(times))}
                                    for name in SPEC.achievement_names if (times := [r["first_achievement_steps"][name] for r in records if name in r["first_achievement_steps"]])},
        "hits": {name: hits[name] for name in SPEC.achievement_names if hits[name]},
        "records": records,
    }


@torch.no_grad()
def diagnose(agent, seeds, sample_seed=54321):
    """tools/policy_diagnostics.diagnose for a Dreamer agent (same outputs)."""
    device = agent.device
    torch.manual_seed(sample_seed)
    totals = np.zeros(SPEC.n_actions, np.int64); legal = np.zeros_like(totals)
    probability = np.zeros(SPEC.n_actions, np.float64); maxes = []; records = []
    inv0 = SPEC.cells * (SPEC.tile_kinds + 1) + SPEC.status_inv0
    for base in range(0, len(seeds), 64):
        cohort = seeds[base:base + 64]; envs = [TerrariaLite() for _ in cohort]
        try:
            obs = np.stack([e.reset(seed=s)[0] for e, s in zip(envs, cohort)])
            mask = np.stack([e.action_mask() for e in envs]); active = np.ones(len(envs), bool)
            peak = np.zeros((len(envs), SPEC.n_items), np.int32)
            opportunities = np.zeros((len(envs), SPEC.n_actions), np.int32)
            native = NativeBatch(envs)
            state = agent.initial_state(len(envs))
            first = torch.ones(len(envs), dtype=torch.bool, device=device)
            for t in range(SPEC.default_steps):
                inv = np.rint(obs[:, inv0:inv0 + SPEC.n_items] ** 2 * SPEC.inventory_clip).astype(np.int32)
                peak[active] = np.maximum(peak[active], inv[active])
                x = torch.as_tensor(obs, device=device); m = torch.as_tensor(mask, device=device)
                logp, (h, z) = agent.policy_logp(x, m, state, first)
                a = sample_logp(logp)
                state = (h, z, a)
                first = torch.zeros_like(first)
                actions = a.cpu().numpy()
                legal += mask[active].sum(0); probability += logp.exp().cpu().numpy()[active].sum(0)
                totals += np.bincount(actions[active], minlength=SPEC.n_actions)
                opportunities[active] += mask[active]
                _, te, tr = native.step(actions, obs, mask)
                inv = np.rint(obs[:, inv0:inv0 + SPEC.n_items] ** 2 * SPEC.inventory_clip).astype(np.int32)
                peak[active] = np.maximum(peak[active], inv[active])
                for i in np.flatnonzero(active & (te | tr)):
                    records.append({"seed": cohort[i], "info": envs[i]._info(),
                                    "inventory_peak": peak[i].tolist(), "legal_steps": opportunities[i].tolist()})
                    active[i] = False
                if not active.any(): break
            maxes.extend(peak)
        finally:
            for e in envs: e.close()
    maxes = np.asarray(maxes)
    return {"episodes": len(records), "inventory_peak": {name: {"mean": float(maxes[:, i].mean()),
                "median": float(np.median(maxes[:, i])), "max": int(maxes[:, i].max())} for i, name in enumerate(SPEC.item_names)},
            "actions": {name: {"legal_steps": int(legal[i]), "chosen": int(totals[i]),
                  "mean_probability_when_legal": float(probability[i] / max(1, legal[i])),
                  "episodes_with_opportunity": sum(r["legal_steps"][i] > 0 for r in records)}
                       for i, name in enumerate(SPEC.action_names)}, "records": records}


def main() -> None:
    from terraria_lite.dreamer.agent import load_dreamer
    from terraria_lite.ppo_eval import print_report
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("checkpoint", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--episodes", type=int, default=128)
    p.add_argument("--seed-start", type=int, default=23_000_001)
    p.add_argument("--device", default="cpu")
    p.add_argument("--diagnose", action="store_true", help="policy_diagnostics-style inventory/action report")
    a = p.parse_args()
    agent = load_dreamer(a.checkpoint, a.device)
    seeds = list(range(a.seed_start, a.seed_start + a.episodes))
    if a.diagnose:
        result = diagnose(agent, seeds)
        result["sample_seed"] = 54321
        print(json.dumps({k: result["inventory_peak"][k] for k in ("wood", "iron bar", "gold bar")}))
    else:
        result = evaluate(agent, seeds, sample_seed=54321)
        print_report(result, a.checkpoint.name, False)
    result["seed_range"] = [seeds[0], seeds[-1]]
    result["environment_version"] = SPEC.version
    result["checkpoint_sha256"] = hashlib.sha256(a.checkpoint.read_bytes()).hexdigest()
    if a.out:
        a.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
