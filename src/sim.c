/* Game rules: action dispatch, grid physics, crafting and episode bookkeeping. */
#include <stdio.h>
#include <string.h>

#include "env.h"

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
    "place up-left",   "place up",   "place up-right",
    "place head-left",               "place head-right",
    "place foot-left",               "place foot-right",
    "place down-left", "place down", "place down-right",
    "select next",
    "craft workbench", "craft furnace", "craft stone pick",
    "smelt copper", "craft copper pick", "craft torch",
    "smelt iron", "craft anvil", "craft iron pick",
    "smelt gold", "craft lantern",
};

/* The one reach index that lowers you a tile: mining it is a controlled
   descent, so it is the only one that clears accumulated fall distance. */
#define REACH_UNDER_FEET 8

/* ---- helpers ------------------------------------------------------------- */

/* Achievement unlocks are the only positive reward in the environment. */
static void award(Env *e, int ach) {
    if (has_ach(e, ach)) return;
    e->achievements |= 1u << ach;
    e->reward += 1.0f;
}

static inline void give(Env *e, int item, int qty) {
    int n = e->inv[item] + qty;
    e->inv[item] = (int16_t)(n > INV_CAP ? INV_CAP : n);
}

static inline bool grounded(const Env *e) {
    return tile_solid(tile_at(e, e->px, e->py + 1));
}

/* Chebyshev-radius search, so a station is usable from anywhere in the square
   around the player. tile_at() reports out-of-world cells as bedrock. */
static bool station_near(const Env *e, Tile want) {
    for (int dy = -STATION_RANGE; dy <= STATION_RANGE; dy++)
        for (int dx = -STATION_RANGE; dx <= STATION_RANGE; dx++)
            if (tile_at(e, e->px + dx, e->py + dy) == want) return true;
    return false;
}

static const char *pick_name(uint8_t tier) {
    switch (tier) {
    case TIER_IRON_PICK:   return "iron";
    case TIER_COPPER_PICK: return "copper";
    default:               return "stone";
    }
}

static void award_collect(Env *e, Tile t) {
    switch (t) {
    case TILE_LOG:
    case TILE_WOOD:       award(e, ACH_COLLECT_WOOD);   break;
    case TILE_DIRT:
    case TILE_GRASS:      award(e, ACH_COLLECT_DIRT);   break;
    case TILE_STONE:      award(e, ACH_COLLECT_STONE);  break;
    case TILE_COPPER_ORE: award(e, ACH_COLLECT_COPPER); break;
    case TILE_IRON_ORE:   award(e, ACH_COLLECT_IRON);   break;
    case TILE_GOLD_ORE:   award(e, ACH_COLLECT_GOLD);   break;
    default: break;
    }
}

static void award_place(Env *e, Tile t) {
    switch (t) {
    case TILE_STONE:
    case TILE_DIRT:
    case TILE_WOOD:       award(e, ACH_PLACE_BLOCK);     break;
    case TILE_TORCH:      award(e, ACH_PLACE_TORCH);     break;
    case TILE_LANTERN:    award(e, ACH_PLACE_LANTERN);   break;
    case TILE_WORKBENCH:  award(e, ACH_PLACE_WORKBENCH); break;
    case TILE_FURNACE:    award(e, ACH_PLACE_FURNACE);   break;
    case TILE_ANVIL:      award(e, ACH_PLACE_ANVIL);     break;
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
                    && !tile_solid(tile_at(e, e->px, e->py - PLAYER_H))) {
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
    if (!grounded(e)) {
        SAY(e, "already airborne");
        return;
    }
    /* Clearance is measured above the head, not above the feet. */
    if (tile_solid(tile_at(e, e->px, e->py - PLAYER_H))) {
        SAY(e, "no headroom");
        return;
    }
    e->jump_left = JUMP_HEIGHT;
    e->fall_dist = 0;
}

static void do_mine(Env *e, int r) {
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

    e->tiles[ty][tx] = TILE_AIR;
    e->light_dirty = true;

    /* Lowering yourself one tile at a time is a controlled descent, not a fall;
       genuine falls into pre-existing voids must still hurt. Only the cell
       straight under the feet qualifies -- a diagonal dig does not drop you. */
    if (r == REACH_UNDER_FEET) e->fall_dist = 0;

    int8_t drop = tile_drop(t);
    if (drop >= 0) give(e, drop, 1);
    award_collect(e, t);
    SAY(e, "mined %s", TILE_INFO[t].name);
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
    if (is_body(e, tx, ty)) {   /* no reach index targets the body, but the rule
                                   must hold however the reach table changes */
        SAY(e, "you are standing there");
        return;
    }

    e->tiles[ty][tx] = (uint8_t)p.tile;
    e->inv[p.item]--;
    e->light_dirty = true;
    award_place(e, p.tile);
    SAY(e, "placed %s", TILE_INFO[p.tile].name);
}

/* Skip past placeables the player cannot actually use, but never spin: after a
   full lap the original slot wins, and an empty inventory just steps by one. */
static void do_select(Env *e) {
    int next = (e->selected + 1) % PLACEABLE_COUNT;
    for (int i = 0; i < PLACEABLE_COUNT; i++) {
        int cand = (e->selected + 1 + i) % PLACEABLE_COUNT;
        if (e->inv[PLACEABLES[cand].item] > 0) {
            next = cand;
            break;
        }
    }
    e->selected = (uint8_t)next;

    Item it = PLACEABLES[next].item;
    SAY(e, "selected %s (%d)", ITEM_NAME[it], e->inv[it]);
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
    award(e, r->ach);
    SAY(e, "crafted %s", r->name);
}

/* ---- phase 2: physics --------------------------------------------------- */

/* Touching down: pay for the drop, then clear it. Split out of physics()
   because a fall now has to settle on the tick the feet arrive, from either
   branch below. */
static void land(Env *e) {
    if (e->fall_dist > FALL_SAFE) {
        int dmg = (e->fall_dist - FALL_SAFE) * FALL_DMG_PER_TILE;
        e->health -= dmg;
        e->reward += -0.1f * (float)dmg;
        SAY(e, "fell %d tiles (-%d hp)", e->fall_dist, dmg);
    }
    e->fall_dist = 0;
}

static void physics(Env *e) {
    if (e->jump_left > 0) {
        /* Rising one tile per tick. The head leads, so a ceiling one row above
           the head is what ends the jump early. */
        int head_next = e->py - PLAYER_H;
        if (in_bounds(e->px, head_next) && !tile_solid(tile_at(e, e->px, head_next))) {
            e->py--;
            e->jump_left--;
        } else {
            e->jump_left = 0;
        }
    } else if (!tile_solid(tile_at(e, e->px, e->py + 1))) {
        e->py++;
        e->fall_dist++;
        /* Settle on the tick the feet arrive, not the one after. Deferring it
           left the player standing on the ground with fall_dist still live for
           a whole action, and mining the block underneath zeroes fall_dist as
           a controlled descent -- so a 39-tile drop cost nothing at all if you
           dug on landing. Same-tick settlement closes that window. */
        if (tile_solid(tile_at(e, e->px, e->py + 1))) land(e);
    } else {
        land(e);
    }

    /* The head must stay in the world, so the feet floor is PLAYER_H - 1. */
    if (e->py < PLAYER_H - 1) e->py = PLAYER_H - 1;
    if (e->py > WORLD_H - 1)  e->py = WORLD_H - 1;
}

/* ---- API ---------------------------------------------------------------- */

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
    e->seed = seed;
    e->rng  = seed_mix(seed);

    e->health    = MAX_HEALTH;
    e->tool_tier = TIER_HAND;
    memset(e->inv, 0, sizeof e->inv);
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
    light_recompute(e);
    e->light_dirty = false;
}

void env_step(Env *e, int action) {
    if (e->terminated || e->truncated) return;

    e->reward = 0.0f;
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
        default: break;             /* noop */
        }
    }

    physics(e);

    if (e->py >= DEEP_Y) award(e, ACH_DESCEND_DEEP);

    if (e->health <= 0) {
        e->health = 0;
        e->terminated = true;
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
