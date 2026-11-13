/* The trained "targets" actor-critic (python/terraria_lite/target_agent.py,
 * depth 2) evaluated from raw Obs rows, plus a traced forward/backward pass
 * for one observation that the page draws.
 *
 * Mapping to the PyTorch module (Linear weights are [out][in], row-major):
 *   cells   : relu(W1 relu(W0 [onehot(tile) | light/15 | entity4] + b0) + b1)
 *             The one-hot product is a column lookup, so no 2,376-wide input
 *             is ever built.
 *   global  : g = tanh(Wg1 tanh(Wg0 [cells(99*C) | status[0:S0]] + bg0) + bg1)
 *   context : ctx_r = relu(Wc [cells of the 3x3 around reach r] + bc)
 *   actor   : other = Wa g + ba (43); per reach r,
 *             s_r = Wt1 tanh(Wt0 [g | ctx_r | coord_r] + bt0) + bt1 (mine, place)
 *             logits = other[0:4] | s[:,0] | s[:,1] | other[4:]
 *   critic  : v = Wv g + bv
 * The blob layout is written by tools/viz_export_policy.py in exactly the
 * order of the pointers in policy_init.
 */
#include <stdint.h>
#include <wasm_simd128.h>
#include "shim.h"
#include "env.h"

#define EXPORT(n) __attribute__((export_name(n)))
#define CELLS VIEW_CELLS
#define TK OBS_TILE_KINDS
#define CIN (TK + 5)
#define S0 OBS_ENTITY_0
#define R REACH_COUNT
#define NOTHER (ACT_COUNT - 2 * REACH_COUNT)
#define CTX 64
#define TH 64
#define MAXH 512
#define MAXC 64

static int H, C, GIN;
static const float *W0, *b0, *W1, *b1, *Wg0, *bg0, *Wg1, *bg1, *Wc, *bc,
                   *Wa, *ba, *Wt0, *bt0, *Wt1, *bt1, *Wv, *bv, *coord;
static int nb[R][9];

/* exp via 2^k * e^r with |r| <= ln2/2 and a degree-7 Taylor tail:
   relative error ~2e-7, enough for display and for the parity check. */
static float expc(float x) {
    if (x < -87.f) return 0.f;
    if (x > 88.f) x = 88.f;
    float k = __builtin_floorf(x * 1.44269504f + 0.5f);
    float r = x - k * 0.693147180f;
    float p = 1.f + r * (1.f + r * (0.5f + r * (1.f/6 + r * (1.f/24 + r * (1.f/120 + r * (1.f/720 + r * (1.f/5040)))))));
    union { float f; int32_t i; } u = { 1.f };
    u.i += (int32_t)k << 23;
    return p * u.f;
}
static float tanhc(float x) {
    if (x > 9.f) return 1.f;
    if (x < -9.f) return -1.f;
    float e = expc(2.f * x);
    return (e - 1.f) / (e + 1.f);
}
static float relu(float x) { return x > 0.f ? x : 0.f; }

static float dot(const float *a, const float *b, int n) {
    v128_t s0 = wasm_f32x4_splat(0), s1 = s0, s2 = s0, s3 = s0;
    int i = 0;
    for (; i + 16 <= n; i += 16) {
        s0 = wasm_f32x4_add(s0, wasm_f32x4_mul(wasm_v128_load(a + i), wasm_v128_load(b + i)));
        s1 = wasm_f32x4_add(s1, wasm_f32x4_mul(wasm_v128_load(a + i + 4), wasm_v128_load(b + i + 4)));
        s2 = wasm_f32x4_add(s2, wasm_f32x4_mul(wasm_v128_load(a + i + 8), wasm_v128_load(b + i + 8)));
        s3 = wasm_f32x4_add(s3, wasm_f32x4_mul(wasm_v128_load(a + i + 12), wasm_v128_load(b + i + 12)));
    }
    for (; i + 4 <= n; i += 4) s0 = wasm_f32x4_add(s0, wasm_f32x4_mul(wasm_v128_load(a + i), wasm_v128_load(b + i)));
    v128_t s = wasm_f32x4_add(wasm_f32x4_add(s0, s1), wasm_f32x4_add(s2, s3));
    float t = wasm_f32x4_extract_lane(s, 0) + wasm_f32x4_extract_lane(s, 1)
            + wasm_f32x4_extract_lane(s, 2) + wasm_f32x4_extract_lane(s, 3);
    for (; i < n; i++) t += a[i] * b[i];
    return t;
}
/* out[o] = W[o] . x + b[o] for W [n_out][n_in] */
static void linear(const float *W, const float *b, const float *x, int n_in, int n_out, float *out) {
    for (int o = 0; o < n_out; o++) out[o] = dot(W + (size_t)o * n_in, x, n_in) + (b ? b[o] : 0.f);
}

/* ---- loading ------------------------------------------------------------ */

EXPORT("w_policy_init") int w_policy_init(const float *blob, int hidden, int cell_width) {
    if (hidden < 1 || hidden > MAXH || cell_width < 1 || cell_width > MAXC) return 0;
    H = hidden; C = cell_width; GIN = CELLS * C + S0;
    const float *p = blob;
#define TAKE(ptr, n) (ptr = p, p += (n))
    TAKE(W0, C * CIN); TAKE(b0, C); TAKE(W1, C * C); TAKE(b1, C);
    TAKE(Wg0, (size_t)H * GIN); TAKE(bg0, H); TAKE(Wg1, H * H); TAKE(bg1, H);
    TAKE(Wc, CTX * 9 * C); TAKE(bc, CTX);
    TAKE(Wa, NOTHER * H); TAKE(ba, NOTHER);
    TAKE(Wt0, TH * (H + CTX + 2)); TAKE(bt0, TH); TAKE(Wt1, 2 * TH); TAKE(bt1, 2);
    TAKE(Wv, H); TAKE(bv, 1); TAKE(coord, R * 2);
#undef TAKE
    for (int r = 0; r < R; r++) {
        int x = VIEW_W / 2 + REACH_DX[r], y = VIEW_H / 2 + REACH_DY[r], j = 0;
        for (int oy = -1; oy <= 1; oy++) for (int ox = -1; ox <= 1; ox++) nb[r][j++] = (y + oy) * VIEW_W + x + ox;
    }
    return (int)(p - blob);   /* floats consumed: the exporter checks it */
}
EXPORT("w_policy_floats") int w_policy_floats(int hidden, int cw) {
    return cw * CIN + cw + cw * cw + cw + hidden * (CELLS * cw + S0) + hidden + hidden * hidden + hidden
         + CTX * 9 * cw + CTX + NOTHER * hidden + NOTHER + TH * (hidden + CTX + 2) + TH + 2 * TH + 2 + hidden + 1 + R * 2;
}

/* ---- forward ------------------------------------------------------------ */

typedef struct {
    float cell_h[CELLS * MAXC], cells[CELLS * MAXC];   /* cell layer 1 / 2 (post-ReLU) */
    float gin[CELLS * MAXC + S0], g1[MAXH], g[MAXH];
    float ctx[R * CTX], tz[R * TH], other[NOTHER], logits[ACT_COUNT], value;
} Acts;

static void forward(const Obs *o, Acts *a) {
    float pre[MAXC];
    for (int k = 0; k < CELLS; k++) {
        const float light = (float)((double)o->light[k] / 15.);
        const float *ent = &o->status[S0 + k * 4];
        for (int c = 0; c < C; c++) {
            const float *w = W0 + c * CIN;
            pre[c] = relu(w[o->tile[k]] + w[TK] * light + w[TK + 1] * ent[0] + w[TK + 2] * ent[1]
                          + w[TK + 3] * ent[2] + w[TK + 4] * ent[3] + b0[c]);
        }
        __builtin_memcpy(&a->cell_h[k * C], pre, (size_t)C * sizeof(float));
        for (int c = 0; c < C; c++) a->cells[k * C + c] = relu(dot(W1 + c * C, pre, C) + b1[c]);
    }
    __builtin_memcpy(a->gin, a->cells, (size_t)CELLS * C * sizeof(float));
    __builtin_memcpy(a->gin + CELLS * C, o->status, S0 * sizeof(float));
    linear(Wg0, bg0, a->gin, GIN, H, a->g1);
    for (int i = 0; i < H; i++) a->g1[i] = tanhc(a->g1[i]);
    linear(Wg1, bg1, a->g1, H, H, a->g);
    for (int i = 0; i < H; i++) a->g[i] = tanhc(a->g[i]);

    /* The scorer's first layer factors as in TargetActor.forward: the g part
       is shared by all 20 targets. Rows of Wt0 are H + CTX + 2 wide. */
    float u[9 * MAXC], zg[TH];
    for (int t = 0; t < TH; t++) zg[t] = dot(Wt0 + t * (H + CTX + 2), a->g, H) + bt0[t];
    linear(Wa, ba, a->g, H, NOTHER, a->other);
    for (int r = 0; r < R; r++) {
        for (int j = 0; j < 9; j++) __builtin_memcpy(u + j * C, &a->cells[nb[r][j] * C], (size_t)C * sizeof(float));
        float *ctx = &a->ctx[r * CTX];
        linear(Wc, bc, u, 9 * C, CTX, ctx);
        for (int i = 0; i < CTX; i++) ctx[i] = relu(ctx[i]);
        float *tz = &a->tz[r * TH];
        for (int t = 0; t < TH; t++) {
            const float *w = Wt0 + t * (H + CTX + 2);
            tz[t] = tanhc(zg[t] + dot(w + H, ctx, CTX) + w[H + CTX] * coord[2 * r] + w[H + CTX + 1] * coord[2 * r + 1]);
        }
        a->logits[ACT_MINE_FIRST + r] = dot(Wt1, tz, TH) + bt1[0];
        a->logits[ACT_PLACE_FIRST + r] = dot(Wt1 + TH, tz, TH) + bt1[1];
    }
    for (int i = 0; i < ACT_MINE_FIRST; i++) a->logits[i] = a->other[i];
    for (int i = ACT_MINE_FIRST; i < NOTHER; i++) a->logits[i + 2 * R] = a->other[i];
    a->value = dot(Wv, a->g, H) + bv[0];
}

static Acts scratch;
/* Batched: obs rows are contiguous Obs structs; writes ACT_COUNT logits and
   one value per row. */
EXPORT("w_policy_forward") void w_policy_forward(const Obs *obs, int n, float *logits, float *values) {
    for (int i = 0; i < n; i++) {
        forward(&obs[i], &scratch);
        __builtin_memcpy(logits + (size_t)i * ACT_COUNT, scratch.logits, sizeof scratch.logits);
        values[i] = scratch.value;
    }
}

/* ---- traced pass: activations + d log pi(action) / d everything ---------- */

typedef struct {
    Acts a;
    float probs[ACT_COUNT], logp, entropy;
    float d_logits[ACT_COUNT], d_g[MAXH], d_g1[MAXH], d_ctx[R * CTX], d_tz[R * TH];
    float d_cells[CELLS * MAXC], d_status[S0], saliency[CELLS];
} Trace;
static Trace tr;

EXPORT("w_trace_ptr") Trace *w_trace_ptr(void) { return &tr; }
/* Offsets (in floats from w_trace_ptr) of each Trace field, for the page. */
EXPORT("w_trace_layout") int w_trace_layout(int *o) {
#define OFF(f) (int)(__builtin_offsetof(Trace, f) / sizeof(float))
    int k = 0;
    o[k++] = OFF(a.cell_h); o[k++] = OFF(a.cells); o[k++] = OFF(a.g1); o[k++] = OFF(a.g);
    o[k++] = OFF(a.ctx); o[k++] = OFF(a.tz); o[k++] = OFF(a.other); o[k++] = OFF(a.logits);
    o[k++] = OFF(a.value); o[k++] = OFF(probs); o[k++] = OFF(logp); o[k++] = OFF(entropy);
    o[k++] = OFF(d_logits); o[k++] = OFF(d_g); o[k++] = OFF(d_g1); o[k++] = OFF(d_ctx);
    o[k++] = OFF(d_tz); o[k++] = OFF(d_cells); o[k++] = OFF(d_status); o[k++] = OFF(saliency);
    o[k++] = OFF(a.gin);
#undef OFF
    return k;
}

/* Masked softmax over legal actions, then the gradient of log pi(action):
   d/dlogit_i = [i == action] - p_i. That is the direction PPO scales by the
   advantage; everything below is that vector pulled back through the net. */
EXPORT("w_policy_trace") float w_policy_trace(const Obs *o, const uint8_t *mask, int action) {
    Acts *a = &tr.a;
    forward(o, a);
    float mx = -1e30f, z = 0.f;
    for (int i = 0; i < ACT_COUNT; i++) if (mask[i] && a->logits[i] > mx) mx = a->logits[i];
    for (int i = 0; i < ACT_COUNT; i++) { tr.probs[i] = mask[i] ? expc(a->logits[i] - mx) : 0.f; z += tr.probs[i]; }
    tr.entropy = 0.f;
    for (int i = 0; i < ACT_COUNT; i++) {
        tr.probs[i] /= z;
        if (tr.probs[i] > 0.f) tr.entropy -= tr.probs[i] * logf(tr.probs[i]);
    }
    if (action < 0 || action >= ACT_COUNT) return 0.f;
    tr.logp = logf(tr.probs[action] > 1e-30f ? tr.probs[action] : 1e-30f);
    for (int i = 0; i < ACT_COUNT; i++) tr.d_logits[i] = (i == action ? 1.f : 0.f) - tr.probs[i];

    __builtin_memset(tr.d_g, 0, sizeof tr.d_g);
    __builtin_memset(tr.d_cells, 0, sizeof tr.d_cells);
    /* "other" logits -> g through Wa */
    for (int j = 0; j < NOTHER; j++) {
        float d = tr.d_logits[j < ACT_MINE_FIRST ? j : j + 2 * R];
        for (int i = 0; i < H; i++) tr.d_g[i] += d * Wa[j * H + i];
    }
    /* per-target scorer -> g, ctx_r */
    for (int r = 0; r < R; r++) {
        float dm = tr.d_logits[ACT_MINE_FIRST + r], dp = tr.d_logits[ACT_PLACE_FIRST + r];
        float *tz = &a->tz[r * TH], *dtz = &tr.d_tz[r * TH], *dctx = &tr.d_ctx[r * CTX], *ctx = &a->ctx[r * CTX];
        __builtin_memset(dctx, 0, CTX * sizeof(float));
        for (int t = 0; t < TH; t++) {
            dtz[t] = dm * Wt1[t] + dp * Wt1[TH + t];
            float dz = dtz[t] * (1.f - tz[t] * tz[t]);
            const float *w = Wt0 + t * (H + CTX + 2);
            for (int i = 0; i < H; i++) tr.d_g[i] += dz * w[i];
            for (int i = 0; i < CTX; i++) dctx[i] += dz * w[H + i];
        }
        /* context ReLU -> 3x3 neighbourhood cells */
        for (int i = 0; i < CTX; i++) {
            float d = ctx[i] > 0.f ? dctx[i] : 0.f;
            if (d == 0.f) continue;
            const float *w = Wc + i * 9 * C;
            for (int j = 0; j < 9; j++) for (int c = 0; c < C; c++) tr.d_cells[nb[r][j] * C + c] += d * w[j * C + c];
        }
    }
    /* global trunk: g = tanh(Wg1 g1), g1 = tanh(Wg0 gin) */
    float dpre[MAXH];
    for (int i = 0; i < H; i++) dpre[i] = tr.d_g[i] * (1.f - a->g[i] * a->g[i]);
    for (int j = 0; j < H; j++) { float s = 0.f; for (int i = 0; i < H; i++) s += dpre[i] * Wg1[i * H + j]; tr.d_g1[j] = s; }
    for (int i = 0; i < H; i++) dpre[i] = tr.d_g1[i] * (1.f - a->g1[i] * a->g1[i]);
    __builtin_memset(tr.d_status, 0, sizeof tr.d_status);
    for (int i = 0; i < H; i++) {
        const float *w = Wg0 + (size_t)i * GIN;
        float d = dpre[i];
        for (int j = 0; j < CELLS * C; j++) tr.d_cells[j] += d * w[j];
        for (int j = 0; j < S0; j++) tr.d_status[j] += d * w[CELLS * C + j];
    }
    for (int k = 0; k < CELLS; k++) {
        float s = 0.f;
        for (int c = 0; c < C; c++) { float v = tr.d_cells[k * C + c]; s += v * v; }
        tr.saliency[k] = sqrtf(s);
    }
    return tr.logp;
}
