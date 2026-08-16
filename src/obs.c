/* The agent's view of the world: an egocentric window plus a status vector.
 *
 * Two rules are load-bearing here and are worth stating once.
 *
 * Darkness is real. A cell lit below DARK_THRESHOLD is reported as
 * OBS_UNKNOWN, not as its tile. Without that the lighting system would be a
 * renderer effect, torches would be decorative, and the depth gate the whole
 * tech tree leans on would not exist for a policy.
 *
 * Achievements are in the observation because the reward depends on them.
 * award() fires once per achievement, so two states with identical worlds but
 * different unlock masks pay differently for the same action. Hide the mask
 * and the MDP stops being Markov for no reason.
 */
#include <string.h>

#include "env.h"

static float clamp01(float v)
{
    return v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
}

void env_obs(const Env *e, Obs *o)
{
    int row, col, i;

    /* Window centred on the feet, so the head is one row up and every reach
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

    o->status[OBS_HEALTH] = clamp01((float)e->health / (float)MAX_HEALTH);
    o->status[OBS_TIER]   = clamp01((float)e->tool_tier / (float)TIER_IRON_PICK);
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
        o->status[OBS_INV_0 + i] = clamp01((float)e->inv[i] / (float)OBS_INV_CLIP);

    for (i = 0; i < ACH_COUNT; i++)
        o->status[OBS_ACH_0 + i] = has_ach(e, i) ? 1.0f : 0.0f;
}
