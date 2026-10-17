/* Focused v4 geometry/fidelity rules. These fixtures are not training data. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "env.h"
#include "keymap.h"
static void flat(Env *e) {
 env_init(e,(EnvConfig){3000}); env_reset(e,17);
 memset(e->tiles,0,sizeof e->tiles); memset(e->mobs,0,sizeof e->mobs);
 memset(e->chests,0,sizeof e->chests); e->chest_count=0;
 for(int x=0;x<WORLD_W;x++) { e->surface[x]=60; e->tiles[60][x]=TILE_STONE; }
 e->px=40;e->py=59;e->facing=1;
 e->terrain_dirty=true; light_recompute(e);
}
int main(void) {
 for(int a=0;a<ACT_COUNT;a++) assert(kb_action(kb_key(a))==a);
 assert(kb_shifted_action('a')==ACT_PLACE_FIRST+10);
 assert(kb_shifted_action('f')==ACT_PLACE_FIRST+15);
 assert(kb_shifted_action('1')==ACT_MINE_FIRST+10);
 assert(kb_shifted_action(',')==ACT_PLACE_FIRST+7);
 Env e,oracle; uint8_t mask[ACT_COUNT];
 flat(&e); assert(body_fits(&e,40,59)&&!body_fits(&e,WORLD_W-1,59));
 int targets[5][4]={{0}};
 for(int i=0;i<REACH_COUNT;i++) { assert(REACH_DY[i]>=-3&&REACH_DY[i]<=1&&REACH_DX[i]>=-1&&REACH_DX[i]<=2);targets[REACH_DY[i]+3][REACH_DX[i]+1]++; }
 for(int y=0;y<5;y++) for(int x=0;x<4;x++) assert(targets[y][x]==1);
 e.tiles[57][41]=TILE_STONE; assert(!body_fits(&e,40,59));
 e.tiles[57][41]=TILE_AIR; e.tiles[56][41]=TILE_STONE;
 env_action_mask(&e,mask); assert(!mask[ACT_JUMP]); env_step(&e,ACT_JUMP); assert(e.py==59);
 e.tiles[59][42]=TILE_STONE; env_action_mask(&e,mask); assert(!mask[ACT_RIGHT]);
 env_step(&e,ACT_RIGHT); assert(e.px==40&&e.py==59); /* cannot step through right-column ceiling */
 flat(&e); e.tiles[60][40]=TILE_AIR; env_step(&e,ACT_NOOP); assert(e.py==59); /* either foot supports */
 /* Two-foot shafts require two successful digs per row, not a movement macro.
    Prove ordinary surface-to-stone descent remains reachable with no damage. */
 flat(&e); for(int y=60;y<=80;y++) for(int x=40;x<=41;x++) e.tiles[y][x]=TILE_STONE;
 e.terrain_dirty=true;light_recompute(&e);
 for(int row=60;row<=79;row++) {
  env_step(&e,ACT_MINE_DOWN); while(e.mine_cd) env_step(&e,ACT_NOOP);
  assert(e.py==row-1); /* second foot remains supported */
  env_step(&e,ACT_MINE_DOWN_INNER_RIGHT); while(e.mine_cd) env_step(&e,ACT_NOOP);
  assert(e.py==row&&e.health==100&&body_fits(&e,e.px,e.py));
 }
 assert(e.inv[ITEM_STONE]==40);
 e.inv[ITEM_WOOD]=20;e.inv[ITEM_TORCH]=3;
 env_step(&e,ACT_CRAFT_WORKBENCH);assert(e.inv[ITEM_WORKBENCH]==1);
 e.selected=5;env_step(&e,ACT_PLACE_BODY_FOOT_LEFT);
 env_step(&e,ACT_CRAFT_FURNACE);assert(e.inv[ITEM_FURNACE]==1&&has_ach(&e,ACH_CRAFT_FURNACE));
 flat(&e); for(int y=54;y<60;y++) e.tiles[y][42]=TILE_LOG;
 e.terrain_dirty=true; light_recompute(&e); assert(e.light[58][42]==LIGHT_MAX);
 env_step(&e,ACT_RIGHT); assert(e.px==41&&e.inv[ITEM_WOOD]==0); /* walk through a tree */
 env_step(&e,ACT_MINE_BODY_FOOT_RIGHT); assert(e.inv[ITEM_WOOD]==6); /* chop an overlapped trunk */
 oracle=e;light_reference(&oracle);assert(!memcmp(e.light,oracle.light,sizeof e.light));
 flat(&e); e.tiles[59][42]=TILE_LOG; e.terrain_dirty=true;light_recompute(&e);
 env_action_mask(&e,mask); assert(!mask[ACT_MINE_DOWN_RIGHT]);
 env_step(&e,ACT_MINE_DOWN_RIGHT); assert(e.tiles[60][42]==TILE_STONE&&e.inv[ITEM_STONE]==0);
 flat(&e); e.tiles[59][42]=TILE_FURNACE; env_step(&e,ACT_RIGHT); assert(e.px==41&&e.py==59);
 flat(&e); e.tiles[59][40]=TILE_WORKBENCH; e.py=57;
 env_step(&e,ACT_NOOP); assert(e.py==58); env_step(&e,ACT_NOOP);assert(e.py==58);
 env_step(&e,ACT_DROP);assert(e.py==59); /* one-way station top */
 flat(&e);e.tiles[60][40]=TILE_PLATFORM;env_step(&e,ACT_DROP);assert(e.py==59); /* other foot still on stone */
 flat(&e);e.inv[ITEM_WOOD]=1;e.selected=2;
 env_action_mask(&e,mask);assert(!mask[ACT_PLACE_BODY_FOOT_RIGHT]);
 env_step(&e,ACT_PLACE_BODY_FOOT_RIGHT);assert(e.tiles[59][41]==TILE_AIR&&e.inv[ITEM_WOOD]==1);
 e.inv[ITEM_ROPE]=1;e.selected=9;
 env_action_mask(&e,mask);assert(mask[ACT_PLACE_BODY_HEAD_RIGHT]);
 env_step(&e,ACT_PLACE_BODY_HEAD_RIGHT);assert(e.tiles[57][41]==TILE_ROPE&&player_on_rope(&e));
 flat(&e);env_step(&e,ACT_JUMP);for(int i=0;i<JUMP_HEIGHT-1;i++) env_step(&e,ACT_NOOP);assert(e.py==59-6);
 for(int distance=25;distance<=27;distance++) {
  flat(&e);e.py=59-distance;
  for(int i=0;i<distance;i++) env_step(&e,ACT_NOOP);
  assert(e.py==59&&e.health==100-(distance>25?(distance-25)*10:0));
 }
 flat(&e);e.armor=2;e.py=32;for(int i=0;i<27;i++) env_step(&e,ACT_NOOP);assert(e.health==82);
 flat(&e);e.armor=1;e.py=33;for(int i=0;i<26;i++) env_step(&e,ACT_NOOP);assert(e.health==91);
 flat(&e);e.armor=1;e.mobs[0]=(Mob){41,57,25,4,0,1,MOB_BLUE_SLIME};env_step(&e,ACT_NOOP);assert(e.health==94);
 flat(&e);e.mobs[0]=(Mob){41,57,25,4,0,1,MOB_BLUE_SLIME};env_step(&e,ACT_NOOP);assert(e.health==93);
 flat(&e);e.mobs[0]=(Mob){43,57,5,1,0,1,MOB_BLUE_SLIME};env_step(&e,ACT_ATTACK);assert(!e.mobs[0].kind);
 puts("v4 fidelity: 2x3 clearance/support/contact, complete reach, pass-through trees/stations, tree ground protection, body placement, jump and fall boundaries passed");
 return 0;
}
