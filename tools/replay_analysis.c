/* Read-only physical telemetry from a versioned action tape. No controller. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "env.h"

int main(int argc,char **argv) {
 if(argc!=2) { fprintf(stderr,"usage: replay-analysis TAPE\n"); return 2; }
 FILE *file=fopen(argv[1],"r"); if(!file) { perror(argv[1]); return 1; }
 char line[512]; int version=0,max_steps=0,count=-1; unsigned long long seed=0;
 while(fgets(line,sizeof line,file)) {
  if(sscanf(line,"environment %d",&version)==1) continue;
  if(sscanf(line,"seed %llu",&seed)==1) continue;
  if(sscanf(line,"max_steps %d",&max_steps)==1) continue;
  if(sscanf(line,"actions %d",&count)==1) break;
 }
 if(version!=ENV_VERSION || max_steps<1 || count<1 || count>10000000) {
  fprintf(stderr,"incompatible or malformed tape header\n"); fclose(file); return 1;
 }
 Env *e=calloc(1,sizeof *e); if(!e) { fclose(file); return 1; }
 env_init(e,(EnvConfig){max_steps}); env_reset(e,seed);
 int initial_y=e->py,min_y=e->py,max_y=e->py;
 int stationary=0,grounded=0,last_progress=0,processed=0;
 int actions[ACT_COUNT]={0},tail[ACT_COUNT]={0},mined[TILE_COUNT]={0},placed[TILE_COUNT]={0},peaks[ITEM_COUNT]={0};
 uint8_t original[WORLD_H][WORLD_W]; bool removed[WORLD_H][WORLD_W]={0};
 int unique_original[TILE_COUNT]={0}; memcpy(original,e->tiles,sizeof original);
 for(int t=0;t<count;t++) {
  int action; char extra;
  if(!fgets(line,sizeof line,file) || sscanf(line,"%d %c",&action,&extra)!=1 || action<0 || action>=ACT_COUNT) {
   fprintf(stderr,"invalid action at tape tick %d\n",t+1); fclose(file); free(e); return 1;
  }
  if(e->terminated || e->truncated) continue;
  int x=e->px,y=e->py,target=-1,tx=0,ty=0; uint32_t bits=e->achievements;
  bool mining=action>=ACT_MINE_FIRST && action<ACT_MINE_FIRST+REACH_COUNT;
  bool placing=action>=ACT_PLACE_FIRST && action<ACT_PLACE_FIRST+REACH_COUNT;
  if(mining || placing) {
   target=action-(mining?ACT_MINE_FIRST:ACT_PLACE_FIRST);
   tx=x+REACH_DX[target];ty=y+REACH_DY[target];
  }
  Tile before=target>=0?tile_at(e,tx,ty):TILE_AIR;
  if(player_grounded(e)) grounded++;
  env_step(e,action);processed++;actions[action]++;tail[action]++;
  /* Count original cells at most once, including a tree's entire felled
     trunk. Re-mining a player-placed block must not masquerade as exploration. */
  for(int yy=0;yy<WORLD_H;yy++) for(int xx=0;xx<WORLD_W;xx++)
   if(!removed[yy][xx] && original[yy][xx]!=TILE_AIR && e->tiles[yy][xx]!=original[yy][xx]) {
    removed[yy][xx]=true;unique_original[original[yy][xx]]++;
   }
  if(e->px==x && e->py==y) stationary++;
  if(e->py<min_y) min_y=e->py;
  if(e->py>max_y) max_y=e->py;
  for(int i=0;i<ITEM_COUNT;i++) if(e->inv[i]>peaks[i]) peaks[i]=e->inv[i];
  Tile after=target>=0?tile_at(e,tx,ty):TILE_AIR;
  if(mining && before!=after) mined[before]++;
  if(placing && before!=after) placed[after]++;
  if(e->achievements!=bits) { last_progress=e->steps; memset(tail,0,sizeof tail); }
 }
 fclose(file);
 printf("{\"environment_version\":%d,\"seed\":%llu,\"tape_actions\":%d,\"processed_actions\":%d,",ENV_VERSION,seed,count,processed);
 printf("\"initial_feet_y\":%d,\"min_feet_y\":%d,\"peak_feet_y\":%d,\"final_feet_y\":%d,",initial_y,min_y,max_y,e->py);
 printf("\"stationary_actions\":%d,\"grounded_before_actions\":%d,\"last_achievement_step\":%d,\"unproductive_tail_actions\":%d,",stationary,grounded,last_progress,e->steps-last_progress);
 printf("\"final_state\":{\"steps\":%d,\"health\":%d,\"achievement_mask\":%u,\"episode_return\":%.1f},",e->steps,e->health,e->achievements,e->ep_return);
 printf("\"actions\":[");for(int i=0;i<ACT_COUNT;i++) printf("%s%d",i?",":"",actions[i]);
 printf("],\"actions_after_last_achievement\":[");for(int i=0;i<ACT_COUNT;i++) printf("%s%d",i?",":"",tail[i]);
 printf("],\"successful_mine_targets_by_tile\":[");for(int i=0;i<TILE_COUNT;i++) printf("%s%d",i?",":"",mined[i]);
 printf("],\"successful_placements_by_tile\":[");for(int i=0;i<TILE_COUNT;i++) printf("%s%d",i?",":"",placed[i]);
 printf("],\"unique_original_terrain_cells_changed_by_tile\":[");for(int i=0;i<TILE_COUNT;i++) printf("%s%d",i?",":"",unique_original[i]);
 printf("],\"inventory_peaks\":[");for(int i=0;i<ITEM_COUNT;i++) printf("%s%d",i?",":"",peaks[i]);
 printf("],\"tile_names\":[");for(int i=0;i<TILE_COUNT;i++) printf("%s\"%s\"",i?",":"",TILE_INFO[i].name);
 printf("],\"item_names\":[");for(int i=0;i<ITEM_COUNT;i++) printf("%s\"%s\"",i?",":"",ITEM_NAME[i]);
 printf("],\"action_names\":[");for(int i=0;i<ACT_COUNT;i++) printf("%s\"%s\"",i?",":"",action_name(i));
 printf("]}\n");env_free(e);free(e);return 0;
}
