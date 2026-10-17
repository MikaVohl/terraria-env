"""Fixed sparse achievement weighting, never prerequisite or action shaping.

Evaluation and the C simulator always keep their original rewards. This module
only replaces newly earned achievement rewards at collection time, retaining
death penalties. The subjective tiers are a frozen experimental intervention.
"""
import numpy as np

from terraria_lite import SPEC


DIFFICULTY_TIERS = {
    "collect wood": 1, "collect stone": 1, "place block": 1,
    "craft workbench": 3, "craft furnace": 5, "craft anvil": 5,
    "place torch": 1, "place platform": 1,
    "collect copper": 3, "collect iron": 3, "collect silver": 3, "collect gold": 3,
    "smelt copper": 5, "smelt iron": 5, "smelt silver": 5, "smelt gold": 5,
    "defeat Blue Slime": 1, "defeat Cave Bat": 3, "open chest": 1,
    "craft wooden sword": 3, "craft metal sword": 5,
    "craft wood breastplate": 3, "craft iron chainmail": 8,
    "heal with food or potion": 1, "use life crystal": 1, "double jump": 1,
    "descend deep": 3, "return to surface": 3, "explore 30 columns": 1,
    "climb rope": 1, "craft iron pickaxe": 8, "craft gold pickaxe": 8,
}


def reward_spec(kind):
    if kind == "equal":
        weights = np.ones(SPEC.n_achievements, dtype=np.float64)
        tiers = {name: 1 for name in SPEC.achievement_names}
    elif kind == "difficulty":
        if set(SPEC.achievement_names) != set(DIFFICULTY_TIERS):
            raise ValueError("Difficulty tiers require the exact 32-achievement contract")
        tiers = DIFFICULTY_TIERS.copy()
        weights = np.array([tiers[name] for name in SPEC.achievement_names], dtype=np.float64)
        weights *= len(weights) / weights.sum()
    else:
        raise ValueError(f"Unknown achievement reward scheme: {kind}")
    return {"kind": kind, "raw_tiers": tiers,
            "weights": dict(zip(SPEC.achievement_names, map(float, weights))),
            "normalization": "sum of all achievement rewards equals achievement count",
            "maximum_achievement_reward": float(weights.sum()),
            "death_reward": -1.0, "health_change_reward": 0.0,
            "prerequisite_shaping": False, "evaluation": "original unweighted C rewards"}


class AchievementRewards:
    """Track first unlocks across native vector autoresets using true final obs."""

    def __init__(self, initial_obs, kind):
        spec = reward_spec(kind)
        self.extra = np.array([spec["weights"][name] - 1.0
                               for name in SPEC.achievement_names], dtype=np.float32)
        start = SPEC.cells * (SPEC.tile_kinds + 1) + SPEC.status_ach0
        self.ach = slice(start, start + SPEC.n_achievements)
        self.previous = (initial_obs[:, self.ach] > .5).copy()

    def step(self, rewards, next_obs, final_obs, ended):
        current = (next_obs[:, self.ach] > .5).copy()
        current[ended] = final_obs[ended, self.ach] > .5
        if np.any(self.previous & ~current):
            raise ValueError("Achievement history decreased before an episode boundary")
        earned = current & ~self.previous
        result = np.asarray(rewards, dtype=np.float32) + earned @ self.extra
        self.previous = (next_obs[:, self.ach] > .5).copy()
        return result
