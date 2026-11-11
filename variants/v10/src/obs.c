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
    o->status[OBS_TIER]   = clamp01((float)pick_tier(e) / (float)TIER_GOLD_PICK);
    o->status[OBS_MAX_HEALTH]=(float)e->max_health/HEALTH_CAP;
    o->status[OBS_WEAPON]=(float)e->weapon/(WEAPON_COUNT-1);
    o->status[OBS_ARMOR]=(float)e->armor/(ARMOR_LEVELS-1);
#if FID_COMBAT
    /* Swing progress (itemAnimation) and i-frames (immuneTime, 40 ticks). */
    o->status[OBS_ATTACK_CD]=e->item_anim_max?(float)e->item_anim/(float)e->item_anim_max:0.0f;
    o->status[OBS_HURT_CD]=clamp01((float)e->immune_ticks/40.0f);
#else
    o->status[OBS_ATTACK_CD]=(float)e->attack_cd/3;
    o->status[OBS_HURT_CD]=(float)e->hurt_cd/8;
#endif
    o->status[OBS_HEAL_CD]=(float)e->heal_cd/60;
#if FID_MINING
    /* Tool time left, as a fraction of the slowest tool (axe, 21 ticks). */
    o->status[OBS_MINE_CD]=clamp01((float)e->tool_time/21.0f);
#else
    o->status[OBS_MINE_CD]=(float)e->mine_cd/3;
#endif
    o->status[OBS_AIR_JUMP]=e->air_jump_used?1:0;
    o->status[OBS_SAFE_TIME]=clamp01((float)e->safe_ticks/40);
    o->status[OBS_FACING] = e->facing > 0 ? 1.0f : 0.0f;
#if FID_PHYSICS
    /* Held-jump ticks left (Player.jump, 15 max). */
    o->status[OBS_JUMP]   = clamp01((float)e->jump / 15.0f);
    /* Hitbox centre within the body's two columns, feet within the feet row,
       and velocity (run speed 3, fall speed 10 px/tick). */
    o->status[OBS_SUB_X] = (float)(e->pos_x + (PLAYER_PX_W/2)*FIX_ONE - e->px*TILE_FIX) / (float)(2*TILE_FIX);
    o->status[OBS_SUB_Y] = (float)(e->pos_y + PLAYER_PX_H*FIX_ONE - e->py*TILE_FIX) / (float)TILE_FIX;
    o->status[OBS_VEL_X] = (float)e->vel_x / (float)(3*FIX_ONE);
    o->status[OBS_VEL_Y] = (float)e->vel_y / (float)(10*FIX_ONE);
#else
    o->status[OBS_JUMP]   = clamp01((float)e->jump_left / (float)JUMP_HEIGHT);
#endif
#if FID_MINING
    /* Accumulated pick/axe damage on the last tile hit (0-100). */
    for (i = 0; i < HIT_SLOTS; i++)
        if (e->hits[i].ttl > 0 && e->hits[i].x == e->dig_x && e->hits[i].y == e->dig_y)
            o->status[OBS_DIG] = (float)e->hits[i].damage / 100.0f;
#endif

    /* Fall distance saturates past twice the safe threshold: beyond that the
       only remaining question is how dead you are. */
    o->status[OBS_FALL]   = clamp01((float)e->fall_dist / (float)(2 * FALL_SAFE));
    o->status[OBS_DEPTH]  = clamp01((float)e->py / (float)(WORLD_H - 1));
    o->status[OBS_ACROSS] = clamp01((float)e->px / (float)(WORLD_W - 1));

    /* Finite horizon, so time spent is part of the state. */
    o->status[OBS_TIME]   = e->max_steps > 0
                          ? clamp01((float)e->steps / (float)e->max_steps)
                          : 0.0f;

    /* v9: time of day, layer, boss. */
    o->status[OBS_DAY_PHASE] = (float)day_time(e) / (float)DAY_CYCLE;
    o->status[OBS_NIGHT] = is_night(e) ? 1.0f : 0.0f;
    o->status[OBS_LAYER_0 + player_layer(e)] = 1.0f;
    const Boss *b = &e->boss;
    if (b->active) {
        o->status[OBS_BOSS + 0] = 1.0f;
        o->status[OBS_BOSS + 1] = clamp01((float)b->hp / (float)EOC_HP);
        o->status[OBS_BOSS + 2] = 2 * b->hp <= EOC_HP ? 1.0f : 0.0f;
        float dx = (float)(b->x + EOC_SIZE / 2 - e->px) / 32.0f;
        float dy = (float)(b->y + EOC_SIZE / 2 - (e->py - 1)) / 32.0f;
        o->status[OBS_BOSS + 3] = dx < -1.0f ? -1.0f : dx > 1.0f ? 1.0f : dx;
        o->status[OBS_BOSS + 4] = dy < -1.0f ? -1.0f : dy > 1.0f ? 1.0f : dy;
    }

    if (e->selected < PLACEABLE_COUNT)
        o->status[OBS_SEL_0 + e->selected] = 1.0f;

    /* Counts saturate at OBS_INV_CLIP (EXPLICIT_TOOLS stacks reach 9,999). */
    for (i = 0; i < ITEM_COUNT; i++) {
        int n = e->inv[i] < OBS_INV_CLIP ? e->inv[i] : OBS_INV_CLIP;
        o->status[OBS_INV_0 + i] = sqrtf((float)n/OBS_INV_CLIP);
    }

    for (i = 0; i < ACH_COUNT; i++)
        o->status[OBS_ACH_0 + i] = has_ach(e, i) ? 1.0f : 0.0f;
#if INV_LOG
    for (i = 0; i < ITEM_COUNT; i++) {
        int n = e->inv[i] < OBS_INV_CLIP ? e->inv[i] : OBS_INV_CLIP;
        o->status[OBS_INVLOG_0 + i] = logf(1.0f + (float)n) / logf(1.0f + (float)OBS_INV_CLIP);
    }
#endif
#if EXPLICIT_TOOLS
    o->status[OBS_HELD_0 + e->held] = 1.0f;
#endif
#if MINIMAP
    for (i = 0; i < MAP_CELLS; i++) {
        float *s = &o->status[OBS_MAP_0 + i * MAP_FEATURES];
        if (!e->map_seen[i]) continue;
        s[0] = 1.0f;
        s[1] = (float)e->map_solid[i] / (float)(MINIMAP_CELL * MINIMAP_CELL);
        s[2] = e->map_station[i] ? 1.0f : 0.0f;
    }
#endif
    /* Per cell: kind one-hot (MOB_KINDS-1 regular kinds, then the boss),
       health fraction, movement phase. Regular mobs hide in darkness; the
       3x3 boss is always drawn (its position is in the status block too).
       BG_WALLS: the wall channel of every lit in-world cell. */
    _Static_assert(OBS_MOB_CHANNELS==MOB_KINDS+2,"entity channel layout");
#if BG_WALLS
    for (row = 0; row < VIEW_H; row++)
        for (col = 0; col < VIEW_W; col++) {
            const int x = x0 + col, y = y0 + row, k = row * VIEW_W + col;
            if (in_bounds(x, y) && o->tile[k] != OBS_UNKNOWN && e->wall[y][x] != WALL_NONE)
                o->status[OBS_ENTITY_0 + k * OBS_ENTITY_CHANNELS + OBS_WALL_CHANNEL] = 1.0f;
        }
#endif
    for(i=0;i<MAX_MOBS;i++) {
        const Mob *m=&e->mobs[i];
        int x=m->x-x0,y=m->y-y0;
        if(!m->kind || x<0 || x>=VIEW_W || y<0 || y>=VIEW_H) continue;
        int k=y*VIEW_W+x;
        if(o->light[k]<DARK_THRESHOLD) continue;
        float *s=&o->status[OBS_ENTITY_0+k*OBS_ENTITY_CHANNELS];
        s[m->kind-1]=1;
        float hp=(float)m->hp/(float)mob_max_hp(m->kind);
        if(hp>s[MOB_KINDS]) s[MOB_KINDS]=hp;
        s[MOB_KINDS+1]=(float)m->phase/7;
    }
    if (b->active) {
        for (int by = 0; by < EOC_SIZE; by++) for (int bx = 0; bx < EOC_SIZE; bx++) {
            int x = b->x + bx - x0, y = b->y + by - y0;
            if (x < 0 || x >= VIEW_W || y < 0 || y >= VIEW_H) continue;
            float *s = &o->status[OBS_ENTITY_0 + (y * VIEW_W + x) * OBS_ENTITY_CHANNELS];
            s[MOB_KINDS - 1] = 1;
            float hp = (float)b->hp / (float)EOC_HP;
            if (hp > s[MOB_KINDS]) s[MOB_KINDS] = hp;
            s[MOB_KINDS + 1] = (float)b->mode / 2;
        }
    }
}
