/* Tile and item taxonomy, plus their static property tables. */
#ifndef TILES_H
#define TILES_H

#include <stdbool.h>
#include <stdint.h>

/* ---- Tiles (16) --------------------------------------------------------- */

typedef enum {
    TILE_AIR = 0,
    TILE_DIRT,
    TILE_GRASS,
    TILE_STONE,
    TILE_LOG,
    TILE_WOOD,
    TILE_LEAVES,
    TILE_COPPER_ORE,
    TILE_IRON_ORE,
    TILE_GOLD_ORE,
    TILE_TORCH,
    TILE_LANTERN,
    TILE_WORKBENCH,
    TILE_FURNACE,
    TILE_ANVIL,
    TILE_BEDROCK,
    TILE_COUNT
} Tile;

/* ---- Items (14) --------------------------------------------------------- */

typedef enum {
    ITEM_WOOD = 0,
    ITEM_STONE,
    ITEM_DIRT,
    ITEM_COPPER_ORE,
    ITEM_IRON_ORE,
    ITEM_GOLD_ORE,
    ITEM_COPPER_BAR,
    ITEM_IRON_BAR,
    ITEM_GOLD_BAR,
    ITEM_TORCH,
    ITEM_LANTERN,
    ITEM_WORKBENCH,
    ITEM_FURNACE,
    ITEM_ANVIL,
    ITEM_COUNT
} Item;

/* ---- Tool tiers ---------------------------------------------------------
 * Tools gate ores; darkness gates depth. Stone is hand-mineable on purpose --
 * see PLAN.md, the tech tree deadlocks otherwise. */

#define TIER_HAND        0
#define TIER_STONE_PICK  1
#define TIER_COPPER_PICK 2
#define TIER_IRON_PICK   3
#define TIER_NEVER       255

typedef struct {
    const char *name;
    char        glyph;     /* ascii render */
    bool        solid;     /* blocks movement */
    bool        opaque;    /* blocks light propagation */
    uint8_t     min_tier;  /* tool tier needed to mine; TIER_NEVER = unmineable */
    int8_t      drop;      /* Item yielded when mined, or -1 for nothing */
    uint8_t     emit;      /* light emitted, 0..LIGHT_MAX */
} TileInfo;

/* LOG is grown by worldgen, WOOD is what you place: both drop ITEM_WOOD, the
   same way GRASS and DIRT both drop ITEM_DIRT. Keeping them apart means a
   frontend can draw bark against planks, and the scripted expert can tell a
   tree it should harvest from the scaffold it just built. */
/* Furnace and anvil deliberately emit no light: a cheap 12-stone furnace would
   otherwise be a permanent lamp and defeat the torch gate. The lantern is the
   reward at the top of the tech tree, so it outshines a torch. */
static const TileInfo TILE_INFO[TILE_COUNT] = {
    /* AIR         */ {"air",       ' ',  false, false, TIER_NEVER,       -1,               0},
    /* DIRT        */ {"dirt",      '#',  true,  true,  TIER_HAND,        ITEM_DIRT,        0},
    /* GRASS       */ {"grass",     '"',  true,  true,  TIER_HAND,        ITEM_DIRT,        0},
    /* STONE       */ {"stone",     '%',  true,  true,  TIER_HAND,        ITEM_STONE,       0},
    /* LOG         */ {"log",       '|',  true,  true,  TIER_HAND,        ITEM_WOOD,        0},
    /* WOOD        */ {"wood",      '=',  true,  true,  TIER_HAND,        ITEM_WOOD,        0},
    /* LEAVES      */ {"leaves",    '^',  false, false, TIER_HAND,        -1,               0},
    /* COPPER_ORE  */ {"copper",    'c',  true,  true,  TIER_STONE_PICK,  ITEM_COPPER_ORE,  0},
    /* IRON_ORE    */ {"iron",      'i',  true,  true,  TIER_COPPER_PICK, ITEM_IRON_ORE,    0},
    /* GOLD_ORE    */ {"gold",      'g',  true,  true,  TIER_IRON_PICK,   ITEM_GOLD_ORE,    0},
    /* TORCH       */ {"torch",     '*',  false, false, TIER_HAND,        ITEM_TORCH,      12},
    /* LANTERN     */ {"lantern",   'O',  false, false, TIER_HAND,        ITEM_LANTERN,    15},
    /* WORKBENCH   */ {"workbench", 'T',  true,  true,  TIER_HAND,        ITEM_WORKBENCH,   0},
    /* FURNACE     */ {"furnace",   'F',  true,  true,  TIER_HAND,        ITEM_FURNACE,     0},
    /* ANVIL       */ {"anvil",     'A',  true,  true,  TIER_HAND,        ITEM_ANVIL,       0},
    /* BEDROCK     */ {"bedrock",   'X',  true,  true,  TIER_NEVER,       -1,               0},
};

static const char *const ITEM_NAME[ITEM_COUNT] = {
    "wood", "stone", "dirt",
    "copper ore", "iron ore", "gold ore",
    "copper bar", "iron bar", "gold bar",
    "torch", "lantern",
    "workbench", "furnace", "anvil",
};

static inline bool tile_solid(Tile t)    { return TILE_INFO[t].solid; }
static inline bool tile_opaque(Tile t)   { return TILE_INFO[t].opaque; }
static inline uint8_t tile_tier(Tile t)  { return TILE_INFO[t].min_tier; }
static inline int8_t tile_drop(Tile t)   { return TILE_INFO[t].drop; }
static inline uint8_t tile_emit(Tile t)  { return TILE_INFO[t].emit; }

/* ---- Placeables --------------------------------------------------------- */

typedef struct {
    Item item;
    Tile tile;
} Placeable;

#define PLACEABLE_COUNT 8

static const Placeable PLACEABLES[PLACEABLE_COUNT] = {
    {ITEM_STONE,     TILE_STONE},
    {ITEM_DIRT,      TILE_DIRT},
    {ITEM_WOOD,      TILE_WOOD},
    {ITEM_TORCH,     TILE_TORCH},
    {ITEM_LANTERN,   TILE_LANTERN},
    {ITEM_WORKBENCH, TILE_WORKBENCH},
    {ITEM_FURNACE,   TILE_FURNACE},
    {ITEM_ANVIL,     TILE_ANVIL},
};

#endif /* TILES_H */
