"""Scoring reconstructed from public result JSON and chart-manifest facts.

This catalogue is sufficient to reproduce every published positive score, not
proof that the complete private upstream milestone catalogue is reproduced.
"""
import json
from pathlib import Path

# Only wood levels were observed in positively scored published runs.
# Remaining levels are explicit inferences from the public five-stage grouping.
REFERENCE_LEVELS = {
    "wood_1": 1, "wood_10": 1, "wood_25": 2, "wood_100": 2,
    "workbench_1": 2, "torch_10": 2, "furnace_1": 2,
    "early_bar_5": 3, "max_life_160": 3, "biome_jungle": 3,
    "boss_eye_of_cthulhu_defeated": 4, "biome_underworld": 5,
    "boss_wall_of_flesh_defeated": 5,
}
DIAGNOSTICS = {
    "held_weapon", "held_axe", "held_pickaxe", "inventory_opened",
    "hardmode_unlocked", "death", "survival", "distance", "descent",
}
LEVEL_LABELS = {1: "Starter resources", 2: "Basic crafting", 3: "Underground self-sufficiency",
                4: "Pre-hardmode bosses", 5: "Underworld and Wall of Flesh"}


def reference_score(events, *, actions=None, direct_tile_control=False, stalled=False):
    events = list(events)
    actions = list(actions) if actions is not None else None
    inherited = {m for e in events if e.get("event") == "start" for m in e.get("baseline", [])}
    firsts, ignored, unknown = {}, [], []
    for event in events:
        milestone = event.get("milestone")
        if not milestone:
            continue
        if milestone not in REFERENCE_LEVELS:
            (ignored if milestone in DIAGNOSTICS or event.get("category") == "non_scoring" else unknown).append(milestone)
            continue
        backed = event.get("agent_driven") is True
        if actions is not None:
            stamp = event.get("unix_seconds")
            # A conservative reconstruction: an agent input must precede the
            # newly acquired fact. It is not proof that the input caused it.
            backed = stamp is not None and any(
                a.get("actor") == "agent" and a.get("started_unix", float("inf")) <= stamp
                for a in actions
            )
        if backed and milestone not in inherited and event.get("category", "progress") == "progress":
            firsts.setdefault(milestone, event)
    valid = not direct_tile_control
    scored = firsts if valid else {}
    return {
        "score_name": "agent_driven_progress_checkpoints_public_subset",
        "agency_score": len(scored),
        "checkpoint_count": len(scored),
        "furthest_level": max((REFERENCE_LEVELS[m] for m in scored), default=0),
        "level_counts": {str(level): sum(REFERENCE_LEVELS[m] == level for m in scored) for level in range(1, 6)},
        "level_labels": {str(k): v for k, v in LEVEL_LABELS.items()},
        "milestones": list(scored),
        "first_unlocks": {m: {k: e[k] for k in ("elapsed_seconds", "game_updates", "timestamp_utc") if k in e} for m, e in scored.items()},
        "diagnostics_not_scored": sorted(set(ignored)),
        "unknown_milestones_not_scored": sorted(set(unknown)),
        "direct_tile_control_used": direct_tile_control,
        "valid_for_scoring": valid,
        "valid_for_long_horizon": valid and not stalled,
        "stalled": stalled,
        "catalog_coverage": "public_chart_manifest_plus_observed_wood_thresholds",
        "complete_upstream_catalog_verified": False,
        "exact_reference_reproduction": False,
        "official_eligible": False,
    }


def score_published_result(result):
    metrics = result["score_metrics"]
    return reference_score(metrics.get("scoring_checkpoints", []),
                           direct_tile_control=metrics.get("direct_tile_control_used", False),
                           stalled=metrics.get("stalled", False))


def load_reference_events(folder):
    paths = list(Path(folder).glob("*.jsonl"))
    if len(paths) != 1:
        raise ValueError("expected one reference world session")
    return [json.loads(line) for line in paths[0].read_text().splitlines()]


def checkpoint_view(events):
    """Match agent-readable checkpoint capability; never expose heartbeat state."""
    return [{k: e[k] for k in ("event", "task", "milestone", "category", "elapsed_seconds", "game_updates") if k in e}
            for e in events if e.get("event") in ("start", "checkpoint", "end")][-80:]
