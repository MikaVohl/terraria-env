/* Full-map light propagation: sunlight, emitters and the player seeded into a
   bucket BFS that attenuates one level per tile. */
#include <string.h>

#include "env.h"

#define LIGHT_CELLS (WORLD_W * WORLD_H)

static inline void seed_cell(Env *e, int x, int y, uint8_t v) {
    if (e->light[y][x] < v) e->light[y][x] = v;
}

void light_recompute(Env *e) {
    /* Two frontier buffers plus the bucketed seed list. A cell enters a
       frontier at most once per level (it must strictly improve to get in),
       and a seed at level L can never also be an improvement to L, so the two
       sources are disjoint and LIGHT_CELLS is a sufficient bound for each. */
    uint16_t buf_a[LIGHT_CELLS];
    uint16_t buf_b[LIGHT_CELLS];
    uint16_t seeds[LIGHT_CELLS];
    int start[LIGHT_MAX + 1];
    int fill[LIGHT_MAX + 1];
    int count[LIGHT_MAX + 1] = {0};

    static const int DX[4] = {1, -1, 0, 0};
    static const int DY[4] = {0, 0, 1, -1};

    memset(e->light, 0, sizeof e->light);

    /* Sunlight: each column is lit from the sky down to its first opaque tile.
       The blocker itself is left dark here and picked up by propagation. */
    for (int x = 0; x < WORLD_W; x++) {
        for (int y = 0; y < WORLD_H; y++) {
            if (tile_opaque((Tile)e->tiles[y][x])) break;
            e->light[y][x] = LIGHT_MAX;
        }
    }

    /* Emitters, then the player's own glow; brightest candidate wins. */
    for (int y = 0; y < WORLD_H; y++) {
        for (int x = 0; x < WORLD_W; x++) {
            uint8_t emit = tile_emit((Tile)e->tiles[y][x]);
            if (emit) seed_cell(e, x, y, emit);
        }
    }
    /* Both body cells glow: a head-height source is what actually reveals the
       tunnel you are walking into. */
    for (int i = 0; i < PLAYER_H; i++)
        if (in_bounds(e->px, e->py - i)) seed_cell(e, e->px, e->py - i, PLAYER_LIGHT);

    /* Counting-sort every seeded cell into a contiguous per-level bucket,
       brightest bucket first. Level 0 is not a seed. */
    for (int y = 0; y < WORLD_H; y++)
        for (int x = 0; x < WORLD_W; x++)
            count[e->light[y][x]]++;

    for (int lvl = LIGHT_MAX, off = 0; lvl >= 1; lvl--) {
        start[lvl] = off;
        fill[lvl] = off;
        off += count[lvl];
    }
    for (int y = 0; y < WORLD_H; y++) {
        for (int x = 0; x < WORLD_W; x++) {
            uint8_t v = e->light[y][x];
            if (v) seeds[fill[v]++] = (uint16_t)(y * WORLD_W + x);
        }
    }

    /* Drain one level at a time, brightest first. Nothing is ever queued above
       the level being drained, so every cell is finalised at its true maximum
       the first time it is written. */
    uint16_t *cur = buf_a, *nxt = buf_b;
    int n_cur = 0;

    for (int lvl = LIGHT_MAX; lvl >= 1; lvl--) {
        for (int i = start[lvl]; i < fill[lvl]; i++) {
            unsigned c = seeds[i];
            int x = (int)(c % WORLD_W), y = (int)(c / WORLD_W);
            /* A brighter wave may have overwritten this seed already. */
            if (e->light[y][x] == lvl && !tile_opaque((Tile)e->tiles[y][x]))
                cur[n_cur++] = (uint16_t)c;
        }

        uint8_t child = (uint8_t)(lvl - 1);
        int n_nxt = 0;

        for (int i = 0; i < n_cur; i++) {
            unsigned c = cur[i];
            int x = (int)(c % WORLD_W), y = (int)(c / WORLD_W);
            for (int d = 0; d < 4; d++) {
                int nx = x + DX[d], ny = y + DY[d];
                if (!in_bounds(nx, ny)) continue;
                if (e->light[ny][nx] >= child) continue;
                e->light[ny][nx] = child;
                /* Opaque tiles light up so walls are visible, but they are a
                   dead end: light never travels through solid matter. */
                if (!tile_opaque((Tile)e->tiles[ny][nx]))
                    nxt[n_nxt++] = (uint16_t)(ny * WORLD_W + nx);
            }
        }

        uint16_t *swap = cur;
        cur = nxt;
        nxt = swap;
        n_cur = n_nxt;
    }
}
