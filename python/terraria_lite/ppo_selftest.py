"""Fast correctness checks for PPO-specific boundary and shaping logic."""
from __future__ import annotations

import numpy as np
import torch
from terraria_lite import SPEC

from terraria_lite.ppo_agent import ProgressShaper, VecTerraria, compute_gae


def test_finite_deadline_objective() -> None:
    """An inherent action budget has no value beyond its final action.

    Also retain a tested, opt-in external-truncation/legacy control. Existing
    boundary parity tests alone could not catch an incorrect task objective.
    """
    from terraria_lite.ppo_agent import Config, _absorb_truncation
    from terraria_lite.recurrent_ppo_agent import Config as RConfig, _bootstrap_truncation

    class Critic:
        calls = 0

        def value(self, x):
            self.calls += 1
            return torch.full((len(x),), 5.0)

        def value_step(self, x, state, done):
            return self.value(x), state

    term = np.array([False, True, False, True])
    trunc = np.array([True, False, False, True])
    final = np.zeros((4, SPEC.obs_size), np.float32)
    raw = torch.tensor([[1.0, -1.0, 0.0, -1.0]])
    state = (torch.zeros(1, 4, 16), torch.zeros(1, 4, 16))
    for recurrent in (False, True):
        critic = Critic()
        for enabled in (False, True):
            cfg = (RConfig if recurrent else Config)(bootstrap_time_limit=enabled)
            reward = raw.clone()
            if recurrent:
                _bootstrap_truncation(cfg, critic, reward, term, trunc, final, state, 0, "cpu")
            else:
                _absorb_truncation(cfg, critic, reward, term, trunc, final, 0, "cpu")
            expected = raw.clone()
            if enabled:
                expected[0, 0] += cfg.gamma * 5
            torch.testing.assert_close(reward, expected)
            assert critic.calls == int(enabled)
            # Return target is exactly the final reward under finite semantics,
            # regardless of critic prediction or next reset world's value.
            value = torch.full_like(reward, 5.0)
            advantage = compute_gae(reward, torch.zeros_like(reward), value,
                                    torch.full((4,), 100.0), torch.ones(4),
                                    cfg.gamma, cfg.gae_lambda)
            torch.testing.assert_close(advantage + value, expected)

    # Undiscounted lambda=1 matches exact finite-episode Monte Carlo returns.
    reward = torch.tensor([[1.0], [2.0], [3.0]])
    value = torch.tensor([[4.0], [7.0], [8.0]])
    advantage = compute_gae(reward, torch.zeros_like(reward), value,
                            torch.tensor([100.0]), torch.ones(1), 1.0, 1.0)
    torch.testing.assert_close(advantage + value, torch.tensor([[6.0], [5.0], [3.0]]))

    # In contrast, an unfinished rollout must still bootstrap its next state.
    advantage = compute_gae(torch.zeros(1, 1), torch.zeros(1, 1), torch.zeros(1, 1),
                            torch.tensor([4.0]), torch.zeros(1), 1.0, .95)
    torch.testing.assert_close(advantage, torch.tensor([[4.0]]))


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
    test_finite_deadline_objective()
    if SPEC.version==1:
        test_progress_nonnegative_and_reset()
    else:
        from terraria_lite.v2_checks import main as v2_checks
        v2_checks()
    print("PPO selftest passed")


if __name__ == "__main__":
    main()
