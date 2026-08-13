/* Deterministic world generation: heightmap, layers, caves, ores, trees, spawn. */
#include <math.h>
#include <stdbool.h>
#include <stdlib.h>

#include "env.h"
#include "rng.h"
#include "tiles.h"

#define TAU 6.28318530717958647692f

/* First stone row in column x (rows [surface+1, surface+DIRT_DEPTH] are dirt). */
static int stone_top(const Env *e, int x) {
    return e->surface[x] + DIRT_DEPTH + 1;
}

/* First bedrock row; nothing below this may ever be rewritten. */
static int bedrock_top(void) {
    return WORLD_H - BEDROCK_ROWS;
}

static int clampi(int v, int lo, int hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

static int roundi(float v) {
    return (int)(v + (v >= 0.0f ? 0.5f : -0.5f));
}

/* ---- 1. Heightmap ------------------------------------------------------- */

static void gen_heightmap(Env *e) {
    const float ph0 = rng_float(&e->rng) * TAU;
    const float ph1 = rng_float(&e->rng) * TAU;
    const float ph2 = rng_float(&e->rng) * TAU;

    float raw[WORLD_W];
    for (int x = 0; x < WORLD_W; ++x) {
        float fx = (float)x;
        raw[x] = (float)SURFACE_BASE
               + 4.0f * sinf(fx * (TAU / 64.0f) + ph0)
               + 2.0f * sinf(fx * (TAU / 23.0f) + ph1)
               + 1.0f * sinf(fx * (TAU / 11.0f) + ph2)
               + (float)rng_range(&e->rng, -1, 1);
    }

    /* 1-2-1 blur: keeps the rolling shape but kills the per-column jitter that
       would otherwise make almost every tile a step. */
    for (int x = 0; x < WORLD_W; ++x) {
        float a = raw[x > 0 ? x - 1 : 0];
        float c = raw[x < WORLD_W - 1 ? x + 1 : WORLD_W - 1];
        e->surface[x] = clampi(roundi((a + 2.0f * raw[x] + c) * 0.25f),
                               SURFACE_MIN, SURFACE_MAX);
    }

    /* Clamp adjacent-column steps to <= 2 so the surface stays walkable. The
       two sweeps interact, so iterate to a fixed point (converges in 2-3). */
    for (int pass = 0; pass < 8; ++pass) {
        bool changed = false;
        for (int x = 1; x < WORLD_W; ++x) {
            int v = clampi(e->surface[x], e->surface[x - 1] - 2, e->surface[x - 1] + 2);
            if (v != e->surface[x]) { e->surface[x] = v; changed = true; }
        }
        for (int x = WORLD_W - 2; x >= 0; --x) {
            int v = clampi(e->surface[x], e->surface[x + 1] - 2, e->surface[x + 1] + 2);
            if (v != e->surface[x]) { e->surface[x] = v; changed = true; }
        }
        if (!changed) break;
    }

    for (int x = 0; x < WORLD_W; ++x)
        e->surface[x] = clampi(e->surface[x], SURFACE_MIN, SURFACE_MAX);
}

/* ---- 2. Layers ---------------------------------------------------------- */

static void gen_layers(Env *e) {
    const int brtop = bedrock_top();

    for (int x = 0; x < WORLD_W; ++x) {
        int s = e->surface[x];
        for (int y = 0; y < s; ++y)
            e->tiles[y][x] = TILE_AIR;
        e->tiles[s][x] = TILE_GRASS;
        int dirt_end = s + DIRT_DEPTH;
        for (int y = s + 1; y <= dirt_end && y < WORLD_H; ++y)
            e->tiles[y][x] = TILE_DIRT;
        for (int y = dirt_end + 1; y < WORLD_H; ++y)
            e->tiles[y][x] = TILE_STONE;
    }

    for (int y = brtop; y < WORLD_H; ++y)
        for (int x = 0; x < WORLD_W; ++x)
            e->tiles[y][x] = TILE_BEDROCK;
}

/* ---- 3. Caves ----------------------------------------------------------- */

static void carve_disc(Env *e, int cx, int cy, int r) {
    const int brtop = bedrock_top();
    const int r2 = r * r + (r > 1 ? 1 : 0);

    for (int dy = -r; dy <= r; ++dy) {
        for (int dx = -r; dx <= r; ++dx) {
            if (dx * dx + dy * dy > r2) continue;
            int x = cx + dx, y = cy + dy;
            if (!in_bounds(x, y)) continue;
            if (y >= brtop) continue;                 /* never touch bedrock */
            if (y < stone_top(e, x)) continue;        /* never carve dirt/grass/sky */
            if (e->tiles[y][x] == TILE_BEDROCK) continue;
            e->tiles[y][x] = TILE_AIR;
        }
    }
}

static void gen_caves(Env *e) {
    const int ymax = bedrock_top() - 2;
    const int worms = rng_range(&e->rng, 14, 22);

    for (int w = 0; w < worms; ++w) {
        int sx = rng_range(&e->rng, 2, WORLD_W - 3);
        int ymin = stone_top(e, sx) + 3;
        if (ymin > ymax) continue;

        float fx = (float)sx;
        float fy = (float)rng_range(&e->rng, ymin, ymax);
        float ang = rng_float(&e->rng) * TAU;
        int steps = rng_range(&e->rng, 40, 140);
        int r = rng_range(&e->rng, 1, 2);

        for (int i = 0; i < steps; ++i) {
            /* Small per-step turn: the direction drifts, so the worm meanders
               in long arcs instead of jittering around its start. */
            ang += (rng_float(&e->rng) - 0.5f) * 0.45f;
            fx += cosf(ang);
            fy += sinf(ang) * 0.55f;   /* flattened: tunnels run mostly sideways */

            int cx = roundi(fx), cy = roundi(fy);
            if (cx < 1 || cx >= WORLD_W - 1) break;
            if (cy < 1 || cy >= WORLD_H - 1) break;
            carve_disc(e, cx, cy, r);
        }
    }
}

/* ---- 4. Ore veins ------------------------------------------------------- */

#define VEIN_MAX 9

/* [ylo, yhi] confines vein growth to an ore's own band. Copper and iron pass
   the whole world and so keep their historical wander a few rows past their
   seed band; only gold is band-locked, and widening the others would move
   every existing seed's ore layout. */
static bool ore_cell_ok(const Env *e, int x, int y, int ylo, int yhi) {
    if (!in_bounds(x, y)) return false;
    if (y < ylo || y > yhi) return false;
    if (y >= bedrock_top()) return false;
    if (y < stone_top(e, x)) return false;
    return e->tiles[y][x] == TILE_STONE;
}

static void grow_vein(Env *e, int sx, int sy, Tile ore, int ylo, int yhi) {
    if (!ore_cell_ok(e, sx, sy, ylo, yhi)) return;

    int cx[VEIN_MAX], cy[VEIN_MAX];
    int n = 0;
    e->tiles[sy][sx] = (uint8_t)ore;
    cx[n] = sx; cy[n] = sy; ++n;

    int target = rng_range(&e->rng, 3, VEIN_MAX);
    static const int DX[4] = { 1, -1, 0, 0 };
    static const int DY[4] = { 0, 0, 1, -1 };

    for (int tries = 0; n < target && tries < 40; ++tries) {
        int i = (int)rng_below(&e->rng, (uint32_t)n);
        int d = (int)rng_below(&e->rng, 4);
        int nx = cx[i] + DX[d], ny = cy[i] + DY[d];
        if (!ore_cell_ok(e, nx, ny, ylo, yhi)) continue;
        e->tiles[ny][nx] = (uint8_t)ore;
        cx[n] = nx; cy[n] = ny; ++n;
    }
}

/* Draw a seed row in [lo, hi], accept/reject weighted linearly by depth.
   shallow_bias != 0 favours the top of the band, otherwise the bottom. */
static int weighted_row(Env *e, int lo, int hi, bool shallow_bias) {
    int y = lo;
    for (int tries = 0; tries < 8; ++tries) {
        y = rng_range(&e->rng, lo, hi);
        float t = (hi > lo) ? (float)(y - lo) / (float)(hi - lo) : 0.0f;
        float p = shallow_bias ? (1.0f - 0.85f * t) : (0.15f + 0.85f * t);
        if (rng_chance(&e->rng, p)) break;
    }
    return y;
}

static void gen_ores(Env *e) {
    const int top = bedrock_top() - 1;

    int copper = rng_range(&e->rng, 50, 60);
    for (int i = 0; i < copper; ++i) {
        int x = (int)rng_below(&e->rng, WORLD_W);
        int y = weighted_row(e, COPPER_MIN_Y, clampi(COPPER_MAX_Y, 0, top), true);
        grow_vein(e, x, y, TILE_COPPER_ORE, 0, WORLD_H - 1);
    }

    int iron = rng_range(&e->rng, 30, 40);
    for (int i = 0; i < iron; ++i) {
        int x = (int)rng_below(&e->rng, WORLD_W);
        int y = weighted_row(e, IRON_MIN_Y, clampi(IRON_MAX_Y, 0, top), false);
        grow_vein(e, x, y, TILE_IRON_ORE, 0, WORLD_H - 1);
    }

    /* Gold last, so its veins overwrite iron where the bands overlap: the
       deepest rows should read as gold-bearing. Scarce by design — it is the
       tier the iron pickaxe unlocks, so it must stay worth the descent, and it
       is pinned inside its band so no gold is reachable before that gate. */
    int gold = rng_range(&e->rng, 12, 20);
    for (int i = 0; i < gold; ++i) {
        int x = (int)rng_below(&e->rng, WORLD_W);
        int y = weighted_row(e, GOLD_MIN_Y, clampi(GOLD_MAX_Y, 0, top), false);
        grow_vein(e, x, y, TILE_GOLD_ORE, GOLD_MIN_Y, clampi(GOLD_MAX_Y, 0, top));
    }
}

/* ---- 5. Trees ----------------------------------------------------------- */

static void put_air_only(Env *e, int x, int y, Tile t) {
    if (!in_bounds(x, y)) return;
    if (e->tiles[y][x] != TILE_AIR) return;
    e->tiles[y][x] = (uint8_t)t;
}

static bool try_tree(Env *e, int x) {
    if (x < 2 || x >= WORLD_W - 2) return false;

    int s = e->surface[x];
    if (e->tiles[s][x] != TILE_GRASS) return false;
    if (abs(e->surface[x - 1] - s) > 1) return false;
    if (abs(e->surface[x + 1] - s) > 1) return false;

    int height = rng_range(&e->rng, 4, 6);
    int top = s - height;                 /* topmost trunk row */
    if (top - 2 < 0) return false;

    for (int y = s - 1; y >= top; --y) {
        if (!in_bounds(x, y) || e->tiles[y][x] != TILE_AIR) return false;
    }
    for (int y = s - 1; y >= top; --y)
        e->tiles[y][x] = TILE_LOG;

    bool big = rng_chance(&e->rng, 0.5f);
    if (big) {
        /* 5x3 rounded canopy wrapping the trunk top; corners omitted. */
        for (int dy = -2; dy <= 0; ++dy)
            for (int dx = -2; dx <= 2; ++dx) {
                if (abs(dx) == 2 && dy != -1) continue;
                put_air_only(e, x + dx, top + dy, TILE_LEAVES);
            }
    } else {
        for (int dy = -2; dy <= -1; ++dy)
            for (int dx = -1; dx <= 1; ++dx)
                put_air_only(e, x + dx, top + dy, TILE_LEAVES);
    }
    return true;
}

static void gen_trees(Env *e, bool *trunk) {
    for (int x = 0; x < WORLD_W; ++x) trunk[x] = false;

    int x = rng_range(&e->rng, 2, 10);
    while (x < WORLD_W - 2) {
        /* Flat ground is scarce, so nudge right a few columns rather than
           dropping the tree entirely and thinning the forest. */
        int placed = x;
        for (int k = 0; k < 4; ++k) {
            if (x + k >= WORLD_W - 2) break;
            if (try_tree(e, x + k)) { trunk[x + k] = true; placed = x + k; break; }
        }
        x = placed + rng_range(&e->rng, 6, 14);
    }
}

/* ---- 6. Spawn ----------------------------------------------------------- */

static void place_player(Env *e, const bool *trunk) {
    const int mid = WORLD_W / 2;
    int best = -1;

    for (int d = 0; d < WORLD_W / 2 && best == -1; ++d) {
        for (int side = 0; side < 2; ++side) {
            int c = side ? mid + d : mid - d;
            if (c < 1 || c >= WORLD_W - 1) continue;
            if (trunk[c]) continue;
            if (abs(e->surface[c - 1] - e->surface[c]) > 1) continue;
            if (abs(e->surface[c + 1] - e->surface[c]) > 1) continue;
            best = c;
            break;
        }
    }
    if (best == -1) best = mid;

    e->px = best;
    e->py = clampi(e->surface[best] - 1, PLAYER_H - 1, WORLD_H - 1);
    e->facing = 1;

    /* Clear the whole body column — feet at py up through the head at
       py - PLAYER_H + 1 — even if a neighbouring tree dropped leaves into it. */
    for (int y = e->py; y > e->py - PLAYER_H && y >= 0; --y)
        if (e->tiles[y][e->px] != TILE_BEDROCK)
            e->tiles[y][e->px] = TILE_AIR;
}

/* ------------------------------------------------------------------------- */

void world_generate(Env *e) {
    bool trunk[WORLD_W];

    gen_heightmap(e);
    gen_layers(e);
    gen_caves(e);
    gen_ores(e);
    gen_trees(e, trunk);
    place_player(e, trunk);
}
