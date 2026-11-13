"""v10 transfer PoC, policy side (Mac, CPU torch): the Terraria-Lite v10 PPO policy plays real Terraria.

    TERRARIA_LITE_LIB=/tmp/v10poc/libv10bridge.dylib PYTHONPATH=python .venv/bin/python \
        TerrariaBench/tools/v10_transfer/policy_driver.py --checkpoint step-1073741824.pt --steps 1500 \
        --run v10-poc-01 --log /tmp/v10poc/run.jsonl

The Omarchy game server (game_server.py, over ssh) returns the real game state after every step; this side maps
it to v10 sim kinds, builds a synthetic v10 Env through libv10bridge (the simulator's own env_obs and
env_action_mask), samples one masked action and sends it back as 15 ticks of inputs (+ declared shortcuts).
"""
import argparse
import collections
import ctypes
import json
import os
import subprocess
import time

import numpy as np
import torch

from terraria_lite.ppo_eval import load_agent
from terraria_lite.rules import SPEC

T = {n: i for i, n in enumerate(SPEC.tile_names)}
I = {n: i for i, n in enumerate(SPEC.item_names)}
A = {n: i for i, n in enumerate(SPEC.action_names)}
ACH = {n: i for i, n in enumerate(SPEC.achievement_names)}
UNKNOWN = SPEC.unknown_tile

# ---- real TileID -> sim tile kind ---------------------------------------------------------------------------
TILE_MAP = {0: "dirt", 1: "stone", 2: "grass", 4: "torch", 5: "log", 6: "iron ore", 7: "copper ore", 8: "gold ore",
            9: "silver ore", 12: "life crystal", 16: "anvil", 17: "furnace", 18: "workbench", 19: "wood platform",
            21: "chest", 467: "chest", 23: "grass", 25: "stone", 26: "demon altar", 30: "wood", 40: "dirt", 53: "dirt",
            56: "stone", 57: "dirt", 59: "dirt", 60: "grass", 70: "grass", 109: "grass", 199: "grass", 477: "grass",
            72: "log", 323: "log", 117: "stone", 123: "dirt", 147: "dirt", 161: "stone", 166: "copper ore",
            167: "iron ore", 168: "silver ore", 169: "gold ore", 203: "stone", 213: "rope", 214: "rope", 353: "rope",
            365: "rope", 366: "rope", 215: "campfire", 224: "dirt", 367: "stone", 368: "stone", 396: "stone",
            397: "stone", 22: "stone", 204: "stone", 58: "stone", 63: "stone", 64: "stone", 65: "stone", 66: "stone",
            67: "stone", 68: "stone", 157: "wood", 158: "wood", 159: "wood", 190: "wood", 208: "wood", 151: "stone",
            38: "stone", 39: "stone", 41: "stone", 43: "stone", 44: "stone", 179: "stone", 180: "stone", 181: "stone",
            182: "stone", 183: "stone", 381: "stone", 534: "stone", 536: "stone", 539: "stone"}
TILE_MAP = {k: T[v] for k, v in TILE_MAP.items()}
TREE_TILES = {5, 72, 323}

# ---- real item name -> sim item -------------------------------------------------------------------------------
ITEM_NAMES = {
    "wood": ["Wood", "Boreal Wood", "Palm Wood", "Rich Mahogany", "Ebonwood", "Shadewood", "Pearlwood"],
    "stone": ["Stone Block", "Ebonstone Block", "Crimstone Block", "Granite Block", "Marble Block", "Sandstone Block"],
    "dirt": ["Dirt Block", "Clay Block", "Sand Block", "Mud Block", "Silt Block", "Snow Block", "Ash Block",
             "Slush Block"],
    "copper ore": ["Copper Ore", "Tin Ore"], "iron ore": ["Iron Ore", "Lead Ore"], "gold ore": ["Gold Ore", "Platinum Ore"],
    "silver ore": ["Silver Ore", "Tungsten Ore"],
    "copper bar": ["Copper Bar", "Tin Bar"], "iron bar": ["Iron Bar", "Lead Bar"], "gold bar": ["Gold Bar", "Platinum Bar"],
    "silver bar": ["Silver Bar", "Tungsten Bar"],
    "torch": ["Torch"], "campfire": ["Campfire"], "workbench": ["Work Bench"], "furnace": ["Furnace"],
    "anvil": ["Iron Anvil", "Lead Anvil"], "gel": ["Gel"], "wood platform": ["Wood Platform"], "rope": ["Rope"],
    "mushroom": ["Mushroom"], "lesser healing potion": ["Lesser Healing Potion"], "life crystal": ["Life Crystal"],
    "Cloud in a Bottle": ["Cloud in a Bottle"], "copper shortsword": ["Copper Shortsword"],
    "wooden sword": ["Wooden Sword"], "copper broadsword": ["Copper Broadsword", "Tin Broadsword"],
    "iron broadsword": ["Iron Broadsword", "Lead Broadsword"], "gold broadsword": ["Gold Broadsword", "Platinum Broadsword"],
    "silver broadsword": ["Silver Broadsword", "Tungsten Broadsword"], "wood breastplate": ["Wood Breastplate"],
    "iron chainmail": ["Iron Chainmail", "Lead Chainmail"], "iron pickaxe": ["Iron Pickaxe", "Lead Pickaxe"],
    "gold pickaxe": ["Gold Pickaxe", "Platinum Pickaxe"], "gold chainmail": ["Gold Chainmail", "Platinum Chainmail"],
    "lens": ["Lens"], "Suspicious Looking Eye": ["Suspicious Looking Eye"], "demonite ore": ["Demonite Ore", "Crimtane Ore"],
}
REAL_TO_SIM = {real: I[sim] for sim, reals in ITEM_NAMES.items() for real in reals}
for real in ("Torch",):
    REAL_TO_SIM[real] = I["torch"]
PLACEABLE_ITEMS = ["stone", "dirt", "wood", "torch", "campfire", "workbench", "furnace", "anvil", "wood platform", "rope"]
WEAPONS = ["copper shortsword", "wooden sword", "copper broadsword", "iron broadsword", "silver broadsword",
           "gold broadsword"]
ARMOR = {"Wood Breastplate": 1, "Iron Chainmail": 2, "Lead Chainmail": 2, "Gold Chainmail": 3, "Platinum Chainmail": 3}
PICK_TIER = {"Copper Pickaxe": 1, "Tin Pickaxe": 1, "Iron Pickaxe": 2, "Lead Pickaxe": 2, "Silver Pickaxe": 2,
             "Tungsten Pickaxe": 2, "Gold Pickaxe": 3, "Platinum Pickaxe": 3}
CRAFT = {"craft workbench": "workbench", "craft furnace": "furnace", "craft torch": "torch",
         "craft campfire": "campfire", "craft platforms": "wood platform", "smelt copper": "copper bar",
         "smelt iron": "iron bar", "smelt silver": "silver bar", "smelt gold": "gold bar",
         "craft anvil": "anvil", "craft iron pickaxe": "iron pickaxe", "craft gold pickaxe": "gold pickaxe",
         "craft wooden sword": "wooden sword", "craft copper sword": "copper broadsword",
         "craft iron sword": "iron broadsword", "craft silver sword": "silver broadsword",
         "craft gold sword": "gold broadsword", "craft wood breastplate": "wood breastplate",
         "craft iron chainmail": "iron chainmail", "craft gold chainmail": "gold chainmail",
         "craft Suspicious Looking Eye": "Suspicious Looking Eye"}


def mob_kind(n):
    """Real NPC -> sim mob kind (1 slime, 2 bat, 3 zombie, 4 demon eye, 5 skeleton), 0 unmapped."""
    name, ai = n["name"], n["ai"]
    if ai == 1 or "Slime" in name:
        return 1
    if ai == 14 or "Bat" in name:
        return 2
    if "Skeleton" in name:
        return 5
    if ai == 3:
        return 3
    if ai in (2, 5) or "Eye" in name:
        return 4
    return 0


class Bridge:
    def __init__(self, lib):
        self.L = ctypes.CDLL(lib)
        self.L.br_new.restype = ctypes.c_void_p
        for f in ("br_set", "br_obs", "br_mask"):
            getattr(self.L, f).argtypes = None
        self.env = ctypes.c_void_p(self.L.br_new())
        self.n_scalar = self.L.br_scalar_count()
        self.flat = np.zeros(self.L.br_flat_size(), np.float32)
        self.mask = np.zeros(self.L.br_action_count(), np.uint8)
        assert self.flat.size == SPEC.obs_size and self.mask.size == SPEC.n_actions

    def encode(self, s, tiles, light, inv, mobs):
        P = lambda a, t: a.ctypes.data_as(ctypes.POINTER(t))  # noqa: E731
        s = np.ascontiguousarray(s, np.int32)
        tiles, light = np.ascontiguousarray(tiles, np.uint8), np.ascontiguousarray(light, np.uint8)
        inv = np.ascontiguousarray(inv, np.int32)
        mobs = np.ascontiguousarray(mobs if len(mobs) else np.zeros((0, 4)), np.int32)
        self.L.br_set(self.env, P(s, ctypes.c_int), P(tiles, ctypes.c_uint8), P(light, ctypes.c_uint8),
                      P(inv, ctypes.c_int), P(mobs, ctypes.c_int), ctypes.c_int(len(mobs)))
        self.L.br_obs(self.env, P(self.flat, ctypes.c_float))
        self.L.br_mask(self.env, P(self.mask, ctypes.c_uint8))
        return self.flat.copy(), self.mask.astype(bool)


class Mapper:
    """Real state -> sim state; keeps the sim-only bookkeeping (selected placeable, weapon, achievements)."""

    def __init__(self):
        self.selected, self.weapon, self.ach = 0, 0, 0
        self.unmapped_tiles, self.unmapped_mobs = collections.Counter(), collections.Counter()
        self.liquid_cells = 0
        self.col_min = self.col_max = None
        self.was_night = False
        self.was_caverns = False
        self.near_mobs = {}
        self.steps = 0
        self.last_dig = None
        self.safe = 0  # steps since the player last lost life (sim safe_ticks, drives the regen observation)

    def award(self, name):
        self.ach |= 1 << ACH[name]

    def inventory(self, st):
        inv = np.zeros(SPEC.n_items, np.int64)
        for e in st["inv"]:
            if e["name"] in REAL_TO_SIM:
                inv[REAL_TO_SIM[e["name"]]] += e["n"]
        return inv

    def build(self, st):
        p, w, g = st["player"], st["world"], st["grid"]
        # Sim body: 2x3 cells, px = left column, py = feet row; the 20x42 px hitbox stands centred in it.
        px_r = int((p["x"] + 2) // 16)
        py_r = int((p["y"] + p["h"] - 1) // 16)
        surface, rock = w["surface"], w["rock"]
        if py_r <= surface:
            layer = 0
            py = int(np.clip(30 + (py_r - w["spawn"][1]), 22, 38))
            sim_surface = py
        elif py_r < rock:
            layer = 1
            py = int(39 + (py_r - surface) * (63 - 39) / max(1, rock - surface))
            sim_surface = 30
        else:
            layer = 2
            py = int(min(64 + (py_r - rock) / 4, 120))
            sim_surface = 30
        px = int(np.clip(64 + (px_r - w["spawn"][0]), 20, 107))
        ox, oy = px - px_r, py - py_r
        typ = np.asarray(g["type"]).reshape(g["h"], g["w"])
        frame = np.asarray(g["frame"]).reshape(g["h"], g["w"])
        solid = np.asarray(g["solid"]).reshape(g["h"], g["w"])
        liquid = np.asarray(g["liquid"]).reshape(g["h"], g["w"])
        tiles = np.zeros(typ.shape, np.uint8)
        for (r, c), t in np.ndenumerate(typ):
            if t < 0:
                tiles[r, c] = T["bedrock"] if t == -2 else T["air"]
            elif t == 3 and frame[r, c] == 144:
                tiles[r, c] = T["mushroom"]
            elif t in TREE_TILES:
                # Sim trees are single-column trunks: roots and branches (no tree tile above or below) become air.
                trunk = (r > 0 and typ[r - 1, c] == t) or (r + 1 < typ.shape[0] and typ[r + 1, c] == t)
                tiles[r, c] = T["log"] if trunk else T["air"]
            elif t in TILE_MAP:
                tiles[r, c] = TILE_MAP[t]
            else:
                tiles[r, c] = T["stone"] if solid[r, c] else T["air"]
                self.unmapped_tiles[(int(t), "stone" if solid[r, c] else "air")] += 1
        self.liquid_cells += int(((liquid > 0) & (typ < 0)).sum())
        light = np.rint(np.asarray(g["light"]).reshape(g["h"], g["w"]) * 15 / 255).astype(np.uint8)
        inv = self.inventory(st)
        owned = [i for i, n in enumerate(WEAPONS) if inv[I[n]] > 0]
        if self.weapon not in owned and owned:
            self.weapon = owned[0]
        tier = max([PICK_TIER.get(e["name"], 0) for e in st["inv"]] + [0])
        armor = ARMOR.get(p["body_armor"], 0)
        # Mobs and the boss.
        mobs, boss = [], [0, 0, 0, 0, 0]
        for n in st["npcs"]:
            cx, cy = int(n["x"] // 16) + ox, int(n["y"] // 16) + oy
            if n["type"] == 4:  # Eye of Cthulhu
                boss = [1, cx - 1, cy - 1, int(1000 * n["life"] / max(1, n["life_max"])), 0]
                continue
            k = mob_kind(n)
            if not k:
                self.unmapped_mobs[n["name"]] += 1
                continue
            mobs.append([k, cx, cy, int(1000 * n["life"] / max(1, n["life_max"]))])
        mobs = mobs[:12]
        # Day/night: sim cycle 1800 day + 1200 night steps, dawn = 0; real day 54000 ticks, night 32400.
        phase = int(w["time"] / 54000 * 1800) if w["day"] else 1800 + int(w["time"] / 32400 * 1200)
        steps = phase + 3000 * max(0, round((self.steps - phase) / 3000))
        fall = max(0, py_r - p["fall_start"]) if p["vy"] > 0 else 0
        dig = [-1, -1, 0]
        if self.last_dig:
            tx, ty = self.last_dig
            dig = [tx + ox, ty + oy, next((d for x, y, d in p["hits"] if (x, y) == (tx, ty)), 0)]
        s = np.zeros(39, np.int64)
        s[:] = [px, py, steps, SPEC.default_steps, max(0, p["life"]), p["life_max"], tier, self.weapon, armor,
                p["anim"], p["anim_max"], p["immune"], p["potion_delay"] // 15, 1 if p["dir"] > 0 else -1, p["jump"], 0,
                fall, int((p["x"] + ox * 16) * 65536), int((p["y"] + oy * 16) * 65536), int(p["vx"] * 65536),
                int(p["vy"] * 65536), self.selected, sim_surface, g["x0"] + ox, g["y0"] + oy, g["w"], g["h"],
                self.ach & 0xffffffff, self.ach >> 32, *boss, p["item_time"], *dig, self.safe]
        info = {"px_r": px_r, "py_r": py_r, "px": px, "py": py, "layer": layer, "inv": inv, "tiles": tiles,
                "typ": typ, "ox": ox, "oy": oy, "night": not w["day"], "mobs": mobs}
        return s, tiles, light, inv, np.asarray(mobs, np.int64).reshape(-1, 4), info

    def update_achievements(self, prev, st, info, action, results):
        inv, pinv = info["inv"], prev["inv"] if prev else None
        for item, ach in (("wood", "collect wood"), ("stone", "collect stone"), ("copper ore", "collect copper"),
                          ("iron ore", "collect iron"), ("silver ore", "collect silver"), ("gold ore", "collect gold"),
                          ("lens", "collect lens")):
            if inv[I[item]] > 0:
                self.award(ach)
        if inv[I["lens"]] >= 6:
            self.award("hold 6 lenses")
        name = SPEC.action_names[action]
        ok = [r for r in results if r.get("ok")]
        if name.startswith("place") and pinv is not None:
            item = PLACEABLE_ITEMS[self.selected]
            if inv[I[item]] < pinv[I[item]]:
                self.award({"torch": "place torch", "wood platform": "place platform"}.get(item, "place block"))
        crafted = {r["name"] for r in ok if r["op"] == "craft"}
        for real, ach in (("Work Bench", "craft workbench"), ("Wooden Sword", "craft wooden sword"),
                          ("Furnace", "craft furnace"), ("Copper Bar", "smelt copper"), ("Tin Bar", "smelt copper"),
                          ("Iron Bar", "smelt iron"), ("Lead Bar", "smelt iron"), ("Silver Bar", "smelt silver"),
                          ("Tungsten Bar", "smelt silver"), ("Gold Bar", "smelt gold"), ("Platinum Bar", "smelt gold"),
                          ("Iron Anvil", "craft anvil"), ("Lead Anvil", "craft anvil"), ("Wood Breastplate", "craft wood breastplate"),
                          ("Iron Chainmail", "craft iron chainmail"), ("Lead Chainmail", "craft iron chainmail"),
                          ("Iron Pickaxe", "craft iron pickaxe"), ("Lead Pickaxe", "craft iron pickaxe"),
                          ("Gold Pickaxe", "craft gold pickaxe"), ("Platinum Pickaxe", "craft gold pickaxe"),
                          ("Suspicious Looking Eye", "craft Suspicious Looking Eye")):
            if real in crafted:
                self.award(ach)
        if any("Broadsword" in c for c in crafted):
            self.award("craft metal sword")
        if any(r["op"] == "loot" for r in ok):
            self.award("open chest")
        if self.col_min is None:
            self.col_min = self.col_max = info["px_r"]
        self.col_min, self.col_max = min(self.col_min, info["px_r"]), max(self.col_max, info["px_r"])
        if self.col_max - self.col_min >= 30:
            self.award("explore 30 columns")
        if st["player"]["pulley"] and name.startswith("climb"):
            self.award("climb rope")
        if prev and name in ("drink healing potion", "eat mushroom") and st["player"]["life"] > prev["life"]:
            self.award("heal with food or potion")
        self.safe = 0 if st["player"]["life"] < prev["life"] or st["player"]["dead"] else self.safe + 1
        if prev and st["player"]["life_max_base"] > prev["life_max_base"]:
            self.award("use life crystal")
        if info["layer"] == 2:
            self.award("reach the caverns")
            self.was_caverns = True
        if self.was_caverns and info["layer"] == 0:
            self.award("return to surface")
        if self.was_night and not info["night"] and not st["player"]["dead"]:
            self.award("survive a night")
        self.was_night = info["night"]
        if (info["typ"] == 26).any():
            self.award("find a Demon Altar")
        if any(n["type"] == 4 for n in st["npcs"]):
            self.award("summon the Eye of Cthulhu")
        if st["world"]["eoc_down"]:
            self.award("defeat the Eye of Cthulhu")
        # Kills (approximate): a mapped hostile within 4 tiles last step that is gone now.
        pcx, pcy = st["player"]["x"] + 10, st["player"]["y"] + 21
        now = {n["id"]: n for n in st["npcs"]}
        kills = []
        for nid, (k, life) in self.near_mobs.items():
            if nid not in now:
                kills.append(k)
                if k != 2:  # bats have no sim kill achievement
                    self.award({1: "defeat Blue Slime", 3: "defeat Zombie", 4: "defeat Demon Eye", 5: "defeat Skeleton"}[k])
        self.near_mobs = {n["id"]: (mob_kind(n), n["life"]) for n in st["npcs"]
                          if mob_kind(n) and abs(n["x"] - pcx) < 64 and abs(n["y"] - pcy) < 64}
        return kills


def command(seq, action, st, info, mapper):
    """One sim action -> 15 ticks of inputs (+ declared shortcut ops)."""
    name = SPEC.action_names[action]
    p = st["player"]
    inv_names = [e["name"] for e in st["inv"]]
    cx, cy = p["x"] + p["w"] / 2, p["y"] + p["h"] / 2
    inp, ops = {}, []
    if name == "left":
        inp["left"] = True
    elif name == "right":
        inp["right"] = True
    elif name == "jump":
        inp["jump"] = True
    elif name.startswith("mine ") or name.startswith("place "):
        r = SPEC.action_names.index(name) - (SPEC.mine_first if name.startswith("mine ") else SPEC.place_first)
        dx, dy = SPEC.reach_offsets[r]
        tx, ty = info["px_r"] + dx, info["py_r"] + dy
        if name.startswith("mine "):
            mapper.last_dig = (tx, ty)
        if name.startswith("mine "):
            g = st["grid"]
            t = info["typ"][ty - g["y0"], tx - g["x0"]]
            if t in TREE_TILES:
                tools = [n for n in inv_names if n.endswith("Axe") and "Pickaxe" not in n]
            else:
                tools = sorted((n for n in inv_names if n in PICK_TIER), key=lambda n: -PICK_TIER[n])
            ops.append({"op": "hold", "names": tools[:1] or ["Copper Pickaxe"]})
        else:
            ops.append({"op": "hold", "names": ITEM_NAMES[PLACEABLE_ITEMS[mapper.selected]]})
        inp.update(use=True, aim=[tx * 16 + 8, ty * 16 + 8])
    elif name == "select next":
        for i in range(1, len(PLACEABLE_ITEMS)):
            cand = (mapper.selected + i) % len(PLACEABLE_ITEMS)
            if info["inv"][I[PLACEABLE_ITEMS[cand]]] > 0:
                mapper.selected = cand
                break
    elif name.startswith("select "):
        mapper.selected = action - A["select stone"]
    elif name in CRAFT:
        ops.append({"op": "craft", "names": ITEM_NAMES[CRAFT[name]]})
        target = CRAFT[name]
        if target in WEAPONS:
            mapper.weapon = WEAPONS.index(target)
        if target in ("wood breastplate", "iron chainmail", "gold chainmail"):
            ops.append({"op": "equip", "names": ITEM_NAMES[target]})
    elif name == "attack":
        ops.append({"op": "hold", "names": ITEM_NAMES[WEAPONS[mapper.weapon]]})
        inp.update(use=True, aim=[cx + 24 * (1 if p["dir"] > 0 else -1), cy])
    elif name == "open chest":
        ops.append({"op": "loot"})
    elif name in ("drink healing potion", "eat mushroom", "use life crystal", "use summon item"):
        item = {"drink healing potion": "lesser healing potion", "eat mushroom": "mushroom",
                "use life crystal": "life crystal", "use summon item": "Suspicious Looking Eye"}[name]
        ops.append({"op": "hold", "names": ITEM_NAMES[item]})
        inp.update(use=True, aim=[cx, cy])
    elif name == "cycle weapon":
        owned = [i for i, n in enumerate(WEAPONS) if info["inv"][I[n]] > 0 and i != mapper.weapon]
        if owned:
            mapper.weapon = min(owned, key=lambda i: (i - mapper.weapon) % len(WEAPONS))
    elif name == "climb up":
        inp["up"] = True
    elif name in ("climb down", "drop through platform"):
        inp["down"] = True
    return {"seq": seq, "ticks": 15, "ops": ops, "input": inp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--steps", type=int, default=1500)
    ap.add_argument("--run", required=True)
    ap.add_argument("--fixture", default="runs/fixtures/default-v07-32000401")
    ap.add_argument("--display", default=":21")
    ap.add_argument("--log", required=True)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--host", default="mika@omarchy")
    a = ap.parse_args()
    torch.manual_seed(a.seed)
    torch.set_num_threads(4)
    agent = load_agent(a.checkpoint)
    bridge = Bridge(os.environ["TERRARIA_LITE_LIB"])
    mapper = Mapper()
    server = subprocess.Popen(
        ["ssh", a.host, f"cd ~/Projects/terraria-lite/TerrariaBench && .venv/bin/python -u tools/v10_transfer/game_server.py "
                        f"--fixture {a.fixture} --output runs/v10-poc/{a.run} --display {a.display}"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    log = open(a.log, "w")
    prev, deaths, was_dead, action_counts = None, 0, False, collections.Counter()
    t0 = time.time()
    try:
        st = json.loads(server.stdout.readline())
        for step in range(a.steps):
            mapper.steps = step
            s, tiles, light, inv, mobs, info = mapper.build(st)
            obs, mask = bridge.encode(s, tiles, light, inv, mobs)
            with torch.no_grad():
                x = torch.as_tensor(obs[None])
                m = torch.as_tensor(mask[None])
                logits = agent.actor(agent.trunk(x)).masked_fill(~m, float("-inf"))
                probs = torch.softmax(logits, -1)
                # Same 1 % uniform mix over legal actions as training (unimix 0.01).
                probs = .99 * probs + .01 * m.float() / m.float().sum()
                action = int(torch.multinomial(probs, 1))
            action_counts[SPEC.action_names[action]] += 1
            cmd = command(step, action, st, info, mapper)
            server.stdin.write(json.dumps(cmd) + "\n")
            server.stdin.flush()
            line = server.stdout.readline()
            if not line:
                raise RuntimeError("game server ended")
            new = json.loads(line)
            ninfo = mapper.build(new)[5]
            kills = mapper.update_achievements(prev and {"inv": prev[1]["inv"], "life": prev[0]["player"]["life"],
                                                         "life_max_base": prev[0]["player"]["life_max_base"]}
                                               or {"inv": info["inv"], "life": st["player"]["life"],
                                                   "life_max_base": st["player"]["life_max_base"]},
                                               new, ninfo, action, new["results"])
            dead = new["player"]["dead"]
            deaths += dead and not was_dead
            was_dead = dead
            log.write(json.dumps({
                "step": step, "action": SPEC.action_names[action], "p": float(probs[0, action]),
                "legal": int(mask.sum()), "ops": cmd["ops"], "results": new["results"], "tick": new["tick"],
                "pos": [ninfo["px_r"], ninfo["py_r"]], "layer": ninfo["layer"], "life": new["player"]["life"],
                "dead": dead, "night": ninfo["night"], "mobs": len(ninfo["mobs"]), "kills": kills,
                "inv": {SPEC.item_names[i]: int(v) for i, v in enumerate(ninfo["inv"]) if v},
                "ach": [n for n, i in ACH.items() if mapper.ach >> i & 1]}) + "\n")
            log.flush()
            prev = (new, ninfo)
            st = new
            if step % 50 == 0:
                print(f"step {step} {time.time() - t0:.0f}s act={SPEC.action_names[action]} pos={ninfo['px_r']},{ninfo['py_r']} "
                      f"layer={ninfo['layer']} life={new['player']['life']} deaths={deaths} "
                      f"inv={ {SPEC.item_names[i]: int(v) for i, v in enumerate(ninfo['inv']) if v} } "
                      f"ach={bin(mapper.ach).count('1')}", flush=True)
    finally:
        try:
            server.stdin.write(json.dumps({"quit": True}) + "\n")
            server.stdin.flush()
            server.wait(60)
        except Exception as e:  # noqa: BLE001
            print("server shutdown:", e)
        summary = {"steps": len(action_counts and range(sum(action_counts.values()))), "deaths": deaths,
                   "achievements": [n for n, i in ACH.items() if mapper.ach >> i & 1],
                   "actions": action_counts.most_common(),
                   "unmapped_tiles": sorted(([list(k), v] for k, v in mapper.unmapped_tiles.items()), key=lambda x: -x[1]),
                   "unmapped_mobs": mapper.unmapped_mobs.most_common(), "liquid_cells_as_air": mapper.liquid_cells,
                   "wall_seconds": time.time() - t0}
        with open(a.log.replace(".jsonl", "-summary.json"), "w") as f:
            json.dump(summary, f, indent=1)
        print(json.dumps({k: v for k, v in summary.items() if k != "actions"}))


if __name__ == "__main__":
    main()
