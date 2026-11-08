/* v10 transfer PoC: encode a real-Terraria snapshot as the v10 policy input.
 *
 * Builds a synthetic v10 Env whose tiles/light around the player are the real
 * game's (already mapped to the 24 sim kinds by the driver), then calls the
 * simulator's own env_obs / env_action_mask, so the observation layout and the
 * mask semantics are exactly the trained policy's. Compiled together with the
 * v10 core sources and src/capi.c (see tools/v10_transfer/README in the report).
 */
#include <stdlib.h>
#include <string.h>
#include "env.h"

#define BR_API __attribute__((visibility("default")))

/* Scalar slots of br_set's `s` array. */
enum { S_PX, S_PY, S_STEPS, S_MAX_STEPS, S_HEALTH, S_MAX_HEALTH, S_TIER, S_WEAPON, S_ARMOR,
       S_ITEM_ANIM, S_ITEM_ANIM_MAX, S_IMMUNE, S_HEAL_CD, S_FACING, S_JUMP, S_AIR_JUMP_USED,
       S_FALL_DIST, S_POS_X, S_POS_Y, S_VEL_X, S_VEL_Y, S_SELECTED, S_SURFACE,
       S_WIN_X0, S_WIN_Y0, S_WIN_W, S_WIN_H, S_ACH_LO, S_ACH_HI,
       S_BOSS_ACTIVE, S_BOSS_X, S_BOSS_Y, S_BOSS_HP, S_BOSS_MODE,
       S_TOOL_TIME, S_DIG_X, S_DIG_Y, S_DIG_DAMAGE, S_SAFE_TICKS, S_COUNT };

BR_API int br_scalar_count(void) { return S_COUNT; }
BR_API int br_flat_size(void) { return VIEW_CELLS * OBS_TILE_KINDS + VIEW_CELLS + OBS_STATUS; }
BR_API int br_action_count(void) { return ACT_COUNT; }
BR_API int br_mob_hp(int kind) { return mob_max_hp(kind); }

BR_API void *br_new(void)
{
    Env *e = calloc(1, sizeof *e);
    env_init(e, (EnvConfig){ EPISODE_STEPS });
    env_reset(e, 1);
    return e;
}

BR_API void br_free(void *p) { free(p); }

/* tiles/light: win_w*win_h row-major sim tile ids / light levels, placed with
   their top-left at (win_x0, win_y0) in sim coordinates. mobs: n rows of
   (kind, x, y, hp_permille). inv: ITEM_COUNT counts. */
BR_API void br_set(void *p, const int *s, const uint8_t *tiles, const uint8_t *light,
                   const int *inv, const int *mobs, int n_mobs)
{
    Env *e = p;
    memset(e->tiles, TILE_AIR, sizeof e->tiles);
    memset(e->light, 0, sizeof e->light);
    memset(e->terrain_light, 0, sizeof e->terrain_light);
    memset(e->object_part, 0, sizeof e->object_part);
    e->chest_count = 0;
    for (int r = 0; r < s[S_WIN_H]; r++)
        for (int c = 0; c < s[S_WIN_W]; c++) {
            int x = s[S_WIN_X0] + c, y = s[S_WIN_Y0] + r;
            if (!in_bounds(x, y)) continue;
            e->tiles[y][x] = tiles[r * s[S_WIN_W] + c];
            e->light[y][x] = light[r * s[S_WIN_W] + c];
        }
    /* Chests: one entry per 2x2 block of TILE_CHEST (anchor = bottom-left). */
    for (int y = 1; y < WORLD_H; y++)
        for (int x = 0; x + 1 < WORLD_W; x++)
            if (e->tiles[y][x] == TILE_CHEST && (x == 0 || e->tiles[y][x - 1] != TILE_CHEST)
                && (y + 1 >= WORLD_H || e->tiles[y + 1][x] != TILE_CHEST) && e->chest_count < MAX_CHESTS) {
                Chest *ch = &e->chests[e->chest_count++];
                memset(ch, 0, sizeof *ch);
                ch->x = x; ch->y = y;
            }
    for (int x = 0; x < WORLD_W; x++) e->surface[x] = s[S_SURFACE];
    e->px = s[S_PX]; e->py = s[S_PY];
    e->steps = s[S_STEPS]; e->max_steps = s[S_MAX_STEPS];
    e->health = s[S_HEALTH]; e->max_health = s[S_MAX_HEALTH];
    e->tool_tier = (uint8_t)s[S_TIER]; e->weapon = s[S_WEAPON]; e->armor = s[S_ARMOR];
    e->item_anim = s[S_ITEM_ANIM]; e->item_anim_max = s[S_ITEM_ANIM_MAX];
    e->immune_ticks = s[S_IMMUNE]; e->heal_cd = s[S_HEAL_CD];
    e->facing = s[S_FACING]; e->jump = s[S_JUMP]; e->air_jump_used = s[S_AIR_JUMP_USED] != 0;
    e->fall_dist = s[S_FALL_DIST];
    e->pos_x = s[S_POS_X]; e->pos_y = s[S_POS_Y]; e->vel_x = s[S_VEL_X]; e->vel_y = s[S_VEL_Y];
    e->pulley = false;
    e->selected = (uint8_t)s[S_SELECTED];
    e->achievements = (uint64_t)(uint32_t)s[S_ACH_LO] | ((uint64_t)(uint32_t)s[S_ACH_HI] << 32);
    e->terminated = e->truncated = false;
    e->tool_time = s[S_TOOL_TIME]; e->dig_x = s[S_DIG_X]; e->dig_y = s[S_DIG_Y]; e->safe_ticks = s[S_SAFE_TICKS];
    memset(e->hits, 0, sizeof e->hits);
    if (s[S_DIG_DAMAGE] > 0)
        e->hits[0] = (HitSlot){ (int16_t)s[S_DIG_X], (int16_t)s[S_DIG_Y], (int16_t)s[S_DIG_DAMAGE], 1 };
    for (int i = 0; i < ITEM_COUNT; i++) e->inv[i] = (int16_t)(inv[i] > 32000 ? 32000 : inv[i]);
    memset(e->mobs, 0, sizeof e->mobs);
    for (int i = 0; i < n_mobs && i < MAX_MOBS; i++) {
        const int *m = mobs + 4 * i;
        int hp = mob_max_hp(m[0]) * m[3] / 1000;
        mob_place(&e->mobs[i], m[0], hp < 1 ? 1 : hp, m[1], m[2]);
        e->mobs[i].x = m[1]; e->mobs[i].y = m[2];
    }
    memset(&e->boss, 0, sizeof e->boss);
    if (s[S_BOSS_ACTIVE]) {
        e->boss.active = true; e->boss.x = s[S_BOSS_X]; e->boss.y = s[S_BOSS_Y];
        e->boss.hp = EOC_HP * s[S_BOSS_HP] / 1000; e->boss.mode = (uint8_t)s[S_BOSS_MODE];
    }
}

BR_API void br_obs(void *p, float *out)
{
    Obs o;
    env_obs(p, &o);
    const int terrain = VIEW_CELLS * OBS_TILE_KINDS;
    memset(out, 0, (size_t)terrain * sizeof(float));
    for (int k = 0; k < VIEW_CELLS; k++) {
        out[k * OBS_TILE_KINDS + o.tile[k]] = 1.f;
        out[terrain + k] = (float)((double)o.light[k] / 15.);
    }
    memcpy(out + terrain + VIEW_CELLS, o.status, sizeof o.status);
}

BR_API void br_mask(void *p, uint8_t *mask) { env_action_mask(p, mask); }
