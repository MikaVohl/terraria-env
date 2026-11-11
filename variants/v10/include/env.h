/* Allocation-free deterministic simulator. All mutable state belongs to Env.
   v10 = v9 (docs/ENV_V9_DESIGN.md: 128x128 world with surface / underground /
   caverns / bedrock, day/night cycle, night mobs, Demon Altars, the Eye of
   Cthulhu) + the real-Terraria behaviour ports of variants/v8fid (D22) at 15
   game ticks per action (D23) + two tier-4 stepping stones (D24): 40 tiered
   achievements. Every [T] parameter is a compile-time knob below;
   variants/v10/README.md lists them with defaults. */
#ifndef ENV_H
#define ENV_H
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
/* Every player-visible message goes through here so the 64-byte buffer can
   never be overrun. */
#define SAY(e, ...) ((void)snprintf((e)->msg, sizeof (e)->msg, __VA_ARGS__))
#include "tiles.h"
#define ENV_STR_(x) #x
#define ENV_STR(x) ENV_STR_(x)
#define ENV_VERSION 10

/* ---- knobs: behaviour ports (D22, D23) ----------------------------------
   Each replaces one simplified mechanic with a behaviour port of Terraria
   1.4.4 (tModLoader 2026.08, decompiled; every port names its method).
   All default ON in v10; with all five 0 the game is v9's rules plus the
   two D24 achievements (build-v10-noport).
   FID_MOBS    real NPC AI on sub-tile fixed-point bodies: Blue Slime
               (aiStyle 1), Cave Bat (aiStyle 14), Zombie and Skeleton
               (aiStyle 3 fighters), Demon Eye (aiStyle 2); real stats.
   FID_COMBAT  damage variance, defense, crits, player i-frames, NPC hit
               immunity, knockback, sword swing/stab hitboxes (boss too).
   FID_PHYSICS fixed-point player movement (run, jump hold, gravity,
               20x42 px hitbox tile collision, step up/down, rope pulley).
   FID_MINING  pick power vs tile, hit counter (HitTile), tool use time.
   FID_TREES   forest tree heights 5-16 and per-tile wood with bonus wood. */
#ifndef FID_MOBS
#define FID_MOBS 1
#endif
#ifndef FID_COMBAT
#define FID_COMBAT 1
#endif
#ifndef FID_PHYSICS
#define FID_PHYSICS 1
#endif
#ifndef FID_MINING
#define FID_MINING 1
#endif
#ifndef FID_TREES
#define FID_TREES 1
#endif
/* Knobs that run in real 60 Hz game ticks: one agent action holds its input
   for FID_TICKS ticks (15: 1/4 s, about one copper-pickaxe swing), so a
   10,000-step episode is 2,500 s of game time. */
#define FID_TICKED (FID_MOBS||FID_COMBAT||FID_PHYSICS||FID_MINING)
#ifndef FID_TICKS
#define FID_TICKS 15
#endif
/* ---- knobs: tile rules (v10 polish, 2026-11-08) -------------------------
   Rule changes after the first v10 runs, also on by default; with both 0 a
   v10 build plays exactly like before them (and build-v10-noport like v9).
   TREE_LEAF_VISUAL  tree canopies and branch leaves are part of the tree
                     sprite, as in Terraria (Tree_Tops / Tree_Branches): the
                     world holds no TILE_LEAVES cells (the id and its
                     observation channel stay, always empty) and felling
                     clears none. Worldgen still reserves the canopy cells,
                     so every other cell equals TREE_LEAF_VISUAL=0's world.
   SUPPORT_RULES     tile anchors (TileObjectData; this world has no walls):
                     torches need a solid tile left, right or below; rope
                     hangs below a solid tile or rope; platforms need a solid
                     tile or platform beside them or a solid tile below;
                     furniture, stations, chests and life crystals need a
                     solid tile under every bottom cell (a workbench also
                     takes a platform); mushrooms a solid tile below.
                     Removing an anchor breaks the dependants into the
                     inventory (WorldGen.KillTile drops), rope chains and
                     all; the block under an unopened chest cannot be mined. */
#ifndef TREE_LEAF_VISUAL
#define TREE_LEAF_VISUAL 1
#endif
#ifndef SUPPORT_RULES
#define SUPPORT_RULES 1
#endif
/* ---- knobs: tools and walls (v10 fidelity, 2026-11-10) -------------------
   Three more Terraria 1.4.4 behaviours, default on; with all three 0 a v10
   build plays exactly as before them (build-v10-noport sets them 0).
   EXPLICIT_TOOLS  the pickaxe and the axe are items (Copper Pickaxe 3509 and
                   Copper Axe 3506 join ITEM_*; the crafted iron/gold pickaxes
                   already were). The episode starts with Terraria's starter
                   set (Copper Shortsword, Copper Pickaxe, Copper Axe); mining
                   power is the best pickaxe owned (no hidden tool tier); a
                   mine action auto-selects (Player.SmartSelect_GetToolStrategy:
                   axe for trunks, pickaxe otherwise) and Env.held records the
                   item in hand (observed); stacks hold 9,999 (Item.maxStack,
                   1.4.4), the observation saturates at OBS_INV_CLIP as before.
                   Default in tiles.h, where the item list depends on it.
   TOOL_DAMAGE     every pickaxe / axe use swings the item's useStyle 1 melee
                   hitbox with its real damage, knockBack and useAnimation
                   (Item.SetDefaults), hitting NPCs through the sword path
                   (immunity, variance, crits, knockback). Needs FID_COMBAT
                   and FID_MINING (the per-tick swing and tool time).
   BG_WALLS        a background wall per cell (Env.wall, Wall ids in tiles.h)
                   from worldgen's "Dirt Wall Backgrounds" and "Cave Walls"
                   passes plus cabin walls; mining never removes one. Blocks
                   need a solid tile, platform or rope beside, above or below,
                   or a wall behind them or a neighbour (Player.PlaceThing_
                   Tiles_BlockPlacementForAssortedThings); torches and
                   platforms may also hang on the wall behind them. */
#ifndef TOOL_DAMAGE
#define TOOL_DAMAGE (FID_COMBAT&&FID_MINING)
#endif
#if TOOL_DAMAGE && !(FID_COMBAT&&FID_MINING)
#error "TOOL_DAMAGE needs FID_COMBAT and FID_MINING"
#endif
#ifndef BG_WALLS
#define BG_WALLS 1
#endif
/* COMBO_ACTIONS: 15 extra actions appended after ACT_SUMMON that hold a
   movement input (left / right / jump, or left/right + jump) AND perform one
   use in the same 15-tick step, as a player holding a direction and the use
   button together. Attack and mine run exactly as their standalone actions
   (swing from the step start, mine held every tick); a place combo places at
   the step start when the standalone place would, else at the first tick its
   target cell takes the block (one per step: pillar while jumping). Legal iff
   the use is (place combos: the selected item is stocked; the two running
   jumps: iff jump is). Off by default: the 86 standalone actions and their
   behaviour are unchanged by it. */
#ifndef COMBO_ACTIONS
#define COMBO_ACTIONS 0
#endif
/* HELD_PLACE: every standalone place action (ACT_PLACE_FIRST .. +REACH_COUNT)
   holds the use button with the selected block for the whole 15-tick step,
   as Terraria's held use and the place combos: it places at the step start
   when that is legal (the result is then the old one), else after the first
   game tick where the target cell, relative to the body at that tick, takes
   the block; at most one block per step. A `place down` step after a jump
   step thus places under the falling feet once the cell below them touches
   the floor or the pillar top (the BG_WALLS-legal pillar, no wall needed).
   The place masks become "the selected placeable is stocked" (a held place
   may land on any tick).
   Needs the tick loop with ported physics; default on with FID_PHYSICS, so
   the noport control keeps v9's step-start place. HELD_PLACE=0 restores the
   step-start-only place (bit-identical to the build before the knob). */
#ifndef HELD_PLACE
#define HELD_PLACE FID_PHYSICS
#endif
#if HELD_PLACE && !FID_PHYSICS
#error "HELD_PLACE needs FID_PHYSICS (held inputs over the tick loop)"
#endif
/* AIM_ATTACK: attacks aim in 8 directions, as Terraria's cursor. `attack`
   (id unchanged) aims forward (the facing side); 7 appended actions after
   ACT_SUMMON aim up-forward, up, up-back, back, down-back, down and
   down-forward, relative to the facing at the action. The player first
   turns to the aim's side (back: turn around; up/down: keep the facing),
   then uses the weapon exactly as `attack`: the copper shortsword's stab
   (useStyle 13, Projectile AI_161_RapierStabs) flies along the aim's unit
   vector, centre = player centre + 2.1*dir*(ai0-1), and hits through
   Collision.CheckAABBvLineCollision(centre, centre + 6*velocity, width 10)
   (also forward: the exact segment test replaces the box approximation of
   the horizontal stab); broadswords swing their useStyle 1 arc on the
   chosen side. A use still running ignores the action (no turn). Masks: as
   `attack`. Needs FID_COMBAT; default on with it, so the noport control is
   unchanged. AIM_ATTACK=0: horizontal stabs only, bit-identical to the
   build before the knob. */
#ifndef AIM_ATTACK
#define AIM_ATTACK FID_COMBAT
#endif
#if AIM_ATTACK && !FID_COMBAT
#error "AIM_ATTACK needs FID_COMBAT (ported swings and the stab projectile)"
#endif
/* ENV_FX: the observational side channel Env.fx (hits, swing start, bodies
   per game tick) for the pixel frontend, which builds with ENV_FX=1. Never
   read by the game, so it cannot change a result; off by default because
   recording it costs training throughput (about 4%). */
#ifndef ENV_FX
#define ENV_FX 0
#endif
/* Fixed point: Q16.16 pixels (16 px per tile), as Terraria positions are px. */
typedef int32_t fix_t;
#define FIX_ONE 65536
#define FIXC(v) ((fix_t)((v)*65536.0+((v)<0?-0.5:0.5)))
#define TILE_FIX (16*FIX_ONE)

/* Mining tools, Item.SetDefaults (case 3509: SetDefaults1(1) then useTime
   15, pick 35, useAnimation 23, damage 4; case 1: useAnimation 20, useTime
   13, damage 5, pick 40, knockBack 2; case 3521: useTime 17, pick 55,
   useAnimation 20, damage 6; case 3506: SetDefaults1(10) then useTime 21,
   axe 7, useAnimation 30, damage 3, knockBack 4.5 from type 10). All are
   useStyle 1 with useTurn and autoReuse. Index = pick tier - 1, axe last
   (the pixel frontend's held-sprite order). */
enum { TOOL_COPPER_PICK, TOOL_IRON_PICK, TOOL_GOLD_PICK, TOOL_COPPER_AXE, TOOL_COUNT };
typedef struct { int terraria_id, pick, axe, use_time, use_anim, damage; fix_t knockback; } ToolInfo;
static const ToolInfo TOOL_INFO[TOOL_COUNT] = {
 {3509, 35, 0, 15, 23, 4, FIXC(2)},
 {1,    40, 0, 13, 20, 5, FIXC(2)},
 {3521, 55, 0, 17, 20, 6, FIXC(2)},
 {3506,  0, 7, 21, 30, 3, FIXC(4.5)},
};

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
/* Mob life / contact damage / defense. With FID_MOBS or FID_COMBAT the
   defaults are the real NPC.SetDefaults values (types 1, 49, 3, 2, 21);
   otherwise v9's. Defense only acts through FID_COMBAT's damage formula. */
#define FID_REAL_STATS (FID_MOBS||FID_COMBAT)
#ifndef SLIME_HP
#define SLIME_HP 25
#endif
#ifndef SLIME_DMG
#define SLIME_DMG 7
#endif
#ifndef SLIME_DEF
#define SLIME_DEF 2
#endif
#ifndef BAT_HP
#define BAT_HP 16
#endif
#ifndef BAT_DMG
#define BAT_DMG (FID_REAL_STATS?13:12)
#endif
#ifndef BAT_DEF
#define BAT_DEF 2
#endif
#ifndef ZOMBIE_HP
#define ZOMBIE_HP (FID_REAL_STATS?45:30)
#endif
#ifndef ZOMBIE_DMG
#define ZOMBIE_DMG (FID_REAL_STATS?14:10)
#endif
#ifndef ZOMBIE_DEF
#define ZOMBIE_DEF 6
#endif
#ifndef DEMON_EYE_HP
#define DEMON_EYE_HP (FID_REAL_STATS?60:30)
#endif
#ifndef DEMON_EYE_DMG
#define DEMON_EYE_DMG (FID_REAL_STATS?18:12)
#endif
#ifndef DEMON_EYE_DEF
#define DEMON_EYE_DEF 2
#endif
#ifndef SKELETON_HP
#define SKELETON_HP (FID_REAL_STATS?60:50)
#endif
#ifndef SKELETON_DMG
#define SKELETON_DMG (FID_REAL_STATS?20:16)
#endif
#ifndef SKELETON_DEF
#define SKELETON_DEF 8
#endif
#ifndef LENS_DROP_PCT
#define LENS_DROP_PCT 33
#endif

/* ---- knobs: Eye of Cthulhu (src/boss.c) ----------------------------------
   v9 tuned contact damage against its 8-step (120-tick at 15 ticks/step)
   hurt cooldown; FID_COMBAT's 40-tick i-frames let contact land 3x as often,
   so with it the defaults are 2/3 of v9's damage and the boss hovers 5 rows
   up (in reach of the 32x32-frame overhead swing) instead of 8. With these a
   scripted iron-gear fight wins >= 90% again (tests/selftest.c). [T] */
#ifndef EOC_HP
#define EOC_HP 240
#endif
#ifndef EOC_DMG1
#define EOC_DMG1 (FID_COMBAT?8:12)    /* contact damage, phase 1 */
#endif
#ifndef EOC_DMG2
#define EOC_DMG2 (FID_COMBAT?12:18)   /* contact damage, phase 2 (HP <= 50%) */
#endif
#ifndef EOC_DEF
/* Defense in FID_COMBAT's damage formula. The real EoC has 12, but v9 tuned
   EOC_HP (240 of the real 2800) against undefended hits, so v10 keeps 0. */
#define EOC_DEF 0
#endif
#ifndef EOC_HOVER_HEIGHT
#define EOC_HOVER_HEIGHT (FID_COMBAT?5:8) /* hover target: this many rows above the player's feet */
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
 ACT_SELECT_PLATFORM,ACT_SELECT_ROPE,ACT_SUMMON,
#if AIM_ATTACK
 ACT_ATTACK_UP_FORWARD,ACT_ATTACK_UP,ACT_ATTACK_UP_BACK,ACT_ATTACK_BACK,
 ACT_ATTACK_DOWN_BACK,ACT_ATTACK_DOWN,ACT_ATTACK_DOWN_FORWARD,
#endif
#if COMBO_ACTIONS
 ACT_LEFT_ATTACK,ACT_RIGHT_ATTACK,ACT_JUMP_ATTACK,ACT_JUMP_PLACE_DOWN,
 ACT_LEFT_MINE_HEAD_LEFT,ACT_LEFT_MINE_MIDDLE_LEFT,ACT_LEFT_MINE_FOOT_LEFT,
 ACT_RIGHT_MINE_HEAD_RIGHT,ACT_RIGHT_MINE_MIDDLE_RIGHT,ACT_RIGHT_MINE_FOOT_RIGHT,
 ACT_JUMP_MINE_UP,ACT_LEFT_JUMP_PLACE_DOWN_LEFT,ACT_RIGHT_JUMP_PLACE_DOWN_RIGHT,
 ACT_LEFT_JUMP,ACT_RIGHT_JUMP,
#endif
 ACT_COUNT
} Action;
#define ACT_SELECT_FIRST ACT_SELECT_STONE
#define ACT_MINE_FIRST ACT_MINE_UP_LEFT
#define ACT_PLACE_FIRST ACT_PLACE_UP_LEFT
#if AIM_ATTACK
/* Aim index 0 = ACT_ATTACK (forward), 1..7 = ACT_AIM_FIRST + i - 1. */
#define ACT_AIM_FIRST ACT_ATTACK_UP_FORWARD
#define AIM_COUNT 8
#endif
#if COMBO_ACTIONS
#if !FID_PHYSICS
#error "COMBO_ACTIONS needs FID_PHYSICS (held inputs)"
#endif
/* A combo: held movement bits plus the standalone action whose use it
   performs (ACT_NOOP: movement only). */
enum { COMBO_L = 1, COMBO_R = 2, COMBO_J = 4 };
typedef struct { uint8_t move; uint8_t use; } Combo;
#define ACT_COMBO_FIRST ACT_LEFT_ATTACK
#define COMBO_COUNT (ACT_COUNT - ACT_COMBO_FIRST)
static const Combo COMBOS[] = {
 {COMBO_L, ACT_ATTACK}, {COMBO_R, ACT_ATTACK}, {COMBO_J, ACT_ATTACK}, {COMBO_J, ACT_PLACE_DOWN},
 {COMBO_L, ACT_MINE_HEAD_LEFT}, {COMBO_L, ACT_MINE_MIDDLE_LEFT}, {COMBO_L, ACT_MINE_FOOT_LEFT},
 {COMBO_R, ACT_MINE_HEAD_RIGHT}, {COMBO_R, ACT_MINE_MIDDLE_RIGHT}, {COMBO_R, ACT_MINE_FOOT_RIGHT},
 {COMBO_J, ACT_MINE_UP}, {COMBO_L|COMBO_J, ACT_PLACE_DOWN_LEFT}, {COMBO_R|COMBO_J, ACT_PLACE_DOWN_RIGHT},
 {COMBO_L|COMBO_J, ACT_NOOP}, {COMBO_R|COMBO_J, ACT_NOOP},
};
_Static_assert(sizeof COMBOS / sizeof COMBOS[0] == COMBO_COUNT, "one Combo per combo action");
#endif

/* Section 8: 38 v9 achievements + D24's two tier-4 stepping stones, in four
   tiers (13/12/8/7, weights 1/3/5/8, max 145). The stepping stones:
   find a Demon Altar  a Demon Altar tile lies within crafting-station range
                       of the body (station_near: the square where the
                       Suspicious Looking Eye recipe works), at step end;
   hold N lenses       inventory holds >= EYE_LENSES lenses at step end. */
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
 ACH_CRAFT_GOLD_PICK,ACH_COLLECT_LENS,ACH_FIND_ALTAR,ACH_HOLD_LENSES,ACH_CRAFT_EYE,ACH_SUMMON_EOC,ACH_DEFEAT_EOC,
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
 "craft gold pickaxe","collect lens","find a Demon Altar","hold " ENV_STR(EYE_LENSES) " lenses",
 "craft Suspicious Looking Eye","summon the Eye of Cthulhu",
 "defeat the Eye of Cthulhu"
};
#define ACH_TIER_TABLE 1
static const uint8_t ACH_TIER[ACH_COUNT] = {
 1,1,1,1,1,1,1,1,1,1,1,1,1,
 2,2,2,2,2,2,2,2,2,2,2,2,
 3,3,3,3,3,3,3,3,
 4,4,4,4,4,4,4
};
#define TIER_COUNT 4
static const int TIER_WEIGHT[TIER_COUNT+1] = {0,1,3,5,8};
_Static_assert(ACH_COUNT==40,"section 8 achievement list + D24");
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
/* Fidelity scalars sit before the per-cell entity block (which consumers
   reshape to the end of the status vector): FID_PHYSICS adds sub-tile offset
   x/y and velocity x/y, FID_MINING the dig target's accumulated damage,
   EXPLICIT_TOOLS the held item (one-hot over ITEM_COUNT). */
#define OBS_FID_0 (OBS_MAP_0+(MINIMAP?MAP_CELLS*MAP_FEATURES:0))
#define OBS_SUB_X (OBS_FID_0)
#define OBS_SUB_Y (OBS_FID_0+1)
#define OBS_VEL_X (OBS_FID_0+2)
#define OBS_VEL_Y (OBS_FID_0+3)
#define OBS_DIG (OBS_FID_0+(FID_PHYSICS?4:0))
#define OBS_HELD_0 (OBS_DIG+(FID_MINING?1:0))
#define OBS_FID_COUNT ((FID_PHYSICS?4:0)+(FID_MINING?1:0)+(EXPLICIT_TOOLS?ITEM_COUNT:0))
#define OBS_ENTITY_0 (OBS_FID_0+OBS_FID_COUNT)
/* Visible cells: presence of Blue Slime, Cave Bat, Zombie, Demon Eye,
   Skeleton, Eye of Cthulhu; health fraction; movement phase; with BG_WALLS
   a ninth channel, 1 where the lit cell has a background wall. */
#define OBS_MOB_CHANNELS 8
#define OBS_WALL_CHANNEL OBS_MOB_CHANNELS
#define OBS_ENTITY_CHANNELS (OBS_MOB_CHANNELS+(BG_WALLS?1:0))
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
typedef struct { int x,y,hp,phase,jump,dir; uint8_t kind;
#if FID_MOBS
 /* NPC state in px (Q16): top-left position, velocity, the previous tick's
    velocity (NPC.oldVelocity), ai[0..2] counters, ai[3] (the slime's stored
    X in px; the fighters' stuck counter as a plain count), NPC.directionY,
    collideX/collideY of the last tile collision, spriteDirection (fighter
    jumps read it), still = position.X == oldPosition.X after the last move,
    hit = NPC.justHit. x,y stay the hitbox-centre cell for observation,
    despawn and grid code. */
 fix_t fx,fy,vx,vy,ovx,ovy,ai3; int ai0,ai1,ai2; int8_t diry,sdir; bool cx,cy,still,hit;
#endif
#if FID_COMBAT
 int immune; /* NPC.immune[player]: ticks before the player can hit it again */
#endif
} Mob;
/* Positional Mob literal of v9 (designated, so the fidelity fields start 0). */
#define MOB_INIT(X,Y,HP,PH,J,D,K) ((Mob){.x=(X),.y=(Y),.hp=(HP),.phase=(PH),.jump=(J),.dir=(D),.kind=(K)})
#if FID_MINING
/* Terraria HitTile slot: accumulated pick damage on a tile, decays as other
   tiles are hit (HitTile.Prune). Real buffer holds 500; 8 suffice here. */
typedef struct { int16_t x,y,damage,ttl; } HitSlot;
#define HIT_SLOTS 8
#endif
/* Eye of Cthulhu (src/boss.c). (x, y) is the top-left of its 3x3 body.
   immune: FID_COMBAT's per-swing NPC immunity, in ticks. */
typedef enum { BOSS_HOVER,BOSS_DASH,BOSS_PAUSE } BossMode;
typedef struct { bool active; uint8_t mode,dashes_left; int x,y,hp,timer,vx,vy,immune; } Boss;
typedef struct { int x,y; bool opened; int16_t loot[ITEM_COUNT]; } Chest;
/* Observational side channel for frontends and tools (Env.fx, ENV_FX=1): what this
   step's combat did and where the bodies were at every game tick. Cleared /
   overwritten by each env_step, written next to the events, never read by
   the simulation, the observation or the reward, so it cannot change a
   result. Hits: damage numbers and hit flashes (x, y: world px of the top
   centre of the struck body; tick: game tick within the step). path: hitbox
   top-left in world px of every mob slot and the player (index FX_PLAYER)
   before the first tick (row 0) and after each tick (FX_NONE: empty slot). */
enum { FX_TARGET_MOB, FX_TARGET_BOSS, FX_TARGET_PLAYER };
typedef struct { int16_t x,y,dmg; uint8_t tick,target,slot; bool crit; } FxHit;
#define FX_HITS 16
#define FX_PLAYER MAX_MOBS
#define FX_NONE INT16_MIN
typedef struct {
 /* swing: a use started this step, at game tick swing_tick, with the
    weapon (swing_tool -1) or TOOL_INFO[swing_tool] (TOOL_DAMAGE). */
 uint8_t tick,n_hits,swing_tick; bool swing; int8_t swing_tool; FxHit hit[FX_HITS];
#if FID_TICKED
 int16_t path[FID_TICKS+1][MAX_MOBS+1][2];
#endif
} EnvFx;
typedef struct { int max_steps; } EnvConfig;
typedef struct Env {
 uint8_t tiles[WORLD_H][WORLD_W],light[WORLD_H][WORLD_W],terrain_light[WORLD_H][WORLD_W];
 /* Row-major sub-tile frame index. No object entities or dynamic allocation;
    ordinary tiles remain unchanged, so the RL taxonomy/observation stays small. */
 uint8_t object_part[WORLD_H][WORLD_W];
 uint8_t sky_cutoff[WORLD_W];
 bool terrain_dirty; int surface[WORLD_W];
 int px,py,facing,jump_left,fall_dist,health;
#if EXPLICIT_TOOLS
 /* Player.HeldItem: the item in hand (Item id). Mining auto-selects a tool,
    attack takes the weapon, place/select the placeable. Mining power comes
    from the inventory (pick_tier), so there is no hidden tool tier. */
 uint8_t held;
#else
 uint8_t tool_tier;
#endif
 int16_t inv[ITEM_COUNT]; uint8_t selected;
 int max_health,weapon,armor,attack_cd,heal_cd,hurt_cd,mine_cd,safe_ticks;
 bool air_jump_used; int drop_ticks,explore_min,explore_max;
 bool mining_tree;
 Mob mobs[MAX_MOBS]; Boss boss; Chest chests[MAX_CHESTS]; int chest_count;
 uint64_t achievements; uint64_t rng,seed;
 int steps,max_steps; float reward,ep_return;
 bool terminated,truncated,light_dirty; char msg[64];
#if BG_WALLS
 /* Background wall per cell (Wall, tiles.h): set by worldgen, never removed
    in play (no hammer), so it needs no light or object bookkeeping. */
 uint8_t wall[WORLD_H][WORLD_W];
#endif
#if MINIMAP
 /* Explored map: cell seen, solid tile count, crafting station seen. */
 uint8_t map_seen[MAP_CELLS],map_solid[MAP_CELLS],map_station[MAP_CELLS];
#endif
#if FID_PHYSICS
 /* Player.position (top-left of the 20x42 px hitbox) and velocity in Q16 px.
    jump = Player.jump (held-jump ticks left), fall_start = Player.fallStart
    (tile row), pulley = on a rope. hold_* are this action's held inputs. */
 fix_t pos_x,pos_y,vel_x,vel_y; int jump,fall_start; bool release_jump,pulley;
 bool hold_left,hold_right,hold_jump,hold_down,hold_up;
#endif
#if FID_COMBAT
 /* Player.itemAnimation/itemAnimationMax/attackCD, immuneTime; stab_tick is
    the copper shortsword stab projectile's ai[0] (0 = none), stab_hits the
    mobs (bit i) and boss (bit MAX_MOBS) it already hit. kb_left/kb_dir:
    knockback still to apply to the grid player, one cell per action. */
 int item_anim,item_anim_max,attack_cd_ticks,immune_ticks,stab_tick,stab_dir,kb_left,kb_dir; uint32_t stab_hits;
#if AIM_ATTACK
 /* The stab's aim, a unit vector (Q16; diagonals 0.7071): its velocity is
    shootSpeed 2.1 times it. stab_dir stays the facing at the stab (the
    knockback side). */
 fix_t stab_ux,stab_uy;
#endif
#if TOOL_DAMAGE
 /* What the running itemAnimation swings: 0 the weapon, else TOOL_INFO
    index + 1 (a pickaxe / axe use). */
 uint8_t swing_tool;
#endif
#endif
#if FID_MINING
 int tool_time,dig_x,dig_y; HitSlot hits[HIT_SLOTS];
#endif
#if ENV_FX
 EnvFx fx; /* observational side channel, see EnvFx */
#endif
} Env;
/* Log one hit to the side channel (dropped once FX_HITS are taken). */
static inline void env_fx_hit(Env *e,int target,int slot,int x,int y,int dmg,bool crit) {
#if ENV_FX
 if(e->fx.n_hits>=FX_HITS) return;
 e->fx.hit[e->fx.n_hits++]=(FxHit){(int16_t)x,(int16_t)y,(int16_t)dmg,e->fx.tick,(uint8_t)target,(uint8_t)slot,crit};
#else
 (void)e;(void)target;(void)slot;(void)x;(void)y;(void)dmg;(void)crit;
#endif
}
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
/* Contact damage. dir: knockback direction (+-1, 0 none). Without FID_COMBAT:
   v9's armor rule and 8-step hurt cooldown; with it Player.Hurt (variance,
   defense/2, 40-tick i-frames, knockback). */
void env_hurt(Env*,int raw_damage,int dir,const char *who);
#if FID_COMBAT
_Static_assert(MAX_MOBS<32,"stab_hits bitset holds the mobs and the boss");
int env_damage_var(Env*,int dmg);              /* Main.DamageVar */
/* One tick of a sword swing (integer px box) / shortsword stab (Q16 box)
   against regular mobs and the boss; `anim` is itemAnimation (NPC immunity). */
void mobs_swing(Env*,int X,int Y,int W,int H,int damage,fix_t kb,int dir,int anim);
void mobs_stab(Env*,fix_t x0,fix_t y0,fix_t x1,fix_t y1,int damage,fix_t kb,int dir);
void boss_swing(Env*,int X,int Y,int W,int H,int damage,int anim);
void boss_stab(Env*,fix_t x0,fix_t y0,fix_t x1,fix_t y1,int damage);
void boss_contact(Env*);                        /* per tick: Player.Update_NPCCollision */
#endif
#if FID_TICKED
void mobs_game_tick(Env*);                      /* per 60 Hz tick: NPC contact, AI, immunity */
#endif
/* src/mobs.c: regular mobs. */
void mobs_tick(Env*);                         /* per action: spawn/despawn; without FID_MOBS also grid AI + contact */
void mobs_attack(Env*,int x0,int y0,int x1,int y1,int damage); /* player melee box */
void mobs_dawn(Env*);                         /* Demon Eyes leave at dawn */
#if FID_MOBS
void mobs_contact(Env*);                      /* per tick: Player.Update_NPCCollision */
#endif
void mobs_reset(Env*);                        /* after worldgen: FID_MOBS bodies for placed mobs */
void mob_place(Mob*,int kind,int hp,int x,int y); /* fresh mob standing in a cell (fixtures, tools) */
int mob_max_hp(int kind);
/* src/boss.c: Eye of Cthulhu. */
void boss_summon(Env*);
void boss_tick(Env*);                          /* per action: AI; contact damage unless FID_COMBAT (per tick) */
bool boss_attack(Env*,int x0,int y0,int x1,int y1,int damage); /* true if hit */
void boss_despawn(Env*,const char *why);
static inline bool in_bounds(int x,int y) { return x>=0&&x<WORLD_W&&y>=0&&y<WORLD_H; }
static inline bool has_ach(const Env *e,int a) { return a>=0&&a<ACH_COUNT&&((e->achievements>>a)&1u); }
static inline Tile tile_at(const Env *e,int x,int y) { return in_bounds(x,y)?(Tile)e->tiles[y][x]:TILE_BEDROCK; }
/* Mining power: the best pickaxe in the inventory (EXPLICIT_TOOLS), else
   v9's hidden tool tier. TIER_HAND: no pickaxe. */
static inline uint8_t pick_tier(const Env *e) {
#if EXPLICIT_TOOLS
 return e->inv[ITEM_GOLD_PICK]>0?TIER_GOLD_PICK:e->inv[ITEM_IRON_PICK]>0?TIER_IRON_PICK
      :e->inv[ITEM_COPPER_PICK]>0?TIER_COPPER_PICK:TIER_HAND;
#else
 return e->tool_tier;
#endif
}
/* Trunks need an axe (always owned without EXPLICIT_TOOLS: the hidden one). */
static inline bool has_axe(const Env *e) {
#if EXPLICIT_TOOLS
 return e->inv[ITEM_COPPER_AXE]>0;
#else
 (void)e; return true;
#endif
}
/* Auto Select (Player.SmartSelect_GetToolStrategy: tileAxe -> axe, else
   pickaxe): the TOOL_INFO entry a mine action on `t` uses. Terraria takes the
   first such item in inventory order; with no slot order the best pickaxe
   stands first. */
static inline int mine_tool(const Env *e, Tile t) {
 int tier=pick_tier(e);
 return t==TILE_LOG?TOOL_COPPER_AXE:tier>TIER_COPPER_PICK?tier-1:TOOL_COPPER_PICK;
}
#if EXPLICIT_TOOLS
static inline Item tool_item(int tool) {
 static const Item ITEMS[TOOL_COUNT]={ITEM_COPPER_PICK,ITEM_IRON_PICK,ITEM_GOLD_PICK,ITEM_COPPER_AXE};
 return ITEMS[tool];
}
#endif
static inline uint8_t wall_at(const Env *e,int x,int y) {
#if BG_WALLS
 return in_bounds(x,y)?e->wall[y][x]:(uint8_t)WALL_NONE;
#else
 (void)e;(void)x;(void)y; return WALL_NONE;
#endif
}
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
/* Player.width/height (px). The grid body is 2x3 cells; with FID_PHYSICS the
   real hitbox moves freely and px/py are derived anchors: px = left of the two
   columns nearest the hitbox centre, py = row of its bottom pixel. Without
   FID_PHYSICS, the fixed-point knobs place this hitbox centred on the body's
   columns and standing on its feet row. */
#define PLAYER_PX_W 20
#define PLAYER_PX_H 42
static inline fix_t player_fx(const Env *e) {
#if FID_PHYSICS
 return e->pos_x;
#else
 return (e->px*16+(PLAYER_W*16-PLAYER_PX_W)/2)*FIX_ONE;
#endif
}
static inline fix_t player_fy(const Env *e) {
#if FID_PHYSICS
 return e->pos_y;
#else
 return ((e->py+1)*16-PLAYER_PX_H)*FIX_ONE;
#endif
}
#if FID_PHYSICS
/* A cell overlaps the hitbox (WorldGen.PlaceTile's player check). */
static inline bool is_body(const Env *e,int x,int y) {
 fix_t cx=x*TILE_FIX,cy=y*TILE_FIX;
 return e->pos_x<cx+TILE_FIX && cx<e->pos_x+PLAYER_PX_W*FIX_ONE && e->pos_y<cy+TILE_FIX && cy<e->pos_y+PLAYER_PX_H*FIX_ONE;
}
#else
static inline bool is_body(const Env *e,int x,int y) { return x>=e->px&&x<e->px+PLAYER_W&&y<=e->py&&y>e->py-PLAYER_H; }
#endif
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
