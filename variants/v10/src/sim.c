/* Game rules: action dispatch, player physics, crafting and episode bookkeeping.
   Regular mob AI lives in mobs.c, the Eye of Cthulhu in boss.c.
   v10: the FID_* blocks are the behaviour ports of variants/v8fid (each names
   the decompiled Terraria 1.4.4 method it follows); with every knob 0 the
   rules are v9's. */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "env.h"
#include "rng.h"
#include "fid.h"

/* Item.maxStack: 999 before Terraria 1.4.4, 9999 since (EXPLICIT_TOOLS
   brings 1.4.4's inventory). The observation saturates at OBS_INV_CLIP. */
#define INV_CAP (EXPLICIT_TOOLS ? 9999 : 999)

static const char *const ACTION_NAME[ACT_COUNT] = {
    "noop", "left", "right", "jump",
    "mine up-left",   "mine up",   "mine up-right",
    "mine head-left",              "mine head-right",
    "mine foot-left",              "mine foot-right",
    "mine down-left", "mine down", "mine down-right",
    "mine above right column","mine middle-left","mine middle-right","mine below right column",
    "mine body head-left","mine body head-right","mine body middle-left","mine body middle-right",
    "mine body foot-left","mine body foot-right",
    "place up-left",   "place up",   "place up-right",
    "place head-left",               "place head-right",
    "place foot-left",               "place foot-right",
    "place down-left", "place down", "place down-right",
    "place above right column","place middle-left","place middle-right","place below right column",
    "place body head-left","place body head-right","place body middle-left","place body middle-right",
    "place body foot-left","place body foot-right",
    "select next",
    "craft workbench","craft furnace","craft torch","craft campfire",
    "craft platforms","smelt copper","smelt iron","smelt silver","smelt gold",
    "craft anvil","craft iron pickaxe","craft gold pickaxe","craft wooden sword",
    "craft copper sword","craft iron sword","craft silver sword","craft gold sword",
    "craft wood breastplate","craft iron chainmail","craft gold chainmail",
    "craft Suspicious Looking Eye",
    "attack","open chest","drink healing potion","eat mushroom","use life crystal",
    "cycle weapon","climb up","climb down","drop through platform",
    "select stone","select dirt","select wood","select torch","select campfire",
    "select workbench","select furnace","select anvil","select platform","select rope",
    "use summon item",
#if AIM_ATTACK
    "attack up-forward","attack up","attack up-back","attack back",
    "attack down-back","attack down","attack down-forward",
#endif
#if COMBO_ACTIONS
    "left + attack","right + attack","jump + attack","jump + place down",
    "left + mine head-left","left + mine middle-left","left + mine foot-left",
    "right + mine head-right","right + mine middle-right","right + mine foot-right",
    "jump + mine up","left + jump + place down-left","right + jump + place down-right",
    "left + jump","right + jump",
#endif
};

/* ---- helpers ------------------------------------------------------------- */

/* Achievement unlocks are the only positive reward in the environment. The
   training reward stays +1 per unlock; the tier weights are evaluation only. */
void env_award(Env *e, int ach) {
    if (ach < 0 || ach >= ACH_COUNT) return;
    if (has_ach(e, ach)) return;
    e->achievements |= 1ull << ach;
    e->reward += 1.0f;
}
#define award env_award

void env_give(Env *e, int item, int qty) {
    int n = e->inv[item] + qty;
    e->inv[item] = (int16_t)(n > INV_CAP ? INV_CAP : n);
}
#define give env_give

/* Side channel (EnvFx, ENV_FX=1): FX_SET(...) writes it, compiled out
   otherwise; fx_player_hit logs damage taken at the top centre of the hitbox. */
#if ENV_FX
#define FX_SET(...) do { __VA_ARGS__; } while (0)
#else
#define FX_SET(...) ((void)0)
#endif
static void fx_player_hit(Env *e, int dmg) {
    env_fx_hit(e, FX_TARGET_PLAYER, 0, (int)(player_fx(e) >> 16) + PLAYER_PX_W / 2, (int)(player_fy(e) >> 16), dmg, false);
}

#if FID_COMBAT
/* Main.DamageVar: dmg * (1 + rand.Next(-15, 16) / 100), Math.Round (half to
   even), computed exactly in integers. */
int env_damage_var(Env *e, int dmg) {
    int v = dmg * (100 + rng_range(&e->rng, -15, 15)), q = v / 100, rem = v % 100;
    if (rem > 50 || (rem == 50 && (q & 1))) q++;
    return q;
}

/* Grid player knockback (no FID_PHYSICS): Player.Hurt sets velocity (4.5,
   -3.5); the FID_PHYSICS port carries that ~5 tiles on flat ground (v8fid
   fixture), applied here as one cell per action. */
#define FID_GRID_KB 5

/* Player.Hurt via HurtModifiers.GetDamage: (int)max(dmg - defense*0.5, 1);
   immuneTime 40 ticks (20 for 1 damage); knockback velocity (4.5*dir, -3.5)
   and fallStart reset. dir 0 = no knockback. */
void env_hurt(Env *e, int raw, int dir, const char *who) {
    if (e->immune_ticks > 0) return;
    int dmg = (2 * env_damage_var(e, raw) - ARMOR_DEFENSE[e->armor]) / 2;
    if (dmg < 1) dmg = 1;
    e->health -= dmg;
    fx_player_hit(e, dmg);
    e->immune_ticks = dmg == 1 ? 20 : 40;
    e->safe_ticks = 0;
    if (dir) {
#if FID_PHYSICS
        e->vel_x = FIXC(4.5) * dir; e->vel_y = FIXC(-3.5); e->fall_start = ftile(e->pos_y);
#else
        e->kb_left = FID_GRID_KB; e->kb_dir = dir;
#endif
    }
    SAY(e, "%s hit you (-%d hp)", who, dmg);
}
#else
/* Contact damage: Classic defense halves (rounded up) off the raw hit, at
   least 1, then the shared invulnerability window. */
void env_hurt(Env *e, int raw, int dir, const char *who) {
    (void)dir;
    if (e->hurt_cd) return;
    int damage = raw - (ARMOR_DEFENSE[e->armor] + 1) / 2;
    if (damage < 1) damage = 1;
    e->health -= damage;
    fx_player_hit(e, damage);
    e->hurt_cd = 8; e->safe_ticks = 0;
    SAY(e, "%s hit you (-%d hp)", who, damage);
}
#endif

#if !FID_PHYSICS
static inline bool grounded(const Env *e) {
    return player_grounded(e);
}
#endif

/* Chebyshev-radius search, so a station is usable from anywhere in the square
   around the player. tile_at() reports out-of-world cells as bedrock. */
static bool station_near(const Env *e, Tile want) {
    for (int dy = -PLAYER_H+1-STATION_RANGE; dy <= STATION_RANGE; dy++)
        for (int dx = -STATION_RANGE; dx < PLAYER_W+STATION_RANGE; dx++)
            if (tile_at(e, e->px + dx, e->py + dy) == want) return true;
    return false;
}

/* One exact neighborhood scan for all recipe masks, rather than repeating the
   same enlarged body-relative search for every station-dependent recipe. */
static uint32_t station_mask(const Env *e) {
    _Static_assert(TILE_COUNT<=32,"station bitset fits taxonomy");
    uint32_t found=0;
    for(int dy=-PLAYER_H+1-STATION_RANGE;dy<=STATION_RANGE;dy++)
        for(int dx=-STATION_RANGE;dx<PLAYER_W+STATION_RANGE;dx++)
            found|=1u<<tile_at(e,e->px+dx,e->py+dy);
    return found;
}

static const char *pick_name(uint8_t tier) {
    switch (tier) {
    case TIER_GOLD_PICK:   return "gold";
    case TIER_IRON_PICK:   return "iron";
    case TIER_COPPER_PICK: return "copper";
    default:               return "copper";
    }
}

static void award_collect(Env *e, Tile t) {
    switch (t) {
    case TILE_LOG:
    case TILE_WOOD:       award(e, ACH_COLLECT_WOOD);   break;
    case TILE_STONE:      award(e, ACH_COLLECT_STONE);  break;
    case TILE_COPPER_ORE: award(e, ACH_COLLECT_COPPER); break;
    case TILE_IRON_ORE:   award(e, ACH_COLLECT_IRON);   break;
    case TILE_GOLD_ORE:   award(e, ACH_COLLECT_GOLD);   break;
    case TILE_SILVER_ORE: award(e, ACH_COLLECT_SILVER); break;
    default: break;
    }
}

static void award_place(Env *e, Tile t) {
    switch (t) {
    case TILE_STONE:
    case TILE_DIRT:
    case TILE_WOOD:       award(e, ACH_PLACE_BLOCK);     break;
    case TILE_TORCH:      award(e, ACH_PLACE_TORCH);     break;
    case TILE_PLATFORM:  award(e, ACH_PLACE_PLATFORM); break;
    default: break;
    }
}

#if FID_MINING
/* Item.SetDefaults via TOOL_INFO (env.h): Copper Pickaxe 3509 (pick 35,
   useTime 15), Iron Pickaxe 1 (40, 13), Gold Pickaxe 3521 (55, 17); tier 0
   (no pickaxe, only reachable in v9 fixtures) mines like copper. Trees take
   the starting Copper Axe 3506 (axe 7 = 35%, useTime 21): (int)(7 * 1.2f) = 8. */
#define AXE_HIT (TOOL_INFO[TOOL_COPPER_AXE].axe * 12 / 10)

/* Player.GetPickaxeDamage for this tile set: dirt takes pick power twice,
   torches (tileNoFail), mushrooms (plants, tileNoFail) and rope (tileRope)
   break in one hit, everything else takes pick power. */
static int pick_damage(const Env *e, Tile t) {
    if (t == TILE_LOG) return AXE_HIT;
    if (t == TILE_TORCH || t == TILE_MUSHROOM || t == TILE_ROPE) return 100;
    int p = TOOL_INFO[mine_tool(e, t)].pick;
    return t == TILE_DIRT ? 2 * p : p;
}

static HitSlot *hit_find(Env *e, int x, int y) {
    for (int i = 0; i < HIT_SLOTS; i++)
        if (e->hits[i].ttl > 0 && e->hits[i].x == x && e->hits[i].y == y) return &e->hits[i];
    return NULL;
}

/* HitTile.AddDamage: refresh the slot's timeToLive to 60. A full buffer
   recycles the slot closest to expiry. */
static int hit_add(Env *e, int x, int y, int dmg) {
    HitSlot *s = hit_find(e, x, y);
    if (!s) {
        s = &e->hits[0];
        for (int i = 1; i < HIT_SLOTS; i++) if (e->hits[i].ttl < s->ttl) s = &e->hits[i];
        *s = (HitSlot){(int16_t)x, (int16_t)y, 0, 0};
    }
    s->damage = (int16_t)(s->damage + dmg);
    s->ttl = 60;
    return s->damage;
}

/* HitTile.Prune (run after every successful hit): age every slot, decay its
   damage by 2/5/7/10 once fewer than 48/36/24/12 hits of life remain. */
static void hit_prune(Env *e) {
    for (int i = 0; i < HIT_SLOTS; i++) {
        HitSlot *s = &e->hits[i];
        if (s->ttl <= 0) continue;
        if (s->ttl <= 1) { s->ttl = 0; continue; }
        s->ttl--;
        s->damage = (int16_t)(s->damage - (s->ttl < 12 ? 10 : s->ttl < 24 ? 7 : s->ttl < 36 ? 5 : s->ttl < 48 ? 2 : 0));
        if (s->damage < 0 || tile_at(e, s->x, s->y) == TILE_AIR) s->ttl = 0;
    }
}
#endif

#if BG_WALLS
/* ---- background walls (BG_WALLS) -----------------------------------------
   A wall at (x, y). In `mask` mode a dark cell counts, so the action mask
   never reveals hidden walls (or the terrain around them). */
static bool wall_anchor(const Env *e, int x, int y, bool mask) {
    if (!in_bounds(x, y)) return false;
    if (mask && e->light[y][x] < DARK_THRESHOLD) return true;
    return e->wall[y][x] != WALL_NONE;
}

/* Player.PlaceThing_Tiles_BlockPlacementForAssortedThings, final branch
   (plain blocks): legal when the tile right, left, below or above is active
   and tileSolid (platforms are), a beam or rope, or that neighbour has a
   wall; failing that, when the target itself has a wall. So blocks still
   build pillars and bridges from existing tiles, but never float in the sky. */
static bool block_anchored(const Env *e, int x, int y, bool mask) {
    static const int DX[4] = {1, -1, 0, 0}, DY[4] = {0, 0, 1, -1};
    for (int i = 0; i < 4; i++) {
        int nx = x + DX[i], ny = y + DY[i];
        if (mask && in_bounds(nx, ny) && e->light[ny][nx] < DARK_THRESHOLD) return true;
        Tile t = tile_at(e, nx, ny);
        if (tile_solid(t) || t == TILE_PLATFORM || t == TILE_ROPE || wall_at(e, nx, ny) != WALL_NONE) return true;
    }
    return wall_anchor(e, x, y, mask);
}
#endif
#if SUPPORT_RULES
/* ---- tile anchors (SUPPORT_RULES) ----------------------------------------
   TileObjectData anchors. Placement needs them; WorldGen.TileFrame's Check*
   calls break a tile that lost them and WorldGen.KillTile drops its item,
   here straight into the inventory as every mined drop. With BG_WALLS a
   torch (BlockPlacementForAssortedThings: `wall > 0` first) or a platform
   may also hang on the wall behind it; walls are never removed, so such a
   tile never loses that anchor. */

/* A solid tile (or a platform where `platform`) anchors. In `mask` mode a
   dark cell may hold anything and counts as an anchor, so the action mask
   never reveals hidden terrain. */
static bool anchor(const Env *e, int x, int y, bool mask, bool platform) {
    if (mask && in_bounds(x, y) && e->light[y][x] < DARK_THRESHOLD) return true;
    Tile t = tile_at(e, x, y);
    return tile_solid(t) || (platform && t == TILE_PLATFORM);
}

/* Does `t` with its bottom-left cell at (left, bottom) have an anchor? Torch:
   solid left, right or below (BG_WALLS: or a wall behind). Rope: solid tile
   or rope above. Platform: solid tile or platform beside it, or a solid tile
   below (BG_WALLS: or a wall behind). Mushroom: solid below. Furniture,
   stations, chests, life crystals: solid under every bottom cell (the
   workbench also stands on platforms). Blocks need nothing here (BG_WALLS
   checks them in do_place / can_place: block_anchored). */
static bool supported(const Env *e, Tile t, int left, int bottom, bool mask) {
    switch (t) {
    case TILE_TORCH:
        return anchor(e, left - 1, bottom, mask, false) || anchor(e, left + 1, bottom, mask, false)
            || anchor(e, left, bottom + 1, mask, false)
#if BG_WALLS
            || wall_anchor(e, left, bottom, mask)
#endif
            ;
    case TILE_ROPE:
        return anchor(e, left, bottom - 1, mask, false) || tile_at(e, left, bottom - 1) == TILE_ROPE;
    case TILE_PLATFORM:
        return anchor(e, left - 1, bottom, mask, true) || anchor(e, left + 1, bottom, mask, true)
            || anchor(e, left, bottom + 1, mask, false)
#if BG_WALLS
            || wall_anchor(e, left, bottom, mask)
#endif
            ;
    case TILE_MUSHROOM:
        return anchor(e, left, bottom + 1, mask, false);
    case TILE_WORKBENCH: case TILE_FURNACE: case TILE_ANVIL: case TILE_CAMPFIRE:
    case TILE_CHEST: case TILE_CHEST_OPEN: case TILE_LIFE_CRYSTAL:
        for (int c = 0; c < tile_object_w(t); c++)
            if (!anchor(e, left + c, bottom + 1, mask, t == TILE_WORKBENCH)) return false;
        return true;
    default:
        return true;
    }
}

static const char *support_need(Tile t) {
    switch (t) {
#if BG_WALLS
    case TILE_TORCH:    return "a solid block beside or below, or a wall behind";
    case TILE_ROPE:     return "a solid block or rope above";
    case TILE_PLATFORM: return "a block or platform beside, a block below, or a wall behind";
#else
    case TILE_TORCH:    return "a solid block beside or below";
    case TILE_ROPE:     return "a solid block or rope above";
    case TILE_PLATFORM: return "a block or platform beside, or a block below";
#endif
    default:            return "solid ground under it";
    }
}

/* What breaks when unanchored. Placed platforms stay (as in Terraria); an
   unopened chest never loses its support (its block cannot be mined). */
static bool breaks_unsupported(Tile t) {
    return t == TILE_TORCH || t == TILE_ROPE || t == TILE_MUSHROOM || t == TILE_WORKBENCH
        || t == TILE_FURNACE || t == TILE_ANVIL || t == TILE_CAMPFIRE || t == TILE_CHEST_OPEN
        || t == TILE_LIFE_CRYSTAL;
}

static void support_lost(Env *e, int x, int y);

/* Break the object covering (x, y) if it lost its anchor; then whatever it
   anchored in turn (rope chains). */
static void support_check(Env *e, int x, int y) {
    if (!in_bounds(x, y)) return;
    Tile t = tile_at(e, x, y);
    if (!breaks_unsupported(t)) return;
    int w = tile_object_w(t), h = tile_object_h(t), part = e->object_part[y][x];
    int left = x - part % w, bottom = y - part / w + h - 1;
    if (supported(e, t, left, bottom, false)) return;
    env_object_remove(e, x, y);
    if (tile_drop(t) >= 0) give(e, tile_drop(t), 1);
    for (int r = 0; r < h; r++) for (int c = 0; c < w; c++) support_lost(e, left + c, bottom - r);
}

/* Cell (x, y) no longer holds what it held: re-check its four neighbours. */
static void support_lost(Env *e, int x, int y) {
    support_check(e, x - 1, y); support_check(e, x + 1, y);
    support_check(e, x, y - 1); support_check(e, x, y + 1);
}
#endif

/* ---- phase 1: actions --------------------------------------------------- */

#if !FID_PHYSICS
static void do_move(Env *e, int dir) {
    e->facing = dir;

    int nx = e->px + dir;
    if (body_fits(e, nx, e->py)) {
        e->px = nx;
        return;
    }
    /* One-tile auto step-up. The whole body has to fit in the new column at the
       raised feet row, and the old column needs clearance above the head for
       the body to rise through -- otherwise you would scrape into a ceiling. */
    if (grounded(e) && body_fits(e, nx, e->py - 1)
                    && body_fits(e,e->px,e->py-1)) {
        e->px = nx;
        e->py -= 1;
        return;
    }
    if (!in_bounds(nx, e->py)) SAY(e, "the world ends here");
    else if (tile_solid(tile_at(e, nx, e->py)))
        SAY(e, "blocked by %s", TILE_INFO[tile_at(e, nx, e->py)].name);
    else
        SAY(e, "%s blocks your head", TILE_INFO[tile_at(e, nx, e->py - 1)].name);
}

static void do_jump(Env *e) {
    if (!grounded(e) && !(e->inv[ITEM_CLOUD_BOTTLE] && !e->air_jump_used)) {
        SAY(e, "already airborne");
        return;
    }
    /* Clearance is measured above the head, not above the feet. */
    if (!body_fits(e,e->px,e->py-1)) {
        SAY(e, "no headroom");
        return;
    }
    e->jump_left = JUMP_HEIGHT;
    e->fall_dist = 0;
    if (!grounded(e)) e->air_jump_used = true;   /* not scored in v9 */
}
#endif

/* The tools owned reach `t`: the axe for trunks, else a pickaxe of at least
   the tile's tier (EXPLICIT_TOOLS: and some pickaxe at all; v9's hidden
   tier 0 mined tier-0 tiles by hand). */
static bool tool_reaches(const Env *e, Tile t) {
    if (t == TILE_LOG) return has_axe(e);
#if EXPLICIT_TOOLS
    if (pick_tier(e) < TIER_COPPER_PICK) return false;
#endif
    return tile_tier(t) <= pick_tier(e);
}

/* With FID_MINING this is one tool hit (called whenever toolTime reaches 0
   while the mine action is held): Player.PickTile / the axe branch of
   ItemCheck_UseMiningTools_ActuallyUseMiningTool. Returns true when a tile
   was removed. */
static bool do_mine(Env *e, int r) {
#if !FID_MINING
    if (e->mine_cd) { SAY(e,"pickaxe cooling down"); return false; }
#endif
    int tx = e->px + REACH_DX[r];
    int ty = e->py + REACH_DY[r];

    if (!in_bounds(tx, ty)) {
        SAY(e, "nothing to mine");
        return false;
    }
    Tile t = tile_at(e, tx, ty);
    if (t == TILE_AIR) {
        SAY(e, "nothing to mine");
        return false;
    }
    if (tile_tier(t) == TIER_NEVER) {
        SAY(e, "%s is unbreakable", TILE_INFO[t].name);
        return false;
    }
    if (!tool_reaches(e, t)) {
        if (t == TILE_LOG) SAY(e, "need an axe");
        else SAY(e, "need a %s pickaxe", pick_name(tile_tier(t)));
        return false;
    }
    if(tile_solid(t)&&tile_at(e,tx,ty-1)==TILE_LOG) {
        SAY(e,"chop the tree before mining its ground"); return false;
    }
#if SUPPORT_RULES
    if(tile_solid(t)&&tile_at(e,tx,ty-1)==TILE_CHEST) {
        SAY(e,"the chest above is not empty"); return false;
    }
#endif

#if FID_MINING
    e->dig_x = tx; e->dig_y = ty;
    e->tool_time = TOOL_INFO[mine_tool(e, t)].use_time;
    if (hit_add(e, tx, ty, pick_damage(e, t)) < 100) {
        /* WorldGen.KillTile(fail: true) turns hit grass into dirt. */
        if (t == TILE_GRASS) { e->tiles[ty][tx] = TILE_DIRT; light_tile_changed(e, tx, ty, TILE_GRASS); }
        hit_prune(e);
        SAY(e, "hit %s (%d/100)", TILE_INFO[t].name, hit_find(e, tx, ty)->damage);
        return false;
    }
    hit_find(e, tx, ty)->ttl = 0;   /* ClearMiningCacheAt */
#endif
#if !FID_PHYSICS
    bool supported_before=grounded(e);
#endif
    e->mining_tree=t==TILE_LOG;
    int harvested_wood=0;
    if(t==TILE_LOG) {
        /* Severing a trunk removes its connected crown. Placed wood blocks
           retain ordinary one-cell mining. One wood per actual trunk cell. */
        int top=ty,wood=0;
        while(top>0 && e->tiles[top-1][tx]==TILE_LOG) top--;
        for(int y=top;y<=ty;y++) {
            e->tiles[y][tx]=TILE_AIR; light_tile_changed(e,tx,y,TILE_LOG); wood++;
        }
#if !TREE_LEAF_VISUAL
        /* Radius-two canopies cannot overlap another generated tree trunk. */
        for(int y=top-2;y<=top;y++) for(int x=tx-2;x<=tx+2;x++) {
            if(in_bounds(x,y) && e->tiles[y][x]==TILE_LEAVES) {
                e->tiles[y][x]=TILE_AIR; light_tile_changed(e,x,y,TILE_LEAVES);
            }
        }
#endif
#if FID_TREES
        /* WorldGen.KillTile_GetTreeDrops: each tree tile drops one wood, plus
           one if genRand.Next(100) < axe (Copper Axe: 7) or rand.Next(3) == 0.
           The trunk's branch tiles (GrowTree: 2 in 10 per side on every inner
           trunk tile, never on two consecutive tiles of a side) and, when the
           base is cut, its 1-2 roots fall with it; they are sampled here
           because the grid keeps single-column trunks. */
        int base=ty;
        while(base+1<WORLD_H && e->tiles[base+1][tx]==TILE_LOG) base++;
        int tree_tiles=wood; bool left=false,right=false;
        for(int y=top+1;y<=ty && y<base;y++) {
            int b=(int)rng_below(&e->rng,10);
            while(((b==5||b==7)&&left)||((b==6||b==7)&&right)) b=(int)rng_below(&e->rng,10);
            left=b==5||b==7; right=b==6||b==7;
            tree_tiles+=left+right;
        }
        if(ty==base) tree_tiles+=rng_below(&e->rng,3)==0?2:1;
        wood=0;
        for(int i=0;i<tree_tiles;i++)
            wood+=1+(rng_below(&e->rng,100)<7 || rng_below(&e->rng,3)==0);
#endif
        give(e,ITEM_WOOD,wood);
        harvested_wood=wood;
    } else {
        int ow = tile_object_w(t), oh = tile_object_h(t), part = e->object_part[ty][tx];
        int left = tx - part % ow, top = ty - part / ow;
        env_object_remove(e,tx,ty);
#if SUPPORT_RULES
        for (int r = 0; r < oh; r++) for (int c = 0; c < ow; c++) support_lost(e, left + c, top + r);
#else
        (void)left; (void)top; (void)oh;
#endif
    }
    e->light_dirty = true;
#if FID_MINING
    hit_prune(e);
#else
    e->mine_cd = t==TILE_LOG?3:4-pick_tier(e);
#endif

#if !FID_PHYSICS
    /* Lowering yourself one tile at a time is a controlled descent, not a fall;
       genuine falls into pre-existing voids must still hurt. Only the cell
       straight under the feet qualifies -- a diagonal dig does not drop you. */
    if (supported_before && REACH_DY[r]==1 && REACH_DX[r]>=0 && REACH_DX[r]<PLAYER_W) e->fall_dist = 0;
#endif

    int8_t drop = tile_drop(t);
    if (drop >= 0 && t!=TILE_LOG) give(e, drop, 1);
    award_collect(e, t);
    if(t==TILE_LOG) SAY(e,"felled tree (%d wood)",harvested_wood);
    else SAY(e, "mined %s", TILE_INFO[t].name);
    return true;
}

/* Blocks need no supporting neighbour on purpose: pillar-jumping upward and
   bridging across a chasm are both intended traversal tools (BG_WALLS: they
   need Terraria's neighbour-or-wall, which pillars and bridges have). With
   SUPPORT_RULES torches, rope, platforms and furniture need their anchors. */
static bool do_place(Env *e, int r) {
    Placeable p = PLACEABLES[e->selected];
    int tx = e->px + REACH_DX[r];
    int ty = e->py + REACH_DY[r];

#if EXPLICIT_TOOLS
    e->held = (uint8_t)p.item;
#endif
    if (e->inv[p.item] <= 0) {
        SAY(e, "no %s to place", ITEM_NAME[p.item]);
        return false;
    }
    if (!in_bounds(tx, ty)) {
        SAY(e, "cannot place outside the world");
        return false;
    }
    int w=tile_object_w(p.tile),h=tile_object_h(p.tile);
    if(!in_bounds(tx+w-1,ty-h+1)) { SAY(e,"object does not fit inside world");return false; }
    for(int row=0;row<h;row++) for(int col=0;col<w;col++) {
        int x=tx+col,y=ty-row;Tile t=tile_at(e,x,y);
        if(t!=TILE_AIR) { SAY(e,"%s is in the way",TILE_INFO[t].name);return false; }
        if(tile_solid(p.tile)&&is_body(e,x,y)) { SAY(e,"you are standing there");return false; }
    }
#if BG_WALLS
    if(tile_solid(p.tile)&&!block_anchored(e,tx,ty,false)) { SAY(e,"%s needs a tile beside it or a wall behind",TILE_INFO[p.tile].name);return false; }
#endif
#if SUPPORT_RULES
    if(!supported(e,p.tile,tx,ty,false)) { SAY(e,"%s needs %s",TILE_INFO[p.tile].name,support_need(p.tile));return false; }
#endif
    env_object_write(e,p.tile,tx,ty);
    e->inv[p.item]--;
    e->light_dirty = true;
    award_place(e, p.tile);
    SAY(e, "placed %s", TILE_INFO[p.tile].name);
    return true;
}

/* Skip past placeables the player cannot actually use, and never spin: after a
   full lap the original slot wins, and an empty inventory leaves the cursor
   alone rather than stepping it to a slot holding nothing. That last case used
   to advance `selected` pointlessly, which burned a tick and -- once the mask
   existed -- made `select next` claim to be useful when it was not. */
static void do_select(Env *e) {
    /* i == PLACEABLE_COUNT lands back on the current slot, so a lone stocked
       slot re-selects itself and nothing changes. */
    for (int i = 1; i <= PLACEABLE_COUNT; i++) {
        int cand = (e->selected + i) % PLACEABLE_COUNT;
        if (e->inv[PLACEABLES[cand].item] > 0) {
            e->selected = (uint8_t)cand;
#if EXPLICIT_TOOLS
            e->held = (uint8_t)PLACEABLES[cand].item;
#endif
            Item it = PLACEABLES[cand].item;
            SAY(e, "selected %s (%d)", ITEM_NAME[it], e->inv[it]);
            return;
        }
    }
    SAY(e, "nothing to select");
}

static void do_craft(Env *e, int idx) {
    const Recipe *r = &RECIPES[idx];

    if (r->station != TILE_AIR && !station_near(e, r->station)) {
        SAY(e, "need to be near %s %s",
            r->station == TILE_ANVIL ? "an" : "a", TILE_INFO[r->station].name);
        return;
    }
    for (int i = 0; i < r->n_in; i++) {
        if (e->inv[r->in_item[i]] < r->in_qty[i]) {
            SAY(e, "need %d more %s", r->in_qty[i] - e->inv[r->in_item[i]],
                ITEM_NAME[r->in_item[i]]);
            return;
        }
    }

    for (int i = 0; i < r->n_in; i++) e->inv[r->in_item[i]] -= (int16_t)r->in_qty[i];
    if (r->out_item >= 0) give(e, r->out_item, r->out_qty);
#if !EXPLICIT_TOOLS
    /* Ownership is independent of the strongest automatically used pick.
       Crafting iron after gold stays legal and never downgrades mining. */
    if (r->grant_tier > e->tool_tier) e->tool_tier = r->grant_tier;
#endif
    /* Crafting explicitly chooses this equipment, rather than auto-selecting
       the best item found in a chest. Weapon cycling can select weaker ones. */
    for (int i=0;i<WEAPON_COUNT;i++) if (r->out_item == (int)WEAPON_ITEM[i]) e->weapon=i;
    if (r->out_item==ITEM_WOOD_ARMOR) e->armor=1;
    if (r->out_item==ITEM_IRON_ARMOR) e->armor=2;
    if (r->out_item==ITEM_GOLD_ARMOR) e->armor=3;
    award(e, r->ach);
    SAY(e, "crafted %s", r->name);
}

/* ---- action validity ----------------------------------------------------- */

/* Physical/epistemic action legality, never a strategy filter. Turning matters
   to combat; empty-air attacks and full-health healing remain possible. Dark
   mining/placement attempts must not leak hidden terrain through the mask.
   Predicates mirror handler guards, with explicit tests in selftest_v2.c. */

#if FID_PHYSICS
/* Player.FindPulley looks for rope in the hitbox centre column; any row the
   hitbox spans (from 8 px above the head, as FindPulley) counts. */
static int ph_center_col(const Env *e) { return ftile(e->pos_x + (PLAYER_PX_W / 2) * FIX_ONE); }
static bool ph_rope_reach(const Env *e) {
    int col = ph_center_col(e), top = ftile(e->pos_y > 8 * FIX_ONE ? e->pos_y - 8 * FIX_ONE : 0);
    for (int y = top; y <= ftile(e->pos_y + (PLAYER_PX_H - 1) * FIX_ONE); y++)
        if (tile_at(e, col, y) == TILE_ROPE) return true;
    return false;
}
/* Standing (velocity.Y == 0) on a solid-top tile under any hitbox column. */
static bool ph_on_platform(const Env *e) {
    if (e->vel_y != 0) return false;
    int row = ftile(e->pos_y + PLAYER_PX_H * FIX_ONE);
    for (int x = ftile(e->pos_x); x <= ftile(e->pos_x + PLAYER_PX_W * FIX_ONE - 1); x++)
        if (tile_solid_top(tile_at(e, x, row))) return true;
    return false;
}
#else
static bool can_move(const Env *e, int dir) {
    if (e->facing != dir) return true; /* turning matters to melee combat */
    int nx = e->px + dir;
    if (body_fits(e, nx, e->py)) return true;
    return grounded(e) && body_fits(e, nx, e->py - 1)
                       && body_fits(e,e->px,e->py-1);
}

static bool can_jump(const Env *e) {
    return (grounded(e)||(e->inv[ITEM_CLOUD_BOTTLE]&&!e->air_jump_used))
        && body_fits(e,e->px,e->py-1);
}
#endif

static bool can_mine(const Env *e, int r) {
#if !FID_MINING
    if (e->mine_cd) return false;   /* FID_MINING: holding use accrues hits */
#endif
    int tx = e->px + REACH_DX[r], ty = e->py + REACH_DY[r];
    if (!in_bounds(tx, ty)) return false;
    Tile t = tile_at(e, tx, ty);
    /* Unknown cells permit attempts: the mask must not reveal hidden ore. */
    if (e->light[ty][tx] < DARK_THRESHOLD) return true;
    if (t == TILE_AIR) return false;
    if (tile_tier(t) == TIER_NEVER) return false;
    if(tile_solid(t)&&tile_at(e,tx,ty-1)==TILE_LOG) return false;
#if SUPPORT_RULES
    if(tile_solid(t)&&ty>0&&tile_at(e,tx,ty-1)==TILE_CHEST&&e->light[ty-1][tx]>=DARK_THRESHOLD) return false;
#endif
    return tool_reaches(e, t);
}

/* The place mask's legality (hidden cells permit attempts). HELD_PLACE takes
   it at the step start and along the step's predicted body path. */
static bool can_place(const Env *e, int r) {
    Placeable p = PLACEABLES[e->selected];
    int tx = e->px + REACH_DX[r], ty = e->py + REACH_DY[r];
    if (e->inv[p.item] <= 0)              return false;
    if (!in_bounds(tx, ty))               return false;
    int w=tile_object_w(p.tile),h=tile_object_h(p.tile);
    if(!in_bounds(tx+w-1,ty-h+1)) return false;
    for(int row=0;row<h;row++) for(int col=0;col<w;col++) {
        int x=tx+col,y=ty-row;
        /* Hidden occupied sub-cells still permit attempts, never disclose
           hidden terrain by asking whether a large object fits there. */
        if(e->light[y][x]>=DARK_THRESHOLD&&tile_at(e,x,y)!=TILE_AIR) return false;
        if(tile_solid(p.tile)&&is_body(e,x,y)) return false;
    }
#if BG_WALLS
    if(tile_solid(p.tile)&&!block_anchored(e,tx,ty,true)) return false;
#endif
#if SUPPORT_RULES
    return supported(e,p.tile,tx,ty,true);
#else
    return true;
#endif
}
#if HELD_PLACE
static void held_place_mask(const Env *e, uint8_t *mask);
#endif

/* Cycling only means something when a slot other than the current one holds
   stock; otherwise do_select lands back where it started. */
static bool can_select(const Env *e) {
    for (int i = 1; i < PLACEABLE_COUNT; i++) {
        int cand = (e->selected + i) % PLACEABLE_COUNT;
        if (e->inv[PLACEABLES[cand].item] > 0) return true;
    }
    return false;
}

static bool can_craft(const Env *e, int idx,uint32_t stations) {
    const Recipe *r = &RECIPES[idx];
    if (r->station != TILE_AIR && !(stations&(1u<<r->station))) return false;
    for (int i = 0; i < r->n_in; i++)
        if (e->inv[r->in_item[i]] < r->in_qty[i])              return false;
    return true;
}

static int nearby_chest(const Env *e) {
    for (int i=0;i<e->chest_count;i++) {
        const Chest *c=&e->chests[i];
        if(c->opened) continue;
        for(int row=0;row<2;row++) for(int col=0;col<2;col++) {
            int x=c->x+col,y=c->y-row;
            if(x>=e->px-1&&x<=e->px+PLAYER_W&&y>=e->py-PLAYER_H&&y<=e->py+1
               &&in_bounds(x,y)&&tile_at(e,x,y)==TILE_CHEST&&e->light[y][x]>=DARK_THRESHOLD) return i;
        }
    }
    return -1;
}

#if !FID_PHYSICS
static bool can_climb(const Env *e,int dir) {
    return player_on_rope(e) && body_fits(e,e->px,e->py+dir);
}
#endif

/* The Suspicious Looking Eye only works at night and with no boss alive. */
static bool can_summon(const Env *e) {
    return is_night(e) && e->inv[ITEM_SUSPICIOUS_EYE]>0 && !e->boss.active;
}

static bool can_equip(const Env *e) {
    for(int i=0;i<WEAPON_COUNT;i++) if(i!=e->weapon && e->inv[WEAPON_ITEM[i]]) return true;
    return false;
}

void env_action_mask(const Env *e, uint8_t *mask) {
    for (int a = 0; a < ACT_COUNT; a++) mask[a] = 0;

    /* Always legal, and the reason the mask is never empty: mid-fall there is
       frequently nothing else worth doing, and a policy still needs somewhere
       to put its probability mass. */
    mask[ACT_NOOP] = 1;
    if (e->terminated || e->truncated) return;

#if FID_PHYSICS
    /* Held inputs: running and turning are always possible; jump starts from
       the ground (velocity.Y == 0), with an unused cloud jump, or continues a
       held jump. */
    mask[ACT_LEFT] = mask[ACT_RIGHT] = 1;
    mask[ACT_JUMP] = e->jump > 0 || e->vel_y == 0 || (e->inv[ITEM_CLOUD_BOTTLE] && !e->air_jump_used);
#else
    mask[ACT_LEFT]        = (uint8_t)can_move(e, -1);
    mask[ACT_RIGHT]       = (uint8_t)can_move(e, +1);
    mask[ACT_JUMP]        = (uint8_t)can_jump(e);
#endif
    mask[ACT_SELECT_NEXT] = (uint8_t)can_select(e);
    for(int i=0;i<PLACEABLE_COUNT;i++)
        mask[ACT_SELECT_FIRST+i]=(uint8_t)(e->inv[PLACEABLES[i].item]>0);
#if FID_COMBAT
    mask[ACT_ATTACK] = e->item_anim == 0; /* a new swing once the last ends */
#if AIM_ATTACK
    for (int i = 0; i < AIM_COUNT - 1; i++) mask[ACT_AIM_FIRST + i] = mask[ACT_ATTACK];
#endif
#else
    mask[ACT_ATTACK] = e->attack_cd==0; /* legal even without a target */
#endif
    mask[ACT_INTERACT] = nearby_chest(e)>=0;
    mask[ACT_HEAL_POTION] = e->inv[ITEM_LESSER_POTION]>0 && !e->heal_cd;
    mask[ACT_EAT_MUSHROOM] = e->inv[ITEM_MUSHROOM]>0 && !e->heal_cd;
    mask[ACT_USE_CRYSTAL] = e->inv[ITEM_LIFE_CRYSTAL]>0 && e->max_health<HEALTH_CAP;
    mask[ACT_EQUIP_NEXT] = can_equip(e);
#if FID_PHYSICS
    mask[ACT_CLIMB_UP] = mask[ACT_CLIMB_DOWN] = e->pulley || ph_rope_reach(e);
    mask[ACT_DROP] = ph_on_platform(e);
#else
    mask[ACT_CLIMB_UP] = can_climb(e,-1);
    mask[ACT_CLIMB_DOWN] = can_climb(e,1);
    for(int col=0;col<PLAYER_W;col++) if(tile_solid_top(tile_at(e,e->px+col,e->py+1))) mask[ACT_DROP]=1;
#endif
    mask[ACT_SUMMON] = can_summon(e);

    for (int r = 0; r < REACH_COUNT; r++) {
        mask[ACT_MINE_FIRST  + r] = (uint8_t)can_mine(e, r);
        mask[ACT_PLACE_FIRST + r] = (uint8_t)can_place(e, r);
    }
#if HELD_PLACE
    held_place_mask(e, mask);
#endif
    uint32_t stations=station_mask(e);
    for (int i = 0; i < RECIPE_COUNT; i++)
        mask[RECIPE_FIRST_ACTION + i] = (uint8_t)can_craft(e, i,stations);
#if COMBO_ACTIONS
    /* Movement is always held; the use decides (a running jump: the jump).
       A held place may land on any tick, so it is legal whenever the
       selected item is stocked (as the standalone place's first check). */
    for (int i = 0; i < COMBO_COUNT; i++) {
        int u = COMBOS[i].use;
        mask[ACT_COMBO_FIRST + i] = u == ACT_NOOP ? mask[ACT_JUMP]
            : u >= ACT_PLACE_FIRST && u < ACT_PLACE_FIRST + REACH_COUNT ? (uint8_t)(e->inv[PLACEABLES[e->selected].item] > 0)
            : mask[u];
    }
#endif
}

/* ---- phase 2: physics --------------------------------------------------- */

/* Fall damage: v9's rule, which is Player.Update's (tiles fallen past 25, 10
   hp each, minus half defense rounded up). With FID_COMBAT it goes through
   Player.Hurt like the real game: no variance, fresh immuneTime. */
static void apply_fall(Env *e, int dist) {
    int dmg = (dist - FALL_SAFE) * FALL_DMG_PER_TILE;
#if FID_COMBAT
    dmg = (2*dmg - ARMOR_DEFENSE[e->armor]) / 2; if (dmg < 1) dmg = 1;
    e->immune_ticks = dmg == 1 ? 20 : 40;
#else
    /* Classic: floor(raw - defense/2), equivalent to ceil defense/2
       for integer raw damage. Preserve odd-defense protection. */
    dmg-=(ARMOR_DEFENSE[e->armor]+1)/2; if(dmg<1) dmg=1;
#endif
    e->health -= dmg;
    fx_player_hit(e, dmg);
    e->safe_ticks=0;
    e->reward += FALL_REWARD_PER_HP * (float)dmg;
    SAY(e, "fell %d tiles (-%d hp)", dist, dmg);
}

#if !FID_PHYSICS
/* Touching down: pay for the drop, then clear it. Split out of physics()
   because a fall now has to settle on the tick the feet arrive, from either
   branch below. */
static void land(Env *e) {
    if (e->fall_dist > FALL_SAFE) apply_fall(e, e->fall_dist);
    e->fall_dist = 0;
    e->air_jump_used = false;
}

static void physics(Env *e) {
#if FID_COMBAT
    /* Knockback carries the grid body one cell per action away from the hit. */
    if (e->kb_left > 0) {
        e->kb_left--;
        if (body_fits(e, e->px + e->kb_dir, e->py)) e->px += e->kb_dir; else e->kb_left = 0;
    }
#endif
    if (e->jump_left > 0) {
        /* Rising one tile per tick. The head leads, so a ceiling one row above
           the head is what ends the jump early. */
        if (body_fits(e,e->px,e->py-1)) {
            e->py--;
            e->jump_left--;
        } else {
            e->jump_left = 0;
        }
    } else if (player_on_rope(e)) {
        e->fall_dist=0;
    } else if (!grounded(e)) {
        e->py++;
        e->fall_dist++;
        /* Settle on the tick the feet arrive, not the one after. Deferring it
           left the player standing on the ground with fall_dist still live for
           a whole action, and mining the block underneath zeroes fall_dist as
           a controlled descent -- so a 39-tile drop cost nothing at all if you
           dug on landing. Same-tick settlement closes that window. */
        if (grounded(e)) land(e);
    } else {
        land(e);
    }

    /* The head must stay in the world, so the feet floor is PLAYER_H - 1. */
    if (e->py < PLAYER_H - 1) e->py = PLAYER_H - 1;
    if (e->py > WORLD_H - 1)  e->py = WORLD_H - 1;
}
#else
/* ---- FID_PHYSICS: Player.Update movement, one 60 Hz tick ----------------- */
/* Player defaults (Player.Update resets): gravity 0.4, maxFallSpeed 10,
   jumpHeight 15, jumpSpeed 5.01, maxRunSpeed = accRunSpeed 3,
   runAcceleration 0.08, runSlowdown 0.2. Cloud in a Bottle
   (CloudInABottleJump): duration 0.75 -> jump = (int)(15 * 0.75) = 11. */
#define PH_GRAVITY FIXC(0.4)
#define PH_MAX_FALL FIXC(10)
#define PH_JUMP_SPEED FIXC(5.01)
#define PH_JUMP_HEIGHT 15
#define PH_CLOUD_HEIGHT 11
#define PH_MAX_RUN FIXC(3)
#define PH_RUN_ACCEL FIXC(0.08)
#define PH_RUN_SLOW FIXC(0.2)

/* Grid anchors of the free hitbox (see env.h). */
static void ph_sync(Env *e) {
    int px = ((e->pos_x + (PLAYER_PX_W / 2 + 8) * FIX_ONE) >> 20) - 1;
    int py = (e->pos_y + PLAYER_PX_H * FIX_ONE - 1) >> 20;
    e->px = px < 0 ? 0 : px > WORLD_W - PLAYER_W ? WORLD_W - PLAYER_W : px;
    e->py = py < PLAYER_H - 1 ? PLAYER_H - 1 : py > WORLD_H - 1 ? WORLD_H - 1 : py;
}

/* Collision.StepDown: walking off a ledge 8-16 px high snaps onto the floor
   below instead of falling (runs when velocity.Y == gravity). */
static void ph_step_down(Env *e) {
    const fix_t W = PLAYER_PX_W * FIX_ONE, H = PLAYER_PX_H * FIX_ONE;
    fix_t nx = e->pos_x + e->vel_x, ny = (((e->pos_y + H) >> 20) << 20) - H;
    int x0 = ftile(nx), x1 = ftile(nx + W), row = ftile(ny + H + 4 * FIX_ONE);
    fix_t best = (row + PLAYER_PX_H / 16 + 1) * TILE_FIX;
    for (int i = x0; i <= x1; i++) for (int j = row; j <= row + 1; j++) {
        if (i < 1 || i >= WORLD_W - 1 || j < 1 || j >= WORLD_H - 1) continue;  /* InWorld(i, j, 1) */
        if (!fid_any_solid((Tile)e->tiles[j][i])) continue;
        fix_t bx = i * TILE_FIX, by = j * TILE_FIX - 17 * FIX_ONE;   /* FloatIntersect(i*16, j*16-17, 16, 16, ...) */
        if (!(bx > e->pos_x + W || by > e->pos_y + H || bx + TILE_FIX < e->pos_x || by + TILE_FIX < e->pos_y)
            && j * TILE_FIX < best) best = j * TILE_FIX;
    }
    fix_t d = best - (e->pos_y + H);
    if (d > 7 * FIX_ONE && d < 17 * FIX_ONE) e->pos_y = best - H;
}

/* Collision.StepUp: running into a one-tile step lifts the hitbox onto it
   when the column ahead has head room (runs when velocity.Y >= gravity and
   Down is not held). holds_up also allows stepping onto solid-top tiles. */
static void ph_step_up(Env *e, bool holds_up) {
    const int w = PLAYER_PX_W, h = PLAYER_PX_H, n = h / 16 + (h % 16 != 0);
    int dir = e->vel_x < 0 ? -1 : e->vel_x > 0 ? 1 : 0;
    fix_t nx = e->pos_x + e->vel_x, ny = e->pos_y;
    int col = ftile(nx + (w / 2) * FIX_ONE + (w / 2 + 1) * dir * FIX_ONE);
    int row = ftile(ny + (h - 1) * FIX_ONE);
    if (!in_bounds(col, row) || !in_bounds(col - dir, row - n)) return;
    for (int i = 1; i < n + 2; i++) if (!in_bounds(col, row - i)) return;
    bool clear = true;
    for (int j = 2; j < n + 1; j++) clear = clear && !fid_block(tile_at(e, col, row - j));
    bool clear_back = !fid_block(tile_at(e, col - dir, row - n));
    bool clear_step = !fid_block(tile_at(e, col, row - 1));
    Tile t = tile_at(e, col, row), above = tile_at(e, col, row - 1);
    bool step = fid_block(t) || (holds_up && tile_solid_top(t) && !fid_any_solid(above));
    step = step && !(tile_solid_top(t) && tile_solid_top(above));
    if (!(col * TILE_FIX < nx + w * FIX_ONE && col * TILE_FIX + TILE_FIX > nx)) return;
    if (!(step && clear_step && clear && clear_back)) return;
    fix_t top = row * TILE_FIX;
    if (!(top < ny + h * FIX_ONE)) return;
    if (ny + h * FIX_ONE - top <= FIXC(16.1)) e->pos_y = top - h * FIX_ONE;
}

/* One tick of Player.Update for this action's held inputs: rope (pulley),
   HorizontalMovement, JumpMovement, gravity, StepDown/StepUp, DryCollision
   (Collision.TileCollision with the 20x42 hitbox), world edges, fall damage. */
static void player_tick(Env *e) {
    const bool left = e->hold_left, right = e->hold_right, jump = e->hold_jump;
    const bool down = e->hold_down, up = e->hold_up;
    bool can_turn = true;
#if FID_COMBAT
    can_turn = e->item_anim == 0;   /* swords have useTurn = false */
#if TOOL_DAMAGE
    can_turn = can_turn || e->swing_tool;   /* pickaxes and the axe have useTurn */
#endif
#endif
    if (e->pulley && (left || right || jump || !ph_rope_reach(e))) e->pulley = false;
    if (!e->pulley && (up || down) && ph_rope_reach(e)) {
        /* Player.FindPulley: snap the hitbox onto the rope's centre column. */
        fix_t nx = (ph_center_col(e) * 16 + 8 - PLAYER_PX_W / 2) * FIX_ONE;
        if (!fid_solid_collision(e, nx, e->pos_y, PLAYER_PX_W, PLAYER_PX_H)) {
            e->pos_x = nx; e->vel_x = 0; e->pulley = true; e->jump = 0;
        }
    }
    if (e->pulley) {
        /* Player.Update pulley branch: climb only while rope continues above
           the head; no gravity. */
        int above = e->pos_y >= 16 * FIX_ONE ? ftile(e->pos_y - 16 * FIX_ONE) : -1;
        bool rope_up = above >= 0 && tile_at(e, ph_center_col(e), above) == TILE_ROPE;
        if (!rope_up && e->vel_y < 0) e->vel_y = 0;
        if (up && rope_up) {
            if (e->vel_y > 0) e->vel_y = fmul(e->vel_y, FIXC(0.7));
            e->vel_y -= e->vel_y > -3 * FIX_ONE ? FIXC(0.2) : FIXC(0.02);
            if (e->vel_y < -8 * FIX_ONE) e->vel_y = -8 * FIX_ONE;
        } else if (down) {
            if (e->vel_y < 0) e->vel_y = fmul(e->vel_y, FIXC(0.7));
            e->vel_y += e->vel_y < 3 * FIX_ONE ? FIXC(0.2) : FIXC(0.1);
            if (e->vel_y > PH_MAX_FALL) e->vel_y = PH_MAX_FALL;
        } else {
            e->vel_y = fmul(e->vel_y, FIXC(0.7));
            if (e->vel_y > -FIXC(0.1) && e->vel_y < FIXC(0.1)) e->vel_y = 0;
        }
        if (up || down) award(e, ACH_CLIMB);
        e->vel_x = 0;
    } else {
        /* HorizontalMovement */
        if (left && e->vel_x > -PH_MAX_RUN) {
            if (e->vel_x > PH_RUN_SLOW) e->vel_x -= PH_RUN_SLOW;
            e->vel_x -= PH_RUN_ACCEL;
            if (can_turn) e->facing = -1;
        } else if (right && e->vel_x < PH_MAX_RUN) {
            if (e->vel_x < -PH_RUN_SLOW) e->vel_x += PH_RUN_SLOW;
            e->vel_x += PH_RUN_ACCEL;
            if (can_turn) e->facing = 1;
        } else {
            fix_t slow = e->vel_y == 0 ? PH_RUN_SLOW : PH_RUN_SLOW / 2;
            if (e->vel_x > slow) e->vel_x -= slow;
            else if (e->vel_x < -slow) e->vel_x += slow;
            else e->vel_x = 0;
        }
        /* JumpMovement: a held jump keeps velocity.Y at -jumpSpeed for up to
           jumpHeight ticks; a new press needs the key released first. */
        if (jump) {
            if (e->jump > 0) {
                if (e->vel_y == 0) e->jump = 0;
                else { e->vel_y = -PH_JUMP_SPEED; e->jump--; }
            } else if (e->release_jump && (e->vel_y == 0 || (e->inv[ITEM_CLOUD_BOTTLE] && !e->air_jump_used))) {
                if (e->vel_y == 0) { e->air_jump_used = false; e->jump = PH_JUMP_HEIGHT; }
                else { e->air_jump_used = true; e->jump = PH_CLOUD_HEIGHT; }   /* not scored since v9 */
                e->vel_y = -PH_JUMP_SPEED;
            }
            e->release_jump = false;
        } else {
            e->jump = 0;
            e->release_jump = true;
        }
        e->vel_y += PH_GRAVITY;
        if (e->vel_y > PH_MAX_FALL) e->vel_y = PH_MAX_FALL;
    }
    if (e->vel_y == PH_GRAVITY) ph_step_down(e);
    if (e->vel_y >= PH_GRAVITY && !down) ph_step_up(e, up);
    FidHit hit;
    fid_tile_collision(e, e->pos_x, e->pos_y, &e->vel_x, &e->vel_y, PLAYER_PX_W, PLAYER_PX_H, down, false, &hit);
    if (hit.up) e->jump = 0;
    e->pos_x += e->vel_x;
    e->pos_y += e->vel_y;
    const fix_t max_x = (WORLD_W * 16 - PLAYER_PX_W) * FIX_ONE;
    if (e->pos_x < 0) { e->pos_x = 0; e->vel_x = 0; }
    if (e->pos_x > max_x) { e->pos_x = max_x; e->vel_x = 0; }
    if (e->pos_y < 0) { e->pos_y = 0; e->vel_y = 0; }
    /* Player.Update fall check: on landing, tiles from fallStart past 25. */
    if (e->vel_y == 0) {
        int dist = ftile(e->pos_y) - e->fall_start;
        if (dist > FALL_SAFE) apply_fall(e, dist);
        e->fall_start = ftile(e->pos_y);
        e->air_jump_used = false;
    }
    if (e->jump > 0 || e->pulley) e->fall_start = ftile(e->pos_y);
    int fallen = ftile(e->pos_y) - e->fall_start;
    e->fall_dist = fallen > 0 ? fallen : 0;
    ph_sync(e);
}
#if HELD_PLACE
/* HELD_PLACE mask: a held place is legal iff it is legal at the step start
   (can_place, already in mask) or after some tick of the step at the body's
   position then, where the held use retries it (env_step). A place step
   holds no movement, so that path is player_tick with no input from the
   current state. Mobs are ignored: a contact knockback in the real step can
   still make a masked-in place miss or a masked-out one land. The path runs
   on the body itself and every field player_tick writes is restored; fall
   damage stays out of reach (fall_start below the world each tick). A tick
   that changes nothing is a fixed point and ends the path. */
static void held_place_mask(const Env *ce, uint8_t *mask) {
    int open = 0;
    for (int r = 0; r < REACH_COUNT; r++) open += !mask[ACT_PLACE_FIRST + r];
    if (!open || ce->inv[PLACEABLES[ce->selected].item] <= 0) return;
    Env *e = (Env *)ce;   /* body fields only, all restored below */
    const fix_t pos_x = e->pos_x, pos_y = e->pos_y, vel_x = e->vel_x, vel_y = e->vel_y;
    const int px = e->px, py = e->py, jump = e->jump, fall_start = e->fall_start, fall_dist = e->fall_dist;
    const bool release_jump = e->release_jump, pulley = e->pulley, air_jump_used = e->air_jump_used;
    const bool hl = e->hold_left, hr = e->hold_right, hj = e->hold_jump, hd = e->hold_down, hu = e->hold_up;
    e->hold_left = e->hold_right = e->hold_jump = e->hold_down = e->hold_up = false;
    for (int t = 0; t < FID_TICKS && open; t++) {
        const fix_t x0 = e->pos_x, y0 = e->pos_y, vx0 = e->vel_x, vy0 = e->vel_y;
        const int j0 = e->jump;
        const bool rj0 = e->release_jump, pu0 = e->pulley, aj0 = e->air_jump_used;
        e->fall_start = WORLD_H + 1;
        player_tick(e);
        if (e->pos_x != x0 || e->pos_y != y0) {
            for (int r = 0; r < REACH_COUNT; r++)
                if (!mask[ACT_PLACE_FIRST + r] && can_place(e, r)) { mask[ACT_PLACE_FIRST + r] = 1; open--; }
        } else if (e->vel_x == vx0 && e->vel_y == vy0 && e->jump == j0 && e->release_jump == rj0
                   && e->pulley == pu0 && e->air_jump_used == aj0) break;
    }
    e->pos_x = pos_x; e->pos_y = pos_y; e->vel_x = vel_x; e->vel_y = vel_y;
    e->px = px; e->py = py; e->jump = jump; e->fall_start = fall_start; e->fall_dist = fall_dist;
    e->release_jump = release_jump; e->pulley = pulley; e->air_jump_used = air_jump_used;
    e->hold_left = hl; e->hold_right = hr; e->hold_jump = hj; e->hold_down = hd; e->hold_up = hu;
}
#endif
#endif

/* ---- API ---------------------------------------------------------------- */

#if !FID_COMBAT
/* Melee covers the body plus two cells ahead of the facing edge, over the
   body's rows. Regular mobs additionally need a clear line (mobs.c). */
static void do_attack(Env *e) {
    if(e->attack_cd) return;
    e->attack_cd=3; FX_SET(e->fx.swing=true);
    int x0=e->facing>0?e->px:e->px-2, x1=e->facing>0?e->px+PLAYER_W+1:e->px+PLAYER_W-1;
    int y0=e->py-PLAYER_H+1, y1=e->py, damage=WEAPON_DAMAGE[e->weapon];
    mobs_attack(e,x0,y0,x1,y1,damage);
    boss_attack(e,x0,y0,x1,y1,damage);
}
#else
/* FID_COMBAT values from Item.SetDefaults (types 3507, 24, 3508, 4, 3514,
   3520; WEAPON_ITEM order): useAnimation and knockBack. Damage is
   WEAPON_DAMAGE, already the real value. The copper shortsword (useStyle 13)
   attacks only through its stab projectile; the others are useStyle 1
   broadsword swings. */
static const int FID_USE_ANIM[WEAPON_COUNT] = {13, 20, 21, 20, 20, 18};
static const fix_t FID_KNOCKBACK[WEAPON_COUNT] = {FIXC(4), FIXC(5), FIXC(5.5), FIXC(5.5), FIXC(6), FIXC(6.5)};
#define FID_STAB_SPEED FIXC(2.1)  /* Copper Shortsword shootSpeed */
#define FID_STAB_TICKS 16         /* Projectile AI_161_RapierStabs: Kill() at ai[0] >= 16 */

/* Player.ItemCheck: a use starts itemAnimation = useAnimation; the copper
   shortsword also spawns its stab projectile (ai[0] counts from 1). */
#if AIM_ATTACK
/* Aims relative to the facing (env.h): forward x and down y of the unit
   vector, index 0 = ACT_ATTACK, 1..7 = ACT_AIM_FIRST... */
#define AIM_DIAG 46341   /* sqrt(1/2) in Q16 */
static const fix_t AIM_FX[AIM_COUNT] = {FIX_ONE, AIM_DIAG, 0, -AIM_DIAG, -FIX_ONE, -AIM_DIAG, 0, AIM_DIAG};
static const fix_t AIM_FY[AIM_COUNT] = {0, -AIM_DIAG, -FIX_ONE, -AIM_DIAG, 0, AIM_DIAG, FIX_ONE, AIM_DIAG};
/* The player turns to the cursor's side when the use starts (Player
   direction; up/down keep it), then the stab flies along the aim. */
static void attack_start(Env *e, int aim) {
    if (e->item_anim > 0) return;
    const fix_t ux = AIM_FX[aim] * e->facing;
    if (ux) e->facing = ux > 0 ? 1 : -1;
#else
static void attack_start(Env *e) {
    if (e->item_anim > 0) return;
#endif
    e->item_anim = e->item_anim_max = FID_USE_ANIM[e->weapon];
    FX_SET(e->fx.swing = true; e->fx.swing_tick = e->fx.tick; e->fx.swing_tool = -1);
#if TOOL_DAMAGE
    e->swing_tool = 0;
#endif
#if AIM_ATTACK
    if (e->weapon == 0) { e->stab_tick = 1; e->stab_dir = e->facing; e->stab_hits = 0; e->stab_ux = ux; e->stab_uy = AIM_FY[aim]; }
#else
    if (e->weapon == 0) { e->stab_tick = 1; e->stab_dir = e->facing; e->stab_hits = 0; }
#endif
}

#if TOOL_DAMAGE
/* A pickaxe / axe use (Player.ItemCheck with the auto-selected tool, which
   has autoReuse): itemAnimation = the tool's useAnimation; its useStyle 1
   swing then hits NPCs every tick like a sword (swing_tick). */
static void tool_swing_start(Env *e, int tool) {
    e->item_anim = e->item_anim_max = TOOL_INFO[tool].use_anim;
    e->swing_tool = (uint8_t)(tool + 1);
#if EXPLICIT_TOOLS
    e->held = (uint8_t)tool_item(tool);
#endif
    FX_SET(e->fx.swing = true; e->fx.swing_tick = e->fx.tick; e->fx.swing_tool = (int8_t)tool);
}
#endif

/* One tick of ItemCheck melee: ItemCheck_GetMeleeHitbox for useStyle 1 with
   the dedicated-server 32x32 item frame (itemLocation from
   ItemCheck_ApplyUseStyle: overhead, forward, low thirds of the swing), then
   ItemCheck_MeleeHitNPCs (mobs.c / boss.c). The stab is Projectile
   AI_161_RapierStabs: centre = player centre + 2.1*dir*(ai0-1), colliding
   along 6 velocity steps with width 10 (as a box), one hit per NPC. With
   TOOL_DAMAGE a pickaxe / axe swing takes the same useStyle 1 box with the
   tool's damage and knockBack (TOOL_INFO). */
static void swing_tick(Env *e) {
    const fix_t ppx = player_fx(e), ppy = player_fy(e);
    const int dir = e->facing;
    int damage = WEAPON_DAMAGE[e->weapon];
    fix_t knockback = FID_KNOCKBACK[e->weapon];
    bool swings = e->weapon > 0;
#if TOOL_DAMAGE
    if (e->swing_tool) {
        damage = TOOL_INFO[e->swing_tool - 1].damage;
        knockback = TOOL_INFO[e->swing_tool - 1].knockback;
        swings = true;
    }
#endif
    if (e->item_anim > 0 && swings) {
        const int anim = e->item_anim, max = e->item_anim_max;
        const int phase = anim * 1000 < max * 333 ? 2 : anim * 1000 < max * 666 ? 1 : 0;
        const fix_t cx = ppx + (PLAYER_PX_W / 2) * FIX_ONE;
        const fix_t lx = phase == 0 ? cx - 10 * FIX_ONE * dir : cx + 6 * FIX_ONE * dir;
        const fix_t ly = ppy + (phase == 2 ? 24 : 10) * FIX_ONE;
        int X = lx >> 16, Y = ly >> 16, W = 32, H = 32;
        if (dir == -1) X -= W;
        Y -= H;
        if (phase == 2) { if (dir == -1) X -= 12; W = 44; Y += 16; H = 35; }
        else if (phase == 0) { if (dir == 1) X -= 38; W = 64; Y -= 12; H = 44; }
        mobs_swing(e, X, Y, W, H, damage, knockback, dir, anim);
        boss_swing(e, X, Y, W, H, damage, anim);
    }
    if (e->stab_tick > 0) {
        const int sd = e->stab_dir;
#if AIM_ATTACK
        /* Centre = player centre + velocity*(ai0-1); mobs_stab / boss_stab
           take the segment centre .. centre + 6*velocity (fid_line_hits). */
        const fix_t vx = fmul(FID_STAB_SPEED, e->stab_ux), vy = fmul(FID_STAB_SPEED, e->stab_uy);
        fix_t ax = ppx + (PLAYER_PX_W / 2) * FIX_ONE + vx * (e->stab_tick - 1);
        fix_t ay = ppy + (PLAYER_PX_H / 2) * FIX_ONE + vy * (e->stab_tick - 1);
        mobs_stab(e, ax, ay, ax + 6 * vx, ay + 6 * vy, WEAPON_DAMAGE[0], FID_KNOCKBACK[0], sd);
        boss_stab(e, ax, ay, ax + 6 * vx, ay + 6 * vy, WEAPON_DAMAGE[0]);
#else
        fix_t a = ppx + (PLAYER_PX_W / 2) * FIX_ONE + FID_STAB_SPEED * (e->stab_tick - 1) * sd;
        fix_t b = a + FID_STAB_SPEED * 6 * sd;
        fix_t x0 = (a < b ? a : b) - 5 * FIX_ONE, x1 = (a < b ? b : a) + 5 * FIX_ONE;
        fix_t y0 = ppy + (PLAYER_PX_H / 2 - 5) * FIX_ONE, y1 = y0 + 10 * FIX_ONE;
        mobs_stab(e, x0, y0, x1, y1, WEAPON_DAMAGE[0], FID_KNOCKBACK[0], sd);
        boss_stab(e, x0, y0, x1, y1, WEAPON_DAMAGE[0]);
#endif
        if (++e->stab_tick >= FID_STAB_TICKS) e->stab_tick = 0;
    }
    if (e->item_anim > 0) e->item_anim--;
    if (e->attack_cd_ticks > 0) e->attack_cd_ticks--;
}
#endif

static void do_interact(Env *e) {
    int i=nearby_chest(e);
    if(i<0) return;
    Chest *c=&e->chests[i]; c->opened=true;
    for(int k=0;k<ITEM_COUNT;k++) give(e,k,c->loot[k]);
    env_object_write(e,TILE_CHEST_OPEN,c->x,c->y);
    e->light_dirty=true;
    award(e,ACH_OPEN_CHEST); SAY(e,"chest looted (check inventory)");
}

static void do_heal(Env *e,Item item,int amount) {
    if(e->heal_cd || !e->inv[item]) return;
    int before=e->health;
    e->inv[item]--; e->health+=amount;
    if(e->health>e->max_health) e->health=e->max_health;
    e->heal_cd=60;
    if(e->health>before) award(e,ACH_HEAL);
    SAY(e,"%s (+%d hp)",ITEM_NAME[item],e->health-before);
}

#if MINIMAP
/* ---- explored map (MINIMAP=1) -------------------------------------------- */
static void map_count_solid(Env *e,int c) {
    int x0=(c%MAP_W)*MINIMAP_CELL,y0=(c/MAP_W)*MINIMAP_CELL,n=0;
    for(int y=y0;y<y0+MINIMAP_CELL;y++) for(int x=x0;x<x0+MINIMAP_CELL;x++) n+=tile_solid((Tile)e->tiles[y][x]);
    e->map_solid[c]=(uint8_t)n;
}
static bool is_station(Tile t) {
    return t==TILE_WORKBENCH||t==TILE_FURNACE||t==TILE_ANVIL||t==TILE_DEMON_ALTAR;
}
/* Cells overlapping the view window become explored; their solid count is
   taken when first explored and again after the player edits tiles there.
   Stations count as seen when lit inside the view. */
static void map_update(Env *e,bool edited) {
    int x0=e->px-VIEW_W/2,x1=e->px+VIEW_W/2,y0=e->py-VIEW_H/2,y1=e->py+VIEW_H/2;
    if(x0<0) x0=0;
    if(y0<0) y0=0;
    if(x1>WORLD_W-1) x1=WORLD_W-1;
    if(y1>WORLD_H-1) y1=WORLD_H-1;
    for(int cy=y0/MINIMAP_CELL;cy<=y1/MINIMAP_CELL;cy++) for(int cx=x0/MINIMAP_CELL;cx<=x1/MINIMAP_CELL;cx++) {
        int c=cy*MAP_W+cx;
        if(!e->map_seen[c]) { e->map_seen[c]=1; map_count_solid(e,c); }
        else if(edited) map_count_solid(e,c);
    }
    for(int y=y0;y<=y1;y++) for(int x=x0;x<=x1;x++)
        if(e->light[y][x]>=DARK_THRESHOLD && is_station((Tile)e->tiles[y][x]))
            e->map_station[(y/MINIMAP_CELL)*MAP_W+x/MINIMAP_CELL]=1;
}
#endif

#if FID_TICKED
/* One real tick in Main.DoUpdate order: Player.Update (immunity, movement,
   NPC contact, ItemCheck: sword and pickaxe), then every NPC. mine_r is the
   reach slot held this action (-1: none). Returns true if a tile was mined. */
static bool fid_tick(Env *e, int mine_r) {
    bool edited = false;
    (void)mine_r;
#if FID_COMBAT
    if (e->immune_ticks > 0) e->immune_ticks--;
#endif
#if FID_PHYSICS
    player_tick(e);
#endif
#if FID_COMBAT
    boss_contact(e);
#endif
#if FID_MOBS
    mobs_contact(e);
#endif
#if TOOL_DAMAGE
    /* A held mine action uses the auto-selected tool whenever no use is
       running (autoReuse); a sword use still running holds it back, as one
       item is in hand at a time. Tool hits need that tool's use running. */
    int tool = -1;
    if (mine_r >= 0) {
        tool = mine_tool(e, tile_at(e, e->px + REACH_DX[mine_r], e->py + REACH_DY[mine_r]));
        if (e->item_anim == 0) tool_swing_start(e, tool);
    }
    const bool tool_in_use = e->item_anim > 0 && e->swing_tool == tool + 1;
#endif
#if FID_COMBAT
    swing_tick(e);
#endif
#if FID_MINING
    if (e->tool_time > 0) e->tool_time--;
#if TOOL_DAMAGE
    if (mine_r >= 0 && e->tool_time == 0 && tool_in_use) edited = do_mine(e, mine_r);
#else
    if (mine_r >= 0 && e->tool_time == 0) edited = do_mine(e, mine_r);
#endif
#endif
    mobs_game_tick(e);   /* NPCs after the player: AI + movement, immunity */
#if FID_COMBAT
    if (e->boss.immune > 0) e->boss.immune--;
#endif
    return edited;
}

/* Side channel (EnvFx.path): every body's hitbox top-left after `row` ticks. */
static void fx_path(Env *e, int row) {
#if !ENV_FX
    (void)e; (void)row;
#else
    int16_t (*p)[2] = e->fx.path[row];
    for (int i = 0; i < MAX_MOBS; i++) {
        const Mob *m = &e->mobs[i];
        if (!m->kind) { p[i][0] = p[i][1] = FX_NONE; continue; }
#if FID_MOBS
        p[i][0] = (int16_t)(m->fx >> 16); p[i][1] = (int16_t)(m->fy >> 16);
#else
        p[i][0] = (int16_t)(m->x * 16); p[i][1] = (int16_t)(m->y * 16);
#endif
    }
    p[FX_PLAYER][0] = (int16_t)(player_fx(e) >> 16); p[FX_PLAYER][1] = (int16_t)(player_fy(e) >> 16);
#endif
}
#endif

void env_init(Env *e, EnvConfig cfg) {
    memset(e, 0, sizeof *e);
    e->max_steps = cfg.max_steps > 0 ? cfg.max_steps : DEFAULT_MAX_STEPS;
}

/* SplitMix64 finalizer. Feeding a raw counter straight into the LCG would give
   adjacent seeds near-identical first draws, and so near-identical worlds. */
static uint64_t seed_mix(uint64_t x) {
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}

void env_reset(Env *e, uint64_t seed) {
    int max_steps=e->max_steps;
    memset(e,0,sizeof *e);
    e->max_steps=max_steps;
    e->seed = seed;
    e->rng  = seed_mix(seed);

    e->health    = MAX_HEALTH;
    e->max_health=MAX_HEALTH;
#if EXPLICIT_TOOLS
    /* Terraria's starter inventory (Player.SetupStartingItems, non-journey):
       Copper Shortsword, Copper Pickaxe, Copper Axe; the sword is in hand. */
    memset(e->inv, 0, sizeof e->inv);
    e->inv[ITEM_COPPER_SHORTSWORD]=1;
    e->inv[ITEM_COPPER_PICK]=1;
    e->inv[ITEM_COPPER_AXE]=1;
    e->held = ITEM_COPPER_SHORTSWORD;
#else
    e->tool_tier = TIER_COPPER_PICK;
    memset(e->inv, 0, sizeof e->inv);
    e->inv[ITEM_COPPER_SHORTSWORD]=1;
#endif
    e->selected     = 0;
    e->achievements = 0;
    e->steps        = 0;
    e->reward       = 0.0f;
    e->ep_return    = 0.0f;
    e->terminated   = false;
    e->truncated    = false;
    e->jump_left    = 0;
    e->fall_dist    = 0;
    e->msg[0]       = '\0';

    world_generate(e);          /* fills tiles[], surface[], px/py/facing */
#if FID_PHYSICS
    /* The hitbox stands centred in the spawn body's two columns. */
    e->pos_x = (e->px*16 + (PLAYER_W*16 - PLAYER_PX_W)/2) * FIX_ONE;
    e->pos_y = ((e->py+1)*16 - PLAYER_PX_H) * FIX_ONE;
    e->fall_start = ftile(e->pos_y);
    e->release_jump = true;
#endif
#if FID_MINING
    e->dig_x = e->dig_y = -1;
#endif
    mobs_reset(e);              /* FID_MOBS: worldgen's mob cells become px bodies */
    e->terrain_dirty=true;
    e->explore_min=e->explore_max=e->px;
    light_recompute(e);
    e->light_dirty = false;
#if MINIMAP
    map_update(e,false);
#endif
}

void env_step(Env *e, int action) {
    e->reward = 0.0f;
    if (e->terminated || e->truncated) return;
    e->msg[0] = '\0';
    FX_SET(e->fx.tick = 0; e->fx.n_hits = 0; e->fx.swing = false; e->fx.swing_tick = 0; e->fx.swing_tool = -1);

    if (action < 0 || action >= ACT_COUNT) action = ACT_NOOP;

    int px0 = e->px, py0 = e->py;
    bool edited = false;
#if FID_PHYSICS
    /* This action's held inputs. A held jump survives left/right while its
       jump ticks last (running jumps); any other action releases it. */
    const bool jump_was_held = e->hold_jump && e->jump > 0;
    e->hold_left = e->hold_right = e->hold_jump = e->hold_down = e->hold_up = false;
#endif
#if COMBO_ACTIONS || HELD_PLACE
    int held_place_r = -1;   /* reach slot of a place held over the step, or -1 */
    /* What a held place's last try saw: the step start's body and stock. */
    fix_t tried_x = e->pos_x, tried_y = e->pos_y;
    int tried_n = e->inv[PLACEABLES[e->selected].item];
#endif
#if COMBO_ACTIONS
    /* A combo holds its movement exactly as left/right/jump alone would (left
       or right without jump keeps a running jump going), then performs its use
       through the standalone action below, at the same ticks. Swords fix the
       facing when the swing starts (useTurn = false); Player.Update turns
       before ItemCheck in the same tick, so a combo's swing faces its run.
       A place combo holds the use button with the block for the whole step:
       it places at the step start when the standalone place would, else at
       the end of the first tick where the target cell (relative to the body
       then) takes the block, at most one block per step (the tick loop below,
       shared with HELD_PLACE's standalone places). Jumping off a floor
       thus drops a block into the cell the feet just left (Terraria's
       one-block-per-jump pillar), which no step-start placement can reach. */
    if (action >= ACT_COMBO_FIRST) {
        const Combo c = COMBOS[action - ACT_COMBO_FIRST];
        e->hold_left = (c.move & COMBO_L) != 0;
        e->hold_right = (c.move & COMBO_R) != 0;
        if (c.move & COMBO_J) {
            if (!jump_was_held) e->release_jump = true;
            e->hold_jump = true;
        } else e->hold_jump = jump_was_held;
#if FID_COMBAT
        if (c.use == ACT_ATTACK && e->item_anim == 0 && (c.move & (COMBO_L | COMBO_R)))
            e->facing = (c.move & COMBO_L) ? -1 : 1;
#endif
        if (c.use >= ACT_PLACE_FIRST && c.use < ACT_PLACE_FIRST + REACH_COUNT) held_place_r = c.use - ACT_PLACE_FIRST;
        action = c.use;
    }
#endif
#if AIM_ATTACK
    /* An aimed attack is `attack` with its aim (attack_start). */
    int aim = 0;
    if (action >= ACT_AIM_FIRST && action < ACT_AIM_FIRST + AIM_COUNT - 1) {
        aim = action - ACT_AIM_FIRST + 1;
        action = ACT_ATTACK;
    }
#endif
    int mine_r = -1;    /* FID_MINING: the use button is held on this reach slot */

    /* The three action blocks are contiguous, so a range test dispatches them
       without enumerating 31 cases. */
    if (action >= ACT_MINE_FIRST && action < ACT_MINE_FIRST + REACH_COUNT) {
#if FID_MINING
        mine_r = action - ACT_MINE_FIRST;
#if EXPLICIT_TOOLS && !TOOL_DAMAGE
        e->held = (uint8_t)tool_item(mine_tool(e, tile_at(e, e->px + REACH_DX[mine_r], e->py + REACH_DY[mine_r])));
#endif
#else
        {
            int r = action - ACT_MINE_FIRST;
#if EXPLICIT_TOOLS
            e->held = (uint8_t)tool_item(mine_tool(e, tile_at(e, e->px + REACH_DX[r], e->py + REACH_DY[r])));
#endif
            edited = do_mine(e, r);
        }
#endif
    } else if (action >= ACT_PLACE_FIRST && action < ACT_PLACE_FIRST + REACH_COUNT) {
        edited = do_place(e, action - ACT_PLACE_FIRST);
#if HELD_PLACE
        /* Placed at the step start (the step-start-only result), else the
           use button stays held over the tick loop (env.h). */
        held_place_r = edited ? -1 : action - ACT_PLACE_FIRST;
#elif COMBO_ACTIONS
        if (edited) held_place_r = -1;   /* placed at the step start, as alone */
#endif
    } else if (action >= RECIPE_FIRST_ACTION
               && action < RECIPE_FIRST_ACTION + RECIPE_COUNT) {
        do_craft(e, action - RECIPE_FIRST_ACTION);
    } else if(action>=ACT_SELECT_FIRST && action<ACT_SELECT_FIRST+PLACEABLE_COUNT) {
        int slot=action-ACT_SELECT_FIRST;
        if(e->inv[PLACEABLES[slot].item]>0) {
            e->selected=(uint8_t)slot;
#if EXPLICIT_TOOLS
            e->held=(uint8_t)PLACEABLES[slot].item;
#endif
            SAY(e,"selected %s",ITEM_NAME[PLACEABLES[slot].item]);
        } else SAY(e,"item not owned");
    } else {
        switch (action) {
#if FID_PHYSICS
        case ACT_LEFT:  e->hold_left = true;  e->hold_jump = jump_was_held; break;
        case ACT_RIGHT: e->hold_right = true; e->hold_jump = jump_was_held; break;
        case ACT_JUMP:
            /* Continue a held jump, else press afresh (released first). */
            if (!jump_was_held) e->release_jump = true;
            e->hold_jump = true;
            break;
#else
        case ACT_LEFT:        do_move(e, -1); break;
        case ACT_RIGHT:       do_move(e, +1); break;
        case ACT_JUMP:        do_jump(e);     break;
#endif
        case ACT_SELECT_NEXT: do_select(e);   break;
#if FID_COMBAT
        case ACT_ATTACK:
#if EXPLICIT_TOOLS
            if (e->item_anim == 0) e->held = (uint8_t)WEAPON_ITEM[e->weapon];
#endif
#if AIM_ATTACK
            attack_start(e, aim); break;
#else
            attack_start(e); break;
#endif
#else
        case ACT_ATTACK:
#if EXPLICIT_TOOLS
            if (!e->attack_cd) e->held = (uint8_t)WEAPON_ITEM[e->weapon];
#endif
            do_attack(e); break;
#endif
        case ACT_INTERACT: do_interact(e); break;
        case ACT_HEAL_POTION: do_heal(e,ITEM_LESSER_POTION,50); break;
        case ACT_EAT_MUSHROOM: do_heal(e,ITEM_MUSHROOM,15); break;
        case ACT_USE_CRYSTAL:
            if(e->inv[ITEM_LIFE_CRYSTAL]>0 && e->max_health<HEALTH_CAP) {
                e->inv[ITEM_LIFE_CRYSTAL]--; e->max_health+=20; e->health+=20;
                award(e,ACH_USE_CRYSTAL); SAY(e,"life increased to %d",e->max_health);
            }
            break;
        case ACT_EQUIP_NEXT:
            for(int i=1;i<WEAPON_COUNT;i++) { int k=(e->weapon+i)%WEAPON_COUNT;
                if(e->inv[WEAPON_ITEM[k]]) { e->weapon=k; break; } }
#if EXPLICIT_TOOLS
            e->held = (uint8_t)WEAPON_ITEM[e->weapon];
#endif
            break;
#if FID_PHYSICS
        case ACT_CLIMB_UP: e->hold_up = true; break;
        case ACT_CLIMB_DOWN: e->hold_down = true; break;
        case ACT_DROP: e->hold_down = true; break;
#else
        case ACT_CLIMB_UP: case ACT_CLIMB_DOWN: {
            int dir=action==ACT_CLIMB_UP?-1:1;
            if(can_climb(e,dir)) { e->py+=dir; e->fall_dist=0; e->jump_left=0;
                award(e,ACH_CLIMB); }
            break;
        }
        case ACT_DROP:
            for(int col=0;col<PLAYER_W;col++)
                if(tile_solid_top(tile_at(e,e->px+col,e->py+1))) e->drop_ticks=2;
            break;
#endif
        case ACT_SUMMON:
            if(can_summon(e)) {
                e->inv[ITEM_SUSPICIOUS_EYE]--;
                boss_summon(e);
                award(e,ACH_SUMMON_EOC);
            } else SAY(e,"nothing happens");
            break;
        default: break;             /* noop */
        }
    }

#if !FID_PHYSICS
    physics(e);
#endif
    mobs_tick(e);
    boss_tick(e);
#if FID_TICKED
    fx_path(e, 0);
    for (int t = 0; t < FID_TICKS; t++) {
        FX_SET(e->fx.tick = (uint8_t)t);
        edited |= fid_tick(e, mine_r);
#if COMBO_ACTIONS || HELD_PLACE
        if (held_place_r >= 0 && (e->pos_x != tried_x || e->pos_y != tried_y
                                  || e->inv[PLACEABLES[e->selected].item] != tried_n)) {
            /* Held place: retry silently (keep the step-start message). Within
               a place step nothing else do_place reads changes (no mining,
               no selection), so an unchanged body and stock would fail again. */
            tried_x = e->pos_x; tried_y = e->pos_y; tried_n = e->inv[PLACEABLES[e->selected].item];
            char said[sizeof e->msg];
            memcpy(said, e->msg, sizeof said);
            if (do_place(e, held_place_r)) { edited = true; held_place_r = -1; }
            else memcpy(e->msg, said, sizeof said);
        }
#endif
        fx_path(e, t + 1);
    }
#else
    (void)mine_r;
#endif
    if(e->attack_cd) e->attack_cd--;
    if(e->mine_cd) e->mine_cd--;
    if(e->heal_cd) e->heal_cd--;
    if(e->hurt_cd) e->hurt_cd--;
    if(e->drop_ticks) e->drop_ticks--;
    if(e->health>0 && ++e->safe_ticks>=40 && e->health<e->max_health) {
        int period=station_near(e,TILE_CAMPFIRE)?8:16;
        if(e->safe_ticks%period==0) e->health++;
    }

    if (e->py >= CAVERN_Y) award(e, ACH_REACH_CAVERNS);
    if(has_ach(e,ACH_REACH_CAVERNS) && e->py<e->surface[e->px]) award(e,ACH_RETURN_SURFACE);
    if(e->px<e->explore_min) e->explore_min=e->px;
    if(e->px>e->explore_max) e->explore_max=e->px;
    if(e->explore_max-e->explore_min>=30) award(e,ACH_EXPLORE);
    /* D24 tier-4 stepping stones (definitions in env.h). */
    if(!has_ach(e,ACH_FIND_ALTAR) && station_near(e,TILE_DEMON_ALTAR)) award(e,ACH_FIND_ALTAR);
    if(e->inv[ITEM_LENS]>=EYE_LENSES) award(e,ACH_HOLD_LENSES);

    if (e->health <= 0) {
        e->health = 0;
        e->terminated = true;
        e->reward += DEATH_REWARD;
        SAY(e, "you died");
        if (e->boss.active) boss_despawn(e, NULL);
    }

    /* Day/night transitions (episodes start at dawn). Sky light changes for
       the whole map only here: two full terrain recomputes per cycle. */
    e->steps++;
    int t = day_time(e);
    if (t == DAY_STEPS || t == 0) {
        e->terrain_dirty = true;
        e->light_dirty = true;
        if (t == 0 && !e->terminated) {
            award(e, ACH_SURVIVE_NIGHT);
            mobs_dawn(e);
            if (e->boss.active) boss_despawn(e, "the Eye of Cthulhu flees at dawn");
        }
    }

    /* The player carries a faint light, so moving invalidates the map too. */
    if (e->px != px0 || e->py != py0) e->light_dirty = true;
    if (e->light_dirty) {
        light_recompute(e);
        e->light_dirty = false;
    }
#if MINIMAP
    map_update(e, edited);
#else
    (void)edited;
#endif

    if (e->steps >= e->max_steps && !e->terminated) e->truncated = true;

    e->ep_return += e->reward;
}

void env_free(Env *e) {
    (void)e;                    /* the world arrays live inline in Env */
}

const char *action_name(int action) {
    if (action < 0 || action >= ACT_COUNT) return "invalid";
    return ACTION_NAME[action];
}
