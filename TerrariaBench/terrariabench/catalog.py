"""Versioned, equally weighted progress facts, not a prerequisite tree."""

CATALOG_VERSION = "progress-v0.1"
GROUPS = {
    "preparation": (
        "wood_25", "stone_25", "possess_torch", "possess_workbench",
        "possess_furnace", "possess_anvil", "life_upgrade", "mana_upgrade",
    ),
    "pre_hardmode": (
        "king_slime", "eye_of_cthulhu", "evil_boss", "queen_bee",
        "skeletron", "deerclops", "wall_of_flesh",
    ),
    "hardmode": (
        "queen_slime", "destroyer", "twins", "skeletron_prime",
        "plantera", "golem", "duke_fishron", "empress_of_light",
    ),
    "endgame": (
        "lunatic_cultist", "solar_pillar", "vortex_pillar",
        "nebula_pillar", "stardust_pillar", "moon_lord",
    ),
}
MILESTONES = tuple(m for group in GROUPS.values() for m in group)
