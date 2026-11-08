/* Off-policy rendering fixtures for terraria-px-v10 (make check-pixel-v10).
   Never part of the training environment. Runs the v10 core under the pixel
   renderer: N steps of a seeded random legal policy drawn every step, then a
   night scene with every regular mob kind, a Demon Altar, the Eye of Cthulhu
   (both phases) and the help overlay, and a cavern view of a worldgen altar.
   Each scene is saved as BMP for inspection. Usage: px-v10-selftest [PREFIX] [N] */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "env.h"
#include "px_render.h"

#define SEED 23000001ULL

static void centre(PxView *v, float tx, float ty)
{
    v->cam_x = tx - PX_VIEW_TW / 2.0f;
    v->cam_y = ty - PX_VIEW_TH / 2.0f;
    if (v->cam_x < 0) v->cam_x = 0;
    if (v->cam_y < 0) v->cam_y = 0;
    if (v->cam_x > WORLD_W - PX_VIEW_TW) v->cam_x = WORLD_W - PX_VIEW_TW;
    if (v->cam_y > WORLD_H - PX_VIEW_TH) v->cam_y = WORLD_H - PX_VIEW_TH;
}

/* The frame loop's interpolation at alpha 1: everything where it is. */
static void sync(PxView *v, const Env *e)
{
    int w, h;
    px_feet(e, &v->feet_x, &v->feet_y);
    centre(v, v->feet_x + PLAYER_W / 2.0f, v->feet_y - 0.5f);
    for (int i = 0; i < MAX_MOBS; i++)
        if (e->mobs[i].kind) px_mob_box(&e->mobs[i], &v->mob_x[i], &v->mob_y[i], &w, &h);
    v->boss_x = (float)(e->boss.x * PX_TILE);
    v->boss_y = (float)(e->boss.y * PX_TILE);
    v->walk_dir = e->vel_x > 0 ? 1 : e->vel_x < 0 ? -1 : 0;
    v->airborne = e->vel_y != 0;
}

static void shot(PxUi *ui, const Env *e, const PxView *v, const char *prefix, const char *name)
{
    char path[512];
    px_draw(ui, e, v);
    snprintf(path, sizeof path, "%s-%s.bmp", prefix, name);
    if (!px_screenshot(ui, path)) { fprintf(stderr, "screenshot %s failed\n", path); exit(1); }
    printf("wrote %s\n", path);
}

static uint64_t xs(uint64_t *s) { *s ^= *s << 13; *s ^= *s >> 7; *s ^= *s << 17; return *s; }

int main(int argc, char **argv)
{
    const char *prefix = argc > 1 ? argv[1] : "/tmp/terraria-v10-ui";
    int n = argc > 2 ? atoi(argv[2]) : 600;
    static Env e;
    PxView v;
    uint8_t mask[ACT_COUNT];
    uint64_t rs = 0x9E3779B97F4A7C15ull;
    int drawn[MOB_KINDS] = {0}, boss_frames = 0;

    env_init(&e, (EnvConfig){EPISODE_STEPS});
    env_reset(&e, SEED);
    PxUi *ui = px_init(1, NULL);
    if (!ui) return 1;
    memset(&v, 0, sizeof v);
    v.hover_reach = v.hover_recipe = v.hover_ach = v.hover_slot = v.hover_item = -1;

    /* Hit tests: 21 recipe rows, achievements one row per tier. */
    for (int i = 0; i < RECIPE_COUNT; i++) assert(px_recipe_at(PX_VIEW_W + 10, 18 + i * 19 + 5) == i);
    for (int i = 0, first = 0; i < ACH_COUNT; i++) {
        if (i > 0 && ACH_TIER[i] != ACH_TIER[i - 1]) first = i;
        int ay = 18 + RECIPE_COUNT * 19 + 22 + (ACH_TIER[i] - 1) * 16 + 2;
        assert(px_ach_at(PX_VIEW_W + 10 + (i - first) * 16 + 2, ay) == i);
    }

    /* 1. Real steps: a seeded random legal policy biased to moving and digging;
       a finished episode continues in the next world. */
    for (int s = 0, deaths = 0; s < n; s++) {
        int act;
        if (e.terminated || e.truncated) {
            printf("step %d: episode over (%s), new world\n", s, e.msg);
            env_reset(&e, SEED + (uint64_t)++deaths);
        }
        env_action_mask(&e, mask);
        do {
            uint64_t r = xs(&rs) % 100;
            act = r < 30 ? ACT_RIGHT : r < 45 ? ACT_LEFT : r < 55 ? ACT_JUMP
                : r < 70 ? ACT_MINE_FIRST + (int)(xs(&rs) % REACH_COUNT)
                : r < 78 ? ACT_ATTACK : (int)(xs(&rs) % ACT_COUNT);
        } while (!mask[act]);
        env_step(&e, act);
        sync(&v, &e);
        v.clock = s * 0.25;
        px_draw(ui, &e, &v);
    }
    printf("%d steps drawn: day %d, y %d, %d achievements\n", n,
           e.steps / DAY_CYCLE + 1, e.py, __builtin_popcountll(e.achievements));
    shot(ui, &e, &v, prefix, "steps");

    /* 2. Night on the surface: every regular mob kind, a Demon Altar, the boss. */
    env_reset(&e, SEED);
    e.steps = DAY_STEPS + 40;
    assert(is_night(&e));
    {
        int left = e.px + 4, bottom = e.py;
        for (int y = bottom - 1; y <= bottom; y++)
            for (int x = left; x < left + 3; x++) env_object_remove(&e, x, y);
        assert(env_object_write(&e, TILE_DEMON_ALTAR, left, bottom));
        static const int kinds[] = {MOB_BLUE_SLIME, MOB_CAVE_BAT, MOB_ZOMBIE, MOB_DEMON_EYE, MOB_SKELETON};
        static const int dx[] = {-6, -3, -9, 3, 9}, dy[] = {0, -5, 0, -6, 0};
        for (int i = 0; i < 5; i++) {
            int x = e.px + dx[i], y = e.py + dy[i];
            while (tile_solid(tile_at(&e, x, y)) || tile_solid(tile_at(&e, x, y - 2))) y--;
            mob_place(&e.mobs[i], kinds[i], mob_max_hp(kinds[i]) * 2 / 3, x, y);
#if FID_MOBS
            if (kinds[i] == MOB_DEMON_EYE) { e.mobs[i].vx = FIXC(-2); e.mobs[i].vy = FIXC(1); }
            if (kinds[i] == MOB_ZOMBIE) { e.mobs[i].vx = FIXC(0.8); e.mobs[i].sdir = 1; }
#endif
        }
    }
    e.inv[ITEM_LENS] = EYE_LENSES; e.inv[ITEM_SUSPICIOUS_EYE] = 1; e.inv[ITEM_GOLD_ARMOR] = 1;
    e.inv[ITEM_TORCH] = 20; e.armor = 3; e.max_health = HEALTH_CAP; e.health = HEALTH_CAP;
    boss_summon(&e);
    e.boss.x = e.px + 3; e.boss.y = e.py - 10;
    e.achievements = (1ull << ACH_COLLECT_WOOD) | (1ull << ACH_KILL_ZOMBIE) | (1ull << ACH_FIND_ALTAR);
    e.terrain_dirty = e.light_dirty = true;
    sync(&v, &e);
    v.clock = 1.0; v.swing_t0 = 0.9; v.swing_len = 0.3;
    v.hover_ach = ACH_FIND_ALTAR;
    {   /* Every regular kind must be lit enough to be drawn at night. */
        Env lit = e;
        light_full(&lit);
        for (int i = 0; i < MAX_MOBS; i++) {
            const Mob *m = &lit.mobs[i];
            if (m->kind && lit.light[m->y][m->x] >= DARK_THRESHOLD) drawn[m->kind]++;
        }
    }
    shot(ui, &e, &v, prefix, "night");
    for (int s = 0; s < 40 && !e.terminated; s++) {   /* live AI: mobs and the boss move */
        env_step(&e, s % 3 ? ACT_NOOP : ACT_ATTACK);
        sync(&v, &e);
        v.clock = 1.0 + s * 0.25;
        boss_frames += e.boss.active;
        px_draw(ui, &e, &v);
    }
    shot(ui, &e, &v, prefix, "night-live");

    /* 3. Phase 2 and the controls overlay. */
    if (!e.terminated) {
        e.boss.active = true; e.boss.hp = EOC_HP / 3; e.boss.mode = BOSS_HOVER;
        e.boss.x = e.px - 4; e.boss.y = e.py - 9;
        sync(&v, &e);
        shot(ui, &e, &v, prefix, "phase2");
        v.help = true;
        shot(ui, &e, &v, prefix, "help");
        v.help = false;
    }

    /* 4. A worldgen Demon Altar in the caverns (camera only). */
    env_reset(&e, SEED);
    {
        int ax = -1, ay = -1;
        for (int y = 0; y < WORLD_H && ax < 0; y++)
            for (int x = 0; x < WORLD_W; x++)
                if (e.tiles[y][x] == TILE_DEMON_ALTAR) { ax = x; ay = y; break; }
        assert(ax >= 0 && ay >= CAVERN_Y);
        sync(&v, &e);
        centre(&v, (float)ax + 1.5f, (float)ay);
        printf("worldgen Demon Altar at (%d,%d)\n", ax, ay);
        shot(ui, &e, &v, prefix, "altar");
    }

    /* 5. Trees: canopies and branches are sprites, the world has no leaf cells
       (TREE_LEAF_VISUAL). The camera centres on the first full-grown trunk. */
    env_reset(&e, SEED);
    {
        int leaves = 0, tx = -1, ty = -1;
        for (int y = 0; y < WORLD_H; y++)
            for (int x = 0; x < WORLD_W; x++) {
                leaves += e.tiles[y][x] == TILE_LEAVES;
                if (tx < 0 && e.tiles[y][x] == TILE_LOG && tile_at(&e, x, y + 4) == TILE_LOG) { tx = x; ty = y; }
            }
        assert(leaves == 0 || !TREE_LEAF_VISUAL);
        assert(tx >= 0);
        sync(&v, &e);
        centre(&v, (float)tx, (float)ty + 3.0f);
        shot(ui, &e, &v, prefix, "trees");
    }

    /* 6. Combat: a broadsword swing mid-arc over a Zombie it just hit, its
       damage number and hit flash, the player blinking after a hit taken. */
    env_reset(&e, SEED);
    for (int i = 0; i < MAX_MOBS; i++) e.mobs[i].kind = MOB_NONE;
    e.inv[ITEM_GOLD_SWORD] = 1; e.weapon = 5; e.facing = 1;
    {
        int hits = 0;
        double t0 = 10.0, tick_s = 0.25 / FID_TICKS;
        memset(&v, 0, sizeof v);
        v.hover_reach = v.hover_recipe = v.hover_ach = v.hover_slot = v.hover_item = -1;
        for (int s = 0; s < 8 && !hits; s++, t0 += 0.25) {
            mob_place(&e.mobs[0], MOB_ZOMBIE, ZOMBIE_HP, e.px + 2, e.py);
            env_action_mask(&e, mask);
            env_step(&e, mask[ACT_ATTACK] ? ACT_ATTACK : ACT_NOOP);
            px_fx_step(&v, &e, t0, tick_s);
            hits = e.fx.n_hits;
        }
        assert(hits > 0);
        sync(&v, &e);
        v.swing_t0 = t0 - 0.25; v.swing_len = 20 * tick_s;   /* a swing in progress */
        v.clock = v.pop[0].t0 + 0.05;                          /* number rising, flash on */
        v.immune_end = v.clock + 0.5; v.player_hit_t = v.clock - 0.01;
        shot(ui, &e, &v, prefix, "combat");
    }

    for (int k = 1; k < MOB_KINDS; k++) assert(drawn[k] == 1);
    assert(boss_frames > 0);
    px_shutdown(ui);
    puts("v10 pixel fixtures passed: steps, all 5 mob kinds, Demon Altar, Eye of Cthulhu (both phases), help, tiered achievements, tree sprites, combat feedback");
    return 0;
}
