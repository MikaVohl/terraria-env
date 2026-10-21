/* Full-map light propagation: sunlight, emitters and the player seeded into a
   bucket BFS that attenuates one level per tile. */
#include <string.h>

#include "env.h"

#define LIGHT_CELLS (WORLD_W * WORLD_H)

static inline void seed_cell(Env *e, int x, int y, uint8_t v) {
    if (e->light[y][x] < v) e->light[y][x] = v;
}

void light_reference(Env *e) {
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
    for (int col=0;col<PLAYER_W;col++) for (int i = 0; i < PLAYER_H; i++)
        if (in_bounds(e->px+col, e->py - i)) seed_cell(e, e->px+col, e->py - i, PLAYER_LIGHT);

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

/* Dynamic terrain lighting solves L=max(source, transmissive neighbors-1).
   A tile edit changes its source/transmission and possibly one sunlight column.
   Local relaxation handles both increases and decreases; strict attenuation
   eliminates self-sustaining cycles. A deduplicated ring bounds queued cells. */
static uint8_t column_cutoff(const Env *e,int x) {
    int y=0;
    while(y<WORLD_H && !tile_opaque((Tile)e->tiles[y][x])) y++;
    return (uint8_t)y;
}

typedef struct {
    uint16_t cells[LIGHT_CELLS]; uint8_t queued[(LIGHT_CELLS+7)/8];
    int head,tail,count;
} LightQueue;

static void enqueue(LightQueue *q,int x,int y) {
    if(!in_bounds(x,y)) return;
    int k=y*WORLD_W+x; uint8_t bit=(uint8_t)(1u<<(k&7));
    if(q->queued[k>>3]&bit) return;
    q->queued[k>>3]|=bit; q->cells[q->tail]=(uint16_t)k;
    q->tail=(q->tail+1)%LIGHT_CELLS; q->count++;
}

void light_tile_changed(Env *e,int x,int y,Tile before) {
    _Static_assert(WORLD_H<256 && LIGHT_CELLS<=65536,"light index bounds");
    if(e->terrain_dirty) return; /* full invalidation owns initial/bulk edits */
    Tile after=(Tile)e->tiles[y][x];
    if(tile_opaque(before)==tile_opaque(after) && tile_emit(before)==tile_emit(after)) return;
    /* Only the dedup bitmap needs clearing: ring cells are written before they
       are read. (A full aggregate initialiser zeroed 26 KB per edit.) */
    LightQueue q; q.head=q.tail=q.count=0; memset(q.queued,0,sizeof q.queued);
    static const int dx[4]={1,-1,0,0},dy[4]={0,0,1,-1};
    int old=e->sky_cutoff[x],fresh=column_cutoff(e,x);
    e->sky_cutoff[x]=(uint8_t)fresh;
    for(int row=old<fresh?old:fresh;row<(old>fresh?old:fresh);row++) enqueue(&q,x,row);
    enqueue(&q,x,y);
    /* Transmission may change even when this cell's brightness does not. */
    for(int d=0;d<4;d++) enqueue(&q,x+dx[d],y+dy[d]);
    while(q.count) {
        int k=q.cells[q.head],cx=k%WORLD_W,cy=k/WORLD_W;
        q.head=(q.head+1)%LIGHT_CELLS; q.count--;
        q.queued[k>>3]&=(uint8_t)~(1u<<(k&7));
        uint8_t value=cy<e->sky_cutoff[cx]?LIGHT_MAX:tile_emit((Tile)e->tiles[cy][cx]);
        for(int d=0;d<4;d++) {
            int nx=cx+dx[d],ny=cy+dy[d];
            if(in_bounds(nx,ny) && !tile_opaque((Tile)e->tiles[ny][nx])) {
                int neighbor=e->terrain_light[ny][nx];
                if(neighbor>value+1) value=(uint8_t)(neighbor-1);
            }
        }
        if(e->terrain_light[cy][cx]==value) continue;
        e->terrain_light[cy][cx]=value;
        for(int d=0;d<4;d++) enqueue(&q,cx+dx[d],cy+dy[d]);
    }
}

static void refresh_terrain(Env *e) {
    if(!e->terrain_dirty) return;
    int x=e->px,y=e->py;
    e->px=e->py=-10; light_reference(e); e->px=x; e->py=y;
    memcpy(e->terrain_light,e->light,sizeof e->light);
    for(int col=0;col<WORLD_W;col++) e->sky_cutoff[col]=column_cutoff(e,col);
    e->terrain_dirty=false;
}

/* Exact max-composition: static sky/torch light plus the small radius-3 player
   wave, seeded over whatever terrain light is already in e->light. */
static void player_glow(Env *e) {
    _Static_assert(PLAYER_LIGHT==3,"revalidate local light composition if player glow changes");
    /* At most PLAYER_LIGHT improvements per cell in this bounding rectangle. */
    uint16_t queue[(PLAYER_W+2*PLAYER_LIGHT)*(PLAYER_H+2*PLAYER_LIGHT)*PLAYER_LIGHT]; int head=0,tail=0;
    for(int col=0;col<PLAYER_W;col++) for(int i=0;i<PLAYER_H;i++) {
        int x=e->px+col,y=e->py-i;
        if(in_bounds(x,y) && e->light[y][x]<PLAYER_LIGHT) {
            e->light[y][x]=PLAYER_LIGHT; queue[tail++]=(uint16_t)(y*WORLD_W+x);
        }
    }
    static const int dx[4]={1,-1,0,0},dy[4]={0,0,1,-1};
    while(head<tail) {
        int k=queue[head++],x=k%WORLD_W,y=k/WORLD_W;
        int child=e->light[y][x]-1;
        if(child<=0 || tile_opaque((Tile)e->tiles[y][x])) continue;
        for(int d=0;d<4;d++) {
            int nx=x+dx[d],ny=y+dy[d];
            if(!in_bounds(nx,ny) || e->light[ny][nx]>=child) continue;
            e->light[ny][nx]=(uint8_t)child;
            if(!tile_opaque((Tile)e->tiles[ny][nx])) queue[tail++]=(uint16_t)(ny*WORLD_W+nx);
        }
    }
}

/* The simulator only ever reads Env.light inside the observation window: the
   observed cells, mask reach cells and nearby chests all lie within it. So
   refresh the window plus the player glow's bounding box (11x10 cells) rather
   than copying all 12 KB of terrain light on every move; that copy dominated
   the step on many-core CPUs and on GPUs. Cells outside the box keep stale
   values; light_full() rebuilds the whole map for renderers and oracles. */
void light_recompute(Env *e) {
    _Static_assert(PLAYER_W-1+PLAYER_LIGHT<=VIEW_W/2 && PLAYER_LIGHT<=VIEW_W/2
                   && PLAYER_H-1+PLAYER_LIGHT<=VIEW_H/2+1 && PLAYER_LIGHT<=VIEW_H/2,
                   "player glow box must lie inside the refreshed box");
    refresh_terrain(e);
    int ylo=e->py-VIEW_H/2-1, yhi=e->py+VIEW_H/2, xlo=e->px-VIEW_W/2, xhi=e->px+VIEW_W/2;
    if(ylo<0) ylo=0;
    if(yhi>WORLD_H-1) yhi=WORLD_H-1;
    if(xlo<0) xlo=0;
    if(xhi>WORLD_W-1) xhi=WORLD_W-1;
    for(int y=ylo;y<=yhi;y++) memcpy(&e->light[y][xlo],&e->terrain_light[y][xlo],(size_t)(xhi-xlo+1));
    player_glow(e);
}

void light_full(Env *e) {
    refresh_terrain(e);
    memcpy(e->light,e->terrain_light,sizeof e->light);
    player_glow(e);
}
