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
    "mine up", "mine down", "mine left", "mine right",
    "place up", "place down", "place left", "place right",
    "select next",
    "craft workbench", "craft furnace", "craft stone pick",
    "smelt copper", "craft copper pick", "craft torch",
};

/* Indexed by (action - ACT_MINE_UP) and (action - ACT_PLACE_UP) alike: the two
   action blocks share the up/down/left/right ordering. */
static const int DIR_DX[4] = { 0,  0, -1, 1};
static const int DIR_DY[4] = {-1,  1,  0, 0};

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
    return tier == TIER_COPPER_PICK ? "copper" : "stone";
}

static void award_collect(Env *e, Tile t) {
    switch (t) {
    case TILE_WOOD:       award(e, ACH_COLLECT_WOOD);   break;
    case TILE_DIRT:
    case TILE_GRASS:      award(e, ACH_COLLECT_DIRT);   break;
    case TILE_STONE:      award(e, ACH_COLLECT_STONE);  break;
    case TILE_COPPER_ORE: award(e, ACH_COLLECT_COPPER); break;
    case TILE_IRON_ORE:   award(e, ACH_COLLECT_IRON);   break;
    default: break;
    }
}

static void award_place(Env *e, Tile t) {
    switch (t) {
    case TILE_STONE:
    case TILE_DIRT:
    case TILE_WOOD:       award(e, ACH_PLACE_BLOCK);     break;
    case TILE_TORCH:      award(e, ACH_PLACE_TORCH);     break;
    case TILE_WORKBENCH:  award(e, ACH_PLACE_WORKBENCH); break;
    case TILE_FURNACE:    award(e, ACH_PLACE_FURNACE);   break;
    default: break;
    }
}

/* ---- phase 1: actions --------------------------------------------------- */

static void do_move(Env *e, int dir) {
    e->facing = dir;

    int nx = e->px + dir;
    if (!tile_solid(tile_at(e, nx, e->py))) {
        e->px = nx;
        return;
    }
    /* One-tile auto step-up: needs footing plus clearance over both the old and
       the new column, so a walk into a single ledge climbs it. */
    if (grounded(e) && !tile_solid(tile_at(e, nx, e->py - 1))
                    && !tile_solid(tile_at(e, e->px, e->py - 1))) {
        e->px = nx;
        e->py -= 1;
        return;
    }
    if (!in_bounds(nx, e->py)) SAY(e, "the world ends here");
    else SAY(e, "blocked by %s", TILE_INFO[tile_at(e, nx, e->py)].name);
}

static void do_jump(Env *e) {
    if (!grounded(e)) {
        SAY(e, "already airborne");
        return;
    }
    if (tile_solid(tile_at(e, e->px, e->py - 1))) {
        SAY(e, "no headroom");
        return;
    }
    e->jump_left = JUMP_HEIGHT;
    e->fall_dist = 0;
}

static void do_mine(Env *e, int d) {
    int tx = e->px + DIR_DX[d];
    int ty = e->py + DIR_DY[d];

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
       genuine falls into pre-existing voids must still hurt. */
    if (DIR_DY[d] == 1) e->fall_dist = 0;

    int8_t drop = tile_drop(t);
    if (drop >= 0) give(e, drop, 1);
    award_collect(e, t);
    SAY(e, "mined %s", TILE_INFO[t].name);
}

/* Placement needs no supporting neighbour on purpose: pillar-jumping upward and
   bridging across a chasm are both intended traversal tools. */
static void do_place(Env *e, int d) {
    Placeable p = PLACEABLES[e->selected];
    int tx = e->px + DIR_DX[d];
    int ty = e->py + DIR_DY[d];

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
    if (tx == e->px && ty == e->py) {   /* unreachable for a 1x1 player; keeps
                                           the rule true if the body grows */
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
    if (r->need_workbench && !station_near(e, TILE_WORKBENCH)) {
        SAY(e, "need to be near a workbench");
        return;
    }
    if (r->need_furnace && !station_near(e, TILE_FURNACE)) {
        SAY(e, "need to be near a furnace");
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

static void physics(Env *e) {
    if (e->jump_left > 0) {
        /* Rising one tile per tick; a ceiling ends the jump early. */
        if (in_bounds(e->px, e->py - 1) && !tile_solid(tile_at(e, e->px, e->py - 1))) {
            e->py--;
            e->jump_left--;
        } else {
            e->jump_left = 0;
        }
    } else if (!tile_solid(tile_at(e, e->px, e->py + 1))) {
        e->py++;
        e->fall_dist++;
    } else {
        if (e->fall_dist > FALL_SAFE) {
            int dmg = (e->fall_dist - FALL_SAFE) * FALL_DMG_PER_TILE;
            e->health -= dmg;
            e->reward += -0.1f * (float)dmg;
            SAY(e, "fell %d tiles (-%d hp)", e->fall_dist, dmg);
        }
        e->fall_dist = 0;
    }

    if (e->py < 0) e->py = 0;
    if (e->py > WORLD_H - 1) e->py = WORLD_H - 1;
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

    switch (action) {
    case ACT_LEFT:  do_move(e, -1); break;
    case ACT_RIGHT: do_move(e, +1); break;
    case ACT_JUMP:  do_jump(e);     break;

    case ACT_MINE_UP:
    case ACT_MINE_DOWN:
    case ACT_MINE_LEFT:
    case ACT_MINE_RIGHT:  do_mine(e, action - ACT_MINE_UP);   break;

    case ACT_PLACE_UP:
    case ACT_PLACE_DOWN:
    case ACT_PLACE_LEFT:
    case ACT_PLACE_RIGHT: do_place(e, action - ACT_PLACE_UP); break;

    case ACT_SELECT_NEXT: do_select(e); break;

    case ACT_CRAFT_WORKBENCH:
    case ACT_CRAFT_FURNACE:
    case ACT_CRAFT_STONE_PICK:
    case ACT_SMELT_COPPER:
    case ACT_CRAFT_COPPER_PICK:
    case ACT_CRAFT_TORCH: do_craft(e, action - RECIPE_FIRST_ACTION); break;

    default: break;             /* noop */
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
