/* Headless invariant checks plus a scripted expert that plays the tech tree. */
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "env.h"

static int failures = 0;

#define CHECK(cond, ...)                                                       \
    do {                                                                       \
        if (!(cond)) {                                                         \
            printf("  FAIL: ");                                                \
            printf(__VA_ARGS__);                                               \
            printf("\n");                                                      \
            failures++;                                                        \
        }                                                                      \
    } while (0)

static Env *env_new(int max_steps) {
    Env *e = calloc(1, sizeof(Env));
    if (!e) { fprintf(stderr, "oom\n"); exit(1); }
    EnvConfig cfg = {.max_steps = max_steps};
    env_init(e, cfg);
    return e;
}

static bool alive(const Env *e) { return !e->terminated && !e->truncated; }

static int count_tile(const Env *e, Tile t, int y0, int y1) {
    int n = 0;
    for (int y = y0; y < y1; y++)
        for (int x = 0; x < WORLD_W; x++)
            if (e->tiles[y][x] == t) n++;
    return n;
}

/* ---- determinism -------------------------------------------------------- */

static void test_determinism(void) {
    printf("determinism\n");
    Env *a = env_new(0), *b = env_new(0);

    env_reset(a, 12345);
    env_reset(b, 12345);
    CHECK(memcmp(a->tiles, b->tiles, sizeof a->tiles) == 0, "worlds differ at reset");
    CHECK(memcmp(a->light, b->light, sizeof a->light) == 0, "light differs at reset");
    CHECK(a->px == b->px && a->py == b->py, "spawn differs");

    uint64_t s = 99;
    for (int i = 0; i < 1500; i++) {
        s = s * 6364136223846793005ULL + 1442695040888963407ULL;
        int act = (int)((s >> 33) % ACT_COUNT);
        env_step(a, act);
        env_step(b, act);
    }
    CHECK(memcmp(a, b, sizeof(Env)) == 0, "state diverged after 1500 identical actions");

    env_reset(a, 12345);
    env_reset(b, 999);
    CHECK(memcmp(a->tiles, b->tiles, sizeof a->tiles) != 0, "different seeds gave identical worlds");

    free(a);
    free(b);
}

/* ---- world invariants --------------------------------------------------- */

static void test_world(void) {
    printf("worldgen invariants (64 seeds)\n");
    Env *e = env_new(0);
    int seeds_with_shallow_copper = 0;
    long total_copper = 0, total_iron = 0, total_wood = 0;

    for (uint64_t seed = 1; seed <= 64; seed++) {
        env_reset(e, seed);

        for (int y = WORLD_H - BEDROCK_ROWS; y < WORLD_H; y++)
            for (int x = 0; x < WORLD_W; x++)
                if (e->tiles[y][x] != TILE_BEDROCK) {
                    CHECK(false, "seed %llu: non-bedrock at (%d,%d)",
                          (unsigned long long)seed, x, y);
                    goto next;
                }

        for (int y = 0; y < WORLD_H; y++)
            for (int x = 0; x < WORLD_W; x++)
                if (e->tiles[y][x] >= TILE_COUNT) {
                    CHECK(false, "seed %llu: bad tile id at (%d,%d)",
                          (unsigned long long)seed, x, y);
                    goto next;
                }

        for (int x = 0; x < WORLD_W; x++) {
            int s = e->surface[x];
            if (s < SURFACE_MIN || s > SURFACE_MAX) {
                CHECK(false, "seed %llu: surface[%d]=%d out of range",
                      (unsigned long long)seed, x, s);
                break;
            }
        }

        CHECK(in_bounds(e->px, e->py), "seed %llu: spawn out of bounds",
              (unsigned long long)seed);
        CHECK(tile_at(e, e->px, e->py) == TILE_AIR, "seed %llu: spawn inside %s",
              (unsigned long long)seed, TILE_INFO[tile_at(e, e->px, e->py)].name);
        CHECK(!tile_solid(tile_at(e, e->px, e->py - 1)), "seed %llu: no headroom at spawn",
              (unsigned long long)seed);
        CHECK(tile_solid(tile_at(e, e->px, e->py + 1)), "seed %llu: spawn unsupported",
              (unsigned long long)seed);

        int shallow = count_tile(e, TILE_COPPER_ORE, 0, 60);
        if (shallow > 0) seeds_with_shallow_copper++;
        total_copper += count_tile(e, TILE_COPPER_ORE, 0, WORLD_H);
        total_iron   += count_tile(e, TILE_IRON_ORE, 0, WORLD_H);
        total_wood   += count_tile(e, TILE_WOOD, 0, WORLD_H);
    next:;
    }

    CHECK(seeds_with_shallow_copper >= 60, "only %d/64 seeds have copper above y=60",
          seeds_with_shallow_copper);
    CHECK(total_copper / 64 >= 30, "mean copper tiles %ld too low", total_copper / 64);
    CHECK(total_iron / 64 >= 20, "mean iron tiles %ld too low", total_iron / 64);
    CHECK(total_wood / 64 >= 30, "mean wood tiles %ld too low", total_wood / 64);
    printf("  mean per world: copper %ld, iron %ld, wood %ld\n",
           total_copper / 64, total_iron / 64, total_wood / 64);
    free(e);
}

/* ---- sandbox rig -------------------------------------------------------- */

/* Wipe to air with a bedrock floor, drop the player on a dirt platform. */
static void sandbox(Env *e, int px, int py) {
    memset(e->tiles, TILE_AIR, sizeof e->tiles);
    for (int x = 0; x < WORLD_W; x++) {
        for (int y = WORLD_H - BEDROCK_ROWS; y < WORLD_H; y++) e->tiles[y][x] = TILE_BEDROCK;
        e->surface[x] = SURFACE_BASE;
    }
    e->px = px;
    e->py = py;
    e->tiles[py + 1][px] = TILE_DIRT;
    e->jump_left = 0;
    e->fall_dist = 0;
    e->health = MAX_HEALTH;
    e->terminated = e->truncated = false;
    e->tool_tier = TIER_HAND;
    e->achievements = 0;
    memset(e->inv, 0, sizeof e->inv);
    light_recompute(e);
}

static void test_tool_gating(void) {
    printf("tool tier gating\n");
    Env *e = env_new(0);
    env_reset(e, 3);

    struct { Tile tile; uint8_t tier; bool expect; const char *what; } cases[] = {
        {TILE_STONE,      TIER_HAND,        true,  "hand mines stone"},
        {TILE_COPPER_ORE, TIER_HAND,        false, "hand mines copper"},
        {TILE_IRON_ORE,   TIER_HAND,        false, "hand mines iron"},
        {TILE_COPPER_ORE, TIER_STONE_PICK,  true,  "stone pick mines copper"},
        {TILE_IRON_ORE,   TIER_STONE_PICK,  false, "stone pick mines iron"},
        {TILE_IRON_ORE,   TIER_COPPER_PICK, true,  "copper pick mines iron"},
        {TILE_BEDROCK,    TIER_COPPER_PICK, false, "copper pick mines bedrock"},
    };

    for (size_t i = 0; i < sizeof cases / sizeof *cases; i++) {
        sandbox(e, 60, 50);
        e->tool_tier = cases[i].tier;
        e->tiles[50][61] = (uint8_t)cases[i].tile;
        env_step(e, ACT_MINE_RIGHT);
        bool mined = e->tiles[50][61] == TILE_AIR;
        CHECK(mined == cases[i].expect, "%s: got %s", cases[i].what,
              mined ? "mined" : "blocked");
    }

    sandbox(e, 60, 50);
    e->tiles[50][61] = TILE_STONE;
    env_step(e, ACT_MINE_RIGHT);
    CHECK(e->inv[ITEM_STONE] == 1, "mining stone yielded %d stone", e->inv[ITEM_STONE]);

    sandbox(e, 60, 50);
    e->tiles[50][61] = TILE_GRASS;
    env_step(e, ACT_MINE_RIGHT);
    CHECK(e->inv[ITEM_DIRT] == 1, "mining grass yielded %d dirt", e->inv[ITEM_DIRT]);

    free(e);
}

static void test_crafting_gates(void) {
    printf("crafting station gates\n");
    Env *e = env_new(0);
    env_reset(e, 4);

    sandbox(e, 60, 50);
    e->inv[ITEM_WOOD] = 20;
    e->inv[ITEM_STONE] = 40;
    env_step(e, ACT_CRAFT_STONE_PICK);
    CHECK(e->tool_tier == TIER_HAND, "crafted stone pick with no workbench");

    env_step(e, ACT_CRAFT_WORKBENCH);
    CHECK(e->inv[ITEM_WORKBENCH] == 1, "workbench craft needs no station but failed");

    e->tiles[50][62] = TILE_WORKBENCH; /* 2 tiles away, inside STATION_RANGE */
    light_recompute(e);
    env_step(e, ACT_CRAFT_STONE_PICK);
    CHECK(e->tool_tier == TIER_STONE_PICK, "stone pick failed beside a workbench");

    sandbox(e, 60, 50);
    e->inv[ITEM_COPPER_ORE] = 6;
    env_step(e, ACT_SMELT_COPPER);
    CHECK(e->inv[ITEM_COPPER_BAR] == 0, "smelted with no furnace");
    e->tiles[50][61] = TILE_FURNACE;
    light_recompute(e);
    env_step(e, ACT_SMELT_COPPER);
    CHECK(e->inv[ITEM_COPPER_BAR] == 1, "smelt failed beside a furnace");
    CHECK(e->inv[ITEM_COPPER_ORE] == 3, "smelt consumed %d ore, expected 3",
          6 - e->inv[ITEM_COPPER_ORE]);

    /* Station out of range must fail. */
    sandbox(e, 60, 50);
    e->inv[ITEM_WOOD] = 20;
    e->inv[ITEM_STONE] = 40;
    e->tiles[50][60 + STATION_RANGE + 1] = TILE_WORKBENCH;
    env_step(e, ACT_CRAFT_STONE_PICK);
    CHECK(e->tool_tier == TIER_HAND, "workbench worked from beyond STATION_RANGE");

    free(e);
}

static void test_fall_damage(void) {
    printf("fall damage threshold\n");
    Env *e = env_new(0);
    env_reset(e, 5);

    const int floor_y = 60;
    for (int drop = FALL_SAFE - 1; drop <= FALL_SAFE + 2; drop++) {
        memset(e->tiles, TILE_AIR, sizeof e->tiles);
        for (int x = 0; x < WORLD_W; x++) {
            e->tiles[floor_y][x] = TILE_STONE;
            for (int y = WORLD_H - BEDROCK_ROWS; y < WORLD_H; y++)
                e->tiles[y][x] = TILE_BEDROCK;
        }
        e->px = 60;
        e->py = floor_y - 1 - drop;
        e->jump_left = 0;
        e->terminated = e->truncated = false;
        e->health = MAX_HEALTH;
        e->fall_dist = 0;

        for (int i = 0; i < 40 && alive(e); i++) {
            env_step(e, ACT_NOOP);
            if (e->py == floor_y - 1 && e->fall_dist == 0) break;
        }
        int expect = drop > FALL_SAFE ? (drop - FALL_SAFE) * FALL_DMG_PER_TILE : 0;
        int got = MAX_HEALTH - e->health;
        CHECK(got == expect, "drop of %d tiles dealt %d damage, expected %d",
              drop, got, expect);
    }

    /* A long enough fall must terminate the episode. */
    sandbox(e, 60, 20);
    for (int x = 0; x < WORLD_W; x++) e->tiles[80][x] = TILE_STONE;
    e->tiles[21][60] = TILE_AIR;
    for (int i = 0; i < 120 && alive(e); i++) env_step(e, ACT_NOOP);
    CHECK(e->terminated, "a 59-tile fall did not kill the player");
    CHECK(!e->truncated, "death should set terminated, not truncated");

    free(e);
}

static void test_lighting(void) {
    printf("lighting\n");
    Env *e = env_new(0);
    env_reset(e, 6);

    memset(e->tiles, TILE_AIR, sizeof e->tiles);
    for (int y = 40; y < WORLD_H; y++)
        for (int x = 0; x < WORLD_W; x++)
            e->tiles[y][x] = (y >= WORLD_H - BEDROCK_ROWS) ? TILE_BEDROCK : TILE_STONE;
    e->px = 4;
    e->py = 39;

    /* Sealed chamber far from the player, lit by one torch. */
    for (int x = 60; x <= 64; x++) e->tiles[60][x] = TILE_AIR;
    e->tiles[60][62] = TILE_TORCH;
    light_recompute(e);

    CHECK(e->light[10][70] == LIGHT_MAX, "open sky not fully lit (got %u)", e->light[10][70]);
    CHECK(e->light[39][70] == LIGHT_MAX, "air just above ground not lit (got %u)",
          e->light[39][70]);
    CHECK(e->light[80][30] == 0, "deep sealed stone is lit (got %u)", e->light[80][30]);

    int torch = tile_emit(TILE_TORCH);
    CHECK(e->light[60][62] == torch, "torch cell light %u, expected %d",
          e->light[60][62], torch);
    CHECK(e->light[60][64] == torch - 2, "light 2 tiles from torch is %u, expected %d",
          e->light[60][64], torch - 2);
    CHECK(e->light[60][58] == 0, "light leaked through 2 tiles of solid stone (got %u)",
          e->light[60][58]);
    CHECK(e->light[60][59] > 0, "stone wall facing a torch is unlit");

    CHECK(e->light[e->py][e->px] >= PLAYER_LIGHT, "player cell below PLAYER_LIGHT");

    /* Player light must follow the player. */
    memset(e->tiles, TILE_STONE, sizeof e->tiles);
    e->tiles[50][60] = TILE_AIR;
    e->tiles[50][61] = TILE_AIR;
    e->px = 60;
    e->py = 50;
    light_recompute(e);
    CHECK(e->light[50][60] >= PLAYER_LIGHT, "buried player has no self-light");

    free(e);
}

/* ---- scripted expert ---------------------------------------------------- */

typedef struct {
    bool solved;
    int  steps;
    int  achievements;
    int  stage;
    bool died;
    int  death_py;
    int  wood;
    int  stone;
    int  hits;
} BotResult;

/* Action -> frontend keystroke, so a bot run can be replayed through the TUI. */
static const char ACTION_KEY[ACT_COUNT] = {
    's', 'a', 'd', 'w', 'i', 'k', 'j', 'l', 't', 'g',
    'f', 'h', 'e', '1', '2', '3', '4', '5', '6',
};

static char g_rec[1 << 16];
static int  g_recn;
static bool g_recording;

/* Every bot action funnels through here so the replay tape stays in sync with
   the simulation. Shadowing env_step keeps the stage machine readable. */
static void bot_step(Env *e, int a) {
    if (g_recording && a >= 0 && a < ACT_COUNT && g_recn < (int)sizeof g_rec - 1)
        g_rec[g_recn++] = ACTION_KEY[a];
    env_step(e, a);
}
#define env_step bot_step

typedef struct {
    int      x, y;
    Tile     t;
    int      age;
    bool     valid;
    uint64_t rs;
} Target;

static bool station_near(const Env *e, Tile t) {
    for (int dy = -STATION_RANGE; dy <= STATION_RANGE; dy++)
        for (int dx = -STATION_RANGE; dx <= STATION_RANGE; dx++)
            if (tile_at(e, e->px + dx, e->py + dy) == t) return true;
    return false;
}

/* Pick a tile of type `t`. Cost penalises tiles above the player, because
   climbing needs a jump while digging down or sideways always works; this is
   what makes the bot strip a tree from the bottom up instead of staring at its
   canopy. `randomize` reservoir-samples instead, to break out of a stall. */
static bool find_target(const Env *e, Tile t, int *ox, int *oy,
                        uint64_t *rs, bool randomize) {
    int best = 1 << 30;
    uint32_t seen = 0;
    bool found = false;
    for (int y = 0; y < WORLD_H - BEDROCK_ROWS; y++)
        for (int x = 0; x < WORLD_W; x++) {
            if (e->tiles[y][x] != t) continue;
            found = true;
            if (randomize) {
                seen++;
                *rs = *rs * 6364136223846793005ULL + 1442695040888963407ULL;
                if ((*rs >> 33) % seen == 0) { *ox = x; *oy = y; }
            } else {
                int climb = e->py - y;
                int cost = abs(x - e->px) + abs(y - e->py) +
                           (climb > 0 ? 3 * climb : 0);
                if (cost < best) { best = cost; *ox = x; *oy = y; }
            }
        }
    return found;
}

static bool mineable(const Env *e, int x, int y) {
    Tile t = tile_at(e, x, y);
    return t != TILE_AIR && tile_tier(t) <= e->tool_tier;
}

/* True when the fall already underway will hurt if we let it finish. */
static bool falling_danger(const Env *e) {
    if (tile_solid(tile_at(e, e->px, e->py + 1))) return false;
    int remaining = 0;
    for (int y = e->py + 1; y < WORLD_H; y++) {
        if (tile_solid(tile_at(e, e->px, y))) break;
        remaining++;
    }
    return e->fall_dist + remaining > FALL_SAFE;
}

/* Terraria's answer to a long drop: put a block under yourself mid-fall.
   Costs one block, which you get straight back by mining it, so a cavern of
   any depth is descended two steps per tile at zero health. */
static bool place_below(Env *e) {
    /* Wood is the early-game fallback: before the first shaft the bot owns no
       dirt or stone, and that is exactly when surface caves swallow it. */
    Item want = ITEM_STONE;
    if (e->inv[ITEM_DIRT] > 0)      want = ITEM_DIRT;
    else if (e->inv[ITEM_STONE] > 0) want = ITEM_STONE;
    else if (e->inv[ITEM_WOOD] > 2)  want = ITEM_WOOD;
    if (e->inv[want] <= 0) return false;
    if (PLACEABLES[e->selected].item != want) { env_step(e, ACT_SELECT_NEXT); return true; }
    env_step(e, ACT_PLACE_DOWN);
    return true;
}

static void arrest_fall(Env *e) {
    if (!place_below(e)) env_step(e, ACT_NOOP);
}

/* Gain one tile of height. Grid physics gives no wall-cling, so the only way
   up an open shaft is Terraria's pillar jump: leap, then build under yourself
   at the apex. Without this the bot can descend into a cave and never leave. */
static void climb(Env *e) {
    if (tile_solid(tile_at(e, e->px, e->py - 1))) {
        if (mineable(e, e->px, e->py - 1)) env_step(e, ACT_MINE_UP);
        else env_step(e, ACT_RIGHT);
        return;
    }
    if (tile_solid(tile_at(e, e->px, e->py + 1))) { env_step(e, ACT_JUMP); return; }
    if (!place_below(e)) env_step(e, ACT_NOOP);
}

/* Descend one tile. Falls are handled by the arrest rule in the main loop. */
static void dig_down_safe(Env *e) {
    if (tile_at(e, e->px, e->py + 1) == TILE_AIR) { env_step(e, ACT_NOOP); return; }
    if (mineable(e, e->px, e->py + 1)) { env_step(e, ACT_MINE_DOWN); return; }
    /* Standing on bedrock or on ore above our tier. Step aside, always toward
       the middle of the world so we can never pin ourselves against a wall. */
    int dir = e->px < WORLD_W / 2 ? 1 : -1;
    if (mineable(e, e->px + dir, e->py)) env_step(e, dir > 0 ? ACT_MINE_RIGHT : ACT_MINE_LEFT);
    else env_step(e, dir > 0 ? ACT_RIGHT : ACT_LEFT);
}

/* One step of greedy dig-toward-target. Always consumes exactly one step. */
static void step_toward(Env *e, int tx, int ty) {
    if (e->px != tx) {
        int dir = tx > e->px ? 1 : -1;
        if (tile_solid(tile_at(e, e->px + dir, e->py))) {
            if (mineable(e, e->px + dir, e->py)) {
                env_step(e, dir > 0 ? ACT_MINE_RIGHT : ACT_MINE_LEFT);
                return;
            }
            /* Unmineable rock in the way: detour toward the target's side,
               never reflexively downward -- that is how a surface errand ends
               up 60 tiles underground. */
            if (ty <= e->py && mineable(e, e->px, e->py - 1)) env_step(e, ACT_MINE_UP);
            else dig_down_safe(e);
            return;
        }
        env_step(e, dir > 0 ? ACT_RIGHT : ACT_LEFT);
        return;
    }
    if (ty > e->py) { dig_down_safe(e); return; }
    if (ty < e->py) { climb(e); return; }
    env_step(e, ACT_NOOP);
}

/* Mine the named tile wherever it is: adjacent first, else navigate to the
   nearest one. Returns false only when the world holds none. */
static bool harvest(Env *e, Tile t, Target *tg) {
    if (tile_at(e, e->px, e->py + 1) == t)      { env_step(e, ACT_MINE_DOWN);  return true; }
    if (tile_at(e, e->px + 1, e->py) == t)      { env_step(e, ACT_MINE_RIGHT); return true; }
    if (tile_at(e, e->px - 1, e->py) == t)      { env_step(e, ACT_MINE_LEFT);  return true; }
    if (tile_at(e, e->px, e->py - 1) == t)      { env_step(e, ACT_MINE_UP);    return true; }

    /* Commit to one target. Re-picking the nearest tile every step makes the
       bot pace between two equidistant trees forever. */
    bool stalled = false;
    if (tg->valid && (tg->t != t || tile_at(e, tg->x, tg->y) != t)) tg->valid = false;
    if (tg->valid && ++tg->age > 250) { tg->valid = false; stalled = true; }
    if (!tg->valid) {
        if (!find_target(e, t, &tg->x, &tg->y, &tg->rs, stalled)) return false;
        tg->t = t;
        tg->age = 0;
        tg->valid = true;
    }
    step_toward(e, tg->x, tg->y);
    return true;
}

/* Clear the cell to the left, then place `what` into it. One step per call. */
static void place_beside(Env *e, Item what, bool left) {
    int dx = left ? -1 : 1;
    if (tile_at(e, e->px + dx, e->py) != TILE_AIR) {
        if (mineable(e, e->px + dx, e->py)) {
            env_step(e, left ? ACT_MINE_LEFT : ACT_MINE_RIGHT);
        } else {
            env_step(e, ACT_MINE_DOWN);
        }
        return;
    }
    if (PLACEABLES[e->selected].item != what) {
        env_step(e, ACT_SELECT_NEXT);
        return;
    }
    env_step(e, left ? ACT_PLACE_LEFT : ACT_PLACE_RIGHT);
}

#define WOOD_TARGET  18
#define STONE_TARGET 25
#define COPPER_TARGET 9

static BotResult bot_play(Env *e, uint64_t seed, int budget) {
    env_reset(e, seed);
    BotResult r = {0};
    int stage = 0, stuck = 0;
    Target tgt = {.rs = seed * 2654435761u + 12345u};
    int last_hp = MAX_HEALTH;

    while (alive(e) && e->steps < budget && stage < 8) {
        int before = e->steps;
        int prev_stage = stage;

        /* Universal safety net: never let a fall finish if it would cost hp. */
        if (falling_danger(e)) {
            arrest_fall(e);
            if (e->health < last_hp) { r.hits++; last_hp = e->health; }
            continue;
        }

        switch (stage) {
        case 0: /* harvest wood wherever it grows */
            if (e->inv[ITEM_WOOD] >= WOOD_TARGET) { stage = 1; break; }
            if (!harvest(e, TILE_WOOD, &tgt)) stage = 1;
            break;

        case 1: /* sink a shaft until we have stone */
            if (e->inv[ITEM_STONE] >= STONE_TARGET) { stage = 2; break; }
            if (!harvest(e, TILE_STONE, &tgt)) dig_down_safe(e);
            break;

        case 2: /* first placed block, then bench up and make a stone pick */
            if (!has_ach(e, ACH_PLACE_BLOCK)) {
                if (PLACEABLES[e->selected].item != ITEM_STONE) env_step(e, ACT_SELECT_NEXT);
                else if (tile_at(e, e->px, e->py - 1) == TILE_AIR) env_step(e, ACT_PLACE_UP);
                else env_step(e, ACT_MINE_UP);
                break;
            }
            if (e->inv[ITEM_WORKBENCH] == 0 && !station_near(e, TILE_WORKBENCH)) {
                env_step(e, ACT_CRAFT_WORKBENCH);
                break;
            }
            if (!station_near(e, TILE_WORKBENCH)) { place_beside(e, ITEM_WORKBENCH, true); break; }
            if (e->tool_tier < TIER_STONE_PICK) { env_step(e, ACT_CRAFT_STONE_PICK); break; }
            if (e->inv[ITEM_FURNACE] == 0 && !has_ach(e, ACH_CRAFT_FURNACE)) {
                env_step(e, ACT_CRAFT_FURNACE);
                break;
            }
            stage = 3;
            break;

        case 3: /* pick the workbench back up and carry it down */
            if (tile_at(e, e->px - 1, e->py) == TILE_WORKBENCH) env_step(e, ACT_MINE_LEFT);
            else if (tile_at(e, e->px + 1, e->py) == TILE_WORKBENCH) env_step(e, ACT_MINE_RIGHT);
            else stage = 4;
            break;

        case 4: /* mine copper */
            if (e->inv[ITEM_COPPER_ORE] >= COPPER_TARGET) { stage = 5; break; }
            if (!harvest(e, TILE_COPPER_ORE, &tgt)) dig_down_safe(e);
            break;

        case 5: /* smelt three bars beside a furnace */
            if (e->inv[ITEM_COPPER_BAR] >= 3) { stage = 6; break; }
            if (!station_near(e, TILE_FURNACE)) { place_beside(e, ITEM_FURNACE, true); break; }
            env_step(e, ACT_SMELT_COPPER);
            break;

        case 6: /* copper pickaxe and torches */
            if (!station_near(e, TILE_WORKBENCH)) { place_beside(e, ITEM_WORKBENCH, false); break; }
            if (e->tool_tier < TIER_COPPER_PICK) { env_step(e, ACT_CRAFT_COPPER_PICK); break; }
            if (!has_ach(e, ACH_CRAFT_TORCH)) { env_step(e, ACT_CRAFT_TORCH); break; }
            stage = 7;
            break;

        case 7: { /* torch the shaft, then go get iron */
            if (!has_ach(e, ACH_PLACE_TORCH) && e->inv[ITEM_TORCH] > 0) {
                if (PLACEABLES[e->selected].item != ITEM_TORCH) env_step(e, ACT_SELECT_NEXT);
                else if (tile_at(e, e->px, e->py - 1) == TILE_AIR) env_step(e, ACT_PLACE_UP);
                else env_step(e, ACT_MINE_UP);
                break;
            }
            if (has_ach(e, ACH_COLLECT_IRON) && has_ach(e, ACH_DESCEND_DEEP)) { stage = 8; break; }
            if (!has_ach(e, ACH_COLLECT_IRON)) {
                if (!harvest(e, TILE_IRON_ORE, &tgt)) dig_down_safe(e);
            } else {
                dig_down_safe(e);
            }
            break;
        }
        }

        if (e->health < last_hp) { r.hits++; last_hp = e->health; }
        if (e->health > last_hp) last_hp = e->health;
        if (e->steps == before) {           /* stage fell through without acting */
            if (stage == prev_stage) {
                env_step(e, ACT_NOOP);
                if (++stuck > 200) break;
            }
        } else {
            stuck = 0;
        }
    }

    r.wood = e->inv[ITEM_WOOD];
    r.stone = e->inv[ITEM_STONE];
    r.death_py = e->py;
    r.steps = e->steps;
    r.stage = stage;
    r.died = e->terminated;
    r.achievements = __builtin_popcount(e->achievements);
    r.solved = has_ach(e, ACH_CRAFT_COPPER_PICK);
    return r;
}

#undef env_step

static void record_run(uint64_t seed) {
    Env *e = env_new(20000);
    g_recording = true;
    g_recn = 0;
    BotResult r = bot_play(e, seed, 20000);
    g_rec[g_recn] = 0;
    fprintf(stderr, "seed %llu: %d/%d achievements in %d steps%s\n",
            (unsigned long long)seed, r.achievements, ACH_COUNT, r.steps,
            r.died ? " (died)" : "");
    printf("%s", g_rec);
    free(e);
}

static void test_beatable(int nseeds, int verbose) {
    printf("scripted expert (%d seeds, omniscient ore search)\n", nseeds);
    Env *e = env_new(20000);
    int solved = 0, full = 0, died = 0;
    long steps_sum = 0;
    int steps_min = 1 << 30, steps_max = 0;
    int stage_hist[9] = {0};

    for (int i = 0; i < nseeds; i++) {
        BotResult r = bot_play(e, (uint64_t)(i + 1), 20000);
        stage_hist[r.stage]++;
        if (r.died) died++;
        if (r.solved) {
            solved++;
            steps_sum += r.steps;
            if (r.steps < steps_min) steps_min = r.steps;
            if (r.steps > steps_max) steps_max = r.steps;
        }
        if (r.achievements == ACH_COUNT) full++;
        if (verbose)
            printf("  seed %2d: stage %d, %2d/%d ach, %5d steps, wood %d stone %d, "
                   "hits %d, y=%d%s\n",
                   i + 1, r.stage, r.achievements, ACH_COUNT, r.steps, r.wood,
                   r.stone, r.hits, r.death_py, r.died ? ", DIED" : "");
    }

    printf("  copper pickaxe: %d/%d   full clear: %d/%d   died: %d\n",
           solved, nseeds, full, nseeds, died);
    if (solved)
        printf("  steps to copper pickaxe: min %d, mean %ld, max %d\n",
               steps_min, steps_sum / solved, steps_max);
    printf("  stopped at stage: ");
    for (int s = 0; s <= 8; s++) if (stage_hist[s]) printf("%d:%d ", s, stage_hist[s]);
    printf("\n");

    CHECK(solved * 100 >= nseeds * 80, "only %d/%d seeds reached a copper pickaxe",
          solved, nseeds);
    free(e);
}

int main(int argc, char **argv) {
    int verbose = 0, nseeds = 20, record_seed = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-v")) verbose = 1;
        else if (!strcmp(argv[i], "-n") && i + 1 < argc) nseeds = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--record") && i + 1 < argc) record_seed = atoi(argv[++i]);
    }

    if (record_seed) { record_run((uint64_t)record_seed); return 0; }

    test_determinism();
    test_world();
    test_tool_gating();
    test_crafting_gates();
    test_fall_damage();
    test_lighting();
    test_beatable(nseeds, verbose);

    printf("\n%s (%d failures)\n", failures ? "FAILED" : "all checks passed", failures);
    return failures ? 1 : 0;
}
