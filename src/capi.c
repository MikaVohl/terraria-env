/* Flat C ABI for foreign callers (ctypes, cffi, anything with a struct-free
 * calling convention).
 *
 * Deliberately narrow: create/destroy, reset, step, observe, and a handful of
 * size queries so the caller never hardcodes a layout constant. Scalar calls
 * use plain buffers; the batch call uses Obs rows with an explicit byte-size
 * query and a checked ctypes layout. Buffer ownership always stays with callers.
 *
 * Observations are written into buffers the caller supplies. The caller also
 * chooses tile encoding: scalar/raw calls return IDs; the optional flat batch
 * call writes the binding's standard float32 one-hot layout directly. Embeddings
 * remain the consumer's business. Consumers must still check schema
 * metadata before loading a policy trained on another taxonomy.
 *
 * Native batching is synchronous, does not autoreset, and partitions independent
 * caller-owned lanes. No global mutable simulator state is shared by workers.
 */
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "env.h"
#ifdef __APPLE__
#include <dispatch/dispatch.h>
#endif

#if defined(_WIN32)
#  define TL_API __declspec(dllexport)
#else
#  define TL_API __attribute__((visibility("default")))
#endif

/* ---- layout queries, so a binding never hardcodes a constant ------------ */

TL_API int tl_view_w(void)      { return VIEW_W; }
TL_API int tl_env_version(void) { return ENV_VERSION; }
TL_API int tl_player_w(void) { return PLAYER_W; }
TL_API int tl_player_h(void) { return PLAYER_H; }
TL_API int tl_jump_height(void) { return JUMP_HEIGHT; }
TL_API int tl_fall_safe(void) { return FALL_SAFE; }
TL_API int tl_fall_damage(void) { return FALL_DMG_PER_TILE; }
TL_API int tl_health_cap(void) { return HEALTH_CAP; }
TL_API int tl_world_h(void) { return WORLD_H; }
TL_API int tl_status_depth(void) { return OBS_DEPTH; }
TL_API int tl_reach_count(void) { return REACH_COUNT; }
TL_API int tl_mine_first(void) { return ACT_MINE_FIRST; }
TL_API int tl_place_first(void) { return ACT_PLACE_FIRST; }
TL_API int tl_reach_dx(int i) { return i>=0&&i<REACH_COUNT?REACH_DX[i]:0; }
TL_API int tl_reach_dy(int i) { return i>=0&&i<REACH_COUNT?REACH_DY[i]:0; }
TL_API int tl_status_entity0(void) { return OBS_ENTITY_0; }
TL_API int tl_recipe_count(void) { return RECIPE_COUNT; }
TL_API const char *tl_recipe_name(int i) { return i>=0&&i<RECIPE_COUNT?RECIPES[i].name:""; }
TL_API int tl_recipe_inputs(int i) { return i>=0&&i<RECIPE_COUNT?RECIPES[i].n_in:0; }
TL_API int tl_recipe_item(int i,int j) { return i>=0&&i<RECIPE_COUNT&&j>=0&&j<RECIPES[i].n_in?RECIPES[i].in_item[j]:-1; }
TL_API int tl_recipe_qty(int i,int j) { return i>=0&&i<RECIPE_COUNT&&j>=0&&j<RECIPES[i].n_in?RECIPES[i].in_qty[j]:0; }
TL_API const char *tl_recipe_station(int i) { return i>=0&&i<RECIPE_COUNT?TILE_INFO[RECIPES[i].station].name:""; }
TL_API int tl_recipe_action(int i) { return i>=0&&i<RECIPE_COUNT?RECIPE_FIRST_ACTION+i:-1; }
TL_API int tl_item_terraria_id(int i) { return i>=0&&i<ITEM_COUNT?ITEM_TERRARIA_ID[i]:-1; }
TL_API int tl_view_h(void)      { return VIEW_H; }
TL_API int tl_view_cells(void)  { return VIEW_CELLS; }
TL_API int tl_tile_kinds(void)  { return OBS_TILE_KINDS; }
TL_API int tl_status_len(void)  { return OBS_STATUS; }
TL_API int tl_action_count(void){ return ACT_COUNT; }
TL_API int tl_ach_count(void)   { return ACH_COUNT; }
TL_API int tl_item_count(void)  { return ITEM_COUNT; }
TL_API int tl_unknown_tile(void){ return OBS_UNKNOWN; }
TL_API int tl_default_steps(void){ return DEFAULT_MAX_STEPS; }
TL_API int tl_status_inv0(void)  { return OBS_INV_0; }
TL_API int tl_status_ach0(void)  { return OBS_ACH_0; }
TL_API int tl_inv_clip(void)     { return OBS_INV_CLIP; }

TL_API const char *tl_action_name(int a) { return action_name(a); }
TL_API const char *tl_ach_name(int i)
{
    return (i >= 0 && i < ACH_COUNT) ? ACH_NAME[i] : "";
}
TL_API const char *tl_item_name(int i)
{
    return (i >= 0 && i < ITEM_COUNT) ? ITEM_NAME[i] : "";
}

/* Ascii glyph per tile, straight from TILE_INFO, so a text renderer on the
   other side of the boundary cannot drift from the taxonomy. */
TL_API int tl_tile_glyph(int t)
{
    return (t >= 0 && t < TILE_COUNT) ? TILE_INFO[t].glyph : '?';
}
TL_API const char *tl_tile_name(int t)
{
    return (t >= 0 && t < TILE_COUNT) ? TILE_INFO[t].name : "";
}

/* ---- lifecycle ---------------------------------------------------------- */

/* Env is ~39 KB, too big for a comfortable stack frame and opaque to the
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

TL_API void tl_observe(const Env *e,unsigned char *tile,unsigned char *light,float *status) {
    if(e) write_obs(e,tile,light,status);
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
TL_API int      tl_player_x(const Env *e)     { return e ? e->px : 0; }

/* ---- whole-state snapshots ----------------------------------------------
   Env owns no pointers (env_free is a no-op), so a byte copy is an exact,
   complete simulator state: world, lighting caches, RNG, step counter and
   achievements. Restoring continues the same episode deterministically.
   Blobs are only valid for the library build that produced them; callers
   keep them in memory and never persist them across builds. */
TL_API int  tl_state_bytes(void) { return (int)sizeof(Env); }
TL_API void tl_save_state(const Env *e, void *out) { if (e && out) memcpy(out, e, sizeof *e); }
TL_API void tl_load_state(Env *e, const void *in) { if (e && in) memcpy(e, in, sizeof *e); }

/* Writes tl_action_count() bytes, 1 where the action would change the state.
   A separate call rather than another out-parameter on tl_step: most callers
   never want it, and one extra FFI crossing costs far less than widening the
   hot path's signature. */
TL_API void tl_action_mask(const Env *e, unsigned char *mask)
{
    if (e && mask) env_action_mask(e, mask);
}

/* Independent lanes, caller-owned buffers, no autoreset or shared RNG. */
typedef struct {
 Env **envs; int n,workers; const int *actions; Obs *obs; float *flat;
 uint8_t *masks; float *rewards; int *ends;
} BatchCall;
#define FLAT_STRIDE (VIEW_CELLS*OBS_TILE_KINDS+VIEW_CELLS+OBS_STATUS)
static void encode_flat(const Obs *o,float *out) {
 const int terrain=VIEW_CELLS*OBS_TILE_KINDS;
 memset(out,0,(size_t)terrain*sizeof(float));
 for(int k=0;k<VIEW_CELLS;k++) {
  out[k*OBS_TILE_KINDS+o->tile[k]]=1.f;
  /* Double intermediate matches NumPy's uint8 / Python-float encoding. */
  out[terrain+k]=(float)((double)o->light[k]/15.);
 }
 memcpy(out+terrain+VIEW_CELLS,o->status,sizeof o->status);
}
static void batch_lane(void *context,size_t worker) {
 BatchCall *b=context;
 for(int i=(int)worker;i<b->n;i+=b->workers) {
  Env *e=b->envs[i]; env_step(e,b->actions[i]);
  Obs local; Obs *o=b->obs?&b->obs[i]:&local; env_obs(e,o);
  if(b->flat) encode_flat(o,b->flat+(size_t)i*FLAT_STRIDE);
  env_action_mask(e,b->masks+(size_t)i*ACT_COUNT); b->rewards[i]=e->reward;
  b->ends[i]=e->terminated?1:e->truncated?2:0;
 }
}

/* Run fn(ctx, w) for every worker w in [0, *workers). *workers is the lane
   stride the context uses; it is lowered before dispatch if the pool cannot
   provide that many threads. Lanes are independent and fixed per worker, so
   results never depend on thread count or scheduling. */
typedef void (*WorkerFn)(void*,size_t);
#if defined(__APPLE__)
static void run_workers(WorkerFn fn,void *ctx,int *workers) {
 if(*workers>1) { dispatch_apply_f((size_t)*workers,dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),ctx,fn); return; }
 fn(ctx,0);
}
#elif defined(__unix__)
/* Persistent pool, created lazily and grown on demand: spawning threads per
   step would cost as much as stepping a small batch. The caller thread runs
   worker 0; pool thread k runs worker k and is woken individually through its
   own semaphore, so idle pool threads are never woken (a broadcast to a large
   pool cost ~250 us per step). call_mu serialises concurrent callers (ctypes
   releases the GIL), since the pool holds one call at a time. */
#include <pthread.h>
#include <semaphore.h>
#include <stdatomic.h>
#define POOL_MAX 255
static pthread_mutex_t pool_call_mu=PTHREAD_MUTEX_INITIALIZER;
static sem_t pool_wake[POOL_MAX+1],pool_done;
static int pool_threads=-1;                /* -1: pool_done not initialised */
static WorkerFn pool_fn;
static void *pool_ctx;
static atomic_int pool_pending;
static void *pool_main(void *arg) {
 size_t id=(size_t)arg;
 for(;;) {
  while(sem_wait(&pool_wake[id])) {}          /* retry on EINTR */
  pool_fn(pool_ctx,id);
  if(atomic_fetch_sub(&pool_pending,1)==1) sem_post(&pool_done);
 }
 return NULL;
}
static void run_workers(WorkerFn fn,void *ctx,int *workers) {
 if(*workers>POOL_MAX+1) *workers=POOL_MAX+1;
 if(*workers<2) { fn(ctx,0); return; }
 pthread_mutex_lock(&pool_call_mu);
 if(pool_threads<0) { sem_init(&pool_done,0,0); pool_threads=0; }
 while(pool_threads<*workers-1) {
  pthread_t t; size_t id=(size_t)pool_threads+1;
  sem_init(&pool_wake[id],0,0);
  if(pthread_create(&t,NULL,pool_main,(void*)id)) { sem_destroy(&pool_wake[id]); break; }
  pthread_detach(t); pool_threads++;
 }
 if(*workers>pool_threads+1) *workers=pool_threads+1;  /* creation failed: fewer workers */
 int w=*workers;
 if(w>1) {
  /* sem_post/sem_wait order these writes before the workers read them. */
  pool_fn=fn; pool_ctx=ctx; atomic_store(&pool_pending,w-1);
  for(int k=1;k<w;k++) sem_post(&pool_wake[k]);
 }
 fn(ctx,0);
 if(w>1) while(sem_wait(&pool_done)) {}
 pthread_mutex_unlock(&pool_call_mu);
}
#else
static void run_workers(WorkerFn fn,void *ctx,int *workers) { for(int i=0;i<*workers;i++) fn(ctx,(size_t)i); }
#endif
static void run_batch(BatchCall *b) { run_workers(batch_lane,b,&b->workers); }

TL_API int tl_obs_bytes(void) { return sizeof(Obs); }
TL_API void tl_batch_step(Env **envs,int n,const int *actions,Obs *obs,
                         uint8_t *masks,float *rewards,int *ends,int workers) {
 if(n<=0 || !envs || !actions || !obs || !masks || !rewards || !ends) return;
 if(workers<1) workers=1;
 if(workers>n) workers=n;
 BatchCall b={envs,n,workers,actions,obs,NULL,masks,rewards,ends};
 run_batch(&b);
}

/* Equivalent encoded observations, written directly by independent C workers. */
TL_API void tl_batch_step_flat(Env **envs,int n,const int *actions,float *obs,
                              uint8_t *masks,float *rewards,int *ends,int workers) {
 if(n<=0 || !envs || !actions || !obs || !masks || !rewards || !ends) return;
 if(workers<1) workers=1;
 if(workers>n) workers=n;
 BatchCall b={envs,n,workers,actions,NULL,obs,masks,rewards,ends};
 run_batch(&b);
}

/* ---- native autoreset ---------------------------------------------------
   The Python VecTerraria contract, without a Python loop over finished lanes:
   step every lane (as above), then, for each lane whose episode ended (lane
   order), copy its terminal observation into final_obs, record its episode
   info, and reset it with the next consecutive seed (next_seed + k for the
   k-th finished lane), writing the fresh observation and mask in place.
   Rows of final_obs for lanes that did not finish are left untouched.
   obs/final_obs are float32 flat rows (flat=1) or raw Obs rows (flat=0).
   info rows hold (steps, health, depth, achievement mask) as int32 and
   info_return the episode return. Returns the number of lanes reset. */
typedef struct {
 Env **envs; const int *lanes; int count,workers,flat; unsigned long long next_seed;
 void *obs,*final_obs; uint8_t *masks; int *info; float *info_return;
} ResetCall;
static void reset_lane(void *context,size_t worker) {
 ResetCall *r=context;
 const size_t row=r->flat?FLAT_STRIDE*sizeof(float):sizeof(Obs);
 for(int k=(int)worker;k<r->count;k+=r->workers) {
  int i=r->lanes[k]; Env *e=r->envs[i];
  unsigned char *o=(unsigned char*)r->obs+(size_t)i*row;
  memcpy((unsigned char*)r->final_obs+(size_t)i*row,o,row);
  int *inf=r->info+(size_t)i*4;
  inf[0]=e->steps; inf[1]=e->health; inf[2]=e->py; inf[3]=(int)e->achievements;
  r->info_return[i]=e->ep_return;
  env_reset(e,(uint64_t)(r->next_seed+(unsigned long long)k));
  if(r->flat) { Obs tmp; env_obs(e,&tmp); encode_flat(&tmp,(float*)o); }
  else env_obs(e,(Obs*)o);
  env_action_mask(e,r->masks+(size_t)i*ACT_COUNT);
 }
}
TL_API int tl_batch_step_autoreset(Env **envs,int n,const int *actions,void *obs,int flat,
                                   uint8_t *masks,float *rewards,int *ends,void *final_obs,
                                   int *info,float *info_return,int *lanes,
                                   unsigned long long next_seed,int workers) {
 if(n<=0 || !envs || !actions || !obs || !masks || !rewards || !ends || !final_obs
    || !info || !info_return || !lanes) return -1;
 if(workers<1) workers=1;
 if(workers>n) workers=n;
 BatchCall b={envs,n,workers,actions,flat?NULL:(Obs*)obs,flat?(float*)obs:NULL,masks,rewards,ends};
 run_batch(&b);
 int count=0;
 for(int i=0;i<n;i++) if(ends[i]) lanes[count++]=i;
 if(count) {
  ResetCall r={envs,lanes,count,workers<count?workers:count,flat,next_seed,obs,final_obs,masks,info,info_return};
  run_workers(reset_lane,&r,&r.workers);
 }
 return count;
}

/* ---- progress-cell decode (python/terraria_lite/cells.py) ----------------
   For raw Obs rows: exact item counts rint(enc^2 * OBS_INV_CLIP) (the status
   encodes sqrt(count / clip)), the achievement bitmask, which of the given
   station tiles are visible, the player row rint(depth * (WORLD_H-1)) and the
   coarse cell key: h = achievements; then h = h*K ^ c over the inventory bins
   (edges <= count), the station flags and the depth band
   min(trunc(depth_f32 * bands), bands-1). Every value equals cells.py's NumPy
   definition bit for bit (perf/check_shaping.py); it exists because the
   shaping aids decode every lane on every step. Any output may be NULL. */
typedef struct {
 const Obs *rows; int n,workers; int n_stations;
 const long long *bin_edges; int n_edges,depth_bands;
 long long *inv; uint8_t *stations; long long *ach,*row,*key;
 uint32_t station_bits[256];      /* tile id -> bit t for station_tiles[t] */
} CellsCall;
/* rint() for the non-negative values decoded here, without a libm call:
   adding and subtracting 2^52 rounds to the nearest integer, ties to even,
   exactly like rint in the default rounding mode. */
static inline double rint_nonneg(double x) {
 return x>=0. && x<0x1p52 ? (x+0x1p52)-0x1p52 : rint(x);
}
static void cells_lane(void *context,size_t worker) {
 const CellsCall *c=context;
 for(int i=(int)worker;i<c->n;i+=c->workers) {
  const Obs *o=&c->rows[i]; const float *s=o->status;
  unsigned long long h=0;
  for(int j=0;j<ACH_COUNT;j++) if(s[OBS_ACH_0+j]>0.5f) h|=1ull<<j;
  if(c->ach) c->ach[i]=(long long)h;
  for(int j=0;j<ITEM_COUNT;j++) {
   double e=(double)s[OBS_INV_0+j];
   long long count=(long long)rint_nonneg(e*e*(double)OBS_INV_CLIP);
   if(c->inv) c->inv[(size_t)i*ITEM_COUNT+j]=count;
   unsigned long long bin=0;
   for(int k=0;k<c->n_edges;k++) bin+=c->bin_edges[k]<=count;
   h=h*0x9E3779B97F4A7C15ull^bin;
  }
  uint32_t seen=0;
  for(int k=0;k<VIEW_CELLS;k++) seen|=c->station_bits[o->tile[k]];
  for(int t=0;t<c->n_stations;t++) {
   unsigned long long flag=(seen>>t)&1u;
   if(c->stations) c->stations[(size_t)i*c->n_stations+t]=(uint8_t)flag;
   h=h*0x9E3779B97F4A7C15ull^flag;
  }
  float d=s[OBS_DEPTH];
  if(c->row) c->row[i]=(long long)rint_nonneg((double)d*(double)(WORLD_H-1));
  long long band=(long long)(d*(float)c->depth_bands);
  if(band>c->depth_bands-1) band=c->depth_bands-1;
  h=h*0x9E3779B97F4A7C15ull^(unsigned long long)band;
  if(c->key) c->key[i]=(long long)h;
 }
}
TL_API void tl_cells_decode(const Obs *rows,int n,const int *station_tiles,int n_stations,
                            const long long *bin_edges,int n_edges,int depth_bands,
                            long long *inv,uint8_t *stations,long long *ach,long long *row,
                            long long *key,int workers) {
 if(n<=0 || !rows || n_stations<0 || n_stations>32 || (n_stations>0 && !station_tiles)
    || (n_edges>0 && !bin_edges) || depth_bands<1) return;
 if(workers<1) workers=1;
 if(workers>n) workers=n;
 CellsCall c={rows,n,workers,n_stations,bin_edges,n_edges,depth_bands,inv,stations,ach,row,key,{0}};
 for(int t=0;t<n_stations;t++) c.station_bits[(uint8_t)station_tiles[t]]|=1u<<t;
 run_workers(cells_lane,&c,&c.workers);
}

/* ---- episodic count novelty (python/terraria_lite/count_novelty.py) -----
   Global visit counts per cell key and, per lane, the set of cells its current
   episode has entered. tl_novelty_step visits every lane's reached cell in
   lane order: count = ++visits[key]; if the episode has not entered the cell
   yet it is added and the lane is paid pow(count, -0.5) (the same libm pow as
   Python's `count ** -0.5`), else 0. tl_novelty_enter starts episodes: the
   lane's set becomes {key} and the cell gets one visit. */
typedef struct { unsigned long long *keys; long long *vals; uint8_t *used; size_t cap,size; } KeyMap;
static size_t keymap_slot(const KeyMap *m,unsigned long long key) {
 size_t i=(size_t)((key*0x9E3779B97F4A7C15ull)>>17)&(m->cap-1);
 while(m->used[i] && m->keys[i]!=key) i=(i+1)&(m->cap-1);
 return i;
}
static int keymap_init(KeyMap *m,size_t cap) {
 m->keys=malloc(cap*sizeof *m->keys); m->vals=malloc(cap*sizeof *m->vals); m->used=calloc(cap,1);
 m->cap=cap; m->size=0;
 return m->keys && m->vals && m->used;
}
static void keymap_free(KeyMap *m) { free(m->keys); free(m->vals); free(m->used); }
/* Slot holding key, inserted with value 0 if absent; NULL if out of memory. */
static long long *keymap_get(KeyMap *m,unsigned long long key,int *inserted) {
 size_t i=keymap_slot(m,key);
 *inserted=!m->used[i];
 if(*inserted) {
  if(2*(m->size+1)>m->cap) {
   KeyMap g; if(!keymap_init(&g,2*m->cap)) { keymap_free(&g); return NULL; }
   for(size_t j=0;j<m->cap;j++) if(m->used[j]) {
    size_t k=keymap_slot(&g,m->keys[j]); g.used[k]=1; g.keys[k]=m->keys[j]; g.vals[k]=m->vals[j];
   }
   g.size=m->size; keymap_free(m); *m=g; i=keymap_slot(m,key);
  }
  m->used[i]=1; m->keys[i]=key; m->vals[i]=0; m->size++;
 }
 return &m->vals[i];
}
typedef struct { KeyMap visits; KeyMap *seen; int n; } Novelty;
TL_API void tl_novelty_destroy(Novelty *v) {
 if(!v) return;
 keymap_free(&v->visits);
 if(v->seen) for(int i=0;i<v->n;i++) keymap_free(&v->seen[i]);
 free(v->seen); free(v);
}
TL_API Novelty *tl_novelty_create(int n) {
 if(n<=0) return NULL;
 Novelty *v=calloc(1,sizeof *v);
 if(!v) return NULL;
 v->n=n; v->seen=calloc((size_t)n,sizeof *v->seen);
 int ok=v->seen && keymap_init(&v->visits,4096);
 for(int i=0;ok && i<n;i++) ok=keymap_init(&v->seen[i],16);
 if(!ok) { tl_novelty_destroy(v); return NULL; }
 return v;
}
TL_API long long tl_novelty_cells(const Novelty *v) { return v?(long long)v->visits.size:0; }
/* Returns the number of lanes paid, or -1 if out of memory. */
TL_API int tl_novelty_step(Novelty *v,const long long *reached,float *bonus) {
 if(!v || !reached || !bonus) return -1;
 int paid=0,inserted;
 for(int i=0;i<v->n;i++) {
  unsigned long long key=(unsigned long long)reached[i];
  long long *count=keymap_get(&v->visits,key,&inserted);
  if(!count || !keymap_get(&v->seen[i],key,&inserted)) return -1;
  ++*count;
  bonus[i]=inserted?(float)pow((double)*count,-0.5):0.f;
  paid+=inserted;
 }
 return paid;
}
TL_API int tl_novelty_enter(Novelty *v,const int *lanes,const long long *keys,int count) {
 if(!v || (count>0 && (!lanes || !keys))) return -1;
 int inserted;
 for(int k=0;k<count;k++) {
  int i=lanes[k];
  if(i<0 || i>=v->n) return -1;
  KeyMap *s=&v->seen[i];
  memset(s->used,0,s->cap); s->size=0;
  long long *c=keymap_get(&v->visits,(unsigned long long)keys[k],&inserted);
  if(!c || !keymap_get(s,(unsigned long long)keys[k],&inserted)) return -1;
  ++*c;
 }
 return 0;
}
