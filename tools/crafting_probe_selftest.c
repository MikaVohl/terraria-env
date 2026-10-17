/* Test diagnostic attribution against the actual frozen legality handler. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "env.h"
void cp_read(const Env*,int*);
int cp_selftest(void);
int main(void) {
    assert(cp_selftest());
    Env *e=malloc(sizeof(Env)),*before=malloc(sizeof(Env));assert(e&&before);
    for(int code=0;code<16;code++) {
        memset(e,0,sizeof(Env));e->px=60;e->py=30;e->health=100;e->max_steps=3000;
        e->inv[ITEM_WOOD]=(code&1)?4:3;e->inv[ITEM_STONE]=(code&2)?20:19;
        e->inv[ITEM_TORCH]=(code&4)?3:2;
        if(code&8) e->tiles[30][64]=TILE_WORKBENCH;
        uint8_t mask[ACT_COUNT];int out[18];
        memcpy(before,e,sizeof(Env));cp_read(e,out);assert(memcmp(e,before,sizeof(Env))==0);
        env_action_mask(e,mask);
        int observed=(out[0]>=4)+2*(out[1]>=20)+4*(out[2]>=3)+8*out[6];
        assert(observed==code);assert(mask[ACT_CRAFT_FURNACE]==(code==15));
    }
#if ENV_VERSION >= 5
    memset(e,0,sizeof(Env));e->px=60;e->py=30;e->health=100;e->max_steps=3000;
    e->inv[ITEM_WOOD]=4;e->inv[ITEM_STONE]=20;e->inv[ITEM_TORCH]=3;
    /* Second component is in range while the anchor is outside it. */
    e->tiles[30][56]=TILE_WORKBENCH;e->tiles[30][57]=TILE_WORKBENCH;e->object_part[30][57]=1;
    int out[18];uint8_t mask[ACT_COUNT];cp_read(e,out);env_action_mask(e,mask);
    assert(out[6]==1&&out[15]==1&&out[14]==3&&mask[ACT_CRAFT_FURNACE]);
#endif
    free(e);free(before);printf("v%d observer: 16 prerequisite combinations, exact handler agreement, read-only state; footprint edge checked when applicable\n",ENV_VERSION);
    return 0;
}
