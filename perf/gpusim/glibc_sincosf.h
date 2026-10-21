/* Device port of glibc 2.39 sinf/cosf (sysdeps/ieee754/flt-32, x86_64 build:
 * TOINT_INTRINSICS=0). glibc's x86_64 libm dispatches to an -mfma -mavx2 build
 * on FMA-capable CPUs, where gcc contracts every a+b*c into an fma; GS_TRIG_FMA
 * selects that variant. Only |x| < 120 is needed by worldgen; larger inputs use
 * the same integer reduction as glibc. Double arithmetic is IEEE on both sides,
 * so with matching contraction the results are bit-identical. */
#pragma once
#include <stdint.h>

namespace gs_trig {
struct SC { double sign[4], hpi_inv, hpi, c0, c1, c2, c3, c4, s1, s2, s3; };
__host__ __device__ inline const SC &table(int k) {
    static constexpr SC T[2] = {
        {{1.0, -1.0, -1.0, 1.0}, 0x1.45F306DC9C883p+23, 0x1.921FB54442D18p0, 0x1p0,
         -0x1.ffffffd0c621cp-2, 0x1.55553e1068f19p-5, -0x1.6c087e89a359dp-10, 0x1.99343027bf8c3p-16,
         -0x1.555545995a603p-3, 0x1.1107605230bc4p-7, -0x1.994eb3774cf24p-13},
        {{1.0, -1.0, -1.0, 1.0}, 0x1.45F306DC9C883p+23, 0x1.921FB54442D18p0, -0x1p0,
         0x1.ffffffd0c621cp-2, -0x1.55553e1068f19p-5, 0x1.6c087e89a359dp-10, -0x1.99343027bf8c3p-16,
         -0x1.555545995a603p-3, 0x1.1107605230bc4p-7, -0x1.994eb3774cf24p-13}};
    return T[k];
}
__host__ __device__ inline uint32_t inv_pio4(int i) {
    static constexpr uint32_t A[24] = {
        0xa2, 0xa2f9, 0xa2f983, 0xa2f9836e, 0xf9836e4e, 0x836e4e44, 0x6e4e4415, 0x4e441529,
        0x441529fc, 0x1529fc27, 0x29fc2757, 0xfc2757d1, 0x2757d1f5, 0x57d1f534, 0xd1f534dd, 0xf534ddc0,
        0x34ddc0db, 0xddc0db62, 0xc0db6295, 0xdb629599, 0x6295993c, 0x95993c43, 0x993c4390, 0x3c439041};
    return A[i];
}
template <bool FMA> __host__ __device__ inline double madd(double a, double b, double c) {  /* c + a*b */
    if (FMA) return __builtin_fma(a, b, c);
    return c + a * b;
}
__host__ __device__ inline uint32_t asuint(float f) { union { float f; uint32_t u; } v; v.f = f; return v.u; }
__host__ __device__ inline uint32_t abstop12(float x) { return (asuint(x) >> 20) & 0x7ff; }

template <bool FMA> __host__ __device__ inline float poly(double x, double x2, const SC *p, int n) {
    if ((n & 1) == 0) {
        double x3 = x * x2, s1 = madd<FMA>(x2, p->s3, p->s2), x7 = x3 * x2, s = madd<FMA>(x3, p->s1, x);
        return (float)madd<FMA>(x7, s1, s);
    }
    double x4 = x2 * x2, c2 = madd<FMA>(x2, p->c4, p->c3), c1 = madd<FMA>(x2, p->c1, p->c0);
    double x6 = x4 * x2, c = madd<FMA>(x4, p->c2, c1);
    return (float)madd<FMA>(x6, c2, c);
}
template <bool FMA> __host__ __device__ inline double reduce_fast(double x, const SC *p, int *np) {
    double r = x * p->hpi_inv;
    int n = ((int32_t)r + 0x800000) >> 24;
    *np = n;
    return madd<FMA>(-(double)n, p->hpi, x);   /* x - n*hpi */
}
__host__ __device__ inline double reduce_large(uint32_t xi, int *np) {
    int base = (xi >> 26) & 15, shift = (xi >> 23) & 7;
    uint64_t n, res0, res1, res2;
    xi = (xi & 0xffffff) | 0x800000; xi <<= shift;
    res0 = xi * inv_pio4(base); res1 = (uint64_t)xi * inv_pio4(base + 4); res2 = (uint64_t)xi * inv_pio4(base + 8);
    res0 = (res2 >> 32) | (res0 << 32); res0 += res1;
    n = (res0 + (1ULL << 61)) >> 62; res0 -= n << 62;
    double x = (double)(int64_t)res0; *np = (int)n;
    return x * 0x1.921FB54442D18p-62;
}
template <bool FMA, bool COS> __host__ __device__ inline float sincos1(float y) {
    double x = y; int n; const SC *p = &table(0);
    if (abstop12(y) < abstop12(0x1.921FB6p-1f)) {
        double x2 = x * x;
        if (abstop12(y) < abstop12(0x1p-12f)) return COS ? 1.0f : y;
        return poly<FMA>(x, x2, p, COS ? 1 : 0);
    } else if (abstop12(y) < abstop12(120.0f)) {
        x = reduce_fast<FMA>(x, p, &n);
        double s = p->sign[n & 3];
        if (n & 2) p = &table(1);
        return poly<FMA>(x * s, x * x, p, COS ? n ^ 1 : n);
    } else if (abstop12(y) < abstop12(__builtin_inff())) {
        uint32_t xi = asuint(y); int sign = xi >> 31;
        x = reduce_large(xi, &n);
        double s = p->sign[(n + sign) & 3];
        if ((n + sign) & 2) p = &table(1);
        return poly<FMA>(x * s, x * x, p, COS ? n ^ 1 : n);
    }
    return (y - y) / (y - y);
}
}  // namespace gs_trig

#ifndef GS_TRIG_FMA
#define GS_TRIG_FMA 1
#endif
__host__ __device__ inline float gs_sinf(float x) { return gs_trig::sincos1<GS_TRIG_FMA, false>(x); }
__host__ __device__ inline float gs_cosf(float x) { return gs_trig::sincos1<GS_TRIG_FMA, true>(x); }
