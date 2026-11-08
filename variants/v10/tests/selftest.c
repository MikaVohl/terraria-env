/* v10 gates (docs/ENV_V9_DESIGN.md sections 10 and 14): determinism, save/load,
   incremental-vs-reference lighting across day/night, one fixture per v9
   mechanic (with whatever FID_* ports the build has), the D24 stepping
   stones, a scripted Eye of Cthulhu fight, and worldgen supply statistics.
   Port-level fixtures against the real constants are in tests/fid_test.c.

     cc -std=c11 -O2 -Ivariants/v10/include variants/v10/src/{sim,worldgen,light,obs,mobs,boss}.c \
        src/capi.c variants/v10/tests/selftest.c -o /tmp/v10-selftest -lm && /tmp/v10-selftest [worlds]
   (add -DFID_MOBS=0 -DFID_COMBAT=0 -DFID_PHYSICS=0 -DFID_MINING=0 -DFID_TREES=0 for the noport build)
*/
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "env.h"
#include "rng.h"
#include "fid.h"

/* src/capi.c (linked in): the native autoreset's episode-info rows. */
int tl_info_width(void);
int tl_batch_step_autoreset(Env **envs, int n, const int *actions, void *obs, int flat, uint8_t *masks,
                            float *rewards, int *ends, void *final_obs, int *info, float *info_return,
                            int *lanes, unsigned long long next_seed, int workers);

static int failures, checks;
#define CHECK(cond, ...) do { checks++; if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); \
    printf(__VA_ARGS__); printf("\n"); } } while (0)

static uint64_t hash_bytes(const void *p, size_t n) {
    const uint8_t *b = p; uint64_t h = 1469598103934665603ull;
    for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 1099511628211ull; }
    return h;
}
/* Everything that defines the game state (light caches included). */
static uint64_t state_hash(const Env *e) { return hash_bytes(e, sizeof *e); }

static int legal_action(const Env *e, uint64_t *rng) {
    uint8_t mask[ACT_COUNT]; int legal[ACT_COUNT], n = 0;
    env_action_mask(e, mask);
    for (int a = 0; a < ACT_COUNT; a++) if (mask[a]) legal[n++] = a;
    return legal[rng_below(rng, (uint32_t)n)];
}

static Env *new_env(int max_steps) {
    Env *e = calloc(1, sizeof *e);
    env_init(e, (EnvConfig){max_steps});
    return e;
}

/* Fixtures move the grid anchors px/py; with FID_PHYSICS the hitbox follows
   (centred in the body's columns, standing on the feet row, at rest). */
static void sync_body(Env *e) {
#if FID_PHYSICS
    e->pos_x = (e->px * 16 + (PLAYER_W * 16 - PLAYER_PX_W) / 2) * FIX_ONE;
    e->pos_y = ((e->py + 1) * 16 - PLAYER_PX_H) * FIX_ONE;
    e->vel_x = e->vel_y = 0; e->jump = 0; e->pulley = false; e->release_jump = true;
    e->fall_start = ftile(e->pos_y);
#else
    (void)e;
#endif
}

/* Clear the post-hit invulnerability (v9 hurt_cd or FID_COMBAT i-frames). */
static void no_iframes(Env *e) {
    e->hurt_cd = 0;
#if FID_COMBAT
    e->immune_ticks = 0;
#endif
}

/* Is d a possible contact-damage outcome of `raw` against `armor`? v9: raw
   minus half defense (rounded up); FID_COMBAT: Main.DamageVar (+-15%, half
   to even) then (int)max(dmg - defense/2, 1). */
static bool contact_damage_ok(int d, int raw, int armor) {
    int def = ARMOR_DEFENSE[armor];
#if FID_COMBAT
    for (int k = -15; k <= 15; k++) {
        int v = raw * (100 + k), q = v / 100, rem = v % 100;
        if (rem > 50 || (rem == 50 && (q & 1))) q++;
        int dmg = (2 * q - def) / 2;
        if ((dmg < 1 ? 1 : dmg) == d) return true;
    }
    return false;
#else
    int dmg = raw - (def + 1) / 2;
    return d == (dmg < 1 ? 1 : dmg);
#endif
}

/* ---- determinism and snapshots ------------------------------------------ */

static void test_determinism(void) {
    Env *a = new_env(0), *b = new_env(0);
    uint64_t ra = 99, rb = 99;
    env_reset(a, 7); env_reset(b, 7);
    CHECK(state_hash(a) == state_hash(b), "reset differs");
    int mismatch = -1;
    for (int t = 0; t < 30000 && mismatch < 0; t++) {
        env_step(a, legal_action(a, &ra)); env_step(b, legal_action(b, &rb));
        if (state_hash(a) != state_hash(b)) mismatch = t;
        if (a->terminated || a->truncated) { env_reset(a, 1000 + t); env_reset(b, 1000 + t); }
    }
    CHECK(mismatch < 0, "same seed+actions diverged at step %d", mismatch);
    /* Snapshot mid-episode, continue both copies with the same actions. */
    env_reset(a, 11);
    for (int t = 0; t < 4000 && !a->terminated; t++) env_step(a, legal_action(a, &ra));
    memcpy(b, a, sizeof *a);
    uint64_t r2 = ra;
    mismatch = -1;
    for (int t = 0; t < 6000; t++) {
        int act = legal_action(a, &ra); legal_action(b, &r2);
        env_step(a, act); env_step(b, act);
        if (state_hash(a) != state_hash(b)) { mismatch = t; break; }
        if (a->terminated || a->truncated) break;
    }
    CHECK(mismatch < 0, "save/load round trip diverged at step %d", mismatch);
    free(a); free(b);
}

/* Incremental terrain light equals the uncached reference, day and night. */
static void test_light_parity(void) {
    Env *e = new_env(0), *ref = new_env(0);
    uint64_t r = 5; int bad = 0, compared = 0;
    for (int seed = 0; seed < 6; seed++) {
        env_reset(e, 300 + seed);
        for (int t = 0; t < 4000 && !e->terminated; t++) {
            env_step(e, legal_action(e, &r));
            if (t % 97 == 0) {
                memcpy(ref, e, sizeof *e);
                ref->px = ref->py = -10; light_reference(ref);
                compared++;
                if (memcmp(ref->light, e->terrain_light, sizeof e->light)) bad++;
            }
        }
    }
    CHECK(bad == 0, "incremental light differs from reference in %d/%d samples", bad, compared);
    /* Night sky level in an open column. */
    env_reset(e, 3);
    e->steps = DAY_STEPS - 1; env_step(e, ACT_NOOP);
    CHECK(is_night(e) && e->terrain_light[0][0] == NIGHT_SKY_LIGHT, "night sky light %d", e->terrain_light[0][0]);
    e->steps = DAY_CYCLE - 1; e->health = e->max_health = HEALTH_CAP; env_step(e, ACT_NOOP);
    CHECK(!is_night(e) && e->terrain_light[0][0] == LIGHT_MAX, "day sky light %d", e->terrain_light[0][0]);
    free(e); free(ref);
}

/* ---- fixtures ------------------------------------------------------------ */

/* Flat stone arena: open air above row FLOOR, player standing at (60, FLOOR-1),
   no mobs, no chests. */
#define FLOOR 40
static void arena(Env *e, int steps) {
    env_reset(e, 1);
    for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) {
        e->tiles[y][x] = y < FLOOR ? TILE_AIR : y >= WORLD_H - BEDROCK_ROWS ? TILE_BEDROCK : TILE_STONE;
        e->object_part[y][x] = 0;
    }
    for (int x = 0; x < WORLD_W; x++) e->surface[x] = FLOOR;
    memset(e->mobs, 0, sizeof e->mobs);
    memset(&e->boss, 0, sizeof e->boss);
    e->chest_count = 0;
    e->px = 60; e->py = FLOOR - 1; e->facing = 1;
    sync_body(e);
    e->steps = steps;
    e->terrain_dirty = true; light_full(e);
}

static int count_kind(const Env *e, int kind) {
    int n = 0;
    for (int i = 0; i < MAX_MOBS; i++) n += e->mobs[i].kind == kind;
    return n;
}

static void test_spawns(void) {
    Env *e = new_env(100000);
    int seen[MOB_KINDS] = {0};
    arena(e, DAY_STEPS);                     /* dusk */
    for (int t = 0; t < NIGHT_STEPS - 1; t++) {
        e->health = e->max_health; no_iframes(e);
        Mob before[MAX_MOBS]; memcpy(before, e->mobs, sizeof before);
        env_step(e, ACT_NOOP);
        for (int i = 0; i < MAX_MOBS; i++)
            if (e->mobs[i].kind && (!before[i].kind || before[i].kind != e->mobs[i].kind)) seen[e->mobs[i].kind]++;
    }
    CHECK(seen[MOB_ZOMBIE] > 0 && seen[MOB_DEMON_EYE] > 0, "night spawns: zombies %d demon eyes %d",
          seen[MOB_ZOMBIE], seen[MOB_DEMON_EYE]);
    CHECK(seen[MOB_BLUE_SLIME] == 0, "slimes spawned at night: %d", seen[MOB_BLUE_SLIME]);
    printf("night surface spawns over %d steps: %d zombies, %d demon eyes\n", NIGHT_STEPS - 1,
           seen[MOB_ZOMBIE], seen[MOB_DEMON_EYE]);
    /* Dawn: survive-a-night, Demon Eyes leave. */
    for (int i = 0; i < MAX_MOBS; i++) if (!e->mobs[i].kind) { mob_place(&e->mobs[i], MOB_DEMON_EYE, DEMON_EYE_HP, 20, 30); break; }
    e->health = e->max_health;
    env_step(e, ACT_NOOP);
    CHECK(day_time(e) == 0 && has_ach(e, ACH_SURVIVE_NIGHT), "survive a night at dawn");
    CHECK(count_kind(e, MOB_DEMON_EYE) == 0, "demon eyes remain after dawn");
    /* Day: only slimes on the surface. */
    memset(seen, 0, sizeof seen);
    memset(e->mobs, 0, sizeof e->mobs);
    for (int t = 0; t < DAY_STEPS - 1; t++) {
        e->health = e->max_health; no_iframes(e);
        Mob before[MAX_MOBS]; memcpy(before, e->mobs, sizeof before);
        env_step(e, ACT_NOOP);
        for (int i = 0; i < MAX_MOBS; i++)
            if (e->mobs[i].kind && (!before[i].kind || before[i].kind != e->mobs[i].kind)) seen[e->mobs[i].kind]++;
    }
    CHECK(seen[MOB_BLUE_SLIME] > 0 && !seen[MOB_ZOMBIE] && !seen[MOB_DEMON_EYE], "day spawns slime %d zombie %d eye %d",
          seen[MOB_BLUE_SLIME], seen[MOB_ZOMBIE], seen[MOB_DEMON_EYE]);
    /* Caverns: skeletons (and bats). */
    memset(seen, 0, sizeof seen);
    arena(e, 0);
    for (int y = CAVERN_Y + 6; y < CAVERN_Y + 12; y++) for (int x = 0; x < WORLD_W; x++) e->tiles[y][x] = TILE_AIR;
    e->py = CAVERN_Y + 11; sync_body(e); e->terrain_dirty = true; light_full(e);
    for (int t = 0; t < 2400; t++) {
        e->health = e->max_health; no_iframes(e);
        Mob before[MAX_MOBS]; memcpy(before, e->mobs, sizeof before);
        env_step(e, ACT_NOOP);
        for (int i = 0; i < MAX_MOBS; i++)
            if (e->mobs[i].kind && (!before[i].kind || before[i].kind != e->mobs[i].kind)) seen[e->mobs[i].kind]++;
    }
    CHECK(seen[MOB_SKELETON] > 0 && seen[MOB_CAVE_BAT] > 0, "cavern spawns: skeletons %d bats %d", seen[MOB_SKELETON], seen[MOB_CAVE_BAT]);
    CHECK(has_ach(e, ACH_REACH_CAVERNS), "reach the caverns");
    /* Return to surface. */
    e->py = FLOOR - 1; e->px = 60; sync_body(e); e->surface[60] = e->surface[61] = FLOOR; e->health = e->max_health;
    env_step(e, ACT_NOOP);
    CHECK(has_ach(e, ACH_RETURN_SURFACE), "return to surface after the caverns");
    free(e);
}

/* Put a mob in the melee box and swing until it dies. The mob is pinned to
   the cell two columns ahead every step (keeping its HP and hit immunity). */
static void kill_one(Env *e, int kind) {
    for (int i = 0; i < MAX_MOBS; i++) e->mobs[i].kind = MOB_NONE;
    mob_place(&e->mobs[0], kind, mob_max_hp(kind), e->px + 2, e->py);
    for (int t = 0; t < 400 && e->mobs[0].kind; t++) {
        Mob *m = &e->mobs[0];
#if FID_COMBAT
        int immune = m->immune;
#endif
        mob_place(m, kind, m->hp, e->px + 2, e->py);
#if FID_COMBAT
        m->immune = immune;
#endif
        e->facing = 1; e->health = e->max_health; no_iframes(e);
        uint8_t mask[ACT_COUNT]; env_action_mask(e, mask);
        env_step(e, mask[ACT_ATTACK] ? ACT_ATTACK : ACT_NOOP);
    }
}

static void test_combat_and_lens(void) {
    Env *e = new_env(1000000);
    arena(e, 0);
    e->inv[ITEM_GOLD_SWORD] = 1; e->weapon = 5;
    kill_one(e, MOB_ZOMBIE);
    CHECK(has_ach(e, ACH_KILL_ZOMBIE), "defeat Zombie");
    kill_one(e, MOB_SKELETON);
    CHECK(has_ach(e, ACH_KILL_SKELETON), "defeat Skeleton");
    kill_one(e, MOB_BLUE_SLIME);
    CHECK(has_ach(e, ACH_KILL_SLIME) && e->inv[ITEM_GEL] == 2, "defeat Blue Slime + gel");
    int kills = 600;
    for (int k = 0; k < kills; k++) { e->steps = 0; kill_one(e, MOB_DEMON_EYE); }
    double rate = (double)e->inv[ITEM_LENS] / kills;
    printf("lens drops: %d / %d demon eyes (%.1f%%, knob %d%%)\n", e->inv[ITEM_LENS], kills, 100 * rate, LENS_DROP_PCT);
    CHECK(has_ach(e, ACH_KILL_DEMON_EYE) && has_ach(e, ACH_COLLECT_LENS), "defeat Demon Eye / collect lens");
    CHECK(rate > LENS_DROP_PCT / 100.0 - 0.07 && rate < LENS_DROP_PCT / 100.0 + 0.07, "lens drop rate %.3f", rate);
    CHECK(!has_ach(e, ACH_DEFEAT_EOC), "no stray boss achievement");
    /* Contact damage from a zombie, reduced by armor. */
    arena(e, DAY_STEPS);
    mob_place(&e->mobs[0], MOB_ZOMBIE, ZOMBIE_HP, e->px, e->py);
    int h = e->health;
    env_step(e, ACT_NOOP);
    CHECK(contact_damage_ok(h - e->health, ZOMBIE_DMG, e->armor), "zombie contact damage %d (raw %d)", h - e->health, ZOMBIE_DMG);
    free(e);
}

static void test_altar_and_summon(void) {
    Env *e = new_env(1000000);
    uint8_t mask[ACT_COUNT];
    arena(e, 0);
    e->inv[ITEM_LENS] = EYE_LENSES;
    env_action_mask(e, mask);
    CHECK(!mask[ACT_CRAFT_SUSPICIOUS_EYE], "eye craftable without an altar");
    env_object_write(e, TILE_DEMON_ALTAR, e->px + 2, e->py); light_full(e);
    env_action_mask(e, mask);
    CHECK(mask[ACT_CRAFT_SUSPICIOUS_EYE], "eye not craftable next to an altar");
    int mine = ACT_MINE_FIRST + 6;   /* foot-right: the altar cell */
    CHECK(tile_at(e, e->px + REACH_DX[6], e->py + REACH_DY[6]) == TILE_DEMON_ALTAR && !mask[mine], "altar is mineable");
    e->inv[ITEM_LENS] = EYE_LENSES - 1;
    env_action_mask(e, mask);
    CHECK(!mask[ACT_CRAFT_SUSPICIOUS_EYE], "eye craftable with too few lenses");
    e->inv[ITEM_LENS] = EYE_LENSES;
    env_step(e, ACT_CRAFT_SUSPICIOUS_EYE);
    CHECK(e->inv[ITEM_SUSPICIOUS_EYE] == 1 && e->inv[ITEM_LENS] == 0 && has_ach(e, ACH_CRAFT_EYE), "craft Suspicious Looking Eye");
    /* Summon legality: night, the item, no boss. */
    env_action_mask(e, mask);
    CHECK(!mask[ACT_SUMMON], "summon legal by day");
    env_step(e, ACT_SUMMON);
    CHECK(!e->boss.active && e->inv[ITEM_SUSPICIOUS_EYE] == 1, "day summon had an effect");
    e->steps = DAY_STEPS;
    env_action_mask(e, mask);
    CHECK(mask[ACT_SUMMON], "summon illegal at night with the eye");
    e->inv[ITEM_SUSPICIOUS_EYE] = 0;
    env_action_mask(e, mask);
    CHECK(!mask[ACT_SUMMON], "summon legal without the eye");
    e->inv[ITEM_SUSPICIOUS_EYE] = 2;
    env_step(e, ACT_SUMMON);
    CHECK(e->boss.active && e->boss.hp == EOC_HP && has_ach(e, ACH_SUMMON_EOC) && e->inv[ITEM_SUSPICIOUS_EYE] == 1,
          "summon the Eye of Cthulhu");
    env_action_mask(e, mask);
    CHECK(!mask[ACT_SUMMON], "second summon legal while the boss lives");
    /* Recipes: gold chainmail equips armor level 3; D16 quantities. */
    env_object_write(e, TILE_ANVIL, e->px - 3, e->py); light_full(e);
    e->inv[ITEM_GOLD_BAR] = GOLD_ARMOR_BARS; e->inv[ITEM_IRON_BAR] = IRON_PICK_BARS - 1; e->inv[ITEM_WOOD] = 10;
    env_action_mask(e, mask);
    CHECK(mask[ACT_CRAFT_GOLD_ARMOR] && !mask[ACT_CRAFT_IRON_PICK], "recipe quantities");
    env_step(e, ACT_CRAFT_GOLD_ARMOR);
    CHECK(e->armor == 3 && e->inv[ITEM_GOLD_ARMOR] == 1, "gold chainmail");
    free(e);
}

/* D24 stepping stones: an altar inside the crafting-station square, and
   holding EYE_LENSES lenses; both tier 4 (weight 8), max score 145. */
static void test_stepping_stones(void) {
    Env *e = new_env(1000000);
    arena(e, 0);
    /* Station square: columns px-3 .. px+PLAYER_W+2. Altar cells start at
       its left anchor, so an anchor at px+PLAYER_W+3 is just out of range. */
    env_object_write(e, TILE_DEMON_ALTAR, e->px + PLAYER_W + 3, e->py); light_full(e);
    env_step(e, ACT_NOOP);
    CHECK(!has_ach(e, ACH_FIND_ALTAR), "find a Demon Altar out of crafting range");
    env_object_remove(e, e->px + PLAYER_W + 3, e->py);
    env_object_write(e, TILE_DEMON_ALTAR, e->px + PLAYER_W + 2, e->py); light_full(e);
    float r0 = e->ep_return;
    env_step(e, ACT_NOOP);
    CHECK(has_ach(e, ACH_FIND_ALTAR) && e->ep_return - r0 == 1.0f, "find a Demon Altar in crafting range");
    e->inv[ITEM_LENS] = EYE_LENSES - 1; env_step(e, ACT_NOOP);
    CHECK(!has_ach(e, ACH_HOLD_LENSES), "hold lenses with %d", EYE_LENSES - 1);
    e->inv[ITEM_LENS] = EYE_LENSES; env_step(e, ACT_NOOP);
    CHECK(has_ach(e, ACH_HOLD_LENSES), "hold %d lenses", EYE_LENSES);
    int max = 0, tiers[TIER_COUNT + 1] = {0};
    for (int a = 0; a < ACH_COUNT; a++) { max += TIER_WEIGHT[ACH_TIER[a]]; tiers[ACH_TIER[a]]++; }
    CHECK(ACH_TIER[ACH_FIND_ALTAR] == 4 && ACH_TIER[ACH_HOLD_LENSES] == 4 && max == 145 &&
          tiers[1] == 13 && tiers[2] == 12 && tiers[3] == 8 && tiers[4] == 7, "tiers 13/12/8/7, max %d", max);
    free(e);
}

#if !FID_PHYSICS
static bool boss_in_box(const Env *e, int facing) {
    int x0 = facing > 0 ? e->px : e->px - 2, x1 = facing > 0 ? e->px + PLAYER_W + 1 : e->px + PLAYER_W - 1;
    const Boss *b = &e->boss;
    return b->x <= x1 && b->x + EOC_SIZE - 1 >= x0 && b->y <= e->py && b->y + EOC_SIZE - 1 >= e->py - PLAYER_H + 1;
}
#endif

static void test_boss(void) {
    Env *e = new_env(1000000);
    arena(e, DAY_STEPS);
    e->inv[ITEM_SUSPICIOUS_EYE] = 1;
    env_step(e, ACT_SUMMON);
    int modes[3] = {0}, max_speed1 = 0, max_speed2 = 0, hits = 0;
    for (int t = 0; t < 300; t++) {
        int bx = e->boss.x, by = e->boss.y;
        e->health = e->max_health = HEALTH_CAP;
        memset(e->mobs, 0, sizeof e->mobs);   /* boss damage only */
        int h = e->health;
        env_step(e, ACT_NOOP);
        modes[e->boss.mode]++;
        int sp = abs(e->boss.x - bx) > abs(e->boss.y - by) ? abs(e->boss.x - bx) : abs(e->boss.y - by);
        if (sp > max_speed1) max_speed1 = sp;
        if (e->health < h) { hits++; CHECK(contact_damage_ok(h - e->health, EOC_DMG1, e->armor), "phase 1 damage %d", h - e->health); }
    }
    CHECK(modes[BOSS_HOVER] && modes[BOSS_DASH] && modes[BOSS_PAUSE], "phase 1 modes %d/%d/%d", modes[0], modes[1], modes[2]);
    CHECK(max_speed1 == EOC_DASH_SPEED1 && hits > 0, "phase 1 dash speed %d, %d hits", max_speed1, hits);
    e->boss.hp = EOC_HP / 2; hits = 0;
    for (int t = 0; t < 300; t++) {
        int bx = e->boss.x, by = e->boss.y;
        e->health = HEALTH_CAP; int h = e->health;
        memset(e->mobs, 0, sizeof e->mobs);
        env_step(e, ACT_NOOP);
        int sp = abs(e->boss.x - bx) > abs(e->boss.y - by) ? abs(e->boss.x - bx) : abs(e->boss.y - by);
        if (sp > max_speed2) max_speed2 = sp;
        if (e->health < h) { hits++; CHECK(contact_damage_ok(h - e->health, EOC_DMG2, e->armor), "phase 2 damage %d", h - e->health); }
    }
    CHECK(max_speed2 == EOC_DASH_SPEED2 && hits > 0, "phase 2 dash speed %d, %d hits", max_speed2, hits);
    Obs o; env_obs(e, &o);
    CHECK(o.status[OBS_BOSS] == 1 && o.status[OBS_BOSS + 2] == 1 && o.status[OBS_BOSS + 1] > 0.49f && o.status[OBS_BOSS + 1] < 0.51f,
          "boss status block");
    /* Defeat. */
    e->boss.hp = 1; e->boss.x = e->px + 2; e->boss.y = e->py - 2; e->boss.mode = BOSS_PAUSE; e->boss.timer = 5;
    e->facing = 1; e->attack_cd = 0;
    env_step(e, ACT_ATTACK);
    CHECK(!e->boss.active && has_ach(e, ACH_DEFEAT_EOC) && e->inv[ITEM_DEMONITE_ORE] >= EOC_DEMONITE_MIN, "defeat the Eye of Cthulhu");
    /* Dawn despawn. */
    arena(e, DAY_CYCLE - 3);
    e->inv[ITEM_SUSPICIOUS_EYE] = 1; env_step(e, ACT_SUMMON);
    CHECK(e->boss.active, "summon before dawn");
    e->health = HEALTH_CAP; e->max_health = HEALTH_CAP; env_step(e, ACT_NOOP);
    e->health = HEALTH_CAP; env_step(e, ACT_NOOP);
    CHECK(day_time(e) == 0 && !e->boss.active, "boss despawns at dawn");
    /* Death despawn. */
    arena(e, DAY_STEPS);
    e->inv[ITEM_SUSPICIOUS_EYE] = 1; env_step(e, ACT_SUMMON);
    e->boss.x = e->px; e->boss.y = e->py - 2; e->boss.mode = BOSS_PAUSE; e->boss.timer = 50; e->health = 1; no_iframes(e);
    env_step(e, ACT_NOOP);
    CHECK(e->terminated && !e->boss.active, "boss despawns when the player dies");
    free(e);
}

#if FID_PHYSICS
/* Fighter for the free-moving hitbox: nearest threat (a regular mob within 4
   columns and rows, else the boss); walk toward it, stop when close (the
   body carries momentum), face it and swing when it is within reach. */
static int fight_action(const Env *e, const uint8_t *mask) {
    int pcx = (int)(player_fx(e) >> 16) + PLAYER_PX_W / 2, ptop = (int)(player_fy(e) >> 16), pbot = ptop + PLAYER_PX_H;
    int tx = 0, t0 = 0, t1 = 0, best = 1 << 30, half = 8;
    for (int i = 0; i < MAX_MOBS; i++) {
        const Mob *m = &e->mobs[i];
        int d = abs(m->x * 16 + 8 - pcx);
        if (m->kind && d <= 64 && abs(m->y - e->py) <= 4 && d < best) {
            best = d; tx = m->x * 16 + 8; t0 = m->y * 16 - 8; t1 = m->y * 16 + 24; half = 12;
        }
    }
    if (best == 1 << 30) { tx = e->boss.x * 16 + 24; t0 = e->boss.y * 16; t1 = t0 + 48; half = 24; }
    int dx = tx - pcx, dir = dx > 0 ? 1 : -1;
    if (t1 > ptop - 40 && t0 < pbot && abs(dx) <= 36 + half) {
        if (dir == e->facing || abs(dx) < 4) return mask[ACT_ATTACK] ? ACT_ATTACK : ACT_NOOP;
        return dir > 0 ? ACT_RIGHT : ACT_LEFT;
    }
    if (abs(dx) > 24) return dir > 0 ? ACT_RIGHT : ACT_LEFT;
    return ACT_NOOP;
}
#endif

/* Scripted fight on flat ground at night (regular night mobs included):
   iron broadsword, iron chainmail, +2 Life Crystals (140 HP), 3 healing
   potions, drink below 40% HP. Grid player (v9's script): chase the boss
   column, face it, swing when it is in the box. FID_PHYSICS: fight_action. */
static void test_fight(void) {
    Env *e = new_env(1000000);
    int wins = 0, n = 200, ticks = 0;
    for (int s = 0; s < n; s++) {
        arena(e, DAY_STEPS);
        e->rng ^= (uint64_t)s * 0x9E3779B97F4A7C15ull;
        e->inv[ITEM_IRON_SWORD] = 1; e->weapon = 3; e->armor = 2;
        e->max_health = e->health = MAX_HEALTH + 40; e->inv[ITEM_LESSER_POTION] = 3;
        e->inv[ITEM_SUSPICIOUS_EYE] = 1; env_step(e, ACT_SUMMON);
        int t = 0;
        for (; t < NIGHT_STEPS - 2 && e->boss.active && !e->terminated; t++) {
            int act;
            uint8_t mask[ACT_COUNT]; env_action_mask(e, mask);
            if (e->health * 10 < e->max_health * 4 && e->inv[ITEM_LESSER_POTION] && !e->heal_cd) act = ACT_HEAL_POTION;
            else {
#if FID_PHYSICS
                act = fight_action(e, mask);
#else
                int dir = e->boss.x + 1 >= e->px + 1 ? 1 : -1;
                if (mask[ACT_ATTACK] && boss_in_box(e, e->facing)) act = ACT_ATTACK;
                else if (mask[ACT_ATTACK] && boss_in_box(e, -e->facing)) act = e->facing > 0 ? ACT_LEFT : ACT_RIGHT;
                else act = dir > 0 ? ACT_RIGHT : ACT_LEFT;
#endif
            }
            env_step(e, act);
        }
        wins += has_ach(e, ACH_DEFEAT_EOC);
        ticks += t;
    }
    printf("scripted EoC fight (iron sword+chainmail, 140 HP, 3 potions): %d/%d wins, mean %.0f steps\n",
           wins, n, (double)ticks / n);
    /* The EoC knobs are tuned for the two shipped rule sets (combat and
       physics both ported, or both v9); mixed ablation builds only report. */
    if (FID_COMBAT == FID_PHYSICS)
        CHECK(wins * 10 >= n * 9, "scripted EoC fight win rate %d/%d below 90%%", wins, n);
    else printf("  (mixed FID_COMBAT/FID_PHYSICS ablation: win rate reported, not gated)\n");
    free(e);
}

/* ---- worldgen supply ----------------------------------------------------- */

static int cmp_int(const void *a, const void *b) { return *(const int *)a - *(const int *)b; }

static void test_worldgen(int worlds) {
    enum { COPPER, IRON, SILVER, GOLD, WOOD, ALTARS, CRYSTALS, CHESTS, STATS };
    static const char *NAMES[STATS] = {"copper ore", "iron ore", "silver ore (caverns)", "gold ore (lower caverns)",
                                       "trunk tiles within reach", "demon altars (caverns)", "life crystals", "chests"};
    /* FID_TREES: ~1.93 wood per trunk tile, so WOOD_MIN wood is fewer tiles (worldgen.c). */
    static const int MINS[STATS] = {COPPER_MIN, IRON_MIN, SILVER_MIN, GOLD_MIN,
                                    FID_TREES ? (WOOD_MIN * 100 + 192) / 193 : WOOD_MIN, ALTAR_MIN, CRYSTAL_MIN, 0};
    int *v[STATS];
    for (int k = 0; k < STATS; k++) v[k] = calloc((size_t)worlds, sizeof(int));
    Env *e = new_env(0);
    int bad_altar = 0, misplaced = 0;
    for (int w = 0; w < worlds; w++) {
        env_reset(e, (uint64_t)(w < worlds / 2 ? w : 23000001 + w));
        for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) {
            Tile t = (Tile)e->tiles[y][x];
            if (t == TILE_COPPER_ORE) v[COPPER][w]++;
            if (t == TILE_IRON_ORE) v[IRON][w]++;
            if (t == TILE_SILVER_ORE) { v[SILVER][w]++; misplaced += y < CAVERN_Y; }
            if (t == TILE_GOLD_ORE) { v[GOLD][w]++; misplaced += y < GOLD_MIN_Y; }
            if (t == TILE_LOG && abs(x - e->px) <= WOOD_REACH) v[WOOD][w]++;
            if (t == TILE_DEMON_ALTAR && e->object_part[y][x] == 3) {   /* bottom-left part */
                v[ALTARS][w]++;
                bad_altar += y < CAVERN_Y || !tile_solid(tile_at(e, x, y + 1));
            }
            if (t == TILE_LIFE_CRYSTAL && e->object_part[y][x] == 2) v[CRYSTALS][w]++;
        }
        v[CHESTS][w] = e->chest_count;
    }
    printf("worldgen supply over %d worlds (seeds 0-%d and 23000001+):\n", worlds, worlds / 2 - 1);
    printf("  %-26s %6s %6s %6s %6s %8s\n", "resource", "min", "p10", "median", "max", "floor");
    for (int k = 0; k < STATS; k++) {
        qsort(v[k], (size_t)worlds, sizeof(int), cmp_int);
        printf("  %-26s %6d %6d %6d %6d %8d\n", NAMES[k], v[k][0], v[k][worlds / 10], v[k][worlds / 2], v[k][worlds - 1], MINS[k]);
        CHECK(v[k][0] >= MINS[k], "%s minimum %d below floor %d", NAMES[k], v[k][0], MINS[k]);
        free(v[k]);
    }
    CHECK(bad_altar == 0, "%d altars outside the caverns or floating", bad_altar);
    CHECK(misplaced == 0, "%d silver/gold tiles outside their layer", misplaced);
    free(e);
}

/* 40 achievements need 64-bit masks end to end, including the info rows. */
static void test_info_rows(void) {
    Env *e = new_env(0);
    env_reset(e, 5);
    e->achievements = (1ull << ACH_DEFEAT_EOC) | (1ull << ACH_RETURN_SURFACE) | 1ull;
    e->max_steps = e->steps + 1;
    static Obs obs, fin;
    uint8_t mask[ACT_COUNT]; float rew, ret; int end, lane, act = ACT_NOOP, info[8] = {0};
    int n = tl_batch_step_autoreset(&e, 1, &act, &obs, 0, mask, &rew, &end, &fin, info, &ret, &lane, 77, 1);
    uint64_t got = (uint64_t)(uint32_t)info[3] | ((uint64_t)(uint32_t)info[4] << 32);
    CHECK(tl_info_width() == 5 && n == 1 && end == 2 && got == ((1ull << ACH_DEFEAT_EOC) | (1ull << ACH_RETURN_SURFACE) | 1ull),
          "autoreset info mask %llx (width %d)", (unsigned long long)got, tl_info_width());
    CHECK(e->seed == 77 && e->achievements == 0, "lane reset");
    free(e);
}

int main(int argc, char **argv) {
    int worlds = argc > 1 ? atoi(argv[1]) : 512;
    printf("v10 selftest (FID_MOBS=%d COMBAT=%d PHYSICS=%d MINING=%d TREES=%d, FID_TICKS=%d): Env %zu bytes, "
           "obs status %d, actions %d, achievements %d\n", FID_MOBS, FID_COMBAT, FID_PHYSICS, FID_MINING, FID_TREES,
           FID_TICKS, sizeof(Env), OBS_STATUS, ACT_COUNT, ACH_COUNT);
    test_determinism();
    test_light_parity();
    test_spawns();
    test_combat_and_lens();
    test_altar_and_summon();
    test_stepping_stones();
    test_boss();
    test_fight();
    test_worldgen(worlds);
    test_info_rows();
    printf("%s: %d/%d checks passed\n", failures ? "FAILED" : "PASSED", checks - failures, checks);
    return failures != 0;
}
