/* Adversarial arbitrary edits: every incremental result matches a full oracle. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "env.h"
#include "rng.h"
int main(void) {
    Env a,b; uint64_t rng=91;
    env_init(&a,(EnvConfig){3000});
    for(int seed=0;seed<12;seed++) {
        env_reset(&a,seed);
        for(int j=0;j<2000;j++) {
            int x=(int)rng_below(&rng,WORLD_W),y=(int)rng_below(&rng,WORLD_H-2);
            Tile before=(Tile)a.tiles[y][x];
            Tile kinds[]={TILE_AIR,TILE_STONE,TILE_TORCH,TILE_CAMPFIRE,TILE_ROPE,TILE_LEAVES};
            a.tiles[y][x]=(uint8_t)kinds[rng_below(&rng,6)];
            light_tile_changed(&a,x,y,before);
            /* Wander so the window (the only region light_recompute keeps
               exact) covers edges, caves and emitters too. */
            a.px=(int)rng_below(&rng,WORLD_W-1); a.py=PLAYER_H-1+(int)rng_below(&rng,WORLD_H-PLAYER_H+1);
            light_recompute(&a);
            b=a; light_reference(&b);
            for(int vy=a.py-VIEW_H/2;vy<=a.py+VIEW_H/2;vy++) for(int vx=a.px-VIEW_W/2;vx<=a.px+VIEW_W/2;vx++)
                if(in_bounds(vx,vy) && a.light[vy][vx]!=b.light[vy][vx]) {
                    fprintf(stderr,"window lighting mismatch seed=%d edit=%d cell (%d,%d)\n",seed,j,vx,vy);
                    return 1;
                }
            light_full(&a);
            if(memcmp(a.light,b.light,sizeof a.light)) {
                fprintf(stderr,"lighting mismatch seed=%d edit=%d (%d,%d) %d -> %d\n",seed,j,x,y,before,a.tiles[y][x]);
                return 1;
            }
        }
    }
    puts("24,000 arbitrary terrain/source edits: observation window and full map match full light propagation");
    return 0;
}
