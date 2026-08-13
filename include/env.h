/* terraria-lite core environment contract.
 *
 * Invariants every module must respect:
 *   - All mutable state lives in `Env`. No globals, no statics, no rand().
 *   - env_step() performs zero heap allocation and zero I/O.
 *   - Randomness comes only from `e->rng` via rng.h.
 */
#ifndef ENV_H
#define ENV_H

#include <stdbool.h>
#include <stdint.h>

#include "tiles.h"

/* ---- World geometry ----------------------------------------------------- */

#define WORLD_W        128
#define WORLD_H        96
#define SURFACE_BASE   30   /* mean surface row */
#define SURFACE_MIN    22   /* clamps for the heightmap */
#define SURFACE_MAX    38
#define DIRT_DEPTH     8    /* dirt rows below the grass line before stone */
#define BEDROCK_ROWS   2

#define COPPER_MIN_Y   42
#define COPPER_MAX_Y   85
#define IRON_MIN_Y     62
#define IRON_MAX_Y     93
#define GOLD_MIN_Y     78   /* deepest band: gated by the iron pickaxe */
#define GOLD_MAX_Y     93

/* ---- Player ------------------------------------------------------------- *
 * The body is PLAYER_H tiles tall and one wide. (px, py) is the FEET cell;
 * the head is (px, py - 1). Every physics and reach rule is written against
 * that convention, so py is never less than PLAYER_H - 1. */

#define PLAYER_H          2

#define MAX_HEALTH        10
#define FALL_SAFE         4    /* tiles you may fall without damage */
#define FALL_DMG_PER_TILE 2
#define JUMP_HEIGHT       3    /* tiles risen per jump, one per tick */
#define STATION_RANGE     3    /* Chebyshev radius for crafting-station use */
#define DEEP_Y            70   /* depth that scores ACH_DESCEND_DEEP */

/* ---- Reach -------------------------------------------------------------- *
 * Mining and placing address the Moore neighbourhood of the body: a 3-wide by
 * 4-tall block minus the two cells the body itself fills, so ten targets.
 * Offsets are from the FEET cell, in reading order, top-left to bottom-right.
 *
 *          dx=-1     dx=0     dx=+1
 *   dy=-2    0         1        2      above the head
 *   dy=-1    3      [head]      4
 *   dy= 0    5      [feet]      6
 *   dy=+1    7         8        9      below the feet
 *
 * Indices line up with (action - ACT_MINE_FIRST) and (action - ACT_PLACE_FIRST)
 * alike: the two action blocks share this ordering. */

#define REACH_COUNT 10

static const int REACH_DX[REACH_COUNT] = {-1,  0, +1, -1, +1, -1, +1, -1,  0, +1};
static const int REACH_DY[REACH_COUNT] = {-2, -2, -2, -1, -1,  0,  0, +1, +1, +1};

static const char *const REACH_NAME[REACH_COUNT] = {
    "up-left",   "up",        "up-right",
    "head-left",              "head-right",
    "foot-left",              "foot-right",
    "down-left", "down",      "down-right",
};

/* ---- Lighting ----------------------------------------------------------- */

#define LIGHT_MAX       15
#define PLAYER_LIGHT    3    /* faint self-light so the dark is hard, not blind */
#define DARK_THRESHOLD  2    /* light below this renders as unknown */

#define DEFAULT_MAX_STEPS 3000

/* ---- Actions (36) ------------------------------------------------------- */

typedef enum {
    ACT_NOOP = 0,
    ACT_LEFT,
    ACT_RIGHT,
    ACT_JUMP,

    /* Ten mine targets, in REACH_* order. */
    ACT_MINE_UP_LEFT,
    ACT_MINE_UP,
    ACT_MINE_UP_RIGHT,
    ACT_MINE_HEAD_LEFT,
    ACT_MINE_HEAD_RIGHT,
    ACT_MINE_FOOT_LEFT,
    ACT_MINE_FOOT_RIGHT,
    ACT_MINE_DOWN_LEFT,
    ACT_MINE_DOWN,
    ACT_MINE_DOWN_RIGHT,

    /* Ten place targets, same order. */
    ACT_PLACE_UP_LEFT,
    ACT_PLACE_UP,
    ACT_PLACE_UP_RIGHT,
    ACT_PLACE_HEAD_LEFT,
    ACT_PLACE_HEAD_RIGHT,
    ACT_PLACE_FOOT_LEFT,
    ACT_PLACE_FOOT_RIGHT,
    ACT_PLACE_DOWN_LEFT,
    ACT_PLACE_DOWN,
    ACT_PLACE_DOWN_RIGHT,

    ACT_SELECT_NEXT,

    ACT_CRAFT_WORKBENCH,
    ACT_CRAFT_FURNACE,
    ACT_CRAFT_STONE_PICK,
    ACT_SMELT_COPPER,
    ACT_CRAFT_COPPER_PICK,
    ACT_CRAFT_TORCH,
    ACT_SMELT_IRON,
    ACT_CRAFT_ANVIL,
    ACT_CRAFT_IRON_PICK,
    ACT_SMELT_GOLD,
    ACT_CRAFT_LANTERN,

    ACT_COUNT
} Action;

#define ACT_MINE_FIRST  ACT_MINE_UP_LEFT
#define ACT_PLACE_FIRST ACT_PLACE_UP_LEFT

/* ---- Achievements (24) -------------------------------------------------- *
 * Listed in progression order, which is also the order frontends draw them. */

typedef enum {
    ACH_COLLECT_WOOD = 0,
    ACH_COLLECT_DIRT,
    ACH_COLLECT_STONE,
    ACH_PLACE_BLOCK,
    ACH_CRAFT_WORKBENCH,
    ACH_PLACE_WORKBENCH,
    ACH_CRAFT_STONE_PICK,
    ACH_CRAFT_FURNACE,
    ACH_PLACE_FURNACE,
    ACH_COLLECT_COPPER,
    ACH_SMELT_COPPER,
    ACH_CRAFT_TORCH,
    ACH_PLACE_TORCH,
    ACH_CRAFT_COPPER_PICK,
    ACH_COLLECT_IRON,
    ACH_SMELT_IRON,
    ACH_CRAFT_ANVIL,
    ACH_PLACE_ANVIL,
    ACH_CRAFT_IRON_PICK,
    ACH_COLLECT_GOLD,
    ACH_SMELT_GOLD,
    ACH_CRAFT_LANTERN,
    ACH_PLACE_LANTERN,
    ACH_DESCEND_DEEP,
    ACH_COUNT
} Achievement;

static const char *const ACH_NAME[ACH_COUNT] = {
    "collect wood", "collect dirt", "collect stone", "place block",
    "craft workbench", "place workbench", "craft stone pick", "craft furnace",
    "place furnace", "collect copper", "smelt copper", "craft torch",
    "place torch", "craft copper pick", "collect iron", "smelt iron",
    "craft anvil", "place anvil", "craft iron pick", "collect gold",
    "smelt gold", "craft lantern", "place lantern", "descend deep",
};

/* ---- Recipes (11) ------------------------------------------------------- */

typedef struct {
    const char *name;
    Item        in_item[2];
    int         in_qty[2];
    int         n_in;
    int8_t      out_item;       /* Item produced, or -1 for none */
    int         out_qty;
    uint8_t     grant_tier;     /* tool tier granted, or 0 for none */
    Tile        station;        /* station that must be near, or TILE_AIR */
    int         ach;
} Recipe;

#define RECIPE_COUNT        11
#define RECIPE_FIRST_ACTION ACT_CRAFT_WORKBENCH

/* Indexed by (action - RECIPE_FIRST_ACTION). Ores always smelt to bars at a
   furnace and bars always become tools at a bench or anvil, so the grammar is
   the same on every rung of the ladder. */
static const Recipe RECIPES[RECIPE_COUNT] = {
    {"workbench",   {ITEM_WOOD,       ITEM_WOOD},  { 8, 0}, 1,
     ITEM_WORKBENCH,  1, 0,                TILE_AIR,       ACH_CRAFT_WORKBENCH},
    {"furnace",     {ITEM_STONE,      ITEM_STONE}, {12, 0}, 1,
     ITEM_FURNACE,    1, 0,                TILE_WORKBENCH, ACH_CRAFT_FURNACE},
    {"stone pick",  {ITEM_WOOD,       ITEM_STONE}, { 3, 5}, 2,
     -1,              0, TIER_STONE_PICK,  TILE_WORKBENCH, ACH_CRAFT_STONE_PICK},
    {"copper bar",  {ITEM_COPPER_ORE, ITEM_WOOD},  { 3, 0}, 1,
     ITEM_COPPER_BAR, 1, 0,                TILE_FURNACE,   ACH_SMELT_COPPER},
    {"copper pick", {ITEM_COPPER_BAR, ITEM_WOOD},  { 2, 3}, 2,
     -1,              0, TIER_COPPER_PICK, TILE_WORKBENCH, ACH_CRAFT_COPPER_PICK},
    {"torch x5",    {ITEM_COPPER_BAR, ITEM_WOOD},  { 1, 2}, 2,
     ITEM_TORCH,      5, 0,                TILE_WORKBENCH, ACH_CRAFT_TORCH},
    {"iron bar",    {ITEM_IRON_ORE,   ITEM_WOOD},  { 3, 0}, 1,
     ITEM_IRON_BAR,   1, 0,                TILE_FURNACE,   ACH_SMELT_IRON},
    {"anvil",       {ITEM_IRON_BAR,   ITEM_WOOD},  { 5, 0}, 1,
     ITEM_ANVIL,      1, 0,                TILE_WORKBENCH, ACH_CRAFT_ANVIL},
    {"iron pick",   {ITEM_IRON_BAR,   ITEM_WOOD},  { 2, 3}, 2,
     -1,              0, TIER_IRON_PICK,   TILE_ANVIL,     ACH_CRAFT_IRON_PICK},
    {"gold bar",    {ITEM_GOLD_ORE,   ITEM_WOOD},  { 3, 0}, 1,
     ITEM_GOLD_BAR,   1, 0,                TILE_FURNACE,   ACH_SMELT_GOLD},
    {"lantern",     {ITEM_GOLD_BAR,   ITEM_WOOD},  { 1, 3}, 2,
     ITEM_LANTERN,    1, 0,                TILE_ANVIL,     ACH_CRAFT_LANTERN},
};

/* ---- Environment state -------------------------------------------------- */

typedef struct {
    int max_steps;
} EnvConfig;

typedef struct Env {
    /* world */
    uint8_t tiles[WORLD_H][WORLD_W];
    uint8_t light[WORLD_H][WORLD_W];
    int     surface[WORLD_W];    /* grass row per column, from worldgen */

    /* player -- (px, py) is the FEET cell; the head is (px, py - 1) */
    int     px, py;
    int     facing;              /* -1 left, +1 right */
    int     jump_left;           /* rising ticks remaining */
    int     fall_dist;           /* tiles fallen since last grounded */
    int     health;
    uint8_t tool_tier;
    int16_t inv[ITEM_COUNT];
    uint8_t selected;            /* index into PLACEABLES */

    /* episode */
    uint32_t achievements;       /* bitmask over Achievement */
    uint64_t rng;
    uint64_t seed;
    int      steps;
    int      max_steps;
    float    reward;             /* reward for the step just taken */
    float    ep_return;
    bool     terminated;         /* died: do not bootstrap */
    bool     truncated;          /* hit step limit: do bootstrap */
    bool     light_dirty;

    char     msg[64];            /* human-facing feedback for the last action */
} Env;

/* ---- API ---------------------------------------------------------------- */

void env_init (Env *e, EnvConfig cfg);
void env_reset(Env *e, uint64_t seed);
void env_step (Env *e, int action);
void env_free (Env *e);

/* Implemented in worldgen.c: fills tiles[], surface[], and spawns the player. */
void world_generate(Env *e);

/* Implemented in light.c: recomputes light[] from scratch. */
void light_recompute(Env *e);

const char *action_name(int action);

/* ---- Shared helpers ----------------------------------------------------- */

static inline bool in_bounds(int x, int y) {
    return x >= 0 && x < WORLD_W && y >= 0 && y < WORLD_H;
}

static inline bool has_ach(const Env *e, int ach) {
    return (e->achievements >> ach) & 1u;
}

static inline Tile tile_at(const Env *e, int x, int y) {
    return in_bounds(x, y) ? (Tile)e->tiles[y][x] : TILE_BEDROCK;
}

/* True when (x, y) is one of the two cells the body occupies. */
static inline bool is_body(const Env *e, int x, int y) {
    return x == e->px && y <= e->py && y > e->py - PLAYER_H;
}

/* A column the body fits in at feet-row `feet`: PLAYER_H clear cells. */
static inline bool body_fits(const Env *e, int x, int feet) {
    for (int i = 0; i < PLAYER_H; i++)
        if (tile_solid(tile_at(e, x, feet - i))) return false;
    return feet - (PLAYER_H - 1) >= 0;
}

#endif /* ENV_H */
