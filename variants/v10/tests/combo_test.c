/* COMBO_ACTIONS fixtures (env.h): every combo performs its movement and its
   use in the same step, each as the standalone action would (a place combo
   also places later in the step, once its cell takes the block); masks;
   determinism and save/load with combos in the stream; and the scripted
   pillaring check (32 worlds and open air, with and without combos).
   sim.c is included for its static internals, so build it as one unit:

     cc -std=c11 -O2 -DCOMBO_ACTIONS=1 -Ivariants/v10/include -Ivariants/v10/src \
        variants/v10/tests/combo_test.c variants/v10/src/{worldgen,light,obs}.c -o /tmp/v10-combo -lm \
        && /tmp/v10-combo

   Prints one "PASS|FAIL name: detail" line per check, exits 1 on a failure. */
#include <stdarg.h>
#include "sim.c"
#include "mobs.c"
#include "boss.c"

#if !COMBO_ACTIONS
#error "build with -DCOMBO_ACTIONS=1"
#endif

static int failures, checks;
static void check(bool ok, const char *name, const char *fmt, ...) {
    char buf[320]; va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    printf("%s %s: %s\n", ok ? "PASS" : "FAIL", name, buf);
    failures += !ok; checks++;
}

static Env base, A, B, C;

/* Empty air world without background walls, stone floor at `floor_row`,
   player standing at column 60, no mobs/chests/boss, fully lit, 50 dirt
   selected. */
static void flat_world(Env *e, int floor_row) {
    env_reset(e, 7);
    for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) {
        e->tiles[y][x] = y >= WORLD_H - BEDROCK_ROWS ? TILE_BEDROCK : y >= floor_row ? TILE_STONE : TILE_AIR;
        e->object_part[y][x] = 0;
#if BG_WALLS
        e->wall[y][x] = WALL_NONE;
#endif
    }
    for (int x = 0; x < WORLD_W; x++) e->surface[x] = floor_row;
    memset(e->mobs, 0, sizeof e->mobs); memset(&e->boss, 0, sizeof e->boss); e->chest_count = 0;
    e->px = 60; e->py = floor_row - 1; e->facing = 1;
    e->inv[ITEM_DIRT] = 50;
    for (int i = 0; i < PLACEABLE_COUNT; i++) if (PLACEABLES[i].item == ITEM_DIRT) e->selected = (uint8_t)i;
    e->terrain_dirty = true; light_recompute(e);
    for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) e->light[y][x] = LIGHT_MAX;
    e->pos_x = (e->px * 16 + 6) * FIX_ONE; e->pos_y = ((e->py + 1) * 16 - PLAYER_PX_H) * FIX_ONE;
    e->vel_x = e->vel_y = 0; e->jump = 0; e->fall_start = ftile(e->pos_y); e->release_jump = true; e->pulley = false;
    e->hold_jump = false;
    e->steps = 1; e->max_steps = 1 << 30;
}
/* A dirt wall behind every cell: blocks may then be placed in mid-air. */
static void wall_all(Env *e) {
#if BG_WALLS
    memset(e->wall, WALL_DIRT, sizeof e->wall);
#else
    (void)e;
#endif
}

/* One action with mob spawning held off (spawn steps are multiples of 60);
   the full light map stays lit so masks never see hidden cells. */
static void act(Env *e, int a) {
    e->steps = 1; env_step(e, a);
    for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) e->light[y][x] = LIGHT_MAX;
}
static bool same_tiles(const Env *a, const Env *b) { return !memcmp(a->tiles, b->tiles, sizeof a->tiles); }
static bool same_inv(const Env *a, const Env *b) { return !memcmp(a->inv, b->inv, sizeof a->inv); }
static bool same_pos(const Env *a, const Env *b) { return a->pos_x == b->pos_x && a->pos_y == b->pos_y && a->vel_x == b->vel_x && a->vel_y == b->vel_y; }
static int use_of(int combo) { return COMBOS[combo - ACT_COMBO_FIRST].use; }
/* The standalone action holding the same movement: jump alone presses or
   continues a jump; left/right alone keep a jump that is still running
   (the combo's own jump press is inert in the air once the jump is spent). */
static int move_of(int combo) {
    int m = COMBOS[combo - ACT_COMBO_FIRST].move;
    return (m & COMBO_L) ? ACT_LEFT : (m & COMBO_R) ? ACT_RIGHT : ACT_JUMP;
}

/* Combo vs standalone use (B) and standalone movement (C) from one state:
   the use's effect (tiles, inventory, swing) equals B's, the motion C's. */
static void compare_step(int combo, const char *scene, bool expect_motion) {
    A = base; B = base; C = base;
    act(&A, combo); act(&B, use_of(combo)); act(&C, move_of(combo));
    bool use_ok = same_tiles(&A, &B) && same_inv(&A, &B) && A.item_anim == B.item_anim;
    bool move_ok = same_pos(&A, &C);
    bool moved = A.pos_x != base.pos_x || A.pos_y != base.pos_y;
    bool used = !same_tiles(&A, &base) || !same_inv(&A, &base) || A.item_anim != base.item_anim
             || A.dig_x != base.dig_x || A.dig_y != base.dig_y;
    check(use_ok && move_ok && used && moved == expect_motion, action_name(combo),
          "%s: use=B %d, motion=C %d, use happened %d, moved %d (expect %d)",
          scene, use_ok, move_ok, used, moved, expect_motion);
}

static void test_one_step(void) {
    /* Attacks in the open with the copper broadsword (20-tick use, so the
       swing is still running at the step end): the swing starts, the body
       runs/jumps. */
    flat_world(&base, 100);
    base.weapon = 1; base.inv[WEAPON_ITEM[1]] = 1;
    compare_step(ACT_LEFT_ATTACK, "open floor", true);
    compare_step(ACT_RIGHT_ATTACK, "open floor", true);
    compare_step(ACT_JUMP_ATTACK, "open floor", true);
    A = base; act(&A, ACT_LEFT_ATTACK);
    check(A.facing == -1 && A.item_anim > 0, "left + attack faces left", "facing %d, item_anim %d", A.facing, A.item_anim);

    /* Places mid-air, one step after a jump, in front of a background wall:
       the standalone place is legal at the step start, so the combo places
       there too (down-left / down-right for the bridging pair) while the
       body flies on. */
    flat_world(&base, 100); wall_all(&base); act(&base, ACT_JUMP);
    compare_step(ACT_JUMP_PLACE_DOWN, "mid-air", true);
    compare_step(ACT_LEFT_JUMP_PLACE_DOWN_LEFT, "mid-air", true);
    compare_step(ACT_RIGHT_JUMP_PLACE_DOWN_RIGHT, "mid-air", true);
    A = base; act(&A, ACT_JUMP_PLACE_DOWN);
    check(A.tiles[base.py + 1][base.px] == TILE_DIRT && A.inv[ITEM_DIRT] == 49, "jump + place down puts dirt under the feet",
          "tile %d, dirt %d", A.tiles[base.py + 1][base.px], A.inv[ITEM_DIRT]);

    /* Held place in open air (no walls): from a standing start, jump + place
       down drops one dirt into the cell the feet just left (anchored on the
       floor) and the body lands on it, one row up. The standalone pair can't:
       place down is blocked on the ground, and after a jump step the cell
       under the feet floats. */
    flat_world(&base, 100);
    A = base; act(&A, ACT_JUMP_PLACE_DOWN);
    int placed_tick = A.tiles[99][60] == TILE_DIRT || A.tiles[99][61] == TILE_DIRT;
    for (int i = 0; i < 6; i++) act(&A, ACT_NOOP);
    B = base; act(&B, ACT_PLACE_DOWN); act(&B, ACT_JUMP); act(&B, ACT_PLACE_DOWN);
    for (int i = 0; i < 6; i++) act(&B, ACT_NOOP);
    check(placed_tick && A.inv[ITEM_DIRT] == 49 && A.py == 98 && B.inv[ITEM_DIRT] == 50 && B.py == 99,
          "jump + place down pillars one row in open air", "combo: placed %d, dirt %d, py %d; alone: dirt %d, py %d",
          placed_tick, A.inv[ITEM_DIRT], A.py, B.inv[ITEM_DIRT], B.py);

    /* Side mining against a stone wall touching the body (left of column 60,
       right of column 61): the run presses into the wall and does not move
       the body cell, so every step's hits equal the standalone mine's until
       the tile breaks. */
    static const int side[] = {ACT_LEFT_MINE_HEAD_LEFT, ACT_LEFT_MINE_MIDDLE_LEFT, ACT_LEFT_MINE_FOOT_LEFT,
                               ACT_RIGHT_MINE_HEAD_RIGHT, ACT_RIGHT_MINE_MIDDLE_RIGHT, ACT_RIGHT_MINE_FOOT_RIGHT};
    for (int k = 0; k < 6; k++) {
        flat_world(&base, 100);
        for (int y = 90; y < 100; y++) base.tiles[y][59] = base.tiles[y][62] = TILE_STONE;
        compare_step(side[k], "first step against the wall", true);
        A = base; B = base;
        int r = use_of(side[k]) - ACT_MINE_FIRST, tx = base.px + REACH_DX[r], ty = base.py + REACH_DY[r];
        int broke_a = -1, broke_b = -1; bool eq = true;
        for (int s = 0; s < 20 && (broke_a < 0 || broke_b < 0); s++) {
            if (broke_a < 0) act(&A, side[k]);
            if (broke_b < 0) act(&B, use_of(side[k]));
            if (broke_a < 0 && A.tiles[ty][tx] == TILE_AIR) broke_a = s;
            if (broke_b < 0 && B.tiles[ty][tx] == TILE_AIR) broke_b = s;
            if (broke_a < 0 && broke_b < 0) eq &= !memcmp(A.hits, B.hits, sizeof A.hits) && same_tiles(&A, &B);
        }
        check(broke_a >= 0 && broke_a == broke_b && eq && same_tiles(&A, &B) && same_inv(&A, &B), action_name(side[k]),
              "stone at reach %s broken after %d / %d steps (combo / alone)", REACH_NAME[r], broke_a + 1, broke_b + 1);
    }

    /* Jump + mine up under one stone ceiling tile over the left column (the
       head bumps it): breaks in the same step as mine up alone, then jumping
       carries the body up through the hole. */
    flat_world(&base, 100);
    base.tiles[96][60] = TILE_STONE;
    compare_step(ACT_JUMP_MINE_UP, "under a ceiling tile (bumps, lands back)", false);
    {
        A = base; B = base;
        int r = ACT_MINE_UP - ACT_MINE_FIRST, tx = base.px + REACH_DX[r], ty = base.py + REACH_DY[r];
        int broke_a = -1, broke_b = -1;
        for (int s = 0; s < 20 && (broke_a < 0 || broke_b < 0); s++) {
            if (broke_a < 0) { act(&A, ACT_JUMP_MINE_UP); if (A.tiles[ty][tx] == TILE_AIR) broke_a = s; }
            if (broke_b < 0) { act(&B, ACT_MINE_UP);      if (B.tiles[ty][tx] == TILE_AIR) broke_b = s; }
        }
        A.steps = 1; for (int i = 0; i < 2; i++) act(&A, ACT_JUMP);
        check(broke_a >= 0 && broke_a == broke_b && A.py < base.py, "jump + mine up",
              "ceiling broken after %d / %d steps (combo / alone); then py %d -> %d", broke_a + 1, broke_b + 1, base.py, A.py);
    }

    /* Running jumps: one step both rises (as jump alone) and runs (as the
       run alone); air and ground acceleration are the same here. */
    flat_world(&base, 100);
    for (int d = 0; d < 2; d++) {
        int combo = d ? ACT_RIGHT_JUMP : ACT_LEFT_JUMP;
        A = base; B = base; C = base;
        act(&A, combo); act(&B, ACT_JUMP); act(&C, d ? ACT_RIGHT : ACT_LEFT);
        check(A.pos_y == B.pos_y && A.pos_x == C.pos_x && A.pos_y < base.pos_y, action_name(combo),
              "dy %d px (jump alone %d), dx %d px (run alone %d)", (int)((A.pos_y - base.pos_y) >> 16), (int)((B.pos_y - base.pos_y) >> 16),
              (int)((A.pos_x - base.pos_x) >> 16), (int)((C.pos_x - base.pos_x) >> 16));
    }

    /* A combo swing hits what its run faces: a zombie on the left, player
       facing right. Attack alone swings right and misses. */
    flat_world(&base, 100);
    Mob *m = &base.mobs[0];
    *m = MOB_INIT(0, 0, 1000, 0, 0, 1, MOB_ZOMBIE);
    m->fx = player_fx(&base) - 24 * FIX_ONE; m->fy = player_fy(&base) + (PLAYER_PX_H - MOB_H[MOB_ZOMBIE]) * FIX_ONE;
    m->vx = m->vy = 0; mob_sync_cell(m);
    A = base; B = base;
    act(&A, ACT_LEFT_ATTACK); act(&B, ACT_ATTACK);
    check(A.mobs[0].hp < 1000 && B.mobs[0].hp == 1000, "left + attack hits a zombie behind",
          "zombie hp after combo %d, after attack alone %d", A.mobs[0].hp, B.mobs[0].hp);
}

/* Masks over random play on real worlds: attack/mine combos equal their
   use's mask, running jumps jump's, place combos "selected item stocked";
   jump + place down stays legal standing on a floor (the held place lands
   once the jump lifts the feet) and goes illegal with no blocks left. */
static void test_masks(void) {
    uint64_t rng = 99; long mism = 0, n = 0, combos_legal = 0;
    uint8_t mask[ACT_COUNT];
    env_reset(&A, 5);
    for (int t = 0; t < 20000; t++) {
        env_action_mask(&A, mask);
        for (int i = 0; i < COMBO_COUNT; i++) {
            int u = COMBOS[i].use == ACT_NOOP ? ACT_JUMP : COMBOS[i].use;
            bool place = u >= ACT_PLACE_FIRST && u < ACT_PLACE_FIRST + REACH_COUNT;
            int want = place ? A.inv[PLACEABLES[A.selected].item] > 0 : mask[u];
            mism += mask[ACT_COMBO_FIRST + i] != want; n++; combos_legal += mask[ACT_COMBO_FIRST + i];
        }
        int legal[ACT_COUNT], k = 0;
        for (int a = 0; a < ACT_COUNT; a++) if (mask[a]) legal[k++] = a;
        env_step(&A, legal[rng_below(&rng, (uint32_t)k)]);
        if (A.terminated || A.truncated) env_reset(&A, 1000 + (uint64_t)t);
    }
    check(mism == 0 && combos_legal > 0, "combo masks", "%ld mismatches of %ld (legal %ld)", mism, n, combos_legal);
    flat_world(&A, 100); env_action_mask(&A, mask);
    int ground = mask[ACT_JUMP_PLACE_DOWN], alone = mask[ACT_PLACE_DOWN];
    A.inv[ITEM_DIRT] = 0; env_action_mask(&A, mask);
    check(ground && !alone && !mask[ACT_JUMP_PLACE_DOWN] && mask[ACT_LEFT_JUMP] && mask[ACT_LEFT_ATTACK],
          "jump + place down legality", "standing %d (place down alone %d), no dirt %d", ground, alone, mask[ACT_JUMP_PLACE_DOWN]);
}

/* Determinism and save/load with a stream rich in combos. */
static int pick(const Env *e, uint64_t *rng) {
    uint8_t mask[ACT_COUNT]; env_action_mask(e, mask);
    int legal[ACT_COUNT], k = 0, kc = 0, combo[COMBO_COUNT];
    for (int a = 0; a < ACT_COUNT; a++) if (mask[a]) { legal[k++] = a; if (a >= ACT_COMBO_FIRST) combo[kc++] = a; }
    if (kc && rng_below(rng, 2)) return combo[rng_below(rng, (uint32_t)kc)];
    return legal[rng_below(rng, (uint32_t)k)];
}
static void test_determinism(void) {
    static Env snap;
    uint64_t r1 = 3, r2 = 3; bool eq = true;
    env_reset(&A, 11); env_reset(&B, 11);
    for (int t = 0; t < 15000 && eq; t++) {
        int a = pick(&A, &r1), b = pick(&B, &r2);
        env_step(&A, a); env_step(&B, b);
        eq = a == b && !memcmp(&A, &B, sizeof A);
        if (A.terminated || A.truncated) { env_reset(&A, 50 + (uint64_t)t); env_reset(&B, 50 + (uint64_t)t); }
    }
    check(eq, "determinism with combos", "15000 steps, byte-identical Env");
    memcpy(&snap, &A, sizeof A);
    uint64_t rs = r1;
    for (int t = 0; t < 3000; t++) { env_step(&A, pick(&A, &r1)); if (A.terminated || A.truncated) break; }
    memcpy(&C, &snap, sizeof C);
    for (int t = 0; t < 3000; t++) { env_step(&C, pick(&C, &rs)); if (C.terminated || C.truncated) break; }
    check(!memcmp(&A, &C, sizeof A), "save/load with combos", "restored snapshot replays byte-identically");
}

/* Scripted pillaring, up to 400 steps with 200 dirt selected:
     shaft  real world (seed), a 2-wide shaft dug from the surface 30 rows
            down at the spawn (it may open into caves); out = feet above the
            surface row
     open   flat floor without walls (the seed only drives the random
            policy); out = 20 rows above the floor
   Policies (P = place down; with combos, P = jump + place down, which holds
   the place over the step and re-presses jump):
     timed   continue a running jump, else P once airborne, else jump
     naive   P whenever legal, else jump
     random  uniform over the legal ones of {noop, jump, place down} (with
             combos also jump + place down): how often blind play gets out */
enum { POL_TIMED, POL_NAIVE, POL_RANDOM };
static int pillar(uint64_t seed, bool open, bool combos, int policy, bool *died) {
    int goal;
    if (open) {
        flat_world(&A, 100);
        goal = 99 - 20;
    } else {
        env_reset(&A, seed);
        int x = A.px, top = A.surface[x] - 1, bottom = A.surface[x] + 30;
        for (int y = 0; y <= bottom; y++) for (int c = x; c < x + PLAYER_W; c++)
            if (y >= top - 12 || A.tiles[y][c] == TILE_LOG) { A.tiles[y][c] = TILE_AIR; A.object_part[y][c] = 0; }
        for (int c = x; c < x + PLAYER_W; c++) A.tiles[bottom + 1][c] = TILE_STONE;
        A.py = bottom;
        A.pos_x = (A.px * 16 + 6) * FIX_ONE; A.pos_y = ((A.py + 1) * 16 - PLAYER_PX_H) * FIX_ONE;
        A.vel_x = A.vel_y = 0; A.jump = 0; A.fall_start = ftile(A.pos_y);
        A.terrain_dirty = true; light_recompute(&A);
        goal = A.surface[x] - 1;
    }
    A.max_steps = 1 << 30;
    A.inv[ITEM_DIRT] = 200;
    for (int i = 0; i < PLACEABLE_COUNT; i++) if (PLACEABLES[i].item == ITEM_DIRT) A.selected = (uint8_t)i;
    uint8_t mask[ACT_COUNT];
    uint64_t rng = seed * 7919;
    *died = false;
    for (int s = 0; s < 400; s++) {
        if (A.py <= goal && A.vel_y == 0) return s;
        env_action_mask(&A, mask);
        int place = combos ? ACT_JUMP_PLACE_DOWN : ACT_PLACE_DOWN, a = ACT_NOOP;
        if (policy == POL_TIMED) {
            if (A.jump > 0) a = ACT_JUMP;
            else if (A.vel_y != 0 && mask[place]) a = place;
            else if (A.vel_y == 0) a = ACT_JUMP;
        } else if (policy == POL_NAIVE) {
            a = mask[place] ? place : ACT_JUMP;
        } else {
            int cand[4] = {ACT_NOOP, ACT_JUMP, ACT_PLACE_DOWN, ACT_JUMP_PLACE_DOWN}, legal[4], k = 0;
            for (int i = 0; i < (combos ? 4 : 3); i++) if (mask[cand[i]]) legal[k++] = cand[i];
            a = legal[rng_below(&rng, (uint32_t)k)];
        }
        if (open) A.steps = 1;   /* mob spawning held off, as act() */
        env_step(&A, a);
        if (open) for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) A.light[y][x] = LIGHT_MAX;
        if (A.terminated) { *died = true; return -1; }
    }
    return -1;
}
static void test_pillar(void) {
    static const char *const pol[] = {"timed", "naive", "random"};
    for (int open = 0; open < 2; open++) for (int p = 0; p < 3; p++) for (int combos = 0; combos < 2; combos++) {
        int ok = 0, deaths = 0; long total = 0;
        for (uint64_t seed = 1; seed <= 32; seed++) {
            bool died; int s = pillar(seed, open, combos, p, &died);
            if (s >= 0) { ok++; total += s; }
            deaths += died;
        }
        printf("PILLAR %-5s %-6s %-9s: %2d/32 out, mean %.1f steps, %d deaths\n", open ? "open" : "shaft",
               pol[p], combos ? "combos" : "no combos", ok, ok ? (double)total / ok : 0.0, deaths);
        if (open && p == POL_NAIVE && combos) check(ok == 32, "open-air pillar with jump + place down", "%d/32", ok);
    }
}

int main(void) {
    test_one_step();
    test_masks();
    test_determinism();
    test_pillar();
    printf("%s: %d/%d checks passed\n", failures ? "FAILED" : "PASSED", checks - failures, checks);
    return failures != 0;
}
