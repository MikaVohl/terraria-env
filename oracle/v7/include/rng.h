/* Per-env PCG32 stream. No globals, no rand(). */
#ifndef RNG_H
#define RNG_H

#include <stdint.h>

static inline uint32_t rng_next(uint64_t *s) {
    uint64_t old = *s;
    *s = old * 6364136223846793005ULL + 1442695040888963407ULL;
    uint32_t xorshifted = (uint32_t)(((old >> 18u) ^ old) >> 27u);
    uint32_t rot = (uint32_t)(old >> 59u);
    return (xorshifted >> rot) | (xorshifted << ((-(int32_t)rot) & 31));
}

/* Uniform in [0, n). */
static inline uint32_t rng_below(uint64_t *s, uint32_t n) {
    return n ? rng_next(s) % n : 0u;
}

/* Uniform in [lo, hi], inclusive. */
static inline int rng_range(uint64_t *s, int lo, int hi) {
    if (hi <= lo) return lo;
    return lo + (int)rng_below(s, (uint32_t)(hi - lo + 1));
}

/* Uniform in [0, 1). */
static inline float rng_float(uint64_t *s) {
    return (float)(rng_next(s) >> 8) * (1.0f / 16777216.0f);
}

/* True with probability p. */
static inline int rng_chance(uint64_t *s, float p) {
    return rng_float(s) < p;
}

#endif /* RNG_H */
