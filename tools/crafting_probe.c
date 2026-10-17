/* Read-only diagnostic observer. Never linked into the training environment. */
#include <stdlib.h>
#include <string.h>
#include "env.h"

enum { CP_FIELDS = 18 };
int cp_version(void) { return ENV_VERSION; }
int cp_fields(void) { return CP_FIELDS; }
static int near(const Env *e, Tile t) {
    for(int dy=-PLAYER_H+1-STATION_RANGE;dy<=STATION_RANGE;dy++)
        for(int dx=-STATION_RANGE;dx<PLAYER_W+STATION_RANGE;dx++)
            if(tile_at(e,e->px+dx,e->py+dy)==t) return 1;
    return 0;
}
static int spaces(const Env *e, Tile t) {
    int n=0;
#if ENV_VERSION >= 5
    int w=tile_object_w(t),h=tile_object_h(t);
#else
    int w=1,h=1;
#endif
    for(int r=0;r<REACH_COUNT;r++) {
        int x=e->px+REACH_DX[r],bottom=e->py+REACH_DY[r],ok=1;
        for(int dy=0;dy<h;dy++) for(int dx=0;dx<w;dx++) {
            int xx=x+dx,yy=bottom-dy;
            if(!in_bounds(xx,yy)||tile_at(e,xx,yy)!=TILE_AIR
               ||(tile_solid(t)&&is_body(e,xx,yy))) ok=0;
        }
        n+=ok;
    }
    return n;
}
void cp_read(const Env *e, int *out) {
    out[0]=e->inv[ITEM_WOOD];out[1]=e->inv[ITEM_STONE];out[2]=e->inv[ITEM_TORCH];
    out[3]=e->inv[ITEM_WORKBENCH];out[4]=e->inv[ITEM_FURNACE];out[5]=e->inv[ITEM_ANVIL];
    out[6]=near(e,TILE_WORKBENCH);out[7]=near(e,TILE_FURNACE);out[8]=near(e,TILE_ANVIL);
    out[9]=PLACEABLES[e->selected].item;out[10]=e->px;out[11]=e->py;
    out[12]=spaces(e,TILE_WORKBENCH);out[13]=spaces(e,TILE_FURNACE);
    int nearest=WORLD_W+WORLD_H,benches=0;
    for(int y=0;y<WORLD_H;y++) for(int x=0;x<WORLD_W;x++) if(e->tiles[y][x]==TILE_WORKBENCH) {
        int dx=x<e->px?e->px-x:(x>=e->px+PLAYER_W?x-(e->px+PLAYER_W-1):0);
        int top=e->py-PLAYER_H+1,dy=y<top?top-y:(y>e->py?y-e->py:0);
        int distance=dx>dy?dx:dy;if(distance<nearest) nearest=distance;
#if ENV_VERSION >= 5
        benches+=e->object_part[y][x]==0;
#else
        benches++;
#endif
    }
    out[14]=benches?nearest:-1;out[15]=benches;
    out[16]=e->steps;out[17]=e->health;
}
int cp_selftest(void) {
    Env *e=calloc(1,sizeof(Env)),*before=malloc(sizeof(Env));if(!e||!before) abort();
    e->px=60;e->py=30;e->health=100;e->inv[ITEM_WOOD]=4;
    e->inv[ITEM_STONE]=20;e->inv[ITEM_TORCH]=3;e->tiles[30][64]=TILE_WORKBENCH;
    int out[CP_FIELDS];memcpy(before,e,sizeof(Env));cp_read(e,out);
    int ok=out[0]==4&&out[1]==20&&out[2]==3&&out[6]==1&&out[14]==3
        &&out[15]==1&&memcmp(before,e,sizeof(Env))==0;
    e->tiles[30][64]=TILE_AIR;e->tiles[30][80]=TILE_WORKBENCH;cp_read(e,out);
    ok=ok&&out[6]==0&&out[14]==19;
    free(before);free(e);return ok;
}
