/* Fixed-point tile collision shared by the player (FID_PHYSICS) and NPCs
   (FID_MOBS). Behaviour ports, rewritten in C, of Terraria 1.4.4
   Collision.TileCollision / StepUp / StepDown / SolidCollision / CanHit
   without slopes, half bricks or liquids (the grid world has none).
   Positions are Q16.16 pixels, always >= 0 (callers clamp to the world). */
#ifndef FID_H
#define FID_H
#include <stdlib.h>
#include "env.h"

/* a*b in Q16, rounded to nearest with ties away from zero, so mirrored
   motion (left vs right) stays exactly symmetric. */
static inline fix_t fmul(fix_t a, fix_t b) {
    int64_t p = (int64_t)a * b;
    return (fix_t)(p >= 0 ? (p + 32768) >> 16 : -((-p + 32768) >> 16));
}
static inline fix_t fabsx(fix_t a) { return a < 0 ? -a : a; }
/* (int)(v / 16f) for the non-negative px values used here. */
static inline int ftile(fix_t v) { return v >> 20; }

/* Main.tileSolid && !tileSolidTop, and tileSolid (blocks or solid tops), as
   bit tests over the tile taxonomy. */
_Static_assert(TILE_COUNT <= 32, "tile bitsets");
#define FID_BIT(t) (1u << (t))
#define FID_TOP_MASK (FID_BIT(TILE_PLATFORM) | FID_BIT(TILE_WORKBENCH) | FID_BIT(TILE_ANVIL))
#define FID_BLOCK_MASK (FID_BIT(TILE_DIRT) | FID_BIT(TILE_GRASS) | FID_BIT(TILE_STONE) | FID_BIT(TILE_WOOD) | \
    FID_BIT(TILE_COPPER_ORE) | FID_BIT(TILE_IRON_ORE) | FID_BIT(TILE_GOLD_ORE) | FID_BIT(TILE_BEDROCK) | FID_BIT(TILE_SILVER_ORE))
static inline bool fid_block(Tile t) { return FID_BLOCK_MASK >> t & 1u; }
static inline bool fid_any_solid(Tile t) { return (FID_BLOCK_MASK | FID_TOP_MASK) >> t & 1u; }
static inline int clampi_fid(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

typedef struct { bool up, down; } FidHit;

/* Collision.TileCollision: returns the velocity that stops the box at the
   first tile face it would cross. fall_through drops through solid-top tiles
   while |vy| <= 1 (Player: controlDown); fall2 always (NPCs that fall). */
static inline void fid_tile_collision(const Env *e, fix_t px, fix_t py, fix_t *vx, fix_t *vy,
                                      int w, int h, bool fall_through, bool fall2, FidHit *hit) {
    const fix_t W = w * FIX_ONE, H = h * FIX_ONE;
    fix_t rx = *vx, ry = *vy;
    const fix_t nx = px + *vx, ny = py + *vy;
    int x0 = clampi_fid(ftile(px) - 1, 0, WORLD_W - 1), x1 = clampi_fid(ftile(px + W) + 2, 0, WORLD_W - 1);
    int y0 = clampi_fid(ftile(py) - 1, 0, WORLD_H - 1), y1 = clampi_fid(ftile(py + H) + 2, 0, WORLD_H - 1);
    int side_x = -1, side_y = -1, floor_x = -1, floor_y = -1;
    fix_t best_floor = (y1 + 3) * TILE_FIX;
    hit->up = hit->down = false;
    /* Only tiles overlapping the moved box act, so scan just those (same
       order as the real x0..x1, y0..y1 sweep, hence the same result). */
    const int i0 = ftile(nx) > x0 ? ftile(nx) : x0, i1 = ftile(nx + W - 1) + 1 < x1 ? ftile(nx + W - 1) + 1 : x1;
    const int j0 = ftile(ny) > y0 ? ftile(ny) : y0, j1 = ftile(ny + H - 1) + 1 < y1 ? ftile(ny + H - 1) + 1 : y1;
    for (int i = i0; i < i1; i++) for (int j = j0; j < j1; j++) {
        Tile t = (Tile)e->tiles[j][i];
        if (!fid_any_solid(t)) continue;
        const bool top_only = tile_solid_top(t);
        const fix_t tx = i * TILE_FIX, ty = j * TILE_FIX;
        if (!(nx + W > tx && nx < tx + TILE_FIX && ny + H > ty && ny < ty + TILE_FIX)) continue;
        if (py + H <= ty) {
            hit->down = true;
            if ((!(top_only && fall_through) || !(*vy <= FIX_ONE || fall2)) && best_floor > ty) {
                floor_x = i; floor_y = j;
                if (floor_x != side_x) { ry = ty - (py + H); best_floor = ty; }
            }
        } else if (px + W <= tx && !top_only) {
            side_x = i; side_y = j;
            if (side_y != floor_y) rx = tx - (px + W);
            if (floor_x == side_x) ry = *vy;
        } else if (px >= tx + TILE_FIX && !top_only) {
            side_x = i; side_y = j;
            if (side_y != floor_y) rx = tx + TILE_FIX - px;
            if (floor_x == side_x) ry = *vy;
        } else if (py >= ty + TILE_FIX && !top_only) {
            hit->up = true; floor_x = i; floor_y = j;
            ry = ty + TILE_FIX - py + FIXC(0.01);
            if (floor_y == side_y) rx = *vx;
        }
    }
    *vx = rx; *vy = ry;
}

/* Collision.SolidCollision: does the box overlap any full solid tile? */
static inline bool fid_solid_collision(const Env *e, fix_t px, fix_t py, int w, int h) {
    const fix_t W = w * FIX_ONE, H = h * FIX_ONE;
    int x0 = clampi_fid(ftile(px), 0, WORLD_W - 1), x1 = clampi_fid(ftile(px + W - 1) + 1, 0, WORLD_W);
    int y0 = clampi_fid(ftile(py), 0, WORLD_H - 1), y1 = clampi_fid(ftile(py + H - 1) + 1, 0, WORLD_H);
    for (int i = x0; i < x1; i++) for (int j = y0; j < y1; j++) {
        if (!fid_block((Tile)e->tiles[j][i])) continue;
        const fix_t tx = i * TILE_FIX, ty = j * TILE_FIX;
        if (px + W > tx && px < tx + TILE_FIX && py + H > ty && py < ty + TILE_FIX) return true;
    }
    return false;
}

/* Collision.CanHit: tile line of sight between the two boxes' centre tiles,
   stepping along the longer axis; blocked by a solid tile on the path or by
   solid tiles on both sides of a step. */
static inline bool fid_can_hit(const Env *e, fix_t ax, fix_t ay, int aw, int ah, fix_t bx, fix_t by, int bw, int bh) {
    int x = ((ax >> 16) + aw / 2) / 16, y = ((ay >> 16) + ah / 2) / 16;
    int tx = ((bx >> 16) + bw / 2) / 16, ty = ((by >> 16) + bh / 2) / 16;
    x = clampi_fid(x, 1, WORLD_W - 1); tx = clampi_fid(tx, 1, WORLD_W - 1);
    y = clampi_fid(y, 1, WORLD_H - 1); ty = clampi_fid(ty, 1, WORLD_H - 1);
    do {
        int dx = abs(x - tx), dy = abs(y - ty);
        if (x == tx && y == ty) return true;
        if (dx > dy) {
            x += x >= tx ? -1 : 1;
            if (fid_block(tile_at(e, x, y - 1)) && fid_block(tile_at(e, x, y + 1))) return false;
        } else {
            y += y >= ty ? -1 : 1;
            if (fid_block(tile_at(e, x - 1, y)) && fid_block(tile_at(e, x + 1, y))) return false;
        }
    } while (!fid_block(tile_at(e, x, y)));
    return false;
}

/* Rectangle.Intersects on integer px rectangles (positions truncated). */
static inline bool fid_rects(fix_t ax, fix_t ay, int aw, int ah, fix_t bx, fix_t by, int bw, int bh) {
    int x1 = ax >> 16, y1 = ay >> 16, x2 = bx >> 16, y2 = by >> 16;
    return x2 < x1 + aw && x1 < x2 + bw && y2 < y1 + ah && y1 < y2 + bh;
}

#if AIM_ATTACK
/* Collision.CheckAABBvLineCollision(objectPosition, objectDimensions,
   lineStart a, lineEnd b, lineWidth lw) with the target as a Rectangle
   (integer px, as NPC.Hitbox). (ux, uy) is the line's unit direction
   (b - a is a multiple of it; len = (b - a).u). Broad phase: the
   segment's box widened by lw/2 on every side (CheckAABBvAABBCollision);
   narrow phase in the line's frame (rotated by -atan2(u)): a target corner
   with 0 <= X < len and |Y| < lw/2, or a target edge crossing one of the
   strip's long edges Y = +-lw/2 at 0 <= X <= len. Like the original it
   misses a target that wholly contains the strip. Integer arithmetic
   throughout (Q16 positions, int64 products). */
static inline bool fid_line_hits(fix_t ax, fix_t ay, fix_t bx, fix_t by, fix_t ux, fix_t uy, fix_t lw,
                                 fix_t ox, fix_t oy, int ow, int oh) {
    const fix_t half = lw / 2;
    ox = (ox >> 16) * FIX_ONE; oy = (oy >> 16) * FIX_ONE;
    const fix_t ow_ = ow * FIX_ONE, oh_ = oh * FIX_ONE;
    fix_t px = ax, py = ay, vx = bx - ax, vy = by - ay;
    const int64_t len = fmul(vx, ux) + fmul(vy, uy);
    if (vx > 0) { vx += lw; px -= half; } else { px += vx - half; vx = -vx + lw; }
    if (vy > 0) { vy += lw; py -= half; } else { py += vy - half; vy = -vy + lw; }
    if (!(ox < px + vx && oy < py + vy && ox + ow_ > px && oy + oh_ > py)) return false;
    const fix_t cx[4] = {ox - ax, ox + ow_ - ax, ox + ow_ - ax, ox - ax};
    const fix_t cy[4] = {oy - ay, oy - ay, oy + oh_ - ay, oy + oh_ - ay};
    int64_t X[4], Y[4];
    for (int i = 0; i < 4; i++) {
        X[i] = fmul(cx[i], ux) + fmul(cy[i], uy);
        Y[i] = fmul(cy[i], ux) - fmul(cx[i], uy);
        if ((Y[i] < 0 ? -Y[i] : Y[i]) < half && X[i] < len && X[i] >= 0) return true;
    }
    for (int j = 0; j < 4; j++) {
        const int k = (j + 1) & 3;
        const int64_t dX = X[k] - X[j], dY = Y[k] - Y[j];
        if (dY == 0 || len == 0) continue;
        for (int s = -1; s <= 1; s += 2) {
            const int64_t num = s * (int64_t)half - Y[j];        /* t = num / dY in [0, 1] */
            const int64_t xc = X[j] * dY + num * dX;              /* crossing X times dY */
            if (dY > 0 ? (num >= 0 && num <= dY && xc >= 0 && xc <= len * dY)
                       : (num <= 0 && num >= dY && xc <= 0 && xc >= len * dY)) return true;
        }
    }
    return false;
}
#endif

#endif
