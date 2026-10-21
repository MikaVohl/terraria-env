/* ctypes-facing launcher library: the caller (PyTorch) owns every device
 * buffer and passes raw pointers plus its HIP stream. Loaded after `import
 * torch`, so the HIP runtime (same SONAME) is shared with PyTorch. */
#include "gpusim_kernels.h"

#define API extern "C" __attribute__((visibility("default")))
static int nb(long long n, int b) { return (int)((n + b - 1) / b); }
static int err() { return (int)hipGetLastError(); }

API int gs_state_bytes(void) { return (int)sizeof(Env); }
API int gs_obs_bytes(void) { return (int)sizeof(Obs); }
API int gs_flat_size(void) { return GS_FLAT; }
API int gs_status_len(void) { return OBS_STATUS; }
API int gs_act_count(void) { return ACT_COUNT; }

API int gs_init(void *env, int n, int max_steps, void *stream) {
    k_init<<<nb(n, 128), 128, 0, (hipStream_t)stream>>>((Env *)env, n, max_steps);
    return err();
}
/* Worldgen on device for `count` lanes (idx NULL: lanes 0..count-1). obs/masks may be NULL. */
API int gs_reset(void *env, const int *idx, const uint64_t *seeds, int count, void *obs, void *masks, void *stream) {
    if (count <= 0) return 0;
    k_reset<<<nb(count, 64), 64, 0, (hipStream_t)stream>>>((Env *)env, idx, seeds, count, (Obs *)obs, (uint8_t *)masks);
    return err();
}
API int gs_step(void *env, int n, const int *actions, void *obs, void *masks, float *rew, int *ends, void *stream) {
    k_step<<<nb(n, 256), 256, 0, (hipStream_t)stream>>>((Env *)env, n, actions, (Obs *)obs, (uint8_t *)masks, rew, ends);
    return err();
}

/* Lane-ordered pool reset: slot[i] (precomputed by the caller, e.g. cursor +
   cumsum(ends!=0)-1, so finished lanes take consecutive pool entries in lane
   order exactly like VecTerraria's seed counter) is copied into lane i when
   ends[i] != 0, then obs/mask are recomputed for that lane. */
__global__ void k_pool_masked(Env *envs, int n, const int *ends, const long long *slot, const Env *pool, int pool_n) {
    int i = blockIdx.x;
    if (i >= n || !ends[i]) return;
    const uint4 *src = (const uint4 *)&pool[slot[i] % pool_n];
    uint4 *dst = (uint4 *)&envs[i];
    for (int k = threadIdx.x; k < (int)(sizeof(Env) / 16); k += blockDim.x) dst[k] = src[k];
}
__global__ void k_obs_mask_masked(Env *envs, int n, const int *ends, Obs *obs, uint8_t *masks) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n || !ends[i]) return;
    env_obs(&envs[i], &obs[i]);
    env_action_mask(&envs[i], masks + (size_t)i * ACT_COUNT);
}
API int gs_reset_from_pool(void *env, int n, const int *ends, const long long *slot, const void *pool, int pool_n,
                           void *obs, void *masks, void *stream) {
    hipStream_t s = (hipStream_t)stream;
    k_pool_masked<<<n, 256, 0, s>>>((Env *)env, n, ends, slot, (const Env *)pool, pool_n);
    k_obs_mask_masked<<<nb(n, 64), 64, 0, s>>>((Env *)env, n, ends, (Obs *)obs, (uint8_t *)masks);
    return err();
}
/* Before a pool reset: for finished lanes, keep the terminal observation row
   and the episode info (steps, health, depth, achievement mask; return) that
   VecTerraria reports for them. */
__global__ void k_capture(const Env *envs, int n, const int *ends, const Obs *obs, Obs *final_obs,
                          int *info, float *info_return) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n || !ends[i]) return;
    const Env *e = &envs[i];
    final_obs[i] = obs[i];
    info[4 * i] = e->steps; info[4 * i + 1] = e->health; info[4 * i + 2] = e->py;
    info[4 * i + 3] = (int)e->achievements;
    info_return[i] = e->ep_return;
}
API int gs_capture(const void *env, int n, const int *ends, const void *obs, void *final_obs,
                   int *info, float *info_return, void *stream) {
    k_capture<<<nb(n, 128), 128, 0, (hipStream_t)stream>>>((const Env *)env, n, ends, (const Obs *)obs,
                                                        (Obs *)final_obs, info, info_return);
    return err();
}
API int gs_encode(const void *obs, long long n, float *flat, void *stream) {
    k_encode<<<nb(n * GS_FLAT, 256), 256, 0, (hipStream_t)stream>>>((const Obs *)obs, n, flat);
    return err();
}
