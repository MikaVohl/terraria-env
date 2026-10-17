/* Off-policy rendering fixtures only. Never part of the training environment. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "env.h"
#include "px_render.h"
int main(int argc,char **argv) {
    Env e; env_init(&e,(EnvConfig){3000}); env_reset(&e,11);
    memset(e.tiles,0,sizeof e.tiles); memset(e.mobs,0,sizeof e.mobs);
    e.px=64; e.py=30;
    for(int x=0;x<WORLD_W;x++) { e.surface[x]=31; e.tiles[31][x]=TILE_GRASS; }
    Tile row[]={TILE_WORKBENCH,TILE_FURNACE,TILE_ANVIL,TILE_CAMPFIRE,
        TILE_CHEST,TILE_CHEST_OPEN,TILE_LIFE_CRYSTAL,TILE_MUSHROOM,TILE_PLATFORM,TILE_ROPE};
    for(int i=0;i<10;i++) e.tiles[30][50+i]=row[i];
    for(int i=0;i<ITEM_COUNT;i++) e.inv[i]=i+1;
    e.mobs[0]=(Mob){68,30,17,4,0,-1,MOB_BLUE_SLIME};
    e.mobs[1]=(Mob){72,27,8,2,0,-1,MOB_CAVE_BAT};
    e.max_health=140; e.health=82; e.weapon=5; e.attack_cd=2; e.heal_cd=45;
    e.terrain_dirty=true; light_recompute(&e);
    PxUi *ui=px_init(1,NULL); if(!ui) return 1;
    PxView v={.cam_x=49,.cam_y=17,.feet_x=64,.feet_y=30,.clock=1,
        .hover_reach=-1,.hover_recipe=-1,.hover_ach=31,.hover_slot=-1,.hover_item=ITEM_IRON_ARMOR};
    for(int i=0;i<RECIPE_COUNT;i++) assert(px_recipe_at(PX_VIEW_W+10,18+i*19+5)==i);
    assert(px_item_at(6+9*22+2,PX_VIEW_H+29+22+2)==30);
    for(int i=0;i<3;i++) {
        e.armor=i; px_draw(ui,&e,&v);
        char path[512]; snprintf(path,sizeof path,"%s-%d.bmp",argc>1?argv[1]:"/tmp/terraria-v2-ui",i);
        if(!px_screenshot(ui,path)) { px_shutdown(ui); return 1; }
    }
    for(int y=25;y<=30;y++) e.tiles[y][66]=TILE_LOG;
    e.tiles[24][66]=e.tiles[23][66]=TILE_LEAVES;
    e.terrain_dirty=true; light_recompute(&e);
    e.attack_cd=0;
    px_draw(ui,&e,&v);
    char before[512],after[512];
    snprintf(before,sizeof before,"%s-tree-before.bmp",argc>1?argv[1]:"/tmp/terraria-v2-ui");
    snprintf(after,sizeof after,"%s-tree-after.bmp",argc>1?argv[1]:"/tmp/terraria-v2-ui");
    assert(px_screenshot(ui,before));
    int wood=e.inv[ITEM_WOOD]; env_step(&e,ACT_MINE_FOOT_RIGHT);
    assert(e.inv[ITEM_WOOD]==wood+6 && e.mining_tree && e.mine_cd);
    px_draw(ui,&e,&v); assert(px_screenshot(ui,after));
    px_shutdown(ui); puts("pixel fixtures passed: every original asset, 3 armor variants, wrapped inventory and recipe hit tests");
    return 0;
}
