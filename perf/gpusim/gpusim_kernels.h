/* Batched device kernels around the verbatim core: one environment per GPU
 * thread, Env state resident in device memory, outputs written straight into
 * device buffers. */
#pragma once
#include "gpusim_core.h"
#include <stdint.h>

#define GS_FLAT (VIEW_CELLS*OBS_TILE_KINDS+VIEW_CELLS+OBS_STATUS)

__global__ void k_init(Env *envs, int n, int max_steps) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    EnvConfig c; c.max_steps = max_steps;
    env_init(&envs[i], c);
}

/* Reset a list of lanes (idx may be NULL: lanes 0..count-1). */
__global__ void k_reset(Env *envs, const int *idx, const uint64_t *seeds, int count,
                        Obs *obs, uint8_t *masks) {
    int t = blockIdx.x * blockDim.x + threadIdx.x;
    if (t >= count) return;
    int i = idx ? idx[t] : t;
    Env *e = &envs[i];
    env_reset(e, seeds[t]);
    if (obs) env_obs(e, &obs[i]);
    if (masks) env_action_mask(e, masks + (size_t)i * ACT_COUNT);
}

/* The tl_batch_step contract: step, observe, mask, reward, end code. */
__global__ void k_step(Env *envs, int n, const int *actions, Obs *obs, uint8_t *masks,
                       float *rewards, int *ends) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    Env *e = &envs[i];
    env_step(e, actions[i]);
    env_obs(e, &obs[i]);
    env_action_mask(e, masks + (size_t)i * ACT_COUNT);
    rewards[i] = e->reward;
    ends[i] = e->terminated ? 1 : e->truncated ? 2 : 0;
}

/* Same, but finished lanes are reset in-kernel with seed base + lane*2^20 +
   per-lane episode counter (deterministic, independent of scheduling). */
__global__ void k_step_autoreset(Env *envs, int n, const int *actions, Obs *obs, uint8_t *masks,
                                 float *rewards, int *ends, uint32_t *episodes, uint64_t seed_base) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    Env *e = &envs[i];
    env_step(e, actions[i]);
    rewards[i] = e->reward;
    int end = e->terminated ? 1 : e->truncated ? 2 : 0;
    ends[i] = end;
    if (end) env_reset(e, seed_base + ((uint64_t)i << 20) + episodes[i]++);
    env_obs(e, &obs[i]);
    env_action_mask(e, masks + (size_t)i * ACT_COUNT);
}

/* Step only; finished lanes are listed for a separate (compacted) reset pass. */
__global__ void k_step_mark(Env *envs, int n, const int *actions, Obs *obs, uint8_t *masks,
                            float *rewards, int *ends, int *done_idx, int *done_count) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    Env *e = &envs[i];
    env_step(e, actions[i]);
    rewards[i] = e->reward;
    int end = e->terminated ? 1 : e->truncated ? 2 : 0;
    ends[i] = end;
    if (end) { done_idx[atomicAdd(done_count, 1)] = i; return; }
    env_obs(e, &obs[i]);
    env_action_mask(e, masks + (size_t)i * ACT_COUNT);
}

/* k_step_mark with outputs staged in LDS and written back as contiguous,
   coalesced 16-byte words (per-lane Obs/mask records are otherwise scattered
   2144/72-byte stores). B threads per block; B*2216 bytes of LDS. */
template <int B>
__global__ void __launch_bounds__(B) k_step_mark_coop(Env *envs, int n, const int *actions, Obs *obs, uint8_t *masks,
                                 float *rewards, int *ends, int *done_idx, int *done_count) {
    __shared__ uint4 sh_obs[B * sizeof(Obs) / 16];
    __shared__ uint4 sh_mask[(B * ACT_COUNT + 15) / 16];
    int base = blockIdx.x * B, i = base + threadIdx.x;
    if (i < n) {
        Env *e = &envs[i];
        env_step(e, actions[i]);
        rewards[i] = e->reward;
        int end = e->terminated ? 1 : e->truncated ? 2 : 0;
        ends[i] = end;
        if (end) done_idx[atomicAdd(done_count, 1)] = i;
        env_obs(e, (Obs *)sh_obs + threadIdx.x);   /* finished lanes are overwritten after reset */
        env_action_mask(e, (uint8_t *)sh_mask + threadIdx.x * ACT_COUNT);
    }
    __syncthreads();
    int lanes = n - base < B ? n - base : B;
    uint4 *go = (uint4 *)(obs + base);
    for (int k = threadIdx.x; k < lanes * (int)(sizeof(Obs) / 16); k += B) go[k] = sh_obs[k];
    uint8_t *gm = masks + (size_t)base * ACT_COUNT, *sm = (uint8_t *)sh_mask;
    if (lanes == B) { for (int k = threadIdx.x; k < B * ACT_COUNT / 16; k += B) ((uint4 *)gm)[k] = sh_mask[k]; }
    else for (int k = threadIdx.x; k < lanes * ACT_COUNT; k += B) gm[k] = sm[k];
}

/* Reset from a pool of pre-generated initial states: a block-cooperative,
   coalesced 38.7 KB copy per finished lane (no worldgen divergence). */
__global__ void k_reset_from_pool(Env *envs, const int *done_idx, const int *done_count,
                                  const Env *pool, int pool_n, uint32_t *pool_cursor) {
    int count = *done_count;
    __shared__ int slot;
    for (int t = blockIdx.x; t < count; t += gridDim.x) {
        int i = done_idx[t];
        if (threadIdx.x == 0) slot = (int)(atomicAdd(pool_cursor, 1u) % (uint32_t)pool_n);
        __syncthreads();
        const uint4 *src = (const uint4 *)&pool[slot];
        uint4 *dst = (uint4 *)&envs[i];
        for (int k = threadIdx.x; k < (int)(sizeof(Env) / 16); k += blockDim.x) dst[k] = src[k];
        __syncthreads();
    }
}

__global__ void k_obs_mask_list(Env *envs, const int *done_idx, const int *done_count,
                                Obs *obs, uint8_t *masks) {
    int t = blockIdx.x * blockDim.x + threadIdx.x;
    if (t >= *done_count) return;
    int i = done_idx[t];
    env_obs(&envs[i], &obs[i]);
    env_action_mask(&envs[i], masks + (size_t)i * ACT_COUNT);
}

__global__ void k_reset_list(Env *envs, const int *done_idx, const int *done_count,
                             uint32_t *episodes, uint64_t seed_base, Obs *obs, uint8_t *masks) {
    int t = blockIdx.x * blockDim.x + threadIdx.x;
    if (t >= *done_count) return;
    int i = done_idx[t];
    Env *e = &envs[i];
    env_reset(e, seed_base + ((uint64_t)i << 20) + episodes[i]++);
    env_obs(e, &obs[i]);
    env_action_mask(e, masks + (size_t)i * ACT_COUNT);
}

/* Uniform over legal actions, from a counter-based hash (no state). */
__device__ __forceinline__ uint64_t gs_hash(uint64_t x) {
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}
__global__ void k_sample(const uint8_t *masks, int n, uint64_t key, int *actions) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    const uint8_t *m = masks + (size_t)i * ACT_COUNT;
    int legal = 0;
    for (int a = 0; a < ACT_COUNT; a++) legal += m[a];
    int r = (int)(gs_hash(key ^ ((uint64_t)i * 0xD1B54A32D192ED03ULL)) % (uint64_t)legal);
    int a = 0;
    for (; a < ACT_COUNT; a++) if (m[a] && r-- == 0) break;
    actions[i] = a;
}

/* Raw Obs -> the binding's float32 layout (one-hot tiles, light/15, status).
   One thread per output float: coalesced writes. */
__global__ void k_encode(const Obs *obs, long long n, float *flat) {
    long long j = (long long)blockIdx.x * blockDim.x + threadIdx.x;
    if (j >= n * GS_FLAT) return;
    long long i = j / GS_FLAT; int k = (int)(j - i * GS_FLAT);
    const Obs *o = &obs[i];
    const int terrain = VIEW_CELLS * OBS_TILE_KINDS;
    float v;
    if (k < terrain) v = o->tile[k / OBS_TILE_KINDS] == (k % OBS_TILE_KINDS) ? 1.f : 0.f;
    else if (k < terrain + VIEW_CELLS) v = (float)((double)o->light[k - terrain] / 15.);
    else v = o->status[k - terrain - VIEW_CELLS];
    flat[j] = v;
}
