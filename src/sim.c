/* Game rules: action dispatch, grid physics, crafting and episode bookkeeping. */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "env.h"
#include "rng.h"

#define INV_CAP 999

/* Every player-visible message goes through here so the 64-byte buffer can
   never be overrun. */
#define SAY(e, ...) ((void)snprintf((e)->msg, sizeof (e)->msg, __VA_ARGS__))

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
    "craft wood breastplate","craft iron chainmail",
    "attack","open chest","drink healing potion","eat mushroom","use life crystal",
    "cycle weapon","climb up","climb down","drop through platform",
};

/* ---- helpers ------------------------------------------------------------- */

/* Achievement unlocks are the only positive reward in the environment. */
static void award(Env *e, int ach) {
    if (ach < 0 || ach >= ACH_COUNT) return;
    if (has_ach(e, ach)) return;
    e->achievements |= 1u << ach;
    e->reward += 1.0f;
}

static inline void give(Env *e, int item, int qty) {
    int n = e->inv[item] + qty;
    e->inv[item] = (int16_t)(n > INV_CAP ? INV_CAP : n);
}

static inline bool grounded(const Env *e) {
    return player_grounded(e);
}

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

/* ---- phase 1: actions --------------------------------------------------- */

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
    if (!grounded(e)) { e->air_jump_used = true; award(e, ACH_DOUBLE_JUMP); }
}

static void do_mine(Env *e, int r) {
    if (e->mine_cd) { SAY(e,"pickaxe cooling down"); return; }
    int tx = e->px + REACH_DX[r];
    int ty = e->py + REACH_DY[r];

    if (!in_bounds(tx, ty)) {
        SAY(e, "nothing to mine");
        return;
    }
    Tile t = tile_at(e, tx, ty);
    if (t == TILE_AIR) {
        SAY(e, "nothing to mine");
        return;
    }
    if (tile_tier(t) == TIER_NEVER) {
        SAY(e, "%s is unbreakable", TILE_INFO[t].name);
        return;
    }
    if (tile_tier(t) > e->tool_tier) {
        SAY(e, "need a %s pickaxe", pick_name(tile_tier(t)));
        return;
    }
    if(tile_solid(t)&&tile_at(e,tx,ty-1)==TILE_LOG) {
        SAY(e,"chop the tree before mining its ground"); return;
    }

    bool supported_before=grounded(e);
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
        /* Radius-two canopies cannot overlap another generated tree trunk. */
        for(int y=top-2;y<=top;y++) for(int x=tx-2;x<=tx+2;x++) {
            if(in_bounds(x,y) && e->tiles[y][x]==TILE_LEAVES) {
                e->tiles[y][x]=TILE_AIR; light_tile_changed(e,x,y,TILE_LEAVES);
            }
        }
        give(e,ITEM_WOOD,wood);
        harvested_wood=wood;
    } else {
        e->tiles[ty][tx] = TILE_AIR; light_tile_changed(e,tx,ty,t);
    }
    e->light_dirty = true;
    e->mine_cd = t==TILE_LOG?3:4-e->tool_tier;

    /* Lowering yourself one tile at a time is a controlled descent, not a fall;
       genuine falls into pre-existing voids must still hurt. Only the cell
       straight under the feet qualifies -- a diagonal dig does not drop you. */
    if (supported_before && REACH_DY[r]==1 && REACH_DX[r]>=0 && REACH_DX[r]<PLAYER_W) e->fall_dist = 0;

    int8_t drop = tile_drop(t);
    if (drop >= 0 && t!=TILE_LOG) give(e, drop, 1);
    award_collect(e, t);
    if(t==TILE_LOG) SAY(e,"felled tree (%d wood)",harvested_wood);
    else SAY(e, "mined %s", TILE_INFO[t].name);
}

/* Placement needs no supporting neighbour on purpose: pillar-jumping upward and
   bridging across a chasm are both intended traversal tools. */
static void do_place(Env *e, int r) {
    Placeable p = PLACEABLES[e->selected];
    int tx = e->px + REACH_DX[r];
    int ty = e->py + REACH_DY[r];

    if (e->inv[p.item] <= 0) {
        SAY(e, "no %s to place", ITEM_NAME[p.item]);
        return;
    }
    if (!in_bounds(tx, ty)) {
        SAY(e, "cannot place outside the world");
        return;
    }
    Tile t = tile_at(e, tx, ty);
    if (t != TILE_AIR) {
        SAY(e, "%s is in the way", TILE_INFO[t].name);
        return;
    }
    if (tile_solid(p.tile) && is_body(e, tx, ty)) {
        SAY(e, "you are standing there");
        return;
    }

    e->tiles[ty][tx] = (uint8_t)p.tile;
    light_tile_changed(e,tx,ty,t);
    e->inv[p.item]--;
    e->light_dirty = true;
    award_place(e, p.tile);
    SAY(e, "placed %s", TILE_INFO[p.tile].name);
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
            Item it = PLACEABLES[cand].item;
            SAY(e, "selected %s (%d)", ITEM_NAME[it], e->inv[it]);
            return;
        }
    }
    SAY(e, "nothing to select");
}

static void do_craft(Env *e, int idx) {
    const Recipe *r = &RECIPES[idx];

    if (r->grant_tier && e->tool_tier >= r->grant_tier) {
        SAY(e, "already have it");
        return;
    }
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
    if (r->grant_tier) e->tool_tier = r->grant_tier;
    /* Crafting explicitly chooses this equipment, rather than auto-selecting
       the best item found in a chest. Weapon cycling can select weaker ones. */
    for (int i=0;i<WEAPON_COUNT;i++) if (r->out_item == (int)WEAPON_ITEM[i]) e->weapon=i;
    if (r->out_item==ITEM_WOOD_ARMOR) e->armor=1;
    if (r->out_item==ITEM_IRON_ARMOR) e->armor=2;
    award(e, r->ach);
    SAY(e, "crafted %s", r->name);
}

/* ---- action validity ----------------------------------------------------- */

/* Physical/epistemic action legality, never a strategy filter. Turning matters
   to combat; empty-air attacks and full-health healing remain possible. Dark
   mining/placement attempts must not leak hidden terrain through the mask.
   Predicates mirror handler guards, with explicit tests in selftest_v2.c. */

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

static bool can_mine(const Env *e, int r) {
    if (e->mine_cd) return false;
    int tx = e->px + REACH_DX[r], ty = e->py + REACH_DY[r];
    if (!in_bounds(tx, ty)) return false;
    Tile t = tile_at(e, tx, ty);
    /* Unknown cells permit attempts: the mask must not reveal hidden ore. */
    if (e->light[ty][tx] < DARK_THRESHOLD) return true;
    if (t == TILE_AIR) return false;
    if (tile_tier(t) == TIER_NEVER) return false;
    if(tile_solid(t)&&tile_at(e,tx,ty-1)==TILE_LOG) return false;
    return tile_tier(t) <= e->tool_tier;
}

static bool can_place(const Env *e, int r) {
    Placeable p = PLACEABLES[e->selected];
    int tx = e->px + REACH_DX[r], ty = e->py + REACH_DY[r];
    if (e->inv[p.item] <= 0)              return false;
    if (!in_bounds(tx, ty))               return false;
    if (e->light[ty][tx] >= DARK_THRESHOLD && tile_at(e,tx,ty)!=TILE_AIR) return false;
    return !tile_solid(p.tile)||!is_body(e, tx, ty);
}

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
    if (r->grant_tier && e->tool_tier >= r->grant_tier)        return false;
    if (r->station != TILE_AIR && !(stations&(1u<<r->station))) return false;
    for (int i = 0; i < r->n_in; i++)
        if (e->inv[r->in_item[i]] < r->in_qty[i])              return false;
    return true;
}

static int nearby_chest(const Env *e) {
    for (int i=0;i<e->chest_count;i++) {
        const Chest *c=&e->chests[i];
        if (!c->opened && c->x>=e->px-1 && c->x<=e->px+PLAYER_W && c->y>=e->py-PLAYER_H && c->y<=e->py+1
            && e->light[c->y][c->x]>=DARK_THRESHOLD) return i;
    }
    return -1;
}

static bool can_climb(const Env *e,int dir) {
    return player_on_rope(e) && body_fits(e,e->px,e->py+dir);
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

    mask[ACT_LEFT]        = (uint8_t)can_move(e, -1);
    mask[ACT_RIGHT]       = (uint8_t)can_move(e, +1);
    mask[ACT_JUMP]        = (uint8_t)can_jump(e);
    mask[ACT_SELECT_NEXT] = (uint8_t)can_select(e);
    mask[ACT_ATTACK] = e->attack_cd==0; /* legal even without a target */
    mask[ACT_INTERACT] = nearby_chest(e)>=0;
    mask[ACT_HEAL_POTION] = e->inv[ITEM_LESSER_POTION]>0 && !e->heal_cd;
    mask[ACT_EAT_MUSHROOM] = e->inv[ITEM_MUSHROOM]>0 && !e->heal_cd;
    mask[ACT_USE_CRYSTAL] = e->inv[ITEM_LIFE_CRYSTAL]>0 && e->max_health<HEALTH_CAP;
    mask[ACT_EQUIP_NEXT] = can_equip(e);
    mask[ACT_CLIMB_UP] = can_climb(e,-1);
    mask[ACT_CLIMB_DOWN] = can_climb(e,1);
    for(int col=0;col<PLAYER_W;col++) if(tile_solid_top(tile_at(e,e->px+col,e->py+1))) mask[ACT_DROP]=1;

    for (int r = 0; r < REACH_COUNT; r++) {
        mask[ACT_MINE_FIRST  + r] = (uint8_t)can_mine(e, r);
        mask[ACT_PLACE_FIRST + r] = (uint8_t)can_place(e, r);
    }
    uint32_t stations=station_mask(e);
    for (int i = 0; i < RECIPE_COUNT; i++)
        mask[RECIPE_FIRST_ACTION + i] = (uint8_t)can_craft(e, i,stations);
}

/* ---- phase 2: physics --------------------------------------------------- */

/* Touching down: pay for the drop, then clear it. Split out of physics()
   because a fall now has to settle on the tick the feet arrive, from either
   branch below. */
static void land(Env *e) {
    if (e->fall_dist > FALL_SAFE) {
        int dmg = (e->fall_dist - FALL_SAFE) * FALL_DMG_PER_TILE;
        /* Classic: floor(raw - defense/2), equivalent to ceil defense/2
           for integer raw damage. Preserve odd-defense protection. */
        dmg-=(ARMOR_DEFENSE[e->armor]+1)/2; if(dmg<1) dmg=1;
        e->health -= dmg;
        e->safe_ticks=0;
        e->reward += FALL_REWARD_PER_HP * (float)dmg;
        SAY(e, "fell %d tiles (-%d hp)", e->fall_dist, dmg);
    }
    e->fall_dist = 0;
    e->air_jump_used = false;
}

static void physics(Env *e) {
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

/* ---- API ---------------------------------------------------------------- */

static void do_attack(Env *e) {
    if(e->attack_cd) return;
    e->attack_cd=3;
    for(int i=0;i<MAX_MOBS;i++) {
        Mob *m=&e->mobs[i];
        int edge=e->px+(e->facing>0?PLAYER_W-1:0),dx=m->x-edge;
        if(!m->kind || (!is_body(e,m->x,m->y)&&(dx*e->facing<0 || abs(dx)>2)) || m->y<e->py-PLAYER_H+1 || m->y>e->py) continue;
        /* No sword hits through a wall. */
        bool blocked=false;
        for(int s=1;s<abs(dx);s++)
            if(tile_solid(tile_at(e,edge+s*e->facing,m->y))) blocked=true;
        if(blocked) continue;
        m->hp-=WEAPON_DAMAGE[e->weapon];
        if(m->hp<=0) {
            if(m->kind==MOB_BLUE_SLIME) { give(e,ITEM_GEL,2); award(e,ACH_KILL_SLIME); }
            else award(e,ACH_KILL_BAT);
            m->kind=MOB_NONE;
            SAY(e,"enemy defeated");
        } else {
            int nx=m->x+e->facing;
            if(!tile_solid(tile_at(e,nx,m->y))) m->x=nx;
            SAY(e,"hit enemy: %d hp",m->hp);
        }
    }
}

static void do_interact(Env *e) {
    int i=nearby_chest(e);
    if(i<0) return;
    Chest *c=&e->chests[i]; c->opened=true;
    for(int k=0;k<ITEM_COUNT;k++) give(e,k,c->loot[k]);
    e->tiles[c->y][c->x]=TILE_CHEST_OPEN;
    light_tile_changed(e,c->x,c->y,TILE_CHEST);
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

static void mob_tick(Env *e) {
    /* Bounded local spawns. One candidate draw per spawn event, not an
       unbounded rejection loop. Unseen/far mobs can be recycled. */
    if(e->steps>=120 && e->steps%120==0) {
        int x=e->px+(rng_below(&e->rng,2)?1:-1)*rng_range(&e->rng,8,14);
        int y=e->py;
        uint8_t kind=e->py>e->surface[e->px]+8?MOB_CAVE_BAT:MOB_BLUE_SLIME;
        if(in_bounds(x,y)) {
            if(kind==MOB_BLUE_SLIME) y=e->surface[x]-1;
            if(!tile_solid(tile_at(e,x,y))) for(int i=0;i<MAX_MOBS;i++) {
                if(!e->mobs[i].kind) {
                    e->mobs[i]=(Mob){x,y,kind==MOB_BLUE_SLIME?25:16,0,0,1,kind}; break;
                }
            }
        }
    }
    for(int i=0;i<MAX_MOBS;i++) {
        Mob *m=&e->mobs[i]; if(!m->kind) continue;
        if(abs(m->x-e->px)>28 || abs(m->y-e->py)>24) { m->kind=0; continue; }
        m->phase=(m->phase+1)%8;
        m->dir=e->px>=m->x?1:-1;
        if(m->kind==MOB_CAVE_BAT) {
            if(m->phase%3==0) {
                int nx=m->x+m->dir,ny=m->y+(e->py>m->y?1:e->py<m->y?-1:0);
                if(!tile_solid(tile_at(e,nx,m->y))) m->x=nx;
                if(!tile_solid(tile_at(e,m->x,ny))) m->y=ny;
            }
        } else {
            bool on_ground=tile_solid(tile_at(e,m->x,m->y+1)) || tile_at(e,m->x,m->y+1)==TILE_PLATFORM;
            if(on_ground && m->phase==0) m->jump=2;
            if(m->jump>0) {
                if(!tile_solid(tile_at(e,m->x,m->y-1))) m->y--;
                m->jump--;
            } else if(!on_ground) m->y++;
            if(m->phase%2==0 && !tile_solid(tile_at(e,m->x+m->dir,m->y))) m->x+=m->dir;
        }
        if(is_body(e,m->x,m->y) && !e->hurt_cd) {
            int damage=(m->kind==MOB_BLUE_SLIME?7:12)-(ARMOR_DEFENSE[e->armor]+1)/2;
            e->health-=damage>0?damage:1;
            e->hurt_cd=8; e->safe_ticks=0;
            SAY(e,"%s hit you (-%d hp)",m->kind==MOB_BLUE_SLIME?"Blue Slime":"Cave Bat",damage);
        }
    }
}

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
    e->tool_tier = TIER_COPPER_PICK;
    memset(e->inv, 0, sizeof e->inv);
    e->inv[ITEM_COPPER_SHORTSWORD]=1;
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
    e->terrain_dirty=true;
    e->explore_min=e->explore_max=e->px;
    light_recompute(e);
    e->light_dirty = false;
}

void env_step(Env *e, int action) {
    e->reward = 0.0f;
    if (e->terminated || e->truncated) return;
    e->msg[0] = '\0';

    if (action < 0 || action >= ACT_COUNT) action = ACT_NOOP;

    int px0 = e->px, py0 = e->py;

    /* The three action blocks are contiguous, so a range test dispatches them
       without enumerating 31 cases. */
    if (action >= ACT_MINE_FIRST && action < ACT_MINE_FIRST + REACH_COUNT) {
        do_mine(e, action - ACT_MINE_FIRST);
    } else if (action >= ACT_PLACE_FIRST && action < ACT_PLACE_FIRST + REACH_COUNT) {
        do_place(e, action - ACT_PLACE_FIRST);
    } else if (action >= RECIPE_FIRST_ACTION
               && action < RECIPE_FIRST_ACTION + RECIPE_COUNT) {
        do_craft(e, action - RECIPE_FIRST_ACTION);
    } else {
        switch (action) {
        case ACT_LEFT:        do_move(e, -1); break;
        case ACT_RIGHT:       do_move(e, +1); break;
        case ACT_JUMP:        do_jump(e);     break;
        case ACT_SELECT_NEXT: do_select(e);   break;
        case ACT_ATTACK: do_attack(e); break;
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
            break;
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
        default: break;             /* noop */
        }
    }

    physics(e);
    mob_tick(e);
    if(e->attack_cd) e->attack_cd--;
    if(e->mine_cd) e->mine_cd--;
    if(e->heal_cd) e->heal_cd--;
    if(e->hurt_cd) e->hurt_cd--;
    if(e->drop_ticks) e->drop_ticks--;
    if(e->health>0 && ++e->safe_ticks>=40 && e->health<e->max_health) {
        int period=station_near(e,TILE_CAMPFIRE)?8:16;
        if(e->safe_ticks%period==0) e->health++;
    }

    if (e->py >= DEEP_Y) award(e, ACH_DESCEND_DEEP);
    if(has_ach(e,ACH_DESCEND_DEEP) && e->py<e->surface[e->px]) award(e,ACH_RETURN_SURFACE);
    if(e->px<e->explore_min) e->explore_min=e->px;
    if(e->px>e->explore_max) e->explore_max=e->px;
    if(e->explore_max-e->explore_min>=30) award(e,ACH_EXPLORE);

    if (e->health <= 0) {
        e->health = 0;
        e->terminated = true;
        e->reward += DEATH_REWARD;
        SAY(e, "you died");
    }

    /* The player carries a faint light, so moving invalidates the map too. */
    if (e->px != px0 || e->py != py0) e->light_dirty = true;
    if (e->light_dirty) {
        light_recompute(e);
        e->light_dirty = false;
    }

    e->steps++;
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
