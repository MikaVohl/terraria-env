/* Finite-resource necessary conditions for all achievements. Not a planner,
 * policy, demonstration or proof of achievable score within the time limit. */
#include <stdio.h>
#include <stdlib.h>
#include "env.h"

static int input_for_achievement(int achievement,Item item) {
 for(int r=0;r<RECIPE_COUNT;r++) if(RECIPES[r].ach==achievement)
  for(int i=0;i<RECIPES[r].n_in;i++) if(RECIPES[r].in_item[i]==item) return RECIPES[r].in_qty[i];
 return 0;
}

int main(void) {
 Env *e=calloc(1,sizeof *e); if(!e) return 1;
 env_init(e,(EnvConfig){DEFAULT_MAX_STEPS});
 int iron_bars=input_for_achievement(ACH_CRAFT_ANVIL,ITEM_IRON_BAR)
              +input_for_achievement(ACH_CRAFT_IRON_PICK,ITEM_IRON_BAR)
              +input_for_achievement(ACH_CRAFT_IRON_ARMOR,ITEM_IRON_BAR);
 int gold_bars=input_for_achievement(ACH_CRAFT_GOLD_PICK,ITEM_GOLD_BAR);
 int iron_per_bar=input_for_achievement(ACH_SMELT_IRON,ITEM_IRON_ORE);
 int gold_per_bar=input_for_achievement(ACH_SMELT_GOLD,ITEM_GOLD_ORE);
 if(!iron_bars || !gold_bars || !iron_per_bar || !gold_per_bar) { free(e); return 1; }
 printf("{\"environment_version\":%d,\"seed_range\":[0,255],",ENV_VERSION);
 printf("\"all_achievements_necessary_iron_ore_equivalent\":%d,\"all_achievements_necessary_gold_ore_equivalent\":%d,",iron_bars*iron_per_bar,gold_bars*gold_per_bar);
 printf("\"records\":[");
 for(int seed=0;seed<256;seed++) {
  env_reset(e,(unsigned)seed);int items[ITEM_COUNT]={0};
  for(int i=0;i<ITEM_COUNT;i++) items[i]=e->inv[i];
  for(int y=0;y<WORLD_H;y++) for(int x=0;x<WORLD_W;x++) {
   int drop=tile_drop(tile_at(e,x,y)); if(drop>=0) items[drop]++;
  }
  for(int c=0;c<e->chest_count;c++) for(int i=0;i<ITEM_COUNT;i++) items[i]+=e->chests[c].loot[i];
  int iron=items[ITEM_IRON_ORE]+iron_per_bar*items[ITEM_IRON_BAR];
  int gold=items[ITEM_GOLD_ORE]+gold_per_bar*items[ITEM_GOLD_BAR];
  printf("%s{\"seed\":%d,\"wood\":%d,\"copper_ore\":%d,\"iron_ore_equivalent\":%d,\"silver_ore\":%d,\"gold_ore_equivalent\":%d,\"iron_shortfall\":%s,\"gold_shortfall\":%s}",
   seed?",":"",seed,items[ITEM_WOOD],items[ITEM_COPPER_ORE],iron,items[ITEM_SILVER_ORE],gold,
   iron<iron_bars*iron_per_bar?"true":"false",gold<gold_bars*gold_per_bar?"true":"false");
 }
 printf("]}\n");env_free(e);free(e);return 0;
}
