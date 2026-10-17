/* White-box reachability diagnostics, never demonstrations or training data.
   Actual generated terrain and primitive actions; wood/torch prerequisites are
   supplied explicitly. Compare mobs on/off, with ordinary 100 HP and 3000 ticks. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "env.h"

static int choose(Env *e) {
 uint8_t mask[ACT_COUNT];env_action_mask(e,mask);
 if(e->inv[ITEM_STONE]>=20) {
  if(mask[ACT_CRAFT_FURNACE]) return ACT_CRAFT_FURNACE;
  if(!e->inv[ITEM_WORKBENCH]&&!has_ach(e,ACH_CRAFT_WORKBENCH)) return ACT_CRAFT_WORKBENCH;
  if(e->inv[ITEM_WORKBENCH]) {
   if(e->selected!=5) return ACT_SELECT_NEXT;
   int best=-1,cost=999;
   for(int r=0;r<REACH_COUNT;r++) if(mask[ACT_PLACE_FIRST+r]) {
    int c=abs(REACH_DX[r])+abs(REACH_DY[r]);if(c<cost){best=r;cost=c;}
   }
   if(best>=0) return ACT_PLACE_FIRST+best;
  }
 }
 if(e->mine_cd) return ACT_ATTACK;
 /* Mine visible neighboring stone first; this can accumulate enough for a
    furnace before a shaft opens into a large chamber. Oracle tile identity
    is intentionally allowed in a mechanics probe, not exposed to learners. */
 for(int r=0;r<REACH_COUNT;r++)
  if(mask[ACT_MINE_FIRST+r]&&tile_at(e,e->px+REACH_DX[r],e->py+REACH_DY[r])==TILE_STONE)
   return ACT_MINE_FIRST+r;
 for(int r=0;r<REACH_COUNT;r++)
  if(REACH_DY[r]==1&&REACH_DX[r]>=0&&REACH_DX[r]<PLAYER_W&&mask[ACT_MINE_FIRST+r])
   return ACT_MINE_FIRST+r;
 /* A trunk protects its ground, so remove overlapping trunks via ordinary
    axe actions, rather than clearing tiles behind the simulation's back. */
 for(int r=REACH_COUNT-1;r>=0;r--)
  if(mask[ACT_MINE_FIRST+r]&&tile_at(e,e->px+REACH_DX[r],e->py+REACH_DY[r])==TILE_LOG)
   return ACT_MINE_FIRST+r;
 return ACT_ATTACK;
}

int main(int argc,char **argv) {
 int n=argc>1?atoi(argv[1]):256;
 if(n<1||n>10000) return 2;
 printf("{\"environment_version\":%d,\"seeds_per_mode\":%d,\"starting_resources_supplied\":{\"wood\":14,\"torch\":3},\"records\":[",ENV_VERSION,n);
 int first=1;
 for(int live=0;live<=1;live++) for(int seed=0;seed<n;seed++) {
  Env e;env_init(&e,(EnvConfig){3000});env_reset(&e,(uint64_t)seed);
  if(!live) memset(e.mobs,0,sizeof e.mobs);
  e.inv[ITEM_WOOD]=14;e.inv[ITEM_TORCH]=3;
  int stone=-1,furnace=-1,peak=e.py;
  while(!e.terminated&&!e.truncated&&!has_ach(&e,ACH_CRAFT_FURNACE)) {
   env_step(&e,choose(&e));
   if(e.py>peak) peak=e.py;
   if(stone<0&&has_ach(&e,ACH_COLLECT_STONE)) stone=e.steps;
   if(furnace<0&&has_ach(&e,ACH_CRAFT_FURNACE)) furnace=e.steps;
  }
  printf("%s{\"seed\":%d,\"mobs_live\":%s,\"first_stone_step\":%d,\"first_furnace_step\":%d,\"steps\":%d,\"health\":%d,\"peak_depth\":%d}",
   first?"":",",seed,live?"true":"false",stone,furnace,e.steps,e.health,peak);first=0;
 }
 puts("]}");return 0;
}
