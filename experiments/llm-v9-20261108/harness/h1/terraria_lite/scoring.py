"""Tiered benchmark score (v9, docs/ENV_V9_DESIGN.md sections 8-9).

The headline is the mean over episodes of the unlocked achievements' tier
weights (1/3/5/8) as a percentage of the maximum (129 for v9). Reported next
to it: per-tier success rates (mean fraction of that tier's achievements
unlocked per episode), the Crafter geometric score over per-achievement
success rates and the furthest tier reached. Evaluation only: training reward
stays whatever the trainer uses. Libraries without tiers (v7/v8) return {}.
"""
from __future__ import annotations

import numpy as np

from terraria_lite import SPEC


def score_masks(masks) -> dict:
    """Score a list of per-episode achievement bitmasks; {} without tiers."""
    if SPEC.achievement_weights is None or not len(masks):
        return {}
    n = SPEC.n_achievements
    bits = np.array([[(int(m) >> i) & 1 for i in range(n)] for m in masks], dtype=np.float64)
    weights = np.asarray(SPEC.achievement_weights, dtype=np.float64)
    tiers = np.asarray(SPEC.achievement_tiers)
    scores = 100.0 * bits @ weights / SPEC.max_weighted_score
    rates = bits.mean(0)
    reached = np.where(bits.any(1), (bits * tiers).max(1), 0).astype(int)
    return {
        "weighted_score": float(scores.mean()),
        "weighted_score_std": float(scores.std()),
        "max_weighted_score": int(SPEC.max_weighted_score),
        "tier_rates": {str(t): float(bits[:, tiers == t].mean()) for t in sorted(set(tiers.tolist()))},
        "crafter_score": float(np.exp(np.mean(np.log(1.0 + 100.0 * rates))) - 1.0),
        "furthest_tier": {str(t): int((reached == t).sum()) for t in range(int(tiers.max()) + 1)},
    }
