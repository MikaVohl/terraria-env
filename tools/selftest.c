/* Headless invariant checks plus a scripted expert that plays the tech tree. */
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "env.h"
#include "keymap.h"

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
        /* The feet convention is an invariant, not just a spawn property: no
           sequence of actions may push the head out of the world. */
        if (a->py < PLAYER_H - 1) {
            CHECK(false, "py %d below the feet floor after action %d", a->py, act);
            break;
        }
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
    int seeds_with_shallow_copper = 0, seeds_with_gold = 0;
    long total_copper = 0, total_iron = 0, total_gold = 0, total_log = 0;

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

        /* Spawn is the FEET cell: the whole PLAYER_H column must be clear and
           the row under the feet must carry the body. */
        CHECK(in_bounds(e->px, e->py), "seed %llu: spawn out of bounds",
              (unsigned long long)seed);
        CHECK(e->py >= PLAYER_H - 1, "seed %llu: spawn feet row %d leaves no head room",
              (unsigned long long)seed, e->py);
        CHECK(body_fits(e, e->px, e->py), "seed %llu: %d-tall body does not fit at spawn",
              (unsigned long long)seed, PLAYER_H);
        CHECK(tile_at(e, e->px, e->py) == TILE_AIR, "seed %llu: spawn inside %s",
              (unsigned long long)seed, TILE_INFO[tile_at(e, e->px, e->py)].name);
        CHECK(tile_solid(tile_at(e, e->px, e->py + 1)), "seed %llu: spawn unsupported",
              (unsigned long long)seed);

        int shallow = count_tile(e, TILE_COPPER_ORE, 0, 60);
        if (shallow > 0) seeds_with_shallow_copper++;
        int gold = count_tile(e, TILE_GOLD_ORE, 0, WORLD_H);
        if (gold > 0) seeds_with_gold++;
        CHECK(count_tile(e, TILE_GOLD_ORE, 0, GOLD_MIN_Y) == 0,
              "seed %llu: gold above GOLD_MIN_Y", (unsigned long long)seed);
        total_copper += count_tile(e, TILE_COPPER_ORE, 0, WORLD_H);
        total_iron   += count_tile(e, TILE_IRON_ORE, 0, WORLD_H);
        total_gold   += gold;
        total_log    += count_tile(e, TILE_LOG, 0, WORLD_H);
        /* Planks are player-made. A fresh world grows logs and nothing else,
           which is exactly what lets the bot tell a tree from its own pillar. */
        CHECK(count_tile(e, TILE_WOOD, 0, WORLD_H) == 0,
              "seed %llu: worldgen placed plank wood", (unsigned long long)seed);
    next:;
    }

    CHECK(seeds_with_shallow_copper >= 60, "only %d/64 seeds have copper above y=60",
          seeds_with_shallow_copper);
    CHECK(seeds_with_gold >= 60, "only %d/64 seeds have any gold", seeds_with_gold);
    CHECK(total_copper / 64 >= 30, "mean copper tiles %ld too low", total_copper / 64);
    CHECK(total_iron / 64 >= 20, "mean iron tiles %ld too low", total_iron / 64);
    CHECK(total_gold / 64 >= 5, "mean gold tiles %ld too low", total_gold / 64);
    CHECK(total_log / 64 >= 30, "mean log tiles %ld too low", total_log / 64);
    printf("  mean per world: copper %ld, iron %ld, gold %ld, log %ld\n",
           total_copper / 64, total_iron / 64, total_gold / 64, total_log / 64);
    free(e);
}

/* ---- sandbox rig -------------------------------------------------------- */

/* Wipe to air with a bedrock floor, drop the player on a dirt platform.
   `py` is the FEET row; the rig guarantees the PLAYER_H cells from (px, py)
   upwards are clear so the body always has somewhere legal to stand. */
static void sandbox(Env *e, int px, int py) {
    memset(e->tiles, TILE_AIR, sizeof e->tiles);
    for (int x = 0; x < WORLD_W; x++) {
        for (int y = WORLD_H - BEDROCK_ROWS; y < WORLD_H; y++) e->tiles[y][x] = TILE_BEDROCK;
        e->surface[x] = SURFACE_BASE;
    }
    e->px = px;
    e->py = py;
    for (int i = 0; i < PLAYER_H; i++) e->tiles[py - i][px] = TILE_AIR;
    e->tiles[py + 1][px] = TILE_DIRT;
    e->facing = 1;
    e->jump_left = 0;
    e->fall_dist = 0;
    e->health = MAX_HEALTH;
    e->terminated = e->truncated = false;
    e->tool_tier = TIER_HAND;
    e->achievements = 0;
    e->selected = 0;
    memset(e->inv, 0, sizeof e->inv);
    light_recompute(e);
}

/* A continuous floor, so a sideways step never turns into a fall. */
static void floor_row(Env *e, int y) {
    for (int x = 0; x < WORLD_W; x++) e->tiles[y][x] = TILE_STONE;
}

static void test_tool_gating(void) {
    printf("tool tier gating\n");
    Env *e = env_new(0);
    env_reset(e, 3);

    struct { Tile tile; uint8_t tier; bool expect; const char *what; } cases[] = {
        {TILE_STONE,      TIER_HAND,        true,  "hand mines stone"},
        {TILE_LOG,        TIER_HAND,        true,  "hand mines log"},
        {TILE_WOOD,       TIER_HAND,        true,  "hand mines planks"},
        {TILE_COPPER_ORE, TIER_HAND,        false, "hand mines copper"},
        {TILE_IRON_ORE,   TIER_HAND,        false, "hand mines iron"},
        {TILE_GOLD_ORE,   TIER_HAND,        false, "hand mines gold"},
        {TILE_COPPER_ORE, TIER_STONE_PICK,  true,  "stone pick mines copper"},
        {TILE_IRON_ORE,   TIER_STONE_PICK,  false, "stone pick mines iron"},
        {TILE_GOLD_ORE,   TIER_STONE_PICK,  false, "stone pick mines gold"},
        {TILE_IRON_ORE,   TIER_COPPER_PICK, true,  "copper pick mines iron"},
        {TILE_GOLD_ORE,   TIER_COPPER_PICK, false, "copper pick mines gold"},
        {TILE_GOLD_ORE,   TIER_IRON_PICK,   true,  "iron pick mines gold"},
        {TILE_BEDROCK,    TIER_COPPER_PICK, false, "copper pick mines bedrock"},
        {TILE_BEDROCK,    TIER_IRON_PICK,   false, "iron pick mines bedrock"},
    };

    for (size_t i = 0; i < sizeof cases / sizeof *cases; i++) {
        sandbox(e, 60, 50);
        e->tool_tier = cases[i].tier;
        e->tiles[50][61] = (uint8_t)cases[i].tile;
        env_step(e, ACT_MINE_FOOT_RIGHT);
        bool mined = e->tiles[50][61] == TILE_AIR;
        CHECK(mined == cases[i].expect, "%s: got %s", cases[i].what,
              mined ? "mined" : "blocked");
    }

    sandbox(e, 60, 50);
    e->tiles[50][61] = TILE_STONE;
    env_step(e, ACT_MINE_FOOT_RIGHT);
    CHECK(e->inv[ITEM_STONE] == 1, "mining stone yielded %d stone", e->inv[ITEM_STONE]);

    sandbox(e, 60, 50);
    e->tiles[50][61] = TILE_GRASS;
    env_step(e, ACT_MINE_FOOT_RIGHT);
    CHECK(e->inv[ITEM_DIRT] == 1, "mining grass yielded %d dirt", e->inv[ITEM_DIRT]);

    /* The head cell reaches a row the feet cannot: a 2-tall body mines a
       2-tall tunnel, which is the only kind it can walk through. */
    sandbox(e, 60, 50);
    e->tiles[49][61] = TILE_STONE;
    env_step(e, ACT_MINE_HEAD_RIGHT);
    CHECK(e->tiles[49][61] == TILE_AIR, "head-right did not reach (61,49)");

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

    /* Station range is Chebyshev from the FEET cell, so a station level with
       the head is as usable as one level with the feet. */
    sandbox(e, 60, 50);
    e->inv[ITEM_IRON_ORE] = 3;
    e->tiles[49][61] = TILE_FURNACE;
    light_recompute(e);
    env_step(e, ACT_SMELT_IRON);
    CHECK(e->inv[ITEM_IRON_BAR] == 1, "smelt failed beside a head-height furnace");

    /* The anvil rung: the iron pick is the first recipe that a workbench
       cannot satisfy, which is what stops the iron tier being free. */
    sandbox(e, 60, 50);
    e->inv[ITEM_IRON_BAR] = 8;
    e->inv[ITEM_WOOD] = 20;
    e->tiles[50][61] = TILE_WORKBENCH;
    light_recompute(e);
    env_step(e, ACT_CRAFT_ANVIL);
    CHECK(e->inv[ITEM_ANVIL] == 1, "anvil craft failed beside a workbench");
    env_step(e, ACT_CRAFT_IRON_PICK);
    CHECK(e->tool_tier == TIER_HAND, "iron pick crafted at a workbench");
    e->tiles[50][59] = TILE_ANVIL;
    light_recompute(e);
    env_step(e, ACT_CRAFT_IRON_PICK);
    CHECK(e->tool_tier == TIER_IRON_PICK, "iron pick failed beside an anvil");

    sandbox(e, 60, 50);
    e->inv[ITEM_GOLD_BAR] = 2;
    e->inv[ITEM_WOOD] = 20;
    env_step(e, ACT_CRAFT_LANTERN);
    CHECK(e->inv[ITEM_LANTERN] == 0, "lantern crafted with no anvil");
    e->tiles[50][61] = TILE_ANVIL;
    light_recompute(e);
    env_step(e, ACT_CRAFT_LANTERN);
    CHECK(e->inv[ITEM_LANTERN] == 1, "lantern failed beside an anvil");

    /* Station out of range must fail. */
    sandbox(e, 60, 50);
    e->inv[ITEM_WOOD] = 20;
    e->inv[ITEM_STONE] = 40;
    e->tiles[50][60 + STATION_RANGE + 1] = TILE_WORKBENCH;
    env_step(e, ACT_CRAFT_STONE_PICK);
    CHECK(e->tool_tier == TIER_HAND, "workbench worked from beyond STATION_RANGE");

    free(e);
}

/* ---- logs vs planks ----------------------------------------------------- */

/* Worldgen grows TILE_LOG, the player places TILE_WOOD, and both drop
   ITEM_WOOD -- the same one-item-two-tiles shape as grass and dirt. The split
   exists so a harvest target can never be the scaffold the bot just built. */
static void test_wood_split(void) {
    printf("logs and planks\n");
    Env *e = env_new(0);
    env_reset(e, 11);

    CHECK(tile_drop(TILE_LOG) == ITEM_WOOD, "log drops item %d, expected wood",
          tile_drop(TILE_LOG));
    CHECK(tile_drop(TILE_WOOD) == ITEM_WOOD, "plank drops item %d, expected wood",
          tile_drop(TILE_WOOD));
    CHECK(TILE_INFO[TILE_LOG].glyph != TILE_INFO[TILE_WOOD].glyph,
          "log and plank both render as '%c'", TILE_INFO[TILE_LOG].glyph);

    /* Chopping a trunk is the first achievement of every run, so a log has to
       behave exactly like the old wood tile did on the mining side. */
    sandbox(e, 60, 50);
    e->tiles[50][61] = TILE_LOG;
    env_step(e, ACT_MINE_FOOT_RIGHT);
    CHECK(e->tiles[50][61] == TILE_AIR, "bare hands failed to chop a log");
    CHECK(e->inv[ITEM_WOOD] == 1, "chopping a log yielded %d wood", e->inv[ITEM_WOOD]);
    CHECK(has_ach(e, ACH_COLLECT_WOOD), "chopping a log did not award collect wood");

    sandbox(e, 60, 50);
    e->tiles[50][61] = TILE_WOOD;
    env_step(e, ACT_MINE_FOOT_RIGHT);
    CHECK(e->tiles[50][61] == TILE_AIR, "bare hands failed to mine planks");
    CHECK(e->inv[ITEM_WOOD] == 1, "mining planks yielded %d wood", e->inv[ITEM_WOOD]);
    CHECK(has_ach(e, ACH_COLLECT_WOOD), "mining planks did not award collect wood");

    /* Nothing the player carries can put a log back into the world. */
    for (int i = 0; i < PLACEABLE_COUNT; i++)
        CHECK(PLACEABLES[i].tile != TILE_LOG, "PLACEABLES[%d] (%s) places a log", i,
              ITEM_NAME[PLACEABLES[i].item]);

    sandbox(e, 60, 50);
    e->inv[ITEM_WOOD] = 4;
    env_step(e, ACT_SELECT_NEXT);   /* wood is the only stack, so this lands on it */
    CHECK(PLACEABLES[e->selected].item == ITEM_WOOD, "hotbar would not settle on wood");
    env_step(e, ACT_PLACE_FOOT_RIGHT);
    CHECK(e->tiles[50][61] == TILE_WOOD, "placing wood laid %s, expected planks",
          TILE_INFO[e->tiles[50][61]].name);

    free(e);
}

/* ---- 2-tall body -------------------------------------------------------- */

static void test_body(void) {
    printf("two-tall body\n");
    Env *e = env_new(0);
    env_reset(e, 7);

    /* A 1-tall gap is a wall: the feet fit, the head does not. */
    sandbox(e, 60, 50);
    floor_row(e, 51);
    e->tiles[49][61] = TILE_STONE;
    env_step(e, ACT_RIGHT);
    CHECK(e->px == 60, "walked into a 1-tall gap (px=%d)", e->px);

    /* A 2-tall gap is a corridor. */
    sandbox(e, 60, 50);
    floor_row(e, 51);
    env_step(e, ACT_RIGHT);
    CHECK(e->px == 61 && e->py == 50, "2-tall corridor blocked (px=%d py=%d)", e->px, e->py);

    /* One-tile ledge with clearance over both columns: auto step-up. */
    sandbox(e, 60, 50);
    floor_row(e, 51);
    e->tiles[50][61] = TILE_STONE;
    env_step(e, ACT_RIGHT);
    CHECK(e->px == 61 && e->py == 49, "step-up failed (px=%d py=%d)", e->px, e->py);

    /* Same ledge, but a ceiling over the column we are leaving: no step-up. */
    sandbox(e, 60, 50);
    floor_row(e, 51);
    e->tiles[50][61] = TILE_STONE;
    e->tiles[48][60] = TILE_STONE;
    env_step(e, ACT_RIGHT);
    CHECK(e->px == 60 && e->py == 50, "stepped up under a ceiling (px=%d py=%d)",
          e->px, e->py);

    /* Same ledge, but the destination column is only 1 tall: no step-up. */
    sandbox(e, 60, 50);
    floor_row(e, 51);
    e->tiles[50][61] = TILE_STONE;
    e->tiles[48][61] = TILE_STONE;
    env_step(e, ACT_RIGHT);
    CHECK(e->px == 60 && e->py == 50, "stepped up onto a 1-tall shelf (px=%d py=%d)",
          e->px, e->py);

    /* A two-tile ledge is never a step-up, whatever the clearance. */
    sandbox(e, 60, 50);
    floor_row(e, 51);
    e->tiles[50][61] = TILE_STONE;
    e->tiles[49][61] = TILE_STONE;
    env_step(e, ACT_RIGHT);
    CHECK(e->px == 60, "climbed a 2-tile ledge in one move (px=%d)", e->px);

    /* Jump clearance is measured above the HEAD, not above the feet. */
    sandbox(e, 60, 50);
    floor_row(e, 51);
    e->tiles[48][60] = TILE_STONE;
    env_step(e, ACT_JUMP);
    CHECK(e->py == 50, "jumped into a solid ceiling (py=%d)", e->py);

    sandbox(e, 60, 50);
    floor_row(e, 51);
    env_step(e, ACT_JUMP);
    CHECK(e->py == 49, "open-air jump did not rise (py=%d)", e->py);

    /* The full arc returns to the launch row and costs no health. */
    sandbox(e, 60, 50);
    floor_row(e, 51);
    env_step(e, ACT_JUMP);
    for (int i = 0; i < 12 && alive(e); i++) {
        env_step(e, ACT_NOOP);
        if (e->py == 50 && e->jump_left == 0 && e->fall_dist == 0) break;
    }
    CHECK(e->py == 50, "jump arc ended at py=%d, expected 50", e->py);
    CHECK(e->health == MAX_HEALTH, "own jump cost %d health", MAX_HEALTH - e->health);

    /* py never drops below the feet floor, even jumping at the world ceiling. */
    sandbox(e, 60, PLAYER_H - 1);
    e->tiles[PLAYER_H][60] = TILE_STONE;
    for (int i = 0; i < 8 && alive(e); i++) env_step(e, ACT_JUMP);
    CHECK(e->py >= PLAYER_H - 1, "py %d escaped the top of the world", e->py);

    free(e);
}

/* ---- reach -------------------------------------------------------------- */

static void test_reach(void) {
    printf("ten-target reach\n");
    Env *e = env_new(0);
    env_reset(e, 8);

    CHECK(PLACEABLES[0].item == ITEM_STONE, "test assumes PLACEABLES[0] is stone");

    for (int i = 0; i < REACH_COUNT; i++) {
        int tx = 60 + REACH_DX[i], ty = 50 + REACH_DY[i];

        sandbox(e, 60, 50);
        e->tiles[ty][tx] = TILE_STONE;
        env_step(e, ACT_MINE_FIRST + i);
        CHECK(e->tiles[ty][tx] == TILE_AIR, "mine %s left (%d,%d) as %s",
              REACH_NAME[i], tx, ty, TILE_INFO[e->tiles[ty][tx]].name);

        sandbox(e, 60, 50);
        e->tiles[ty][tx] = TILE_AIR;
        e->inv[ITEM_STONE] = 4;
        env_step(e, ACT_PLACE_FIRST + i);
        CHECK(e->tiles[ty][tx] == TILE_STONE, "place %s left (%d,%d) as %s",
              REACH_NAME[i], tx, ty, TILE_INFO[e->tiles[ty][tx]].name);
    }

    /* Neither body cell may be addressable, and the ten targets must be
       exactly the rest of the 3-wide by PLAYER_H+2-tall block. */
    sandbox(e, 60, 50);
    int covered = 0;
    for (int dy = -PLAYER_H; dy <= 1; dy++)
        for (int dx = -1; dx <= 1; dx++) {
            bool listed = false;
            for (int i = 0; i < REACH_COUNT; i++)
                if (REACH_DX[i] == dx && REACH_DY[i] == dy) listed = true;
            if (is_body(e, 60 + dx, 50 + dy)) {
                CHECK(!listed, "body cell (%d,%d) is a reach target", dx, dy);
            } else {
                CHECK(listed, "neighbour (%d,%d) is unreachable", dx, dy);
                covered++;
            }
        }
    CHECK(covered == REACH_COUNT, "%d neighbours vs REACH_COUNT %d", covered, REACH_COUNT);

    for (int i = 0; i < REACH_COUNT; i++)
        for (int j = i + 1; j < REACH_COUNT; j++)
            CHECK(!(REACH_DX[i] == REACH_DX[j] && REACH_DY[i] == REACH_DY[j]),
                  "reach slots %d and %d address the same cell", i, j);

    /* Placing into a body cell is impossible because no action names one:
       fill the whole neighbourhood and the body column must stay clear. */
    sandbox(e, 60, 50);
    e->inv[ITEM_STONE] = 99;
    for (int i = 0; i < REACH_COUNT; i++) env_step(e, ACT_PLACE_FIRST + i);
    CHECK(!tile_solid(tile_at(e, e->px, e->py)), "feet cell got walled in");
    CHECK(!tile_solid(tile_at(e, e->px, e->py - 1)), "head cell got walled in");

    free(e);
}

/* ---- keymap -------------------------------------------------------------- */

/* The bindings used to be transcribed in four places and a PTY harness existed
   largely to notice when they diverged. One table plus this test is a stronger
   guarantee and about a hundred and forty lines cheaper. */
static void test_keymap(void) {
    printf("keymap round-trip\n");
    for (int a = 0; a < ACT_COUNT; a++) {
        char k = kb_key(a);
        CHECK(k != 0, "%s has no key", action_name(a));
        if (!k) continue;
        CHECK(kb_action((unsigned char)k) == a, "key '%c' maps to %s, not %s",
              k, action_name(kb_action((unsigned char)k)), action_name(a));
    }
    for (int a = 0; a < ACT_COUNT; a++)
        for (int b = a + 1; b < ACT_COUNT; b++)
            CHECK(kb_key(a) != kb_key(b), "%s and %s both answer to '%c'",
                  action_name(a), action_name(b), kb_key(a));
}

/* ---- fall damage -------------------------------------------------------- */

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
        e->py = floor_y - 1 - drop;   /* feet row, so the landing row is floor_y - 1 */
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

    /* Mining the cell under the feet is a controlled descent, not a fall: the
       whole point of reach slot 8 is that you can lower yourself for free. */
    sandbox(e, 60, 40);
    for (int y = 41; y < 60; y++) e->tiles[y][60] = TILE_STONE;
    light_recompute(e);
    for (int i = 0; i < 10 && alive(e); i++) env_step(e, ACT_MINE_DOWN);
    CHECK(e->health == MAX_HEALTH, "digging down cost %d health", MAX_HEALTH - e->health);
    CHECK(e->py > 40, "digging down did not descend (py=%d)", e->py);

    /* Landing settles on the tick the feet arrive, not the one after. While it
       lagged, the player stood on solid ground for a whole action with the fall
       still owed -- and mining the cell underneath zeroes fall_dist as a
       controlled descent, so a fatal drop cost nothing at all if you dug the
       instant you landed. Both halves are checked: the debt is paid on
       touchdown, and digging cannot wipe it. */
    const int far    = FALL_SAFE + 4;                        /* survivable: 8 of 10 hp */
    const int owed   = (far - FALL_SAFE) * FALL_DMG_PER_TILE;
    for (int dig = 0; dig <= 1; dig++) {
        memset(e->tiles, TILE_AIR, sizeof e->tiles);
        for (int x = 0; x < WORLD_W; x++) {
            e->tiles[floor_y][x] = TILE_STONE;
            for (int y = WORLD_H - BEDROCK_ROWS; y < WORLD_H; y++)
                e->tiles[y][x] = TILE_BEDROCK;
        }
        e->px = 60;
        e->py = floor_y - 1 - far;
        e->jump_left = 0;
        e->terminated = e->truncated = false;
        e->health    = MAX_HEALTH;
        e->fall_dist = 0;
        e->tool_tier = TIER_HAND;

        for (int i = 0; i < 40 && alive(e); i++) {
            if (tile_solid(tile_at(e, e->px, e->py + 1))) break;
            env_step(e, ACT_NOOP);
        }
        CHECK(MAX_HEALTH - e->health == owed,
              "damage lagged the landing: lost %d hp on touchdown, expected %d",
              MAX_HEALTH - e->health, owed);
        CHECK(e->fall_dist == 0, "fall_dist %d still owed after touchdown",
              e->fall_dist);

        if (dig) {
            env_step(e, ACT_MINE_DOWN);
            CHECK(MAX_HEALTH - e->health == owed,
                  "mining down on landing erased the fall: lost %d hp, expected %d",
                  MAX_HEALTH - e->health, owed);
        }
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

/* ---- lighting ----------------------------------------------------------- */

static void test_lighting(void) {
    printf("lighting\n");
    Env *e = env_new(0);
    env_reset(e, 6);

    memset(e->tiles, TILE_AIR, sizeof e->tiles);
    for (int y = 40; y < WORLD_H; y++)
        for (int x = 0; x < WORLD_W; x++)
            e->tiles[y][x] = (y >= WORLD_H - BEDROCK_ROWS) ? TILE_BEDROCK : TILE_STONE;
    e->px = 4;
    e->py = 39;   /* feet on the stone at y=40, head at y=38 */

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
    CHECK(e->light[e->py - 1][e->px] >= PLAYER_LIGHT, "head cell below PLAYER_LIGHT");

    /* The lantern is the top of the tech tree, so it must outshine a torch. */
    CHECK(tile_emit(TILE_LANTERN) > tile_emit(TILE_TORCH),
          "lantern emits %u, torch %u", tile_emit(TILE_LANTERN), tile_emit(TILE_TORCH));
    memset(e->tiles, TILE_STONE, sizeof e->tiles);
    for (int x = 20; x <= 24; x++) e->tiles[70][x] = TILE_AIR;
    e->tiles[70][22] = TILE_LANTERN;
    e->px = 4;
    e->py = 39;
    e->tiles[39][4] = TILE_AIR;
    e->tiles[38][4] = TILE_AIR;
    light_recompute(e);
    CHECK(e->light[70][22] == tile_emit(TILE_LANTERN), "lantern cell light %u, expected %u",
          e->light[70][22], tile_emit(TILE_LANTERN));

    /* Player light must follow the player -- both body cells, buried. */
    memset(e->tiles, TILE_STONE, sizeof e->tiles);
    e->tiles[50][60] = TILE_AIR;
    e->tiles[49][60] = TILE_AIR;
    e->px = 60;
    e->py = 50;
    light_recompute(e);
    CHECK(e->light[50][60] >= PLAYER_LIGHT, "buried player has no self-light");
    CHECK(e->light[49][60] >= PLAYER_LIGHT, "buried player's head has no self-light");

    free(e);
}

/* ---- observation -------------------------------------------------------- */

/* Window index of world (x, y), written from the contract rather than read off
   obs.c: the feet cell (px, py) sits at the centre, so the head is one row up. */
static int obs_index(const Env *e, int x, int y) {
    return (y - e->py + VIEW_H / 2) * VIEW_W + (x - e->px + VIEW_W / 2);
}

/* The single window cell holding `t`: -1 when absent, -2 when it shows up more
   than once. The duplicate case is the point -- a mapping that folds two world
   cells onto one index still satisfies a plain "the marker is at k" check. */
static int obs_find(const Obs *o, Tile t) {
    int found = -1;
    for (int k = 0; k < VIEW_CELLS; k++) {
        if (o->tile[k] != t) continue;
        if (found >= 0) return -2;
        found = k;
    }
    return found;
}

/* Every status entry is a ratio of small integers, so the encodings are exact
   and the tolerance only guards against a stray last-bit difference. */
static bool f_eq(float a, float b) {
    float d = a - b;
    return (d < 0.0f ? -d : d) < 1e-6f;
}

/* The [0,1] bound doubles as the finiteness check -- a NaN fails both
   comparisons and an infinity fails one -- so this needs no math.h. */
static void check_status_range(const Obs *o, const char *what) {
    for (int i = 0; i < OBS_STATUS; i++)
        CHECK(o->status[i] >= 0.0f && o->status[i] <= 1.0f,
              "%s: status[%d] = %g is not a finite value in [0,1]", what, i, o->status[i]);
}

/* Solid stone everywhere, with a body-shaped air pocket. Nothing in the world
   is lit afterwards except what the player carries. */
static void bury(Env *e, int px, int py) {
    memset(e->tiles, TILE_STONE, sizeof e->tiles);
    e->px = px;
    e->py = py;
    for (int i = 0; i < PLAYER_H; i++) e->tiles[py - i][px] = TILE_AIR;
    light_recompute(e);
}

static void test_obs(void) {
    printf("egocentric observation\n");
    Env *e = env_new(0);
    Obs o;

    const int centre = (VIEW_H / 2) * VIEW_W + (VIEW_W / 2);

    env_reset(e, 12);

    /* ---- 1. geometry: the window is centred on the feet ------------------ */

    /* Two player positions, differing in both axes, because a window that
       ignored (px, py) and always reported the same slab of world -- or that
       centred on the head -- would still pass at a single position. */
    sandbox(e, 20, 50);
    e->tiles[e->py][e->px]         = TILE_ANVIL;      /* feet */
    e->tiles[e->py - 1][e->px]     = TILE_FURNACE;    /* head */
    e->tiles[e->py - 2][e->px + 3] = TILE_GOLD_ORE;   /* asymmetric, so a
                                                         row/col swap shows */
    light_recompute(e);
    env_obs(e, &o);

    CHECK(obs_find(&o, TILE_ANVIL) == centre,
          "feet cell landed at window index %d, expected the centre %d",
          obs_find(&o, TILE_ANVIL), centre);
    CHECK(obs_find(&o, TILE_FURNACE) == centre - VIEW_W,
          "head cell landed at window index %d, expected one row above centre (%d)",
          obs_find(&o, TILE_FURNACE), centre - VIEW_W);
    CHECK(obs_find(&o, TILE_GOLD_ORE) == obs_index(e, e->px + 3, e->py - 2),
          "marker at (+3,-2) landed at window index %d, expected %d",
          obs_find(&o, TILE_GOLD_ORE), obs_index(e, e->px + 3, e->py - 2));

    /* Second position, markers in opposite corners of the frame. The expected
       indices here are literals, independent of obs_index(). */
    sandbox(e, 77, 33);
    e->tiles[e->py + VIEW_H / 2][e->px - VIEW_W / 2] = TILE_LOG;
    e->tiles[e->py - VIEW_H / 2][e->px + VIEW_W / 2] = TILE_LEAVES;
    light_recompute(e);
    env_obs(e, &o);

    CHECK(obs_find(&o, TILE_LOG) == (VIEW_H - 1) * VIEW_W,
          "bottom-left corner landed at window index %d, expected %d",
          obs_find(&o, TILE_LOG), (VIEW_H - 1) * VIEW_W);
    CHECK(obs_find(&o, TILE_LEAVES) == VIEW_W - 1,
          "top-right corner landed at window index %d, expected %d",
          obs_find(&o, TILE_LEAVES), VIEW_W - 1);

    /* ---- 2. darkness is real, and a torch undoes it ---------------------- */

    /* A sealed pocket three tiles right of the body: well inside the window,
       but walled off from the only light in this world -- the player's own
       glow, which dies inside the first stone tile it enters. */
    bury(e, 60, 50);
    e->tiles[50][62] = TILE_AIR;
    e->tiles[50][63] = TILE_AIR;
    e->tiles[50][64] = TILE_GOLD_ORE;   /* back wall: a distinctive true id */
    light_recompute(e);
    env_obs(e, &o);

    const int c_near = obs_index(e, 62, 50);
    const int c_far  = obs_index(e, 63, 50);
    const int c_wall = obs_index(e, 64, 50);
    const int c_past = obs_index(e, 65, 50);

    CHECK(o.light[c_near] < DARK_THRESHOLD,
          "the chamber is not actually dark (light %u): the test proves nothing",
          o.light[c_near]);
    CHECK(o.tile[c_near] == OBS_UNKNOWN, "unlit chamber cell reads %u, expected OBS_UNKNOWN (%d)",
          o.tile[c_near], OBS_UNKNOWN);
    CHECK(o.tile[c_far] == OBS_UNKNOWN, "unlit chamber cell reads %u, expected OBS_UNKNOWN (%d)",
          o.tile[c_far], OBS_UNKNOWN);
    CHECK(o.tile[c_wall] == OBS_UNKNOWN, "unlit chamber wall reads %u, expected OBS_UNKNOWN (%d)",
          o.tile[c_wall], OBS_UNKNOWN);

    /* Same cells, one torch later. If the visibility test were ever
       "optimised" into reporting tiles unconditionally, the block above passes
       nothing and this block passes everything -- so both halves are needed. */
    e->tiles[50][63] = TILE_TORCH;
    light_recompute(e);
    env_obs(e, &o);

    CHECK(o.tile[c_near] == TILE_AIR, "lit chamber air reads %u, expected air", o.tile[c_near]);
    CHECK(o.tile[c_far] == TILE_TORCH, "lit torch cell reads %u, expected torch (%d)",
          o.tile[c_far], TILE_TORCH);
    CHECK(o.tile[c_wall] == TILE_GOLD_ORE, "lit chamber wall reads %u, expected gold ore (%d)",
          o.tile[c_wall], TILE_GOLD_ORE);
    CHECK(o.tile[c_past] == OBS_UNKNOWN,
          "stone behind the lit chamber reads %u: the torch lit cells it cannot reach",
          o.tile[c_past]);

    /* ---- 3. the player always sees itself -------------------------------- */

    /* PLAYER_LIGHT (3) beats DARK_THRESHOLD (2) with one level to spare, so a
       buried player sees both body cells and one orthogonal step out. Light
       spreads on the 4-neighbourhood, so the diagonals are two steps away and
       are legitimately dark -- they are deliberately not asserted here. */
    bury(e, 40, 60);
    env_obs(e, &o);

    static const int NDX[5] = { 0, -1, +1,  0,  0};
    static const int NDY[5] = { 0,  0,  0, -1, +1};

    for (int b = 0; b < PLAYER_H; b++)
        for (int n = 0; n < 5; n++) {
            int x = e->px + NDX[n], y = e->py - b + NDY[n];
            int k = obs_index(e, x, y);
            CHECK(o.tile[k] != OBS_UNKNOWN,
                  "buried player cannot see (%+d,%+d) from body cell %d", NDX[n], NDY[n], b);
            CHECK(o.tile[k] == e->tiles[y][x],
                  "buried player reads %u at (%+d,%+d) from body cell %d, world holds %u",
                  o.tile[k], NDX[n], NDY[n], b, e->tiles[y][x]);
        }

    /* ...and the rest of the window is dark, or the checks above are vacuous. */
    int unknown = 0;
    for (int k = 0; k < VIEW_CELLS; k++) if (o.tile[k] == OBS_UNKNOWN) unknown++;
    CHECK(unknown > 0, "a buried player's whole window is visible");

    /* ---- 4. the world edge is visible bedrock, never unknown ------------- */

    static const int EDGE_X[3] = {2, WORLD_W - 3, 60};
    static const int EDGE_Y[3] = {50, 50, WORLD_H - 3};

    for (int p = 0; p < 3; p++) {
        sandbox(e, EDGE_X[p], EDGE_Y[p]);
        env_obs(e, &o);

        int outside = 0, not_bedrock = 0, not_bright = 0, edge_unknown = 0;
        for (int row = 0; row < VIEW_H; row++)
            for (int col = 0; col < VIEW_W; col++) {
                int x = e->px - VIEW_W / 2 + col, y = e->py - VIEW_H / 2 + row;
                int k = row * VIEW_W + col;
                if (in_bounds(x, y)) continue;
                outside++;
                if (o.tile[k]  != TILE_BEDROCK) not_bedrock++;
                if (o.light[k] != LIGHT_MAX)    not_bright++;
                if (o.tile[k]  == OBS_UNKNOWN)  edge_unknown++;
            }

        CHECK(outside > 0, "player at (%d,%d) sees no out-of-world cells: nothing was tested",
              e->px, e->py);
        CHECK(not_bedrock == 0, "%d of %d out-of-world cells at (%d,%d) are not bedrock",
              not_bedrock, outside, e->px, e->py);
        CHECK(not_bright == 0, "%d of %d out-of-world cells at (%d,%d) are not at LIGHT_MAX",
              not_bright, outside, e->px, e->py);
        CHECK(edge_unknown == 0,
              "%d out-of-world cells at (%d,%d) read OBS_UNKNOWN: the map edge is "
              "indistinguishable from an unlit cave", edge_unknown, e->px, e->py);
    }

    /* ---- 5. status vector ------------------------------------------------ */

    env_reset(e, 21);
    env_obs(e, &o);
    check_status_range(&o, "fresh reset");
    CHECK(f_eq(o.status[OBS_HEALTH], 1.0f), "full health encodes as %g, expected 1",
          o.status[OBS_HEALTH]);

    static const char *const STATE_NAME[5] = {
        "clean sandbox", "mid-fall", "damaged", "full inventory", "late and decorated"
    };
    for (int s = 0; s < 5; s++) {
        sandbox(e, 30 + s * 10, 40 + s);
        switch (s) {
        case 0: break;
        case 1: e->fall_dist = 3 * FALL_SAFE; e->jump_left = JUMP_HEIGHT; break;
        case 2: e->health = 1; e->facing = -1; break;
        case 3:
            for (int i = 0; i < ITEM_COUNT; i++) e->inv[i] = 30000;
            e->selected = PLACEABLE_COUNT - 1;
            break;
        case 4:
            for (int i = 0; i < ACH_COUNT; i++) e->achievements |= 1u << i;
            e->tool_tier = TIER_IRON_PICK;
            e->steps = e->max_steps * 3;   /* past the horizon: must saturate */
            break;
        }
        env_obs(e, &o);
        check_status_range(&o, STATE_NAME[s]);
        if (s == 4)
            CHECK(f_eq(o.status[OBS_TIME], 1.0f), "steps past max_steps encodes as %g, expected 1",
                  o.status[OBS_TIME]);
    }

    /* The specific encodings, one field at a time. */
    sandbox(e, 60, 50);

    e->tool_tier = TIER_IRON_PICK;
    env_obs(e, &o);
    CHECK(f_eq(o.status[OBS_TIER], 1.0f), "TIER_IRON_PICK encodes as %g, expected 1",
          o.status[OBS_TIER]);
    e->tool_tier = TIER_HAND;
    env_obs(e, &o);
    CHECK(f_eq(o.status[OBS_TIER], 0.0f), "TIER_HAND encodes as %g, expected 0",
          o.status[OBS_TIER]);

    e->facing = 1;
    env_obs(e, &o);
    CHECK(f_eq(o.status[OBS_FACING], 1.0f), "facing right encodes as %g, expected 1",
          o.status[OBS_FACING]);
    e->facing = -1;
    env_obs(e, &o);
    CHECK(f_eq(o.status[OBS_FACING], 0.0f), "facing left encodes as %g, expected 0",
          o.status[OBS_FACING]);

    e->health = MAX_HEALTH / 2;
    env_obs(e, &o);
    CHECK(f_eq(o.status[OBS_HEALTH], 0.5f), "half health encodes as %g, expected 0.5",
          o.status[OBS_HEALTH]);
    e->health = MAX_HEALTH;

    /* Depth and across are normalised over the last valid index, not the size. */
    e->px = WORLD_W - 1;
    e->py = WORLD_H - 1;
    env_obs(e, &o);
    CHECK(f_eq(o.status[OBS_DEPTH], 1.0f), "the bottom row encodes as depth %g, expected 1",
          o.status[OBS_DEPTH]);
    CHECK(f_eq(o.status[OBS_ACROSS], 1.0f), "the last column encodes as across %g, expected 1",
          o.status[OBS_ACROSS]);

    sandbox(e, 60, 50);
    for (int sel = 0; sel < PLACEABLE_COUNT; sel++) {
        e->selected = (uint8_t)sel;
        env_obs(e, &o);
        int hot = 0;
        for (int i = 0; i < PLACEABLE_COUNT; i++)
            if (o.status[OBS_SEL_0 + i] != 0.0f) hot++;
        CHECK(hot == 1, "selecting %s sets %d one-hot slots, expected exactly 1",
              ITEM_NAME[PLACEABLES[sel].item], hot);
        CHECK(f_eq(o.status[OBS_SEL_0 + sel], 1.0f),
              "selecting %s leaves its own slot at %g, expected 1",
              ITEM_NAME[PLACEABLES[sel].item], o.status[OBS_SEL_0 + sel]);
    }

    memset(e->inv, 0, sizeof e->inv);
    e->inv[ITEM_STONE] = OBS_INV_CLIP;
    e->inv[ITEM_WOOD]  = OBS_INV_CLIP + 7;
    e->inv[ITEM_TORCH] = OBS_INV_CLIP / 4;
    env_obs(e, &o);
    CHECK(f_eq(o.status[OBS_INV_0 + ITEM_STONE], 1.0f),
          "a count of exactly OBS_INV_CLIP encodes as %g, expected a saturated 1",
          o.status[OBS_INV_0 + ITEM_STONE]);
    CHECK(f_eq(o.status[OBS_INV_0 + ITEM_WOOD], 1.0f),
          "a count past OBS_INV_CLIP encodes as %g, expected a saturated 1",
          o.status[OBS_INV_0 + ITEM_WOOD]);
    CHECK(f_eq(o.status[OBS_INV_0 + ITEM_TORCH], 0.25f),
          "a quarter of OBS_INV_CLIP encodes as %g, expected 0.25",
          o.status[OBS_INV_0 + ITEM_TORCH]);
    CHECK(f_eq(o.status[OBS_INV_0 + ITEM_ANVIL], 0.0f), "an empty slot encodes as %g, expected 0",
          o.status[OBS_INV_0 + ITEM_ANVIL]);

    e->achievements = 0;
    for (int i = 0; i < ACH_COUNT; i += 3) e->achievements |= 1u << i;
    env_obs(e, &o);
    for (int i = 0; i < ACH_COUNT; i++)
        CHECK(f_eq(o.status[OBS_ACH_0 + i], has_ach(e, i) ? 1.0f : 0.0f),
              "achievement %s reads %g, has_ach says %d",
              ACH_NAME[i], o.status[OBS_ACH_0 + i], has_ach(e, i));

    /* ---- 6. purity ------------------------------------------------------- */

    /* A played-in state, so every field holds something worth corrupting. */
    env_reset(e, 33);
    for (int i = 0; i < 40; i++) env_step(e, i % ACT_COUNT);

    Env *snap = malloc(sizeof *snap);
    if (!snap) { fprintf(stderr, "oom\n"); exit(1); }
    memcpy(snap, e, sizeof *e);
    env_obs(e, &o);
    CHECK(memcmp(snap, e, sizeof *e) == 0, "env_obs mutated the Env it was handed");
    free(snap);

    /* Two calls on one state must agree byte for byte. Both destinations start
       from the same fill so the struct's padding cannot differ. */
    Obs a, b;
    memset(&a, 0xAA, sizeof a);
    memset(&b, 0xAA, sizeof b);
    env_obs(e, &a);
    env_obs(e, &b);
    CHECK(memcmp(&a, &b, sizeof a) == 0, "two env_obs calls on one state disagree");

    /* ---- 7. no stale bytes ----------------------------------------------- */

    /* 0xAA is 170: outside every valid tile id and every light level, so any
       cell env_obs forgets to write is unmistakable. */
    for (int p = 0; p < 3; p++) {
        const char *what = "mid-world";
        switch (p) {
        case 0: sandbox(e, 60, 50); break;
        case 1: bury(e, 44, 66);    what = "buried";      break;
        case 2: sandbox(e, 1, WORLD_H - 3); what = "corner"; break;
        }

        memset(&o, 0xAA, sizeof o);
        env_obs(e, &o);

        int bad_tile = -1, bad_light = -1;
        for (int k = 0; k < VIEW_CELLS; k++) {
            if (bad_tile < 0 && o.tile[k] >= OBS_TILE_KINDS) bad_tile = k;
            if (bad_light < 0 && o.light[k] > LIGHT_MAX) bad_light = k;
        }
        CHECK(bad_tile < 0, "%s: window cell %d holds tile id %u, outside 0..%d",
              what, bad_tile, o.tile[bad_tile < 0 ? 0 : bad_tile], OBS_TILE_KINDS - 1);
        CHECK(bad_light < 0, "%s: window cell %d holds light %u, above LIGHT_MAX",
              what, bad_light, o.light[bad_light < 0 ? 0 : bad_light]);
    }

    free(e);
}

/* ---- scripted expert ---------------------------------------------------- */

typedef struct {
    bool solved;      /* reached the copper pickaxe */
    bool lantern;     /* placed the lantern: the top of the tech tree */
    int  steps;
    int  achievements;
    int  stage;
    bool died;
    int  death_py;
    int  deepest;
    int  wood;
    int  stone;
    int  hits;
} BotResult;

/* The replay tape is written with keymap.h's action->key table, the same one
   both frontends read keys through, so a tape cannot drift from the bindings.
   test_keymap() holds the round-trip. */
static char g_rec[1 << 17];
static int  g_recn;
static bool g_recording;

/* Every bot action funnels through here so the replay tape stays in sync with
   the simulation. Shadowing env_step keeps the stage machine readable. */
static void bot_step(Env *e, int a) {
    if (g_recording && a >= 0 && a < ACT_COUNT && g_recn < (int)sizeof g_rec - 1)
        g_rec[g_recn++] = kb_key(a);
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

/* Adjacency preference. Body-level sides come first because clearing them is
   also what opens the tunnel we are about to walk down; straight down next,
   since that is the free controlled descent; the diagonals and the ceiling
   last, as reaching those costs a jump to exploit. */
static const int REACH_PREF[REACH_COUNT] = {5, 6, 8, 3, 4, 7, 9, 1, 0, 2};

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

/* The body is PLAYER_H tall, so a sideways step needs the whole destination
   column clear -- clearing only the foot cell wedges the bot against its own
   head, which is the classic way a 1-tall-era bot dies of old age. */
static bool side_clear(const Env *e, int dir) {
    return body_fits(e, e->px + dir, e->py);
}

/* Mirror of the engine's auto step-up so the bot knows when a solid foot cell
   is still walkable and must not be mined. */
static bool can_step_up(const Env *e, int dir) {
    return tile_solid(tile_at(e, e->px, e->py + 1)) &&
           body_fits(e, e->px + dir, e->py - 1) &&
           !tile_solid(tile_at(e, e->px, e->py - PLAYER_H));
}

/* Cut one cell out of the neighbouring column. Returns false without spending
   a step when what blocks us is above our tier. */
static bool dig_side(Env *e, int dir) {
    int x = e->px + dir;
    if (tile_solid(tile_at(e, x, e->py))) {
        if (!mineable(e, x, e->py)) return false;
        env_step(e, dir > 0 ? ACT_MINE_FOOT_RIGHT : ACT_MINE_FOOT_LEFT);
        return true;
    }
    if (tile_solid(tile_at(e, x, e->py - 1))) {
        if (!mineable(e, x, e->py - 1)) return false;
        env_step(e, dir > 0 ? ACT_MINE_HEAD_RIGHT : ACT_MINE_HEAD_LEFT);
        return true;
    }
    return false;
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
    /* Any bulk block will do, so never spend a step cycling the hotbar: if
       what is already selected is placeable, drop that. Mid-fall each wasted
       step is another tile of drop, and a 2-tall body has no wall-cling to
       buy the time back. */
    Item cur = PLACEABLES[e->selected].item;
    if (e->inv[cur] > (cur == ITEM_WOOD ? 2 : 0) &&
        (cur == ITEM_DIRT || cur == ITEM_STONE || cur == ITEM_WOOD)) {
        env_step(e, ACT_PLACE_DOWN);
        return true;
    }
    /* Wood is the early-game fallback: before the first shaft the bot owns no
       dirt or stone, and that is exactly when surface caves swallow it. */
    Item want = ITEM_STONE;
    if (e->inv[ITEM_DIRT] > 0)       want = ITEM_DIRT;
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

static void dig_down_safe(Env *e);

/* Gain one tile of height. Grid physics gives no wall-cling, so the only way
   up an open shaft is Terraria's pillar jump: leap, then build under yourself
   at the apex. Jump clearance is measured above the HEAD, so the cell the bot
   has to keep open is (px, py - PLAYER_H), not the one over its feet. */
static void climb(Env *e) {
    if (tile_solid(tile_at(e, e->px, e->py - PLAYER_H))) {
        if (mineable(e, e->px, e->py - PLAYER_H)) env_step(e, ACT_MINE_UP);
        else dig_down_safe(e);          /* capped by rock: go under it instead */
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
    if (!dig_side(e, dir)) env_step(e, dir > 0 ? ACT_RIGHT : ACT_LEFT);
}

/* One step of greedy dig-toward-target. Always consumes exactly one step. */
static void step_toward(Env *e, int tx, int ty) {
    if (e->px != tx) {
        int dir = tx > e->px ? 1 : -1;
        if (!side_clear(e, dir) && !can_step_up(e, dir)) {
            if (dig_side(e, dir)) return;
            /* Rock we cannot break. Go over it when the goal is level or
               above, under it otherwise -- and never grind sideways against
               it. One tile of altitude demotes a head-height obstruction to a
               foot-height one, which is the only reason a 2-tall body ever
               gets past a gold seam it has no pickaxe for. */
            if (ty <= e->py) climb(e);
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

/* The best reach slot currently holding tile `t`, or -1. With `keep_footing`
   the three cells below the feet are off limits. */
static int reach_slot(const Env *e, Tile t, bool keep_footing) {
    for (int k = 0; k < REACH_COUNT; k++) {
        int i = REACH_PREF[k];
        if (keep_footing && REACH_DY[i] > 0) continue;
        if (tile_at(e, e->px + REACH_DX[i], e->py + REACH_DY[i]) == t) return i;
    }
    return -1;
}

/* Mine the named tile wherever it is: in reach first, else navigate to the
   nearest one. Returns false only when the world holds none. */
static bool harvest(Env *e, Tile t, Target *tg) {
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

    /* Target selection comes first so the reach scan knows which way we are
       headed. While the goal is above us the cells under the feet are our
       footing, not loot: mining them undoes the climb we just paid for.
       Splitting logs from planks retires the worst case -- a tree run can no
       longer chase the pillar it built, because place_below lays TILE_WOOD
       while only TILE_LOG is ever a wood target -- but stone is still both a
       harvest target and the bot's pillar stock, so S_STONE would rebuild the
       same hover loop without this rule. It stays. */
    if (tile_tier(t) <= e->tool_tier) {
        int i = reach_slot(e, t, tg->y < e->py);
        if (i >= 0) { env_step(e, ACT_MINE_FIRST + i); return true; }
    }

    step_toward(e, tg->x, tg->y);
    return true;
}

/* Stand a station in a free cell beside the feet, `left` first. One step per
   call; false (and no step) when we are not carrying the thing.

   Both flanks are tried, because down in the gold band the near flank is
   routinely ore above our tier while the cell below is bedrock -- grinding at
   that pair is how the bot used to spend a whole stage budget standing still. */
static bool place_beside(Env *e, Item what, bool left) {
    if (e->inv[what] <= 0) return false;
    int first = left ? -1 : 1;

    for (int k = 0; k < 2; k++) {
        int dx = k ? -first : first;
        if (tile_at(e, e->px + dx, e->py) != TILE_AIR) continue;
        if (PLACEABLES[e->selected].item != what) { env_step(e, ACT_SELECT_NEXT); return true; }
        env_step(e, dx > 0 ? ACT_PLACE_FOOT_RIGHT : ACT_PLACE_FOOT_LEFT);
        return true;
    }
    for (int k = 0; k < 2; k++) {
        int dx = k ? -first : first;
        if (!mineable(e, e->px + dx, e->py)) continue;
        env_step(e, dx > 0 ? ACT_MINE_FOOT_RIGHT : ACT_MINE_FOOT_LEFT);
        return true;
    }
    climb(e); /* walled in by rock we cannot break: rise out of the pocket */
    return true;
}

/* Drop a non-solid fixture (torch, lantern) into a free reach slot, preferring
   the cell above the head where nothing else competes for it. */
static void place_fixture(Env *e, Item what) {
    if (PLACEABLES[e->selected].item != what) { env_step(e, ACT_SELECT_NEXT); return; }
    if (tile_at(e, e->px, e->py - PLAYER_H) == TILE_AIR) { env_step(e, ACT_PLACE_UP); return; }
    int i = reach_slot(e, TILE_AIR, false);
    if (i >= 0) { env_step(e, ACT_PLACE_FIRST + i); return; }
    env_step(e, ACT_MINE_UP);
}

/* Mine a station we placed back into the pack, so the same workbench serves
   the whole descent instead of one per rung. */
static bool reclaim(Env *e, Tile t) {
    int i = reach_slot(e, t, false);
    if (i < 0) return false;
    env_step(e, ACT_MINE_FIRST + i);
    return true;
}

/* Park the hotbar on stone before a long descent. Fall-arrest that has to
   cycle the hotbar mid-drop arrives a tile late per cycled slot, and the
   caverns under the iron band are exactly where that is fatal. */
static bool park_hotbar(Env *e) {
    if (e->inv[ITEM_STONE] <= 0 || PLACEABLES[e->selected].item == ITEM_STONE) return false;
    env_step(e, ACT_SELECT_NEXT);
    return true;
}

#define WOOD_TARGET   32   /* 22 goes on recipes; the surplus is fall-arrest stock */
#define STONE_TARGET  30   /* 12 furnace + 5 stone pick, rest is pillar stock */
#define COPPER_TARGET  9   /* 3 bars: copper pick (2) + torches (1) */
#define IRON_TARGET   21   /* 7 bars: anvil (5) + iron pick (2) */
#define GOLD_TARGET    3   /* 1 bar: the lantern */
#define IRON_BARS      7
#define GOLD_BARS      1

/* Rungs of the tech tree, in the order the bot climbs them. */
enum {
    S_WOOD, S_STONE, S_BENCH, S_PACK_BENCH, S_COPPER, S_SMELT_COPPER,
    S_COPPER_PICK, S_TORCH, S_IRON, S_SMELT_IRON, S_ANVIL, S_IRON_PICK,
    S_GOLD, S_SMELT_GOLD, S_LANTERN, S_DONE
};

#define BOT_BUDGET  40000
#define STAGE_LIMIT  3500  /* abandon a rung rather than burn the whole budget */

static BotResult bot_play(Env *e, uint64_t seed, int budget) {
    env_reset(e, seed);
    BotResult r = {0};
    int stage = S_WOOD, stuck = 0, stage_entry = 0;
    Target tgt = {.rs = seed * 2654435761u + 12345u};
    int last_hp = MAX_HEALTH;
    int deepest = e->py;

    while (alive(e) && e->steps < budget && stage < S_DONE) {
        int before = e->steps;
        int prev_stage = stage;

        /* Universal safety net: never let a fall finish if it would cost hp. */
        if (falling_danger(e)) {
            arrest_fall(e);
            if (e->health < last_hp) { r.hits++; last_hp = e->health; }
            continue;
        }

        switch (stage) {
        case S_WOOD: /* chop trunks: worldgen grows logs, never planks */
            /* Two spadefuls of dirt before anything else. With an empty pack
               the first surface cave the bot walks into is unarrestable, and
               that is the only way a run dies before it has begun. */
            if (e->inv[ITEM_DIRT] < 2 && e->inv[ITEM_STONE] == 0 && e->inv[ITEM_WOOD] <= 2) {
                dig_down_safe(e);
                break;
            }
            if (e->inv[ITEM_WOOD] >= WOOD_TARGET) { stage = S_STONE; break; }
            if (!harvest(e, TILE_LOG, &tgt)) stage = S_STONE;
            break;

        case S_STONE: /* sink a shaft until we have stone */
            if (e->inv[ITEM_STONE] >= STONE_TARGET) { stage = S_BENCH; break; }
            if (!harvest(e, TILE_STONE, &tgt)) dig_down_safe(e);
            break;

        case S_BENCH: /* first placed block, then bench up and make a stone pick */
            if (!has_ach(e, ACH_PLACE_BLOCK)) {
                place_fixture(e, ITEM_STONE);
                break;
            }
            if (e->inv[ITEM_WORKBENCH] == 0 && !station_near(e, TILE_WORKBENCH)) {
                env_step(e, ACT_CRAFT_WORKBENCH);
                break;
            }
            if (!station_near(e, TILE_WORKBENCH)) {
                if (!place_beside(e, ITEM_WORKBENCH, true)) stage = S_PACK_BENCH;
                break;
            }
            if (e->tool_tier < TIER_STONE_PICK) { env_step(e, ACT_CRAFT_STONE_PICK); break; }
            if (e->inv[ITEM_FURNACE] == 0 && !has_ach(e, ACH_CRAFT_FURNACE)) {
                env_step(e, ACT_CRAFT_FURNACE);
                break;
            }
            stage = S_PACK_BENCH;
            break;

        case S_PACK_BENCH: /* pick the workbench back up and carry it down */
            if (!reclaim(e, TILE_WORKBENCH)) stage = S_COPPER;
            break;

        case S_COPPER: /* mine copper */
            if (e->inv[ITEM_COPPER_ORE] >= COPPER_TARGET) { stage = S_SMELT_COPPER; break; }
            if (!harvest(e, TILE_COPPER_ORE, &tgt)) stage = S_SMELT_COPPER;
            break;

        case S_SMELT_COPPER: /* smelt three bars beside a furnace, then pack it */
            if (e->inv[ITEM_COPPER_BAR] >= 3 || e->inv[ITEM_COPPER_ORE] < 3) {
                if (!reclaim(e, TILE_FURNACE)) stage = S_COPPER_PICK;
                break;
            }
            if (!station_near(e, TILE_FURNACE)) {
                if (!place_beside(e, ITEM_FURNACE, true)) stage = S_COPPER_PICK;
                break;
            }
            env_step(e, ACT_SMELT_COPPER);
            break;

        case S_COPPER_PICK: /* copper pickaxe and torches */
            if (e->tool_tier >= TIER_COPPER_PICK && has_ach(e, ACH_CRAFT_TORCH)) {
                if (!reclaim(e, TILE_WORKBENCH)) stage = S_TORCH;
                break;
            }
            if (!station_near(e, TILE_WORKBENCH)) {
                if (!place_beside(e, ITEM_WORKBENCH, false)) stage = S_TORCH;
                break;
            }
            if (e->tool_tier < TIER_COPPER_PICK) { env_step(e, ACT_CRAFT_COPPER_PICK); break; }
            env_step(e, ACT_CRAFT_TORCH);
            break;

        case S_TORCH: /* light the shaft, then square away for the descent */
            if (!has_ach(e, ACH_PLACE_TORCH) && e->inv[ITEM_TORCH] > 0) {
                place_fixture(e, ITEM_TORCH);
                break;
            }
            if (!park_hotbar(e)) stage = S_IRON;
            break;

        case S_IRON: /* iron needs the copper pick, and lives below y=62 */
            if (e->inv[ITEM_IRON_ORE] >= IRON_TARGET) { stage = S_SMELT_IRON; break; }
            if (!harvest(e, TILE_IRON_ORE, &tgt)) stage = S_SMELT_IRON;
            break;

        case S_SMELT_IRON:
            if (e->inv[ITEM_IRON_BAR] >= IRON_BARS || e->inv[ITEM_IRON_ORE] < 3) {
                if (!reclaim(e, TILE_FURNACE)) stage = S_ANVIL;
                break;
            }
            if (!station_near(e, TILE_FURNACE)) {
                if (!place_beside(e, ITEM_FURNACE, true)) stage = S_ANVIL;
                break;
            }
            env_step(e, ACT_SMELT_IRON);
            break;

        case S_ANVIL: /* the anvil is a workbench recipe; the pick is not */
            if (!has_ach(e, ACH_CRAFT_ANVIL)) {
                if (e->inv[ITEM_IRON_BAR] < 5) { stage = S_DONE; break; }
                if (!station_near(e, TILE_WORKBENCH)) {
                    if (!place_beside(e, ITEM_WORKBENCH, false)) stage = S_DONE;
                    break;
                }
                env_step(e, ACT_CRAFT_ANVIL);
                break;
            }
            if (!station_near(e, TILE_ANVIL)) {
                if (!place_beside(e, ITEM_ANVIL, true)) stage = S_IRON_PICK;
                break;
            }
            stage = S_IRON_PICK;
            break;

        case S_IRON_PICK:
            if (e->tool_tier >= TIER_IRON_PICK) {
                /* Carry the anvil down: the lantern is forged at the bottom. */
                if (reclaim(e, TILE_ANVIL)) break;
                if (!park_hotbar(e)) stage = S_GOLD;
                break;
            }
            if (!station_near(e, TILE_ANVIL)) {
                if (!place_beside(e, ITEM_ANVIL, true)) stage = S_DONE;
                break;
            }
            env_step(e, ACT_CRAFT_IRON_PICK);
            break;

        case S_GOLD: /* the deep band, gated by the iron pickaxe */
            if (e->inv[ITEM_GOLD_ORE] >= GOLD_TARGET && has_ach(e, ACH_DESCEND_DEEP)) {
                stage = S_SMELT_GOLD;
                break;
            }
            if (e->inv[ITEM_GOLD_ORE] < GOLD_TARGET && harvest(e, TILE_GOLD_ORE, &tgt)) break;
            /* No gold left in the world: at least bank the depth achievement. */
            if (!has_ach(e, ACH_DESCEND_DEEP)) { dig_down_safe(e); break; }
            stage = S_SMELT_GOLD;
            break;

        case S_SMELT_GOLD:
            if (e->inv[ITEM_GOLD_BAR] >= GOLD_BARS || e->inv[ITEM_GOLD_ORE] < 3) {
                stage = S_LANTERN;
                break;
            }
            if (!station_near(e, TILE_FURNACE)) {
                if (!place_beside(e, ITEM_FURNACE, true)) stage = S_LANTERN;
                break;
            }
            env_step(e, ACT_SMELT_GOLD);
            break;

        case S_LANTERN:
            if (!has_ach(e, ACH_CRAFT_LANTERN)) {
                if (e->inv[ITEM_GOLD_BAR] == 0) { stage = S_DONE; break; }
                if (!station_near(e, TILE_ANVIL)) {
                    if (!place_beside(e, ITEM_ANVIL, false)) stage = S_DONE;
                    break;
                }
                env_step(e, ACT_CRAFT_LANTERN);
                break;
            }
            if (has_ach(e, ACH_PLACE_LANTERN)) { stage = S_DONE; break; }
            place_fixture(e, ITEM_LANTERN);
            break;
        }

        if (e->py > deepest) deepest = e->py;
        if (e->health < last_hp) { r.hits++; last_hp = e->health; }
        if (e->health > last_hp) last_hp = e->health;

        if (stage != prev_stage) {
            stage_entry = e->steps;
        } else if (e->steps - stage_entry > STAGE_LIMIT) {
            stage++;                        /* rung refuses to yield; move on */
            stage_entry = e->steps;
        }

        /* A stage that neither acts nor advances is a live-lock; a handful of
           free transitions in a row is normal, two hundred is not. */
        if (e->steps == before) { if (++stuck > 200) break; }
        else stuck = 0;
    }

    r.wood = e->inv[ITEM_WOOD];
    r.stone = e->inv[ITEM_STONE];
    r.death_py = e->py;
    r.deepest = deepest;
    r.steps = e->steps;
    r.stage = stage;
    r.died = e->terminated;
    r.achievements = __builtin_popcount(e->achievements);
    r.solved = has_ach(e, ACH_CRAFT_COPPER_PICK);
    r.lantern = has_ach(e, ACH_PLACE_LANTERN);
    return r;
}

#undef env_step

static void record_run(uint64_t seed) {
    Env *e = env_new(BOT_BUDGET);
    g_recording = true;
    g_recn = 0;
    BotResult r = bot_play(e, seed, BOT_BUDGET);
    g_rec[g_recn] = 0;
    fprintf(stderr, "seed %llu: %d/%d achievements in %d steps%s\n",
            (unsigned long long)seed, r.achievements, ACH_COUNT, r.steps,
            r.died ? " (died)" : "");
    printf("%s\n", g_rec);
    free(e);
}

static void test_beatable(int nseeds, int verbose) {
    printf("scripted expert (%d seeds, omniscient ore search)\n", nseeds);
    Env *e = env_new(BOT_BUDGET);
    int solved = 0, lanterns = 0, full = 0, died = 0;
    long steps_sum = 0, ach_sum = 0;
    int steps_min = 1 << 30, steps_max = 0;
    int stage_hist[S_DONE + 1] = {0};

    for (int i = 0; i < nseeds; i++) {
        BotResult r = bot_play(e, (uint64_t)(i + 1), BOT_BUDGET);
        stage_hist[r.stage]++;
        ach_sum += r.achievements;
        if (r.died) died++;
        if (r.lantern) lanterns++;
        if (r.solved) {
            solved++;
            steps_sum += r.steps;
            if (r.steps < steps_min) steps_min = r.steps;
            if (r.steps > steps_max) steps_max = r.steps;
        }
        if (r.achievements == ACH_COUNT) full++;
        if (verbose)
            printf("  seed %2d: stage %2d, %2d/%d ach, %5d steps, wood %d stone %d, "
                   "hits %d, deepest y=%d%s\n",
                   i + 1, r.stage, r.achievements, ACH_COUNT, r.steps, r.wood,
                   r.stone, r.hits, r.deepest, r.died ? ", DIED" : "");
    }

    printf("  copper pickaxe: %d/%d   lantern placed: %d/%d   full clear: %d/%d   died: %d\n",
           solved, nseeds, lanterns, nseeds, full, nseeds, died);
    printf("  mean achievements: %.1f/%d\n", (double)ach_sum / nseeds, ACH_COUNT);
    if (solved)
        printf("  steps to copper pickaxe: min %d, mean %ld, max %d\n",
               steps_min, steps_sum / solved, steps_max);
    printf("  stopped at stage: ");
    for (int s = 0; s <= S_DONE; s++) if (stage_hist[s]) printf("%d:%d ", s, stage_hist[s]);
    printf("\n");

    CHECK(solved * 100 >= nseeds * 80, "only %d/%d seeds reached a copper pickaxe",
          solved, nseeds);
    free(e);
}

/* The mask predicates in sim.c deliberately duplicate the guard clauses in the
   do_* handlers, because the handlers each report a distinct failure message
   and cannot simply return a bool. This pins the copy to the original.

   The test cannot diff raw Env states: env_step also runs physics, which moves
   the player whether or not the action did anything. So it uses the definition
   that actually matters -- an inert action is one that is INDISTINGUISHABLE
   FROM NOOP. Step two copies, one with the action and one with noop, and the
   states must match exactly iff the mask said the action was invalid. */
static void test_action_mask(void) {
    printf("action mask\n");
    Env *base = env_new(0), *wa = env_new(0), *wn = env_new(0);
    uint8_t mask[ACT_COUNT];
    long inert = 0, total = 0;

    for (uint64_t seed = 1; seed <= 12; seed++) {
        env_reset(base, seed);
        uint64_t s = seed * 7919u + 13u;

        for (int t = 0; t < 300 && alive(base); t++) {
            env_action_mask(base, mask);

            CHECK(mask[ACT_NOOP] == 1, "seed %llu: noop masked off -- the mask "
                  "must never be empty", (unsigned long long)seed);

            /* ACT_NOOP is exempt: it is the always-available safety valve, and
               by construction it is the thing everything else is compared to. */
            for (int a = 1; a < ACT_COUNT; a++) {
                *wa = *base;
                *wn = *base;
                env_step(wa, a);
                env_step(wn, ACT_NOOP);

                /* `facing` is observational only and `msg` is human text; a
                   move into a wall sets both and changes nothing real. */
                wa->facing = wn->facing = 0;
                memset(wa->msg, 0, sizeof wa->msg);
                memset(wn->msg, 0, sizeof wn->msg);

                bool changed = memcmp(wa, wn, sizeof(Env)) != 0;
                total++;
                if (!changed) inert++;
                if (changed != (mask[a] != 0)) {
                    CHECK(false, "seed %llu step %d: %s -- mask says %s but it "
                          "%s the state", (unsigned long long)seed, t,
                          action_name(a), mask[a] ? "valid" : "inert",
                          changed ? "changed" : "did not change");
                    goto done;   /* one report is enough; the rest would echo */
                }
            }

            s = s * 6364136223846793005ULL + 1442695040888963407ULL;
            env_step(base, (int)((s >> 33) % ACT_COUNT));
        }
    }
done:
    printf("  %ld/%ld action-states inert (%.0f%%) -- that is the tax masking "
           "removes\n", inert, total, 100.0 * (double)inert / (double)total);
    free(base);
    free(wa);
    free(wn);
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
    test_wood_split();
    test_body();
    test_keymap();
    test_reach();
    test_obs();
    test_action_mask();
    test_fall_damage();
    test_lighting();
    test_beatable(nseeds, verbose);

    printf("\n%s (%d failures)\n", failures ? "FAILED" : "all checks passed", failures);
    return failures ? 1 : 0;
}
