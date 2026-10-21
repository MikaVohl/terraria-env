/* Exhaustive check of device sinf/cosf against the host glibc over every float
 * with |x| < limit: ROCm ocml, glibc-port without FMA, glibc-port with FMA. */
#include <hip/hip_runtime.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <thread>
#include <vector>
#include "glibc_sincosf.h"

__global__ void k_trig(uint32_t base, int n, float *out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    uint32_t u = base + (uint32_t)i; float x; memcpy(&x, &u, 4);
    out[0 * (size_t)n + i] = sinf(x);
    out[1 * (size_t)n + i] = cosf(x);
    out[2 * (size_t)n + i] = gs_trig::sincos1<false, false>(x);
    out[3 * (size_t)n + i] = gs_trig::sincos1<false, true>(x);
    out[4 * (size_t)n + i] = gs_trig::sincos1<true, false>(x);
    out[5 * (size_t)n + i] = gs_trig::sincos1<true, true>(x);
}

int main(int argc, char **argv) {
    float limit = argc > 1 ? atof(argv[1]) : 128.f;
    uint32_t top; memcpy(&top, &limit, 4);
    const int CH = 1 << 24;
    float *d; if (hipMalloc(&d, 6 * sizeof(float) * CH) != hipSuccess) return 1;
    std::vector<float> g(6 * (size_t)CH), hs(CH), hc(CH);
    long long bad[6] = {0}, total = 0;
    for (int sign = 0; sign < 2; sign++)
        for (uint32_t b = 0; b < top; b += CH) {
            uint32_t base = b | (sign ? 0x80000000u : 0u);
            int n = (int)((top - b) < (uint32_t)CH ? top - b : (uint32_t)CH);
            k_trig<<<(n + 255) / 256, 256>>>(base, n, d);
            std::vector<std::thread> th;
            for (int w = 0; w < 16; w++) th.emplace_back([&, w] {
                for (int i = w; i < n; i += 16) { uint32_t u = base + i; float x; memcpy(&x, &u, 4); hs[i] = sinf(x); hc[i] = cosf(x); }
            });
            for (auto &t : th) t.join();
            if (hipMemcpy(g.data(), d, 6 * sizeof(float) * (size_t)n, hipMemcpyDeviceToHost) != hipSuccess) return 1;
            for (int v = 0; v < 6; v++) {
                const float *ref = (v & 1) ? hc.data() : hs.data(), *got = &g[(size_t)v * n];
                for (int i = 0; i < n; i++) bad[v] += memcmp(&ref[i], &got[i], 4) != 0;
            }
            total += n;
        }
    printf("TRIG |x|<%g floats=%lld mismatches vs host glibc: ocml sinf %lld cosf %lld | glibc-port(no fma) sinf %lld cosf %lld | glibc-port(fma) sinf %lld cosf %lld\n",
           limit, total, bad[0], bad[1], bad[2], bad[3], bad[4], bad[5]);
    return 0;
}
