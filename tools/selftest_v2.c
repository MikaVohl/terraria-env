/* v2 mechanics/invariants. Fixtures test rules, not demonstration training. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "env.h"
#include "keymap.h"
#include "rng.h"
static void flat(Env *e) {
 env_init(e,(EnvConfig){3000}); env_reset(e,7);
 memset(e->tiles,0,sizeof e->tiles); memset(e->mobs,0,sizeof e->mobs);
 memset(e->chests,0,sizeof e->chests); e->chest_count=0;
 for(int x=0;x<WORLD_W;x++) { e->surface[x]=40; e->tiles[40][x]=TILE_STONE;
  for(int y=WORLD_H-2;y<WORLD_H;y++) e->tiles[y][x]=TILE_BEDROCK; }
 e->px=64; e->py=39; e->explore_min=e->explore_max=64;
 e->terrain_dirty=true; light_recompute(e);
}
static void mechanics(void) {
 Env e; uint8_t mask[ACT_COUNT];
 flat(&e);
 for(int y=34;y<=39;y++) e.tiles[y][66]=TILE_LOG;
 e.tiles[33][66]=e.tiles[33][65]=TILE_LEAVES;
 e.terrain_dirty=true; light_recompute(&e);
 env_step(&e,ACT_MINE_FOOT_RIGHT);
 assert(e.inv[ITEM_WOOD]==6 && e.mining_tree && e.mine_cd==2);
 for(int y=34;y<=39;y++) assert(e.tiles[y][66]==TILE_AIR);
 assert(e.tiles[33][66]==TILE_AIR && e.tiles[33][65]==TILE_AIR);
 Env oracle=e; light_reference(&oracle); assert(!memcmp(e.light,oracle.light,sizeof e.light));
 env_step(&e,ACT_MINE_FOOT_RIGHT); assert(e.inv[ITEM_WOOD]==6);
 flat(&e);
 for(int y=34;y<=39;y++) e.tiles[y][66]=TILE_LOG;
 e.terrain_dirty=true; light_recompute(&e);
 env_step(&e,ACT_MINE_HEAD_RIGHT); /* cut at row 37: four cells above cut */
 assert(e.inv[ITEM_WOOD]==4 && e.tiles[38][66]==TILE_LOG && e.tiles[39][66]==TILE_LOG);
 flat(&e); e.tiles[39][66]=e.tiles[38][66]=TILE_WOOD;
 e.terrain_dirty=true; light_recompute(&e); env_step(&e,ACT_MINE_FOOT_RIGHT);
 assert(e.inv[ITEM_WOOD]==1 && e.tiles[38][66]==TILE_WOOD && !e.mining_tree);
 flat(&e); assert(e.tool_tier==TIER_COPPER_PICK && e.health==100);
 env_action_mask(&e,mask); assert(mask[ACT_ATTACK]);
 env_step(&e,ACT_ATTACK); assert(e.attack_cd==2 && e.reward==0);
 env_action_mask(&e,mask); assert(!mask[ACT_ATTACK]);
 flat(&e); e.mobs[0]=(Mob){65,39,5,1,0,1,MOB_BLUE_SLIME};
 env_step(&e,ACT_ATTACK); assert(!e.mobs[0].kind && e.inv[ITEM_GEL]==2);
 assert(e.reward==1 && has_ach(&e,ACH_KILL_SLIME));
 e.mobs[0]=(Mob){65,39,5,1,0,1,MOB_BLUE_SLIME}; e.attack_cd=0;
 env_step(&e,ACT_ATTACK); assert(e.reward==0 && e.inv[ITEM_GEL]==4);
 flat(&e); e.mobs[0]=(Mob){65,39,16,1,0,1,MOB_CAVE_BAT};
 e.weapon=5; env_step(&e,ACT_ATTACK); assert(e.mobs[0].hp==1);
 e.mobs[0].x=65; e.attack_cd=0; env_step(&e,ACT_ATTACK);
 assert(has_ach(&e,ACH_KILL_BAT));
 flat(&e); e.armor=2; e.mobs[0]=(Mob){64,39,25,4,0,1,MOB_BLUE_SLIME};
 env_step(&e,ACT_NOOP); assert(e.health==95 && e.hurt_cd==7);
 env_step(&e,ACT_NOOP); assert(e.health==95);
 flat(&e); e.health=30; e.inv[ITEM_LESSER_POTION]=2;
 env_step(&e,ACT_HEAL_POTION); assert(e.health==80 && e.inv[ITEM_LESSER_POTION]==1);
 assert(has_ach(&e,ACH_HEAL)); env_step(&e,ACT_HEAL_POTION); assert(e.inv[ITEM_LESSER_POTION]==1);
 flat(&e); e.inv[ITEM_MUSHROOM]=1; env_action_mask(&e,mask);
 assert(mask[ACT_EAT_MUSHROOM]); /* full-health healing stays legal */
 env_step(&e,ACT_EAT_MUSHROOM); assert(!has_ach(&e,ACH_HEAL));
 flat(&e); e.inv[ITEM_LIFE_CRYSTAL]=16;
 for(int i=0;i<16;i++) env_step(&e,ACT_USE_CRYSTAL);
 assert(e.max_health==400 && e.health==400 && e.inv[ITEM_LIFE_CRYSTAL]==1);
 flat(&e); e.inv[ITEM_WOOD]=50;
 env_step(&e,ACT_CRAFT_WORKBENCH); assert(e.inv[ITEM_WOOD]==40);
 e.tiles[39][65]=TILE_WORKBENCH;
 env_step(&e,ACT_CRAFT_WOOD_SWORD); assert(e.weapon==1 && e.inv[ITEM_WOOD]==33);
 env_step(&e,ACT_CRAFT_WOOD_ARMOR); assert(e.armor==1 && e.inv[ITEM_WOOD]==3);
 e.inv[ITEM_STONE]=20; e.inv[ITEM_TORCH]=3; e.inv[ITEM_WOOD]=4;
 env_step(&e,ACT_CRAFT_FURNACE); assert(e.inv[ITEM_FURNACE]==1 && !e.inv[ITEM_TORCH]);
 flat(&e); e.inv[ITEM_GEL]=1; e.inv[ITEM_WOOD]=1;
 env_step(&e,ACT_CRAFT_TORCH); assert(e.inv[ITEM_TORCH]==3 && !e.inv[ITEM_GEL]);
 flat(&e); e.tiles[39][66]=TILE_GOLD_ORE;
 env_step(&e,ACT_MINE_FOOT_RIGHT); assert(e.inv[ITEM_GOLD_ORE]==1);
 e.tiles[39][66]=TILE_IRON_ORE; env_step(&e,ACT_MINE_FOOT_RIGHT);
 assert(!e.inv[ITEM_IRON_ORE]); env_step(&e,ACT_NOOP); env_step(&e,ACT_MINE_FOOT_RIGHT);
 assert(e.inv[ITEM_IRON_ORE]==1);
 flat(&e); e.tiles[40][64]=e.tiles[40][65]=TILE_PLATFORM;
 env_step(&e,ACT_NOOP); assert(e.py==39);
 env_step(&e,ACT_DROP); assert(e.py==40);
 flat(&e); e.tiles[39][64]=e.tiles[38][64]=e.tiles[37][64]=TILE_ROPE;
 env_step(&e,ACT_CLIMB_UP); assert(e.py==38 && has_ach(&e,ACH_CLIMB));
 flat(&e); e.inv[ITEM_CLOUD_BOTTLE]=1;
 env_step(&e,ACT_JUMP); env_step(&e,ACT_JUMP);
 assert(e.air_jump_used && has_ach(&e,ACH_DOUBLE_JUMP));
 env_action_mask(&e,mask); assert(!mask[ACT_JUMP]);
 flat(&e); e.chest_count=1; e.chests[0].x=65;e.chests[0].y=39;
 e.chests[0].loot[ITEM_ROPE]=30; e.chests[0].loot[ITEM_CLOUD_BOTTLE]=1;
 e.tiles[39][65]=TILE_CHEST; env_step(&e,ACT_INTERACT);
 assert(e.inv[ITEM_ROPE]==30 && has_ach(&e,ACH_OPEN_CHEST));
 env_step(&e,ACT_INTERACT); assert(e.inv[ITEM_ROPE]==30 && e.reward==0);
 flat(&e); e.tiles[39][66]=TILE_STONE; e.light[39][66]=0;
 env_action_mask(&e,mask); assert(mask[ACT_MINE_FOOT_RIGHT]);
 e.tiles[39][66]=TILE_AIR; env_action_mask(&e,mask); assert(mask[ACT_MINE_FOOT_RIGHT]);
 flat(&e); e.health=1; e.mobs[0]=(Mob){64,39,25,4,0,1,MOB_BLUE_SLIME};
 env_step(&e,ACT_NOOP); assert(e.terminated && e.reward==-1);
 env_step(&e,ACT_NOOP); assert(e.reward==0 && e.steps==1);
 for(int a=0;a<ACT_COUNT;a++) assert(kb_action(kb_key(a))==a);
}
static void invariants(void) {
 Env a,b; Obs obs; uint8_t mask[ACT_COUNT]; uint64_t r=999;
 env_init(&a,(EnvConfig){3000}); env_init(&b,(EnvConfig){3000});
 for(int seed=0;seed<100;seed++) {
  env_reset(&a,seed); env_reset(&b,seed); assert(!memcmp(&a,&b,sizeof a));
  for(int x=0;x<WORLD_W;x++) assert(a.tiles[WORLD_H-1][x]==TILE_BEDROCK);
  assert(a.chest_count==MAX_CHESTS && body_fits(&a,a.px,a.py));
  for(int j=0;j<3000;j++) {
   env_action_mask(&a,mask); assert(mask[0]);
   int action=(int)rng_below(&r,ACT_COUNT);
   env_step(&a,action); env_step(&b,action); assert(!memcmp(&a,&b,sizeof a));
   assert(body_fits(&a,a.px,a.py));
   assert(a.health>=0 && a.health<=a.max_health);
   assert(a.tool_tier>=1 && a.tool_tier<=3 && a.selected<PLACEABLE_COUNT);
   for(int k=0;k<MAX_MOBS;k++) if(a.mobs[k].kind) assert(in_bounds(a.mobs[k].x,a.mobs[k].y));
   for(int k=0;k<ITEM_COUNT;k++) assert(a.inv[k]>=0 && a.inv[k]<=999);
   b=a; env_obs(&a,&obs); assert(!memcmp(&a,&b,sizeof a));
   /* Live light is exact in the observation window; light_full is exact everywhere. */
   light_reference(&b);
   for(int vy=a.py-VIEW_H/2;vy<=a.py+VIEW_H/2;vy++) for(int vx=a.px-VIEW_W/2;vx<=a.px+VIEW_W/2;vx++)
    if(in_bounds(vx,vy)) assert(a.light[vy][vx]==b.light[vy][vx]);
   { Env c=a; light_full(&c); assert(!memcmp(c.light,b.light,sizeof c.light)); }
   b=a;
   for(int k=0;k<OBS_STATUS;k++) assert(isfinite(obs.status[k]) && obs.status[k]>=0 && obs.status[k]<=1);
   for(int k=0;k<VIEW_CELLS;k++) assert(obs.tile[k]<=OBS_UNKNOWN && obs.light[k]<=LIGHT_MAX);
   if(a.terminated || a.truncated) break;
  }
 }
 flat(&a); a.mobs[0]=(Mob){65,39,25,1,0,1,MOB_BLUE_SLIME};a.light[39][65]=0;
 env_obs(&a,&obs); int k=(VIEW_H/2)*VIEW_W+VIEW_W/2+1;
 assert(obs.status[OBS_ENTITY_0+k*4]==0);
 a.light[39][65]=15; env_obs(&a,&obs); assert(obs.status[OBS_ENTITY_0+k*4]==1);
 printf("v%d: mechanics, keymap, hidden entities, deterministic worlds and rollout invariants passed (100 seeds)\n",ENV_VERSION);
}
int main(void) { mechanics(); invariants(); return 0; }
