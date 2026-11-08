/* Fixed taxonomy. Original Terraria asset IDs are distinct from simulator IDs. */
#ifndef TILES_H
#define TILES_H
#include <stdbool.h>
#include <stdint.h>
typedef enum {
 TILE_AIR,TILE_DIRT,TILE_GRASS,TILE_STONE,TILE_LOG,TILE_WOOD,TILE_LEAVES,
 TILE_COPPER_ORE,TILE_IRON_ORE,TILE_GOLD_ORE,TILE_TORCH,TILE_CAMPFIRE,
 TILE_WORKBENCH,TILE_FURNACE,TILE_ANVIL,TILE_BEDROCK,TILE_SILVER_ORE,
 TILE_PLATFORM,TILE_ROPE,TILE_CHEST,TILE_CHEST_OPEN,TILE_LIFE_CRYSTAL,
 TILE_MUSHROOM,TILE_COUNT
} Tile;
typedef enum {
 ITEM_WOOD,ITEM_STONE,ITEM_DIRT,ITEM_COPPER_ORE,ITEM_IRON_ORE,ITEM_GOLD_ORE,
 ITEM_COPPER_BAR,ITEM_IRON_BAR,ITEM_GOLD_BAR,ITEM_TORCH,ITEM_CAMPFIRE,
 ITEM_WORKBENCH,ITEM_FURNACE,ITEM_ANVIL,ITEM_SILVER_ORE,ITEM_SILVER_BAR,
 ITEM_GEL,ITEM_PLATFORM,ITEM_ROPE,ITEM_MUSHROOM,ITEM_LESSER_POTION,
 ITEM_LIFE_CRYSTAL,ITEM_CLOUD_BOTTLE,ITEM_COPPER_SHORTSWORD,ITEM_WOOD_SWORD,
 ITEM_COPPER_SWORD,ITEM_IRON_SWORD,ITEM_GOLD_SWORD,ITEM_SILVER_SWORD,ITEM_WOOD_ARMOR,
 ITEM_IRON_ARMOR,ITEM_IRON_PICK,ITEM_GOLD_PICK,ITEM_COUNT
} Item;
#define TIER_HAND 0
#define TIER_COPPER_PICK 1
#define TIER_IRON_PICK 2
#define TIER_GOLD_PICK 3
#define TIER_NEVER 255
typedef struct {
 const char *name; char glyph; bool solid,opaque; uint8_t min_tier; int8_t drop; uint8_t emit;
} TileInfo;
static const TileInfo TILE_INFO[TILE_COUNT] = {
 {"air",' ',false,false,255,-1,0},{"dirt",'#',true,true,0,ITEM_DIRT,0},
 {"grass",'"',true,true,0,ITEM_DIRT,0},{"stone",'%',true,true,0,ITEM_STONE,0},
 {"log",'|',false,false,0,ITEM_WOOD,0},{"wood",'=',true,true,0,ITEM_WOOD,0},
 {"leaves",'^',false,false,255,-1,0},
 {"copper ore",'c',true,true,1,ITEM_COPPER_ORE,0},
 {"iron ore",'i',true,true,1,ITEM_IRON_ORE,0},
 {"gold ore",'g',true,true,1,ITEM_GOLD_ORE,0},
 {"torch",'*',false,false,0,ITEM_TORCH,12},
 {"campfire",'O',false,false,0,ITEM_CAMPFIRE,12},
 {"workbench",'T',false,false,0,ITEM_WORKBENCH,0},
 {"furnace",'F',false,false,0,ITEM_FURNACE,0},{"anvil",'A',false,false,0,ITEM_ANVIL,0},
 {"bedrock",'X',true,true,255,-1,0},
 {"silver ore",'s',true,true,1,ITEM_SILVER_ORE,0},
 {"wood platform",'-',false,false,0,ITEM_PLATFORM,0},
 {"rope",':',false,false,0,ITEM_ROPE,0},
 {"chest",'C',false,false,255,-1,0},{"empty chest",'c',false,false,255,-1,0},
 {"life crystal",'H',false,false,1,ITEM_LIFE_CRYSTAL,0},
 {"mushroom",'m',false,false,0,ITEM_MUSHROOM,0}
};
static const char *const ITEM_NAME[ITEM_COUNT] = {
 "wood","stone","dirt","copper ore","iron ore","gold ore","copper bar",
 "iron bar","gold bar","torch","campfire","workbench","furnace","anvil",
 "silver ore","silver bar","gel","wood platform","rope","mushroom",
 "lesser healing potion","life crystal","Cloud in a Bottle","copper shortsword",
 "wooden sword","copper broadsword","iron broadsword","gold broadsword",
 "silver broadsword","wood breastplate","iron chainmail","iron pickaxe","gold pickaxe"
};
static const int ITEM_TERRARIA_ID[ITEM_COUNT] = {
 9,3,2,12,11,13,20,22,19,8,966,36,33,35,14,21,23,94,965,5,28,29,53,
 3507,24,3508,4,3520,3514,728,81,1,3521
};
#define WEAPON_COUNT 6
static const Item WEAPON_ITEM[WEAPON_COUNT] = {ITEM_COPPER_SHORTSWORD,ITEM_WOOD_SWORD,
 ITEM_COPPER_SWORD,ITEM_IRON_SWORD,ITEM_SILVER_SWORD,ITEM_GOLD_SWORD};
static const int WEAPON_DAMAGE[WEAPON_COUNT] = {5,7,9,12,14,15};
static const int ARMOR_DEFENSE[3] = {0,1,3};
static inline bool tile_solid(Tile t) { return TILE_INFO[t].solid; }
/* Terraria tables/benches/anvils are solid-top, not full collision blocks. */
static inline bool tile_solid_top(Tile t) { return t==TILE_PLATFORM||t==TILE_WORKBENCH||t==TILE_ANVIL; }
static inline bool tile_opaque(Tile t) { return TILE_INFO[t].opaque; }
static inline uint8_t tile_tier(Tile t) { return TILE_INFO[t].min_tier; }
static inline int8_t tile_drop(Tile t) { return TILE_INFO[t].drop; }
static inline uint8_t tile_emit(Tile t) { return TILE_INFO[t].emit; }
/* Shared logical footprints: original Terraria tiles, not inventory icon sizes. */
static inline int tile_object_w(Tile t) {
 switch(t) {
 case TILE_CAMPFIRE: case TILE_FURNACE: return 3;
 case TILE_WORKBENCH: case TILE_ANVIL: case TILE_CHEST:
 case TILE_CHEST_OPEN: case TILE_LIFE_CRYSTAL: return 2;
 default: return 1;
 }
}
static inline int tile_object_h(Tile t) {
 return t==TILE_CAMPFIRE||t==TILE_FURNACE||t==TILE_CHEST||t==TILE_CHEST_OPEN||t==TILE_LIFE_CRYSTAL?2:1;
}
typedef struct { Item item; Tile tile; } Placeable;
#define PLACEABLE_COUNT 10
static const Placeable PLACEABLES[PLACEABLE_COUNT] = {
 {ITEM_STONE,TILE_STONE},{ITEM_DIRT,TILE_DIRT},{ITEM_WOOD,TILE_WOOD},
 {ITEM_TORCH,TILE_TORCH},{ITEM_CAMPFIRE,TILE_CAMPFIRE},
 {ITEM_WORKBENCH,TILE_WORKBENCH},{ITEM_FURNACE,TILE_FURNACE},{ITEM_ANVIL,TILE_ANVIL},
 {ITEM_PLATFORM,TILE_PLATFORM},{ITEM_ROPE,TILE_ROPE}
};
#endif
