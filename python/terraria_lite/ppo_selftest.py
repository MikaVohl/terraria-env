"""Fast correctness checks for PPO-specific boundary and shaping logic."""
from __future__ import annotations

import numpy as np
import torch

from terraria_lite.ppo_agent import ProgressShaper, VecTerraria, compute_gae


def test_gae_boundary() -> None:
    # At t=1 a fresh episode begins. Its very large reward/advantage must not
    # flow backward into t=0 from the previous episode.
    reward = torch.tensor([[1.0], [100.0]])
    value = torch.zeros_like(reward)
    done = torch.tensor([[0.0], [1.0]])
    advantage = compute_gae(reward, done, value, torch.zeros(1),
                            torch.ones(1), gamma=0.999, gae_lambda=0.95)
    assert torch.allclose(advantage[0], torch.tensor([1.0]))
    assert torch.allclose(advantage[1], torch.tensor([100.0]))


def test_progress_nonnegative_and_reset() -> None:
    envs = VecTerraria(2, seed=901)
    try:
        obs, _ = envs.reset()
        shaper = ProgressShaper(2)
        shaper.reset(obs)
        for _ in range(32):
            obs, _, _, term, trunc, final, _ = envs.step(np.zeros(2, dtype=int))
            bonus = shaper.step(obs, final, term, trunc)
            assert np.isfinite(bonus).all()
            assert (bonus >= 0).all()
    finally:
        envs.close()


def main() -> None:
    test_gae_boundary()
    test_progress_nonnegative_and_reset()
    print("PPO selftest passed")


if __name__ == "__main__":
    main()
