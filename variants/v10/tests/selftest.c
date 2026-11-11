/* v10 gates (docs/ENV_V9_DESIGN.md sections 10 and 14): determinism, save/load,
   incremental-vs-reference lighting across day/night, one fixture per v9
   mechanic (with whatever FID_* ports the build has), the D24 stepping
   stones, a scripted Eye of Cthulhu fight, and worldgen supply statistics.
   Port-level fixtures against the real constants are in tests/fid_test.c.

     cc -std=c11 -O2 -Ivariants/v10/include variants/v10/src/{sim,worldgen,light,obs,mobs,boss}.c \
        src/capi.c variants/v10/tests/selftest.c -o /tmp/v10-selftest -lm && /tmp/v10-selftest [worlds]
   (add -DFID_MOBS=0 -DFID_COMBAT=0 -DFID_PHYSICS=0 -DFID_MINING=0 -DFID_TREES=0 -DTREE_LEAF_VISUAL=0
    -DSUPPORT_RULES=0 -DEXPLICIT_TOOLS=0 -DTOOL_DAMAGE=0 -DBG_WALLS=0 for the noport build; -DENV_FX=1
    for the side-channel fixture)
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
   no mobs, no chests, no walls. */
#define FLOOR 40
static void arena(Env *e, int steps) {
    env_reset(e, 1);
    for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) {
        e->tiles[y][x] = y < FLOOR ? TILE_AIR : y >= WORLD_H - BEDROCK_ROWS ? TILE_BEDROCK : TILE_STONE;
        e->object_part[y][x] = 0;
    }
    for (int x = 0; x < WORLD_W; x++) e->surface[x] = FLOOR;
#if BG_WALLS
    memset(e->wall, 0, sizeof e->wall);
#endif
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

/* ---- tile rules (TREE_LEAF_VISUAL, SUPPORT_RULES) and the fx channel ---- */

#if SUPPORT_RULES || ENV_FX
static bool mask_of(const Env *e, int act) { uint8_t m[ACT_COUNT]; env_action_mask(e, m); return m[act]; }
#endif
/* A rejected place: its mask says so (HELD_PLACE: these fixtures stand still,
   so no tick of the step reaches the cell either). */
#define REFUSED(legal, ok) (!(legal) && !(ok))

#if SUPPORT_RULES
static void relight(Env *e) { e->terrain_dirty = true; light_full(e); }

/* Incremental terrain light still equals the uncached reference. */
static bool light_exact(const Env *e) {
    static Env ref;
    memcpy(&ref, e, sizeof ref);
    ref.px = ref.py = -10; light_reference(&ref);
    return memcmp(ref.light, e->terrain_light, sizeof e->light) == 0;
}

/* Every air cell has object_part 0 and every object cell its own frame. */
static bool parts_exact(const Env *e) {
    for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) {
        Tile t = (Tile)e->tiles[y][x];
        if (e->object_part[y][x] >= tile_object_w(t) * tile_object_h(t)) return false;
    }
    return true;
}

static int reach_to(const Env *e, int x, int y) {
    for (int r = 0; r < REACH_COUNT; r++) if (e->px + REACH_DX[r] == x && e->py + REACH_DY[r] == y) return r;
    return -1;
}

/* Hold the mine action on (x, y) for up to 12 steps; true once it is air. */
static bool mine_cell(Env *e, int x, int y) {
    int r = reach_to(e, x, y);
    for (int t = 0; t < 12 && r >= 0 && tile_at(e, x, y) != TILE_AIR; t++) env_step(e, ACT_MINE_FIRST + r);
    return tile_at(e, x, y) == TILE_AIR;
}

/* Select placeable slot `slot` (PLACEABLES), stock it, report mask and result. */
static bool place_at(Env *e, int slot, int x, int y, bool *legal) {
    int r = reach_to(e, x, y);
    e->selected = (uint8_t)slot; e->inv[PLACEABLES[slot].item] = 5;
    *legal = mask_of(e, ACT_PLACE_FIRST + r);
    env_step(e, ACT_PLACE_FIRST + r);
    return tile_at(e, x, y) == PLACEABLES[slot].tile;
}

enum { SLOT_TORCH = 3, SLOT_WORKBENCH = 5, SLOT_FURNACE = 6, SLOT_PLATFORM = 8, SLOT_ROPE = 9 };
#endif

static void test_support(void) {
#if SUPPORT_RULES
    Env *e = new_env(1000000);
    const int X = 62, F = FLOOR;   /* the column right of the body; F is the stone floor row */
    bool legal, ok;

    /* Torch: mid-air illegal (mask and handler agree); on the floor legal. */
    arena(e, 0);
    ok = place_at(e, SLOT_TORCH, X, F - 4, &legal);
    CHECK(REFUSED(legal, ok) && e->inv[ITEM_TORCH] == 5, "torch in mid-air: mask %d placed %d", legal, ok);
    ok = place_at(e, SLOT_TORCH, X, F - 1, &legal);
    CHECK(legal && ok, "torch on the floor: mask %d placed %d", legal, ok);
    /* Anchored only below: mining the block drops the torch into the pack. */
    arena(e, 0);
    e->tiles[F - 3][X] = TILE_STONE; relight(e);
    ok = place_at(e, SLOT_TORCH, X, F - 4, &legal);
    CHECK(legal && ok, "torch on a block: mask %d placed %d", legal, ok);
    int torches = e->inv[ITEM_TORCH], stone = e->inv[ITEM_STONE];
    CHECK(mine_cell(e, X, F - 3), "mine the torch's block");
    CHECK(tile_at(e, X, F - 4) == TILE_AIR && e->inv[ITEM_TORCH] == torches + 1 && e->inv[ITEM_STONE] == stone + 1,
          "unanchored torch breaks and drops (tile %d, torches %d->%d)", tile_at(e, X, F - 4), torches, e->inv[ITEM_TORCH]);
    CHECK(light_exact(e) && parts_exact(e), "light/object parts exact after the torch broke");
    /* A second anchor (block to the left) keeps it. */
    arena(e, 0);
    e->tiles[F - 3][X] = TILE_STONE; e->tiles[F - 4][X - 1] = TILE_STONE; relight(e);
    ok = place_at(e, SLOT_TORCH, X, F - 4, &legal);
    CHECK(ok && mine_cell(e, X, F - 3) && tile_at(e, X, F - 4) == TILE_TORCH, "torch with a side anchor stays");

    /* Rope: hangs below a block or rope; the chain falls with its anchor. */
    arena(e, 0);
    ok = place_at(e, SLOT_ROPE, X, F - 3, &legal);
    CHECK(REFUSED(legal, ok), "rope in mid-air: mask %d placed %d", legal, ok);
    e->tiles[F - 4][X] = TILE_STONE; relight(e);
    bool l1, l2, l3;
    ok = place_at(e, SLOT_ROPE, X, F - 3, &l1) && place_at(e, SLOT_ROPE, X, F - 2, &l2) && place_at(e, SLOT_ROPE, X, F - 1, &l3);
    CHECK(ok && l1 && l2 && l3, "rope chain below a block");
    int ropes = e->inv[ITEM_ROPE];
    CHECK(mine_cell(e, X, F - 2), "mine the middle rope");
    CHECK(tile_at(e, X, F - 3) == TILE_ROPE && tile_at(e, X, F - 1) == TILE_AIR && e->inv[ITEM_ROPE] == ropes + 2,
          "rope below the cut falls (ropes %d->%d)", ropes, e->inv[ITEM_ROPE]);
    ok = place_at(e, SLOT_ROPE, X, F - 2, &l1) && place_at(e, SLOT_ROPE, X, F - 1, &l2);
    ropes = e->inv[ITEM_ROPE];
    CHECK(ok && mine_cell(e, X, F - 4), "mine the rope's anchor");
    CHECK(tile_at(e, X, F - 3) == TILE_AIR && tile_at(e, X, F - 2) == TILE_AIR && tile_at(e, X, F - 1) == TILE_AIR
          && e->inv[ITEM_ROPE] == ropes + 3, "whole rope chain falls (ropes %d->%d)", ropes, e->inv[ITEM_ROPE]);
    CHECK(light_exact(e) && parts_exact(e), "light/object parts exact after the rope fell");

    /* Platform: beside a platform or block, or on a block; not in mid-air. */
    arena(e, 0);
    ok = place_at(e, SLOT_PLATFORM, X, F - 3, &legal);
    CHECK(REFUSED(legal, ok), "platform in mid-air: mask %d placed %d", legal, ok);
    ok = place_at(e, SLOT_PLATFORM, X, F - 1, &legal);
    CHECK(legal && ok, "platform on the floor");
    ok = place_at(e, SLOT_PLATFORM, X, F - 2, &legal);
    CHECK(REFUSED(legal, ok), "platform on a platform needs a side anchor: mask %d placed %d", legal, ok);
    e->tiles[F - 3][X + 1] = TILE_PLATFORM; relight(e);
    ok = place_at(e, SLOT_PLATFORM, X, F - 3, &legal);
    CHECK(legal && ok, "platform beside a platform");

    /* Furniture: solid under every bottom cell; a workbench also on platforms. */
    arena(e, 0);
    ok = place_at(e, SLOT_WORKBENCH, X, F - 2, &legal);
    CHECK(REFUSED(legal, ok), "workbench in mid-air: mask %d placed %d", legal, ok);
    for (int x = X; x < X + 3; x++) e->tiles[F - 2][x] = TILE_PLATFORM;
    relight(e);
    ok = place_at(e, SLOT_FURNACE, X, F - 3, &legal);
    CHECK(REFUSED(legal, ok), "furnace on platforms: mask %d placed %d", legal, ok);
    ok = place_at(e, SLOT_WORKBENCH, X, F - 3, &legal);
    CHECK(legal && ok, "workbench on platforms: mask %d placed %d", legal, ok);
    arena(e, 0);
    e->tiles[F][X + 1] = TILE_AIR; relight(e);
    ok = place_at(e, SLOT_WORKBENCH, X, F - 1, &legal);
    CHECK(REFUSED(legal, ok), "workbench over a hole: mask %d placed %d", legal, ok);
    arena(e, 0);
    ok = place_at(e, SLOT_WORKBENCH, X, F - 1, &legal);
    CHECK(legal && ok, "workbench on the floor");
    int benches = e->inv[ITEM_WORKBENCH];
    CHECK(mine_cell(e, X, F), "mine under the workbench");
    CHECK(tile_at(e, X, F - 1) == TILE_AIR && tile_at(e, X + 1, F - 1) == TILE_AIR && e->inv[ITEM_WORKBENCH] == benches + 1,
          "unsupported workbench breaks and drops");
    CHECK(light_exact(e) && parts_exact(e), "light/object parts exact after the workbench broke");
    /* Campfire (an emitter): the light map loses it exactly. */
    arena(e, 0);
    env_object_write(e, TILE_CAMPFIRE, X, F - 1); relight(e);
    CHECK(mine_cell(e, X, F) && tile_at(e, X + 1, F - 2) == TILE_AIR && e->inv[ITEM_CAMPFIRE] == 1, "campfire breaks");
    CHECK(light_exact(e) && parts_exact(e), "light exact after the campfire broke");

    /* Mushroom and life crystal break with their ground and drop. */
    arena(e, 0);
    e->tiles[F - 1][X] = TILE_MUSHROOM; relight(e);
    CHECK(mine_cell(e, X, F) && tile_at(e, X, F - 1) == TILE_AIR && e->inv[ITEM_MUSHROOM] == 1, "mushroom breaks with its ground");
    arena(e, 0);
#if EXPLICIT_TOOLS
    e->inv[ITEM_COPPER_PICK] = 1;
#else
    e->tool_tier = TIER_COPPER_PICK;
#endif
    env_object_write(e, TILE_LIFE_CRYSTAL, X, F - 1); relight(e);
    CHECK(mine_cell(e, X, F) && tile_at(e, X + 1, F - 2) == TILE_AIR && e->inv[ITEM_LIFE_CRYSTAL] == 1, "life crystal breaks and drops");
    CHECK(light_exact(e) && parts_exact(e), "light/object parts exact after the crystal broke");

    /* Chest: the block under an unopened chest cannot be mined; once looted
       the empty chest breaks with it (no item: chests are not craftable). */
    arena(e, 0);
    env_object_write(e, TILE_CHEST, X, F - 1);
    e->chests[0] = (Chest){X, F - 1, false, {0}}; e->chests[0].loot[ITEM_TORCH] = 3; e->chest_count = 1;
    relight(e);
    int r = reach_to(e, X, F);
    CHECK(!mask_of(e, ACT_MINE_FIRST + r), "mask forbids mining under an unopened chest");
    CHECK(!mine_cell(e, X, F) && tile_at(e, X, F - 1) == TILE_CHEST, "block under an unopened chest holds");
    CHECK(mask_of(e, ACT_INTERACT), "chest in reach");
    env_step(e, ACT_INTERACT);
    CHECK(tile_at(e, X, F - 1) == TILE_CHEST_OPEN && mask_of(e, ACT_MINE_FIRST + r), "looted chest's block minable");
    CHECK(mine_cell(e, X, F) && tile_at(e, X, F - 1) == TILE_AIR && tile_at(e, X + 1, F - 2) == TILE_AIR, "empty chest breaks");
    CHECK(light_exact(e) && parts_exact(e), "light/object parts exact after the chest broke");
    free(e);
#else
    printf("support rules: SUPPORT_RULES=0, fixtures skipped\n");
#endif
}

/* TREE_LEAF_VISUAL: no leaf cells in any world, trees still stand. */
static void test_tree_leaves(void) {
    Env *e = new_env(0);
    int leaves = 0, logs = 0;
    for (int s = 0; s < 16; s++) {
        env_reset(e, 23000001 + s);
        for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) {
            leaves += e->tiles[y][x] == TILE_LEAVES; logs += e->tiles[y][x] == TILE_LOG;
        }
    }
#if TREE_LEAF_VISUAL
    CHECK(leaves == 0 && logs > 0, "TREE_LEAF_VISUAL worlds: %d leaf cells, %d trunk cells", leaves, logs);
#else
    CHECK(leaves > 0 && logs > 0, "leaf cells %d, trunk cells %d", leaves, logs);
#endif
    free(e);
}

/* ENV_FX=1: the side channel reports this step's hits and per-tick bodies. */
static void test_fx(void) {
#if !ENV_FX
    printf("fx side channel: ENV_FX=0, fixture skipped\n");
#else
    Env *e = new_env(1000000);
    arena(e, 0);
    e->inv[ITEM_GOLD_SWORD] = 1; e->weapon = 5;
    mob_place(&e->mobs[0], MOB_ZOMBIE, ZOMBIE_HP, e->px + 2, e->py);
    int hp = e->mobs[0].hp, seen = 0, swings = 0;
    for (int t = 0; t < 20 && e->mobs[0].hp == hp; t++) {
        mob_place(&e->mobs[0], MOB_ZOMBIE, hp, e->px + 2, e->py);
        e->facing = 1; e->health = e->max_health; no_iframes(e);
        env_step(e, mask_of(e, ACT_ATTACK) ? ACT_ATTACK : ACT_NOOP);
        swings += e->fx.swing;
        for (int i = 0; i < e->fx.n_hits; i++)
            if (e->fx.hit[i].target == FX_TARGET_MOB && e->fx.hit[i].slot == 0) seen += e->fx.hit[i].dmg;
    }
    CHECK(swings > 0 && seen > 0 && e->mobs[0].kind && seen == hp - e->mobs[0].hp,
          "fx hit damage %d vs hp lost %d", seen, hp - e->mobs[0].hp);
    arena(e, DAY_STEPS);
    mob_place(&e->mobs[0], MOB_ZOMBIE, ZOMBIE_HP, e->px, e->py);
    int h = e->health;
    env_step(e, ACT_NOOP);
    int got = 0;
    for (int i = 0; i < e->fx.n_hits; i++) if (e->fx.hit[i].target == FX_TARGET_PLAYER) got += e->fx.hit[i].dmg;
    CHECK(got == h - e->health && got > 0, "fx player damage %d vs %d", got, h - e->health);
#if FID_TICKED
    CHECK(e->fx.path[FID_TICKS][FX_PLAYER][0] == (int16_t)(player_fx(e) >> 16)
          && e->fx.path[FID_TICKS][FX_PLAYER][1] == (int16_t)(player_fy(e) >> 16), "fx path ends at the player");
#endif
    free(e);
#endif
}

/* ---- explicit tools, tool swings, background walls ----------------------- */

#if EXPLICIT_TOOLS || BG_WALLS
static bool tw_mask(const Env *e, int act) { uint8_t m[ACT_COUNT]; env_action_mask(e, m); return m[act]; }
static int tw_reach(const Env *e, int x, int y) {
    for (int r = 0; r < REACH_COUNT; r++) if (e->px + REACH_DX[r] == x && e->py + REACH_DY[r] == y) return r;
    return -1;
}
static void tw_relight(Env *e) { e->terrain_dirty = true; light_full(e); }
#endif
#if BG_WALLS
/* Place PLACEABLES[slot] at (x, y): mask verdict and whether it landed. */
static bool tw_place(Env *e, int slot, int x, int y, bool *legal) {
    int r = tw_reach(e, x, y);
    e->selected = (uint8_t)slot; e->inv[PLACEABLES[slot].item] = 5;
    *legal = tw_mask(e, ACT_PLACE_FIRST + r);
    env_step(e, ACT_PLACE_FIRST + r);
    return tile_at(e, x, y) == PLACEABLES[slot].tile;
}
#endif

static void test_tools(void) {
#if EXPLICIT_TOOLS
    Env *e = new_env(1000000);
    const int X = 62, F = FLOOR;
    /* Terraria's starter set; the shortsword in hand; copper mining power. */
    env_reset(e, 5);
    int owned = 0;
    for (int i = 0; i < ITEM_COUNT; i++) owned += e->inv[i];
    CHECK(owned == 3 && e->inv[ITEM_COPPER_SHORTSWORD] == 1 && e->inv[ITEM_COPPER_PICK] == 1 && e->inv[ITEM_COPPER_AXE] == 1
          && e->held == ITEM_COPPER_SHORTSWORD && pick_tier(e) == TIER_COPPER_PICK, "starter inventory (%d items)", owned);
    static Obs o;
    env_obs(e, &o);
    CHECK(o.status[OBS_HELD_0 + ITEM_COPPER_SHORTSWORD] == 1.0f && o.status[OBS_INV_0 + ITEM_COPPER_PICK] > 0.0f,
          "held item and tools observed");
    /* Auto Select: the axe for a trunk, the best pickaxe for a block. */
    arena(e, 0);
    e->tiles[F - 1][X] = TILE_LOG; e->tiles[F - 2][X] = TILE_LOG; tw_relight(e);
    env_step(e, ACT_MINE_FIRST + tw_reach(e, X, F - 1));
    CHECK(e->held == ITEM_COPPER_AXE, "trunk auto-selects the axe (held %d)", e->held);
    arena(e, 0);
    e->inv[ITEM_COPPER_AXE] = 0;
    e->tiles[F - 1][X] = TILE_LOG; tw_relight(e);
    CHECK(!tw_mask(e, ACT_MINE_FIRST + tw_reach(e, X, F - 1)), "no axe: trunk not minable");
    arena(e, 0);
    e->tiles[F - 1][X] = TILE_STONE; tw_relight(e);
    env_step(e, ACT_MINE_FIRST + tw_reach(e, X, F - 1));
    CHECK(e->held == ITEM_COPPER_PICK, "block auto-selects the copper pickaxe (held %d)", e->held);
    arena(e, 0);
    e->inv[ITEM_GOLD_PICK] = 1; e->inv[ITEM_IRON_PICK] = 1;
    e->tiles[F - 1][X] = TILE_GOLD_ORE; tw_relight(e);
    env_step(e, ACT_MINE_FIRST + tw_reach(e, X, F - 1));
    CHECK(e->held == ITEM_GOLD_PICK && pick_tier(e) == TIER_GOLD_PICK, "best pickaxe auto-selected (held %d)", e->held);
    arena(e, 0);
    e->inv[ITEM_COPPER_PICK] = 0;
    e->tiles[F - 1][X] = TILE_DIRT; tw_relight(e);
    CHECK(!tw_mask(e, ACT_MINE_FIRST + tw_reach(e, X, F - 1)), "no pickaxe: dirt not minable");
    /* A crafted iron pickaxe becomes the mining tool: two hits of 40 in one
       15-tick action (useTime 13) instead of copper's one hit of 35. */
    arena(e, 0);
    env_object_write(e, TILE_ANVIL, X + 2, F - 1);
    e->tiles[F - 1][X] = TILE_STONE; tw_relight(e);
    e->inv[ITEM_IRON_BAR] = IRON_PICK_BARS; e->inv[ITEM_WOOD] = 3;
    env_step(e, ACT_CRAFT_IRON_PICK);
    CHECK(e->inv[ITEM_IRON_PICK] == 1 && pick_tier(e) == TIER_IRON_PICK, "iron pickaxe crafted and owned");
    env_step(e, ACT_MINE_FIRST + tw_reach(e, X, F - 1));
    CHECK(e->held == ITEM_IRON_PICK, "crafted iron pickaxe in hand for mining (held %d)", e->held);
#if FID_MINING
    int dmg = -1;
    for (int i = 0; i < HIT_SLOTS; i++) if (e->hits[i].ttl > 0 && e->hits[i].x == X && e->hits[i].y == F - 1) dmg = e->hits[i].damage;
    CHECK(dmg == 80 && e->tool_time > 0, "iron pickaxe: 2 hits of 40 in one action (damage %d)", dmg);
#endif
    /* 9,999 stacks; the observation saturates at OBS_INV_CLIP. */
    arena(e, 0);
    e->inv[ITEM_STONE] = 9990; env_give(e, ITEM_STONE, 50);
    env_obs(e, &o);
    CHECK(e->inv[ITEM_STONE] == 9999 && o.status[OBS_INV_0 + ITEM_STONE] == 1.0f, "stack cap 9999, observation saturates");
#if TOOL_DAMAGE && ENV_FX
    /* A pickaxe use swings (fx) and its useAnimation runs past the action. */
    arena(e, 0);
    e->tiles[F - 1][X] = TILE_STONE; tw_relight(e);
    env_step(e, ACT_MINE_FIRST + tw_reach(e, X, F - 1));
    CHECK(e->fx.swing && e->fx.swing_tool == TOOL_COPPER_PICK && e->item_anim == TOOL_INFO[TOOL_COPPER_PICK].use_anim - FID_TICKS
          && !tw_mask(e, ACT_ATTACK), "copper pickaxe swing (anim %d)", e->item_anim);
#endif
    free(e);
#else
    printf("explicit tools: EXPLICIT_TOOLS=0, fixtures skipped\n");
#endif
}

static void test_walls(void) {
#if BG_WALLS
    Env *e = new_env(1000000);
    const int X = 62, F = FLOOR;
    bool legal, ok;
    enum { SLOT_STONE = 0, SLOT_TORCH_ = 3 };
    /* Generated walls: none in the sky, dirt walls through the dirt band. */
    int sky = 0, band = 0, band_cells = 0, cave = 0, cabin = 0;
    for (int s = 0; s < 64; s++) {
        env_reset(e, 23000001 + s);
        for (int x = 0; x < WORLD_W; x++) for (int y = 0; y < WORLD_H; y++) {
            sky += y <= e->surface[x] && e->wall[y][x] != WALL_NONE;
            if (y >= e->surface[x] + 3 && y <= e->surface[x] + DIRT_DEPTH) { band_cells++; band += e->wall[y][x] == WALL_DIRT; }
            cave += e->wall[y][x] >= WALL_CAVE_59 && e->wall[y][x] <= WALL_CAVE_171;
            cabin += e->wall[y][x] == WALL_PLANKED;
        }
    }
    printf("walls over 64 worlds: %d sky, dirt band %d/%d, %.0f cave-wall and %.0f cabin-wall cells per world\n",
           sky, band, band_cells, cave / 64.0, cabin / 64.0);
    CHECK(sky == 0 && band == band_cells && cave > 0 && cabin > 0, "generated walls");
    /* Open sky: a block needs a neighbour; a wall behind it or beside it is
       enough; a floor neighbour still makes a bridge. */
    arena(e, 0);
    ok = tw_place(e, SLOT_STONE, X, F - 4, &legal);
    CHECK(REFUSED(legal, ok), "block in open sky: mask %d placed %d", legal, ok);
    ok = tw_place(e, SLOT_STONE, X, F - 1, &legal);
    CHECK(legal && ok, "block on the floor: mask %d placed %d", legal, ok);
    arena(e, 0);
    e->wall[F - 4][X] = WALL_DIRT;
    ok = tw_place(e, SLOT_STONE, X, F - 4, &legal);
    CHECK(legal && ok, "block against a wall: mask %d placed %d", legal, ok);
    arena(e, 0);
    e->wall[F - 4][X + 1] = WALL_DIRT;
    ok = tw_place(e, SLOT_STONE, X, F - 4, &legal);
    CHECK(legal && ok, "block beside a walled cell: mask %d placed %d", legal, ok);
    /* Underground, against the generated wall: a dug-out pocket in the dirt
       band of a real world, the target with no tile around it. */
    env_reset(e, 23000001);
    {
        int x = e->px + 2, y = e->surface[x] + 6;
        for (int yy = y - 4; yy <= y; yy++) for (int xx = x - 3; xx <= x + 1; xx++) { e->tiles[yy][xx] = TILE_AIR; e->object_part[yy][xx] = 0; }
        e->tiles[y + 1][x - 2] = e->tiles[y + 1][x - 1] = TILE_DIRT;
        memset(e->mobs, 0, sizeof e->mobs);
        e->px = x - 2; e->py = y; sync_body(e); tw_relight(e);
        for (int yy = 0; yy < WORLD_H; yy++) for (int xx = 0; xx < WORLD_W; xx++) e->light[yy][xx] = LIGHT_MAX;
        int tx = x, ty = y - 3;
        ok = tw_place(e, SLOT_STONE, tx, ty, &legal);
        CHECK(e->wall[ty][tx] == WALL_DIRT && legal && ok, "block against the dirt wall underground: mask %d placed %d", legal, ok);
    }
#if SUPPORT_RULES
    /* Torch on the wall alone. */
    arena(e, 0);
    ok = tw_place(e, SLOT_TORCH_, X, F - 4, &legal);
    CHECK(REFUSED(legal, ok), "torch in open sky: mask %d placed %d", legal, ok);
    e->wall[F - 4][X] = WALL_DIRT;
    ok = tw_place(e, SLOT_TORCH_, X, F - 4, &legal);
    CHECK(legal && ok, "torch on a wall: mask %d placed %d", legal, ok);
#endif
    /* Mining never removes a wall; the wall channel shows lit walls only. */
    arena(e, 0);
    e->tiles[F - 1][X] = TILE_STONE; e->wall[F - 1][X] = WALL_DIRT; tw_relight(e);
    int r = tw_reach(e, X, F - 1);
    for (int t = 0; t < 12 && tile_at(e, X, F - 1) != TILE_AIR; t++) env_step(e, ACT_MINE_FIRST + r);
    CHECK(tile_at(e, X, F - 1) == TILE_AIR && e->wall[F - 1][X] == WALL_DIRT, "wall survives mining");
    static Obs o;
    env_obs(e, &o);
    int k = (F - 1 - (e->py - VIEW_H / 2)) * VIEW_W + (X - (e->px - VIEW_W / 2));
    float *cell = &o.status[OBS_ENTITY_0 + k * OBS_ENTITY_CHANNELS];
    CHECK(cell[OBS_WALL_CHANNEL] == 1.0f && cell[OBS_WALL_CHANNEL - 1] == 0.0f, "wall channel on a lit wall");
    e->light[F - 1][X] = 0; env_obs(e, &o);
    CHECK(cell[OBS_WALL_CHANNEL] == 0.0f, "wall hidden in the dark");
    free(e);
#else
    printf("background walls: BG_WALLS=0, fixtures skipped\n");
#endif
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

/* HELD_PLACE (env.h): a standalone place holds the use button over the step.
   In the open-air arena (no walls), after a jump the cell under the feet
   floats, so the step-start place is refused; held, `place down` lands later
   in the step once the falling feet are one row above the floor or the
   pillar top. Masks: legal at the step start or on the step's no-input body
   path; with no mobs the mask predicts every place-down outcome, and
   computing it leaves the state untouched. */
static void test_held_place(void) {
#if HELD_PLACE
    Env *e = new_env(1000000);
    int dirt = 0;
    for (int i = 0; i < PLACEABLE_COUNT; i++) if (PLACEABLES[i].item == ITEM_DIRT) dirt = i;
    uint8_t m[ACT_COUNT];
    arena(e, 1);
    e->selected = (uint8_t)dirt; e->inv[ITEM_DIRT] = 50;
    env_action_mask(e, m);
    int legal = 0;
    for (int r = 0; r < REACH_COUNT; r++) legal += m[ACT_PLACE_FIRST + r];
    const int down_standing = m[ACT_PLACE_DOWN];
    e->inv[ITEM_DIRT] = 0; env_action_mask(e, m);
    int legal0 = 0;
    for (int r = 0; r < REACH_COUNT; r++) legal0 += m[ACT_PLACE_FIRST + r];
    CHECK(legal < REACH_COUNT && !down_standing && legal0 == 0,
          "held place masks standing: %d legal with dirt (place down %d), %d without", legal, down_standing, legal0);

    /* Standing still: place down into the floor never lands, no stock used. */
    e->inv[ITEM_DIRT] = 50;
    env_step(e, ACT_PLACE_DOWN);
    CHECK(e->inv[ITEM_DIRT] == 50 && e->py == FLOOR - 1, "held place into the floor: dirt %d", e->inv[ITEM_DIRT]);

    int dirt_tiles;
#if BG_WALLS   /* without walls rules a block may float, the step start places */
    /* Later tick: jump, then place down; the step-start cell under the feet
       has no neighbour (refused), the block lands lower in the same step or
       the next place step; each step places at most one block. */
    int later = 0, one_each = 1, placed_steps = 0, predicted = 1, untouched = 1;
    int py0 = e->py;
    Env *snap = malloc(sizeof *e);
    env_step(e, ACT_JUMP);
    for (int s = 0; s < 4 && e->inv[ITEM_DIRT] == 50; s++) {
        int start_py = e->py, before = e->inv[ITEM_DIRT];
        bool floating = start_py + 2 < FLOOR;
        memcpy(snap, e, sizeof *e);
        env_action_mask(e, m);
        untouched &= memcmp(snap, e, sizeof *e) == 0;
        env_step(e, ACT_PLACE_DOWN);
        one_each &= before - e->inv[ITEM_DIRT] <= 1;
        predicted &= m[ACT_PLACE_DOWN] == (e->inv[ITEM_DIRT] < before);
        placed_steps++;
        if (e->inv[ITEM_DIRT] < before) later = floating && tile_at(e, e->px, start_py + 1) == TILE_AIR;
    }
    free(snap);
    for (int s = 0; s < 8 && e->vel_y != 0; s++) env_step(e, ACT_NOOP);
    dirt_tiles = 0;
    for (int y = 0; y < FLOOR; y++) for (int x = 0; x < WORLD_W; x++) dirt_tiles += e->tiles[y][x] == TILE_DIRT;
    CHECK(later && one_each && predicted && untouched && e->inv[ITEM_DIRT] == 49 && dirt_tiles == 1
          && tile_at(e, e->px, FLOOR - 1) == TILE_DIRT && e->py == py0 - 1,
          "held place lands on a later tick: %d place steps, later %d, mask predicted %d, state untouched %d, dirt %d, tiles %d, py %d -> %d",
          placed_steps, later, predicted, untouched, e->inv[ITEM_DIRT], dirt_tiles, py0, e->py);

    /* Open-air pillar with standalone actions: jump, place down while the
       mask allows it (no timing), settle; 10 rows, one block per row. */
    int rows = 0, steps = 0, used = 0;
    for (int k = 0; k < 10; k++) {
        int start = e->py, inv = e->inv[ITEM_DIRT];
        env_step(e, ACT_JUMP); steps++;
        for (int s = 0; s < 8 && e->inv[ITEM_DIRT] == inv; s++) {
            env_action_mask(e, m); env_step(e, m[ACT_PLACE_DOWN] ? ACT_PLACE_DOWN : ACT_NOOP); steps++;
        }
        for (int s = 0; s < 8 && e->vel_y != 0; s++) { env_step(e, ACT_NOOP); steps++; }
        used += inv - e->inv[ITEM_DIRT];
        rows += e->py == start - 1;
    }
    printf("held place: open-air pillar %d/10 rows in %d steps (jump, place down when masked in, settle)\n", rows, steps);
    CHECK(rows == 10 && used == 10 && !e->terminated, "open-air pillar with jump + place down: %d/10 rows, %d dirt, %d steps",
          rows, used, steps);
#endif

    /* Step-start legal (a wall behind every cell): the block lands at the
       step start under the feet, exactly one, as the step-start place did. */
    arena(e, 1);
    e->selected = (uint8_t)dirt; e->inv[ITEM_DIRT] = 50;
#if BG_WALLS
    memset(e->wall, WALL_DIRT, sizeof e->wall);
#endif
    env_step(e, ACT_JUMP);
    int tx = e->px, ty = e->py + 1;
    env_step(e, ACT_PLACE_DOWN);
    dirt_tiles = 0;
    for (int y = 0; y < FLOOR; y++) for (int x = 0; x < WORLD_W; x++) dirt_tiles += e->tiles[y][x] == TILE_DIRT;
    CHECK(tile_at(e, tx, ty) == TILE_DIRT && dirt_tiles == 1 && e->inv[ITEM_DIRT] == 49,
          "held place legal at the step start places there once: tile %d, tiles %d", tile_at(e, tx, ty), dirt_tiles);
    free(e);
#endif
}

/* HELD_PLACE mask on real worlds under random play: computing it never
   changes the state, and it predicts whether each place action would place
   (tried on a copy). Misses come from mobs (contact knockback changes the
   path) and from the darkness rule (hidden cells permit attempts). */
static void test_held_place_mask_random(void) {
#if HELD_PLACE
    Env *e = new_env(2000), *c = malloc(sizeof *e), *snap = malloc(sizeof *e);
    uint64_t rng = 77;
    long untouched = 0, steps = 0, in_ok = 0, in_fail = 0, out_ok = 0, out_fail = 0;
    uint8_t m[ACT_COUNT];
    for (uint64_t seed = 1; seed <= 4; seed++) {
        env_reset(e, seed);
        while (!e->terminated && !e->truncated) {
            memcpy(snap, e, sizeof *e);
            env_action_mask(e, m);
            untouched += memcmp(snap, e, sizeof *e) == 0; steps++;
            const int item = PLACEABLES[e->selected].item;
            if (e->inv[item] > 0) for (int r = 0; r < REACH_COUNT; r++) {
                memcpy(c, e, sizeof *e);
                env_step(c, ACT_PLACE_FIRST + r);
                const bool ok = c->inv[item] < e->inv[item];
                if (m[ACT_PLACE_FIRST + r]) { if (ok) in_ok++; else in_fail++; }
                else { if (ok) out_ok++; else out_fail++; }
            }
            env_step(e, legal_action(e, &rng));
        }
    }
    printf("held place mask, random play (%ld steps): masked in %ld placed / %ld failed, masked out %ld placed / %ld failed\n",
           steps, in_ok, in_fail, out_ok, out_fail);
    CHECK(untouched == steps && out_ok * 100 <= in_ok, "held place mask leaves the state untouched (%ld/%ld) and misses few landings (%ld of %ld)",
          untouched, steps, out_ok, in_ok + out_ok);
    free(e); free(c); free(snap);
#endif
}

int main(int argc, char **argv) {
    int worlds = argc > 1 ? atoi(argv[1]) : 512;
    printf("v10 selftest (FID_MOBS=%d COMBAT=%d PHYSICS=%d MINING=%d TREES=%d, FID_TICKS=%d, TREE_LEAF_VISUAL=%d "
           "SUPPORT_RULES=%d EXPLICIT_TOOLS=%d TOOL_DAMAGE=%d BG_WALLS=%d): Env %zu bytes, obs status %d, actions %d, "
           "achievements %d\n", FID_MOBS, FID_COMBAT, FID_PHYSICS, FID_MINING, FID_TREES, FID_TICKS, TREE_LEAF_VISUAL,
           SUPPORT_RULES, EXPLICIT_TOOLS, TOOL_DAMAGE, BG_WALLS, sizeof(Env), OBS_STATUS, ACT_COUNT, ACH_COUNT);
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
    test_support();
    test_tree_leaves();
    test_fx();
    test_tools();
    test_walls();
    test_held_place();
    test_held_place_mask_random();
    printf("%s: %d/%d checks passed\n", failures ? "FAILED" : "PASSED", checks - failures, checks);
    return failures != 0;
}
