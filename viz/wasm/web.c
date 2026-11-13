/* WebAssembly entry points for viz/: the unmodified v8 core (default knobs, so
 * byte-identical to frozen v7) behind a flat, single-threaded API, plus the
 * few libc pieces the core needs. JavaScript reads Env fields directly from
 * linear memory through the offsets w_layout() reports, so nothing here copies
 * world state. Parallelism in the page comes from one module instance per
 * Web Worker, the same caller-owned-lanes model as src/capi.c.
 */
#include <stddef.h>
#include <stdint.h>
#include "shim.h"
#include "env.h"

#define EXPORT(n) __attribute__((export_name(n)))

/* ---- libc subset -------------------------------------------------------- */

void *memcpy(void *restrict d, const void *restrict s, size_t n) {
    unsigned char *a = d; const unsigned char *b = s;
    while (n--) *a++ = *b++;
    return d;
}
void *memset(void *d, int c, size_t n) {
    unsigned char *a = d;
    while (n--) *a++ = (unsigned char)c;
    return d;
}
void *memmove(void *d, const void *s, size_t n) {
    unsigned char *a = d; const unsigned char *b = s;
    if (a < b) while (n--) *a++ = *b++;
    else { a += n; b += n; while (n--) *--a = *--b; }
    return d;
}
size_t strlen(const char *s) { size_t n = 0; while (s[n]) n++; return n; }

/* %s %d %c %% only: every format sim.c's SAY uses. */
int vsnprintf(char *restrict out, size_t n, const char *restrict fmt, va_list ap) {
    size_t k = 0;
#define PUT(ch) do { if (k + 1 < n) out[k] = (ch); k++; } while (0)
    for (; *fmt; fmt++) {
        if (*fmt != '%') { PUT(*fmt); continue; }
        fmt++;
        if (*fmt == 's') { const char *s = va_arg(ap, const char *); while (s && *s) PUT(*s++); }
        else if (*fmt == 'd') {
            int v = va_arg(ap, int); char buf[12]; int m = 0;
            unsigned u = v < 0 ? 0u - (unsigned)v : (unsigned)v;
            do { buf[m++] = (char)('0' + u % 10); u /= 10; } while (u);
            if (v < 0) PUT('-');
            while (m) PUT(buf[--m]);
        } else if (*fmt == 'c') PUT((char)va_arg(ap, int));
        else if (*fmt == '%') PUT('%');
        else if (!*fmt) break;
    }
    if (n) out[k < n ? k : n - 1] = 0;
#undef PUT
    return (int)k;
}
int snprintf(char *restrict out, size_t n, const char *restrict fmt, ...) {
    va_list ap; va_start(ap, fmt);
    int r = vsnprintf(out, n, fmt, ap);
    va_end(ap);
    return r;
}

/* Bump allocator: the page allocates its envs and buffers once. */
extern unsigned char __heap_base;
static uintptr_t heap_top;
void *malloc(size_t n) {
    if (!heap_top) heap_top = (uintptr_t)&__heap_base;
    uintptr_t p = (heap_top + 15) & ~(uintptr_t)15, end = p + n;
    size_t have = __builtin_wasm_memory_size(0) * 65536u;
    if (end > have && __builtin_wasm_memory_grow(0, (end - have + 65535) / 65536) == (size_t)-1) return 0;
    heap_top = end;
    return (void *)p;
}
void free(void *p) { (void)p; }
void *calloc(size_t n, size_t m) { void *p = malloc(n * m); if (p) memset(p, 0, n * m); return p; }

EXPORT("w_malloc") void *w_malloc(int n) { return calloc(1, (size_t)n); }

/* ---- environments ------------------------------------------------------- */

EXPORT("w_create") Env *w_create(int max_steps) {
    Env *e = calloc(1, sizeof *e);
    if (!e) return 0;
    EnvConfig cfg = { max_steps };
    env_init(e, cfg);
    return e;
}
/* Seeds arrive as two uint32 halves: JS numbers are not uint64. */
EXPORT("w_reset") void w_reset(Env *e, uint32_t lo, uint32_t hi) {
    env_reset(e, ((uint64_t)hi << 32) | lo);
}
EXPORT("w_step") void w_step(Env *e, int action) { env_step(e, action); }
EXPORT("w_obs") void w_obs(const Env *e, Obs *o) { env_obs(e, o); }
EXPORT("w_mask") void w_mask(const Env *e, uint8_t *m) { env_action_mask(e, m); }
EXPORT("w_save") void w_save(const Env *e, void *out) { memcpy(out, e, sizeof *e); }
EXPORT("w_load") void w_load(Env *e, const void *in) { memcpy(e, in, sizeof *e); }

/* ---- layout and tables, so the page never hardcodes a constant ---------- */

enum {
    L_ENV_BYTES, L_OBS_BYTES, L_TILES, L_LIGHT, L_OBJECT_PART, L_PX, L_PY, L_FACING,
    L_JUMP_LEFT, L_FALL, L_HEALTH, L_MAX_HEALTH, L_TOOL_TIER, L_INV, L_SELECTED,
    L_WEAPON, L_ARMOR, L_MOBS, L_MOB_BYTES, L_CHESTS, L_CHEST_COUNT, L_ACH, L_RNG,
    L_SEED, L_STEPS, L_MAX_STEPS, L_REWARD, L_RETURN, L_TERMINATED, L_TRUNCATED,
    L_MSG, L_OBS_TILE, L_OBS_LIGHT, L_OBS_STATUS, L_WORLD_W, L_WORLD_H, L_VIEW_W,
    L_VIEW_H, L_TILE_COUNT, L_ITEM_COUNT, L_ACH_COUNT, L_ACT_COUNT, L_RECIPE_COUNT,
    L_REACH_COUNT, L_OBS_STATUS_LEN, L_OBS_SEL0, L_OBS_INV0, L_OBS_ACH0, L_OBS_ENTITY0,
    L_MINE_FIRST, L_PLACE_FIRST, L_SELECT_FIRST, L_PLACEABLE_COUNT, L_LIGHT_MAX,
    L_DARK, L_ENV_VERSION, L_RECIPE_FIRST, L_SKY_CUTOFF, L_SURFACE, L_MINING_TREE,
    L_TERRAIN_LIGHT, L_ATTACK_CD, L_MINE_CD, L_AIR_JUMP, L_DROP_TICKS, L_COUNT
};
EXPORT("w_layout") int w_layout(int *o) {
    o[L_ENV_BYTES] = sizeof(Env); o[L_OBS_BYTES] = sizeof(Obs);
    o[L_TILES] = offsetof(Env, tiles); o[L_LIGHT] = offsetof(Env, light);
    o[L_OBJECT_PART] = offsetof(Env, object_part); o[L_PX] = offsetof(Env, px);
    o[L_PY] = offsetof(Env, py); o[L_FACING] = offsetof(Env, facing);
    o[L_JUMP_LEFT] = offsetof(Env, jump_left); o[L_FALL] = offsetof(Env, fall_dist);
    o[L_HEALTH] = offsetof(Env, health); o[L_MAX_HEALTH] = offsetof(Env, max_health);
    o[L_TOOL_TIER] = offsetof(Env, tool_tier); o[L_INV] = offsetof(Env, inv);
    o[L_SELECTED] = offsetof(Env, selected); o[L_WEAPON] = offsetof(Env, weapon);
    o[L_ARMOR] = offsetof(Env, armor); o[L_MOBS] = offsetof(Env, mobs);
    o[L_MOB_BYTES] = sizeof(Mob); o[L_CHESTS] = offsetof(Env, chests);
    o[L_CHEST_COUNT] = offsetof(Env, chest_count); o[L_ACH] = offsetof(Env, achievements);
    o[L_RNG] = offsetof(Env, rng); o[L_SEED] = offsetof(Env, seed);
    o[L_STEPS] = offsetof(Env, steps); o[L_MAX_STEPS] = offsetof(Env, max_steps);
    o[L_REWARD] = offsetof(Env, reward); o[L_RETURN] = offsetof(Env, ep_return);
    o[L_TERMINATED] = offsetof(Env, terminated); o[L_TRUNCATED] = offsetof(Env, truncated);
    o[L_MSG] = offsetof(Env, msg); o[L_OBS_TILE] = offsetof(Obs, tile);
    o[L_OBS_LIGHT] = offsetof(Obs, light); o[L_OBS_STATUS] = offsetof(Obs, status);
    o[L_WORLD_W] = WORLD_W; o[L_WORLD_H] = WORLD_H; o[L_VIEW_W] = VIEW_W; o[L_VIEW_H] = VIEW_H;
    o[L_TILE_COUNT] = TILE_COUNT; o[L_ITEM_COUNT] = ITEM_COUNT; o[L_ACH_COUNT] = ACH_COUNT;
    o[L_ACT_COUNT] = ACT_COUNT; o[L_RECIPE_COUNT] = RECIPE_COUNT; o[L_REACH_COUNT] = REACH_COUNT;
    o[L_OBS_STATUS_LEN] = OBS_STATUS; o[L_OBS_SEL0] = OBS_SEL_0; o[L_OBS_INV0] = OBS_INV_0;
    o[L_OBS_ACH0] = OBS_ACH_0; o[L_OBS_ENTITY0] = OBS_ENTITY_0; o[L_MINE_FIRST] = ACT_MINE_FIRST;
    o[L_PLACE_FIRST] = ACT_PLACE_FIRST; o[L_SELECT_FIRST] = ACT_SELECT_FIRST;
    o[L_PLACEABLE_COUNT] = PLACEABLE_COUNT; o[L_LIGHT_MAX] = LIGHT_MAX; o[L_DARK] = DARK_THRESHOLD;
    o[L_ENV_VERSION] = ENV_VERSION; o[L_RECIPE_FIRST] = RECIPE_FIRST_ACTION;
    o[L_SKY_CUTOFF] = offsetof(Env, sky_cutoff); o[L_SURFACE] = offsetof(Env, surface);
    o[L_MINING_TREE] = offsetof(Env, mining_tree); o[L_TERRAIN_LIGHT] = offsetof(Env, terrain_light);
    o[L_ATTACK_CD] = offsetof(Env, attack_cd); o[L_MINE_CD] = offsetof(Env, mine_cd);
    o[L_AIR_JUMP] = offsetof(Env, air_jump_used); o[L_DROP_TICKS] = offsetof(Env, drop_ticks);
    return L_COUNT;
}

EXPORT("w_action_name") const char *w_action_name(int a) { return action_name(a); }
EXPORT("w_ach_name") const char *w_ach_name(int i) { return i >= 0 && i < ACH_COUNT ? ACH_NAME[i] : ""; }
EXPORT("w_item_name") const char *w_item_name(int i) { return i >= 0 && i < ITEM_COUNT ? ITEM_NAME[i] : ""; }
EXPORT("w_tile_name") const char *w_tile_name(int t) { return t >= 0 && t < TILE_COUNT ? TILE_INFO[t].name : "unknown"; }
EXPORT("w_tile_solid") int w_tile_solid(int t) { return t >= 0 && t < TILE_COUNT && TILE_INFO[t].solid; }
EXPORT("w_tile_object_w") int w_tile_object_w(int t) { return tile_object_w((Tile)t); }
EXPORT("w_tile_object_h") int w_tile_object_h(int t) { return tile_object_h((Tile)t); }
EXPORT("w_reach_dx") int w_reach_dx(int i) { return i >= 0 && i < REACH_COUNT ? REACH_DX[i] : 0; }
EXPORT("w_reach_dy") int w_reach_dy(int i) { return i >= 0 && i < REACH_COUNT ? REACH_DY[i] : 0; }
EXPORT("w_reach_name") const char *w_reach_name(int i) { return i >= 0 && i < REACH_COUNT ? REACH_NAME[i] : ""; }
EXPORT("w_placeable_item") int w_placeable_item(int i) { return i >= 0 && i < PLACEABLE_COUNT ? PLACEABLES[i].item : -1; }
EXPORT("w_recipe_name") const char *w_recipe_name(int r) { return r >= 0 && r < RECIPE_COUNT ? RECIPES[r].name : ""; }
EXPORT("w_recipe_inputs") int w_recipe_inputs(int r) { return r >= 0 && r < RECIPE_COUNT ? RECIPES[r].n_in : 0; }
EXPORT("w_recipe_in_item") int w_recipe_in_item(int r, int j) { return RECIPES[r].in_item[j]; }
EXPORT("w_recipe_in_qty") int w_recipe_in_qty(int r, int j) { return RECIPES[r].in_qty[j]; }
EXPORT("w_recipe_out") int w_recipe_out(int r) { return RECIPES[r].out_item; }
EXPORT("w_recipe_out_qty") int w_recipe_out_qty(int r) { return RECIPES[r].out_qty; }
EXPORT("w_recipe_station") int w_recipe_station(int r) { return RECIPES[r].station; }
EXPORT("w_recipe_ach") int w_recipe_ach(int r) { return RECIPES[r].ach; }
