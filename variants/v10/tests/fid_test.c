/* v10 port fixtures: each enabled FID_* knob against the Terraria 1.4.4
   constants it ports, on v10's entities (all five regular mobs and the Eye of
   Cthulhu). Adapted from tools/v8fid_test.c; sim.c, mobs.c and boss.c are
   included here for their static internals, so build it as one unit:

     cc -std=c11 -O2 -Ivariants/v10/include -Ivariants/v10/src variants/v10/tests/fid_test.c \
        variants/v10/src/{worldgen,light,obs}.c -o /tmp/v10-fid -lm && /tmp/v10-fid

   Prints one "PASS|FAIL name: measured (expected)" line per check and exits 1
   on any failure. Reference values are recomputed from the real constants in
   double precision (independent of the fixed-point port). */
#include <math.h>
#include <stdarg.h>
#include "sim.c"
#include "mobs.c"
#include "boss.c"

static int failures, checks;
static void check(bool ok, const char *name, const char *fmt, ...) {
    char buf[320]; va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    printf("%s %s: %s\n", ok ? "PASS" : "FAIL", name, buf);
    failures += !ok; checks++;
}

static Env env;

/* Empty air world with a stone floor at `floor_row`, player standing on it
   at column 60, no mobs/chests/boss, fully lit, daytime step 1. */
static void flat_world(Env *e, int floor_row) {
    env_reset(e, 7);
    for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) {
        e->tiles[y][x] = y >= WORLD_H - BEDROCK_ROWS ? TILE_BEDROCK : y >= floor_row ? TILE_STONE : TILE_AIR;
        e->object_part[y][x] = 0;
    }
    for (int x = 0; x < WORLD_W; x++) e->surface[x] = floor_row;
    memset(e->mobs, 0, sizeof e->mobs); memset(&e->boss, 0, sizeof e->boss); e->chest_count = 0;
#if BG_WALLS
    memset(e->wall, 0, sizeof e->wall);
#endif
    e->px = 60; e->py = floor_row - 1; e->facing = 1;
    e->terrain_dirty = true; light_recompute(e);
    for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) e->light[y][x] = LIGHT_MAX;
#if FID_PHYSICS
    e->pos_x = (e->px * 16 + 6) * FIX_ONE; e->pos_y = ((e->py + 1) * 16 - PLAYER_PX_H) * FIX_ONE;
    e->vel_x = e->vel_y = 0; e->jump = 0; e->fall_start = ftile(e->pos_y); e->release_jump = true; e->pulley = false;
    e->hold_jump = false;
#endif
    e->steps = 1; e->max_steps = 1 << 30;
}

/* One action with mob spawning held off (spawn steps are multiples of 60). */
static void act(Env *e, int a) { e->steps = 1; env_step(e, a); }

/* ---------------------------------------------------------------- physics */
#if FID_PHYSICS
static double ref_rise(int held_ticks) {
    /* JumpMovement + gravity in doubles: press tick sets vy -5.01, jump 15;
       held ticks re-set vy -5.01 while jump > 0; then gravity 0.4/tick. */
    double vy = -5.01, y = 0, top = 0; int jump = 15;
    for (int t = 0; t < 200; t++) {
        if (t > 0) { if (t < held_ticks && jump > 0) { vy = -5.01; jump--; } else if (t >= held_ticks) jump = 0; }
        vy += 0.4; if (vy > 10) vy = 10;
        y += vy; if (y < top) top = y;
        if (vy > 0 && y >= 0) break;
    }
    return -top;
}

static void test_physics(void) {
    Env *e = &env;
    /* jump held for one action (FID_TICKS ticks) and for two; the apex is
       sampled every tick (player_tick with the action's held input) */
    for (int hold = 0; hold < 2; hold++) {
        flat_world(e, 60);
        fix_t y0 = e->pos_y, top = y0;
        int held = hold ? 2 * FID_TICKS : FID_TICKS;
        for (int t = 0; t < 12 * FID_TICKS; t++) {
            e->hold_jump = t < held;
            player_tick(e);
            if (e->pos_y < top) top = e->pos_y;
        }
        double rise = (double)(y0 - top) / FIX_ONE, ref = ref_rise(held);
        check(fabs(rise - ref) < 1.0, hold ? "physics jump held two actions" : "physics jump held one action",
              "%.2f px = %.2f tiles (real JumpMovement, %d held ticks: %.2f px)", rise, rise / 16, held, ref);
        check(e->vel_y == 0 && e->pos_y == y0, hold ? "physics long jump lands" : "physics jump lands", "back on the floor");
    }
    /* running: acceleration 0.08 with 0.2 slowdown, max 3 px/tick */
    flat_world(e, 60); e->px = 10; e->pos_x = (10 * 16 + 6) * FIX_ONE;
    fix_t vmax = 0;
    for (int i = 0; i < 6; i++) { act(e, ACT_RIGHT); if (e->vel_x > vmax) vmax = e->vel_x; }
    fix_t x0 = e->pos_x; for (int i = 0; i < 2; i++) act(e, ACT_RIGHT);
    double speed = (double)(e->pos_x - x0) / FIX_ONE / (2 * FID_TICKS);
    check(vmax <= FIXC(3.08) && vmax >= FIXC(2.9) && fabs(speed - 3) < 0.15, "physics run speed",
          "max %.3f px/tick, steady %.3f px/tick (maxRunSpeed 3, accel 0.08)", (double)vmax / FIX_ONE, speed);
    for (int i = 0; i < 2; i++) act(e, ACT_NOOP);
    check(e->vel_x == 0, "physics ground friction", "stops within %d ticks (runSlowdown 0.2 from 3 px/tick: 15 ticks)", 2 * FID_TICKS);
    /* terminal velocity and fall damage: 30-tile drop = (30-25)*10 hp */
    flat_world(e, 80);
    e->pos_y -= 30 * TILE_FIX; e->fall_start = ftile(e->pos_y); ph_sync(e);
    fix_t vfall = 0; int hp0 = e->health;
    for (int i = 0; i < 20 && !(e->vel_y == 0 && i > 0); i++) { act(e, ACT_NOOP); if (e->vel_y > vfall) vfall = e->vel_y; }
    check(vfall == PH_MAX_FALL, "physics max fall speed", "%.2f px/tick (maxFallSpeed 10)", (double)vfall / FIX_ONE);
    int want = (30 - FALL_SAFE) * FALL_DMG_PER_TILE;
    check(hp0 - e->health == want, "physics fall damage 30 tiles", "%d hp (real (30-25)*10 = %d)", hp0 - e->health, want);
    /* step up a one-tile ledge while running, but not a two-tile wall */
    for (int wall = 1; wall <= 2; wall++) {
        flat_world(e, 60);
        for (int x = 64; x < WORLD_W; x++) for (int k = 1; k <= wall; k++) e->tiles[60 - k][x] = TILE_STONE;
        for (int i = 0; i < 4; i++) act(e, ACT_RIGHT);
        bool up = e->py == 60 - 1 - wall && e->px >= 64;
        check(wall == 1 ? up : (!up && e->px < 64), wall == 1 ? "physics step up 1 tile" : "physics blocked by 2 tiles",
              "feet row %d, column %d", e->py, e->px);
    }
    /* 42 px hitbox: a 2-tile (32 px) tunnel blocks, a 3-tile one passes */
    for (int h = 2; h <= 3; h++) {
        flat_world(e, 60);
        for (int x = 64; x < 80; x++) for (int y = 0; y < 60 - h; y++) e->tiles[y][x] = TILE_STONE;
        for (int i = 0; i < 5; i++) act(e, ACT_RIGHT);
        check(h == 2 ? e->px < 64 : e->px >= 66, h == 2 ? "physics 2-high tunnel blocks 42px hitbox" : "physics 3-high tunnel passes",
              "column %d", e->px);
    }
    /* 20 px wide hitbox cannot drop through a 1-wide hole, does through 2 */
    for (int w = 1; w <= 2; w++) {
        flat_world(e, 60);
        int hx = ftile(e->pos_x);
        for (int k = 0; k < w; k++) for (int y = 60; y < 70; y++) e->tiles[y][hx + k] = TILE_AIR;
        if (w == 2) { e->pos_x = hx * TILE_FIX + 6 * FIX_ONE; ph_sync(e); }
        for (int i = 0; i < 3; i++) act(e, ACT_NOOP);
        check(w == 1 ? e->py == 59 : e->py > 60, w == 1 ? "physics 1-wide hole holds 20px hitbox" : "physics 2-wide hole drops",
              "feet row %d", e->py);
    }
    /* rope: climb up a rope column (pulley), award climb rope */
    flat_world(e, 60);
    int rc = ph_center_col(e);
    for (int y = 40; y < 60; y++) e->tiles[y][rc] = TILE_ROPE;
    uint8_t mask[ACT_COUNT]; env_action_mask(e, mask);
    int py0 = e->py;
    for (int i = 0; i < 4; i++) act(e, ACT_CLIMB_UP);
    check(mask[ACT_CLIMB_UP] && e->pulley && e->py < py0 - 3 && has_ach(e, ACH_CLIMB), "physics rope climb",
          "feet row %d -> %d, pulley %d", py0, e->py, e->pulley);
#if FID_COMBAT
    /* knockback on flat ground: Player.Hurt velocity (4.5, -3.5) */
    flat_world(e, 60); e->px = 20; e->pos_x = (20 * 16 + 6) * FIX_ONE; ph_sync(e);
    x0 = e->pos_x; env_hurt(e, 7, 1, "test");
    check(e->vel_x == FIXC(4.5) && e->vel_y == FIXC(-3.5), "combat knockback velocity", "(%.2f, %.2f)",
          (double)e->vel_x / FIX_ONE, (double)e->vel_y / FIX_ONE);
    for (int i = 0; i < 6; i++) act(e, ACT_NOOP);
    double kb_tiles = (double)(e->pos_x - x0) / TILE_FIX;
    check(fabs(kb_tiles - FID_GRID_KB) < 0.75, "combat knockback distance (grid FID_GRID_KB)",
          "%.2f tiles on flat ground (grid knockback %d cells)", kb_tiles, FID_GRID_KB);
#endif
}
#endif

/* ------------------------------------------------------------------- mobs */
#if FID_MOBS
static Mob *put_mob(Env *e, int kind, int x, int y) {
    Mob *m = &e->mobs[0];
    mob_place(m, kind, mob_max_hp(kind), x, y);
    return m;
}

static void slime_ref(double vy0, double *rise) {   /* AI sets vy, gravity 0.3 added, then move */
    double vy = vy0, y = 0, top = 0;
    for (int t = 0; t < 100; t++) { vy += 0.3; y += vy; if (y < top) top = y; if (vy > 0 && y >= 0) break; }
    *rise = -top;
}

/* Run mob 0 alone for n ticks; returns max |vx|, |vy| and the closest
   cell distance to the player's body. */
static void run_mob(Env *e, Mob *m, int n, fix_t *mvx, fix_t *mvy, int *closest) {
    *mvx = *mvy = 0; *closest = 1 << 30;
    for (int t = 0; t < n && m->kind; t++) {
        mob_update(e, m);
        if (fabsx(m->vx) > *mvx) *mvx = fabsx(m->vx);
        if (fabsx(m->vy) > *mvy) *mvy = fabsx(m->vy);
        int d = abs(m->x - e->px) + abs(m->y - (e->py - 1));
        if (d < *closest) *closest = d;
    }
}

static void test_mobs(void) {
    Env *e = &env;
    for (int aggressive = 0; aggressive < 2; aggressive++) {
        /* Surface floor (above worldSurface), day: passive unless damaged. */
        flat_world(e, 30);
        e->px = 5; e->py = 29;          /* far away: no contact */
#if FID_PHYSICS
        e->pos_x = (5 * 16 + 6) * FIX_ONE;
#endif
        Mob *m = put_mob(e, MOB_BLUE_SLIME, 64, 29);
        if (aggressive) m->hp = 20;
        int grounded = 0, hops = 0, gaps[8] = {0}; fix_t y0 = m->fy, top_small = y0, top_big = y0;
        int last_kind = 0;
        for (int t = 0; t < 2400 && hops < 8; t++) {
            fix_t vy_before = m->vy;
            mob_update(e, m);
            if (vy_before == 0) {
                grounded++;
                if (m->vy < 0) { gaps[hops++] = grounded; grounded = 0; last_kind = m->ai0 == -200 ? 3 : 1; }
            }
            if (last_kind == 3 && m->fy < top_big) top_big = m->fy;
            if (last_kind == 1 && m->fy < top_small) top_small = m->fy;
            if (m->fx < 20 * TILE_FIX || m->fx > 108 * TILE_FIX) { m->fx = 64 * TILE_FIX; }  /* stay mid-floor */
        }
        int s = aggressive ? 2 : 1;
        bool ok = gaps[1] == 120 / s && gaps[2] == 120 / s && gaps[3] == 200 / s && gaps[4] == 120 / s && gaps[5] == 120 / s && gaps[6] == 200 / s;
        check(ok, aggressive ? "mobs slime hop gaps (aggressive)" : "mobs slime hop gaps (passive)",
              "grounded ticks %d,%d,%d,%d,%d,%d (AI_001: %d,%d,%d repeating)", gaps[1], gaps[2], gaps[3], gaps[4], gaps[5], gaps[6],
              120 / s, 120 / s, 200 / s);
        if (!aggressive) {
            double rs, rb; slime_ref(-6, &rs); slime_ref(-8, &rb);
            double hs = (double)(y0 - top_small) / FIX_ONE, hb = (double)(y0 - top_big) / FIX_ONE;
            check(fabs(hs - rs) < 1 && fabs(hb - rb) < 1, "mobs slime hop heights",
                  "small %.1f px, big %.1f px (real vy -6/-8, gravity 0.3: %.1f/%.1f px)", hs, hb, rs, rb);
        }
    }
    /* Slimes are aggressive at night (AI_001: !Main.dayTime). */
    flat_world(e, 30); e->steps = DAY_STEPS + 1;
    Mob *ns = put_mob(e, MOB_BLUE_SLIME, 64, 29);
    int first = 0; for (int t = 0; t < 400 && !first; t++) { fix_t vb = ns->vy; mob_update(e, ns); if (vb == 0 && ns->vy < 0) first = t + 1; }
    for (int t = 0, g = 0; t < 400; t++) { fix_t vb = ns->vy; mob_update(e, ns); if (vb == 0) { g++; if (ns->vy < 0) { first = g; break; } } }
    check(first == 60, "mobs slime aggressive at night", "second hop after %d grounded ticks (120 halved)", first);
    /* Cave bat and Demon Eye: open cavern, player 10+ tiles away; speed envelope. */
    for (int k = MOB_CAVE_BAT; k <= MOB_DEMON_EYE; k += MOB_DEMON_EYE - MOB_CAVE_BAT) {
        flat_world(e, 90); e->steps = DAY_STEPS + 1;
        Mob *b = put_mob(e, k, 80, 70);
        fix_t mvx, mvy; int closest;
        run_mob(e, b, 1200, &mvx, &mvy, &closest);
        bool bat = k == MOB_CAVE_BAT;
        check(mvx <= 4 * FIX_ONE && mvx >= FIXC(3.9) && mvy <= FIXC(1.6) && mvy >= FIXC(1.4),
              bat ? "mobs bat flight speed" : "mobs demon eye flight speed",
              "max |vx| %.2f, |vy| %.2f px/tick (%s: 4, 1.5)", (double)mvx / FIX_ONE, (double)mvy / FIX_ONE,
              bat ? "aiStyle 14 type 49" : "AI_002_FloatingEye");
        check(closest <= 1, bat ? "mobs bat reaches player" : "mobs demon eye reaches player", "closest %d cells", closest);
    }
    /* Fighters: walk speed caps 1.0 (Zombie) / 1.5 (Skeleton), accel 0.07. */
    for (int k = MOB_ZOMBIE; k <= MOB_SKELETON; k += MOB_SKELETON - MOB_ZOMBIE) {
        bool zombie = k == MOB_ZOMBIE;
        flat_world(e, 60); e->steps = DAY_STEPS + 1;   /* night */
        Mob *z = put_mob(e, k, 30, 59);
        fix_t mvx, mvy; int closest, t15 = -1;
        for (int t = 0; t < 40; t++) { mob_update(e, z); if (t15 < 0 && z->vx >= (zombie ? FIXC(0.99) : FIXC(1.49))) t15 = t + 1; }
        run_mob(e, z, 1200, &mvx, &mvy, &closest);
        fix_t cap = zombie ? FIXC(1.0) : FIXC(1.5);
        check(mvx == cap && t15 > 0 && t15 <= (zombie ? 16 : 23), zombie ? "mobs zombie walk speed" : "mobs skeleton walk speed",
              "max |vx| %.3f px/tick after %d ticks (AI_003: %.1f, +0.07/tick)", (double)mvx / FIX_ONE, t15, zombie ? 1.0 : 1.5);
        check(closest <= 1, zombie ? "mobs zombie reaches player" : "mobs skeleton reaches player", "closest %d cells", closest);
    }
    /* Fighter wall handling (AI_003 64542 jump probe 15 px ahead, row r = the
       lowest occupied row): a 1-tile ledge is climbed by the inline step-up;
       2-, 3- and 4-tile walls get vy -6 / -7 / -8 (the test sees the AI's
       value plus one tick of gravity, 0.3). The -8 jump rises 6.6 tiles and
       the step-up (vy >= 0, so also at the apex) adds one: 7 tiles are
       still crossed, an 8-tile wall stops it. */
    for (int wall = 1; wall <= 8; wall += wall == 4 ? 3 : 1) {
        flat_world(e, 60); e->steps = DAY_STEPS + 1;
        e->px = 90; e->py = 59 - wall;
        for (int x = 70; x < WORLD_W; x++) for (int h = 1; h <= wall; h++) e->tiles[60 - h][x] = TILE_STONE;
#if FID_PHYSICS
        e->pos_x = (90 * 16 + 6) * FIX_ONE; e->pos_y = ((e->py + 1) * 16 - PLAYER_PX_H) * FIX_ONE;
#endif
        Mob *z = put_mob(e, MOB_ZOMBIE, 60, 59);
        fix_t jump_vy = 0;
        for (int t = 0; t < 600; t++) { mob_update(e, z); if (z->vy < jump_vy) jump_vy = z->vy; }
        bool over = z->x >= 70 && z->y <= 59 - wall;
        double ai_vy = (double)(jump_vy - NPC_GRAVITY) / FIX_ONE, want = wall == 2 ? -6 : wall == 3 ? -7 : -8;
        char name[64]; snprintf(name, sizeof name, "mobs zombie %d-tile wall", wall);
        if (wall <= 4) check(over && (wall == 1 ? jump_vy > FIXC(-5) : fabs(ai_vy - want) < 0.01), name,
                             "crossed to column %d row %d, strongest jump %.2f (AI_003: %s)", z->x, z->y,
                             wall == 1 ? (double)jump_vy / FIX_ONE : ai_vy, wall == 1 ? "step-up, no jump" : wall == 2 ? "vy -6" : wall == 3 ? "vy -7" : "vy -8");
        else if (wall == 7) check(over, name, "crossed to column %d row %d (vy -8 to 6.6 tiles, then the inline step-up)", z->x, z->y);
        else check(!over && z->x < 70, name, "stays at column %d (vy -8 rises 6.6 tiles, step-up adds 1)", z->x);
    }
    /* Daytime above worldSurface: fighters stop targeting and wander (turn
       after 2 still grounded ticks), at night they chase. */
    for (int night = 0; night < 2; night++) {
        flat_world(e, 30); e->steps = night ? DAY_STEPS + 1 : 1;
        e->px = 20; e->py = 29;
#if FID_PHYSICS
        e->pos_x = (20 * 16 + 6) * FIX_ONE;
#endif
        Mob *z = put_mob(e, MOB_ZOMBIE, 60, 29);
        for (int t = 0; t < 200; t++) mob_update(e, z);
        check(night ? z->x < 60 : z->x > 60, night ? "mobs zombie chases at night" : "mobs zombie wanders by day on the surface",
              "column %d from 60 (player at 20)", z->x);
    }
    /* stats and contact damage (no armor) for all five kinds */
    static const int LIFE[MOB_KINDS] = {0, 25, 16, 45, 60, 60}, DMG[MOB_KINDS] = {0, 7, 13, 14, 18, 20};
    for (int k = MOB_BLUE_SLIME; k < MOB_KINDS; k++) {
        flat_world(e, 60);
        Mob *m = put_mob(e, k, e->px, e->py);
        m->fx = player_fx(e); m->fy = player_fy(e) + 10 * FIX_ONE;
        int hp0 = e->health; mobs_contact(e);
        int lo = DMG[k], hi = DMG[k];
#if FID_COMBAT
        lo = (int)floor(lo * 0.85 + 0.5); hi = (int)floor(hi * 1.15 + 0.5);
#endif
        char name[64]; snprintf(name, sizeof name, "mobs %s stats", MOB_NAME[k]);
        check(hp0 - e->health >= lo && hp0 - e->health <= hi && m->hp == LIFE[k] && MOB_HP[k] == LIFE[k] && MOB_DMG[k] == DMG[k], name,
              "life %d, contact damage %d (NPC.SetDefaults: %d life, %d damage, %dx%d px)", m->hp, hp0 - e->health, LIFE[k], DMG[k],
              MOB_W[k], MOB_H[k]);
    }
}
#endif

/* ----------------------------------------------------------------- combat */
#if FID_COMBAT
/* Put mob 0 at a player-relative px offset of its box centre. */
static Mob *place_mob(Env *e, int kind, int dx_px, int dy_px) {
    Mob *m = &e->mobs[0];
    *m = MOB_INIT(0, 0, 1000, 0, 0, 1, kind);
    fix_t cx = player_fx(e) + (PLAYER_PX_W / 2 + dx_px) * FIX_ONE, cy = player_fy(e) + (PLAYER_PX_H / 2 + dy_px) * FIX_ONE;
#if FID_MOBS
    m->fx = cx - (MOB_W[kind] / 2) * FIX_ONE; m->fy = cy - (MOB_H[kind] / 2) * FIX_ONE; m->vx = m->vy = 0; m->ai2 = 1;
    mob_sync_cell(m);
#else
    m->x = (int)(cx >> 20); m->y = (int)(cy >> 20);
#endif
    return m;
}

#if AIM_ATTACK
#define ATTACK_FORWARD(e) attack_start(e, 0)   /* `attack`: aim forward */
#else
#define ATTACK_FORWARD(e) attack_start(e)
#endif
/* Hits landed on a 1000-hp target by one full use of the current weapon. */
static int hits_one_use(Env *e, Mob *m) {
    int n = 0;
    ATTACK_FORWARD(e);
    for (int t = 0; t < 40; t++) {
        int before = m->hp; swing_tick(e);
        if (m->hp < before) n++;
        if (m->immune > 0) m->immune--;
#if FID_MOBS
        m->vx = m->vy = 0;   /* hold the target in place (ignore its knockback) */
#endif
    }
    return n;
}
#if AIM_ATTACK
/* The same with an aim (0 = forward, AIM_FX/AIM_FY order). */
static int hits_aim(Env *e, Mob *m, int aim) {
    int n = 0;
    attack_start(e, aim);
    for (int t = 0; t < 40; t++) {
        int before = m->hp; swing_tick(e);
        if (m->hp < before) n++;
        if (m->immune > 0) m->immune--;
#if FID_MOBS
        m->vx = m->vy = 0;
#endif
    }
    return n;
}
#endif

static void test_combat(void) {
    Env *e = &env;
    /* damage variance + defense: Main.DamageVar(7), defense 0 and 3 */
    int hist[2][12] = {{0}};
    for (int armor = 0; armor < 3; armor += 2) {
        flat_world(e, 60); e->armor = armor;
        for (int i = 0; i < 31000; i++) {
            e->immune_ticks = 0; e->health = 100; env_hurt(e, 7, 0, "t");
            hist[armor / 2][100 - e->health]++;
        }
    }
    double p6 = hist[0][6] / 31000.0, p7 = hist[0][7] / 31000.0, p8 = hist[0][8] / 31000.0;
    check(fabs(p6 - 8 / 31.0) < 0.01 && fabs(p7 - 15 / 31.0) < 0.012 && fabs(p8 - 8 / 31.0) < 0.01 && hist[0][5] == 0 && hist[0][9] == 0,
          "combat damage variance (slime 7, defense 0)", "P(6,7,8) = %.3f %.3f %.3f (DamageVar +-15%%: %.3f %.3f %.3f)",
          p6, p7, p8, 8 / 31.0, 15 / 31.0, 8 / 31.0);
    check(hist[1][4] && hist[1][5] && hist[1][6] && !hist[1][3] && !hist[1][7], "combat defense 3 (iron chainmail)",
          "damage %s4-6 (int)(6..8 - 1.5)", hist[1][4] ? "" : "not ");
    /* i-frames: a body-overlapping attacker hits every 40 ticks */
    flat_world(e, 60);
    int hits = 0, spacing = -1, last = -1, first = -1;
    for (int t = 0; t < 200; t++) {
        if (e->immune_ticks > 0) e->immune_ticks--;
        e->health = 100;
        env_hurt(e, 7, 0, "slime");
        if (e->health < 100) { hits++; if (first < 0) first = t; else if (spacing < 0) spacing = t - last; last = t; }
    }
    check(hits == 5 && spacing == 40, "combat player i-frames", "%d hits in 200 ticks, every %d ticks (immuneTime 40)", hits, spacing);
    /* one hit per swing per NPC (NPC.immune = itemAnimation) */
    flat_world(e, 60); e->weapon = 3;   /* iron broadsword */
    Mob *m = place_mob(e, MOB_ZOMBIE, 24, 0);
    int h1 = hits_one_use(e, m), h2 = hits_one_use(e, m);
    check(h1 == 1 && h2 == 1, "combat NPC immunity per swing", "%d then %d hits in two swings", h1, h2);
    /* swing coverage (useStyle 1, 32x32 server item frame): offsets in px */
    char row[200] = ""; bool front = false, far = true, overhead = false;
    for (int dx = -64; dx <= 80; dx += 16) {
        flat_world(e, 60); e->weapon = 3;
        m = place_mob(e, MOB_BLUE_SLIME, dx, 12);
        int h = hits_one_use(e, m);
        char cell[16]; snprintf(cell, sizeof cell, "%+d:%d ", dx, h); strcat(row, cell);
        if (dx == 32) front = h == 1;
        if (dx == 80) far = h == 0;
    }
    flat_world(e, 60); e->weapon = 3; m = place_mob(e, MOB_BLUE_SLIME, 0, -40); overhead = hits_one_use(e, m) == 1;
    check(front && far && overhead, "combat broadsword hitbox", "foot-level hits by x offset %s; overhead %d", row, overhead);
    /* copper shortsword stab: reach ~ 2.1*14 + 12.6 + 5 px past the centre
       (AIM_ATTACK: the exact segment test, 2.1*14 + 12.6 = 42) */
    int reach = 0;
    for (int dx = 8; dx <= 96; dx += 4) {
        flat_world(e, 60); e->weapon = 0;
        m = place_mob(e, MOB_CAVE_BAT, dx, 0);
        fix_t mx, my; int mw, mh; mob_rect(m, &mx, &my, &mw, &mh); (void)my; (void)mw; (void)mh;
        int left = (int)((mx - player_fx(e)) >> 16) - PLAYER_PX_W / 2;
        if (hits_one_use(e, m) && left > reach) reach = left;
    }
    check(reach > 47 - 16 && reach <= 52, "combat shortsword stab reach", "hits up to %d px past centre (AI_161: 2.1*14 + 12.6 + 5 = 47)", reach);
#if AIM_ATTACK
    /* Aimed stabs (AI_161 velocity = 2.1 x the aim): a cave bat 30 px along
       each aim (diagonals 22, 22) from the player centre, open air around it
       (the floor removed for down aims): the aimed stab hits it, `attack`
       (forward) only when it is ahead. The player turns to the aim's side. */
    {
        static const int AX[AIM_COUNT] = {1, 1, 0, -1, -1, -1, 0, 1}, AY[AIM_COUNT] = {0, -1, -1, -1, 0, 1, 1, 1};
        static const int TURN[AIM_COUNT] = {1, 1, 1, -1, -1, -1, 1, 1};
        int good = 0; char got[200] = "";
        for (int a = 0; a < AIM_COUNT; a++) {
            int hits[2], facing = 0;
            for (int k = 0; k < 2; k++) {
                flat_world(e, 60); e->weapon = 0; e->facing = 1;
                if (AY[a] > 0) for (int y = e->py + 1; y < e->py + 6; y++) for (int x = e->px - 4; x < e->px + 6; x++) e->tiles[y][x] = TILE_AIR;
                int d = AX[a] && AY[a] ? 22 : 30;
                m = place_mob(e, MOB_CAVE_BAT, AX[a] * d, AY[a] * d);
                hits[k] = hits_aim(e, m, k ? a : 0);
                if (k) facing = e->facing;
            }
            char c[24]; snprintf(c, sizeof c, "%d:%d/%d/%+d ", a, hits[1], hits[0], facing); strcat(got, c);
            good += hits[1] == 1 && hits[0] == (a == 0) && facing == TURN[a];
        }
        check(good == AIM_COUNT, "combat aimed stab, 8 directions", "aim:aimed/forward hits/facing %s", got);
    }
    /* A Demon Eye straight above: `attack up` hits, `attack` misses. */
    {
        int h[2];
        for (int k = 0; k < 2; k++) {
            flat_world(e, 60); e->weapon = 0; e->facing = 1;
            m = place_mob(e, MOB_DEMON_EYE, 0, -36);
            h[k] = hits_aim(e, m, k ? 2 : 0);
        }
        check(h[1] == 1 && h[0] == 0 && e->facing == 1, "combat attack up hits a Demon Eye overhead", "up %d, forward %d", h[1], h[0]);
    }
    /* A slime below a one-tile ledge ahead: `attack down-forward` hits it,
       `attack` passes over it. */
    {
        int h[2];
        for (int k = 0; k < 2; k++) {
            flat_world(e, 60); e->weapon = 0; e->facing = 1;
            for (int x = e->px + PLAYER_W; x < WORLD_W; x++) e->tiles[e->py + 1][x] = TILE_AIR;
            m = place_mob(e, MOB_BLUE_SLIME, 36, 37 - MOB_H[MOB_BLUE_SLIME] / 2);
            h[k] = hits_aim(e, m, k ? 7 : 0);
        }
        check(h[1] == 1 && h[0] == 0, "combat attack down-forward hits a slime below a ledge", "down-forward %d, forward %d", h[1], h[0]);
    }
    /* Broadsword: the aim only picks the side. `attack back` turns and hits
       a foot-level slime 32 px behind (the forward arc starts overhead
       behind the head and misses it); `attack up` keeps the facing and
       swings exactly as `attack` (same hits on a zombie ahead). */
    {
        int h[3];
        for (int k = 0; k < 2; k++) {
            flat_world(e, 60); e->weapon = 3; e->facing = 1;
            m = place_mob(e, MOB_BLUE_SLIME, -32, 12);
            h[k] = hits_aim(e, m, k ? 4 : 0);
        }
        flat_world(e, 60); e->weapon = 3; e->facing = 1;
        m = place_mob(e, MOB_ZOMBIE, 28, 0);
        h[2] = hits_aim(e, m, 2);
        int up_facing = e->facing;
        flat_world(e, 60); e->weapon = 3; e->facing = 1;
        m = place_mob(e, MOB_ZOMBIE, 28, 0);
        int fwd = hits_aim(e, m, 0);
        check(h[1] == 1 && h[0] == 0 && h[2] == fwd && fwd == 1 && up_facing == 1, "combat broadsword aim picks the side",
              "back %d (forward %d), up %d = forward %d, facing after up %+d", h[1], h[0], h[2], fwd, up_facing);
    }
#endif
    /* crit rate and NPC damage vs defense: copper broadsword 9 on a slime (2) -> 7..9; on a skeleton (8) -> 4..6 */
    for (int k = MOB_BLUE_SLIME; k <= MOB_SKELETON; k += MOB_SKELETON - MOB_BLUE_SLIME) {
        flat_world(e, 60);
        int crits = 0, n = 20000, lo = 99, hi = 0, def = MOB_DEF[k];
        for (int i = 0; i < n; i++) {
            m = place_mob(e, k, 24, 0);
            int before = m->hp; mob_strike(e, m, 9, FIXC(5.5), 1); int d = before - m->hp;
            if (d >= 2 * ((2 * 8 - def) / 2)) crits++; else { if (d < lo) lo = d; if (d > hi) hi = d; }
        }
        int wlo = (2 * 8 - def) / 2, whi = (2 * 10 - def) / 2;
        char name[64]; snprintf(name, sizeof name, "combat NPC damage and crits (%s, defense %d)", MOB_NAME[k], def);
        check(fabs(crits / (double)n - 0.04) < 0.006 && lo == wlo && hi == whi, name,
              "non-crit %d-%d (want %d-%d: round(9*0.85..1.15) - def/2), crit rate %.3f (4%%)", lo, hi, wlo, whi, crits / (double)n);
    }
#if FID_MOBS
    /* StrikeNPC knockback: kb x knockBackResist (x1.4 crit); a heavy hit
       (damage*10 > lifeMax) pushes up to that, a light hit sets velocity to it
       x knockBackResist again. */
    m = place_mob(e, MOB_BLUE_SLIME, 24, 0); m->hp = 25;
    mob_strike(e, m, 9, FIXC(5.5), 1);
    check(m->vx == FIXC(5.5) || m->vx == fmul(FIXC(5.5), FIXC(1.4)), "combat NPC knockback (heavy hit)",
          "slime vx %.2f vy %.2f (kb 5.5, vy -0.75*kb)", (double)m->vx / FIX_ONE, (double)m->vy / FIX_ONE);
    m = place_mob(e, MOB_ZOMBIE, 24, 0); m->hp = 1000; m->vx = m->vy = 0;
    mob_strike(e, m, 1, FIXC(4), 1);
    fix_t k1 = fmul(fmul(FIXC(4), FIXC(0.5)), FIXC(0.5)), k2 = fmul(fmul(fmul(FIXC(4), FIXC(0.5)), FIXC(1.4)), FIXC(0.5));
    check(m->vx == k1 || m->vx == k2, "combat zombie knockback (light hit, resist twice)",
          "vx %.3f (kb 4 * 0.5 * 0.5 = 1.0)", (double)m->vx / FIX_ONE);
#endif
    /* Eye of Cthulhu: one hit per swing, no line of sight needed (noTileCollide), contact through i-frames */
    flat_world(e, 60); e->weapon = 3; e->steps = DAY_STEPS + 1;
    e->inv[ITEM_SUSPICIOUS_EYE] = 1; env_step(e, ACT_SUMMON);
    Boss *b = &e->boss;
    b->x = e->px + 1; b->y = e->py - 2; b->mode = BOSS_PAUSE; b->timer = 1000;
    for (int y = b->y; y < b->y + EOC_SIZE; y++) e->tiles[y][b->x + 2] = TILE_STONE;   /* partly inside a wall */
    int bh0 = b->hp, bhits = 0;
    ATTACK_FORWARD(e);
    for (int t = 0; t < 40; t++) { int before = b->hp; swing_tick(e); if (b->immune > 0) b->immune--; bhits += b->hp < before; }
    check(bhits == 1 && b->hp < bh0, "combat boss one hit per swing", "%d hits, hp %d -> %d", bhits, bh0, b->hp);
    e->immune_ticks = 0; e->health = e->max_health = HEALTH_CAP; int bc = 0;
    for (int t = 0; t < 120; t++) { if (e->immune_ticks > 0) e->immune_ticks--; int h = e->health; boss_contact(e); bc += e->health < h;
#if FID_PHYSICS
        e->vel_x = e->vel_y = 0;
#endif
    }
    check(bc == 3, "combat boss contact i-frames", "%d contact hits in 120 ticks (immuneTime 40)", bc);
}
#endif

/* ------------------------------------------------------------ tool damage */
#if TOOL_DAMAGE
/* Main.DamageVar at the variance extremes (-15 / +15), half to even. */
static int var_at(int dmg, int k) {
    int v = dmg * (100 + k), q = v / 100, rem = v % 100;
    if (rem > 50 || (rem == 50 && (q & 1))) q++;
    return q;
}

static void test_tool_damage(void) {
    Env *e = &env;
    static const char *NAME[TOOL_COUNT] = {"copper pickaxe 3509", "iron pickaxe 1", "gold pickaxe 3521", "copper axe 3506"};
    static const int WANT[TOOL_COUNT][4] = {{4, 23, 15, 2}, {5, 20, 13, 2}, {6, 20, 17, 2}, {3, 30, 21, 4}}; /* damage, useAnimation, useTime, kb (x2 for 4.5) */
    for (int k = 0; k < TOOL_COUNT; k++) {
        const ToolInfo *ti = &TOOL_INFO[k];
        char name[96];
        snprintf(name, sizeof name, "tool %s constants", NAME[k]);
        check(ti->damage == WANT[k][0] && ti->use_anim == WANT[k][1] && ti->use_time == WANT[k][2]
              && ti->knockback == (k == TOOL_COPPER_AXE ? FIXC(4.5) : FIXC(2)), name,
              "damage %d, useAnimation %d, useTime %d, knockBack %.1f", ti->damage, ti->use_anim, ti->use_time,
              (double)ti->knockback / FIX_ONE);
        /* Strikes on a Blue Slime (defense 2): DamageVar, -defense/2, crit x2. */
        flat_world(e, 60);
        int def = MOB_DEF[MOB_BLUE_SLIME], lo = 99, hi = 0, bad = 0, n = 20000;
        int wlo = (2 * var_at(ti->damage, -15) - def) / 2, whi = (2 * var_at(ti->damage, 15) - def) / 2;
        if (wlo < 1) wlo = 1;
        for (int i = 0; i < n; i++) {
            Mob *m = place_mob(e, MOB_BLUE_SLIME, 24, 12);
            int before = m->hp; mob_strike(e, m, ti->damage, ti->knockback, 1); int d = before - m->hp;
            if (d < lo) lo = d;
            if (d > hi) hi = d;
            bad += !((d >= wlo && d <= whi) || (d % 2 == 0 && d / 2 >= wlo && d / 2 <= whi));
        }
        snprintf(name, sizeof name, "tool %s damage on a slime", NAME[k]);
        check(lo == wlo && hi == 2 * whi && bad == 0, name, "%d-%d, crits to %d (want %d-%d, crit x2 to %d), %d outside",
              lo, whi, hi, wlo, whi, 2 * whi, bad);
        /* One use = one useStyle 1 swing: one hit per NPC (immunity = itemAnimation). */
        flat_world(e, 60);
        Mob *m = place_mob(e, MOB_BLUE_SLIME, 24, 12);
        int hits = 0;
        tool_swing_start(e, k);
        int anim = e->item_anim;
        for (int t = 0; t < 40; t++) {
            int before = m->hp; swing_tick(e);
            hits += m->hp < before;
            if (m->immune > 0) m->immune--;
#if FID_MOBS
            m->vx = m->vy = 0;
#endif
        }
        snprintf(name, sizeof name, "tool %s swing", NAME[k]);
        check(anim == ti->use_anim && hits == 1, name, "useAnimation %d, %d hit per use", anim, hits);
    }
    /* End to end: holding a mine action on stone swings the pickaxe through a
       slime in front (knocked away from the player) while the stone takes hits. */
    flat_world(e, 60);
    int r = ACT_MINE_FOOT_RIGHT - ACT_MINE_FIRST, tx = e->px + REACH_DX[r], ty = e->py + REACH_DY[r];
    e->tiles[ty][tx] = TILE_STONE;
    Mob *m = place_mob(e, MOB_BLUE_SLIME, 24, 12);
    int hp0 = m->hp;
    act(e, ACT_MINE_FIRST + r);
    HitSlot *s = hit_find(e, tx, ty);
#if EXPLICIT_TOOLS
    bool held_ok = e->held == ITEM_COPPER_PICK;
#else
    bool held_ok = true;
#endif
    check(m->hp < hp0 && s && s->damage == 35 && held_ok, "tool mining swing hits a slime",
          "slime hp %d -> %d, stone damage %d", hp0, m->hp, s ? s->damage : -1);
}
#endif

/* ----------------------------------------------------------------- mining */
#if FID_MINING
static int hits_to_break(Env *e, Tile t, int tier) {
    flat_world(e, 60);
#if EXPLICIT_TOOLS
    e->inv[ITEM_COPPER_PICK] = tier == TIER_COPPER_PICK; e->inv[ITEM_IRON_PICK] = tier == TIER_IRON_PICK;
    e->inv[ITEM_GOLD_PICK] = tier == TIER_GOLD_PICK;
#else
    e->tool_tier = (uint8_t)tier;
#endif
    int r = ACT_MINE_FOOT_RIGHT - ACT_MINE_FIRST;
    int tx = e->px + REACH_DX[r], ty = e->py + REACH_DY[r];
    if (t == TILE_LOG) { e->tiles[ty][tx] = TILE_LOG; e->tiles[ty - 1][tx] = TILE_LOG; }
    else e->tiles[ty][tx] = (uint8_t)t;
    int hits = 0, ticks = 0;
    e->tool_time = 0;
    while (tile_at(e, tx, ty) != TILE_AIR && hits < 50) {
        if (e->tool_time > 0) e->tool_time--;
        if (e->tool_time == 0) { do_mine(e, r); hits++; }
        ticks++;
    }
    return hits * 1000 + ticks;
}

static void test_mining(void) {
    Env *e = &env;
    struct { Tile t; const char *name; int want[4]; } cases[] = {
        {TILE_DIRT, "dirt", {0, 2, 2, 1}}, {TILE_GRASS, "grass", {0, 2, 2, 2}}, {TILE_STONE, "stone", {0, 3, 3, 2}},
        {TILE_COPPER_ORE, "copper ore", {0, 3, 3, 2}}, {TILE_IRON_ORE, "iron ore", {0, 3, 3, 2}},
        {TILE_SILVER_ORE, "silver ore", {0, 3, 3, 2}}, {TILE_GOLD_ORE, "gold ore", {0, 3, 3, 2}},
        {TILE_WOOD, "wood block", {0, 3, 3, 2}}, {TILE_TORCH, "torch", {0, 1, 1, 1}},
        {TILE_LOG, "tree (copper axe)", {0, 13, 13, 13}},
    };
    const char *pick[4] = {"", "copper", "iron", "gold"};
    for (size_t c = 0; c < sizeof cases / sizeof cases[0]; c++) for (int tier = 1; tier <= 3; tier++) {
        int r = hits_to_break(e, cases[c].t, tier), hits = r / 1000, ticks = r % 1000;
        int ut = TOOL_INFO[cases[c].t == TILE_LOG ? TOOL_COPPER_AXE : tier - 1].use_time;
        char name[64]; snprintf(name, sizeof name, "mining %s with %s pick", cases[c].name, pick[tier]);
        check(hits == cases[c].want[tier] && ticks == (hits - 1) * ut + 1, name,
              "%d hits, %d ticks = %d actions (want %d hits every %d ticks)", hits, ticks, (ticks + FID_TICKS - 1) / FID_TICKS,
              cases[c].want[tier], ut);
    }
    /* The Demon Altar never breaks. */
    flat_world(e, 60);
    env_object_write(e, TILE_DEMON_ALTAR, e->px + 2, e->py);
    for (int i = 0; i < 10; i++) act(e, ACT_MINE_FIRST + 6);
    check(tile_at(e, e->px + 2, e->py) == TILE_DEMON_ALTAR, "mining demon altar unbreakable", "still standing after 10 actions");
    /* partial damage decays only after many other hits (HitTile.Prune) */
    flat_world(e, 60);
    int r0 = ACT_MINE_FOOT_RIGHT - ACT_MINE_FIRST, tx = e->px + REACH_DX[r0], ty = e->py + REACH_DY[r0];
    e->tiles[ty][tx] = TILE_STONE; e->tool_time = 0; do_mine(e, r0);
    int d0 = hit_find(e, tx, ty)->damage;
    for (int i = 0; i < 20; i++) { hit_add(e, 5 + (i % 3), 70, 1); hit_prune(e); }
    HitSlot *s = hit_find(e, tx, ty);
    check(d0 == 35 && s && s->damage == 35 - 2 * 9, "mining hit damage decay", "35 -> %d after 20 other hits (decay 2/hit once ttl < 48)", s ? s->damage : -1);
    /* held mine action at FID_TICKS ticks per action: stone in one action or two */
    flat_world(e, 60);
    e->tiles[ty][tx] = TILE_STONE;
    int n = 0; while (tile_at(e, tx, ty) == TILE_STONE && n < 10) { act(e, ACT_MINE_FIRST + r0); n++; }
    check(n == (2 * TOOL_INFO[TOOL_COPPER_PICK].use_time + 1 + FID_TICKS - 1) / FID_TICKS, "mining stone with held action",
          "%d actions at %d ticks/action (3 hits, useTime 15: 31 ticks)", n, FID_TICKS);
}
#endif

/* ------------------------------------------------------------------ trees */
#if FID_TREES
static void test_trees(void) {
    Env *e = &env;
    int hist[20] = {0}, trees = 0, worlds = 400; long wood = 0, height_sum = 0;
    for (int s = 0; s < worlds; s++) {
        env_reset(e, (uint64_t)s);
        for (int x = 2; x < WORLD_W - 2; x++) {
            int y = e->surface[x] - 1;
            if (tile_at(e, x, y) != TILE_LOG) continue;
            int h = 0; while (tile_at(e, x, y - h) == TILE_LOG) h++;
            if (h < 20) hist[h]++;
            trees++; height_sum += h;
            /* fell from the base: wood from trunk, branches, roots, bonus */
            e->px = x - 1; e->py = y; int before = e->inv[ITEM_WOOD];
            e->inv[ITEM_WOOD] = 0;
#if FID_MINING
            for (int k = 0; k < 13; k++) { e->tool_time = 0; do_mine(e, ACT_MINE_BODY_FOOT_RIGHT - ACT_MINE_FIRST); }
#else
            e->mine_cd = 0; do_mine(e, ACT_MINE_BODY_FOOT_RIGHT - ACT_MINE_FIRST);
#endif
            wood += e->inv[ITEM_WOOD]; e->inv[ITEM_WOOD] = (int16_t)before;
        }
    }
    int lo = 99, hi = 0;
    char row[200] = "";
    for (int h = 0; h < 20; h++) if (hist[h]) {
        if (h < lo) lo = h;
        if (h > hi) hi = h;
        char c[16]; snprintf(c, sizeof c, "%d:%d ", h, hist[h]); strcat(row, c);
    }
    /* v10 grows trees within reach of spawn toward the wood floor, so the
       height histogram is GrowTree's 5-16 plus grown trunks (still <= 16). */
    check(lo == 5 && hi == 16, "trees height range", "%d trees in %d worlds, heights %s(GrowTree Next(5,17), floor growth capped at 16)",
          trees, worlds, row);
    double mh = (double)height_sum / trees, mw = (double)wood / trees;
    check(mw / mh > 1.75 && mw / mh < 2.1, "trees wood per trunk tile", "mean trunk %.2f tiles, mean wood %.2f (%.2f per trunk tile; worldgen floor assumes 1.93)",
          mh, mw, mw / mh);
}
#endif

int main(void) {
    printf("v10 port fixtures: MOBS=%d COMBAT=%d PHYSICS=%d MINING=%d TREES=%d, FID_TICKS=%d, EXPLICIT_TOOLS=%d TOOL_DAMAGE=%d\n",
           FID_MOBS, FID_COMBAT, FID_PHYSICS, FID_MINING, FID_TREES, FID_TICKS, EXPLICIT_TOOLS, TOOL_DAMAGE);
#if FID_PHYSICS
    test_physics();
#endif
#if FID_MOBS
    test_mobs();
#endif
#if FID_COMBAT
    test_combat();
#endif
#if TOOL_DAMAGE
    test_tool_damage();
#endif
#if FID_MINING
    test_mining();
#endif
#if FID_TREES
    test_trees();
#endif
    printf("%d/%d checks passed\n", checks - failures, checks);
    return failures != 0;
}
