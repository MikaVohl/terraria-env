#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "env.h"
int probe_check(Env *e);
static unsigned rng=192837;
static unsigned draw(void) { rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng; }
int main(void) {
    Env e;env_init(&e,(EnvConfig){3000});
    for(int t=0;t<20000;t++) {
        if(t%1000==0) {
            env_reset(&e,draw());
            /* Mix all tile kinds, including emissive/opaque tiles and caves. */
            for(int j=0;j<2000;j++)e.tiles[draw()%WORLD_H][draw()%WORLD_W]=draw()%TILE_COUNT;
        }
        if(t%16==0)e.tiles[draw()%WORLD_H][draw()%WORLD_W]=draw()%TILE_COUNT;
        e.px=draw()%WORLD_W;e.py=draw()%WORLD_H;
        light_full(&e);assert(probe_check(&e));
    }
    puts("PASS: 20000 full-map comparisons, terrain edits, emitters, movement, edges");
    return 0;
}
