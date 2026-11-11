"""Python-side v10 gates: SPEC contract (40 achievements, max 145, status
layout with the physics/mining scalars before the entity block), Python = C
(scalar vs native batch with autoreset, 64-bit masks), determinism and
save/load through the binding, tiered scoring, the boss-chain and v10
lens/altar potential goals and an evaluation smoke run.

    TERRARIA_LITE_LIB=$PWD/perf/v7/build-v10/libterraria.so PYTHONPATH=python \
        .venv/bin/python variants/v10/tests/check_v10.py
"""
import numpy as np
import torch

from terraria_lite import SPEC, TerrariaLite

TIERS = {
    1: ["collect wood", "collect stone", "place block", "place torch", "place platform", "craft workbench",
        "craft wooden sword", "collect copper", "defeat Blue Slime", "open chest", "explore 30 columns",
        "climb rope", "heal with food or potion"],
    2: ["craft furnace", "smelt copper", "collect iron", "smelt iron", "craft anvil", "craft metal sword",
        "craft wood breastplate", "use life crystal", "defeat Zombie", "defeat Demon Eye", "survive a night",
        "reach the caverns"],
    3: ["craft iron pickaxe", "collect silver", "smelt silver", "collect gold", "smelt gold",
        "craft iron chainmail", "defeat Skeleton", "return to surface"],
    4: ["craft gold pickaxe", "collect lens", "find a Demon Altar", "hold 6 lenses",
        "craft Suspicious Looking Eye", "summon the Eye of Cthulhu", "defeat the Eye of Cthulhu"],
}


def check_spec():
    assert SPEC.version == 10, SPEC.version
    assert SPEC.n_achievements == 40 and SPEC.max_weighted_score == 145 and SPEC.n_actions == 86
    for tier, names in TIERS.items():
        for name in names:
            i = SPEC.achievement_names.index(name)
            assert SPEC.achievement_tiers[i] == tier, name
            assert SPEC.achievement_weights[i] == {1: 1, 2: 3, 3: 5, 4: 8}[tier], name
    assert sorted(sum(TIERS.values(), [])) == sorted(SPEC.achievement_names)
    assert "use summon item" in SPEC.action_names and "craft Suspicious Looking Eye" in SPEC.action_names
    for item in ("lens", "Suspicious Looking Eye", "demonite ore", "gold chainmail"):
        assert item in SPEC.item_names, item
    walls = SPEC.wall_channel is not None
    assert "demon altar" in SPEC.tile_names and SPEC.entity_channels == 8 + walls and SPEC.info_width == 5
    assert SPEC.mob_channels == 8 and (not walls or SPEC.wall_channel == 8)
    assert SPEC.default_steps == 10_000 and SPEC.world_h == 128
    assert SPEC.status_entity0 + SPEC.cells * SPEC.entity_channels == SPEC.status_len, (SPEC.status_entity0, SPEC.status_len)


def check_tools_and_walls():
    """EXPLICIT_TOOLS: starter tools in the inventory, held item observed; BG_WALLS:
    the wall channel and the text view's wall glyph (skipped for builds without them)."""
    from terraria_lite.llm_protocol import Session
    from terraria_lite.llm_text import text_observation, WALL_AIR
    if SPEC.status_held0 is not None:
        for item in ("copper pickaxe", "copper axe"):
            assert item in SPEC.item_names, item
        s = Session(23000001, max_steps=50)
        p = s.packet()
        assert p["inventory"]["copper pickaxe"] == 1 and p["inventory"]["copper axe"] == 1 and p["held"] == "copper shortsword", p
        assert "Holding copper shortsword" in text_observation(p, 50, None)
        s.close()
    if SPEC.wall_channel is not None:
        env = TerrariaLite()
        obs, _ = env.reset(seed=23000001)
        status = obs[SPEC.cells * (SPEC.tile_kinds + 1):]
        ent = status[SPEC.status_entity0:].reshape(SPEC.cells, SPEC.entity_channels)
        assert set(np.unique(ent[:, SPEC.wall_channel])) <= {0.0, 1.0}
        # Dig straight down from spawn: the shaft through the dirt band shows walls.
        down = SPEC.action_names.index("mine down"); right = SPEC.action_names.index("mine below right column")
        seen = 0
        for _ in range(60):
            mask = env.action_mask()
            act = down if mask[down] else right if mask[right] else 0
            obs = env.step(act)[0]
            status = obs[SPEC.cells * (SPEC.tile_kinds + 1):]
            seen = max(seen, int(status[SPEC.status_entity0:].reshape(SPEC.cells, SPEC.entity_channels)[:, SPEC.wall_channel].sum()))
        assert seen > 0, "no wall seen while digging down"
        env.close()
        s = Session(23000001, max_steps=200)
        down_id = SPEC.action_names.index("mine down")
        for _ in range(40):
            s.act({"action": down_id if down_id in s.packet()["legal_actions"] else 0})
        p = s.packet()
        assert "walls" in p and any(any(r) for r in p["walls"]), "packet walls"
        assert WALL_AIR in text_observation(p, 200, None).split("dx:")[1], "wall glyph in the text view"
        s.close()


def check_determinism_and_snapshots():
    rng = np.random.default_rng(1)
    a, b = TerrariaLite(), TerrariaLite()
    a.reset(seed=42); b.reset(seed=42)
    for t in range(6000):
        act = int(rng.choice(np.flatnonzero(a.action_mask())))
        ra, rb = a.step(act), b.step(act)
        np.testing.assert_array_equal(ra[0], rb[0]); assert ra[1:] == rb[1:]
        if ra[2] or ra[3]:
            a.reset(seed=1000 + t); b.reset(seed=1000 + t)
    assert a.save_state() == b.save_state(), "same seed + actions, different state bytes"
    c = TerrariaLite(); c.reset(seed=7)
    c.load_state(a.save_state())
    for _ in range(3000):
        act = int(rng.choice(np.flatnonzero(a.action_mask())))
        ra, rc = a.step(act), c.step(act)
        np.testing.assert_array_equal(ra[0], rc[0]); assert ra[1:] == rc[1:]
        if ra[2] or ra[3]:
            break
    assert a.save_state() == c.save_state()


def check_native_autoreset():
    """VecTerraria: Python reset loop == native C autoreset (obs, masks, infos)."""
    from terraria_lite.ppo_agent import VecTerraria
    n = 16
    x = VecTerraria(n, seed=500, max_steps=400)
    y = VecTerraria(n, seed=500, max_steps=400, native_autoreset=True)
    x.reset(); y.reset()
    rng = np.random.default_rng(3); episodes = 0
    for _ in range(2500):
        actions = np.where(x.mask, rng.random(x.mask.shape), -1).argmax(1)
        left, right = x.step(actions), y.step(actions)
        for i in range(6):
            np.testing.assert_array_equal(left[i], right[i])
        assert [(i, {k: v for k, v in d.items()}) for i, d in left[6]] == right[6]
        episodes += len(left[6])
    x.close(); y.close()
    assert episodes > 50, episodes


def check_scoring():
    from terraria_lite.scoring import score_masks
    full = (1 << SPEC.n_achievements) - 1
    tier1 = sum(1 << SPEC.achievement_names.index(n) for n in TIERS[1])
    boss = 1 << SPEC.achievement_names.index("defeat the Eye of Cthulhu")
    s = score_masks([full, tier1, 0, boss])
    assert abs(s["weighted_score"] - 100 * (145 + 13 + 0 + 8) / (4 * 145)) < 1e-9, s
    assert s["tier_rates"]["1"] == 0.5 and s["tier_rates"]["4"] == (7 + 1) / (4 * 7)
    assert s["furthest_tier"] == {"0": 1, "1": 1, "2": 0, "3": 0, "4": 2}


def check_boss_potential():
    """Boss-chain goals: eye at night > eye by day > no eye; damage dealt raises phi."""
    from terraria_lite.potential import RecipePotential
    env = TerrariaLite(); obs, _ = env.reset(seed=3); env.close()
    s0 = SPEC.cells * (SPEC.tile_kinds + 1)
    eye = s0 + SPEC.status_inv0 + SPEC.item_names.index("Suspicious Looking Eye")
    night, boss = s0 + SPEC.status_night, s0 + SPEC.status_boss
    summoned = s0 + SPEC.status_ach0 + SPEC.achievement_names.index("summon the Eye of Cthulhu")
    rows = np.repeat(obs[None], 6, 0)
    rows[1:, eye] = np.sqrt(1 / SPEC.inventory_clip)
    rows[2:, night] = 1
    rows[3:, summoned] = 1; rows[3:, eye] = 0
    rows[4:, boss] = 1; rows[4, boss + 1] = 1.0; rows[5, boss + 1] = 0.25
    for mode in ("frontier", "frontier_surface"):
        phi = RecipePotential(rows, .9999, 1.0, mode).phi(rows)
        assert phi[0] < phi[1] < phi[2], (mode, phi)
        assert phi[4] < phi[5], (mode, phi)


def check_v10_potential():
    """v10 goals: more lenses raise phi; while "find a Demon Altar" is open (and
    the caverns not yet reached) a deeper row raises phi, and once it is earned
    depth no longer matters in "frontier" mode."""
    from terraria_lite.potential import RecipePotential
    env = TerrariaLite(); obs, _ = env.reset(seed=3); env.close()
    s0 = SPEC.cells * (SPEC.tile_kinds + 1)
    lens = s0 + SPEC.status_inv0 + SPEC.item_names.index("lens")
    depth = s0 + SPEC.status_depth
    found = s0 + SPEC.status_ach0 + SPEC.achievement_names.index("find a Demon Altar")
    surface, deep = SPEC.surface_base / (SPEC.world_h - 1), (SPEC.deep_row - 1) / (SPEC.world_h - 1)
    rows = np.repeat(obs[None], 7, 0)
    rows[0:3, lens] = np.sqrt(np.array([0, 3, 6]) / SPEC.inventory_clip)
    rows[3, depth] = surface; rows[4, depth] = deep
    rows[5:, found] = 1; rows[5, depth] = surface; rows[6, depth] = deep
    for mode in ("frontier", "frontier_surface"):
        p = RecipePotential(rows, .9999, 1.0, mode)
        assert p.lens and p.altar, mode
        phi = p.phi(rows)
        assert phi[0] < phi[1] < phi[2], (mode, phi)
        assert phi[3] < phi[4], (mode, phi)
        if mode == "frontier":
            assert phi[5] == phi[6], (mode, phi)


def check_evaluation():
    from terraria_lite.ppo_eval import evaluate
    from terraria_lite.spatial_agent import build_agent
    torch.manual_seed(0)
    agent = build_agent("targets")
    r = evaluate(agent, list(range(2_000_001, 2_000_009)), num_envs=8, max_steps=300)
    for key in ("weighted_score", "tier_rates", "crafter_score", "mean_achievements", "hits"):
        assert key in r, key


def main():
    torch.set_num_threads(4)
    for check in (check_spec, check_tools_and_walls, check_determinism_and_snapshots, check_native_autoreset, check_scoring,
                  check_boss_potential, check_v10_potential, check_evaluation):
        check()
        print("ok", check.__name__, flush=True)
    print(f"v10 Python checks passed ({SPEC})")


if __name__ == "__main__":
    main()
