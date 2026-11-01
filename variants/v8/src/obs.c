/* The agent's view of the world: an egocentric window plus a status vector.
 *
 * Two rules are load-bearing here and are worth stating once.
 *
 * Darkness is real. A cell lit below DARK_THRESHOLD is reported as
 * OBS_UNKNOWN, not as its tile. Without that the lighting system would be a
 * renderer effect and torches would not help the policy navigate underground.
 *
 * Achievements are in the observation because the reward depends on them.
 * award() fires once per achievement, so two states with identical worlds but
 * different unlock masks pay differently for the same action. Hide the mask
 * and even otherwise identical local observations have unnecessarily hidden
 * reward history. The local view is still partially observable.
 */
#include <string.h>
#include <math.h>

#include "env.h"

static float clamp01(float v)
{
    return v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
}

void env_obs(const Env *e, Obs *o)
{
    int row, col, i;

    /* Window centred on the left feet cell, so the head is two rows up and every reach
       target lands well inside the frame. */
    const int x0 = e->px - VIEW_W / 2;
    const int y0 = e->py - VIEW_H / 2;

    for (row = 0; row < VIEW_H; row++) {
        for (col = 0; col < VIEW_W; col++) {
            const int x = x0 + col, y = y0 + row;
            const int k = row * VIEW_W + col;

            if (!in_bounds(x, y)) {
                /* The world edge is a wall you can see, never an unlit cave. */
                o->tile[k]  = TILE_BEDROCK;
                o->light[k] = LIGHT_MAX;
                continue;
            }
            o->light[k] = e->light[y][x];
            o->tile[k]  = e->light[y][x] < DARK_THRESHOLD
                        ? (uint8_t)OBS_UNKNOWN
                        : e->tiles[y][x];
        }
    }

    memset(o->status, 0, sizeof o->status);

    o->status[OBS_HEALTH] = clamp01((float)e->health / (float)e->max_health);
    o->status[OBS_TIER]   = clamp01((float)e->tool_tier / (float)TIER_GOLD_PICK);
    o->status[OBS_MAX_HEALTH]=(float)e->max_health/HEALTH_CAP;
    o->status[OBS_WEAPON]=(float)e->weapon/(WEAPON_COUNT-1);
    o->status[OBS_ARMOR]=(float)e->armor/2;
    o->status[OBS_ATTACK_CD]=(float)e->attack_cd/3;
    o->status[OBS_HEAL_CD]=(float)e->heal_cd/60;
    o->status[OBS_HURT_CD]=(float)e->hurt_cd/8;
    o->status[OBS_MINE_CD]=(float)e->mine_cd/3;
    o->status[OBS_AIR_JUMP]=e->air_jump_used?1:0;
    o->status[OBS_SAFE_TIME]=clamp01((float)e->safe_ticks/40);
    o->status[OBS_FACING] = e->facing > 0 ? 1.0f : 0.0f;
    o->status[OBS_JUMP]   = clamp01((float)e->jump_left / (float)JUMP_HEIGHT);

    /* Fall distance saturates past twice the safe threshold: beyond that the
       only remaining question is how dead you are. */
    o->status[OBS_FALL]   = clamp01((float)e->fall_dist / (float)(2 * FALL_SAFE));
    o->status[OBS_DEPTH]  = clamp01((float)e->py / (float)(WORLD_H - 1));
    o->status[OBS_ACROSS] = clamp01((float)e->px / (float)(WORLD_W - 1));

    /* Finite horizon, so time spent is part of the state. */
    o->status[OBS_TIME]   = e->max_steps > 0
                          ? clamp01((float)e->steps / (float)e->max_steps)
                          : 0.0f;

    if (e->selected < PLACEABLE_COUNT)
        o->status[OBS_SEL_0 + e->selected] = 1.0f;

    for (i = 0; i < ITEM_COUNT; i++)
        o->status[OBS_INV_0 + i] = sqrtf((float)e->inv[i]/OBS_INV_CLIP);

    for (i = 0; i < ACH_COUNT; i++)
        o->status[OBS_ACH_0 + i] = has_ach(e, i) ? 1.0f : 0.0f;
    for(i=0;i<MAX_MOBS;i++) {
        const Mob *m=&e->mobs[i];
        int x=m->x-x0,y=m->y-y0;
        if(!m->kind || x<0 || x>=VIEW_W || y<0 || y>=VIEW_H) continue;
        int k=y*VIEW_W+x;
        if(o->light[k]<DARK_THRESHOLD) continue;
        float *s=&o->status[OBS_ENTITY_0+k*4];
        s[m->kind-1]=1;
        float hp=(float)m->hp/(m->kind==MOB_BLUE_SLIME?25:16);
        if(hp>s[2]) s[2]=hp;
        s[3]=(float)m->phase/7;
    }
}
