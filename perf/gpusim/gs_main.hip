/* Standalone driver: parity against the CPU library and throughput benchmarks.
 *   gs_main parity <cpu_lib.so> <n_envs> <steps> [illegal_pct] [full_state_every] [gpu_reset=1]
 *   gs_main bench  <n_envs> <steps> <mode> [block]
 *     mode: step        step+obs+mask only (no episode ends handled)
 *           auto        in-kernel autoreset (worldgen on GPU, divergent)
 *           list        step, then compacted reset kernel for finished lanes
 *           pool        step, then reset by copying a pre-generated state
 *           auto+enc / list+enc / pool+enc   ... plus float32 one-hot encode
 *   gs_main cpuparity <libA.so> <libB.so> <n_envs> <steps> [illegal_pct] [full_state_every]
 *   gs_main worldparity <cpu_lib.so> <seed0> <count> [batch]
 *   gs_main profile <n_envs> <steps> [block]
 */
#include "gpusim_kernels.h"
#include <dlfcn.h>
#include <chrono>
#include <vector>
#include <string>
#include <thread>

#define CK(x) do { hipError_t err_ = (x); if (err_ != hipSuccess) { \
    fprintf(stderr, "%s:%d %s: %s\n", __FILE__, __LINE__, #x, hipGetErrorString(err_)); exit(1); } } while (0)

static double now() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
static int blocks(long long n, int b) { return (int)((n + b - 1) / b); }

/* ---------------------------------------------------------------- CPU lib */
struct CpuLib {
    Env *(*create)(int);
    void (*reset)(Env *, unsigned long long, unsigned char *, unsigned char *, float *);
    void (*batch_step)(Env **, int, const int *, Obs *, uint8_t *, float *, int *, int);
    int (*state_bytes)(void);
    void (*action_mask)(const Env *, unsigned char *);
    int (*obs_bytes)(void);
    int (*version)(void);
    void load(const char *path) {
        void *h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
        if (!h) { fprintf(stderr, "dlopen: %s\n", dlerror()); exit(1); }
#define SYM(f, s) *(void **)&f = dlsym(h, s); if (!f) { fprintf(stderr, "missing %s\n", s); exit(1); }
        SYM(create, "tl_create") SYM(reset, "tl_reset") SYM(batch_step, "tl_batch_step")
        SYM(state_bytes, "tl_state_bytes") SYM(action_mask, "tl_action_mask")
        SYM(obs_bytes, "tl_obs_bytes") SYM(version, "tl_env_version")
#undef SYM
    }
};

static uint64_t splitmix(uint64_t x) {
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}

/* Field-wise Env comparison (padding and the device-elided msg excluded). */
static const char *env_diff(const Env *a, const Env *b) {
#define F(x) if (memcmp(&a->x, &b->x, sizeof a->x)) return #x;
    /* Env.light is only exact inside the observation window (light.c); older
       builds kept the whole map, so compare the window only. */
    for (int y = a->py - VIEW_H / 2; y <= a->py + VIEW_H / 2; y++)
        for (int x = a->px - VIEW_W / 2; x <= a->px + VIEW_W / 2; x++)
            if (in_bounds(x, y) && a->light[y][x] != b->light[y][x]) return "light (window)";
    F(tiles) F(terrain_light) F(sky_cutoff) F(terrain_dirty) F(surface)
#if ENV_VERSION >= 7
    F(object_part)
#endif
    F(px) F(py) F(facing) F(jump_left) F(fall_dist) F(health) F(tool_tier) F(inv) F(selected)
    F(max_health) F(weapon) F(armor) F(attack_cd) F(heal_cd) F(hurt_cd) F(mine_cd) F(safe_ticks)
    F(air_jump_used) F(drop_ticks) F(explore_min) F(explore_max) F(mining_tree)
    for (int m = 0; m < MAX_MOBS; m++) {
        F(mobs[m].x) F(mobs[m].y) F(mobs[m].hp) F(mobs[m].phase) F(mobs[m].jump) F(mobs[m].dir) F(mobs[m].kind)
    }
    for (int c = 0; c < MAX_CHESTS; c++) { F(chests[c].x) F(chests[c].y) F(chests[c].opened) F(chests[c].loot) }
    F(chest_count) F(achievements) F(rng) F(seed) F(steps) F(max_steps) F(reward) F(ep_return)
    F(terminated) F(truncated) F(light_dirty)
#undef F
    return nullptr;
}

/* gpu_reset=0: worldgen stays on the CPU library and the 38.7 KB state blob
   (what tl_save_state copies) is uploaded; obs/mask are then produced on GPU. */
static int parity(const char *libpath, int n, int steps, int illegal_pct, int full_every, int gpu_reset) {
    CpuLib L; L.load(libpath);
    printf("cpu lib %s: env v%d, state %d B, obs %d B | hip: state %zu B, obs %zu B\n", libpath,
           L.version(), L.state_bytes(), L.obs_bytes(), sizeof(Env), sizeof(Obs));
    if (L.state_bytes() != (int)sizeof(Env) || L.obs_bytes() != (int)sizeof(Obs) || L.version() != ENV_VERSION) {
        fprintf(stderr, "layout mismatch\n"); return 2;
    }
    const int MAXS = DEFAULT_MAX_STEPS;
    std::vector<Env *> cpu(n);
    for (int i = 0; i < n; i++) cpu[i] = L.create(MAXS);
    std::vector<Obs> cobs(n), gobs(n);
    std::vector<uint8_t> cmask((size_t)n * ACT_COUNT), gmask((size_t)n * ACT_COUNT);
    std::vector<float> crew(n), grew(n);
    std::vector<int> cend(n), gend(n), act(n);
    std::vector<uint64_t> seeds(n);
    uint64_t next_seed = 10000000ULL;  /* ppo_agent's v2 seeding: seed*10_000_000 */

    Env *d_env; Obs *d_obs; uint8_t *d_mask; float *d_rew; int *d_end, *d_act, *d_idx; uint64_t *d_seed;
    CK(hipMalloc(&d_env, sizeof(Env) * (size_t)n)); CK(hipMalloc(&d_obs, sizeof(Obs) * (size_t)n));
    CK(hipMalloc(&d_mask, (size_t)n * ACT_COUNT)); CK(hipMalloc(&d_rew, 4 * (size_t)n));
    CK(hipMalloc(&d_end, 4 * (size_t)n)); CK(hipMalloc(&d_act, 4 * (size_t)n));
    CK(hipMalloc(&d_idx, 4 * (size_t)n)); CK(hipMalloc(&d_seed, 8 * (size_t)n));
    int *d_cnt; CK(hipMalloc(&d_cnt, 4));
    auto upload_resets = [&](const std::vector<int> &idx) {
        for (int i : idx) CK(hipMemcpy(&d_env[i], cpu[i], sizeof(Env), hipMemcpyHostToDevice));
        int c = (int)idx.size();
        CK(hipMemcpy(d_idx, idx.data(), 4 * idx.size(), hipMemcpyHostToDevice));
        CK(hipMemcpy(d_cnt, &c, 4, hipMemcpyHostToDevice));
        k_obs_mask_list<<<blocks(c, 64), 64>>>(d_env, d_idx, d_cnt, d_obs, d_mask);
        CK(hipDeviceSynchronize());
    };
    k_init<<<blocks(n, 128), 128>>>(d_env, n, MAXS);

    /* Initial reset, lanes in order, consecutive seeds (VecTerraria.reset). */
    for (int i = 0; i < n; i++) {
        seeds[i] = next_seed++;
        L.reset(cpu[i], seeds[i], cobs[i].tile, cobs[i].light, cobs[i].status);
        L.action_mask(cpu[i], &cmask[(size_t)i * ACT_COUNT]);
    }
    if (gpu_reset) {
        CK(hipMemcpy(d_seed, seeds.data(), 8 * (size_t)n, hipMemcpyHostToDevice));
        k_reset<<<blocks(n, 64), 64>>>(d_env, nullptr, d_seed, n, d_obs, d_mask);
        CK(hipDeviceSynchronize());
    } else {
        std::vector<int> all(n); for (int i = 0; i < n; i++) all[i] = i;
        upload_resets(all);
    }

    long long obs_bad = 0, mask_bad = 0, rew_bad = 0, end_bad = 0, state_bad = 0, compared = 0, episodes = 0;
    long long state_checks = 0;
    std::vector<Env> genv(n);
    auto check_state = [&](const char *when, int t) {
        CK(hipMemcpy(genv.data(), d_env, sizeof(Env) * (size_t)n, hipMemcpyDeviceToHost));
        for (int i = 0; i < n; i++) {
            const char *f = env_diff(cpu[i], &genv[i]);
            state_checks++;
            if (f) { if (state_bad < 10) printf("STATE DIFF %s step %d lane %d field %s\n", when, t, i, f); state_bad++; }
        }
    };
    auto check_outputs = [&](int t, bool with_rew) {
        CK(hipMemcpy(gobs.data(), d_obs, sizeof(Obs) * (size_t)n, hipMemcpyDeviceToHost));
        CK(hipMemcpy(gmask.data(), d_mask, (size_t)n * ACT_COUNT, hipMemcpyDeviceToHost));
        if (with_rew) {
            CK(hipMemcpy(grew.data(), d_rew, 4 * (size_t)n, hipMemcpyDeviceToHost));
            CK(hipMemcpy(gend.data(), d_end, 4 * (size_t)n, hipMemcpyDeviceToHost));
        }
        for (int i = 0; i < n; i++) {
            bool ob = memcmp(cobs[i].tile, gobs[i].tile, VIEW_CELLS) || memcmp(cobs[i].light, gobs[i].light, VIEW_CELLS)
                   || memcmp(cobs[i].status, gobs[i].status, sizeof cobs[i].status);
            bool mb = memcmp(&cmask[(size_t)i * ACT_COUNT], &gmask[(size_t)i * ACT_COUNT], ACT_COUNT) != 0;
            bool rb = with_rew && memcmp(&crew[i], &grew[i], 4);
            bool eb = with_rew && cend[i] != gend[i];
            if ((ob || mb || rb || eb) && obs_bad + mask_bad + rew_bad + end_bad < 10)
                printf("OUT DIFF step %d lane %d obs=%d mask=%d rew=%d end=%d\n", t, i, ob, mb, rb, eb);
            obs_bad += ob; mask_bad += mb; rew_bad += rb; end_bad += eb; compared++;
        }
    };
    check_outputs(-1, false);
    check_state("reset", -1);

    uint64_t arng = 12345;
    int workers = (int)std::thread::hardware_concurrency(); if (workers > 16) workers = 16;
    double t0 = now();
    for (int t = 0; t < steps; t++) {
        /* Actions: mostly uniform over legal (CPU mask), sometimes any action. */
        for (int i = 0; i < n; i++) {
            uint64_t r = splitmix(arng++);
            const uint8_t *m = &cmask[(size_t)i * ACT_COUNT];
            if ((int)(r % 100) < illegal_pct) { act[i] = (int)((r >> 8) % ACT_COUNT); continue; }
            int legal = 0; for (int a = 0; a < ACT_COUNT; a++) legal += m[a];
            int k = (int)((r >> 16) % (uint64_t)legal), a = 0;
            for (; a < ACT_COUNT; a++) if (m[a] && k-- == 0) break;
            act[i] = a;
        }
        L.batch_step(cpu.data(), n, act.data(), cobs.data(), cmask.data(), crew.data(), cend.data(), workers);
        CK(hipMemcpy(d_act, act.data(), 4 * (size_t)n, hipMemcpyHostToDevice));
        k_step<<<blocks(n, 64), 64>>>(d_env, n, d_act, d_obs, d_mask, d_rew, d_end);
        CK(hipGetLastError());
        check_outputs(t, true);
        if (full_every > 0 && (t + 1) % full_every == 0) check_state("step", t);
        /* Autoreset in lane order with the next consecutive seeds (VecTerraria.step). */
        std::vector<int> idx; std::vector<uint64_t> sd;
        for (int i = 0; i < n; i++) if (cend[i]) {
            idx.push_back(i); sd.push_back(next_seed++);
            L.reset(cpu[i], sd.back(), cobs[i].tile, cobs[i].light, cobs[i].status);
            L.action_mask(cpu[i], &cmask[(size_t)i * ACT_COUNT]);
        }
        if (!idx.empty()) {
            episodes += (long long)idx.size();
            if (gpu_reset) {
                CK(hipMemcpy(d_idx, idx.data(), 4 * idx.size(), hipMemcpyHostToDevice));
                CK(hipMemcpy(d_seed, sd.data(), 8 * sd.size(), hipMemcpyHostToDevice));
                k_reset<<<blocks((long long)idx.size(), 64), 64>>>(d_env, d_idx, d_seed, (int)idx.size(), d_obs, d_mask);
                CK(hipDeviceSynchronize());
            } else upload_resets(idx);
            check_outputs(t, false);
        }
        if ((t + 1) % 1000 == 0) {
            printf("step %d: compared %lld lane-steps, episodes reset %lld, bad obs %lld mask %lld rew %lld end %lld state %lld/%lld (%.0fs)\n",
                   t + 1, compared, episodes, obs_bad, mask_bad, rew_bad, end_bad, state_bad, state_checks, now() - t0);
            fflush(stdout);
        }
    }
    check_state("final", steps);
    printf("PARITY %s: n=%d steps=%d illegal_pct=%d reset=%s lane_steps=%lld episodes_reset=%lld obs_bad=%lld mask_bad=%lld rew_bad=%lld end_bad=%lld state_bad=%lld/%lld\n",
           (obs_bad | mask_bad | rew_bad | end_bad | state_bad) ? "FAIL" : "OK", n, steps, illegal_pct, gpu_reset ? "gpu" : "cpu-blob",
           (long long)n * steps, episodes, obs_bad, mask_bad, rew_bad, end_bad, state_bad, state_checks);
    return (obs_bad | mask_bad | rew_bad | end_bad | state_bad) ? 1 : 0;
}

/* ----------------------------------------------------------------- bench */
static int bench(int n, int steps, std::string mode, int B) {
    bool enc = mode.size() > 4 && mode.substr(mode.size() - 4) == "+enc";
    std::string base = enc ? mode.substr(0, mode.size() - 4) : mode;
    const int MAXS = DEFAULT_MAX_STEPS;
    Env *d_env; Obs *d_obs; uint8_t *d_mask; float *d_rew, *d_flat = nullptr; int *d_end, *d_act, *d_idx, *d_cnt;
    uint32_t *d_ep, *d_cur; uint64_t *d_seed; Env *d_pool = nullptr;
    CK(hipMalloc(&d_env, sizeof(Env) * (size_t)n)); CK(hipMalloc(&d_obs, sizeof(Obs) * (size_t)n));
    CK(hipMalloc(&d_mask, (size_t)n * ACT_COUNT)); CK(hipMalloc(&d_rew, 4 * (size_t)n));
    CK(hipMalloc(&d_end, 4 * (size_t)n)); CK(hipMalloc(&d_act, 4 * (size_t)n));
    CK(hipMalloc(&d_idx, 4 * (size_t)n)); CK(hipMalloc(&d_cnt, 4)); CK(hipMalloc(&d_cur, 4));
    CK(hipMalloc(&d_ep, 4 * (size_t)n)); CK(hipMalloc(&d_seed, 8 * (size_t)n));
    CK(hipMemset(d_ep, 0, 4 * (size_t)n)); CK(hipMemset(d_cur, 0, 4));
    if (enc) CK(hipMalloc(&d_flat, 4 * (size_t)n * GS_FLAT));
    std::vector<uint64_t> seeds(n);
    for (int i = 0; i < n; i++) seeds[i] = 10000000ULL + i;
    CK(hipMemcpy(d_seed, seeds.data(), 8 * (size_t)n, hipMemcpyHostToDevice));
    k_init<<<blocks(n, 128), 128>>>(d_env, n, MAXS);
    double tr = now();
    k_reset<<<blocks(n, 64), 64>>>(d_env, nullptr, d_seed, n, d_obs, d_mask);
    CK(hipDeviceSynchronize());
    double reset_s = now() - tr;
    int pool_n = 0;
    bool pooled = base == "pool" || base == "poolc";
    if (pooled) {
        pool_n = n < 65536 ? n : 65536;
        CK(hipMalloc(&d_pool, sizeof(Env) * (size_t)pool_n));
        std::vector<uint64_t> ps(pool_n);
        for (int i = 0; i < pool_n; i++) ps[i] = 900000000ULL + i;
        CK(hipMemcpy(d_seed, ps.data(), 8 * (size_t)pool_n, hipMemcpyHostToDevice));
        k_init<<<blocks(pool_n, 128), 128>>>(d_pool, pool_n, MAXS);
        k_reset<<<blocks(pool_n, 64), 64>>>(d_pool, nullptr, d_seed, pool_n, nullptr, nullptr);
        CK(hipDeviceSynchronize());
    }
    hipEvent_t e0, e1; CK(hipEventCreate(&e0)); CK(hipEventCreate(&e1));
    auto one = [&](int t) {
        k_sample<<<blocks(n, 256), 256>>>(d_mask, n, 0xABCDEF00ULL + (uint64_t)t, d_act);
        if (base == "step") {
            k_step<<<blocks(n, B), B>>>(d_env, n, d_act, d_obs, d_mask, d_rew, d_end);
        } else if (base == "auto") {
            k_step_autoreset<<<blocks(n, B), B>>>(d_env, n, d_act, d_obs, d_mask, d_rew, d_end, d_ep, 20000000ULL);
        } else {
            CK(hipMemsetAsync(d_cnt, 0, 4));
            if (base == "poolc")
                k_step_mark_coop<32><<<blocks(n, 32), 32>>>(d_env, n, d_act, d_obs, d_mask, d_rew, d_end, d_idx, d_cnt);
            else
                k_step_mark<<<blocks(n, B), B>>>(d_env, n, d_act, d_obs, d_mask, d_rew, d_end, d_idx, d_cnt);
            /* Grid sized for the worst case; idle blocks exit on the device count. */
            if (base == "list") {
                k_reset_list<<<blocks(n, 64), 64>>>(d_env, d_idx, d_cnt, d_ep, 20000000ULL, d_obs, d_mask);
            } else {
                k_reset_from_pool<<<1024, 256>>>(d_env, d_idx, d_cnt, d_pool, pool_n, d_cur);
                k_obs_mask_list<<<blocks(n, 64), 64>>>(d_env, d_idx, d_cnt, d_obs, d_mask);
            }
        }
        if (enc) k_encode<<<blocks((long long)n * GS_FLAT, 256), 256>>>(d_obs, n, d_flat);
    };
    int warm = steps / 10 > 50 ? 50 : steps / 10;
    for (int t = 0; t < warm; t++) one(t);
    CK(hipDeviceSynchronize());
    CK(hipEventRecord(e0));
    for (int t = warm; t < steps + warm; t++) one(t);
    CK(hipEventRecord(e1)); CK(hipEventSynchronize(e1)); CK(hipGetLastError());
    float ms; CK(hipEventElapsedTime(&ms, e0, e1));
    std::vector<uint32_t> ep(n); CK(hipMemcpy(ep.data(), d_ep, 4 * (size_t)n, hipMemcpyDeviceToHost));
    long long eps = 0; for (auto x : ep) eps += x;
    uint32_t pool_resets = 0; CK(hipMemcpy(&pool_resets, d_cur, 4, hipMemcpyDeviceToHost));
    if (pooled) eps = pool_resets;
    double sps = (double)n * steps / (ms / 1e3);
    printf("BENCH mode=%s n=%d block=%d steps=%d time=%.3fs us/step=%.1f env_steps_per_s=%.3e initial_reset_s=%.3f (%.0f resets/s) episodes_reset=%lld (incl. warmup)\n",
           mode.c_str(), n, B, steps, ms / 1e3, ms * 1e3 / steps, sps, reset_s, n / reset_s, eps);
    (void)hipFree(d_env); (void)hipFree(d_obs); (void)hipFree(d_mask); (void)hipFree(d_rew); (void)hipFree(d_end); (void)hipFree(d_act);
    (void)hipFree(d_idx); (void)hipFree(d_cnt); (void)hipFree(d_cur); (void)hipFree(d_ep); (void)hipFree(d_seed);
    if (d_flat) (void)hipFree(d_flat);
    if (d_pool) (void)hipFree(d_pool);
    return 0;
}

/* Two CPU builds (e.g. this branch vs the unmodified main-branch library):
   same seeds, same actions (uniform legal from A's mask, plus illegal_pct%
   uniform over all actions), autoreset in lane order with consecutive seeds;
   obs/mask/reward/end compared every step, full state every full_every. */
static int cpuparity(const char *pa, const char *pb, int n, int steps, int illegal_pct, int full_every) {
    CpuLib A, B; A.load(pa); B.load(pb);
    if (A.state_bytes() != (int)sizeof(Env) || B.state_bytes() != (int)sizeof(Env) || A.obs_bytes() != (int)sizeof(Obs)
        || B.obs_bytes() != (int)sizeof(Obs) || A.version() != ENV_VERSION || B.version() != ENV_VERSION) {
        fprintf(stderr, "layout mismatch: libraries must match the headers this driver was built with\n"); return 2;
    }
    std::vector<Env *> ea(n), eb(n);
    std::vector<Obs> oa(n), ob(n);
    std::vector<uint8_t> ma((size_t)n * ACT_COUNT), mb((size_t)n * ACT_COUNT);
    std::vector<float> ra(n), rb(n);
    std::vector<int> da(n), db(n), act(n);
    uint64_t next_seed = 10000000ULL, arng = 4242;
    auto reset = [&](int i) {
        uint64_t s = next_seed++;
        A.reset(ea[i], s, oa[i].tile, oa[i].light, oa[i].status); A.action_mask(ea[i], &ma[(size_t)i * ACT_COUNT]);
        B.reset(eb[i], s, ob[i].tile, ob[i].light, ob[i].status); B.action_mask(eb[i], &mb[(size_t)i * ACT_COUNT]);
    };
    for (int i = 0; i < n; i++) { ea[i] = A.create(DEFAULT_MAX_STEPS); eb[i] = B.create(DEFAULT_MAX_STEPS); reset(i); }
    long long bad_out = 0, bad_state = 0, checks = 0, episodes = 0;
    auto compare = [&](int t, bool state) {
        for (int i = 0; i < n; i++) {
            bool o = memcmp(oa[i].tile, ob[i].tile, VIEW_CELLS) || memcmp(oa[i].light, ob[i].light, VIEW_CELLS)
                  || memcmp(oa[i].status, ob[i].status, sizeof oa[i].status)
                  || memcmp(&ma[(size_t)i * ACT_COUNT], &mb[(size_t)i * ACT_COUNT], ACT_COUNT)
                  || memcmp(&ra[i], &rb[i], 4) || da[i] != db[i];
            if (o && bad_out++ < 10) printf("OUT DIFF step %d lane %d\n", t, i);
            if (state) { const char *f = env_diff(ea[i], eb[i]); checks++;
                if (f && bad_state++ < 10) printf("STATE DIFF step %d lane %d field %s\n", t, i, f); }
        }
    };
    compare(-1, true);
    for (int t = 0; t < steps; t++) {
        for (int i = 0; i < n; i++) {
            uint64_t r = splitmix(arng++);
            const uint8_t *m = &ma[(size_t)i * ACT_COUNT];
            if ((int)(r % 100) < illegal_pct) { act[i] = (int)((r >> 8) % ACT_COUNT); continue; }
            int legal = 0; for (int a = 0; a < ACT_COUNT; a++) legal += m[a];
            int k = (int)((r >> 16) % (uint64_t)legal), a = 0;
            for (; a < ACT_COUNT; a++) if (m[a] && k-- == 0) break;
            act[i] = a;
        }
        A.batch_step(ea.data(), n, act.data(), oa.data(), ma.data(), ra.data(), da.data(), 16);
        B.batch_step(eb.data(), n, act.data(), ob.data(), mb.data(), rb.data(), db.data(), 16);
        compare(t, full_every > 0 && (t + 1) % full_every == 0);
        for (int i = 0; i < n; i++) if (da[i]) { reset(i); episodes++; }
    }
    printf("CPUPARITY %s: %s vs %s n=%d steps=%d illegal_pct=%d lane_steps=%lld episodes_reset=%lld out_bad=%lld state_bad=%lld/%lld\n",
           (bad_out | bad_state) ? "FAIL" : "OK", pa, pb, n, steps, illegal_pct, (long long)n * steps, episodes, bad_out, bad_state, checks);
    return (bad_out | bad_state) ? 1 : 0;
}

/* Worldgen-only parity: env_reset for a seed range on both sides, full state compared. */
static int worldparity(const char *libpath, uint64_t seed0, long long count, int batch) {
    CpuLib L; L.load(libpath);
    int workers = 16;
    std::vector<Env *> cpu(batch);
    for (int i = 0; i < batch; i++) cpu[i] = L.create(DEFAULT_MAX_STEPS);
    std::vector<Env> genv(batch);
    std::vector<uint64_t> seeds(batch);
    Env *d_env; uint64_t *d_seed;
    CK(hipMalloc(&d_env, sizeof(Env) * (size_t)batch)); CK(hipMalloc(&d_seed, 8 * (size_t)batch));
    k_init<<<blocks(batch, 128), 128>>>(d_env, batch, DEFAULT_MAX_STEPS);
    long long bad = 0, done = 0, bad_cells = 0;
    double t0 = now();
    for (long long off = 0; off < count; off += batch) {
        int b = (int)(count - off < batch ? count - off : batch);
        for (int i = 0; i < b; i++) seeds[i] = seed0 + (uint64_t)(off + i);
        CK(hipMemcpy(d_seed, seeds.data(), 8 * (size_t)b, hipMemcpyHostToDevice));
        k_reset<<<blocks(b, 64), 64>>>(d_env, nullptr, d_seed, b, nullptr, nullptr);
        std::vector<std::thread> th;
        for (int w = 0; w < workers; w++) th.emplace_back([&, w] {
            for (int i = w; i < b; i += workers) L.reset(cpu[i], seeds[i], nullptr, nullptr, nullptr);
        });
        for (auto &x : th) x.join();
        CK(hipMemcpy(genv.data(), d_env, sizeof(Env) * (size_t)b, hipMemcpyDeviceToHost));
        for (int i = 0; i < b; i++) {
            const char *f = env_diff(cpu[i], &genv[i]);
            if (!f) continue;
            int cells = 0;
            for (int y = 0; y < WORLD_H; y++) for (int x = 0; x < WORLD_W; x++) cells += cpu[i]->tiles[y][x] != genv[i].tiles[y][x];
            if (bad < 20) printf("WORLD DIFF seed %llu first field %s, %d tiles differ\n", (unsigned long long)seeds[i], f, cells);
            bad++; bad_cells += cells;
        }
        done += b;
        printf("worlds %lld/%lld bad %lld (%.0fs)\n", done, count, bad, now() - t0); fflush(stdout);
    }
    printf("WORLDPARITY %s: seeds [%llu, %llu) worlds=%lld differing=%lld (%.6f%%) differing_tiles=%lld\n", bad ? "FAIL" : "OK",
           (unsigned long long)seed0, (unsigned long long)(seed0 + count), done, bad, 100.0 * bad / done, bad_cells);
    return bad ? 1 : 0;
}

/* Per-phase kernels for a cost breakdown (same envs, random legal actions). */
__global__ void k_only_step(Env *envs, int n, const int *actions) {
    int i = blockIdx.x * blockDim.x + threadIdx.x; if (i < n) env_step(&envs[i], actions[i]);
}
__global__ void k_only_obs(Env *envs, int n, Obs *obs) {
    int i = blockIdx.x * blockDim.x + threadIdx.x; if (i < n) env_obs(&envs[i], &obs[i]);
}
__global__ void k_only_mask(Env *envs, int n, uint8_t *masks) {
    int i = blockIdx.x * blockDim.x + threadIdx.x; if (i < n) env_action_mask(&envs[i], masks + (size_t)i * ACT_COUNT);
}
__global__ void k_only_light(Env *envs, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x; if (i < n) light_recompute(&envs[i]);
}
static int profile(int n, int steps, int B) {
    Env *d_env; Obs *d_obs; uint8_t *d_mask; int *d_act; uint64_t *d_seed;
    CK(hipMalloc(&d_env, sizeof(Env) * (size_t)n)); CK(hipMalloc(&d_obs, sizeof(Obs) * (size_t)n));
    CK(hipMalloc(&d_mask, (size_t)n * ACT_COUNT)); CK(hipMalloc(&d_act, 4 * (size_t)n)); CK(hipMalloc(&d_seed, 8 * (size_t)n));
    std::vector<uint64_t> seeds(n); for (int i = 0; i < n; i++) seeds[i] = 10000000ULL + i;
    CK(hipMemcpy(d_seed, seeds.data(), 8 * (size_t)n, hipMemcpyHostToDevice));
    k_init<<<blocks(n, 128), 128>>>(d_env, n, 1 << 30);   /* no truncation during the profile */
    k_reset<<<blocks(n, 64), 64>>>(d_env, nullptr, d_seed, n, d_obs, d_mask);
    CK(hipDeviceSynchronize());
    hipEvent_t a, b; CK(hipEventCreate(&a)); CK(hipEventCreate(&b));
    double t_sample = 0, t_step = 0, t_obs = 0, t_mask = 0, t_light = 0; float ms;
#define TIMED(acc, launch) do { CK(hipEventRecord(a)); launch; CK(hipEventRecord(b)); CK(hipEventSynchronize(b)); \
        CK(hipEventElapsedTime(&ms, a, b)); acc += ms; } while (0)
    for (int t = 0; t < steps; t++) {
        TIMED(t_sample, (k_sample<<<blocks(n, 256), 256>>>(d_mask, n, 77 + t, d_act)));
        TIMED(t_step, (k_only_step<<<blocks(n, B), B>>>(d_env, n, d_act)));
        TIMED(t_obs, (k_only_obs<<<blocks(n, B), B>>>(d_env, n, d_obs)));
        TIMED(t_mask, (k_only_mask<<<blocks(n, B), B>>>(d_env, n, d_mask)));
        TIMED(t_light, (k_only_light<<<blocks(n, B), B>>>(d_env, n)));
    }
#undef TIMED
    printf("PROFILE n=%d block=%d per-step ms: sample %.3f env_step %.3f env_obs %.3f env_action_mask %.3f | extra light_recompute alone %.3f\n",
           n, B, t_sample / steps, t_step / steps, t_obs / steps, t_mask / steps, t_light / steps);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: see header\n"); return 2; }
    std::string cmd = argv[1];
    if (cmd == "parity" && argc >= 5)
        return parity(argv[2], atoi(argv[3]), atoi(argv[4]), argc > 5 ? atoi(argv[5]) : 10, argc > 6 ? atoi(argv[6]) : 500,
                      argc > 7 ? atoi(argv[7]) : 1);
    if (cmd == "bench" && argc >= 5)
        return bench(atoi(argv[2]), atoi(argv[3]), argv[4], argc > 5 ? atoi(argv[5]) : 64);
    if (cmd == "cpuparity" && argc >= 6)
        return cpuparity(argv[2], argv[3], atoi(argv[4]), atoi(argv[5]), argc > 6 ? atoi(argv[6]) : 10, argc > 7 ? atoi(argv[7]) : 500);
    if (cmd == "worldparity" && argc >= 5)
        return worldparity(argv[2], strtoull(argv[3], nullptr, 10), atoll(argv[4]), argc > 5 ? atoi(argv[5]) : 65536);
    if (cmd == "profile" && argc >= 4)
        return profile(atoi(argv[2]), atoi(argv[3]), argc > 4 ? atoi(argv[4]) : 64);
    fprintf(stderr, "bad args\n");
    return 2;
}
