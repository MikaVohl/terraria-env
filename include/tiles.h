/* Tile and item taxonomy, plus their static property tables. */
#ifndef TILES_H
#define TILES_H

#include <stdbool.h>
#include <stdint.h>

/* ---- Tiles (12) --------------------------------------------------------- */

typedef enum {
    TILE_AIR = 0,
    TILE_DIRT,
    TILE_GRASS,
    TILE_STONE,
    TILE_WOOD,
    TILE_LEAVES,
    TILE_COPPER_ORE,
    TILE_IRON_ORE,
    TILE_TORCH,
    TILE_WORKBENCH,
    TILE_FURNACE,
    TILE_BEDROCK,
    TILE_COUNT
} Tile;

/* ---- Items (9) ---------------------------------------------------------- */

typedef enum {
    ITEM_WOOD = 0,
    ITEM_STONE,
    ITEM_DIRT,
    ITEM_COPPER_ORE,
    ITEM_IRON_ORE,
    ITEM_COPPER_BAR,
    ITEM_TORCH,
    ITEM_WORKBENCH,
    ITEM_FURNACE,
    ITEM_COUNT
} Item;

/* ---- Tool tiers --------------------------------------------------------- */

#define TIER_HAND        0
#define TIER_STONE_PICK  1
#define TIER_COPPER_PICK 2
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

/* Furnace deliberately emits no light: a cheap 12-stone furnace would
   otherwise be a permanent lamp and defeat the torch gate. */
static const TileInfo TILE_INFO[TILE_COUNT] = {
    /* AIR         */ {"air",       ' ',  false, false, TIER_NEVER,       -1,               0},
    /* DIRT        */ {"dirt",      '#',  true,  true,  TIER_HAND,        ITEM_DIRT,        0},
    /* GRASS       */ {"grass",     '"',  true,  true,  TIER_HAND,        ITEM_DIRT,        0},
    /* STONE       */ {"stone",     '%',  true,  true,  TIER_HAND,        ITEM_STONE,       0},
    /* WOOD        */ {"wood",      '|',  true,  true,  TIER_HAND,        ITEM_WOOD,        0},
    /* LEAVES      */ {"leaves",    '^',  false, false, TIER_HAND,        -1,               0},
    /* COPPER_ORE  */ {"copper",    'c',  true,  true,  TIER_STONE_PICK,  ITEM_COPPER_ORE,  0},
    /* IRON_ORE    */ {"iron",      'i',  true,  true,  TIER_COPPER_PICK, ITEM_IRON_ORE,    0},
    /* TORCH       */ {"torch",     '*',  false, false, TIER_HAND,        ITEM_TORCH,      12},
    /* WORKBENCH   */ {"workbench", 'T',  true,  true,  TIER_HAND,        ITEM_WORKBENCH,   0},
    /* FURNACE     */ {"furnace",   'F',  true,  true,  TIER_HAND,        ITEM_FURNACE,     0},
    /* BEDROCK     */ {"bedrock",   'X',  true,  true,  TIER_NEVER,       -1,               0},
};

static const char *const ITEM_NAME[ITEM_COUNT] = {
    "wood", "stone", "dirt", "copper ore", "iron ore", "copper bar",
    "torch", "workbench", "furnace",
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

#define PLACEABLE_COUNT 6

static const Placeable PLACEABLES[PLACEABLE_COUNT] = {
    {ITEM_STONE,     TILE_STONE},
    {ITEM_DIRT,      TILE_DIRT},
    {ITEM_WOOD,      TILE_WOOD},
    {ITEM_TORCH,     TILE_TORCH},
    {ITEM_WORKBENCH, TILE_WORKBENCH},
    {ITEM_FURNACE,   TILE_FURNACE},
};

#endif /* TILES_H */
