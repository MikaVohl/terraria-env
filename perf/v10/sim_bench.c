/* Trainer-shaped simulator benchmark and lockstep parity check.

   Bench: N lanes stepped by tl_batch_step_autoreset (compact rows, W pool
   workers, lane-ordered reset seeds) with uniform legal actions (PCG32),
   as the trainer's VecTerraria(native_autoreset, compact) does. Reports
   ms per batch step, steps/s, resets per step and the cost of one tl_reset.

     cc -O2 perf/v10/sim_bench.c -o /tmp/sim_bench -ldl -lpthread
     /tmp/sim_bench [-n 1024] [-w 12] [-s 2000] [-e episode_steps] LIB

   Parity: with two libraries, both are stepped in lockstep from the same
   seeds and the same actions (drawn from library A's mask) and every output
   of every step is compared byte for byte: compact obs rows, masks, rewards,
   end codes, terminal rows, episode info rows and returns, the reset lane
   list. Exits 1 at the first difference.

     /tmp/sim_bench -n 256 -w 16 -s 100000 LIB_A LIB_B
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
typedef int (*auto_fn)(void **, int, const int *, void *, int, uint8_t *, float *, int *, void *, int *, float *,
                       int *, unsigned long long, int);
typedef void (*obs_fn)(const void *, unsigned char *, unsigned char *, float *);

typedef struct {
    void *h; create_fn create; reset_fn reset; mask_fn mask; auto_fn step; obs_fn observe;
    int actions, obs_bytes, info_w, cells;
    void **envs; uint8_t *obs, *final, *masks; float *rew, *ret; int *ends, *info, *lanes;
} Lib;

static uint32_t pcg(uint64_t *s) {
    uint64_t old = *s;
    *s = old * 6364136223846793005ULL + 1442695040888963407ULL;
    uint32_t x = (uint32_t)(((old >> 18u) ^ old) >> 27u), rot = (uint32_t)(old >> 59u);
    return (x >> rot) | (x << ((-(int32_t)rot) & 31));
}
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }
static void *sym(void *h, const char *n) { void *p = dlsym(h, n); if (!p) { fprintf(stderr, "missing %s\n", n); exit(2); } return p; }

static void open_lib(Lib *L, const char *path, int n, int episode) {
    memset(L, 0, sizeof *L);
    L->h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!L->h) { fprintf(stderr, "%s\n", dlerror()); exit(2); }
    L->create = (create_fn)sym(L->h, "tl_create"); L->reset = (reset_fn)sym(L->h, "tl_reset");
    L->mask = (mask_fn)sym(L->h, "tl_action_mask"); L->step = (auto_fn)sym(L->h, "tl_batch_step_autoreset");
    L->actions = ((int_fn)sym(L->h, "tl_action_count"))(); L->obs_bytes = ((int_fn)sym(L->h, "tl_obs_bytes"))();
    L->info_w = ((int_fn)sym(L->h, "tl_info_width"))();
    L->envs = malloc(sizeof(void *) * n);
    L->obs = calloc((size_t)n, L->obs_bytes); L->final = calloc((size_t)n, L->obs_bytes);
    L->masks = calloc((size_t)n, L->actions); L->rew = calloc(n, 4); L->ret = calloc(n, 4);
    L->ends = calloc(n, 4); L->info = calloc((size_t)n * L->info_w, 4); L->lanes = calloc(n, 4);
    int cells = 0; /* tl_reset writes tile/light/status into the compact row via tl_observe-free path */
    (void)cells;
    for (int i = 0; i < n; i++) {
        L->envs[i] = L->create(episode);
        /* compact row = tile[cells], light[cells], pad, status: the library's own layout through tl_reset's
           pointers is not needed; one autoreset-free step fills obs, so take the mask only. */
        L->reset(L->envs[i], (unsigned long long)(i + 1), NULL, NULL, NULL);
        L->mask(L->envs[i], L->masks + (size_t)i * L->actions);
    }
}

static int diff(const char *what, const void *a, const void *b, size_t bytes, long step) {
    if (!memcmp(a, b, bytes)) return 0;
    fprintf(stderr, "MISMATCH %s at batch step %ld\n", what, step);
    return 1;
}

int main(int argc, char **argv) {
    int n = 1024, w = 12, steps = 2000, episode = 0, nl = 0; const char *paths[2];
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-n")) n = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-w")) w = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-s")) steps = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-e")) episode = atoi(argv[++i]);
        else if (nl < 2) paths[nl++] = argv[i];
    }
    if (!nl) { fprintf(stderr, "usage: sim_bench [-n lanes] [-w workers] [-s steps] [-e episode] LIB [LIB_B]\n"); return 2; }
    Lib L[2];
    for (int k = 0; k < nl; k++) open_lib(&L[k], paths[k], n, episode);
    int *acts = malloc(sizeof(int) * n), *legal = malloc(sizeof(int) * L[0].actions);
    uint64_t rng = 12345; unsigned long long seed = (unsigned long long)n + 1;
    long resets = 0; double t_step = 0, t_reset_steps = 0; long n_reset_steps = 0;
    for (long t = 0; t < steps; t++) {
        for (int i = 0; i < n; i++) {
            const uint8_t *m = L[0].masks + (size_t)i * L[0].actions; int k = 0;
            for (int a = 0; a < L[0].actions; a++) if (m[a]) legal[k++] = a;
            acts[i] = legal[pcg(&rng) % (uint32_t)k];
        }
        int count[2];
        for (int k = 0; k < nl; k++) {
            double t0 = now();
            count[k] = L[k].step(L[k].envs, n, acts, L[k].obs, 0, L[k].masks, L[k].rew, L[k].ends, L[k].final,
                                 L[k].info, L[k].ret, L[k].lanes, seed, w);
            double dt = now() - t0;
            if (k == 0) { t_step += dt; if (count[0]) { t_reset_steps += dt; n_reset_steps++; } }
        }
        if (nl == 2) {
            int bad = count[0] != count[1];
            if (bad) fprintf(stderr, "MISMATCH reset count at batch step %ld\n", t);
            bad = bad || diff("obs", L[0].obs, L[1].obs, (size_t)n * L[0].obs_bytes, t)
                || diff("masks", L[0].masks, L[1].masks, (size_t)n * L[0].actions, t)
                || diff("rewards", L[0].rew, L[1].rew, 4u * n, t) || diff("ends", L[0].ends, L[1].ends, 4u * n, t)
                || diff("lanes", L[0].lanes, L[1].lanes, 4u * count[0], t);
            for (int c = 0; !bad && c < count[0]; c++) {
                int i = L[0].lanes[c];
                bad = diff("final", L[0].final + (size_t)i * L[0].obs_bytes, L[1].final + (size_t)i * L[0].obs_bytes,
                           L[0].obs_bytes, t)
                    || diff("info", L[0].info + (size_t)i * L[0].info_w, L[1].info + (size_t)i * L[0].info_w, 4u * L[0].info_w, t)
                    || diff("return", L[0].ret + i, L[1].ret + i, 4, t);
            }
            if (bad) return 1;
        }
        resets += count[0]; seed += (unsigned long long)count[0];
    }
    /* one tl_reset, for scale */
    double t0 = now();
    for (int k = 0; k < 32; k++) L[0].reset(L[0].envs[0], 999000 + k, NULL, NULL, NULL);
    double t_one = (now() - t0) / 32;
    printf("{\"lanes\":%d,\"workers\":%d,\"steps\":%d,\"ms_per_step\":%.4f,\"steps_per_s\":%.0f,\"resets_per_step\":%.4f,"
           "\"ms_per_step_with_reset\":%.4f,\"ms_per_step_without\":%.4f,\"ms_tl_reset\":%.4f,\"parity\":%s}\n",
           n, w, steps, 1e3 * t_step / steps, (double)n * steps / t_step, (double)resets / steps,
           n_reset_steps ? 1e3 * t_reset_steps / n_reset_steps : 0.0,
           steps > n_reset_steps ? 1e3 * (t_step - t_reset_steps) / (steps - n_reset_steps) : 0.0, 1e3 * t_one,
           nl == 2 ? "\"identical\"" : "null");
    return 0;
}
