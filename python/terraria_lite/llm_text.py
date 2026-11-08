"""Text rendering of the symbolic packet, the optional game guide and named-action parsing.

The text view is a re-encoding of the RL observation packet (tiles, entities, status,
action mask): it adds no world information. Dropped relative to the packet: per-cell
light levels (only lit/unlit is kept) and mob movement phase.
"""
import re

from terraria_lite import SPEC

TEXT_VIEW = "terraria-text-v1"
GLYPHS = {"air": ".", "dirt": "#", "grass": '"', "stone": "%", "log": "|", "wood": "=", "leaves": "^",
          "copper ore": "c", "iron ore": "i", "gold ore": "g", "torch": "*", "campfire": "O", "workbench": "T",
          "furnace": "F", "anvil": "A", "bedrock": "X", "silver ore": "s", "wood platform": "-", "rope": ":",
          "chest": "C", "empty chest": "u", "life crystal": "H", "mushroom": "m", "demon altar": "D"}
UNKNOWN = "?"
PLAYER = "@"
MOBS = ("Blue Slime", "Cave Bat", "Zombie", "Demon Eye", "Skeleton", "Eye of Cthulhu")
MOB_GLYPHS = ("S", "B", "Z", "Y", "K", "W")
WEAPONS = ("copper shortsword", "wooden sword", "copper broadsword", "iron broadsword", "silver broadsword", "gold broadsword")
ARMORS = ("none", "wood breastplate", "iron chainmail", "gold chainmail")
PICKS = ("hand", "copper pickaxe", "iron pickaxe", "gold pickaxe")
PLACEABLES = ("stone", "dirt", "wood", "torch", "campfire", "workbench", "furnace", "anvil", "platform", "rope")


def cycle_constants(environment_root):
    """Day/night lengths from the frozen source header (compile-time defaults)."""
    from pathlib import Path
    header = (Path(environment_root) / "include/env.h").read_text()
    day = re.search(r"#define DAY_STEPS (\d+)", header)
    night = re.search(r"#define NIGHT_STEPS (\d+)", header)
    return (int(day[1]), int(night[1])) if day and night else None


def legend():
    tiles = ", ".join(f"'{GLYPHS[name]}' {name}" for name in SPEC.tile_names)
    mobs = ", ".join(f"'{g}' {m}" for g, m in zip(MOB_GLYPHS, MOBS))
    return (f"Map legend: {tiles}; '{UNKNOWN}' unlit/unknown (not visible); '{PLAYER}' your body; mobs drawn on top: {mobs}. "
            "Rows run top (row 0) to bottom; dy>0 is DOWN, dx>0 is RIGHT.")


def reach_table():
    rows = []
    for i, (dx, dy) in enumerate(SPEC.reach_offsets):
        suffix = SPEC.action_names[SPEC.mine_first+i][len("mine "):]
        rows.append(f"{suffix}=({dx:+d},{dy:+d})")
    return ("Your body is 2 tiles wide and 3 tall. Offsets (dx,dy) are relative to your LEFT FOOT cell (dx=0,dy=0); "
            "your body covers dx 0..1, dy -2..0; the ground under your feet is dy=+1. "
            "'mine X'/'place X' act on exactly one adjacent cell: " + ", ".join(rows) + ".")


def text_observation(packet, max_steps, cycle):
    s = packet["scalars"]
    cap = SPEC.health_cap
    max_health = round(s["max_health_fraction"]*cap)
    health = round(s["health_fraction"]*max_health)
    x = round(s["horizontal_fraction"]*(SPEC.world_w-1))
    y = round(s["depth_fraction"]*(SPEC.world_h-1))
    lines = [f"Step {packet['steps']} of {max_steps} ({max_steps-packet['steps']} primitive actions left)."]
    v9 = packet.get("v9")
    if v9:
        when = "NIGHT" if v9["is_night"] else "day"
        if cycle:
            day, night = cycle
            t = packet["steps"] % (day+night)
            left = (day - t) if t < day else (day + night - t)
            when += f", {left} steps until {'dawn' if t >= day else 'nightfall'}"
        lines.append(f"Time: {when}. Layer: {v9['layer']}. Position x={x} y={y} (y grows downward).")
    else:
        lines.append(f"Position x={x} y={y} (y grows downward).")
    weapon = WEAPONS[round(s["weapon_fraction"]*(len(WEAPONS)-1))]
    armor = ARMORS[round(s["armor_fraction"]*(len(ARMORS)-1))]
    pick = PICKS[round(s["mining_tier_fraction"]*(len(PICKS)-1))]
    lines.append(f"Health {health}/{max_health}. Weapon {weapon}. Armor {armor}. Pickaxe {pick}. Facing {'right' if s['facing_right'] > .5 else 'left'}.")
    fall = round(s["fall_fraction"]*2*SPEC.fall_safe)
    if fall:
        lines.append(f"FALLING: {fall} tiles so far (falls over {SPEC.fall_safe} tiles hurt).")
    cooldowns = {"mine": round(s["mine_cooldown"]*3), "attack": round(s["attack_cooldown"]*3), "heal": round(s["heal_cooldown"]*60)}
    busy = ", ".join(f"{k} {v}" for k, v in cooldowns.items() if v)
    if busy:
        lines.append(f"Cooldown ticks: {busy}.")
    if v9:
        selected = [PLACEABLES[i] for i, v in enumerate(v9["selected_slot_one_hot"]) if v > .5]
        lines.append(f"Selected placeable: {selected[0] if selected else 'none'}.")
        if v9["boss"]["present"]:
            b = v9["boss"]
            lines.append(f"EYE OF CTHULHU present: health {b['health_fraction']:.2f}, phase {'2' if b['phase2'] else '1'}, "
                         f"offset dx={round(b['dx_over_32']*32):+d} dy={round(b['dy_over_32']*32):+d} (clipped at 32).")
    inventory = ", ".join(f"{k} {v}" for k, v in packet["inventory"].items() if v)
    lines.append(f"Inventory: {inventory or 'empty'}.")
    have = packet["achievements"]
    if SPEC.achievement_weights:
        weights = dict(zip(SPEC.achievement_names, SPEC.achievement_weights))
        got = sum(weights[a] for a in have)
        lines.append(f"Achievements {len(have)}/{SPEC.n_achievements} (weighted {got}/{SPEC.max_weighted_score}): {', '.join(have) or 'none'}.")
    else:
        lines.append(f"Achievements {len(have)}/{SPEC.n_achievements}: {', '.join(have) or 'none'}.")
    ax, ay = SPEC.view_w//2, SPEC.view_h//2
    grid = [[UNKNOWN if t == SPEC.unknown_tile else GLYPHS[SPEC.tile_names[t]] for t in row] for row in packet["tiles"]]
    for dy in range(-SPEC.player_h+1, 1):
        for dx in range(SPEC.player_w):
            if 0 <= ay+dy < SPEC.view_h and 0 <= ax+dx < SPEC.view_w:
                grid[ay+dy][ax+dx] = PLAYER
    mobs = []
    for entity in packet["visible_entities"]:
        cell, f = entity["cell"], entity["features"]
        row, col = divmod(cell, SPEC.view_w)
        kinds = [i for i in range(min(len(MOBS), SPEC.entity_channels-2)) if f[i] > .5]
        for i in kinds:
            mobs.append(f"{MOBS[i]} at dx={col-ax:+d} dy={row-ay:+d} health {f[SPEC.entity_channels-2]:.2f}")
        if kinds and grid[row][col] != PLAYER:
            grid[row][col] = MOB_GLYPHS[kinds[0]]
    under = [SPEC.tile_names[packet["tiles"][ay+dy][ax+dx]] for dy in range(-SPEC.player_h+1, 1) for dx in range(SPEC.player_w)
             if packet["tiles"][ay+dy][ax+dx] not in (SPEC.unknown_tile, 0)]
    lines.append(f"View {SPEC.view_w}x{SPEC.view_h}, your left foot at row {ay} col {ax}; column header is dx:")
    lines.append("     " + "".join(f"{c-ax:+d}"[-1] if c != ax else "0" for c in range(SPEC.view_w)))
    lines.append("     " + "".join("-" if c < ax else "+" if c > ax else " " for c in range(SPEC.view_w)))
    for r, row in enumerate(grid):
        lines.append(f"dy{r-ay:+d} " + "".join(row))
    if under:
        lines.append("Inside your body cells (hidden by '@'): " + ", ".join(sorted(set(under))) + ".")
    lines.append("Mobs: " + ("; ".join(mobs) if mobs else "none visible") + ".")
    legal = packet["legal_actions"]
    names = []
    for a in legal:
        name = SPEC.action_names[a]
        if SPEC.mine_first <= a < SPEC.mine_first+SPEC.reach_count:
            dx, dy = SPEC.reach_offsets[a-SPEC.mine_first]
            t = packet["tiles"][ay+dy][ax+dx] if 0 <= ay+dy < SPEC.view_h and 0 <= ax+dx < SPEC.view_w else SPEC.unknown_tile
            name += f" [{'unlit' if t == SPEC.unknown_tile else SPEC.tile_names[t]}]"
        names.append(name)
    lines.append("Legal now: " + ", ".join(names) + ".")
    return "\n".join(lines)


# Max weighted score and the tier-4 list come from the library (v9: 129; v10
# adds "find a Demon Altar" and "hold 6 lenses", max 145).
_TIER4_NOTES = {"find a Demon Altar": "find a Demon Altar (stand with a demon altar within crafting range)",
                "hold 6 lenses": "hold 6 lenses (6 lens in inventory at once)"}
_TIER4 = ", ".join(_TIER4_NOTES.get(n, n) for n, t in zip(SPEC.achievement_names, SPEC.achievement_tiers or [])
                   if t == 4) or ("craft gold pickaxe, collect lens, craft Suspicious Looking Eye, "
                                  "summon the Eye of Cthulhu, defeat the Eye of Cthulhu")
GUIDE = f"""GAME GUIDE (declared game-knowledge track; facts about this environment, not a scripted policy)
Scoring: achievements are weighted by tier: tier1 x1, tier2 x3, tier3 x5, tier4 x8 (max {SPEC.max_weighted_score or 129}). Each counts once.
 Tier1: collect wood, collect stone, place block, place torch, place platform, craft workbench, craft wooden sword, collect copper, defeat Blue Slime, open chest, explore 30 columns (span 30 columns of x), climb rope, heal with food or potion.
 Tier2: craft furnace, smelt copper, collect iron, smelt iron, craft anvil, craft metal sword (copper/iron/silver/gold sword), craft wood breastplate, use life crystal, defeat Zombie, defeat Demon Eye, survive a night (be alive at dawn), reach the caverns (y>=64).
 Tier3: craft iron pickaxe, collect silver, smelt silver, collect gold, smelt gold, craft iron chainmail, defeat Skeleton, return to surface (after reaching caverns, get back above the surface line).
 Tier4: {_TIER4}.
World: 128x128 tiles. Surface around y=26-30 (spawn at the surface, at dawn). Underground below the surface; caverns from y=64 down; bedrock at the bottom. Trees (trunk '|') near spawn.
Ores: copper and iron in underground and caverns (iron is common); silver in caverns; gold in the lower half of the caverns. Your copper pickaxe mines every ore. Life crystals ('H') and chests ('C', open with 'open chest' when adjacent/near) are underground. Demon altars ('D') are in cavern chambers.
Mining: one 'mine' action removes one adjacent tile (into your inventory). Pickaxe cooldown after each mine: copper pickaxe 3 ticks (mine, then 2 other actions such as noop or moving, then mine again); iron 2; gold 1. During cooldown every mine action is illegal. Mining a tree trunk ('|') at the cell beside your feet/body cuts the trunk above it: one wood per trunk cell.
Moving: left/right move one tile and turn you that way; when grounded you automatically step up a 1-tile ledge if there is headroom; otherwise a blocked move is illegal. jump gives up to 6 tiles of rise over the next ticks (only when standing on ground); steer with left/right while airborne. Falls up to 25 tiles are safe. To go down, mine 'down' (0,+1) and 'below right column' (+1,+1), the two cells under your 2-wide body, and you fall. To dig sideways mine the 3 cells beside your body on that side (right: head-right, middle-right, foot-right; left: head-left, middle-left, foot-left) then walk. To dig up mine 'up' and 'above right column'. To get out of a shaft: jump repeatedly while placing blocks under you, dig a staircase, or place rope and 'climb up'.
Crafting needs ingredients in inventory and the station within 3 tiles: workbench (10 wood, no station), torch x3 (1 wood + 1 gel; gel drops from Blue Slimes), platform x2 (1 wood), wooden sword (7 wood @workbench), wood breastplate (30 wood @workbench), furnace (20 stone + 4 wood + 3 torches @workbench), copper bar (3 copper ore @furnace), iron bar (3 iron ore @furnace), silver bar (4 silver ore @furnace), gold bar (4 gold ore @furnace), anvil (5 iron bars @workbench), iron pickaxe (12 iron bars + 3 wood @anvil), gold pickaxe (12 gold bars + 3 wood @anvil), copper sword (6 copper bars @anvil), iron sword (8 iron bars @anvil), iron chainmail (20 iron bars @anvil), Suspicious Looking Eye (6 lens @demon altar). Craft a station item, then select it ('select workbench') and 'place' it in an empty cell next to you (usually on the ground beside you); mine it to pick it up again and carry it.
Placing: select the item first (select stone/dirt/wood/torch/platform/rope/workbench/furnace/anvil/campfire), then 'place <direction>'. Station objects are multi-tile: the target cell is the object's bottom-left cell and it extends right and up (workbench and anvil 2x1, furnace and campfire 3x2); non-solid objects (stations, torches, platforms, rope) may overlap your body cells, e.g. 'place body foot-left'. Only place actions listed under 'Legal now' fit. Torches light dark tunnels (unlit cells show '?').
Combat: 'attack' hits mobs in front of you (the direction you face, up to ~2 tiles beyond your body). Attack has a 3-tick cooldown. Better swords deal more damage. Death ENDS the episode (no respawn): keep health up, retreat or wall yourself in with blocks when low. Health regenerates slowly when not hurt (faster near a campfire); mushrooms (+15) and healing potions (+50) heal.
Night (last 1200 of every 3000 steps; episode starts at dawn): Zombies and Demon Eyes spawn on the surface; Demon Eyes drop lens (about 1 in 3). Underground is safe from them but has Cave Bats; caverns have Skeletons (strong: 50 HP, 16 damage).
Boss chain: collect 6 lens from Demon Eyes -> craft Suspicious Looking Eye at a demon altar -> at night 'use summon item' -> Eye of Cthulhu (240 HP, phase 2 below half health). Gear up first (better sword, armor, life crystals).
Typical progression: wood -> workbench -> wooden sword (+ wood breastplate) -> dig down for stone/copper/iron, kill slimes for gel -> torches -> furnace -> bars -> anvil -> metal sword, iron pickaxe, iron chainmail -> caverns (silver, gold, skeletons, altars) -> return to surface -> survive nights."""


ACTION_RE = re.compile(r"^\s*(.+?)(?:\s*(?:x|\*)\s*(\d+))?\s*$", re.IGNORECASE)


def parse_named(items, limit, macros=False):
    """Strings 'action name' / 'action name xN' (or integer IDs), plus macro strings when enabled.

    Returns a list of items: primitive IDs (int) or (macro_name, n) tuples; None if invalid.
    """
    from terraria_lite.llm_macros import parse_macro
    lookup = {name.lower(): i for i, name in enumerate(SPEC.action_names)}
    result, ticks = [], 0
    for item in items:
        if type(item) is int:
            if not 0 <= item < SPEC.n_actions:
                return None
            result.append(item)
            ticks += 1
            continue
        if not isinstance(item, str):
            return None
        text = re.sub(r"\s*\[[^\]]*\]\s*$", "", item.strip())  # tolerate copied '[tile]' annotations
        macro = parse_macro(text) if macros else None
        if macro:
            if not 1 <= macro[1] <= limit:
                return None
            result.append(macro)
            ticks += 1
            continue
        match = ACTION_RE.match(text)
        if not match:
            return None
        name, count = match[1].strip().lower(), int(match[2] or 1)
        if name not in lookup:
            name = text.strip().lower()
            if name not in lookup:
                return None
            count = 1
        if not 1 <= count <= limit:
            return None
        result += [lookup[name]] * count
        ticks += count
    return result if 1 <= ticks <= limit else None
