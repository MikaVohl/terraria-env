"""Versioned symbolic interface: public rules and exactly the RL information."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import numpy as np
from terraria_lite import SPEC, TerrariaLite
from terraria_lite.rules import player_knowledge

PROTOCOL = "terraria-symbolic-v2"
PROTECTED = ((3000001, 256), (7000001, 128), (9000001, 128), (11000001, 128),
             (15000001, 128), (17000001, 128), (19000001, 128))
STATUS_NAMES = ("health_fraction", "mining_tier_fraction", "facing_right", "jump_fraction",
                "fall_fraction", "depth_fraction", "horizontal_fraction", "elapsed_fraction",
                "max_health_fraction", "weapon_fraction", "armor_fraction", "attack_cooldown",
                "heal_cooldown", "hurt_cooldown", "air_jump_used", "mine_cooldown", "safe_time")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_seed(seed):
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("Seed must be an unsigned 64-bit integer, not a bool")
    if any(lo <= seed < lo+n for lo, n in PROTECTED):
        raise ValueError("Protected PPO test/study world; use a dedicated LLM development world")


def tile_legend(environment_root=None):
    root = Path(environment_root or Path(__file__).resolve().parents[2])
    header = (root / "include/tiles.h").read_text()
    table = header.split("TILE_INFO[TILE_COUNT] = {", 1)[1].split("\n};", 1)[0]
    names = re.findall(r'\{"([^"]+)"', table)
    if len(names) != SPEC.tile_kinds-1:
        raise ValueError("Tile legend does not match the loaded library")
    return names + ["unknown (unlit)"]


class Session:
    def __init__(self, seed, max_steps=3000, environment_root=None):
        validate_seed(seed)
        if type(max_steps) is not int or not 1 <= max_steps <= 3000:
            raise ValueError("Primitive action budget must be an integer in 1..3000")
        self.seed, self.max_steps = seed, max_steps
        self.environment_root = environment_root
        self.env = TerrariaLite(max_steps=max_steps)
        self.obs, self.info = self.env.reset(seed=seed)
        self.terminated = self.truncated = self.ended = False
        self.invalid_requests = self.illegal_attempts = 0

    def packet(self):
        n = SPEC.cells * SPEC.tile_kinds
        status = self.obs[n+SPEC.cells:]
        entities = status[SPEC.status_entity0:].reshape(SPEC.cells, 4)
        # Native inventory encoding is sqrt(count/999), NOT count/999.
        inventory = {name: int(round(float(status[SPEC.status_inv0+i])**2 * SPEC.inventory_clip))
                     for i, name in enumerate(SPEC.item_names)}
        return {"environment_version": SPEC.version, "steps": self.info["steps"],
                "score": self.info["achievements"], "terminated": self.terminated, "truncated": self.truncated,
                "tiles": self.obs[:n].reshape(SPEC.cells, SPEC.tile_kinds).argmax(-1).reshape(SPEC.view_h, SPEC.view_w).tolist(),
                "light": np.rint(self.obs[n:n+SPEC.cells]*15).astype(int).reshape(SPEC.view_h, SPEC.view_w).tolist(),
                "status": status[:SPEC.status_entity0].tolist(),
                "scalars": dict(zip(STATUS_NAMES, map(float, status[:len(STATUS_NAMES)]))),
                "inventory": inventory,
                "achievements": [name for i, name in enumerate(SPEC.achievement_names) if status[SPEC.status_ach0+i] > .5],
                "visible_entities": [{"cell": i, "features": x.tolist()} for i, x in enumerate(entities) if x.any()],
                "legal_actions": np.flatnonzero(self.env.action_mask()).tolist(),
                "invalid_requests": self.invalid_requests, "illegal_attempts": self.illegal_attempts}

    def knowledge(self):
        return {"protocol": PROTOCOL, "rules": player_knowledge(), "tile_names": tile_legend(self.environment_root),
                "view_anchor": {"row": SPEC.view_h//2, "column": SPEC.view_w//2, "meaning": "player left-feet cell"},
                "reach_actions": [{"mine_action": SPEC.mine_first+i, "place_action": SPEC.place_first+i, "dx": dx, "dy": dy}
                                  for i, (dx, dy) in enumerate(SPEC.reach_offsets)],
                "status_schema": {"scalars": STATUS_NAMES, "inventory_encoding": "sqrt(count/999)",
                                  "selected_placeable_one_hot": [17, SPEC.status_inv0],
                                  "selected_placeable_order": ["stone", "dirt", "wood", "torch", "campfire", "workbench", "furnace", "anvil", "platform", "rope"],
                                  "inventory_offset": SPEC.status_inv0, "achievement_offset": SPEC.status_ach0,
                                  "entity_features": ["blue_slime_presence", "cave_bat_presence", "health", "movement_phase"]},
                "tool_rules": "Independent iron/gold pick ownership; duplicates consume ingredients; strongest mining tier used automatically" if SPEC.version >= 6 else "Legacy tier ownership; crafting lower tiers after higher tiers is blocked",
                "action_budget": self.max_steps,
                "clock": "One tick per primitive action, no ticks during model thinking. No reset or undo.",
                "legality": "Masks are not strategy advice. Hidden-terrain attempts may fail; illegal actions still consume a tick."}

    def act(self, request):
        if self.ended:
            raise ValueError("Episode already ended; no reset inside a scored session")
        action = request.get("action") if isinstance(request, dict) else None
        if isinstance(action, str):
            action = SPEC.action_names.index(action) if action in SPEC.action_names else None
        invalid = type(action) is not int or not 0 <= action < SPEC.n_actions
        if invalid:
            self.invalid_requests += 1
            action = 0
        elif not self.env.action_mask()[action]:
            self.illegal_attempts += 1
        self.obs, reward, self.terminated, self.truncated, self.info = self.env.step(action)
        self.ended = self.terminated or self.truncated
        return {**self.packet(), "reward": reward, "invalid_request": invalid, "executed_action": action}

    def close(self):
        self.env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=9)
    parser.add_argument("--max-steps", type=int, default=3000)
    parser.add_argument("--environment-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    session = Session(args.seed, args.max_steps, args.environment_root)
    log = None
    try:
        if args.out:
            log = args.out.open("x")
        def emit(value):
            line = canonical(value)
            if log:
                log.write(line + "\n"); log.flush()
            print(line, flush=True)
        emit({**session.knowledge(), "observation": session.packet(), "response_schema": {"action": "one ID or exact action name"}})
        for line in sys.stdin:
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                request = None
            emit(session.act(request))
            if session.ended:
                break
    finally:
        session.close()
        if log:
            log.close()
