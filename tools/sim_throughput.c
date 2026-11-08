/* Whole-step simulator throughput of one or more libterraria builds (D18 gate).

   Each library gets the same protocol: N lanes, uniform legal actions drawn
   from the lane's own action mask (PCG32, fixed seed), and per step the full
   trainer work for every lane through tl_batch_step on one worker: env_step,
   observation, action mask. Finished lanes reset with the next seed (resets
   included in the timing, like the trainer). Libraries are timed in
   interleaved rounds; the median steps/s per library is reported.

     cc -O2 tools/sim_throughput.c -o /tmp/sim_throughput
     /tmp/sim_throughput [-n lanes] [-s steps_per_lane] [-r rounds] [-e episode_steps] LIB...

   -e 0 (default) uses each library's own episode length.
*/
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef void *(*create_fn)(int);
typedef void (*reset_fn)(void *, unsigned long long, unsigned char *, unsigned char *, float *);
typedef void (*mask_fn)(const void *, unsigned char *);
typedef int (*int_fn)(void);
typedef void (*batch_fn)(void **, int, const int *, void *, uint8_t *, float *, int *, int);

typedef struct {
    const char *path; void *h; create_fn create; reset_fn reset; mask_fn mask; batch_fn batch;
    int actions, obs_bytes, version, steps;
} Lib;

static uint32_t pcg(uint64_t *s) {
    uint64_t old = *s;
    *s = old * 6364136223846793005ULL + 1442695040888963407ULL;
    uint32_t x = (uint32_t)(((old >> 18u) ^ old) >> 27u), rot = (uint32_t)(old >> 59u);
    return (x >> rot) | (x << ((-(int32_t)rot) & 31));
}

static double now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + 1e-9 * (double)t.tv_nsec;
}

static void *sym(void *h, const char *name) {
    void *p = dlsym(h, name);
    if (!p) { fprintf(stderr, "missing %s\n", name); exit(2); }
    return p;
}

static double run(Lib *L, int n, int steps, int episode) {
    void **envs = malloc(sizeof(void *) * (size_t)n);
    uint8_t *masks = malloc((size_t)n * (size_t)L->actions);
    unsigned char *obs = malloc((size_t)n * (size_t)L->obs_bytes);
    float *rewards = malloc(sizeof(float) * (size_t)n);
    int *ends = malloc(sizeof(int) * (size_t)n), *acts = malloc(sizeof(int) * (size_t)n), *legal = malloc(sizeof(int) * (size_t)L->actions);
    unsigned long long seed = 1;
    for (int i = 0; i < n; i++) {
        envs[i] = L->create(episode);
        L->reset(envs[i], seed++, NULL, NULL, NULL);
        L->mask(envs[i], masks + (size_t)i * (size_t)L->actions);
    }
    uint64_t rng = 12345;
    double t0 = now();
    for (int t = 0; t < steps; t++) {
        for (int i = 0; i < n; i++) {
            const uint8_t *m = masks + (size_t)i * (size_t)L->actions; int k = 0;
            for (int a = 0; a < L->actions; a++) if (m[a]) legal[k++] = a;
            acts[i] = legal[pcg(&rng) % (uint32_t)k];
        }
        L->batch(envs, n, acts, obs, masks, rewards, ends, 1);
        for (int i = 0; i < n; i++) if (ends[i]) {
            L->reset(envs[i], seed++, NULL, NULL, NULL);
            L->mask(envs[i], masks + (size_t)i * (size_t)L->actions);
        }
    }
    double dt = now() - t0;
    void (*destroy)(void *) = (void (*)(void *))sym(L->h, "tl_destroy");
    for (int i = 0; i < n; i++) destroy(envs[i]);
    free(envs); free(masks); free(obs); free(rewards); free(ends); free(acts); free(legal);
    return (double)n * steps / dt;
}

static int cmp(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }

int main(int argc, char **argv) {
    int n = 64, steps = 4000, rounds = 5, episode = 0, nl = 0;
    Lib libs[8];
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-n") && i + 1 < argc) n = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-s") && i + 1 < argc) steps = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-r") && i + 1 < argc) rounds = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-e") && i + 1 < argc) episode = atoi(argv[++i]);
        else if (nl < 8) {
            Lib *L = &libs[nl++]; memset(L, 0, sizeof *L); L->path = argv[i];
            L->h = dlopen(argv[i], RTLD_NOW | RTLD_LOCAL);
            if (!L->h) { fprintf(stderr, "%s\n", dlerror()); return 2; }
            L->create = (create_fn)sym(L->h, "tl_create"); L->reset = (reset_fn)sym(L->h, "tl_reset");
            L->mask = (mask_fn)sym(L->h, "tl_action_mask"); L->batch = (batch_fn)sym(L->h, "tl_batch_step");
            L->actions = ((int_fn)sym(L->h, "tl_action_count"))(); L->obs_bytes = ((int_fn)sym(L->h, "tl_obs_bytes"))();
            L->version = ((int_fn)sym(L->h, "tl_env_version"))(); L->steps = ((int_fn)sym(L->h, "tl_default_steps"))();
        }
    }
    if (!nl) { fprintf(stderr, "usage: %s [-n lanes] [-s steps] [-r rounds] LIB...\n", argv[0]); return 2; }
    double *sps = calloc((size_t)(nl * rounds), sizeof(double));
    for (int r = 0; r < rounds; r++) for (int k = 0; k < nl; k++) sps[k * rounds + r] = run(&libs[k], n, steps, episode);
    printf("{\"lanes\":%d,\"steps_per_lane\":%d,\"rounds\":%d,\"episode_steps_override\":%d,\"libraries\":[", n, steps, rounds, episode);
    for (int k = 0; k < nl; k++) {
        qsort(sps + k * rounds, (size_t)rounds, sizeof(double), cmp);
        printf("%s{\"path\":\"%s\",\"version\":%d,\"episode_steps\":%d,\"median_steps_per_s\":%.0f,\"min\":%.0f,\"max\":%.0f}",
               k ? "," : "", libs[k].path, libs[k].version, episode ? episode : libs[k].steps, sps[k * rounds + rounds / 2], sps[k * rounds], sps[k * rounds + rounds - 1]);
    }
    printf("]}\n");
    return 0;
}
