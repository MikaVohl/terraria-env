/* Allocation-free deterministic simulator. All mutable state belongs to Env.
   v9 (docs/ENV_V9_DESIGN.md): 128x128 world with surface / underground /
   caverns / bedrock, day/night cycle, night mobs, Demon Altars, the Eye of
   Cthulhu and 38 tiered achievements. Every [T] parameter of the design is a
   compile-time knob below; variants/v9/README.md lists them with defaults. */
#ifndef ENV_H
#define ENV_H
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
/* Every player-visible message goes through here so the 64-byte buffer can
   never be overrun. */
#define SAY(e, ...) ((void)snprintf((e)->msg, sizeof (e)->msg, __VA_ARGS__))
#include "tiles.h"
#define ENV_VERSION 9

/* ---- knobs: world geometry (D6) ----------------------------------------- */
#ifndef WORLD_W
#define WORLD_W 128
#endif
#ifndef WORLD_H
#define WORLD_H 128           /* [T] depth 112-144 */
#endif
#ifndef CAVERN_Y
#define CAVERN_Y 64           /* first cavern row ("reach the caverns") */
#endif
#define SURFACE_BASE 30
#define SURFACE_MIN 22
#define SURFACE_MAX 38
#define DIRT_DEPTH 8
#define BEDROCK_ROWS 2
/* Gold lives in the lower half of the caverns. */
#define GOLD_MIN_Y ((CAVERN_Y+WORLD_H-BEDROCK_ROWS)/2)
/* v7/v8 name for the depth achievement row; v9's is the cavern row. */
#define DEEP_Y CAVERN_Y

/* ---- knobs: supply (D5) -------------------------------------------------- */
#ifndef ORE_DENSITY_PCT
#define ORE_DENSITY_PCT 100   /* vein counts: v7's per-row vein rate over each ore's v9 band */
#endif
#ifndef COPPER_MIN
#define COPPER_MIN 30
#endif
#ifndef IRON_MIN
#define IRON_MIN 140
#endif
#ifndef SILVER_MIN
#define SILVER_MIN 40
#endif
#ifndef GOLD_MIN
#define GOLD_MIN 60
#endif
#ifndef WOOD_MIN
#define WOOD_MIN 150          /* trunk tiles within WOOD_REACH columns of spawn */
#endif
#ifndef WOOD_REACH
#define WOOD_REACH 48
#endif
#ifndef ALTAR_MIN
#define ALTAR_MIN 2           /* worlds get ALTAR_MIN or ALTAR_MIN+1 altars */
#endif
#ifndef CRYSTAL_MIN
#define CRYSTAL_MIN 3         /* worlds get CRYSTAL_MIN..CRYSTAL_MIN+2 life crystals */
#endif
#ifndef TREE_HEIGHT_PCT
#define TREE_HEIGHT_PCT 200   /* trunk heights 8-12 before the wood guarantee */
#endif

/* ---- knobs: time (D7, D8) ------------------------------------------------ */
#ifndef EPISODE_STEPS
#define EPISODE_STEPS 10000
#endif
#ifndef DAY_STEPS
#define DAY_STEPS 1800
#endif
#ifndef NIGHT_STEPS
#define NIGHT_STEPS 1200
#endif
#ifndef NIGHT_SKY_LIGHT
#define NIGHT_SKY_LIGHT 3     /* sky light level at night (day: LIGHT_MAX) */
#endif
#define DAY_CYCLE (DAY_STEPS+NIGHT_STEPS)

/* ---- knobs: recipes (D16) ------------------------------------------------ */
#ifndef IRON_PICK_BARS
#define IRON_PICK_BARS 12
#endif
#ifndef GOLD_PICK_BARS
#define GOLD_PICK_BARS 12
#endif
#ifndef IRON_ARMOR_BARS
#define IRON_ARMOR_BARS 20
#endif
#ifndef GOLD_ARMOR_BARS
#define GOLD_ARMOR_BARS 25
#endif
#ifndef EYE_LENSES
#define EYE_LENSES 6
#endif

/* ---- knobs: mobs (section 5) --------------------------------------------- */
#ifndef MOB_CAP
#define MOB_CAP 12            /* regular mobs; the boss has its own slot */
#endif
#ifndef SPAWN_PERIOD
#define SPAWN_PERIOD 120      /* steps between spawn attempts (day surface, underground, caverns) */
#endif
#ifndef NIGHT_SPAWN_PERIOD
#define NIGHT_SPAWN_PERIOD 60 /* steps between spawn attempts on the surface at night */
#endif
#ifndef EYE_SPAWN_PCT
#define EYE_SPAWN_PCT 50      /* night surface spawns: Demon Eye, else Zombie */
#endif
#ifndef SKELETON_SPAWN_PCT
#define SKELETON_SPAWN_PCT 50 /* cavern spawns: Skeleton, else Cave Bat */
#endif
#ifndef SLIME_HP
#define SLIME_HP 25
#endif
#ifndef SLIME_DMG
#define SLIME_DMG 7
#endif
#ifndef BAT_HP
#define BAT_HP 16
#endif
#ifndef BAT_DMG
#define BAT_DMG 12
#endif
#ifndef ZOMBIE_HP
#define ZOMBIE_HP 30
#endif
#ifndef ZOMBIE_DMG
#define ZOMBIE_DMG 10
#endif
#ifndef DEMON_EYE_HP
#define DEMON_EYE_HP 30
#endif
#ifndef DEMON_EYE_DMG
#define DEMON_EYE_DMG 12
#endif
#ifndef SKELETON_HP
#define SKELETON_HP 50
#endif
#ifndef SKELETON_DMG
#define SKELETON_DMG 16
#endif
#ifndef LENS_DROP_PCT
#define LENS_DROP_PCT 33
#endif

/* ---- knobs: Eye of Cthulhu (src/boss.c) ---------------------------------- */
#ifndef EOC_HP
#define EOC_HP 240
#endif
#ifndef EOC_DMG1
#define EOC_DMG1 12           /* contact damage, phase 1 */
#endif
#ifndef EOC_DMG2
#define EOC_DMG2 18           /* contact damage, phase 2 (HP <= 50%) */
#endif
#ifndef EOC_HOVER_HEIGHT
#define EOC_HOVER_HEIGHT 8    /* hover target: this many rows above the player's feet */
#endif
#ifndef EOC_HOVER_TICKS1
#define EOC_HOVER_TICKS1 30
#endif
#ifndef EOC_HOVER_TICKS2
#define EOC_HOVER_TICKS2 15
#endif
#ifndef EOC_DASHES1
#define EOC_DASHES1 3
#endif
#ifndef EOC_DASHES2
#define EOC_DASHES2 5
#endif
#ifndef EOC_DASH_TICKS1
#define EOC_DASH_TICKS1 8
#endif
#ifndef EOC_DASH_TICKS2
#define EOC_DASH_TICKS2 6
#endif
#ifndef EOC_DASH_SPEED1
#define EOC_DASH_SPEED1 2     /* tiles per tick */
#endif
#ifndef EOC_DASH_SPEED2
#define EOC_DASH_SPEED2 3
#endif
#ifndef EOC_PAUSE_TICKS1
#define EOC_PAUSE_TICKS1 6    /* between consecutive dashes */
#endif
#ifndef EOC_PAUSE_TICKS2
#define EOC_PAUSE_TICKS2 3
#endif
#ifndef EOC_DEMONITE_MIN
#define EOC_DEMONITE_MIN 30
#endif
#ifndef EOC_DEMONITE_MAX
#define EOC_DEMONITE_MAX 87
#endif
#define EOC_SIZE 3

/* ---- knobs: observation (D9) --------------------------------------------- */
/* INV_LOG=1 adds ITEM_COUNT status entries log(1+count)/log(1+999) right after
   the achievement bits, so mid-range counts are legible. */
#ifndef INV_LOG
#define INV_LOG 0
#endif
/* MINIMAP=1 adds a coarse explored map (MAP_W x MAP_H cells of MINIMAP_CELL^2
   tiles; per cell: explored, solid fraction, station seen) to the status
   scalars, before the per-cell entity block. Prototype option, default off. */
#ifndef MINIMAP
#define MINIMAP 0
#endif
#ifndef MINIMAP_CELL
#define MINIMAP_CELL 8
#endif
#ifndef VIEW_W
#define VIEW_W 11
#endif
#ifndef VIEW_H
#define VIEW_H 9
#endif

#define PLAYER_W 2
#define PLAYER_H 3
#define MAX_HEALTH 100
#define HEALTH_CAP 400
#define FALL_SAFE 25
#define FALL_DMG_PER_TILE 10
#define JUMP_HEIGHT 6
#define STATION_RANGE 3
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
#define DEFAULT_MAX_STEPS EPISODE_STEPS
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
 ACT_CRAFT_GOLD_ARMOR,ACT_CRAFT_SUSPICIOUS_EYE,
 ACT_ATTACK,ACT_INTERACT,ACT_HEAL_POTION,ACT_EAT_MUSHROOM,ACT_USE_CRYSTAL,
 ACT_EQUIP_NEXT,ACT_CLIMB_UP,ACT_CLIMB_DOWN,ACT_DROP,
 ACT_SELECT_STONE,ACT_SELECT_DIRT,ACT_SELECT_WOOD,ACT_SELECT_TORCH,
 ACT_SELECT_CAMPFIRE,ACT_SELECT_WORKBENCH,ACT_SELECT_FURNACE,ACT_SELECT_ANVIL,
 ACT_SELECT_PLATFORM,ACT_SELECT_ROPE,ACT_SUMMON,ACT_COUNT
} Action;
#define ACT_SELECT_FIRST ACT_SELECT_STONE
#define ACT_MINE_FIRST ACT_MINE_UP_LEFT
#define ACT_PLACE_FIRST ACT_PLACE_UP_LEFT

/* Section 8: 38 achievements in four tiers (weights 1/3/5/8, max 129). */
typedef enum {
 /* tier 1 */
 ACH_COLLECT_WOOD,ACH_COLLECT_STONE,ACH_PLACE_BLOCK,ACH_PLACE_TORCH,ACH_PLACE_PLATFORM,
 ACH_CRAFT_WORKBENCH,ACH_CRAFT_WOOD_SWORD,ACH_COLLECT_COPPER,ACH_KILL_SLIME,ACH_OPEN_CHEST,
 ACH_EXPLORE,ACH_CLIMB,ACH_HEAL,
 /* tier 2 */
 ACH_CRAFT_FURNACE,ACH_SMELT_COPPER,ACH_COLLECT_IRON,ACH_SMELT_IRON,ACH_CRAFT_ANVIL,
 ACH_CRAFT_METAL_SWORD,ACH_CRAFT_WOOD_ARMOR,ACH_USE_CRYSTAL,ACH_KILL_ZOMBIE,ACH_KILL_DEMON_EYE,
 ACH_SURVIVE_NIGHT,ACH_REACH_CAVERNS,
 /* tier 3 */
 ACH_CRAFT_IRON_PICK,ACH_COLLECT_SILVER,ACH_SMELT_SILVER,ACH_COLLECT_GOLD,ACH_SMELT_GOLD,
 ACH_CRAFT_IRON_ARMOR,ACH_KILL_SKELETON,ACH_RETURN_SURFACE,
 /* tier 4 */
 ACH_CRAFT_GOLD_PICK,ACH_COLLECT_LENS,ACH_CRAFT_EYE,ACH_SUMMON_EOC,ACH_DEFEAT_EOC,
 ACH_COUNT
} Achievement;
static const char *const ACH_NAME[ACH_COUNT] = {
 "collect wood","collect stone","place block","place torch","place platform",
 "craft workbench","craft wooden sword","collect copper","defeat Blue Slime","open chest",
 "explore 30 columns","climb rope","heal with food or potion",
 "craft furnace","smelt copper","collect iron","smelt iron","craft anvil",
 "craft metal sword","craft wood breastplate","use life crystal","defeat Zombie","defeat Demon Eye",
 "survive a night","reach the caverns",
 "craft iron pickaxe","collect silver","smelt silver","collect gold","smelt gold",
 "craft iron chainmail","defeat Skeleton","return to surface",
 "craft gold pickaxe","collect lens","craft Suspicious Looking Eye","summon the Eye of Cthulhu",
 "defeat the Eye of Cthulhu"
};
#define ACH_TIER_TABLE 1
static const uint8_t ACH_TIER[ACH_COUNT] = {
 1,1,1,1,1,1,1,1,1,1,1,1,1,
 2,2,2,2,2,2,2,2,2,2,2,2,
 3,3,3,3,3,3,3,3,
 4,4,4,4,4
};
#define TIER_COUNT 4
static const int TIER_WEIGHT[TIER_COUNT+1] = {0,1,3,5,8};
_Static_assert(ACH_COUNT==38,"section 8 achievement list");
/* Preprocessor-visible mask width (ACH_COUNT is an enum): src/capi.c widens
   the native autoreset info rows for 64-bit masks. */
#define ACH_MASK_BITS 64
_Static_assert(ACH_COUNT<=ACH_MASK_BITS && ACH_COUNT>32,"achievement ABI is uint64");

_Static_assert(VIEW_W%2==1 && VIEW_H%2==1 && VIEW_W>=11 && VIEW_H>=9,"view is centred and at least v7's 11x9");
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
#define OBS_DAY_PHASE 17      /* position in the day/night cycle, 0 = dawn */
#define OBS_NIGHT 18
#define OBS_LAYER_0 19        /* one-hot: surface, underground, caverns */
#define OBS_BOSS 22           /* present, HP fraction, phase 2, dx/32, dy/32 (clipped) */
#define OBS_SEL_0 27
#define OBS_INV_0 (OBS_SEL_0+PLACEABLE_COUNT)
#define OBS_ACH_0 (OBS_INV_0+ITEM_COUNT)
#define OBS_INVLOG_0 (OBS_ACH_0+ACH_COUNT)
#define MAP_W (WORLD_W/MINIMAP_CELL)
#define MAP_H (WORLD_H/MINIMAP_CELL)
#define MAP_CELLS (MAP_W*MAP_H)
#define MAP_FEATURES 3
#define OBS_MAP_0 (OBS_INVLOG_0+(INV_LOG?ITEM_COUNT:0))
#define OBS_ENTITY_0 (OBS_MAP_0+(MINIMAP?MAP_CELLS*MAP_FEATURES:0))
/* Visible cells: presence of Blue Slime, Cave Bat, Zombie, Demon Eye,
   Skeleton, Eye of Cthulhu; health fraction; movement phase. */
#define OBS_ENTITY_CHANNELS 8
#define OBS_STATUS (OBS_ENTITY_0+VIEW_CELLS*OBS_ENTITY_CHANNELS)
#define OBS_INV_CLIP 999
typedef struct { uint8_t tile[VIEW_CELLS],light[VIEW_CELLS]; float status[OBS_STATUS]; } Obs;
typedef struct {
 const char *name; Item in_item[3]; int in_qty[3]; int n_in;
 int8_t out_item; int out_qty; uint8_t grant_tier; Tile station; int ach;
} Recipe;
#define RECIPE_COUNT 21
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
 {"iron pickaxe",{ITEM_IRON_BAR,ITEM_WOOD},{IRON_PICK_BARS,3},2,ITEM_IRON_PICK,1,TIER_IRON_PICK,TILE_ANVIL,ACH_CRAFT_IRON_PICK},
 {"gold pickaxe",{ITEM_GOLD_BAR,ITEM_WOOD},{GOLD_PICK_BARS,3},2,ITEM_GOLD_PICK,1,TIER_GOLD_PICK,TILE_ANVIL,ACH_CRAFT_GOLD_PICK},
 {"wooden sword",{ITEM_WOOD},{7},1,ITEM_WOOD_SWORD,1,0,TILE_WORKBENCH,ACH_CRAFT_WOOD_SWORD},
 {"copper sword",{ITEM_COPPER_BAR},{6},1,ITEM_COPPER_SWORD,1,0,TILE_ANVIL,ACH_CRAFT_METAL_SWORD},
 {"iron sword",{ITEM_IRON_BAR},{8},1,ITEM_IRON_SWORD,1,0,TILE_ANVIL,ACH_CRAFT_METAL_SWORD},
 {"silver sword",{ITEM_SILVER_BAR},{7},1,ITEM_SILVER_SWORD,1,0,TILE_ANVIL,ACH_CRAFT_METAL_SWORD},
 {"gold sword",{ITEM_GOLD_BAR},{8},1,ITEM_GOLD_SWORD,1,0,TILE_ANVIL,ACH_CRAFT_METAL_SWORD},
 {"wood breastplate",{ITEM_WOOD},{30},1,ITEM_WOOD_ARMOR,1,0,TILE_WORKBENCH,ACH_CRAFT_WOOD_ARMOR},
 {"iron chainmail",{ITEM_IRON_BAR},{IRON_ARMOR_BARS},1,ITEM_IRON_ARMOR,1,0,TILE_ANVIL,ACH_CRAFT_IRON_ARMOR},
 {"gold chainmail",{ITEM_GOLD_BAR},{GOLD_ARMOR_BARS},1,ITEM_GOLD_ARMOR,1,0,TILE_ANVIL,-1},
 {"suspicious looking eye",{ITEM_LENS},{EYE_LENSES},1,ITEM_SUSPICIOUS_EYE,1,0,TILE_DEMON_ALTAR,ACH_CRAFT_EYE}
};
_Static_assert(RECIPE_FIRST_ACTION+RECIPE_COUNT==ACT_ATTACK,"recipe actions are contiguous");

#define MAX_MOBS MOB_CAP
#define MAX_CHESTS 10
typedef enum { MOB_NONE,MOB_BLUE_SLIME,MOB_CAVE_BAT,MOB_ZOMBIE,MOB_DEMON_EYE,MOB_SKELETON,MOB_KINDS } MobKind;
typedef struct { int x,y,hp,phase,jump,dir; uint8_t kind; } Mob;
/* Eye of Cthulhu (src/boss.c). (x, y) is the top-left of its 3x3 body. */
typedef enum { BOSS_HOVER,BOSS_DASH,BOSS_PAUSE } BossMode;
typedef struct { bool active; uint8_t mode,dashes_left; int x,y,hp,timer,vx,vy; } Boss;
typedef struct { int x,y; bool opened; int16_t loot[ITEM_COUNT]; } Chest;
typedef struct { int max_steps; } EnvConfig;
typedef struct Env {
 uint8_t tiles[WORLD_H][WORLD_W],light[WORLD_H][WORLD_W],terrain_light[WORLD_H][WORLD_W];
 /* Row-major sub-tile frame index. No object entities or dynamic allocation;
    ordinary tiles remain unchanged, so the RL taxonomy/observation stays small. */
 uint8_t object_part[WORLD_H][WORLD_W];
 uint8_t sky_cutoff[WORLD_W];
 bool terrain_dirty; int surface[WORLD_W];
 int px,py,facing,jump_left,fall_dist,health;
 uint8_t tool_tier; int16_t inv[ITEM_COUNT]; uint8_t selected;
 int max_health,weapon,armor,attack_cd,heal_cd,hurt_cd,mine_cd,safe_ticks;
 bool air_jump_used; int drop_ticks,explore_min,explore_max;
 bool mining_tree;
 Mob mobs[MAX_MOBS]; Boss boss; Chest chests[MAX_CHESTS]; int chest_count;
 uint64_t achievements; uint64_t rng,seed;
 int steps,max_steps; float reward,ep_return;
 bool terminated,truncated,light_dirty; char msg[64];
#if MINIMAP
 /* Explored map: cell seen, solid tile count, crafting station seen. */
 uint8_t map_seen[MAP_CELLS],map_solid[MAP_CELLS],map_station[MAP_CELLS];
#endif
} Env;
void env_init(Env*,EnvConfig);
void env_reset(Env*,uint64_t);
void env_step(Env*,int);
void env_free(Env*);
void env_obs(const Env*,Obs*);
void env_action_mask(const Env*,uint8_t*);
void world_generate(Env*);
void light_recompute(Env*);   /* observation window + player glow (see light.c) */
void light_full(Env*);        /* whole map, for renderers and oracles */
void light_tile_changed(Env*,int,int,Tile); /* exact incremental terrain lighting */
void light_reference(Env*); /* uncached oracle for parity tests */
const char *action_name(int);
/* Shared by sim.c, mobs.c and boss.c. */
void env_award(Env*,int ach);
void env_give(Env*,int item,int qty);
void env_hurt(Env*,int raw_damage,const char *who);   /* contact damage: armor, hurt cooldown */
/* src/mobs.c: regular mobs. */
void mobs_tick(Env*);                         /* spawn attempt + per-kind AI + contact damage */
void mobs_attack(Env*,int x0,int y0,int x1,int y1,int damage); /* player melee box */
void mobs_dawn(Env*);                         /* Demon Eyes leave at dawn */
int mob_max_hp(int kind);
/* src/boss.c: Eye of Cthulhu. */
void boss_summon(Env*);
void boss_tick(Env*);                          /* AI + contact damage */
bool boss_attack(Env*,int x0,int y0,int x1,int y1,int damage); /* true if hit */
void boss_despawn(Env*,const char *why);
static inline bool in_bounds(int x,int y) { return x>=0&&x<WORLD_W&&y>=0&&y<WORLD_H; }
static inline bool has_ach(const Env *e,int a) { return a>=0&&a<ACH_COUNT&&((e->achievements>>a)&1u); }
static inline Tile tile_at(const Env *e,int x,int y) { return in_bounds(x,y)?(Tile)e->tiles[y][x]:TILE_BEDROCK; }
/* Day/night: episodes start at dawn; night is the last NIGHT_STEPS of each cycle. */
static inline int day_time(const Env *e) { return e->steps%DAY_CYCLE; }
static inline bool is_night(const Env *e) { return day_time(e)>=DAY_STEPS; }
static inline uint8_t sky_light(const Env *e) { return is_night(e)?NIGHT_SKY_LIGHT:LIGHT_MAX; }
/* 0 surface (sky and dirt band), 1 underground, 2 caverns. */
static inline int player_layer(const Env *e) {
 if(e->py>=CAVERN_Y) return 2;
 return e->py>e->surface[e->px]+DIRT_DEPTH?1:0;
}
static inline uint8_t cell_emit(const Env *e,int x,int y) {
 Tile t=tile_at(e,x,y);
 if(!tile_emit(t)) return 0;
 /* A larger emitter remains one light source at its bottom-left anchor. */
 if(tile_object_h(t)>1 && e->object_part[y][x]!=(tile_object_h(t)-1)*tile_object_w(t)) return 0;
 return tile_emit(t);
}
/* The selected target is the object's bottom-left anchor. Callers check empty
   space before placing; worldgen/fixtures clear their reserved rectangles. */
static inline bool env_object_write(Env *e,Tile t,int left,int bottom) {
 int w=tile_object_w(t),h=tile_object_h(t),top=bottom-h+1;
 if(!in_bounds(left,top)||!in_bounds(left+w-1,bottom)) return false;
 for(int row=0;row<h;row++) for(int col=0;col<w;col++) {
  int x=left+col,y=top+row;Tile before=tile_at(e,x,y);
  e->tiles[y][x]=(uint8_t)t;e->object_part[y][x]=(uint8_t)(row*w+col);
  light_tile_changed(e,x,y,before);
 }
 e->light_dirty=true;return true;
}
static inline void env_object_remove(Env *e,int x,int y) {
 Tile t=tile_at(e,x,y);int w=tile_object_w(t),h=tile_object_h(t);
 if(w==1&&h==1) {
  e->tiles[y][x]=TILE_AIR;e->object_part[y][x]=0;light_tile_changed(e,x,y,t);e->light_dirty=true;return;
 }
 int part=e->object_part[y][x];
 int left=x-part%w,top=y-part/w;
 for(int row=0;row<h;row++) for(int col=0;col<w;col++) {
  int cx=left+col,cy=top+row;
  if(in_bounds(cx,cy)&&tile_at(e,cx,cy)==t&&e->object_part[cy][cx]==row*w+col) {
   e->tiles[cy][cx]=TILE_AIR;e->object_part[cy][cx]=0;light_tile_changed(e,cx,cy,t);
  }
 }
 e->light_dirty=true;
}
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
