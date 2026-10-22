/* Omniscient scripted planner for terraria-lite v7 (diagnostic, not a policy).

   Privileged: it reads the full Env (every tile, chest, mob) to plan.
   Constrained: it acts ONLY through env_step, one action per step, and every
   action it issues must be marked legal by env_action_mask at that moment
   (checked; an illegal action aborts the run as a planner bug). Its score is
   therefore a genuine achievable lower bound on the v7 ceiling.

   Usage: oracle_v7 [-h horizon] [-s first_seed] [-n count] [-t tapefile]
                    [-p name=value]... [-v]...      planner runs
          oracle_v7 -L [-s first_seed] [-n count]   necessary-condition lower bounds
   Prints one JSON object per world on stdout; -t appends (seed,horizon,len,
   actions) tape records for replay_verify.py. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "env.h"

#define NW WORLD_W
#define NH WORLD_H
#define NN (NW * NH)
#define MAXTAPE 40000
#define INF 0x3fffffff
#define FEET_MAX (NH - BEDROCK_ROWS - 1) /* lowest feet row (93) */

enum { K_IRON, K_GOLD, K_COPPER, K_SILVER, K_KINDS };
static const Tile KIND_TILE[K_KINDS] = {TILE_IRON_ORE, TILE_GOLD_ORE, TILE_COPPER_ORE, TILE_SILVER_ORE};
static const Item KIND_ITEM[K_KINDS] = {ITEM_IRON_ORE, ITEM_GOLD_ORE, ITEM_COPPER_ORE, ITEM_SILVER_ORE};

enum { P_SURFACE, P_DEEP, P_RETURN, P_POST, P_DONE };

/* Tunable planner parameters (-p name=value). */
static struct {
    double w_gold_a;   /* distance multiplier for gold before the iron pickaxe */
    double w_iron_b;   /* distance multiplier for iron between iron and gold pickaxes */
    int chest_bonus;   /* steps a chest room is preferred over the nearest ore */
    int return_reserve;
    int wood_goal;
} P = {4.0, 2.0, 200, 40, 62};

typedef struct {
    Env e;
    int horizon;
    uint8_t tape[MAXTAPE];
    int nt;
    int ach_step[ACH_COUNT];
    int got[ITEM_COUNT]; /* cumulative items gained by mining */
    int n_move, n_mine_ore, n_mine_other, n_noop_cd, n_noop_air, n_noop_other, n_place, n_craft, n_misc;
    bool illegal;
    int phase;
    int need[K_KINDS];
    int tgt;          /* target cell id, -1 none */
    int tgt_kind;     /* TK_* */
    int tgt_age;
    bool pillar;
    int pillar_y;
    bool session;
    int chest_done;
    int verbose;
    int last_progress;
    uint8_t bad[NH][NW];   /* targets proven unreachable */
    int st_x[TILE_COUNT], st_y[TILE_COUNT]; /* stations we placed and must recover */
    bool st_live[TILE_COUNT];
    int tree_order[NW], n_trees;
    int path[NN], path_len;
    int mob_ignore_until, mob_chase_start;
    int placed_cell[64]; int n_placed; /* recent placements: never strip-mine them */
} Bot;

enum { TK_NONE, TK_ORE, TK_LOG, TK_MUSHROOM, TK_CHEST, TK_CRYSTAL, TK_DEEP, TK_SURFACE, TK_SLIME, TK_STATION };

static Bot B;
#define E (&B.e)

/* ------------------------------------------------------------- helpers -- */

static int RIDX[5][4]; /* [dy+3][dx+1] -> reach index */
static void init_reach(void) {
    for (int i = 0; i < 5; i++)
        for (int j = 0; j < 4; j++) RIDX[i][j] = -1;
    for (int r = 0; r < REACH_COUNT; r++) RIDX[REACH_DY[r] + 3][REACH_DX[r] + 1] = r;
}
static int reach_of(int x, int y) {
    int dx = x - E->px, dy = y - E->py;
    if (dx < -1 || dx > 2 || dy < -3 || dy > 1) return -1;
    return RIDX[dy + 3][dx + 1];
}
static inline Tile T(int x, int y) { return tile_at(E, x, y); }
static inline bool SOL(int x, int y) { return tile_solid(T(x, y)); }
static inline bool SUPC(int x, int y) {
    Tile t = T(x, y);
    return tile_solid(t) || tile_solid_top(t);
}
static int mine_period(void) { return 4 - E->tool_tier; }
static bool mineable(int x, int y) {
    if (!in_bounds(x, y)) return false;
    Tile t = T(x, y);
    if (t == TILE_AIR) return false;
    if (tile_tier(t) == TIER_NEVER || tile_tier(t) > E->tool_tier) return false;
    if (tile_solid(t) && T(x, y - 1) == TILE_LOG) return false;
    return true;
}
static uint8_t want[NH][NW];
/* want[] can be stale for one decision; trust it only while the ore is there. */
static bool wanted(int x, int y) {
    if (!in_bounds(x, y) || !want[y][x]) return false;
    Tile t = (Tile)E->tiles[y][x];
    return t == TILE_IRON_ORE || t == TILE_GOLD_ORE || t == TILE_COPPER_ORE || t == TILE_SILVER_ORE || t == TILE_WOOD;
}
/* Cost to make a cell passable for the body; -1 impossible. */
static int ccost(int x, int y) {
    if (!in_bounds(x, y)) return -1;
    Tile t = T(x, y);
    if (!tile_solid(t)) return 0;
    if (!mineable(x, y)) return -1;
    if (wanted(x, y)) return 1;
    return mine_period();
}
static bool rope_in_body(int x, int y) {
    for (int c = 0; c < PLAYER_W; c++)
        for (int r = 0; r < PLAYER_H; r++)
            if (T(x + c, y - r) == TILE_ROPE) return true;
    return false;
}
static bool supported_at(int x, int y) { return SUPC(x, y + 1) || SUPC(x + 1, y + 1) || rope_in_body(x, y); }
static int land_from(int x, int y) {
    while (y < FEET_MAX && !supported_at(x, y)) y++;
    return y;
}
static int wood_needed(void);
/* Bulk block slot to build with: dirt, then stone, then surplus wood. */
static int blocks_slot(void) {
    if (E->inv[ITEM_DIRT] > 0) return 1;
    if (E->inv[ITEM_STONE] > 0) return 0;
    if (E->inv[ITEM_WOOD] > wood_needed()) return 2;
    return -1;
}
static int block_count(void) {
    int w = E->inv[ITEM_WOOD] - wood_needed();
    return E->inv[ITEM_DIRT] + E->inv[ITEM_STONE] + (w > 0 ? w : 0);
}
static bool standing(void) { return player_grounded(E) && E->jump_left == 0; }

/* ----------------------------------------------------------------- act -- */

static bool done(void) { return E->terminated || E->truncated || B.illegal; }

static void act(int a) {
    if (done()) return;
    uint8_t m[ACT_COUNT];
    env_action_mask(E, m);
    if (!m[a]) {
        fprintf(stderr, "ILLEGAL %s seed=%llu step=%d px=%d py=%d\n", action_name(a),
                (unsigned long long)E->seed, E->steps, E->px, E->py);
        B.illegal = true;
        return;
    }
    int16_t before[ITEM_COUNT];
    memcpy(before, E->inv, sizeof before);
    uint32_t a0 = E->achievements;
    if (a == ACT_LEFT || a == ACT_RIGHT || a == ACT_JUMP) B.n_move++;
    else if (a >= ACT_MINE_FIRST && a < ACT_MINE_FIRST + REACH_COUNT) {
        Tile t = T(E->px + REACH_DX[a - ACT_MINE_FIRST], E->py + REACH_DY[a - ACT_MINE_FIRST]);
        if (t == TILE_IRON_ORE || t == TILE_GOLD_ORE || t == TILE_COPPER_ORE || t == TILE_SILVER_ORE || t == TILE_LOG) B.n_mine_ore++;
        else B.n_mine_other++;
    } else if (a == ACT_NOOP) {
        if (E->mine_cd) B.n_noop_cd++;
        else if (!player_grounded(E) || E->jump_left) B.n_noop_air++;
        else B.n_noop_other++;
    } else if (a >= ACT_PLACE_FIRST && a < ACT_PLACE_FIRST + REACH_COUNT) B.n_place++;
    else if (a >= RECIPE_FIRST_ACTION && a < RECIPE_FIRST_ACTION + RECIPE_COUNT) B.n_craft++;
    else B.n_misc++;
    env_step(E, a);
    if (B.verbose > 2) fprintf(stderr, "    %d %s -> (%d,%d) %s\n", E->steps, action_name(a), E->px, E->py, E->msg);
    if (B.nt < MAXTAPE) B.tape[B.nt++] = (uint8_t)a;
    if (a >= ACT_MINE_FIRST && a < ACT_MINE_FIRST + REACH_COUNT)
        for (int i = 0; i < ITEM_COUNT; i++)
            if (E->inv[i] > before[i]) B.got[i] += E->inv[i] - before[i];
    uint32_t nw = E->achievements & ~a0;
    for (int i = 0; i < ACH_COUNT; i++)
        if (nw >> i & 1u) {
            B.ach_step[i] = E->steps;
            B.last_progress = E->steps;
            if (B.verbose) fprintf(stderr, "  [%5d] %s\n", E->steps, ACH_NAME[i]);
        }
}

static bool mine_cell(int x, int y) {
    int r = reach_of(x, y);
    if (r < 0 || !mineable(x, y)) return false;
    if (E->mine_cd) act(ACT_NOOP);
    else act(ACT_MINE_FIRST + r);
    return true;
}
static bool select_slot(int slot) {
    if (E->selected == slot) return false;
    act(ACT_SELECT_FIRST + slot);
    return true;
}
/* Place a block from the bulk slot at (x,y); one action (select or place). */
static bool place_block(int x, int y) {
    int r = reach_of(x, y);
    if (r < 0 || T(x, y) != TILE_AIR || is_body(E, x, y)) return false;
    int s = blocks_slot();
    if (s < 0) return false;
    if (select_slot(s)) return true;
    act(ACT_PLACE_FIRST + r);
    B.placed_cell[B.n_placed++ & 63] = y * NW + x;
    return true;
}
static bool recently_placed(int x, int y) {
    int n = B.n_placed < 64 ? B.n_placed : 64;
    for (int i = 0; i < n; i++) if (B.placed_cell[i] == y * NW + x) return true;
    return false;
}

/* ----------------------------------------------------------- dijkstra -- */

enum { ET_WALK = 1, ET_BRIDGE, ET_FALL, ET_STEP, ET_DIG, ET_PILLAR };
static int dist_[NN], prev_[NN];
static uint8_t ety_[NN];
static uint64_t heap_[NN * 8];
static int hn;
static void hpush(uint64_t v) {
    int i = hn++;
    heap_[i] = v;
    while (i) {
        int p = (i - 1) >> 1;
        if (heap_[p] <= heap_[i]) break;
        uint64_t t = heap_[p]; heap_[p] = heap_[i]; heap_[i] = t; i = p;
    }
}
static uint64_t hpop(void) {
    uint64_t top = heap_[0];
    heap_[0] = heap_[--hn];
    int i = 0;
    for (;;) {
        int l = 2 * i + 1, r = l + 1, m = i;
        if (l < hn && heap_[l] < heap_[m]) m = l;
        if (r < hn && heap_[r] < heap_[m]) m = r;
        if (m == i) break;
        uint64_t t = heap_[m]; heap_[m] = heap_[i]; heap_[i] = t; i = m;
    }
    return top;
}
static inline void relax(int from, int x, int y, int d, int type) {
    if (x < 0 || x > NW - PLAYER_W || y < PLAYER_H - 1 || y > FEET_MAX) return;
    int id = y * NW + x;
    if (d >= dist_[id]) return;
    dist_[id] = d; prev_[id] = from; ety_[id] = (uint8_t)type;
    if (hn < NN * 8) hpush((uint64_t)d << 20 | (uint64_t)id);
}
static int fall_cost(int d, int c) {
    if (d <= FALL_SAFE) return d;
    return d + (d / 20) * (c + 3);
}
static int g_surface_best; /* nearest node above surface from last run */
static void dijkstra(int sx, int sy) {
    for (int i = 0; i < NN; i++) dist_[i] = INF;
    hn = 0;
    int c = mine_period();
    bool blocks = block_count() > 0;
    int s = sy * NW + sx;
    dist_[s] = 0; prev_[s] = -1; ety_[s] = 0;
    hpush((uint64_t)s);
    g_surface_best = -1;
    while (hn) {
        uint64_t v = hpop();
        int d = (int)(v >> 20), n = (int)(v & 0xFFFFF);
        if (d > dist_[n]) continue;
        int x = n % NW, y = n / NW;
        if (g_surface_best < 0 && y < E->surface[x]) g_surface_best = n;
        for (int dir = -1; dir <= 1; dir += 2) {
            int ax = x + dir, nx = dir > 0 ? x + 2 : x - 1;
            if (ax < 0 || ax > NW - PLAYER_W) continue;
            int k0 = ccost(nx, y), k1 = ccost(nx, y - 1), k2 = ccost(nx, y - 2);
            if (k0 >= 0 && k1 >= 0 && k2 >= 0) {
                int k = k0 + k1 + k2;
                if (supported_at(ax, y)) relax(n, ax, y, d + k + 1, ET_WALK << 1 | (dir > 0));
                else {
                    if (blocks && T(nx, y + 1) == TILE_AIR)
                        relax(n, ax, y, d + k + 2, ET_BRIDGE << 1 | (dir > 0));
                    int ly = land_from(ax, y), dd = ly - y;
                    if (dd <= FALL_SAFE || blocks)
                        relax(n, ax, ly, d + k + 1 + fall_cost(dd, c), ET_FALL << 1 | (dir > 0));
                }
            }
            if (SOL(nx, y) && y - 3 >= 0) {
                int a = ccost(x, y - 3), b = ccost(x + 1, y - 3), p = ccost(nx, y - 3),
                    q = ccost(nx, y - 2), r = ccost(nx, y - 1);
                if (a >= 0 && b >= 0 && p >= 0 && q >= 0 && r >= 0)
                    relax(n, ax, y - 1, d + a + b + p + q + r + 1, ET_STEP << 1 | (dir > 0));
            }
        }
        if (y + 1 <= FEET_MAX) {
            int k = 0;
            bool any = false, ok = true;
            for (int col = 0; col < 2; col++) {
                int cx = x + col, cy = y + 1;
                if (SUPC(cx, cy)) {
                    any = true;
                    if (!mineable(cx, cy)) { ok = false; break; }
                    k += tile_solid(T(cx, cy)) ? ccost(cx, cy) : c;
                }
            }
            if (any && ok) {
                int ly = land_from(x, y + 1), dd = ly - y;
                if (dd <= FALL_SAFE || blocks) relax(n, x, ly, d + k + fall_cost(dd, c), ET_DIG << 1);
            }
        }
        if (blocks && y - 3 >= 0 && y - 1 >= PLAYER_H - 1 &&
            (T(x, y) == TILE_AIR || T(x + 1, y) == TILE_AIR)) {
            int a = ccost(x, y - 3), b = ccost(x + 1, y - 3);
            if (a >= 0 && b >= 0) relax(n, x, y - 1, d + a + b + 2, ET_PILLAR << 1);
        }
    }
}
/* First edge on the path from the Dijkstra source to node g. */
static int first_edge(int g, int *dest) {
    int n = g;
    if (prev_[n] < 0) return 0;
    while (prev_[prev_[n]] >= 0) n = prev_[n];
    *dest = n;
    return ety_[n];
}

/* Full path (source excluded) to node g into B.path; returns its length. */
static int build_path(int g) {
    int n = 0;
    for (int v = g; v >= 0 && prev_[v] >= 0; v = prev_[v]) B.path[n++] = v;
    for (int i = 0; i < n / 2; i++) { int t = B.path[i]; B.path[i] = B.path[n - 1 - i]; B.path[n - 1 - i] = t; }
    B.path_len = n;
    return n;
}
/* Consecutive open pillar rows at the start of B.path (one jump covers <=6). */
static int pillar_chain(void) {
    int x = E->px, y = E->py, k = 0;
    for (int i = 0; i < B.path_len && k < JUMP_HEIGHT; i++) {
        int v = B.path[i];
        if ((ety_[v] >> 1) != ET_PILLAR || v % NW != x || v / NW != y - k - 1) break;
        if (SOL(x, y - 3 - k) || SOL(x + 1, y - 3 - k)) { if (k == 0) k = 1; break; }
        k++;
    }
    return k < 1 ? 1 : k;
}

/* Goal anchors from which cell (ox,oy) is within reach. With `lit` only cells
   4-adjacent to the body (player glow >= DARK_THRESHOLD) qualify. */
static int best_anchor(int ox, int oy, bool lit, int *best_d) {
    int best = -1, bd = INF;
    for (int ay = oy - 1; ay <= oy + 3; ay++)
        for (int ax = ox - 2; ax <= ox + 1; ax++) {
            if (ax < 0 || ax > NW - PLAYER_W || ay < PLAYER_H - 1 || ay > FEET_MAX) continue;
            int dx = ox - ax, dy = oy - ay;
            if (lit && (dx == -1 || dx == 2) && (dy == -3 || dy == 1)) continue;
            int d = dist_[ay * NW + ax];
            if (d < bd) { bd = d; best = ay * NW + ax; }
        }
    *best_d = bd;
    return best;
}

/* Anchors from which a mob at (mx,my) is in sword range once we face it. */
static int mob_anchor(int mx, int my, int *best_d) {
    int best = -1, bd = INF;
    for (int ay = my; ay <= my + PLAYER_H - 1; ay++)
        for (int ax = mx - PLAYER_W - 1; ax <= mx + 2; ax++) {
            if (ax < 0 || ax > NW - PLAYER_W || ay < PLAYER_H - 1 || ay > FEET_MAX) continue;
            int d = dist_[ay * NW + ax];
            if (d < bd) { bd = d; best = ay * NW + ax; }
        }
    *best_d = bd;
    return best;
}

/* ------------------------------------------------------------ executor -- */

static void exec_edge(int code, int chain) {
    int type = code >> 1, dir = (code & 1) ? 1 : -1;
    int x = E->px, y = E->py;
    int nx = dir > 0 ? x + 2 : x - 1;
    switch (type) {
    case ET_WALK: case ET_BRIDGE: case ET_FALL:
        for (int r = 0; r < 3; r++)
            if (SOL(nx, y - r)) { if (!mine_cell(nx, y - r)) act(ACT_NOOP); return; }
        if (type == ET_BRIDGE && !supported_at(x + dir, y) && T(nx, y + 1) == TILE_AIR) {
            if (place_block(nx, y + 1)) return;
        }
        act(dir > 0 ? ACT_RIGHT : ACT_LEFT);
        return;
    case ET_STEP: {
        int cells[5][2] = {{x, y - 3}, {x + 1, y - 3}, {nx, y - 3}, {nx, y - 2}, {nx, y - 1}};
        for (int i = 0; i < 5; i++)
            if (SOL(cells[i][0], cells[i][1])) { if (!mine_cell(cells[i][0], cells[i][1])) act(ACT_NOOP); return; }
        act(dir > 0 ? ACT_RIGHT : ACT_LEFT);
        return;
    }
    case ET_DIG:
        for (int col = 1; col >= 0; col--)
            if (SUPC(x + col, y + 1)) { if (!mine_cell(x + col, y + 1)) act(ACT_NOOP); return; }
        act(ACT_NOOP);
        return;
    case ET_PILLAR:
        for (int col = 0; col < 2; col++)
            if (SOL(x + col, y - 3)) { if (!mine_cell(x + col, y - 3)) act(ACT_NOOP); return; }
        { int s = blocks_slot(); if (s >= 0 && select_slot(s)) return; }
        B.pillar = true;
        B.pillar_y = y - chain;
        act(ACT_JUMP);
        return;
    }
    act(ACT_NOOP);
}

/* ------------------------------------------------------------- safety -- */

static bool mob_hittable(const Mob *m) {
    int edge = E->px + (E->facing > 0 ? PLAYER_W - 1 : 0), dx = m->x - edge;
    if (!m->kind) return false;
    if (!is_body(E, m->x, m->y) && (dx * E->facing < 0 || abs(dx) > 2)) return false;
    if (m->y < E->py - PLAYER_H + 1 || m->y > E->py) return false;
    for (int s = 1; s < abs(dx); s++)
        if (tile_solid(tile_at(E, edge + s * E->facing, m->y))) return false;
    return true;
}
static bool safety(void) {
    Env *e = E;
    if (e->inv[ITEM_LIFE_CRYSTAL] > 0 && e->max_health < HEALTH_CAP) { act(ACT_USE_CRYSTAL); return true; }
    if (!e->heal_cd && e->health < e->max_health) {
        bool first = !has_ach(e, ACH_HEAL);
        if (e->inv[ITEM_LESSER_POTION] > 0 && (e->health <= e->max_health - 50 || (first && e->inv[ITEM_MUSHROOM] == 0))) {
            act(ACT_HEAL_POTION); return true;
        }
        if (e->inv[ITEM_MUSHROOM] > 0 && (first || e->health <= e->max_health - 15)) { act(ACT_EAT_MUSHROOM); return true; }
    }
    if (!e->attack_cd)
        for (int i = 0; i < MAX_MOBS; i++)
            if (mob_hittable(&e->mobs[i])) { act(ACT_ATTACK); return true; }
    /* Turn toward a mob crowding our back so the next swing connects. */
    if (!e->attack_cd && standing())
        for (int i = 0; i < MAX_MOBS; i++) {
            const Mob *m = &e->mobs[i];
            if (!m->kind || m->y < e->py - 2 || m->y > e->py) continue;
            int back = e->facing > 0 ? e->px : e->px + 1;
            int dx = m->x - back;
            if (dx * e->facing < 0 && abs(dx) <= 2) {
                int a = e->facing > 0 ? ACT_LEFT : ACT_RIGHT;
                /* A turn is a move when the column (or a step-up) is free;
                   only turn in place. */
                int nxp = e->px - e->facing;
                bool moves = body_fits(e, nxp, e->py) ||
                             (player_grounded(e) && body_fits(e, nxp, e->py - 1) && body_fits(e, e->px, e->py - 1));
                if (!moves) { act(a); return true; }
            }
        }
    return false;
}

/* While airborne: finish pillar placements, arrest dangerous falls, take the
   double jump when it is free. */
static void airborne(void) {
    Env *e = E;
    if (e->inv[ITEM_CLOUD_BOTTLE] && !has_ach(e, ACH_DOUBLE_JUMP) && !B.pillar && e->jump_left == 0) {
        uint8_t m[ACT_COUNT]; env_action_mask(e, m);
        if (m[ACT_JUMP]) { act(ACT_JUMP); return; }
    }
    if (B.pillar) {
        if ((e->py <= B.pillar_y || e->jump_left == 0)) {
            for (int col = 0; col < 2; col++)
                if (T(e->px + col, e->py + 1) == TILE_AIR && place_block(e->px + col, e->py + 1)) return;
        }
        act(ACT_NOOP);
        return;
    }
    if (e->jump_left == 0) {
        int rem = land_from(e->px, e->py) - e->py;
        if (e->fall_dist + rem > FALL_SAFE && e->fall_dist >= 18) {
            if (place_block(e->px, e->py + 1) || place_block(e->px + 1, e->py + 1)) return;
        }
    }
    act(ACT_NOOP);
}

/* ------------------------------------------------------------ crafting -- */

static bool near_station(Tile t) {
    for (int dy = -PLAYER_H + 1 - STATION_RANGE; dy <= STATION_RANGE; dy++)
        for (int dx = -STATION_RANGE; dx < PLAYER_W + STATION_RANGE; dx++)
            if (tile_at(E, E->px + dx, E->py + dy) == t) return true;
    return false;
}
static int wood_reserve(void) {
    int r = 0;
    if (!has_ach(E, ACH_CRAFT_IRON_PICK)) r += 3;
    if (!has_ach(E, ACH_CRAFT_GOLD_PICK)) r += 4;
    if (!has_ach(E, ACH_CRAFT_FURNACE)) r += 4;
    return r;
}
/* Wood still to be spent on recipes we intend to craft. */
static int wood_needed(void) {
    int r = wood_reserve();
    if (!has_ach(E, ACH_CRAFT_WORKBENCH)) r += 10;
    if (!has_ach(E, ACH_CRAFT_WOOD_SWORD)) r += 7;
    if (!has_ach(E, ACH_CRAFT_WOOD_ARMOR)) r += 30;
    return r;
}
static bool furnace_owned(void) { return E->inv[ITEM_FURNACE] > 0 || has_ach(E, ACH_CRAFT_FURNACE); }

/* Next craft wanted now, or -1. *station receives the station tile needed.
   `valued` reports whether this craft earns a new achievement/tier. */
static int next_craft(Tile *station, bool *valued) {
    Env *e = E;
    int wood = e->inv[ITEM_WOOD];
    *valued = false;
    /* torches for the furnace and the place-torch achievement */
    if (e->inv[ITEM_GEL] > 0 && wood > 1 &&
        ((!furnace_owned() && e->inv[ITEM_TORCH] < 3) || (!has_ach(e, ACH_PLACE_TORCH) && e->inv[ITEM_TORCH] == 0 && furnace_owned()))) {
        *station = TILE_AIR; *valued = true; return ACT_CRAFT_TORCH;
    }
    if (!has_ach(e, ACH_PLACE_PLATFORM) && e->inv[ITEM_PLATFORM] == 0 && wood > wood_reserve() + 1) {
        *station = TILE_AIR; *valued = true; return ACT_CRAFT_PLATFORM;
    }
    bool have_wb = e->inv[ITEM_WORKBENCH] > 0 || near_station(TILE_WORKBENCH);
    if (!have_wb && wood >= 10) { *station = TILE_AIR; *valued = !has_ach(e, ACH_CRAFT_WORKBENCH); return ACT_CRAFT_WORKBENCH; }
    bool have_f = e->inv[ITEM_FURNACE] > 0 || near_station(TILE_FURNACE);
    if (have_f) {
        *station = TILE_FURNACE;
        if (e->inv[ITEM_COPPER_ORE] >= 3) { *valued = !has_ach(e, ACH_SMELT_COPPER); return ACT_SMELT_COPPER; }
        if (e->inv[ITEM_IRON_ORE] >= 3) { *valued = !has_ach(e, ACH_SMELT_IRON); return ACT_SMELT_IRON; }
        if (e->inv[ITEM_SILVER_ORE] >= 4) { *valued = !has_ach(e, ACH_SMELT_SILVER); return ACT_SMELT_SILVER; }
        if (e->inv[ITEM_GOLD_ORE] >= 4) { *valued = !has_ach(e, ACH_SMELT_GOLD); return ACT_SMELT_GOLD; }
    }
    if (have_wb) {
        *station = TILE_WORKBENCH;
        if (!have_f && e->inv[ITEM_STONE] >= 20 && wood >= 4 && e->inv[ITEM_TORCH] >= 3) {
            *valued = !has_ach(e, ACH_CRAFT_FURNACE); return ACT_CRAFT_FURNACE;
        }
        if (!has_ach(e, ACH_CRAFT_WOOD_SWORD) && wood >= 7 + wood_reserve()) { *valued = true; return ACT_CRAFT_WOOD_SWORD; }
        if (!has_ach(e, ACH_CRAFT_WOOD_ARMOR) && wood >= 30 + wood_reserve()) { *valued = true; return ACT_CRAFT_WOOD_ARMOR; }
        bool have_a = e->inv[ITEM_ANVIL] > 0 || near_station(TILE_ANVIL);
        if (!have_a && e->inv[ITEM_IRON_BAR] >= 5) { *valued = !has_ach(e, ACH_CRAFT_ANVIL); return ACT_CRAFT_ANVIL; }
    }
    bool have_a = e->inv[ITEM_ANVIL] > 0 || near_station(TILE_ANVIL);
    if (have_a) {
        *station = TILE_ANVIL;
        if (!has_ach(e, ACH_CRAFT_IRON_PICK) && e->inv[ITEM_IRON_BAR] >= 10 && wood >= 3) { *valued = true; return ACT_CRAFT_IRON_PICK; }
        if (!has_ach(e, ACH_CRAFT_GOLD_PICK) && e->inv[ITEM_GOLD_BAR] >= 10 && wood >= 4) { *valued = true; return ACT_CRAFT_GOLD_PICK; }
        if (!has_ach(e, ACH_CRAFT_METAL_SWORD) && e->inv[ITEM_COPPER_BAR] >= 6) { *valued = true; return ACT_CRAFT_COPPER_SWORD; }
        if (!has_ach(e, ACH_CRAFT_IRON_ARMOR) && e->inv[ITEM_IRON_BAR] >= 25 &&
            (has_ach(e, ACH_CRAFT_IRON_PICK) || e->inv[ITEM_IRON_BAR] >= 35)) { *valued = true; return ACT_CRAFT_IRON_ARMOR; }
    }
    return -1;
}

/* Would a session (smelt all ore, craft everything possible) earn something? */
static bool session_valuable(void) {
    /* Simulate crafts on a scratch copy of the inventory only: we pretend every
       owned station is nearby by placing nothing and checking recipes. */
    bool value = false;
    int16_t inv[ITEM_COUNT];
    memcpy(inv, E->inv, sizeof inv);
    uint8_t tier = E->tool_tier;
    uint32_t ach = E->achievements;
    for (int guard = 0; guard < 200; guard++) {
        Tile st; bool v;
        /* pretend stations we own are near: temporarily mark via inventory */
        int a = next_craft(&st, &v);
        if (a < 0) break;
        if (v) { value = true; break; }
        if (st != TILE_AIR && !(E->inv[st == TILE_WORKBENCH ? ITEM_WORKBENCH : st == TILE_FURNACE ? ITEM_FURNACE : ITEM_ANVIL] > 0 || near_station(st))) break;
        const Recipe *r = &RECIPES[a - RECIPE_FIRST_ACTION];
        bool ok = true;
        for (int i = 0; i < r->n_in; i++) if (E->inv[r->in_item[i]] < r->in_qty[i]) ok = false;
        if (!ok) break;
        for (int i = 0; i < r->n_in; i++) E->inv[r->in_item[i]] -= (int16_t)r->in_qty[i];
        if (r->out_item >= 0) E->inv[r->out_item] += (int16_t)r->out_qty;
        if (r->grant_tier > E->tool_tier) E->tool_tier = r->grant_tier;
        if (r->ach >= 0) E->achievements |= 1u << r->ach;
    }
    memcpy(E->inv, inv, sizeof inv);
    E->tool_tier = tier;
    E->achievements = ach;
    return value;
}

static Item station_item(Tile t) {
    return t == TILE_WORKBENCH ? ITEM_WORKBENCH : t == TILE_FURNACE ? ITEM_FURNACE : ITEM_ANVIL;
}
static int slot_of(Item it) {
    for (int i = 0; i < PLACEABLE_COUNT; i++) if (PLACEABLES[i].item == it) return i;
    return -1;
}
/* One action toward placing station tile t somewhere in reach. */
static bool place_station(Tile t) {
    int w = tile_object_w(t), h = tile_object_h(t);
    int best = -1, best_solid = 99;
    for (int r = 0; r < REACH_COUNT; r++) {
        int tx = E->px + REACH_DX[r], ty = E->py + REACH_DY[r];
        if (!in_bounds(tx, ty) || !in_bounds(tx + w - 1, ty - h + 1)) continue;
        int solid = 0;
        bool ok = true;
        for (int row = 0; row < h && ok; row++)
            for (int col = 0; col < w; col++) {
                int x = tx + col, y = ty - row;
                Tile c = T(x, y);
                if (c == TILE_AIR) continue;
                /* never dig our own footing or anything we cannot dig */
                if (!tile_solid(c) || !mineable(x, y) || y == E->py + 1 || reach_of(x, y) < 0) { ok = false; break; }
                solid++;
            }
        if (!ok) continue;
        if (solid < best_solid) { best_solid = solid; best = r; }
    }
    if (best < 0) return false;
    int tx = E->px + REACH_DX[best], ty = E->py + REACH_DY[best];
    if (best_solid > 0) {
        for (int row = 0; row < h; row++)
            for (int col = 0; col < w; col++)
                if (T(tx + col, ty - row) != TILE_AIR) { mine_cell(tx + col, ty - row); return true; }
    }
    if (select_slot(slot_of(station_item(t)))) return true;
    act(ACT_PLACE_FIRST + best);
    if (T(tx, ty) == t) { B.st_x[t] = tx; B.st_y[t] = ty; B.st_live[t] = true; }
    return true;
}
/* One action of a crafting session; false when the session is over. */
static bool session_step(void) {
    Tile st; bool v;
    int a = next_craft(&st, &v);
    if (B.verbose > 2) fprintf(stderr, "      session next=%s st=%d near=%d\n", a >= 0 ? action_name(a) : "-", st, a >= 0 ? near_station(st) : -1);
    if (a >= 0) {
        if (st == TILE_AIR || near_station(st)) {
            uint8_t m[ACT_COUNT]; env_action_mask(E, m);
            if (m[a]) { act(a); return true; }
        } else if (E->inv[station_item(st)] > 0) {
            if (place_station(st)) return true;
        }
    }
    /* pick placed stations back up (out-of-reach ones are recovered by decide) */
    for (int t = 0; t < TILE_COUNT; t++) {
        if (!B.st_live[t]) continue;
        for (int r = 0; r < REACH_COUNT; r++) {
            int x = E->px + REACH_DX[r], y = E->py + REACH_DY[r];
            if (T(x, y) == (Tile)t) { mine_cell(x, y); return true; }
        }
    }
    return false;
}

/* --------------------------------------------------------------- chores -- */

/* Cheap one-off achievements doable wherever we stand. */
static bool chores(void) {
    Env *e = E;
    /* Keep a small stock of bulk blocks: pillars, bridges and fall arrests
       all need one, and an empty pack can strand us in a pit. */
    if (block_count() < 6 && !e->mine_cd) {
        for (int r = 0; r < REACH_COUNT; r++) {
            int x = e->px + REACH_DX[r], y = e->py + REACH_DY[r];
            Tile t = T(x, y);
            if (t != TILE_DIRT && t != TILE_GRASS && t != TILE_STONE) continue;
            if (y == e->py + 1 && x >= e->px && x <= e->px + 1) continue; /* footing */
            if (y == e->py + 1 && block_count() > 0) continue; /* bridges and ledges */
            if (recently_placed(x, y) || !mineable(x, y)) continue;
            act(ACT_MINE_FIRST + r);
            return true;
        }
    }
    /* place block */
    if (!has_ach(e, ACH_PLACE_BLOCK)) {
        int s = blocks_slot();
        if (s < 0 && e->inv[ITEM_WOOD] > wood_reserve() + 40) s = 2;
        if (s >= 0) {
            static const int cand[][2] = {{-1, -2}, {2, -2}, {-1, -1}, {2, -1}};
            for (int i = 0; i < 4; i++) {
                int x = e->px + cand[i][0], y = e->py + cand[i][1];
                if (T(x, y) == TILE_AIR) {
                    if (select_slot(s)) return true;
                    act(ACT_PLACE_FIRST + reach_of(x, y));
                    return true;
                }
            }
        }
    }
    /* non-solid fixtures go into our own head cells */
    static const struct { int ach; Item it; } fix[] = {{ACH_PLACE_TORCH, ITEM_TORCH}, {ACH_PLACE_PLATFORM, ITEM_PLATFORM}};
    for (int k = 0; k < 2; k++) {
        if (has_ach(e, fix[k].ach) || e->inv[fix[k].it] <= 0) continue;
        if (fix[k].it == ITEM_TORCH && !furnace_owned() && e->inv[ITEM_TORCH] <= 3) continue;
        for (int col = 0; col < 2; col++) {
            int x = e->px + col, y = e->py - 2;
            if (T(x, y) == TILE_AIR) {
                if (select_slot(slot_of(fix[k].it))) return true;
                act(ACT_PLACE_FIRST + reach_of(x, y));
                return true;
            }
        }
    }
    /* climb rope: hang a rope in our middle cell, climb, come back, take it */
    if (!has_ach(e, ACH_CLIMB) && e->inv[ITEM_ROPE] > 0) {
        uint8_t m[ACT_COUNT]; env_action_mask(e, m);
        if (player_on_rope(e)) {
            if (m[ACT_CLIMB_UP]) { act(ACT_CLIMB_UP); return true; }
            if (m[ACT_CLIMB_DOWN]) { act(ACT_CLIMB_DOWN); return true; }
        } else if (T(e->px, e->py - 1) == TILE_AIR && body_fits(e, e->px, e->py - 1)) {
            if (select_slot(slot_of(ITEM_ROPE))) return true;
            act(ACT_PLACE_FIRST + reach_of(e->px, e->py - 1));
            return true;
        }
    }
    if (has_ach(e, ACH_CLIMB)) {
        for (int c = 0; c < 2; c++)
            for (int r = 0; r < 3; r++)
                if (T(e->px + c, e->py - r) == TILE_ROPE) {
                    if (e->mine_cd) {
                        /* hanging on a rope we placed: climb back down to the floor first */
                        act(ACT_NOOP);
                    } else act(ACT_MINE_FIRST + reach_of(e->px + c, e->py - r));
                    return true;
                }
    }
    /* double jump: needs two free rows above the head */
    if (e->inv[ITEM_CLOUD_BOTTLE] && !has_ach(e, ACH_DOUBLE_JUMP) && standing() &&
        body_fits(e, e->px, e->py - 2)) {
        act(ACT_JUMP);
        return true;
    }
    return false;
}

/* ----------------------------------------------------------- targeting -- */

static int count_got(int k) {
    Env *e = E;
    switch (k) {
    case K_IRON: return B.got[ITEM_IRON_ORE];
    case K_GOLD: return B.got[ITEM_GOLD_ORE];
    case K_COPPER: return B.got[ITEM_COPPER_ORE];
    default: (void)e; return B.got[ITEM_SILVER_ORE];
    }
}
static void refresh_want(void) {
    memset(want, 0, sizeof want);
    /* Scarce-tree worlds: chest-room wood floors cover the recipe deficit. */
    if (B.phase == P_DEEP && E->inv[ITEM_WOOD] < wood_needed() + (has_ach(E, ACH_PLACE_PLATFORM) ? 0 : 1))
        for (int y = 0; y < NH; y++)
            for (int x = 0; x < NW; x++)
                if (E->tiles[y][x] == TILE_WOOD) want[y][x] = 1;
    for (int k = 0; k < K_KINDS; k++) {
        if (count_got(k) >= B.need[k]) continue;
        for (int y = 0; y < NH; y++)
            for (int x = 0; x < NW; x++)
                if (E->tiles[y][x] == KIND_TILE[k]) want[y][x] = 1;
    }
}
static int chest_target(void) {
    for (int i = 2; i < E->chest_count; i++) {
        const Chest *c = &E->chests[i];
        if (!c->opened) return i;
    }
    return -1;
}

static bool opportunistic(void) {
    if (E->mine_cd) return false;
    if (E->inv[ITEM_MUSHROOM] + B.got[ITEM_MUSHROOM] < 1)
        for (int r = 0; r < REACH_COUNT; r++) {
            int x = E->px + REACH_DX[r], y = E->py + REACH_DY[r];
            if (T(x, y) == TILE_MUSHROOM) { act(ACT_MINE_FIRST + r); return true; }
        }
    for (int r = 0; r < REACH_COUNT; r++) {
        int x = E->px + REACH_DX[r], y = E->py + REACH_DY[r];
        if (!wanted(x, y) || !mineable(x, y)) continue;
        /* mining our only support starts a fall; allow when it lands safely */
        if (REACH_DY[r] == 1 && REACH_DX[r] >= 0 && REACH_DX[r] <= 1) {
            int other = E->px + (1 - REACH_DX[r]);
            if (!SUPC(other, y)) {
                int ly = land_from(E->px, E->py + 1);
                if (ly - E->py > FALL_SAFE) continue;
            }
        }
        act(ACT_MINE_FIRST + r);
        return true;
    }
    return false;
}

/* Surface wood plan: the shortest sweep [L,R] over tree trunks that yields
   the wood goal, visited near end first and then across. */
static int trunk_height(int x) {
    int y = E->surface[x] - 1, h = 0;
    while (y >= 0 && T(x, y) == TILE_LOG) { h++; y--; }
    return h;
}
static void plan_surface(void) {
    int xs[NW], hs[NW], n = 0, x0 = E->px;
    for (int x = 0; x < NW; x++) {
        int h = trunk_height(x);
        if (h > 0) { xs[n] = x; hs[n] = h; n++; }
    }
    int bi = -1, bj = -1, bc = INF;
    for (int i = 0; i < n; i++) {
        int w = 0;
        for (int j = i; j < n; j++) {
            w += hs[j];
            if (w < P.wood_goal) continue;
            int L = xs[i], R = xs[j];
            int c = (R - L) + (abs(x0 - L) < abs(x0 - R) ? abs(x0 - L) : abs(x0 - R));
            if (x0 > L && x0 < R) c = (R - L) + (x0 - L < R - x0 ? x0 - L : R - x0);
            if (c < bc) { bc = c; bi = i; bj = j; }
            break;
        }
    }
    if (B.verbose) fprintf(stderr, "  surface plan: %d trunks, interval [%d,%d] cost %d\n", n, bi >= 0 ? xs[bi] : -1, bj >= 0 ? xs[bj] : -1, bc);
    B.n_trees = 0;
    if (bi < 0) { for (int i = 0; i < n; i++) B.tree_order[B.n_trees++] = xs[i]; return; }
    int L = xs[bi], R = xs[bj];
    bool left_first = abs(x0 - L) <= abs(x0 - R);
    int near = left_first ? L : R;
    /* trees between x0 and the near end, nearest first */
    for (int k = 0; k < NW; k++)
        for (int sgn = 0; sgn < 1; sgn++) {
            int x = left_first ? x0 - k : x0 + k;
            if (x < L || x > R) continue;
            if (trunk_height(x) > 0) B.tree_order[B.n_trees++] = x;
        }
    /* then the sweep from the near end to the far end */
    for (int k = 0; k < NW; k++) {
        int x = left_first ? near + k : near - k;
        if (x < L || x > R) continue;
        if (left_first ? x <= x0 : x >= x0) continue;
        if (trunk_height(x) > 0) B.tree_order[B.n_trees++] = x;
    }
}

static double kind_weight(Tile t) {
    Env *e = E;
    if (!has_ach(e, ACH_CRAFT_IRON_PICK)) return t == TILE_GOLD_ORE ? P.w_gold_a : 1.0;
    if (!has_ach(e, ACH_CRAFT_GOLD_PICK)) return t == TILE_IRON_ORE ? P.w_iron_b : 1.0;
    return 1.0;
}

static bool mob_alive(int kind, int *sx, int *sy) {
    int best = INF;
    for (int i = 0; i < MAX_MOBS; i++) {
        const Mob *m = &E->mobs[i];
        if (m->kind != kind || !in_bounds(m->x, m->y)) continue;
        int d = abs(m->x - E->px) + abs(m->y - E->py);
        if (d < best) { best = d; *sx = m->x; *sy = m->y; }
    }
    return best < INF;
}
static bool slime_alive(int *sx, int *sy) {
    int best = INF;
    for (int i = 0; i < MAX_MOBS; i++) {
        const Mob *m = &E->mobs[i];
        if (m->kind != MOB_BLUE_SLIME) continue;
        int d = abs(m->x - E->px) + abs(m->y - E->py);
        if (d < best) { best = d; *sx = m->x; *sy = m->y; }
    }
    return best < INF;
}

/* Choose a target cell (or special goal) by Dijkstra distance. Fills
   B.tgt/B.tgt_kind; returns false when nothing remains. Dijkstra must have
   been run from the current position. */
static bool choose_target(void) {
    double best = 1e18;
    int bt = -1, bk = TK_NONE;
    Env *e = E;
    if (B.phase == P_SURFACE) {
        for (int i = 0; i < B.n_trees && bt < 0; i++) {
            int x = B.tree_order[i], y = e->surface[x] - 1;
            if (T(x, y) != TILE_LOG || B.bad[y][x]) continue;
            int d;
            best_anchor(x, y, false, &d);
            if (d < INF) { bt = y * NW + x; bk = TK_LOG; }
        }
    }
    if (B.phase == P_SURFACE && !has_ach(e, ACH_KILL_SLIME)) {
        int mx, my;
        if (e->steps >= B.mob_ignore_until && slime_alive(&mx, &my) && in_bounds(mx, my)) {
            int d;
            mob_anchor(mx, my, &d);
            if (d < 30) { bt = my * NW + mx; bk = TK_SLIME; }
        }
    }
    if (B.phase == P_SURFACE && bt < 0) B.phase = P_DEEP; /* sweep exhausted */
    if (B.phase == P_POST) {
        if (!has_ach(e, ACH_CRAFT_WOOD_ARMOR) && e->inv[ITEM_WOOD] < 30 + wood_reserve())
            for (int x = 0; x < NW; x++) {
                int y = e->surface[x] - 1;
                if (T(x, y) != TILE_LOG || B.bad[y][x]) continue;
                int d;
                best_anchor(x, y, false, &d);
                if (d < best) { best = d; bt = y * NW + x; bk = TK_LOG; }
            }
        int sx, sy;
        if (bt < 0 && !has_ach(e, ACH_KILL_SLIME) && e->steps >= B.mob_ignore_until && slime_alive(&sx, &sy) && in_bounds(sx, sy)) {
            bt = sy * NW + sx; bk = TK_SLIME;
        }
    }
    if (B.phase == P_DEEP) {
        for (int y = 0; y < NH; y++)
            for (int x = 0; x < NW; x++) {
                if (!wanted(x, y) || B.bad[y][x]) continue;
                int d;
                best_anchor(x, y, false, &d);
                if (d >= INF) continue;
                double sc = d * kind_weight(T(x, y));
                if (sc < best) { best = sc; bt = y * NW + x; bk = TK_ORE; }
            }
        int mx, my;
        if (!has_ach(e, ACH_KILL_BAT) && e->steps >= B.mob_ignore_until && mob_alive(MOB_CAVE_BAT, &mx, &my)) {
            int d;
            mob_anchor(mx, my, &d);
            if (d < 80) { best = -1e9; bt = my * NW + mx; bk = TK_SLIME; }
        }
        int ci = chest_target();
        if (!B.chest_done && ci >= 0) {
            const Chest *c = &e->chests[ci];
            int d;
            best_anchor(c->x, c->y, true, &d);
            if (d < INF && d - P.chest_bonus < best) { best = d - P.chest_bonus; bt = c->y * NW + c->x; bk = TK_CHEST; }
        }
        /* life crystal next to the opened chest */
        if (B.chest_done && !has_ach(e, ACH_USE_CRYSTAL))
            for (int y = 0; y < NH; y++)
                for (int x = 0; x < NW; x++)
                    if (E->tiles[y][x] == TILE_LIFE_CRYSTAL) {
                        int d;
                        best_anchor(x, y, false, &d);
                        if (d < INF && d - P.chest_bonus < best) { best = d - P.chest_bonus; bt = y * NW + x; bk = TK_CRYSTAL; }
                    }
        if (bt < 0 && !has_ach(e, ACH_DESCEND_DEEP)) {
            for (int y = DEEP_Y; y <= FEET_MAX; y++)
                for (int x = 0; x <= NW - PLAYER_W; x++)
                    if (dist_[y * NW + x] < best) { best = dist_[y * NW + x]; bt = y * NW + x; bk = TK_DEEP; }
        }
    }
    B.tgt = bt;
    B.tgt_kind = bk;
    B.tgt_age = 0;
    return bt >= 0;
}

/* Is the current target satisfied? */
static bool target_done(void) {
    if (B.tgt < 0) return true;
    int x = B.tgt % NW, y = B.tgt / NW;
    switch (B.tgt_kind) {
    case TK_ORE: return !wanted(x, y);
    case TK_LOG: return T(x, y) != TILE_LOG;
    case TK_MUSHROOM: return T(x, y) != TILE_MUSHROOM;
    case TK_CHEST: return T(x, y) != TILE_CHEST;
    case TK_CRYSTAL: return T(x, y) != TILE_LIFE_CRYSTAL;
    case TK_DEEP: return has_ach(E, ACH_DESCEND_DEEP);
    case TK_SLIME: return true; /* mobs move: re-aim every decision */
    case TK_STATION: return true;
    }
    return true;
}

/* Walk one edge toward node g. */
static void step_toward(int g) {
    if (g < 0 || dist_[g] >= INF) { act(ACT_NOOP); return; }
    build_path(g);
    if (!B.path_len) { act(ACT_NOOP); return; }
    if (B.verbose > 3) {
        fprintf(stderr, "      path d=%d:", dist_[g]);
        for (int i = 0; i < B.path_len && i < 8; i++)
            fprintf(stderr, " (%d,%d)t%d%c d%d", B.path[i] % NW, B.path[i] / NW, ety_[B.path[i]] >> 1, (ety_[B.path[i]] & 1) ? '+' : '-', dist_[B.path[i]]);
        fprintf(stderr, "\n");
    }
    exec_edge(ety_[B.path[0]], pillar_chain());
}

/* Act on the target: interact/mine when in reach, else path one edge. */
static void pursue(void) {
    int x = B.tgt % NW, y = B.tgt / NW;
    int d, g;
    if (B.tgt_kind == TK_SLIME) {
        if (B.mob_chase_start < 0) B.mob_chase_start = E->steps;
        if (E->steps - B.mob_chase_start > 90) {
            /* cannot corner it: ignore mobs for a while */
            B.mob_ignore_until = E->steps + 240; B.mob_chase_start = -1; B.tgt = -1; act(ACT_NOOP); return;
        }
        g = mob_anchor(x, y, &d);
        if (g == E->py * NW + E->px) {
            int dir = x >= E->px + 1 ? 1 : -1;
            if (E->facing != dir) {
                int nxp = E->px + dir;
                bool moves = body_fits(E, nxp, E->py) ||
                             (player_grounded(E) && body_fits(E, nxp, E->py - 1) && body_fits(E, E->px, E->py - 1));
                if (!moves) { act(dir > 0 ? ACT_RIGHT : ACT_LEFT); return; }
            }
            act(ACT_NOOP);
            return;
        }
        if (g < 0 || d >= INF) { B.mob_ignore_until = E->steps + 240; B.tgt = -1; act(ACT_NOOP); return; }
        step_toward(g);
        return;
    }
    B.mob_chase_start = -1;
    if (B.tgt_kind == TK_DEEP) { g = B.tgt; d = dist_[g]; }
    else g = best_anchor(x, y, B.tgt_kind == TK_CHEST, &d);
    if (g < 0 || d >= INF) { B.bad[y][x] = 1; B.tgt = -1; act(ACT_NOOP); return; }
    if (g == E->py * NW + E->px) {
        if (B.tgt_kind == TK_CHEST) {
            uint8_t m[ACT_COUNT]; env_action_mask(E, m);
            if (m[ACT_INTERACT]) { act(ACT_INTERACT); B.chest_done = 1; return; }
            B.bad[y][x] = 1; B.tgt = -1; act(ACT_NOOP); return;
        }
        if (B.tgt_kind == TK_DEEP || B.tgt_kind == TK_SLIME) { act(ACT_NOOP); return; }
        if (!mine_cell(x, y)) { B.bad[y][x] = 1; B.tgt = -1; act(ACT_NOOP); }
        return;
    }
    step_toward(g);
}

/* ---------------------------------------------------------------- brain -- */

static void start_session(void) { B.session = true; }

static void decide(void) {
    Env *e = E;
    if (safety()) return;
    if (!standing()) {
        if (!player_on_rope(e)) { if (!B.session && opportunistic()) return; airborne(); return; }
    }
    B.pillar = false;
    if (B.session) {
        if (session_step()) return;
        B.session = false;
        int s = blocks_slot();
        if (s >= 0 && select_slot(s)) return;
    }
    if (chores()) return;
    if (opportunistic()) return;
    refresh_want();
    dijkstra(e->px, e->py);
    /* never leave a placed station behind */
    for (int t = 0; t < TILE_COUNT; t++) {
        if (!B.st_live[t]) continue;
        if (T(B.st_x[t], B.st_y[t]) != (Tile)t) { B.st_live[t] = false; continue; }
        if (mine_cell(B.st_x[t], B.st_y[t])) return;
        int d, g = best_anchor(B.st_x[t], B.st_y[t], false, &d);
        if (g >= 0 && d < INF) { step_toward(g); return; }
        B.st_live[t] = false; /* unreachable: give up on it */
    }
    if (B.phase != P_SURFACE && session_valuable()) {
        start_session();
        if (session_step()) return;
        B.session = false;
    }
    if (B.phase == P_SURFACE && e->inv[ITEM_WOOD] >= P.wood_goal) {
        /* craft the wooden tier where we stand, then head down */
        B.phase = P_DEEP; B.tgt = -1;
        if (session_valuable()) { start_session(); if (session_step()) return; B.session = false; }
    }
    if (B.phase == P_DEEP) {
        /* time to go home? */
        int left = B.horizon - e->steps;
        int ret = g_surface_best >= 0 ? dist_[g_surface_best] : INF;
        if (has_ach(e, ACH_DESCEND_DEEP) && !has_ach(e, ACH_RETURN_SURFACE) && ret < INF &&
            left <= ret + ret / 4 + P.return_reserve) {
            if (B.verbose) fprintf(stderr, "  return at %d: left=%d ret=%d blocks=%d\n", e->steps, left, ret, block_count());
            B.phase = P_RETURN; B.tgt = -1;
        }
    }
    if (B.phase == P_RETURN) {
        if (has_ach(e, ACH_RETURN_SURFACE)) { B.phase = P_POST; B.tgt = -1; }
        else { step_toward(g_surface_best); return; }
    }
    if (B.tgt >= 0 && target_done()) B.tgt = -1;
    if (B.tgt >= 0 && ++B.tgt_age > 400) { B.bad[B.tgt / NW][B.tgt % NW] = 1; B.tgt = -1; }
    if (B.tgt < 0 && !choose_target()) {
        if (B.verbose) {
            int nw = 0, nb = 0, ni = 0;
            for (int y = 0; y < NH; y++) for (int x = 0; x < NW; x++) if (wanted(x, y)) {
                nw++; if (B.bad[y][x]) nb++; int d; best_anchor(x, y, false, &d); if (d >= INF) ni++; }
            int nl = 0; for (int x = 0; x < NW; x++) if (trunk_height(x) > 0) nl++;
            fprintf(stderr, "  no target at %d phase %d: wanted=%d bad=%d inf=%d trees=%d wood=%d armor=%d\n", e->steps, B.phase, nw, nb, ni, nl, e->inv[ITEM_WOOD], has_ach(e, ACH_CRAFT_WOOD_ARMOR));
        }
        if (B.phase == P_DEEP) { B.phase = has_ach(e, ACH_DESCEND_DEEP) ? P_RETURN : P_DEEP; }
        else if (B.phase == P_POST) {
            /* nothing left to chase: idle on the surface while slimes may spawn */
            if (!has_ach(e, ACH_KILL_SLIME)) { act(ACT_NOOP); return; }
            B.phase = P_DONE;
        }
        act(ACT_NOOP);
        return;
    }
    pursue();
}

/* ------------------------------------------------------- lower bounds -- */
/* Necessary-condition lower bounds on the earliest step at which each hard
   achievement can be earned in a world, independent of any planner. Every
   term counts actions that must occur (one per step) or physical rates that
   cannot be exceeded; tunnelling, enemies and path detours are ignored, so the
   bounds are loose but sound:
     - each ore/stone tile yields exactly one item per mine action; a felled
       trunk yields its height in wood per mine action, a wood block one;
     - mines are spaced by the pickaxe period 4-tier (3 copper, 2 iron, 1 gold)
       in force when each was made; upgrades need their recipes first;
     - every smelt/craft/placement/select/interact is its own action;
     - px changes by at most 1 per step and only through move actions;
     - feet descend at most 1 row per step and rise at most 2 rows per step. */
typedef struct { int iron, gold, metal, metal_kind, wood, smelts, crafts, stations; bool stone; bool torch; } Req;

static int lb_wood_mines(int wood, const int *yield, int n) {
    if (wood <= 0) return 0;
    int k = 0, sum = 0;
    for (int i = 0; i < n && sum < wood; i++) { sum += yield[i]; k++; }
    return sum >= wood ? k : INF;
}
/* Pickaxe-period chain: m1 mines at period p1, then m2 at p2, then m3 at p3. */
static int lb_chain(int m1, int p1, int m2, int p2, int m3, int p3) {
    int m = m1 + m2 + m3;
    if (m <= 0) return 0;
    long t = 1 + (long)p1 * m1 + (long)p2 * m2 + (long)p3 * m3;
    int plast = m3 ? p3 : m2 ? p2 : p1;
    return (int)(t - plast);
}
typedef struct {
    int col_iron[NW], col_gold[NW], col_copper[NW], col_silver[NW], col_wood[NW];
    int yield[NW * 2 + 64], n_yield;
    int rows[K_KINDS][NN / 4], n_rows[K_KINDS];
    int x0, y0;
} World;

static void lb_scan(World *w) {
    memset(w, 0, sizeof *w);
    w->x0 = E->px; w->y0 = E->py;
    for (int y = 0; y < NH; y++)
        for (int x = 0; x < NW; x++) {
            Tile t = (Tile)E->tiles[y][x];
            for (int k = 0; k < K_KINDS; k++)
                if (t == KIND_TILE[k] && w->n_rows[k] < NN / 4) w->rows[k][w->n_rows[k]++] = y;
            if (t == TILE_IRON_ORE) w->col_iron[x]++;
            if (t == TILE_GOLD_ORE) w->col_gold[x]++;
            if (t == TILE_COPPER_ORE) w->col_copper[x]++;
            if (t == TILE_SILVER_ORE) w->col_silver[x]++;
            if (t == TILE_WOOD) { w->col_wood[x]++; w->yield[w->n_yield++] = 1; }
        }
    for (int x = 0; x < NW; x++) {
        int h = trunk_height(x);
        if (h) { w->col_wood[x] += h; w->yield[w->n_yield++] = h; }
    }
    /* yields descending */
    for (int i = 0; i < w->n_yield; i++)
        for (int j = i + 1; j < w->n_yield; j++)
            if (w->yield[j] > w->yield[i]) { int t = w->yield[i]; w->yield[i] = w->yield[j]; w->yield[j] = t; }
    for (int k = 0; k < K_KINDS; k++)
        for (int i = 0; i < w->n_rows[k]; i++)
            for (int j = i + 1; j < w->n_rows[k]; j++)
                if (w->rows[k][j] < w->rows[k][i]) { int t = w->rows[k][i]; w->rows[k][i] = w->rows[k][j]; w->rows[k][j] = t; }
}
/* Horizontal moves: anchors span [a,b] containing x0; columns [a-1,b+2] must
   hold the required resources (wood counted by yield). */
static int lb_horizontal(const World *w, const Req *r) {
    int best = INF;
    for (int a = 0; a <= w->x0; a++)
        for (int b = w->x0; b <= NW - PLAYER_W; b++) {
            int fe = 0, au = 0, me = 0, wd = 0;
            for (int x = a - 1; x <= b + 2; x++) {
                if (x < 0 || x >= NW) continue;
                fe += w->col_iron[x]; au += w->col_gold[x]; wd += w->col_wood[x];
                me += r->metal_kind == K_COPPER ? w->col_copper[x] : r->metal_kind == K_SILVER ? w->col_silver[x]
                    : r->metal_kind == K_GOLD ? w->col_gold[x] : w->col_iron[x];
            }
            int need_fe = r->iron + (r->metal_kind == K_IRON ? r->metal : 0);
            int need_au = r->gold + (r->metal_kind == K_GOLD ? r->metal : 0);
            if (fe < need_fe || au < need_au || wd < r->wood) continue;
            if (r->metal && r->metal_kind != K_IRON && r->metal_kind != K_GOLD && me < r->metal) continue;
            int c = (b - a) + (w->x0 - a < b - w->x0 ? w->x0 - a : b - w->x0);
            if (c < best) best = c;
        }
    return best;
}
/* Descent: the n-th shallowest tile of each needed kind must be reached; the
   anchor feet sit at most one row above a mined cell. */
static int lb_depth(const World *w, const Req *r) {
    int deep = 0, need[K_KINDS] = {r->iron, r->gold, 0, 0};
    if (r->metal) need[r->metal_kind] += r->metal;
    for (int k = 0; k < K_KINDS; k++) {
        if (!need[k]) continue;
        if (need[k] > w->n_rows[k]) return INF;
        int row = w->rows[k][need[k] - 1] - 1;
        if (row > deep) deep = row;
    }
    return deep > w->y0 ? deep - w->y0 : 0;
}
static int lb_req(const World *w, const Req *r, bool needs_ipick, bool needs_gpick) {
    int stone = r->stone ? 20 : 0;
    int wm = lb_wood_mines(r->wood, w->yield, w->n_yield);
    if (wm >= INF) return INF;
    int fe = r->iron + (r->metal_kind == K_IRON ? r->metal : 0);
    int au = r->gold + (r->metal_kind == K_GOLD ? r->metal : 0);
    int other = (r->metal_kind == K_COPPER || r->metal_kind == K_SILVER) ? r->metal : 0;
    int mines = fe + au + other + stone + wm;
    /* mine-period chain, minimised over pickaxe upgrade orders */
    int chain = lb_chain(mines, 3, 0, 0, 0, 0);
    if (r->stone) {
        int ip_m = 45 + 20 + lb_wood_mines(17, w->yield, w->n_yield);
        int gp_m = 15 + 40 + 20 + lb_wood_mines(18, w->yield, w->n_yield);
        int tot_i = (fe > 45 ? fe : 45) + au + other + stone + lb_wood_mines(r->wood + (needs_ipick ? 0 : 3), w->yield, w->n_yield);
        int tot_g = (fe > 15 ? fe : 15) + (au > 40 ? au : 40) + other + stone + lb_wood_mines(r->wood + (needs_gpick ? 0 : 4), w->yield, w->n_yield);
        int tot_ig = (fe > 45 ? fe : 45) + (au > 40 ? au : 40) + other + stone +
                     lb_wood_mines(r->wood + (needs_ipick ? 0 : 3) + (needs_gpick ? 0 : 4), w->yield, w->n_yield);
        int c;
        if (tot_i >= ip_m) { c = lb_chain(ip_m, 3, tot_i - ip_m, 2, 0, 1); if (c < chain) chain = c; }
        if (tot_g >= gp_m) { c = lb_chain(gp_m, 3, 0, 2, tot_g - gp_m, 1); if (c < chain) chain = c; }
        if (tot_ig >= ip_m + 40) { c = lb_chain(ip_m, 3, 40, 2, tot_ig - ip_m - 40, 1); if (c < chain) chain = c; }
    }
    int h = lb_horizontal(w, r);
    if (h >= INF) return INF;
    int actions = mines + r->smelts + r->crafts + 2 * r->stations + (r->torch ? 1 : 0) + h;
    int depth = lb_depth(w, r);
    int t = chain > actions ? chain : actions;
    return t > depth ? t : depth;
}
static void lower_bounds(uint64_t seed) {
    memset(&B, 0, sizeof B);
    env_init(E, (EnvConfig){DEFAULT_MAX_STEPS});
    env_reset(E, seed);
    static World w;
    lb_scan(&w);
    /* cheapest metal sword: copper 18, iron 24, silver 28, gold 32 ore */
    static const int MK[4] = {K_COPPER, K_IRON, K_SILVER, K_GOLD}, MQ[4] = {18, 24, 28, 32}, MB[4] = {6, 8, 7, 8};
    int lb_anvil, lb_ip, lb_gp, lb_chainm, lb_breast, lb_sword = INF, lb_ret, lb_all = INF;
    Req r;
    r = (Req){.iron = 15, .wood = 14, .smelts = 5, .crafts = 3, .stations = 2, .stone = true, .torch = true};
    lb_anvil = lb_req(&w, &r, false, false);
    r = (Req){.iron = 45, .wood = 17, .smelts = 15, .crafts = 4, .stations = 3, .stone = true, .torch = true};
    lb_ip = lb_req(&w, &r, true, false);
    r = (Req){.iron = 15, .gold = 40, .wood = 18, .smelts = 15, .crafts = 4, .stations = 3, .stone = true, .torch = true};
    lb_gp = lb_req(&w, &r, false, true);
    r = (Req){.iron = 90, .wood = 14, .smelts = 30, .crafts = 4, .stations = 3, .stone = true, .torch = true};
    lb_chainm = lb_req(&w, &r, false, false);
    r = (Req){.wood = 40, .crafts = 2, .stations = 1};
    lb_breast = lb_req(&w, &r, false, false);
    for (int m = 0; m < 4; m++) {
        r = (Req){.iron = 15, .metal = MQ[m], .metal_kind = MK[m], .wood = 14, .smelts = 5 + MB[m], .crafts = 4,
                  .stations = 3, .stone = true, .torch = true};
        int v = lb_req(&w, &r, false, false);
        if (v < lb_sword) lb_sword = v;
        /* all seven hard achievements together */
        r = (Req){.iron = 120, .gold = 40, .metal = MQ[m], .metal_kind = MK[m], .wood = 51,
                  .smelts = 40 + 10 + MB[m], .crafts = 8, .stations = 3, .stone = true, .torch = true};
        v = lb_req(&w, &r, true, true);
        if (v < lb_all) lb_all = v;
    }
    /* return to surface: reach feet row DEEP_Y, then rise above the surface */
    int smax = 0;
    for (int x = 0; x < NW; x++) if (E->surface[x] > smax) smax = E->surface[x];
    lb_ret = (DEEP_Y - E->py) + (DEEP_Y - (smax - 1) + 1) / 2;
    int all = lb_all > lb_ret ? lb_all : lb_ret;
    int ore[K_KINDS];
    for (int k = 0; k < K_KINDS; k++) ore[k] = w.n_rows[k];
    int tw = 0;
    for (int i = 0; i < w.n_yield; i++) tw += w.yield[i];
    printf("{\"seed\":%llu,\"ore\":{\"iron\":%d,\"gold\":%d,\"copper\":%d,\"silver\":%d},\"wood_available\":%d,"
           "\"lb\":{\"craft anvil\":%d,\"craft iron pickaxe\":%d,\"craft gold pickaxe\":%d,\"craft iron chainmail\":%d,"
           "\"craft wood breastplate\":%d,\"craft metal sword\":%d,\"return to surface\":%d,\"all hard\":%d}}\n",
           (unsigned long long)seed, ore[K_IRON], ore[K_GOLD], ore[K_COPPER], ore[K_SILVER], tw,
           lb_anvil, lb_ip, lb_gp, lb_chainm, lb_breast, lb_sword, lb_ret, all);
}

/* ----------------------------------------------------------------- main -- */

static void run(uint64_t seed, int horizon, int verbose) {
    memset(&B, 0, sizeof B);
    B.verbose = verbose;
    env_init(E, (EnvConfig){horizon});
    env_reset(E, seed);
    B.horizon = horizon;
    for (int i = 0; i < ACH_COUNT; i++) B.ach_step[i] = -1;
    B.need[K_IRON] = 120; B.need[K_GOLD] = 40; B.need[K_COPPER] = 18; B.need[K_SILVER] = 4;
    B.tgt = -1;
    B.mob_chase_start = -1;
    B.phase = P_SURFACE;
    plan_surface();
    int same = 0;
    while (!done()) {
        int before = E->steps;
        if (B.verbose > 1 && E->steps % 50 == 0)
            fprintf(stderr, "  t=%d ph=%d pos=(%d,%d) hp=%d tgt=%d,%d k=%d inv: wood=%d stone=%d dirt=%d fe=%d au=%d cu=%d bars=%d/%d tier=%d\n",
                    E->steps, B.phase, E->px, E->py, E->health, B.tgt >= 0 ? B.tgt % NW : -1, B.tgt >= 0 ? B.tgt / NW : -1,
                    B.tgt_kind, E->inv[ITEM_WOOD], E->inv[ITEM_STONE], E->inv[ITEM_DIRT], E->inv[ITEM_IRON_ORE],
                    E->inv[ITEM_GOLD_ORE], E->inv[ITEM_COPPER_ORE], E->inv[ITEM_IRON_BAR], E->inv[ITEM_GOLD_BAR], E->tool_tier);
        decide();
        if (E->steps == before) {
            if (++same > 50) { fprintf(stderr, "stall seed=%llu step=%d\n", (unsigned long long)seed, E->steps); break; }
        } else same = 0;
        if (B.phase == P_DONE) break;
    }
}

static int g_verbose;
int main(int argc, char **argv) {
    uint64_t first = 23000001;
    int count = 1, horizon = DEFAULT_MAX_STEPS;
    const char *tapefile = NULL;
    bool lb_mode = false;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-h") && i + 1 < argc) horizon = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-s") && i + 1 < argc) first = strtoull(argv[++i], 0, 10);
        else if (!strcmp(argv[i], "-n") && i + 1 < argc) count = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-t") && i + 1 < argc) tapefile = argv[++i];
        else if (!strcmp(argv[i], "-v")) g_verbose++;
        else if (!strcmp(argv[i], "-L")) lb_mode = true;
        else if (!strcmp(argv[i], "-p") && i + 1 < argc) {
            char k[64]; double v;
            if (sscanf(argv[++i], "%63[^=]=%lf", k, &v) != 2) { fprintf(stderr, "bad -p\n"); return 2; }
            if (!strcmp(k, "w_gold_a")) P.w_gold_a = v;
            else if (!strcmp(k, "w_iron_b")) P.w_iron_b = v;
            else if (!strcmp(k, "chest_bonus")) P.chest_bonus = (int)v;
            else if (!strcmp(k, "return_reserve")) P.return_reserve = (int)v;
            else if (!strcmp(k, "wood_goal")) P.wood_goal = (int)v;
            else { fprintf(stderr, "unknown param %s\n", k); return 2; }
        }
    }
    init_reach();
    if (lb_mode) {
        for (int w = 0; w < count; w++) lower_bounds(first + (uint64_t)w);
        return 0;
    }
    FILE *tf = tapefile ? fopen(tapefile, "wb") : NULL;
    for (int w = 0; w < count; w++) {
        uint64_t seed = first + (uint64_t)w;
        run(seed, horizon, g_verbose);
        printf("{\"seed\":%llu,\"horizon\":%d,\"steps\":%d,\"score\":%d,\"died\":%s,\"illegal\":%s,\"ach_step\":[",
               (unsigned long long)seed, horizon, E->steps, __builtin_popcount(E->achievements),
               E->terminated ? "true" : "false", B.illegal ? "true" : "false");
        for (int i = 0; i < ACH_COUNT; i++) printf("%s%d", i ? "," : "", B.ach_step[i]);
        printf("],\"acts\":{\"move\":%d,\"mine_ore\":%d,\"mine_other\":%d,\"noop_cd\":%d,\"noop_air\":%d,\"noop_other\":%d,\"place\":%d,\"craft\":%d,\"misc\":%d}",
               B.n_move, B.n_mine_ore, B.n_mine_other, B.n_noop_cd, B.n_noop_air, B.n_noop_other, B.n_place, B.n_craft, B.n_misc);
        printf(",\"got\":{\"iron\":%d,\"gold\":%d,\"copper\":%d,\"silver\":%d,\"wood\":%d},\"health\":%d}\n",
               B.got[ITEM_IRON_ORE], B.got[ITEM_GOLD_ORE], B.got[ITEM_COPPER_ORE], B.got[ITEM_SILVER_ORE],
               B.got[ITEM_WOOD], E->health);
        fflush(stdout);
        if (tf) {
            uint32_t hdr[3] = {(uint32_t)(seed & 0xffffffffu), (uint32_t)horizon, (uint32_t)B.nt};
            fwrite(hdr, sizeof hdr, 1, tf);
            fwrite(B.tape, 1, (size_t)B.nt, tf);
        }
    }
    if (tf) fclose(tf);
    return 0;
}
