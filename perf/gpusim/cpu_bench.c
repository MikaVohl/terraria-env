/* CPU simulator throughput through the training entry point (tl_batch_step_flat),
 * random legal actions, autoreset with consecutive seeds. Only the batch call
 * and resets are timed.
 *   cpu_bench <lib.so> <n_envs> <steps> <workers> [flat=1]
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "env.h"

static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec * 1e-9; }
static uint64_t mix(uint64_t x) {
    x += 0x9E3779B97F4A7C15ULL; x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL; return x ^ (x >> 31);
}
int main(int argc, char **argv) {
    if (argc < 5) { fprintf(stderr, "usage\n"); return 2; }
    void *h = dlopen(argv[1], RTLD_NOW);
    if (!h) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    int n = atoi(argv[2]), steps = atoi(argv[3]), workers = atoi(argv[4]), flat = argc > 5 ? atoi(argv[5]) : 1;
    Env *(*create)(int) = dlsym(h, "tl_create");
    void (*reset)(Env *, unsigned long long, unsigned char *, unsigned char *, float *) = dlsym(h, "tl_reset");
    void (*mask)(const Env *, unsigned char *) = dlsym(h, "tl_action_mask");
    void (*bstep)(Env **, int, const int *, void *, uint8_t *, float *, int *, int) =
        dlsym(h, flat ? "tl_batch_step_flat" : "tl_batch_step");
    const int F = VIEW_CELLS * OBS_TILE_KINDS + VIEW_CELLS + OBS_STATUS;
    Env **envs = malloc(sizeof(Env *) * n);
    void *obs = malloc((size_t)n * (flat ? F * 4 : sizeof(Obs)));
    uint8_t *masks = malloc((size_t)n * ACT_COUNT);
    float *rew = malloc(4 * (size_t)n); int *ends = malloc(4 * (size_t)n), *act = malloc(4 * (size_t)n);
    uint64_t seed = 10000000ULL, r = 1;
    for (int i = 0; i < n; i++) { envs[i] = create(DEFAULT_MAX_STEPS); reset(envs[i], seed++, NULL, NULL, NULL); mask(envs[i], masks + (size_t)i * ACT_COUNT); }
    double t_step = 0, t_reset = 0; long long resets = 0;
    for (int t = 0; t < steps; t++) {
        for (int i = 0; i < n; i++) {
            const uint8_t *m = masks + (size_t)i * ACT_COUNT; int legal = 0;
            for (int a = 0; a < ACT_COUNT; a++) legal += m[a];
            int k = (int)(mix(r++) % (uint64_t)legal), a = 0;
            for (; a < ACT_COUNT; a++) if (m[a] && k-- == 0) break;
            act[i] = a;
        }
        double t0 = now();
        bstep(envs, n, act, obs, masks, rew, ends, workers);
        double t1 = now();
        for (int i = 0; i < n; i++) if (ends[i]) { reset(envs[i], seed++, NULL, NULL, NULL); mask(envs[i], masks + (size_t)i * ACT_COUNT); resets++; }
        t_reset += now() - t1; t_step += t1 - t0;
    }
    printf("CPU lib=%s n=%d workers=%d flat=%d steps=%d step_only=%.3e steps/s incl_serial_resets=%.3e steps/s resets=%lld (%.1f us/reset serial)\n",
           argv[1], n, workers, flat, steps, (double)n * steps / t_step, (double)n * steps / (t_step + t_reset),
           resets, resets ? 1e6 * t_reset / resets : 0.0);
    return 0;
}
