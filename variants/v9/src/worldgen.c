/* Deterministic world generation: heightmap, layers, caves, ores, trees, spawn.
   v9 (design section 3): surface / underground (dirt-stone mix) / caverns
   (open caves, Demon Altars) / bedrock, per-layer ore bands, realistic vein
   density and a guaranteed per-world minimum for every resource. */
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

    /* Underground dirt/stone mix: dirt blobs in the stone above the caverns. */
    const int blobs = rng_range(&e->rng, 36, 48) * WORLD_W / 128;
    for (int i = 0; i < blobs; ++i) {
        int cx = rng_range(&e->rng, 1, WORLD_W - 2);
        int cy = rng_range(&e->rng, stone_top(e, cx) + 1, CAVERN_Y - 2);
        int r = rng_range(&e->rng, 1, 2);
        for (int dy = -r; dy <= r; ++dy) for (int dx = -r - 1; dx <= r + 1; ++dx) {
            int x = cx + dx, y = cy + dy;
            if (!in_bounds(x, y) || y >= CAVERN_Y || y < stone_top(e, x)) continue;
            if (dx * dx + 2 * dy * dy > r * r + 2) continue;
            if (e->tiles[y][x] == TILE_STONE) e->tiles[y][x] = TILE_DIRT;
        }
    }
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

static void worm(Env *e, int ylo, int yhi, int rlo, int rhi, int slo, int shi) {
    int sx = rng_range(&e->rng, 2, WORLD_W - 3);
    int ymin = stone_top(e, sx) + 3;
    if (ymin < ylo) ymin = ylo;
    if (ymin > yhi) return;

    float fx = (float)sx;
    float fy = (float)rng_range(&e->rng, ymin, yhi);
    float ang = rng_float(&e->rng) * TAU;
    int steps = rng_range(&e->rng, slo, shi);
    int r = rng_range(&e->rng, rlo, rhi);

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

/* Underground: narrow worm tunnels. Caverns: wider worms plus open chambers. */
static void gen_caves(Env *e) {
    const int ymax = bedrock_top() - 2;
    int n = rng_range(&e->rng, 10, 16) * WORLD_W / 128;
    for (int w = 0; w < n; ++w) worm(e, 0, CAVERN_Y - 1, 1, 2, 40, 140);
    n = rng_range(&e->rng, 12, 18) * WORLD_W / 128;
    for (int w = 0; w < n; ++w) worm(e, CAVERN_Y, ymax, 1, 3, 60, 160);
    n = rng_range(&e->rng, 4, 7) * WORLD_W / 128;
    for (int c = 0; c < n; ++c) {
        int cx = rng_range(&e->rng, 6, WORLD_W - 7), cy = rng_range(&e->rng, CAVERN_Y + 4, ymax - 3);
        int hw = rng_range(&e->rng, 4, 8), hh = rng_range(&e->rng, 2, 4);
        for (int dy = -hh; dy <= hh; ++dy) for (int dx = -hw; dx <= hw; ++dx) {
            if (dx * dx * hh * hh + dy * dy * hw * hw > hw * hw * hh * hh) continue;
            int x = cx + dx, y = cy + dy;
            if (in_bounds(x, y) && y < bedrock_top() && y >= stone_top(e, x)) e->tiles[y][x] = TILE_AIR;
        }
    }
}

/* ---- 4. Ore veins ------------------------------------------------------- */

#define VEIN_MAX 9

/* [ylo, yhi] confines vein growth to an ore's own band (all v9 ores). */
static bool ore_cell_ok(const Env *e, int x, int y, int ylo, int yhi) {
    if (!in_bounds(x, y)) return false;
    if (y < ylo || y > yhi) return false;
    if (y >= bedrock_top()) return false;
    if (y < stone_top(e, x)) return false;
    return e->tiles[y][x] == TILE_STONE;
}

static int grow_vein(Env *e, int sx, int sy, Tile ore, int ylo, int yhi) {
    if (!ore_cell_ok(e, sx, sy, ylo, yhi)) return 0;

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
    return n;
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

/* v7's per-row vein rate over each ore's v9 band (realistic density, D5):
   copper 50-60 veins per 44 rows, iron 30-40 per 49, silver 30 per 42, gold
   12-20 per 32, all per 128 columns, scaled by ORE_DENSITY_PCT. */
static int vein_count(int v7_veins, int rows, int v7_rows) {
    return v7_veins * rows * ORE_DENSITY_PCT / (v7_rows * 100) * WORLD_W / 128;
}

static void ore_band(Tile ore, int *lo, int *hi) {
    const int top = bedrock_top() - 1;
    *hi = top;
    switch (ore) {
    case TILE_SILVER_ORE: *lo = CAVERN_Y; break;
    case TILE_GOLD_ORE:   *lo = GOLD_MIN_Y; break;
    default:              *lo = SURFACE_MIN + DIRT_DEPTH + 1; break;  /* underground + caverns */
    }
}

static void gen_ores(Env *e) {
    static const Tile ORES[4] = {TILE_COPPER_ORE, TILE_IRON_ORE, TILE_SILVER_ORE, TILE_GOLD_ORE};
    static const int LO[4] = {50, 30, 30, 12}, HI[4] = {60, 40, 30, 20}, REF[4] = {44, 49, 42, 32};
    /* Gold last, overwriting other ores where bands overlap. */
    for (int k = 0; k < 4; ++k) {
        int lo, hi;
        ore_band(ORES[k], &lo, &hi);
        int veins = vein_count(rng_range(&e->rng, LO[k], HI[k]), hi - lo + 1, REF[k]);
        for (int i = 0; i < veins; ++i) {
            int x = (int)rng_below(&e->rng, WORLD_W);
            int y = weighted_row(e, lo, hi, ORES[k] == TILE_COPPER_ORE);
            grow_vein(e, x, y, ORES[k], lo, hi);
        }
    }
}

/* ---- 5. Trees ----------------------------------------------------------- */

static void put_air_only(Env *e, int x, int y, Tile t) {
    if (!in_bounds(x, y)) return;
    if (e->tiles[y][x] != TILE_AIR) return;
    e->tiles[y][x] = (uint8_t)t;
}

#define TREE_MAX_H 16
#define MAX_TREES (WORLD_W / 5 + 1)
typedef struct { int x, height; bool big; } Tree;

static void put_canopy(Env *e, int x, int top, bool big) {
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
}

static bool tree_fits(const Env *e, int x, int height) {
    int s = e->surface[x], top = s - height;
    if (top - 2 < 0) return false;
    for (int y = s - 1; y >= top; --y)
        if (!in_bounds(x, y) || e->tiles[y][x] != TILE_AIR) return false;
    return true;
}

static bool try_tree(Env *e, int x, Tree *t) {
    if (x < 2 || x >= WORLD_W - 2) return false;

    int s = e->surface[x];
    if (e->tiles[s][x] != TILE_GRASS) return false;
    if (abs(e->surface[x - 1] - s) > 1) return false;
    if (abs(e->surface[x + 1] - s) > 1) return false;

    int height = rng_range(&e->rng, 4*TREE_HEIGHT_PCT/100, 6*TREE_HEIGHT_PCT/100);
    if (height > TREE_MAX_H) height = TREE_MAX_H;
    if (!tree_fits(e, x, height)) return false;
    for (int y = s - 1; y >= s - height; --y)
        e->tiles[y][x] = TILE_LOG;
    bool big = rng_chance(&e->rng, 0.5f);
    put_canopy(e, x, s - height, big);
    *t = (Tree){x, height, big};
    return true;
}

/* Regrow a generated tree one trunk tile taller (its canopy moves up). With
   trunks at least 5 columns apart no other tree's leaves are touched. */
static bool grow_tree(Env *e, Tree *t) {
    int s = e->surface[t->x], top = s - t->height;
    if (t->height >= TREE_MAX_H || top - 3 < 0) return false;
    for (int y = top - 2; y <= top; ++y) for (int x = t->x - 2; x <= t->x + 2; ++x)
        if (in_bounds(x, y) && e->tiles[y][x] == TILE_LEAVES) e->tiles[y][x] = TILE_AIR;
    if (e->tiles[top - 1][t->x] != TILE_AIR) {   /* blocked: restore the canopy */
        put_canopy(e, t->x, top, t->big);
        return false;
    }
    e->tiles[top - 1][t->x] = TILE_LOG;
    t->height++;
    put_canopy(e, t->x, top - 1, t->big);
    return true;
}

static int gen_trees(Env *e, bool *trunk, Tree *trees) {
    for (int x = 0; x < WORLD_W; ++x) trunk[x] = false;
    int n = 0;
    int x = rng_range(&e->rng, 2, 8);
    while (x < WORLD_W - 2 && n < MAX_TREES) {
        /* Flat ground is scarce, so nudge right a few columns rather than
           dropping the tree entirely and thinning the forest. */
        int placed = x;
        for (int k = 0; k < 4; ++k) {
            if (x + k >= WORLD_W - 2) break;
            if (try_tree(e, x + k, &trees[n])) { trunk[x + k] = true; placed = x + k; n++; break; }
        }
        x = placed + rng_range(&e->rng, 5, 10);
    }
    return n;
}

static int wood_in_reach(const Env *e) {
    int n = 0;
    for (int x = e->px - WOOD_REACH; x <= e->px + WOOD_REACH; ++x) {
        if (x < 0 || x >= WORLD_W) continue;
        for (int y = 0; y < SURFACE_MAX; ++y) n += e->tiles[y][x] == TILE_LOG;
    }
    return n;
}

/* Wood floor (D5): grow the trees within reach of spawn round-robin until
   WOOD_MIN trunk tiles stand there or no tree can grow further. */
static void guarantee_wood(Env *e, Tree *trees, int n) {
    int have = wood_in_reach(e);
    for (bool grew = true; have < WOOD_MIN && grew;) {
        grew = false;
        for (int i = 0; i < n && have < WOOD_MIN; ++i) {
            if (abs(trees[i].x - e->px) > WOOD_REACH) continue;
            if (e->tiles[e->surface[trees[i].x] - 1][trees[i].x] != TILE_LOG) continue;
            if (grow_tree(e, &trees[i])) { have++; grew = true; }
        }
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
    int support=e->surface[best];
    for(int col=1;col<PLAYER_W;col++) if(e->surface[best+col]<support) support=e->surface[best+col];
    e->py = clampi(support - 1, PLAYER_H - 1, WORLD_H - 1);
    e->facing = 1;

    /* Clear the whole body column — feet at py up through the head at
       py - PLAYER_H + 1 — even if a neighbouring tree dropped leaves into it. */
    for(int col=0;col<PLAYER_W;col++) for (int y = e->py; y > e->py - PLAYER_H && y >= 0; --y)
        if (tile_solid((Tile)e->tiles[y][e->px+col]) && e->tiles[y][e->px+col] != TILE_BEDROCK)
            e->tiles[y][e->px+col] = TILE_AIR;
}

/* Necessary material supply, not a route, reward, or time-budget guarantee.
   Rooms are carved first, so their erased ore cannot invalidate these floors.
   Deficient ore first gets extra in-band veins (same grower as gen_ores), and
   only if those cannot be seeded, single randomized in-band stone cells;
   all existing ores, object components and bedrock are preserved. */
static void guarantee_ore(Env *e,Tile ore,int have,int minimum,int lo,int hi) {
    for(int tries=0;have<minimum && tries<4000;tries++) {
        int x=rng_range(&e->rng,1,WORLD_W-2),y=rng_range(&e->rng,lo,hi);
        have+=grow_vein(e,x,y,ore,lo,hi);
    }
    if(have>=minimum) return;
    int cells[WORLD_W*WORLD_H],n=0;
    for(int y=0;y<WORLD_H;y++) for(int x=0;x<WORLD_W;x++) {
        if(x>0 && x<WORLD_W-1 && y>=lo && y<=hi &&
           e->tiles[y][x]==TILE_STONE && !e->object_part[y][x]) cells[n++]=y*WORLD_W+x;
    }
    int need=minimum-have;
    for(int i=0;i<need && n>0;i++) {
        int j=(int)rng_below(&e->rng,(uint32_t)n),cell=cells[j];
        cells[j]=cells[--n]; e->tiles[cell/WORLD_W][cell%WORLD_W]=(uint8_t)ore;
    }
}

/* ---- 7. Rooms, altars, crystals ----------------------------------------- */

typedef struct { int x0, y0, x1, y1; } Rect;

static bool rect_free(const Rect *r, int n, Rect c) {
    for (int i = 0; i < n; ++i)
        if (c.x0 <= r[i].x1 + 1 && c.x1 >= r[i].x0 - 1 && c.y0 <= r[i].y1 + 1 && c.y1 >= r[i].y0 - 1) return false;
    return true;
}

/* Deepest stone_top over [x0, x1]: rooms never cut into the dirt band. */
static int stone_floor(const Env *e, int x0, int x1) {
    int m = 0;
    for (int x = x0; x <= x1; ++x) if (stone_top(e, x) > m) m = stone_top(e, x);
    return m;
}

/* Clear [x0,x1] x [y0,y1] and lay a floor of `floor` under it. */
static void carve_room(Env *e, Rect r, Tile floor) {
    for (int y = r.y0; y <= r.y1; ++y) for (int x = r.x0; x <= r.x1; ++x) {
        e->tiles[y][x] = TILE_AIR; e->object_part[y][x] = 0;
    }
    for (int x = r.x0; x <= r.x1; ++x) { e->tiles[r.y1 + 1][x] = (uint8_t)floor; e->object_part[r.y1 + 1][x] = 0; }
}

/* Try a random placement for a w x h room (plus floor) in rows [ylo, yhi]
   of columns [xlo, xhi]; bounded attempts, deterministic. */
static bool place_room(Env *e, Rect *taken, int *n, int w, int h, int xlo, int xhi, int ylo, int yhi, Rect *out) {
    for (int tries = 0; tries < 64; ++tries) {
        int x0 = rng_range(&e->rng, xlo, xhi - w + 1);
        int lo = ylo, top = stone_floor(e, x0, x0 + w - 1) + 1;
        if (lo < top + h - 1) lo = top + h - 1;
        if (lo > yhi) continue;
        int y1 = rng_range(&e->rng, lo, yhi);
        Rect c = {x0, y1 - h + 1, x0 + w - 1, y1 + 1};
        if (!rect_free(taken, *n, c)) continue;
        taken[(*n)++] = c;
        c.y1 = y1;
        *out = c;
        return true;
    }
    return false;
}

static void gen_altars(Env *e, Rect *taken, int *n) {
    int count = ALTAR_MIN + (int)rng_below(&e->rng, 2), ylo = CAVERN_Y + 4, yhi = bedrock_top() - 3;
    for (int k = 0; k < count; ++k) {
        int xlo = k * WORLD_W / count + 2, xhi = (k + 1) * WORLD_W / count - 3;
        Rect r;
        if (!place_room(e, taken, n, 7, 4, xlo, xhi, ylo, yhi, &r)
            && !place_room(e, taken, n, 7, 4, 2, WORLD_W - 3, ylo, yhi, &r)) continue;
        carve_room(e, r, TILE_STONE);
        env_object_write(e, TILE_DEMON_ALTAR, r.x0 + 2, r.y1);
    }
}

static void gen_crystals(Env *e, Rect *taken, int *n) {
    int count = CRYSTAL_MIN + (int)rng_below(&e->rng, 3);
    for (int k = 0; k < count; ++k) {
        Rect r;
        if (!place_room(e, taken, n, 4, 3, 2, WORLD_W - 3, SURFACE_MAX + DIRT_DEPTH + 4, bedrock_top() - 3, &r)) continue;
        carve_room(e, r, TILE_STONE);
        env_object_write(e, TILE_LIFE_CRYSTAL, r.x0 + 1, r.y1);
    }
}

/* Two surface supply chests plus eight treasure rooms alternating between
   the underground and the caverns. Contents vary, item universe doesn't. */
static void gen_chests(Env *e, Rect *taken, int *n) {
    e->chest_count = 0;
    for (int i = 0; i < MAX_CHESTS; i++) {
        Chest *c = &e->chests[e->chest_count];
        if (i < 2) {
            int x = i ? WORLD_W - 12 : 11;
            /* Never cut a trunk: move to the nearest column pair without logs. */
            for (int d = 0; d < 8; ++d) {
                int cand = x + ((d & 1) ? (d + 1) / 2 : -(d / 2));
                int y = e->surface[cand] - 1, other = e->surface[cand + 1] - 1;
                if (other < y) y = other;
                bool clear = true;
                for (int row = 0; row < 2; row++) for (int col = 0; col < 2; col++)
                    if (e->tiles[y - row][cand + col] == TILE_LOG) clear = false;
                if (clear || d == 7) { x = cand; break; }
            }
            c->x = x;
            c->y = e->surface[x] - 1;
            int other = e->surface[x + 1] - 1;
            if (other < c->y) c->y = other;
            for (int row = 0; row < 2; row++) for (int col = 0; col < 2; col++)
                e->tiles[c->y - row][c->x + col] = TILE_AIR;
            for (int col = 0; col < 2; col++) e->tiles[c->y + 1][c->x + col] = TILE_GRASS;
        } else {
            int xlo = 2 + (i - 2) * (WORLD_W - 4) / (MAX_CHESTS - 2), xhi = 2 + (i - 1) * (WORLD_W - 4) / (MAX_CHESTS - 2) - 1;
            bool under = i % 2 == 0;
            Rect r;
            if (!place_room(e, taken, n, 7, 4, xlo, xhi, under ? 0 : CAVERN_Y + 3,
                            under ? CAVERN_Y - 2 : bedrock_top() - 3, &r)) continue;
            carve_room(e, r, TILE_WOOD);
            c->x = r.x0 + 3; c->y = r.y1;
        }
        env_object_write(e, TILE_CHEST, c->x, c->y);
        c->opened = false;
        for (int k = 0; k < ITEM_COUNT; ++k) c->loot[k] = 0;
        c->loot[ITEM_LESSER_POTION] = (int16_t)rng_range(&e->rng, 2, 4);
        c->loot[ITEM_ROPE] = (int16_t)rng_range(&e->rng, 20, 40);
        c->loot[ITEM_TORCH] = (int16_t)rng_range(&e->rng, 6, 12);
        if (i >= 2) c->loot[ITEM_CLOUD_BOTTLE] = 1;
        else c->loot[ITEM_WOOD_SWORD] = 1;
        e->chest_count++;
    }
}

static int count_tiles(const Env *e, Tile t, int lo, int hi) {
    int n = 0;
    for (int y = lo; y <= hi; y++) for (int x = 0; x < WORLD_W; x++) n += e->tiles[y][x] == t;
    return n;
}

/* ------------------------------------------------------------------------- */

void world_generate(Env *e) {
    bool trunk[WORLD_W];
    Tree trees[MAX_TREES];
    Rect taken[MAX_CHESTS + ALTAR_MIN + CRYSTAL_MIN + 8];
    int n_taken = 0;
    /* env_reset recomputes all light afterwards; skip incremental updates. */
    e->terrain_dirty = true;

    gen_heightmap(e);
    gen_layers(e);
    gen_caves(e);
    gen_ores(e);
    int n_trees = gen_trees(e, trunk, trees);
    place_player(e, trunk);
    /* Altars first: they are the scarcest station, so they never lose a slot. */
    gen_altars(e, taken, &n_taken);
    gen_chests(e, taken, &n_taken);
    gen_crystals(e, taken, &n_taken);
    /* Mushrooms are an early recovery source, not a synthetic healing token. */
    for (int x = 3; x < WORLD_W - 3; x += 5) {
        int y = e->surface[x] - 1;
        if (e->tiles[y][x] == TILE_AIR && x != e->px && x != e->px + 1) e->tiles[y][x] = TILE_MUSHROOM;
    }
    guarantee_wood(e, trees, n_trees);
    /* Nearby slimes are available immediately without spawning on the player. */
    for (int i = 0; i < 2; i++) {
        int x = e->px + (i ? 12 : -12);
        if (in_bounds(x, e->py) && !tile_solid(tile_at(e, x, e->surface[x] - 1)))
            e->mobs[i] = (Mob){x, e->surface[x] - 1, SLIME_HP, i * 4, 0, 1, MOB_BLUE_SLIME};
    }
    /* Per-layer ore floors (D5), after every room is carved. */
    static const Tile ORES[4] = {TILE_COPPER_ORE, TILE_IRON_ORE, TILE_SILVER_ORE, TILE_GOLD_ORE};
    static const int MINS[4] = {COPPER_MIN, IRON_MIN, SILVER_MIN, GOLD_MIN};
    for (int k = 0; k < 4; ++k) {
        int lo, hi;
        ore_band(ORES[k], &lo, &hi);
        guarantee_ore(e, ORES[k], count_tiles(e, ORES[k], lo, hi), MINS[k], lo, hi);
    }
}
