"""Synthetic boundary/reward regression tests; not demonstrations or training."""
import numpy as np
from terraria_lite import SPEC
from terraria_lite.achievement_rewards import AchievementRewards, reward_spec


def main():
    equal, weighted = reward_spec("equal"), reward_spec("difficulty")
    assert all(w == 1 for w in equal["weights"].values())
    assert abs(sum(weighted["weights"].values()) - SPEC.n_achievements) < 1e-12
    assert set(weighted["raw_tiers"].values()) == {1, 3, 5, 8}
    obs = np.zeros((3, SPEC.obs_size), np.float32)
    offset = SPEC.cells * (SPEC.tile_kinds + 1) + SPEC.status_ach0
    ach = lambda name: offset + SPEC.achievement_names.index(name)
    a = AchievementRewards(obs, "difficulty")
    identity = AchievementRewards(obs, "equal")
    obs[0, ach("collect wood")] = 1
    obs[0, ach("collect stone")] = 1
    final = obs.copy()
    # Lane 1 earns a furnace on its terminal tick, dies and autoresets.
    final[1, ach("craft furnace")] = 1
    ended = np.array([False, True, False])
    reward = np.array([2, 0, 0], np.float32)  # terminal +1 achievement and -1 death
    expected = [weighted["weights"]["collect wood"] + weighted["weights"]["collect stone"],
                weighted["weights"]["craft furnace"] - 1, 0]
    np.testing.assert_allclose(a.step(reward, obs, final, ended), expected, atol=1e-6)
    np.testing.assert_array_equal(identity.step(reward, obs, final, ended), reward)
    # Persistent unlocks do not pay twice; fresh lane can earn the same unlock.
    obs[1, ach("craft furnace")] = 1
    expected = np.array([0, weighted["weights"]["craft furnace"], 0], np.float32)
    np.testing.assert_allclose(a.step(np.array([0, 1, 0]), obs, obs, np.zeros(3, bool)), expected)
    # Inherent deadline, simultaneous multiple unlocks, and a retained death penalty.
    final = obs.copy()
    final[2, [ach("craft iron pickaxe"), ach("craft gold pickaxe")]] = 1
    expected = [0, 0, weighted["weights"]["craft iron pickaxe"] + weighted["weights"]["craft gold pickaxe"] - 1]
    np.testing.assert_allclose(a.step(np.array([0, 0, 1]), obs, final, np.array([False, False, True])), expected)
    np.testing.assert_array_equal(a.step(np.array([0, 0, -1]), obs, obs, np.zeros(3, bool)), [0, 0, -1])
    for invalid in ("unknown",):
        try:
            reward_spec(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid reward configuration accepted")
    print("Reward tests passed: fixed normalized tiers, equal identity, first unlocks, multiple unlocks, deaths and autoreset/deadline final observations")


if __name__ == "__main__":
    main()
