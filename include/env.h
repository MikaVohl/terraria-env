/* Allocation-free deterministic simulator. All mutable state belongs to Env. */
#ifndef ENV_H
#define ENV_H
#include <stdbool.h>
#include <stdint.h>
#include "tiles.h"
#define ENV_VERSION 4
#define WORLD_W 128
#define WORLD_H 96
#define SURFACE_BASE 30
#define SURFACE_MIN 22
#define SURFACE_MAX 38
#define DIRT_DEPTH 8
#define BEDROCK_ROWS 2
#define COPPER_MIN_Y 42
#define COPPER_MAX_Y 85
#define IRON_MIN_Y 45
#define IRON_MAX_Y 93
#define GOLD_MIN_Y 62
#define GOLD_MAX_Y 93
#define PLAYER_W 2
#define PLAYER_H 3
#define MAX_HEALTH 100
#define HEALTH_CAP 400
#define FALL_SAFE 25
#define FALL_DMG_PER_TILE 10
#define JUMP_HEIGHT 6
#define STATION_RANGE 3
#define DEEP_Y 70
#define FALL_REWARD_PER_HP 0.0f
#define DEATH_REWARD -1.0f
#define REACH_COUNT 20
/* Complete one-cell border and six overlapped body cells. The latter are
   needed to chop pass-through trees and place non-solid rope/torches. px is
   the body's left column, py its feet row; facing never changes the anchor. */
static const int REACH_DX[REACH_COUNT] = {-1,0,2,-1,2,-1,2,-1,0,2,1,-1,2,1,0,1,0,1,0,1};
static const int REACH_DY[REACH_COUNT] = {-3,-3,-3,-2,-2,0,0,1,1,1,-3,-1,-1,1,-2,-2,-1,-1,0,0};
static const char *const REACH_NAME[REACH_COUNT] = {"up-left","up","up-right",
 "head-left","head-right","foot-left","foot-right","down-left","down","down-right",
 "above right column","middle-left","middle-right","below right column",
 "body head-left","body head-right","body middle-left","body middle-right","body foot-left","body foot-right"};
#define LIGHT_MAX 15
#define PLAYER_LIGHT 3
#define DARK_THRESHOLD 2
#define DEFAULT_MAX_STEPS 3000
typedef enum {
 ACT_NOOP,ACT_LEFT,ACT_RIGHT,ACT_JUMP,
 ACT_MINE_UP_LEFT,ACT_MINE_UP,ACT_MINE_UP_RIGHT,ACT_MINE_HEAD_LEFT,
 ACT_MINE_HEAD_RIGHT,ACT_MINE_FOOT_LEFT,ACT_MINE_FOOT_RIGHT,
 ACT_MINE_DOWN_LEFT,ACT_MINE_DOWN,ACT_MINE_DOWN_RIGHT,
 ACT_MINE_UP_INNER_RIGHT,ACT_MINE_MIDDLE_LEFT,ACT_MINE_MIDDLE_RIGHT,ACT_MINE_DOWN_INNER_RIGHT,
 ACT_MINE_BODY_HEAD_LEFT,ACT_MINE_BODY_HEAD_RIGHT,ACT_MINE_BODY_MIDDLE_LEFT,ACT_MINE_BODY_MIDDLE_RIGHT,
 ACT_MINE_BODY_FOOT_LEFT,ACT_MINE_BODY_FOOT_RIGHT,
 ACT_PLACE_UP_LEFT,ACT_PLACE_UP,ACT_PLACE_UP_RIGHT,ACT_PLACE_HEAD_LEFT,
 ACT_PLACE_HEAD_RIGHT,ACT_PLACE_FOOT_LEFT,ACT_PLACE_FOOT_RIGHT,
 ACT_PLACE_DOWN_LEFT,ACT_PLACE_DOWN,ACT_PLACE_DOWN_RIGHT,
 ACT_PLACE_UP_INNER_RIGHT,ACT_PLACE_MIDDLE_LEFT,ACT_PLACE_MIDDLE_RIGHT,ACT_PLACE_DOWN_INNER_RIGHT,
 ACT_PLACE_BODY_HEAD_LEFT,ACT_PLACE_BODY_HEAD_RIGHT,ACT_PLACE_BODY_MIDDLE_LEFT,ACT_PLACE_BODY_MIDDLE_RIGHT,
 ACT_PLACE_BODY_FOOT_LEFT,ACT_PLACE_BODY_FOOT_RIGHT,ACT_SELECT_NEXT,
 ACT_CRAFT_WORKBENCH,ACT_CRAFT_FURNACE,ACT_CRAFT_TORCH,ACT_CRAFT_CAMPFIRE,
 ACT_CRAFT_PLATFORM,ACT_SMELT_COPPER,ACT_SMELT_IRON,ACT_SMELT_SILVER,
 ACT_SMELT_GOLD,ACT_CRAFT_ANVIL,ACT_CRAFT_IRON_PICK,ACT_CRAFT_GOLD_PICK,
 ACT_CRAFT_WOOD_SWORD,ACT_CRAFT_COPPER_SWORD,ACT_CRAFT_IRON_SWORD,
 ACT_CRAFT_SILVER_SWORD,ACT_CRAFT_GOLD_SWORD,ACT_CRAFT_WOOD_ARMOR,ACT_CRAFT_IRON_ARMOR,
 ACT_ATTACK,ACT_INTERACT,ACT_HEAL_POTION,ACT_EAT_MUSHROOM,ACT_USE_CRYSTAL,
 ACT_EQUIP_NEXT,ACT_CLIMB_UP,ACT_CLIMB_DOWN,ACT_DROP,ACT_COUNT
} Action;
#define ACT_MINE_FIRST ACT_MINE_UP_LEFT
#define ACT_PLACE_FIRST ACT_PLACE_UP_LEFT
typedef enum {
 ACH_COLLECT_WOOD,ACH_COLLECT_STONE,ACH_PLACE_BLOCK,ACH_CRAFT_WORKBENCH,
 ACH_CRAFT_FURNACE,ACH_CRAFT_ANVIL,ACH_PLACE_TORCH,ACH_PLACE_PLATFORM,
 ACH_COLLECT_COPPER,ACH_COLLECT_IRON,ACH_COLLECT_SILVER,ACH_COLLECT_GOLD,
 ACH_SMELT_COPPER,ACH_SMELT_IRON,ACH_SMELT_SILVER,ACH_SMELT_GOLD,
 ACH_KILL_SLIME,ACH_KILL_BAT,ACH_OPEN_CHEST,ACH_CRAFT_WOOD_SWORD,
 ACH_CRAFT_METAL_SWORD,ACH_CRAFT_WOOD_ARMOR,ACH_CRAFT_IRON_ARMOR,
 ACH_HEAL,ACH_USE_CRYSTAL,ACH_DOUBLE_JUMP,ACH_DESCEND_DEEP,ACH_RETURN_SURFACE,
 ACH_EXPLORE,ACH_CLIMB,ACH_CRAFT_IRON_PICK,ACH_CRAFT_GOLD_PICK,ACH_COUNT
} Achievement;
static const char *const ACH_NAME[ACH_COUNT] = {
 "collect wood","collect stone","place block","craft workbench","craft furnace",
 "craft anvil","place torch","place platform","collect copper","collect iron",
 "collect silver","collect gold","smelt copper","smelt iron","smelt silver","smelt gold",
 "defeat Blue Slime","defeat Cave Bat","open chest","craft wooden sword",
 "craft metal sword","craft wood breastplate","craft iron chainmail","heal with food or potion",
 "use life crystal","double jump","descend deep","return to surface","explore 30 columns",
 "climb rope","craft iron pickaxe","craft gold pickaxe"
};
_Static_assert(ACH_COUNT<=32,"achievement ABI is uint32");
#define VIEW_W 11
#define VIEW_H 9
#define VIEW_CELLS (VIEW_W*VIEW_H)
#define OBS_UNKNOWN TILE_COUNT
#define OBS_TILE_KINDS (TILE_COUNT+1)
#define OBS_HEALTH 0
#define OBS_TIER 1
#define OBS_FACING 2
#define OBS_JUMP 3
#define OBS_FALL 4
#define OBS_DEPTH 5
#define OBS_ACROSS 6
#define OBS_TIME 7
#define OBS_MAX_HEALTH 8
#define OBS_WEAPON 9
#define OBS_ARMOR 10
#define OBS_ATTACK_CD 11
#define OBS_HEAL_CD 12
#define OBS_HURT_CD 13
#define OBS_AIR_JUMP 14
#define OBS_MINE_CD 15
#define OBS_SAFE_TIME 16
#define OBS_SEL_0 17
#define OBS_INV_0 (OBS_SEL_0+PLACEABLE_COUNT)
#define OBS_ACH_0 (OBS_INV_0+ITEM_COUNT)
#define OBS_ENTITY_0 (OBS_ACH_0+ACH_COUNT)
/* Visible cells: slime presence, bat presence, health, movement phase. */
#define OBS_STATUS (OBS_ENTITY_0+VIEW_CELLS*4)
#define OBS_INV_CLIP 999
typedef struct { uint8_t tile[VIEW_CELLS],light[VIEW_CELLS]; float status[OBS_STATUS]; } Obs;
typedef struct {
 const char *name; Item in_item[3]; int in_qty[3]; int n_in;
 int8_t out_item; int out_qty; uint8_t grant_tier; Tile station; int ach;
} Recipe;
#define RECIPE_COUNT 19
#define RECIPE_FIRST_ACTION ACT_CRAFT_WORKBENCH
static const Recipe RECIPES[RECIPE_COUNT] = {
 {"workbench",{ITEM_WOOD},{10},1,ITEM_WORKBENCH,1,0,TILE_AIR,ACH_CRAFT_WORKBENCH},
 {"furnace",{ITEM_STONE,ITEM_WOOD,ITEM_TORCH},{20,4,3},3,ITEM_FURNACE,1,0,TILE_WORKBENCH,ACH_CRAFT_FURNACE},
 {"torch x3",{ITEM_WOOD,ITEM_GEL},{1,1},2,ITEM_TORCH,3,0,TILE_AIR,-1},
 {"campfire",{ITEM_WOOD,ITEM_TORCH},{10,5},2,ITEM_CAMPFIRE,1,0,TILE_AIR,-1},
 {"platform x2",{ITEM_WOOD},{1},1,ITEM_PLATFORM,2,0,TILE_AIR,-1},
 {"copper bar",{ITEM_COPPER_ORE},{3},1,ITEM_COPPER_BAR,1,0,TILE_FURNACE,ACH_SMELT_COPPER},
 {"iron bar",{ITEM_IRON_ORE},{3},1,ITEM_IRON_BAR,1,0,TILE_FURNACE,ACH_SMELT_IRON},
 {"silver bar",{ITEM_SILVER_ORE},{4},1,ITEM_SILVER_BAR,1,0,TILE_FURNACE,ACH_SMELT_SILVER},
 {"gold bar",{ITEM_GOLD_ORE},{4},1,ITEM_GOLD_BAR,1,0,TILE_FURNACE,ACH_SMELT_GOLD},
 {"anvil",{ITEM_IRON_BAR},{5},1,ITEM_ANVIL,1,0,TILE_WORKBENCH,ACH_CRAFT_ANVIL},
 {"iron pickaxe",{ITEM_IRON_BAR,ITEM_WOOD},{10,3},2,-1,0,TIER_IRON_PICK,TILE_ANVIL,ACH_CRAFT_IRON_PICK},
 {"gold pickaxe",{ITEM_GOLD_BAR,ITEM_WOOD},{10,4},2,-1,0,TIER_GOLD_PICK,TILE_ANVIL,ACH_CRAFT_GOLD_PICK},
 {"wooden sword",{ITEM_WOOD},{7},1,ITEM_WOOD_SWORD,1,0,TILE_WORKBENCH,ACH_CRAFT_WOOD_SWORD},
 {"copper sword",{ITEM_COPPER_BAR},{6},1,ITEM_COPPER_SWORD,1,0,TILE_ANVIL,ACH_CRAFT_METAL_SWORD},
 {"iron sword",{ITEM_IRON_BAR},{8},1,ITEM_IRON_SWORD,1,0,TILE_ANVIL,ACH_CRAFT_METAL_SWORD},
 {"silver sword",{ITEM_SILVER_BAR},{7},1,ITEM_SILVER_SWORD,1,0,TILE_ANVIL,ACH_CRAFT_METAL_SWORD},
 {"gold sword",{ITEM_GOLD_BAR},{8},1,ITEM_GOLD_SWORD,1,0,TILE_ANVIL,ACH_CRAFT_METAL_SWORD},
 {"wood breastplate",{ITEM_WOOD},{30},1,ITEM_WOOD_ARMOR,1,0,TILE_WORKBENCH,ACH_CRAFT_WOOD_ARMOR},
 {"iron chainmail",{ITEM_IRON_BAR},{25},1,ITEM_IRON_ARMOR,1,0,TILE_ANVIL,ACH_CRAFT_IRON_ARMOR}
};
#define MAX_MOBS 8
#define MAX_CHESTS 10
typedef enum { MOB_NONE,MOB_BLUE_SLIME,MOB_CAVE_BAT } MobKind;
typedef struct { int x,y,hp,phase,jump,dir; uint8_t kind; } Mob;
typedef struct { int x,y; bool opened; int16_t loot[ITEM_COUNT]; } Chest;
typedef struct { int max_steps; } EnvConfig;
typedef struct Env {
 uint8_t tiles[WORLD_H][WORLD_W],light[WORLD_H][WORLD_W],terrain_light[WORLD_H][WORLD_W];
 uint8_t sky_cutoff[WORLD_W];
 bool terrain_dirty; int surface[WORLD_W];
 int px,py,facing,jump_left,fall_dist,health;
 uint8_t tool_tier; int16_t inv[ITEM_COUNT]; uint8_t selected;
 int max_health,weapon,armor,attack_cd,heal_cd,hurt_cd,mine_cd,safe_ticks;
 bool air_jump_used; int drop_ticks,explore_min,explore_max;
 bool mining_tree;
 Mob mobs[MAX_MOBS]; Chest chests[MAX_CHESTS]; int chest_count;
 uint32_t achievements; uint64_t rng,seed;
 int steps,max_steps; float reward,ep_return;
 bool terminated,truncated,light_dirty; char msg[64];
} Env;
void env_init(Env*,EnvConfig);
void env_reset(Env*,uint64_t);
void env_step(Env*,int);
void env_free(Env*);
void env_obs(const Env*,Obs*);
void env_action_mask(const Env*,uint8_t*);
void world_generate(Env*);
void light_recompute(Env*);
void light_tile_changed(Env*,int,int,Tile); /* exact incremental terrain lighting */
void light_reference(Env*); /* uncached oracle for parity tests */
const char *action_name(int);
static inline bool in_bounds(int x,int y) { return x>=0&&x<WORLD_W&&y>=0&&y<WORLD_H; }
static inline bool has_ach(const Env *e,int a) { return a>=0&&a<ACH_COUNT&&((e->achievements>>a)&1u); }
static inline Tile tile_at(const Env *e,int x,int y) { return in_bounds(x,y)?(Tile)e->tiles[y][x]:TILE_BEDROCK; }
static inline bool is_body(const Env *e,int x,int y) { return x>=e->px&&x<e->px+PLAYER_W&&y<=e->py&&y>e->py-PLAYER_H; }
static inline bool body_fits(const Env *e,int x,int feet) {
 if(x<0||x+PLAYER_W>WORLD_W||feet<PLAYER_H-1||feet>=WORLD_H) return false;
 for(int col=0;col<PLAYER_W;col++) for(int i=0;i<PLAYER_H;i++)
  if(tile_solid(tile_at(e,x+col,feet-i))) return false;
 return true;
}
static inline bool tile_supports(Tile t,bool dropping) { return tile_solid(t)||(!dropping&&tile_solid_top(t)); }
static inline bool player_grounded(const Env *e) {
 for(int col=0;col<PLAYER_W;col++) if(tile_supports(tile_at(e,e->px+col,e->py+1),e->drop_ticks!=0)) return true;
 return false;
}
static inline bool player_on_rope(const Env *e) {
 for(int col=0;col<PLAYER_W;col++) for(int row=0;row<PLAYER_H;row++)
  if(tile_at(e,e->px+col,e->py-row)==TILE_ROPE) return true;
 return false;
}
#endif
