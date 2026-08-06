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

/* ---- Player tuning ------------------------------------------------------ */

#define MAX_HEALTH        10
#define FALL_SAFE         4    /* tiles you may fall without damage */
#define FALL_DMG_PER_TILE 2
#define JUMP_HEIGHT       3    /* tiles risen per jump, one per tick */
#define STATION_RANGE     3    /* Chebyshev radius for workbench/furnace use */
#define DEEP_Y            70   /* depth that scores ACH_DESCEND_DEEP */

/* ---- Lighting ----------------------------------------------------------- */

#define LIGHT_MAX       15
#define PLAYER_LIGHT    3    /* faint self-light so the dark is hard, not blind */
#define DARK_THRESHOLD  2    /* light below this renders as unknown */

#define DEFAULT_MAX_STEPS 3000

/* ---- Actions (19) ------------------------------------------------------- */

typedef enum {
    ACT_NOOP = 0,
    ACT_LEFT,
    ACT_RIGHT,
    ACT_JUMP,
    ACT_MINE_UP,
    ACT_MINE_DOWN,
    ACT_MINE_LEFT,
    ACT_MINE_RIGHT,
    ACT_PLACE_UP,
    ACT_PLACE_DOWN,
    ACT_PLACE_LEFT,
    ACT_PLACE_RIGHT,
    ACT_SELECT_NEXT,
    ACT_CRAFT_WORKBENCH,
    ACT_CRAFT_FURNACE,
    ACT_CRAFT_STONE_PICK,
    ACT_SMELT_COPPER,
    ACT_CRAFT_COPPER_PICK,
    ACT_CRAFT_TORCH,
    ACT_COUNT
} Action;

/* ---- Achievements (16) -------------------------------------------------- */

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
    ACH_DESCEND_DEEP,
    ACH_COUNT
} Achievement;

static const char *const ACH_NAME[ACH_COUNT] = {
    "collect wood", "collect dirt", "collect stone", "place block",
    "craft workbench", "place workbench", "craft stone pick", "craft furnace",
    "place furnace", "collect copper", "smelt copper", "craft torch",
    "place torch", "craft copper pick", "collect iron", "descend deep",
};

/* ---- Recipes (6) -------------------------------------------------------- */

typedef struct {
    const char *name;
    Item        in_item[2];
    int         in_qty[2];
    int         n_in;
    int8_t      out_item;       /* Item produced, or -1 for none */
    int         out_qty;
    uint8_t     grant_tier;     /* tool tier granted, or 0 for none */
    bool        need_workbench;
    bool        need_furnace;
    int         ach;
} Recipe;

#define RECIPE_COUNT        6
#define RECIPE_FIRST_ACTION ACT_CRAFT_WORKBENCH

/* Indexed by (action - RECIPE_FIRST_ACTION). */
static const Recipe RECIPES[RECIPE_COUNT] = {
    {"workbench",   {ITEM_WOOD,       ITEM_WOOD},  { 8, 0}, 1,
     ITEM_WORKBENCH,  1, 0, false, false, ACH_CRAFT_WORKBENCH},
    {"furnace",     {ITEM_STONE,      ITEM_STONE}, {12, 0}, 1,
     ITEM_FURNACE,    1, 0, true,  false, ACH_CRAFT_FURNACE},
    {"stone pick",  {ITEM_WOOD,       ITEM_STONE}, { 3, 5}, 2,
     -1,              0, TIER_STONE_PICK,  true, false, ACH_CRAFT_STONE_PICK},
    {"copper bar",  {ITEM_COPPER_ORE, ITEM_WOOD},  { 3, 0}, 1,
     ITEM_COPPER_BAR, 1, 0, false, true,  ACH_SMELT_COPPER},
    {"copper pick", {ITEM_COPPER_BAR, ITEM_WOOD},  { 2, 3}, 2,
     -1,              0, TIER_COPPER_PICK, true, false, ACH_CRAFT_COPPER_PICK},
    {"torch x5",    {ITEM_COPPER_BAR, ITEM_WOOD},  { 1, 2}, 2,
     ITEM_TORCH,      5, 0, true,  false, ACH_CRAFT_TORCH},
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

    /* player */
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

/* ---- Shared helpers ----------------------------------------------------- */

static inline bool in_bounds(int x, int y) {
    return x >= 0 && x < WORLD_W && y >= 0 && y < WORLD_H;
}

static inline Tile tile_at(const Env *e, int x, int y) {
    return in_bounds(x, y) ? (Tile)e->tiles[y][x] : TILE_BEDROCK;
}

static inline bool has_ach(const Env *e, int a) {
    return (e->achievements >> a) & 1u;
}

const char *action_name(int action);

#endif /* ENV_H */
