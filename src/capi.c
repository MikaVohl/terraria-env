/* Flat C ABI for foreign callers (ctypes, cffi, anything with a struct-free
 * calling convention).
 *
 * Deliberately narrow: create/destroy, reset, step, observe, and a handful of
 * size queries so the caller never hardcodes a layout constant. Everything
 * crosses the boundary as scalars or caller-owned buffers, so there is no
 * struct layout to agree on and no ownership to negotiate.
 *
 * Observations are written into buffers the caller supplies. The caller also
 * chooses the tile encoding: this hands over ids, and one-hot (or an
 * embedding) is the consumer's business. That is what keeps adding a tile from
 * being an observation-layout change.
 *
 * Not vectorised. A batched entry point belongs here too when a trainer is
 * actually starved, and nothing in this file forecloses it.
 */
#include <stdlib.h>
#include <string.h>

#include "env.h"

#if defined(_WIN32)
#  define TL_API __declspec(dllexport)
#else
#  define TL_API __attribute__((visibility("default")))
#endif

/* ---- layout queries, so a binding never hardcodes a constant ------------ */

TL_API int tl_view_w(void)      { return VIEW_W; }
TL_API int tl_view_h(void)      { return VIEW_H; }
TL_API int tl_view_cells(void)  { return VIEW_CELLS; }
TL_API int tl_tile_kinds(void)  { return OBS_TILE_KINDS; }
TL_API int tl_status_len(void)  { return OBS_STATUS; }
TL_API int tl_action_count(void){ return ACT_COUNT; }
TL_API int tl_ach_count(void)   { return ACH_COUNT; }
TL_API int tl_item_count(void)  { return ITEM_COUNT; }
TL_API int tl_unknown_tile(void){ return OBS_UNKNOWN; }
TL_API int tl_default_steps(void){ return DEFAULT_MAX_STEPS; }

TL_API const char *tl_action_name(int a) { return action_name(a); }
TL_API const char *tl_ach_name(int i)
{
    return (i >= 0 && i < ACH_COUNT) ? ACH_NAME[i] : "";
}

/* Ascii glyph per tile, straight from TILE_INFO, so a text renderer on the
   other side of the boundary cannot drift from the taxonomy. */
TL_API int tl_tile_glyph(int t)
{
    return (t >= 0 && t < TILE_COUNT) ? TILE_INFO[t].glyph : '?';
}

/* ---- lifecycle ---------------------------------------------------------- */

/* Env is ~25 KB, too big for a comfortable stack frame and opaque to the
   caller, which only ever holds the pointer. */
TL_API Env *tl_create(int max_steps)
{
    EnvConfig cfg;
    Env *e = calloc(1, sizeof *e);
    if (!e) return NULL;
    cfg.max_steps = max_steps;
    env_init(e, cfg);
    return e;
}

TL_API void tl_destroy(Env *e)
{
    if (!e) return;
    env_free(e);
    free(e);
}

/* ---- stepping ----------------------------------------------------------- */

/* Any of the three output pointers may be NULL, so a caller that only wants
   the status vector does not have to allocate a map. */
static void write_obs(const Env *e, unsigned char *tile, unsigned char *light,
                      float *status)
{
    Obs o;
    if (!tile && !light && !status) return;
    env_obs(e, &o);
    if (tile)   memcpy(tile,   o.tile,   sizeof o.tile);
    if (light)  memcpy(light,  o.light,  sizeof o.light);
    if (status) memcpy(status, o.status, sizeof o.status);
}

TL_API void tl_reset(Env *e, unsigned long long seed,
                     unsigned char *tile, unsigned char *light, float *status)
{
    if (!e) return;
    env_reset(e, (uint64_t)seed);
    write_obs(e, tile, light, status);
}

/* One action, one tick -- the same contract the frontends get. `reward` is for
   the step just taken; terminated (died) and truncated (out of steps) stay
   separate so a value bootstrap can tell them apart. */
TL_API void tl_step(Env *e, int action,
                    unsigned char *tile, unsigned char *light, float *status,
                    float *reward, int *terminated, int *truncated)
{
    if (!e) return;
    env_step(e, action);
    write_obs(e, tile, light, status);
    if (reward)     *reward     = e->reward;
    if (terminated) *terminated = e->terminated ? 1 : 0;
    if (truncated)  *truncated  = e->truncated ? 1 : 0;
}

/* ---- read-only introspection, for logging and debugging ----------------- */

TL_API int      tl_steps(const Env *e)        { return e ? e->steps : 0; }
TL_API float    tl_return(const Env *e)       { return e ? e->ep_return : 0.0f; }
TL_API int      tl_health(const Env *e)       { return e ? e->health : 0; }
TL_API int      tl_depth(const Env *e)        { return e ? e->py : 0; }
TL_API unsigned tl_achievements(const Env *e) { return e ? e->achievements : 0u; }
TL_API const char *tl_message(const Env *e)   { return e ? e->msg : ""; }

/* Writes tl_action_count() bytes, 1 where the action would change the state.
   A separate call rather than another out-parameter on tl_step: most callers
   never want it, and one extra FFI crossing costs far less than widening the
   hot path's signature. */
TL_API void tl_action_mask(const Env *e, unsigned char *mask)
{
    if (e && mask) env_action_mask(e, mask);
}
