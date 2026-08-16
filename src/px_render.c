/* Tile art and every pixel this frontend draws.
 *
 * All art comes from a local Terraria install: the real sheets are decoded
 * with stb_image and re-cut into our 16x16 grid. Nothing is copied into the
 * repo and nothing is cached to disk -- these are Re-Logic's assets and they
 * stay where they were installed.
 *
 * Loading is all-or-nothing. There is no synthesised fallback, so a missing or
 * renamed sheet is a hard error that names the file, rather than one tile that
 * quietly looks wrong. */
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <SDL.h>

#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_PNG
#define STBI_NO_LINEAR
#define STBI_NO_HDR
#if defined(__clang__) || defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#include "stb_image.h"
#if defined(__clang__) || defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

#include "px_render.h"

/* ---- Layout ------------------------------------------------------------- *
 * Shared between the draw code and the hit tests so a click always lands on
 * the thing it looks like it lands on. */

#define SX          PX_VIEW_W          /* left edge of the sidebar */
#define HY          PX_VIEW_H          /* top edge of the HUD strip */

#define REC_Y0      18
#define REC_PITCH   20
#define REC_H       19

#define ACH_X0      (PX_VIEW_W + 10)
#define ACH_Y0      260
#define ACH_PITCH   16
#define ACH_CELL    13
#define ACH_COLS    8

#define INV_X0      6
#define INV_Y0      (HY + 29)
#define INV_PITCH   22
#define INV_SLOT    20

/* ---- Palette ------------------------------------------------------------ *
 * 0xAARRGGBB throughout, which is also SDL_PIXELFORMAT_ARGB8888. */

#define UI_BG       0xFF14131Au
#define UI_BG2      0xFF201E2Au
#define UI_BG3      0xFF2C2A3Au
#define UI_LINE     0xFF3A3748u
#define UI_TEXT     0xFFD9D4C6u
#define UI_DIM      0xFF817C90u
#define UI_FAINT    0xFF565266u
#define UI_ACCENT   0xFFE8A94Eu
#define UI_GOOD     0xFF74CF5Cu
#define UI_BAD      0xFFD65B4Bu
#define UI_HEART    0xFFE0424Au
#define UI_BODY     0xFF3E6FC0u    /* the "you are here" torso in the key grid */
#define VOID_COL    0xFF07070Bu

#define CA(c) ((int)(((c) >> 24) & 0xFFu))
#define CR(c) ((int)(((c) >> 16) & 0xFFu))
#define CG(c) ((int)(((c) >>  8) & 0xFFu))
#define CB(c) ((int)( (c)        & 0xFFu))

/* One tile's art. `nvar` variants sit side by side; when `masked` is set the
   rows are indexed by the 4-neighbour solidity mask, which is how Terraria
   sheets are organised and what makes edges and corners come out right. */
typedef struct {
    SDL_Texture *tex;
    int          nvar;
    bool         masked;
} TileArt;

struct PxUi {
    SDL_Window   *win;
    SDL_Renderer *ren;
    TileArt       art[TILE_COUNT];    /* art[TILE_AIR].tex stays NULL */
    SDL_Texture  *bg_dirt;
    SDL_Texture  *bg_stone;
    SDL_Texture  *item[ITEM_COUNT];
    bool          item_owned[ITEM_COUNT];
    SDL_Texture  *font;
    SDL_Texture  *light;
    SDL_Texture  *player;             /* 20 frames x 2 facings */
    int           real_tiles;         /* how many tiles came from real sheets */
    int           real_items;         /* ...and how many item icons */
    char          missing[32];        /* first sheet that failed to load */
};

/* ---- Colour arithmetic -------------------------------------------------- */

static int clamp255(int v) { return v < 0 ? 0 : (v > 255 ? 255 : v); }

static uint32_t rgb(int r, int g, int b)
{
    return 0xFF000000u | ((uint32_t)clamp255(r) << 16) |
           ((uint32_t)clamp255(g) << 8) | (uint32_t)clamp255(b);
}

/* t is 0..256, where 0 is all `a`. */
static uint32_t mix(uint32_t a, uint32_t b, int t)
{
    return rgb(CR(a) + (CR(b) - CR(a)) * t / 256,
               CG(a) + (CG(b) - CG(a)) * t / 256,
               CB(a) + (CB(b) - CB(a)) * t / 256);
}

/* Scale a colour toward black, keeping alpha. */
static uint32_t dim_col(uint32_t c, int num, int den)
{
    return (c & 0xFF000000u) |
           (rgb(CR(c) * num / den, CG(c) * num / den, CB(c) * num / den) & 0x00FFFFFFu);
}

/* ---- Deterministic noise ------------------------------------------------ *
 * A hash rather than a PRNG so a pixel's grain and a tile's variant depend
 * only on their coordinates: the same seed renders identically on every run
 * and every machine, which matters when a screenshot is the record of an
 * agent's episode. */
static uint32_t hash2(int x, int y, uint32_t salt)
{
    uint32_t h = (uint32_t)x * 0x9E3779B1u ^ (uint32_t)y * 0x85EBCA77u ^ salt * 0xC2B2AE3Du;
    h ^= h >> 15; h *= 0x2545F491u;
    h ^= h >> 13; h *= 0x27D4EB2Fu;
    h ^= h >> 16;
    return h;
}

/* ---- Backdrop ----------------------------------------------------------- */

/* Cave walls are the same rock seen from behind: much darker and pushed
   toward blue, so the foreground always reads as in front of them. */
static uint32_t backdrop(uint32_t c)
{
    return mix(dim_col(c, 38, 100), 0xFF101828u, 60);
}

/* ---- Font --------------------------------------------------------------- *
 * 5x7, column-major, bit r of column byte c lights pixel (c, r). Cell pitch in
 * the atlas is 6 so glyphs never bleed under filtering. */

#define GLYPH_W 5
#define GLYPH_H 7
#define CELL_W  6

static const unsigned char FONT5X7[95][GLYPH_W] = {
    {0x00,0x00,0x00,0x00,0x00},{0x00,0x00,0x5f,0x00,0x00},{0x00,0x03,0x00,0x03,0x00},{0x14,0x7f,0x14,0x7f,0x14},
    {0x24,0x2a,0x7f,0x2a,0x12},{0x23,0x13,0x08,0x64,0x62},{0x36,0x49,0x55,0x22,0x50},{0x00,0x00,0x03,0x00,0x00},
    {0x00,0x1c,0x22,0x41,0x00},{0x00,0x41,0x22,0x1c,0x00},{0x2a,0x1c,0x3e,0x1c,0x2a},{0x08,0x08,0x3e,0x08,0x08},
    {0x00,0x50,0x30,0x00,0x00},{0x08,0x08,0x08,0x08,0x08},{0x00,0x60,0x60,0x00,0x00},{0x40,0x30,0x08,0x06,0x01},
    {0x3e,0x51,0x49,0x45,0x3e},{0x00,0x42,0x7f,0x40,0x00},{0x42,0x61,0x51,0x49,0x46},{0x21,0x41,0x45,0x4b,0x31},
    {0x18,0x14,0x12,0x7f,0x10},{0x27,0x45,0x45,0x45,0x39},{0x3c,0x4a,0x49,0x49,0x30},{0x01,0x71,0x09,0x05,0x03},
    {0x36,0x49,0x49,0x49,0x36},{0x06,0x49,0x49,0x29,0x1e},{0x00,0x36,0x36,0x00,0x00},{0x00,0x56,0x36,0x00,0x00},
    {0x08,0x14,0x22,0x41,0x00},{0x14,0x14,0x14,0x14,0x14},{0x00,0x41,0x22,0x14,0x08},{0x02,0x01,0x51,0x09,0x06},
    {0x3e,0x41,0x5d,0x55,0x1e},{0x7e,0x09,0x09,0x09,0x7e},{0x7f,0x49,0x49,0x49,0x36},{0x3e,0x41,0x41,0x41,0x22},
    {0x7f,0x41,0x41,0x22,0x1c},{0x7f,0x49,0x49,0x49,0x41},{0x7f,0x09,0x09,0x09,0x01},{0x3e,0x41,0x49,0x49,0x7a},
    {0x7f,0x08,0x08,0x08,0x7f},{0x00,0x41,0x7f,0x41,0x00},{0x20,0x40,0x41,0x3f,0x01},{0x7f,0x08,0x14,0x22,0x41},
    {0x7f,0x40,0x40,0x40,0x40},{0x7f,0x02,0x0c,0x02,0x7f},{0x7f,0x04,0x08,0x10,0x7f},{0x3e,0x41,0x41,0x41,0x3e},
    {0x7f,0x09,0x09,0x09,0x06},{0x3e,0x41,0x51,0x21,0x5e},{0x7f,0x09,0x19,0x29,0x46},{0x46,0x49,0x49,0x49,0x31},
    {0x01,0x01,0x7f,0x01,0x01},{0x3f,0x40,0x40,0x40,0x3f},{0x1f,0x20,0x40,0x20,0x1f},{0x7f,0x20,0x18,0x20,0x7f},
    {0x63,0x14,0x08,0x14,0x63},{0x03,0x04,0x78,0x04,0x03},{0x61,0x51,0x49,0x45,0x43},{0x00,0x7f,0x41,0x41,0x00},
    {0x01,0x06,0x08,0x30,0x40},{0x00,0x41,0x41,0x7f,0x00},{0x04,0x02,0x01,0x02,0x04},{0x40,0x40,0x40,0x40,0x40},
    {0x00,0x01,0x02,0x00,0x00},{0x20,0x54,0x54,0x54,0x78},{0x7f,0x44,0x44,0x44,0x38},{0x38,0x44,0x44,0x44,0x44},
    {0x38,0x44,0x44,0x44,0x7f},{0x38,0x54,0x54,0x54,0x18},{0x08,0x7e,0x09,0x09,0x02},{0x0c,0x52,0x52,0x52,0x3e},
    {0x7f,0x04,0x04,0x04,0x78},{0x00,0x44,0x7d,0x40,0x00},{0x20,0x40,0x44,0x3d,0x00},{0x7f,0x10,0x28,0x44,0x00},
    {0x00,0x41,0x7f,0x40,0x00},{0x7c,0x04,0x78,0x04,0x78},{0x7c,0x04,0x04,0x04,0x78},{0x38,0x44,0x44,0x44,0x38},
    {0x7e,0x12,0x12,0x12,0x0c},{0x0c,0x12,0x12,0x12,0x7e},{0x7c,0x08,0x04,0x04,0x08},{0x48,0x54,0x54,0x54,0x24},
    {0x04,0x3f,0x44,0x44,0x20},{0x3c,0x40,0x40,0x20,0x7c},{0x1c,0x20,0x40,0x20,0x1c},{0x3c,0x40,0x30,0x40,0x3c},
    {0x44,0x28,0x10,0x28,0x44},{0x0e,0x50,0x50,0x50,0x3e},{0x44,0x64,0x54,0x4c,0x44},{0x00,0x08,0x77,0x41,0x00},
    {0x00,0x00,0x7f,0x00,0x00},{0x00,0x41,0x77,0x08,0x00},{0x08,0x04,0x04,0x08,0x04},
};

/* ---- Terraria sheets ---------------------------------------------------- */

/* Frame (col, row) in an 18px-stride sheet for each 4-neighbour solidity mask,
   three interchangeable variants each. Bit 0 up, 1 down, 2 left, 3 right; a
   set bit means "solid neighbour there", so mask 15 is a buried block.
   Derived by measuring which frame edges are transparent across Tiles_0/1/2/
   6/7/8/25/30 -- all eight agree, which is why one table serves them all. */
static const unsigned char FRAME_TAB[16][3][2] = {
    /*  0 ---- */ {{ 9,3},{10,3},{11,3}},
    /*  1 U--- */ {{ 6,3},{ 7,3},{ 8,3}},
    /*  2 -D-- */ {{ 6,0},{ 7,0},{ 8,0}},
    /*  3 UD-- */ {{ 5,0},{ 5,1},{ 5,2}},
    /*  4 --L- */ {{12,0},{12,1},{12,2}},
    /*  5 U-L- */ {{ 1,4},{ 3,4},{ 5,4}},
    /*  6 -DL- */ {{ 1,3},{ 3,3},{ 5,3}},
    /*  7 UDL- */ {{ 4,0},{ 4,1},{ 4,2}},
    /*  8 ---R */ {{ 9,0},{ 9,1},{ 9,2}},
    /*  9 U--R */ {{ 0,4},{ 2,4},{ 4,4}},
    /* 10 -D-R */ {{ 0,3},{ 2,3},{ 4,3}},
    /* 11 UD-R */ {{ 0,0},{ 0,1},{ 0,2}},
    /* 12 --LR */ {{ 6,4},{ 7,4},{ 8,4}},
    /* 13 U-LR */ {{ 1,2},{ 2,2},{ 3,2}},
    /* 14 -DLR */ {{ 1,0},{ 2,0},{ 3,0}},
    /* 15 UDLR */ {{ 1,1},{ 2,1},{ 3,1}},
};

typedef struct {
    uint32_t *px;      /* ARGB8888, malloc'd */
    int       w, h;
} Sheet;

static uint32_t sheet_at(const Sheet *s, int x, int y)
{
    if (x < 0 || y < 0 || x >= s->w || y >= s->h) return 0u;
    return s->px[y * s->w + x];
}

static void sheet_free(Sheet *s)
{
    free(s->px);
    s->px = NULL;
}

/* Remember the first sheet that would not load. Loading is all or nothing, so
   that first miss is the whole story and everything after it is noise. */
static bool sheet_fail(PxUi *ui, const char *name)
{
    if (!ui->missing[0]) snprintf(ui->missing, sizeof ui->missing, "%s", name);
    return false;
}

static bool sheet_load(PxUi *ui, Sheet *s, const char *dir, const char *name)
{
    char path[1024];
    unsigned char *raw;
    int w, h, n, i;

    s->px = NULL;
    snprintf(path, sizeof path, "%s/%s.png", dir, name);
    raw = stbi_load(path, &w, &h, &n, 4);
    if (!raw) return sheet_fail(ui, name);

    s->px = malloc((size_t)w * (size_t)h * sizeof *s->px);
    if (!s->px) { stbi_image_free(raw); return sheet_fail(ui, name); }
    /* stb hands back R,G,B,A bytes; we want one ARGB word per pixel. */
    for (i = 0; i < w * h; i++)
        s->px[i] = ((uint32_t)raw[i * 4 + 3] << 24) | ((uint32_t)raw[i * 4 + 0] << 16) |
                   ((uint32_t)raw[i * 4 + 1] <<  8) |  (uint32_t)raw[i * 4 + 2];
    stbi_image_free(raw);
    s->w = w;
    s->h = h;
    return true;
}

/* Area-average a source rect into a destination rect, in premultiplied alpha
   so shrinking a sprite against transparency does not fringe it with black.
   Terraria's furniture is 2 or 3 tiles across and has to fit in one of ours;
   an honest box filter survives that better than point sampling. */
static void blit_box(const Sheet *s, int sx, int sy, int sw, int sh,
                     uint32_t *dst, int dstride, int dx, int dy, int dw, int dh)
{
    int ox, oy;
    for (oy = 0; oy < dh; oy++)
        for (ox = 0; ox < dw; ox++) {
            int x0 = sx + ox * sw / dw, x1 = sx + (ox + 1) * sw / dw;
            int y0 = sy + oy * sh / dh, y1 = sy + (oy + 1) * sh / dh;
            long ar = 0, ag = 0, ab = 0, aa = 0, n = 0;
            int x, y;

            if (x1 <= x0) x1 = x0 + 1;
            if (y1 <= y0) y1 = y0 + 1;
            for (y = y0; y < y1; y++)
                for (x = x0; x < x1; x++) {
                    uint32_t c = sheet_at(s, x, y);
                    int a = CA(c);
                    ar += CR(c) * a; ag += CG(c) * a; ab += CB(c) * a;
                    aa += a; n++;
                }
            if (aa == 0) {
                dst[(dy + oy) * dstride + dx + ox] = 0u;
            } else {
                dst[(dy + oy) * dstride + dx + ox] =
                    ((uint32_t)(aa / n) << 24) |
                    ((uint32_t)(ar / aa) << 16) |
                    ((uint32_t)(ag / aa) <<  8) |
                     (uint32_t)(ab / aa);
            }
        }
}

/* Splice a cols x rows block of 16x16 frames (18px stride) into a contiguous
   buffer, dropping the padding gutters. */
static void gather_frames(const Sheet *s, int x0, int y0, int cols, int rows, uint32_t *out)
{
    int c, r, x, y;
    for (r = 0; r < rows; r++)
        for (c = 0; c < cols; c++)
            for (y = 0; y < 16; y++)
                for (x = 0; x < 16; x++)
                    out[(r * 16 + y) * (cols * 16) + c * 16 + x] =
                        sheet_at(s, x0 + c * 18 + x, y0 + r * 18 + y);
}

/* ---- Texture plumbing --------------------------------------------------- */

static SDL_Texture *mk_tex(SDL_Renderer *ren, const uint32_t *px, int w, int h)
{
    SDL_Texture *t = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
                                       SDL_TEXTUREACCESS_STATIC, w, h);
    if (!t) return NULL;
    SDL_UpdateTexture(t, NULL, px, w * (int)sizeof(uint32_t));
    SDL_SetTextureBlendMode(t, SDL_BLENDMODE_BLEND);
    return t;
}

/* A full 3-variant x 16-mask atlas cut straight out of a Terraria block
   sheet. `dark` scales the result, which is how ebonstone becomes bedrock. */
static bool load_grid(PxUi *ui, Tile t, const char *dir, const char *name, int dark)
{
    static uint32_t atlas[16 * 16 * 3 * 16];   /* 48 x 256 */
    Sheet s;
    int m, v, x, y;

    if (!sheet_load(ui, &s, dir, name)) return false;

    for (m = 0; m < 16; m++)
        for (v = 0; v < 3; v++) {
            int fx = FRAME_TAB[m][v][0] * 18, fy = FRAME_TAB[m][v][1] * 18;
            for (y = 0; y < 16; y++)
                for (x = 0; x < 16; x++) {
                    uint32_t c = sheet_at(&s, fx + x, fy + y);
                    if (dark != 100)
                        c = (c & 0xFF000000u) | (dim_col(c, dark, 100) & 0x00FFFFFFu);
                    atlas[(m * 16 + y) * 48 + v * 16 + x] = c;
                }
        }
    sheet_free(&s);

    ui->art[t].tex    = mk_tex(ui->ren, atlas, 48, 256);
    ui->art[t].nvar   = 3;
    ui->art[t].masked = true;
    ui->real_tiles++;
    return true;
}

/* One or more 16x16 variants built by box-fitting an arbitrary source rect.
   `bottom` sits the result on the tile floor, which is what furniture wants;
   otherwise it is centred. */
static bool load_fitted(PxUi *ui, Tile t, const Sheet *s, const int (*src)[4],
                        int nvar, bool bottom)
{
    static uint32_t atlas[16 * 16 * 8];
    int v, i;

    if (nvar > 8) return false;
    for (i = 0; i < 16 * 16 * nvar; i++) atlas[i] = 0u;

    for (v = 0; v < nvar; v++) {
        int sw = src[v][2], sh = src[v][3];
        int dw = sw >= sh ? 16 : sw * 16 / sh;
        int dh = sh >= sw ? 16 : sh * 16 / sw;
        if (dw < 1) dw = 1;
        if (dh < 1) dh = 1;
        blit_box(s, src[v][0], src[v][1], sw, sh, atlas, 16 * nvar,
                 v * 16 + (16 - dw) / 2, bottom ? 16 - dh : (16 - dh) / 2, dw, dh);
    }

    ui->art[t].tex    = mk_tex(ui->ren, atlas, 16 * nvar, 16);
    ui->art[t].nvar   = nvar;
    ui->art[t].masked = false;
    ui->real_tiles++;
    return true;
}

/* Furniture that spans several Terraria tiles but one of ours: splice the
   frames together, then shrink the whole object into a single cell. */
static bool load_object(PxUi *ui, Tile t, const char *dir, const char *name,
                        int x0, int y0, int cols, int rows)
{
    Sheet s, obj;
    int src[1][4];
    bool ok;

    if (!sheet_load(ui, &s, dir, name)) return false;
    obj.w  = cols * 16;
    obj.h  = rows * 16;
    obj.px = malloc((size_t)obj.w * (size_t)obj.h * sizeof *obj.px);
    if (!obj.px) { sheet_free(&s); return false; }
    gather_frames(&s, x0, y0, cols, rows, obj.px);
    sheet_free(&s);

    src[0][0] = 0; src[0][1] = 0; src[0][2] = obj.w; src[0][3] = obj.h;
    ok = load_fitted(ui, t, &obj, src, 1, true);
    sheet_free(&obj);
    return ok;
}

static bool load_crops(PxUi *ui, Tile t, const char *dir, const char *name,
                       const int (*src)[4], int nvar, bool bottom)
{
    Sheet s;
    bool ok;
    if (!sheet_load(ui, &s, dir, name)) return false;
    ok = load_fitted(ui, t, &s, src, nvar, bottom);
    sheet_free(&s);
    return ok;
}

/* Terraria item ids for our 14 items, verified by eye against the sheets.
   ITEM_LANTERN has no id here: the real lantern item sprite is a dark chain
   lamp that reads as a black square at 16 px, so it borrows the tile art. */
static const int ITEM_ID[ITEM_COUNT] = {
    9, 3, 2, 12, 11, 13, 20, 22, 19, 8, -1, 36, 33, 35
};

/* Every icon but the lantern's is its own Item_N sheet, box-fitted into a
   16x16 cell; the lantern borrows its tile art back in px_init. */
static bool load_items(PxUi *ui, const char *dir)
{
    static uint32_t buf[16 * 16];
    char name[32];
    Sheet s;
    int i;

    for (i = 0; i < ITEM_COUNT; i++) {
        int dw, dh, k;
        if (ITEM_ID[i] < 0) continue;
        snprintf(name, sizeof name, "Item_%d", ITEM_ID[i]);
        if (!sheet_load(ui, &s, dir, name)) return false;

        for (k = 0; k < 16 * 16; k++) buf[k] = 0u;
        dw = s.w >= s.h ? 16 : s.w * 16 / s.h;
        dh = s.h >= s.w ? 16 : s.h * 16 / s.w;
        blit_box(&s, 0, 0, s.w, s.h, buf, 16, (16 - dw) / 2, (16 - dh) / 2, dw, dh);
        sheet_free(&s);

        ui->item[i] = mk_tex(ui->ren, buf, 16, 16);
        ui->item_owned[i] = true;
        ui->real_items++;
    }
    return true;
}

/* ---- Player avatar ------------------------------------------------------ *
 * Terraria's player is not a sprite but a stack of greyscale masks: one sheet
 * per layer, tinted at runtime and composited back to front. Which sheet holds
 * which layer was read off the pixels rather than remembered, because guessing
 * it is what makes this look like a mannequin:
 *
 *   Player_0_0 / _1 / _2      head skin, eye white, pupil
 *   Player_0_10 / _11 / _12   leg skin, pants, shoes
 *   Player_0_3 / _6           torso skin, shirt
 *   Player_0_7 / _8 / _4      arm skin, undershirt sleeve, shirt sleeve
 *   Player_0_5                hand
 *   Player_Hair_1             hair
 *
 * The strips are 20 frames of 40x56 stacked vertically -- the 0/1/2 sheets are
 * two rows short of the twentieth, which sheet_at clamps to transparent. The
 * torso/arm sheets are a 9x4 grid of the same frame: column 0 is the standing
 * torso and column 7 the arm hanging at the near side, and the rest are
 * item-use poses we never strike. The hair sheet's 14 frames line up with body
 * frames 6..19, so anything below that takes hair frame 0 (both are the
 * un-bobbed head position).
 *
 * Frame roles, likewise measured: 0 stands, 5 is the tucked jump, 6..19 walk. */

#define PL_FW      40            /* source frame */
#define PL_FH      56
#define PL_CW      26            /* composited cell; see PL_OX / PL_OY */
#define PL_CH      37
#define PL_FRAMES  20
#define PL_JUMP     5
#define PL_WALK0    6
#define PL_WALKN   14

/* Where the cell goes relative to the 16x32 body box. Chosen so the drawn
   pixels span exactly the box vertically -- feet on the feet cell's floor, no
   float and no sink -- and so the frame's centre line is the box's. The ~3 px
   of hair and shoulder that hang outside are decoration only: hit testing and
   the reach overlay still key off the true 1x2 body. */
#define PL_OX      (-5)
#define PL_OY      (-4)

/* Terraria's default character, nudged by eye against the tinted masks. */
#define PC_SKIN    0xFFFF7D5Au
#define PC_HAIR    0xFFD75A37u
#define PC_EYE     0xFFFFFFFFu
#define PC_PUPIL   0xFF695A4Bu
#define PC_SHIRT   0xFFAFA58Cu
#define PC_UNDER   0xFFA0B4D7u
#define PC_PANTS   0xFFFFE6AFu
#define PC_SHOES   0xFFA0693Cu

#define PL_ANIM    (-1)          /* vertical strip, frame = animation frame */
#define PL_HAIRS   (-2)          /* vertical strip, frame offset by PL_WALK0 */

typedef struct {
    const char *name;
    uint32_t    tint;
    int         col;             /* grid column, or PL_ANIM / PL_HAIRS */
} PlayerLayer;

/* Back to front. Bare skin goes under its garment even where the garment
   covers it completely, because a torn extraction should show skin, not a
   hole. */
static const PlayerLayer PLAYER_LAYER[] = {
    {"Player_0_10",   PC_SKIN,  PL_ANIM },
    {"Player_0_11",   PC_PANTS, PL_ANIM },
    {"Player_0_12",   PC_SHOES, PL_ANIM },
    {"Player_0_3",    PC_SKIN,  0       },
    {"Player_0_6",    PC_SHIRT, 0       },
    {"Player_0_7",    PC_SKIN,  7       },
    {"Player_0_8",    PC_UNDER, 7       },
    {"Player_0_4",    PC_SHIRT, 7       },
    {"Player_0_5",    PC_SKIN,  7       },
    {"Player_0_0",    PC_SKIN,  PL_ANIM },
    {"Player_0_1",    PC_EYE,   PL_ANIM },
    {"Player_0_2",    PC_PUPIL, PL_ANIM },
    {"Player_Hair_1", PC_HAIR,  PL_HAIRS}
};

#define PL_LAYERS ((int)(sizeof PLAYER_LAYER / sizeof *PLAYER_LAYER))

/* Straight-alpha source-over. The masks are hard-edged so this is a copy
   almost everywhere; it only earns its keep where an extraction has soft
   edges, and there it stops the layers fringing each other. */
static uint32_t blend_over(uint32_t dst, uint32_t src)
{
    int sa = CA(src), ia = CA(dst) * (255 - sa) / 255, oa = sa + ia;

    if (oa == 0) return 0u;
    return ((uint32_t)oa << 24) |
           ((uint32_t)((CR(src) * sa + CR(dst) * ia) / oa) << 16) |
           ((uint32_t)((CG(src) * sa + CG(dst) * ia) / oa) <<  8) |
            (uint32_t)((CB(src) * sa + CB(dst) * ia) / oa);
}

/* One animation frame, composited at source resolution into `out`. */
static void player_compose(uint32_t *out, const Sheet *sh, int f)
{
    int i, x, y;

    memset(out, 0, (size_t)PL_FW * PL_FH * sizeof *out);
    for (i = 0; i < PL_LAYERS; i++) {
        const PlayerLayer *L = &PLAYER_LAYER[i];
        int sx = L->col >= 0 ? L->col * PL_FW : 0;
        int sy = L->col == PL_HAIRS ? (f >= PL_WALK0 ? f - PL_WALK0 : 0) * PL_FH
               : L->col == PL_ANIM  ? f * PL_FH
               : 0;

        for (y = 0; y < PL_FH; y++)
            for (x = 0; x < PL_FW; x++) {
                uint32_t m = sheet_at(&sh[i], sx + x, sy + y), c;
                if (CA(m) == 0) continue;
                /* The mask's grey is the layer's shading, the tint its hue. */
                c = (m & 0xFF000000u) |
                    ((uint32_t)(CR(m) * CR(L->tint) / 255) << 16) |
                    ((uint32_t)(CR(m) * CG(L->tint) / 255) <<  8) |
                     (uint32_t)(CR(m) * CB(L->tint) / 255);
                out[y * PL_FW + x] = blend_over(out[y * PL_FW + x], c);
            }
    }
}

/* Composite all twenty frames once into an atlas, each stored twice: mirrored
   in the atlas rather than flipped at draw time, so the mirror axis is exactly
   the body column's centre line and the character does not shuffle sideways
   when it turns. Pre-rendering also keeps the 56 -> 32 resample off the frame
   path, where it would run twice a frame for nothing. */
static bool load_player(PxUi *ui, const char *dir)
{
    static uint32_t atlas[2 * PL_CH][PL_FRAMES * PL_CW];
    uint32_t frm[PL_FW * PL_FH];
    Sheet sh[PL_LAYERS];
    bool ok = true;
    int i, f, x, y;

    /* Every layer is attempted even once one has failed, so that the single
       teardown below covers the whole array; sheet_fail keeps the first name. */
    for (i = 0; i < PL_LAYERS; i++)
        if (!sheet_load(ui, &sh[i], dir, PLAYER_LAYER[i].name)) ok = false;

    if (ok) {
        memset(atlas, 0, sizeof atlas);
        for (f = 0; f < PL_FRAMES; f++) {
            player_compose(frm, sh, f);
            for (y = 0; y < PL_CH; y++)
                for (x = 0; x < PL_CW; x++) {
                    /* Point sampling. A box filter over art this chunky only
                       smears the face into a smudge; nearest keeps the eye. */
                    uint32_t c = frm[(y * PL_FH / PL_CH) * PL_FW + x * PL_FW / PL_CW];
                    atlas[y][f * PL_CW + x] = c;
                    /* Column 0 has no partner across the axis, and the frame
                       has nothing in it: the art starts two columns in. */
                    if (x > 0) atlas[PL_CH + y][f * PL_CW + PL_CW - x] = c;
                }
        }
        ui->player = mk_tex(ui->ren, atlas[0], PL_FRAMES * PL_CW, 2 * PL_CH);
    }

    for (i = 0; i < PL_LAYERS; i++) sheet_free(&sh[i]);
    return ok;
}

/* Sub-rects, all measured off the real sheets rather than guessed:
   the torch cell is 22 px wide with the sprite offset inside it, the little
   round lamp on row 1 of Tiles_42 is the only self-contained one-tile lantern,
   and the four leaf crops are opaque interior patches of a tree canopy. */
static const int TORCH_SRC[1][4]  = {{3, 2, 16, 16}};
static const int LAMP_SRC[1][4]   = {{0, 18, 16, 16}};
static const int LEAF_SRC[4][4]   = {{14, 22, 16, 16}, {30, 22, 16, 16},
                                     {46, 22, 16, 16}, {30, 38, 16, 16}};

/* Short-circuits on the first sheet that will not load: with no fallback there
   is nothing useful to say about the fourteen after it. */
static bool load_terraria(PxUi *ui, const char *dir)
{
    return load_grid(ui, TILE_DIRT,       dir, "Tiles_0",  100) &&
           load_grid(ui, TILE_STONE,      dir, "Tiles_1",  100) &&
           load_grid(ui, TILE_GRASS,      dir, "Tiles_2",  100) &&
           load_grid(ui, TILE_LOG,        dir, "Tiles_191", 100) &&
           load_grid(ui, TILE_WOOD,       dir, "Tiles_30", 100) &&
           load_grid(ui, TILE_COPPER_ORE, dir, "Tiles_7",  100) &&
           load_grid(ui, TILE_IRON_ORE,   dir, "Tiles_6",  100) &&
           load_grid(ui, TILE_GOLD_ORE,   dir, "Tiles_8",  100) &&
           /* Ebonstone at 45% is near-black with a purple cast: unmistakably a
              wall you are never getting through, which is bedrock's job. */
           load_grid(ui, TILE_BEDROCK,    dir, "Tiles_25",  45) &&

           load_crops (ui, TILE_LEAVES,    dir, "Tree_Tops_0", LEAF_SRC,  4, false) &&
           load_crops (ui, TILE_TORCH,     dir, "Tiles_4",     TORCH_SRC, 1, false) &&
           load_crops (ui, TILE_LANTERN,   dir, "Tiles_42",    LAMP_SRC,  1, false) &&
           load_object(ui, TILE_ANVIL,     dir, "Tiles_16", 0, 0, 2, 1) &&
           load_object(ui, TILE_WORKBENCH, dir, "Tiles_18", 0, 0, 2, 1) &&
           load_object(ui, TILE_FURNACE,   dir, "Tiles_17", 0, 0, 3, 2) &&

           load_items(ui, dir) &&
           load_player(ui, dir);
}

/* Cave walls are the buried frame of the same block sheet the foreground uses,
   so the two can never disagree about what rock looks like. */
static SDL_Texture *mk_bg_real(PxUi *ui, const char *dir, const char *name)
{
    static uint32_t buf[16 * 16];
    Sheet s;
    int x, y;

    if (!sheet_load(ui, &s, dir, name)) return NULL;
    for (y = 0; y < 16; y++)
        for (x = 0; x < 16; x++)
            buf[y * 16 + x] = backdrop(sheet_at(&s, 18 + x, 18 + y));   /* buried frame */
    sheet_free(&s);
    return mk_tex(ui->ren, buf, 16, 16);
}

static SDL_Texture *mk_font(SDL_Renderer *ren)
{
    static uint32_t atlas[95 * CELL_W * GLYPH_H];
    int g, x, y;

    memset(atlas, 0, sizeof atlas);
    for (g = 0; g < 95; g++)
        for (x = 0; x < GLYPH_W; x++)
            for (y = 0; y < GLYPH_H; y++)
                if (FONT5X7[g][x] & (1u << y))
                    atlas[y * (95 * CELL_W) + g * CELL_W + x] = 0xFFFFFFFFu;

    return mk_tex(ren, atlas, 95 * CELL_W, GLYPH_H);
}

/* ---- Primitive drawing -------------------------------------------------- */

static void set_col(PxUi *ui, uint32_t c)
{
    SDL_SetRenderDrawColor(ui->ren, (Uint8)CR(c), (Uint8)CG(c), (Uint8)CB(c), (Uint8)CA(c));
}

static void fill(PxUi *ui, int x, int y, int w, int h, uint32_t c)
{
    SDL_Rect r = {x, y, w, h};
    set_col(ui, c);
    SDL_RenderFillRect(ui->ren, &r);
}

static void frame(PxUi *ui, int x, int y, int w, int h, uint32_t c)
{
    SDL_Rect r = {x, y, w, h};
    set_col(ui, c);
    SDL_RenderDrawRect(ui->ren, &r);
}

static int text_w(const char *s) { return (int)strlen(s) * CELL_W - 1; }

static void text(PxUi *ui, int x, int y, uint32_t col, const char *s)
{
    SDL_Rect src = {0, 0, GLYPH_W, GLYPH_H};
    SDL_Rect dst = {x, y, GLYPH_W, GLYPH_H};

    SDL_SetTextureColorMod(ui->font, (Uint8)CR(col), (Uint8)CG(col), (Uint8)CB(col));
    SDL_SetTextureAlphaMod(ui->font, (Uint8)CA(col));
    for (; *s; s++) {
        int c = (unsigned char)*s;
        if (c < 32 || c > 126) c = '?';
        if (c != ' ') {
            src.x = (c - 32) * CELL_W;
            SDL_RenderCopy(ui->ren, ui->font, &src, &dst);
        }
        dst.x += CELL_W;
    }
}

static void textf(PxUi *ui, int x, int y, uint32_t col, const char *fmt, ...)
{
    char buf[160];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    text(ui, x, y, col, buf);
}

static void text_right(PxUi *ui, int xr, int y, uint32_t col, const char *s)
{
    text(ui, xr - text_w(s), y, col, s);
}

static void icon(PxUi *ui, SDL_Texture *tex, int x, int y, int size, int alpha)
{
    SDL_Rect dst = {x, y, size, size};
    if (!tex) return;
    SDL_SetTextureColorMod(tex, 255, 255, 255);
    SDL_SetTextureAlphaMod(tex, (Uint8)alpha);
    SDL_RenderCopy(ui->ren, tex, NULL, &dst);
    SDL_SetTextureAlphaMod(tex, 255);
}

/* A tile drawn outside the world: always the buried, first-variant frame. */
static void tile_icon(PxUi *ui, Tile t, int x, int y, int size, int alpha)
{
    const TileArt *a = &ui->art[t];
    SDL_Rect src = {0, a->masked ? 15 * PX_TILE : 0, PX_TILE, PX_TILE};
    SDL_Rect dst = {x, y, size, size};
    if (!a->tex) return;
    SDL_SetTextureColorMod(a->tex, 255, 255, 255);
    SDL_SetTextureAlphaMod(a->tex, (Uint8)alpha);
    SDL_RenderCopy(ui->ren, a->tex, &src, &dst);
    SDL_SetTextureAlphaMod(a->tex, 255);
}

/* ---- Init / teardown ---------------------------------------------------- */

/* Cheap presence test, and the file the whole load hangs off: if Tiles_0.png
   is not here, nothing else in the directory will be either. */
static bool has_sheets(const char *dir)
{
    char probe[1024];
    FILE *f;

    snprintf(probe, sizeof probe, "%s/Tiles_0.png", dir);
    f = fopen(probe, "rb");
    if (!f) return false;
    fclose(f);
    return true;
}

/* Where Steam puts Terraria, per platform. Probed in order; the first that
   contains Tiles_0.png wins. */
static bool probe_dir(char *out, size_t n)
{
    static const char *const REL[] = {
        "%s/Library/Application Support/Steam/steamapps/common/Terraria/ExtractedTextures",
        "%s/.steam/steam/steamapps/common/Terraria/ExtractedTextures",
        "%s/.local/share/Steam/steamapps/common/Terraria/ExtractedTextures",
    };
    const char *home = getenv("HOME");
    size_t i;

    if (!home) return false;
    for (i = 0; i < sizeof REL / sizeof *REL; i++) {
        snprintf(out, n, REL[i], home);
        if (has_sheets(out)) return true;
    }
    return false;
}

/* The two lines every failed load prints: what could not be read, and the one
   flag that fixes it. Modelled on the argument errors in src/main.c -- state
   the problem, then the remedy, and say nothing else. */
static void complain(const char *dir, const char *file)
{
    fprintf(stderr, "textures: cannot read %s/%s.png\n", dir, file);
    fprintf(stderr, "textures: a Terraria install is required; pass --textures DIR "
                    "to point at its ExtractedTextures directory\n");
}

PxUi *px_init(int scale, const char *tex_dir)
{
    static PxUi ui;   /* one window per process; no reason to heap this */
    char probed[1024];
    const char *dir = tex_dir;

    memset(&ui, 0, sizeof ui);

    /* Resolved before SDL is touched. A wrong or absent install is far and away
       the likeliest failure here, and diagnosing it must not flash a window. */
    if (!dir && probe_dir(probed, sizeof probed)) dir = probed;
    if (!dir) {
        fprintf(stderr, "textures: no Terraria install in any default Steam "
                        "location under $HOME\n");
        fprintf(stderr, "textures: a Terraria install is required; pass --textures DIR "
                        "to point at its ExtractedTextures directory\n");
        return NULL;
    }
    if (!has_sheets(dir)) {
        complain(dir, "Tiles_0");
        return NULL;
    }

    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        return NULL;
    }
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "0");   /* crisp pixels by default */

    ui.win = SDL_CreateWindow("terraria-lite",
                              SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                              PX_WIN_W * scale, PX_WIN_H * scale,
                              SDL_WINDOW_ALLOW_HIGHDPI);
    if (!ui.win) {
        fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError());
        px_shutdown(&ui);
        return NULL;
    }
    ui.ren = SDL_CreateRenderer(ui.win, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!ui.ren) ui.ren = SDL_CreateRenderer(ui.win, -1, SDL_RENDERER_SOFTWARE);
    if (!ui.ren) {
        fprintf(stderr, "SDL_CreateRenderer: %s\n", SDL_GetError());
        px_shutdown(&ui);
        return NULL;
    }
    SDL_RenderSetLogicalSize(ui.ren, PX_WIN_W, PX_WIN_H);
    SDL_SetRenderDrawBlendMode(ui.ren, SDL_BLENDMODE_BLEND);

    /* All or nothing, and the assignment order matters: mk_bg_real only runs
       once every tile is in, so `missing` always names the first casualty. */
    if (!load_terraria(&ui, dir) ||
        !(ui.bg_dirt  = mk_bg_real(&ui, dir, "Tiles_0")) ||
        !(ui.bg_stone = mk_bg_real(&ui, dir, "Tiles_1"))) {
        if (ui.missing[0])
            complain(dir, ui.missing);
        else
            fprintf(stderr, "textures: %s: %s\n", dir, SDL_GetError());
        px_shutdown(&ui);
        return NULL;
    }

    /* ITEM_LANTERN is the one item Terraria has no usable icon sheet for, so it
       shows its own tile art -- the same lamp, already cropped out of Tiles_42.
       Borrowed, not owned: art[TILE_LANTERN] is what frees it, exactly once. */
    ui.item[ITEM_LANTERN] = ui.art[TILE_LANTERN].tex;
    ui.real_items++;

    ui.font = mk_font(ui.ren);
    if (!ui.font) {
        fprintf(stderr, "font texture: %s\n", SDL_GetError());
        px_shutdown(&ui);
        return NULL;
    }

    ui.light = SDL_CreateTexture(ui.ren, SDL_PIXELFORMAT_ARGB8888,
                                 SDL_TEXTUREACCESS_STREAMING,
                                 PX_VIEW_TW + 2, PX_VIEW_TH + 2);
    if (!ui.light) {
        fprintf(stderr, "SDL_CreateTexture(light): %s\n", SDL_GetError());
        px_shutdown(&ui);
        return NULL;
    }
    /* The one texture that must NOT be nearest: sampling the light grid
       linearly is what turns per-tile light levels into a smooth falloff. */
    SDL_SetTextureScaleMode(ui.light, SDL_ScaleModeLinear);
    SDL_SetTextureBlendMode(ui.light, SDL_BLENDMODE_MOD);

    printf("textures: %d/%d tiles, %d/%d item icons and the player, from %s\n",
           ui.real_tiles, TILE_COUNT - 1, ui.real_items, ITEM_COUNT, dir);
    fflush(stdout);

    return &ui;
}

/* The window title is the only chrome a caller can write to. The frame loop
   uses it for out-of-band status -- which recorded step a replay is on --
   that has no place in the drawn HUD. */
void px_set_title(PxUi *ui, const char *title)
{
    if (ui && ui->win && title) SDL_SetWindowTitle(ui->win, title);
}

void px_shutdown(PxUi *ui)
{
    int i;
    if (!ui) { SDL_Quit(); return; }
    for (i = 0; i < TILE_COUNT; i++) if (ui->art[i].tex) SDL_DestroyTexture(ui->art[i].tex);
    for (i = 0; i < ITEM_COUNT; i++) if (ui->item_owned[i]) SDL_DestroyTexture(ui->item[i]);
    if (ui->bg_dirt)  SDL_DestroyTexture(ui->bg_dirt);
    if (ui->bg_stone) SDL_DestroyTexture(ui->bg_stone);
    if (ui->font)     SDL_DestroyTexture(ui->font);
    if (ui->light)    SDL_DestroyTexture(ui->light);
    if (ui->player)   SDL_DestroyTexture(ui->player);
    if (ui->ren)      SDL_DestroyRenderer(ui->ren);
    if (ui->win)      SDL_DestroyWindow(ui->win);
    SDL_Quit();
}

/* ---- Coordinates -------------------------------------------------------- */

bool px_pointer(const PxUi *ui, int *wx, int *wy)
{
    if (SDL_GetMouseFocus() != ui->win) {
        *wx = *wy = -1;
        return false;
    }
    SDL_GetMouseState(wx, wy);
    return true;
}

void px_to_art(const PxUi *ui, int wx, int wy, int *ax, int *ay)
{
    float fx = 0.0f, fy = 0.0f;
    SDL_RenderWindowToLogical(ui->ren, wx, wy, &fx, &fy);
    *ax = (int)floorf(fx);
    *ay = (int)floorf(fy);
}

static int cam_px(float c) { return (int)floorf(c * PX_TILE); }

void px_cell_at(const PxView *v, int ax, int ay, int *tx, int *ty)
{
    int wx = ax + cam_px(v->cam_x);
    int wy = ay + cam_px(v->cam_y);
    *tx = (wx >= 0) ? wx / PX_TILE : -1;
    *ty = (wy >= 0) ? wy / PX_TILE : -1;
}

void px_cell_centre(const PxView *v, int tx, int ty, int *ax, int *ay)
{
    *ax = tx * PX_TILE + PX_TILE / 2 - cam_px(v->cam_x);
    *ay = ty * PX_TILE + PX_TILE / 2 - cam_px(v->cam_y);
}

int px_recipe_at(int ax, int ay)
{
    int rel = ay - REC_Y0, r;
    if (ax < SX || ax >= PX_WIN_W || rel < 0) return -1;
    r = rel / REC_PITCH;
    if (r >= RECIPE_COUNT || rel % REC_PITCH >= REC_H) return -1;
    return r;
}

int px_ach_at(int ax, int ay)
{
    int gx = ax - ACH_X0, gy = ay - ACH_Y0, c, r;
    if (gx < 0 || gy < 0) return -1;
    c = gx / ACH_PITCH;
    r = gy / ACH_PITCH;
    if (gx % ACH_PITCH >= ACH_CELL || gy % ACH_PITCH >= ACH_CELL) return -1;
    if (c >= ACH_COLS || r * ACH_COLS + c >= ACH_COUNT) return -1;
    return r * ACH_COLS + c;
}

/* The inventory strip is one slot per *item*, but selection cycles over
   PLACEABLES, so a hit has to be translated back. Items with nothing to place
   -- ores, bars, the pickaxes -- are not on that cycle and report -1. */
int px_hotbar_at(int ax, int ay)
{
    int gx = ax - INV_X0, gy = ay - INV_Y0, i, p;

    if (gx < 0 || gy < 0 || gy >= INV_SLOT) return -1;
    i = gx / INV_PITCH;
    if (i >= ITEM_COUNT || gx % INV_PITCH >= INV_SLOT) return -1;

    for (p = 0; p < PLACEABLE_COUNT; p++)
        if (PLACEABLES[p].item == (Item)i) return p;
    return -1;
}

/* ---- Crafting availability ---------------------------------------------- */

static bool station_near(const Env *e, Tile st)
{
    int dx, dy;
    if (st == TILE_AIR) return true;
    for (dy = -STATION_RANGE; dy <= STATION_RANGE; dy++)
        for (dx = -STATION_RANGE; dx <= STATION_RANGE; dx++)
            if (tile_at(e, e->px + dx, e->py + dy) == st) return true;
    return false;
}

bool px_recipe_ready(const Env *e, int r)
{
    const Recipe *rc = &RECIPES[r];
    int i;
    for (i = 0; i < rc->n_in; i++)
        if (e->inv[rc->in_item[i]] < rc->in_qty[i]) return false;
    return station_near(e, rc->station);
}

/* ---- World -------------------------------------------------------------- */

/* Perceived brightness of one tile, 0..1. Continuous through DARK_THRESHOLD so
   the bilinear pass has nothing to step over, and gamma-shaped because a torch
   whose pool fades linearly looks like a spotlight, not firelight. */
static float tile_bright(const Env *e, int x, int y)
{
    float t;
    if (!in_bounds(x, y)) return 0.0f;
    t = (float)((int)e->light[y][x] - (DARK_THRESHOLD - 1)) /
        (float)(LIGHT_MAX - (DARK_THRESHOLD - 1));
    if (t <= 0.0f) return 0.0f;
    if (t >= 1.0f) return 1.0f;
    return powf(t, 0.72f);
}

static uint32_t sky_col(int y)
{
    int t = y * 256 / (SURFACE_MAX + 8);
    if (t > 256) t = 256;
    return mix(0xFF3E74C6u, 0xFFAEDAF4u, t);
}

/* Which frame a block wears: bit per solid neighbour, matching FRAME_TAB.
   Out-of-world reads come back as bedrock, so the map borders merge shut
   instead of drawing a rim of exposed edges. */
static int tile_mask(const Env *e, int x, int y)
{
    int m = 0;
    if (tile_solid(tile_at(e, x, y - 1))) m |= 1;
    if (tile_solid(tile_at(e, x, y + 1))) m |= 2;
    if (tile_solid(tile_at(e, x - 1, y))) m |= 4;
    if (tile_solid(tile_at(e, x + 1, y))) m |= 8;
    return m;
}

/* How far a wall backdrop is pulled in on a side that fronts open sky, in art
   px. Terraria's block sprites fade out over their outermost pixels, so an
   eighth of a tile is enough to hide the backdrop's edge under the sprite's
   own opaque core without eating into anything the sprite draws solid. */
#define BG_INSET 2

/* True when this cell shows sky rather than a wall. The skyline is worldgen's
   static surface[], never the live tiles, and the grass tile sits *at* it --
   so the grass row counts as outdoors, while a shaft the player digs below the
   line keeps its wall: down there you are looking at the back of a tunnel. */
static bool bg_is_sky(const Env *e, int x, int y)
{
    return y <= e->surface[x];
}

/* ...and that neighbour is genuinely open sky, not just a hole in the rock. */
static bool sky_neighbour(const Env *e, int x, int y)
{
    return in_bounds(x, y) && e->tiles[y][x] == TILE_AIR && bg_is_sky(e, x, y);
}

static void draw_world(PxUi *ui, const Env *e, const PxView *v)
{
    int camx = cam_px(v->cam_x), camy = cam_px(v->cam_y);
    int t0x = camx / PX_TILE, t0y = camy / PX_TILE;
    int tx, ty;

    for (ty = t0y; ty <= t0y + PX_VIEW_TH; ty++)
        for (tx = t0x; tx <= t0x + PX_VIEW_TW; tx++) {
            int sx = tx * PX_TILE - camx;
            int sy = ty * PX_TILE - camy;
            SDL_Rect dst = {sx, sy, PX_TILE, PX_TILE};
            const TileArt *a;
            SDL_Rect src;
            Tile t;

            if (!in_bounds(tx, ty)) {
                fill(ui, sx, sy, PX_TILE, PX_TILE, VOID_COL);
                continue;
            }
            t = (Tile)e->tiles[ty][tx];

            /* Backdrop first: air cells are otherwise a hole in the picture.
               Drawing the grass row as underground put dirt behind Terraria's
               shaped grass tops, which showed through their transparent notches
               as a brown fringe against the sky. */
            if (bg_is_sky(e, tx, ty)) {
                fill(ui, sx, sy, PX_TILE, PX_TILE, sky_col(ty));
            } else {
                /* Rows [surface + 1, surface + DIRT_DEPTH] are the dirt worldgen
                   lays down; stone starts below them. */
                SDL_Texture *wall = ty <= e->surface[tx] + DIRT_DEPTH ? ui->bg_dirt
                                                                      : ui->bg_stone;
                /* Same leak, general case: any block whose edge pixels are
                   partly transparent bleeds its backdrop out past itself where
                   it fronts sky. Lay the sky across the whole cell and pull the
                   wall in on the sky-facing sides, so what seeps through the
                   sprite's rim is sky and the inset margin is never a hole.
                   Only sky neighbours count -- an air cell underground paints
                   the very same wall we do, so insetting towards it would cut a
                   seam into what reads as one continuous surface. A sky
                   neighbour below is impossible: the skyline only rises. */
                int l = 0, r = 0, u = 0;

                if (tile_solid(t)) {
                    if (sky_neighbour(e, tx - 1, ty)) l = BG_INSET;
                    if (sky_neighbour(e, tx + 1, ty)) r = BG_INSET;
                    if (sky_neighbour(e, tx, ty - 1)) u = BG_INSET;
                }
                if (l || r || u) {
                    /* Crop the texture instead of squashing it, so the wall
                       stays pixel-aligned with the cells around it. */
                    SDL_Rect wsrc = {l, u, PX_TILE - l - r, PX_TILE - u};
                    SDL_Rect wdst = {sx + l, sy + u, wsrc.w, wsrc.h};

                    fill(ui, sx, sy, PX_TILE, PX_TILE, sky_col(ty));
                    SDL_RenderCopy(ui->ren, wall, &wsrc, &wdst);
                } else {
                    SDL_RenderCopy(ui->ren, wall, NULL, &dst);
                }
            }

            if (t == TILE_AIR) continue;

            a = &ui->art[t];
            src.x = (int)(hash2(tx, ty, 0x5EEDu) % (uint32_t)a->nvar) * PX_TILE;
            src.y = a->masked ? tile_mask(e, tx, ty) * PX_TILE : 0;
            src.w = PX_TILE;
            src.h = PX_TILE;
            SDL_SetTextureAlphaMod(a->tex, 255);
            /* A canopy is a solid green rectangle otherwise: Terraria draws
               tree tops as one big sprite, we tile them, so the depth has to
               be faked with a per-cell shade. */
            if (t == TILE_LEAVES) {
                Uint8 s = (Uint8)(200 + hash2(tx, ty, 0xF0Au) % 56u);
                SDL_SetTextureColorMod(a->tex, s, s, s);
            } else {
                SDL_SetTextureColorMod(a->tex, 255, 255, 255);
            }
            SDL_RenderCopy(ui->ren, a->tex, &src, &dst);
        }
}

static void draw_light(PxUi *ui, const Env *e, const PxView *v)
{
    enum { LW = PX_VIEW_TW + 2, LH = PX_VIEW_TH + 2 };
    uint32_t buf[LH][LW];
    int camx = cam_px(v->cam_x), camy = cam_px(v->cam_y);
    int t0x = camx / PX_TILE, t0y = camy / PX_TILE;
    int i, j;
    SDL_Rect dst;

    /* Texel (i, j) is the *corner* shared by four tiles, so its value is their
       mean. Stretching that grid by one tile with linear filtering gives exact
       bilinear interpolation across every tile interior. */
    for (j = 0; j < LH; j++)
        for (i = 0; i < LW; i++) {
            int cx = t0x + i, cy = t0y + j;
            float b = 0.25f * (tile_bright(e, cx - 1, cy - 1) + tile_bright(e, cx, cy - 1) +
                               tile_bright(e, cx - 1, cy)     + tile_bright(e, cx, cy));
            /* Warm at low light, neutral in daylight: a torch should read as
               fire, not as a grey dimmer. */
            buf[j][i] = rgb((int)(b * 255.0f),
                            (int)(b * (0.70f + 0.30f * b) * 255.0f),
                            (int)(b * (0.46f + 0.54f * b) * 255.0f));
        }

    SDL_UpdateTexture(ui->light, NULL, buf, LW * (int)sizeof(uint32_t));

    dst.x = t0x * PX_TILE - camx - PX_TILE / 2;
    dst.y = t0y * PX_TILE - camy - PX_TILE / 2;
    dst.w = LW * PX_TILE;
    dst.h = LH * PX_TILE;
    SDL_RenderCopy(ui->ren, ui->light, NULL, &dst);
}

/* ---- Player ------------------------------------------------------------- *
 * The composited Terraria avatar, built once by load_player. It overhangs the
 * 1x2 body box by a few pixels of hair and shoulder, which is decoration only:
 * hit testing keys off the body cells alone. */

/* Which of the twenty frames the pose calls for. The walk rate is by eye: the
   14-frame cycle at 18 fps is roughly one stride per body length at our run
   speed, which is what stops the feet skating. */
static int player_frame(const PxView *v)
{
    if (v->airborne) return PL_JUMP;
    if (v->walk_dir != 0)
        return PL_WALK0 + (int)fmod(v->clock * 18.0, (double)PL_WALKN);
    return 0;
}

static void draw_player(PxUi *ui, const Env *e, const PxView *v, int alpha)
{
    int bx = (int)lroundf(v->feet_x * PX_TILE) - cam_px(v->cam_x);
    int by = (int)lroundf(v->feet_y * PX_TILE) - cam_px(v->cam_y) + PX_TILE - PLAYER_H * PX_TILE;
    SDL_Rect src = {player_frame(v) * PL_CW, e->facing < 0 ? PL_CH : 0, PL_CW, PL_CH};
    SDL_Rect dst = {bx + PL_OX, by + PL_OY, PL_CW, PL_CH};

    SDL_SetTextureAlphaMod(ui->player, (Uint8)alpha);
    SDL_RenderCopy(ui->ren, ui->player, &src, &dst);
}

/* ---- Reach overlay ------------------------------------------------------ */

static void draw_reach(PxUi *ui, const Env *e, const PxView *v)
{
    int camx = cam_px(v->cam_x), camy = cam_px(v->cam_y);
    int i;

    for (i = 0; i < REACH_COUNT; i++) {
        int tx = e->px + REACH_DX[i], ty = e->py + REACH_DY[i];
        int sx = tx * PX_TILE - camx, sy = ty * PX_TILE - camy;
        if (!in_bounds(tx, ty)) continue;
        frame(ui, sx, sy, PX_TILE, PX_TILE, 0x24FFFFFFu);
    }

    if (v->hover_reach >= 0) {
        int tx = e->px + REACH_DX[v->hover_reach], ty = e->py + REACH_DY[v->hover_reach];
        int sx = tx * PX_TILE - camx, sy = ty * PX_TILE - camy;
        bool empty = tile_at(e, tx, ty) == TILE_AIR;
        bool ok = empty ? v->can_place : v->can_mine;
        uint32_t c = ok ? UI_GOOD : UI_BAD;

        /* A placement preview only makes sense on an empty cell, and only when
           the placement would actually land. */
        if (empty && v->can_place)
            tile_icon(ui, PLACEABLES[e->selected].tile, sx, sy, PX_TILE, 110);

        /* The cell now *snaps* to whichever reach square the cursor is nearest,
           so this marker is the only thing telling you which one won. Corner
           brackets on top of the wash make the jump between neighbours read at
           a glance, where a plain tint alone just looked like a lit tile. */
        fill(ui, sx, sy, PX_TILE, PX_TILE, (c & 0x00FFFFFFu) | 0x38000000u);
        frame(ui, sx, sy, PX_TILE, PX_TILE, (c & 0x00FFFFFFu) | 0xF0000000u);
        frame(ui, sx + 1, sy + 1, PX_TILE - 2, PX_TILE - 2, (c & 0x00FFFFFFu) | 0x50000000u);
        {
            uint32_t k = (c & 0x00FFFFFFu) | 0xFF000000u;
            int L = 4, j;
            for (j = 0; j < 2; j++) {
                int ox = j ? PX_TILE - L : 0;
                int cx = j ? PX_TILE - 1 : 0;
                fill(ui, sx + ox, sy, L, 2, k);
                fill(ui, sx + ox, sy + PX_TILE - 2, L, 2, k);
                fill(ui, sx + cx - (j ? 1 : 0), sy, 2, L, k);
                fill(ui, sx + cx - (j ? 1 : 0), sy + PX_TILE - L, 2, L, k);
            }
        }
    }
}

/* ---- HUD ---------------------------------------------------------------- */

static const char HEART[7][9] = {
    ".##..##.",
    "########",
    "########",
    "########",
    ".######.",
    "..####..",
    "...##...",
};

static void draw_heart(PxUi *ui, int x, int y, bool full)
{
    int r, c;
    for (r = 0; r < 7; r++)
        for (c = 0; c < 8; c++) {
            if (HEART[r][c] != '#') continue;
            if (full) {
                uint32_t col = (r < 2) ? mix(UI_HEART, 0xFFFFFFFFu, 70) : UI_HEART;
                fill(ui, x + c, y + r, 1, 1, col);
            } else {
                fill(ui, x + c, y + r, 1, 1, 0xFF2A1F26u);
            }
        }
}

static const char *const TIER_NAME[4] = {
    "bare hands", "stone pickaxe", "copper pickaxe", "iron pickaxe"
};

static void draw_hud(PxUi *ui, const Env *e, const PxView *v)
{
    char buf[96];
    int i, hearts;

    fill(ui, 0, HY, PX_VIEW_W, PX_HUD_H, UI_BG);
    fill(ui, 0, HY, PX_VIEW_W, 1, UI_LINE);

    hearts = e->health < 0 ? 0 : e->health;
    for (i = 0; i < MAX_HEALTH; i++) draw_heart(ui, 6 + i * 9, HY + 5, i < hearts);

    text(ui, 6 + MAX_HEALTH * 9 + 10, HY + 5, UI_ACCENT,
         TIER_NAME[e->tool_tier < 4 ? e->tool_tier : 3]);

    snprintf(buf, sizeof buf, "depth %d   step %d/%d   return %+.1f",
             e->py, e->steps, e->max_steps, (double)e->ep_return);
    text_right(ui, PX_VIEW_W - 6, HY + 5, UI_DIM, buf);

    text(ui, 6, HY + 17, e->msg[0] ? UI_TEXT : UI_FAINT, e->msg[0] ? e->msg : "-");

    /* Inventory: all 14 slots always, so the ladder you are climbing is
       visible as a row of things you do not have yet. Only the placeable ones
       are clickable, so only those light up under the cursor. */
    for (i = 0; i < ITEM_COUNT; i++) {
        int x = INV_X0 + i * INV_PITCH;
        int have = e->inv[i];
        bool hot = v->hover_slot >= 0 && PLACEABLES[v->hover_slot].item == (Item)i;
        fill(ui, x, INV_Y0, INV_SLOT, INV_SLOT, hot ? UI_BG3 : (have ? UI_BG2 : UI_BG));
        frame(ui, x, INV_Y0, INV_SLOT, INV_SLOT,
              hot ? (have ? UI_ACCENT : UI_FAINT) : (have ? UI_LINE : 0xFF262330u));
        icon(ui, ui->item[i], x + 2, INV_Y0 + 2, PX_TILE, have ? 255 : 44);
        if (have) {
            snprintf(buf, sizeof buf, "%d", have);
            fill(ui, x + INV_SLOT - text_w(buf) - 2, INV_Y0 + INV_SLOT - 8,
                 text_w(buf) + 2, 8, 0xC0000000u);
            text_right(ui, x + INV_SLOT - 1, INV_Y0 + INV_SLOT - 8, UI_TEXT, buf);
        }
    }

    {   /* Selected placeable, called out because E is easy to forget. */
        int x = INV_X0 + ITEM_COUNT * INV_PITCH + 8;
        Item it = PLACEABLES[e->selected].item;
        int have = e->inv[it];
        fill(ui, x, INV_Y0, INV_SLOT, INV_SLOT, UI_BG3);
        frame(ui, x, INV_Y0, INV_SLOT, INV_SLOT, UI_ACCENT);
        tile_icon(ui, PLACEABLES[e->selected].tile, x + 2, INV_Y0 + 2, PX_TILE, have ? 255 : 60);
        text(ui, x + 25, INV_Y0 + 2, have ? UI_TEXT : UI_FAINT, ITEM_NAME[it]);
        textf(ui, x + 25, INV_Y0 + 12, have ? UI_ACCENT : UI_BAD, "x%d  [e]", have);
    }

    /* What a click would do right now, spelled out. The hotbar wins the line
       when the cursor is on it: the reach target is unreachable from there by
       construction, so there is nothing else this row could be reporting. */
    if (v->hover_slot >= 0) {
        Item it = PLACEABLES[v->hover_slot].item;
        int have = e->inv[it];
        snprintf(buf, sizeof buf, "hotbar  %s  x%d  -  %s", ITEM_NAME[it], have,
                 have ? (v->hover_slot == e->selected ? "already selected"
                                                      : "lmb selects it")
                      : "empty stack, cannot be selected");
        text(ui, 6, HY + 56, have ? UI_GOOD : UI_BAD, buf);
    } else if (v->hover_reach >= 0) {
        Tile t = tile_at(e, v->hover_x, v->hover_y);
        if (t != TILE_AIR)
            snprintf(buf, sizeof buf, "target  %s  %s  -  %s", REACH_NAME[v->hover_reach],
                     TILE_INFO[t].name,
                     v->can_mine ? "lmb mines it"
                                 : (tile_tier(t) == TIER_NEVER ? "unbreakable"
                                                               : "pickaxe too weak"));
        else
            snprintf(buf, sizeof buf, "target  %s  empty  -  %s", REACH_NAME[v->hover_reach],
                     v->can_place ? "rmb places it" : "nothing to place");
        text(ui, 6, HY + 56, (v->can_mine || v->can_place) ? UI_GOOD : UI_BAD, buf);
    } else {
        text(ui, 6, HY + 56, UI_FAINT, "target  -  point into the world to aim");
    }

    text(ui, 6, HY + 68, UI_FAINT,
         "a d walk   w jump   lmb mine   rmb place   e cycle   r new world   q quit");
}

/* ---- Sidebar ------------------------------------------------------------ */

static const char RECIPE_KEY[RECIPE_COUNT] = {
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-'
};

static void recipe_inputs(const Recipe *rc, char *out, size_t n)
{
    if (rc->n_in == 2)
        snprintf(out, n, "%d %s + %d %s", rc->in_qty[0], ITEM_NAME[rc->in_item[0]],
                 rc->in_qty[1], ITEM_NAME[rc->in_item[1]]);
    else
        snprintf(out, n, "%d %s", rc->in_qty[0], ITEM_NAME[rc->in_item[0]]);
}

static void draw_reach_key_grid(PxUi *ui, const PxView *v, int gx, int gy)
{
    static const char KEYCH[REACH_COUNT] = {'y','u','i','h','k','n','m',',','.','/'};
    int col, row;

    for (row = 0; row < 4; row++)
        for (col = 0; col < 3; col++) {
            int x = gx + col * 16, y = gy + row * 14;
            int dx = col - 1, dy = row - 2;
            int k;
            if (dx == 0 && (dy == -1 || dy == 0)) {   /* the body's own cells */
                fill(ui, x, y, 13, 12, UI_BG3);
                fill(ui, x + 4, y + 2, 5, 8, UI_BODY);
                continue;
            }
            for (k = 0; k < REACH_COUNT; k++)
                if (REACH_DX[k] == dx && REACH_DY[k] == dy) break;
            fill(ui, x, y, 13, 12, v->hover_reach == k ? UI_ACCENT : UI_BG2);
            textf(ui, x + 4, y + 3, v->hover_reach == k ? UI_BG : UI_DIM, "%c", KEYCH[k]);
        }
}

static void draw_sidebar(PxUi *ui, const Env *e, const PxView *v)
{
    char buf[96];
    int i, done = 0;

    fill(ui, SX, 0, PX_SIDE_W, PX_WIN_H, UI_BG);
    fill(ui, SX, 0, 1, PX_WIN_H, UI_LINE);

    text(ui, SX + 6, 6, UI_ACCENT, "CRAFTING");

    for (i = 0; i < RECIPE_COUNT; i++) {
        const Recipe *rc = &RECIPES[i];
        int y = REC_Y0 + i * REC_PITCH;
        bool ready = px_recipe_ready(e, i);
        bool hot = (v->hover_recipe == i);

        /* The hover frame carries the same verdict px_recipe_ready already
           greys the row out with, so the cursor tells you whether the click is
           worth spending a step on before you spend it. */
        fill(ui, SX + 2, y, PX_SIDE_W - 4, REC_H, hot ? UI_BG3 : (ready ? UI_BG2 : UI_BG));
        if (hot) {
            uint32_t hc = ready ? UI_GOOD : UI_BAD;
            fill(ui, SX + 2, y, PX_SIDE_W - 4, REC_H, (hc & 0x00FFFFFFu) | 0x22000000u);
            frame(ui, SX + 2, y, PX_SIDE_W - 4, REC_H, hc);
        }

        fill(ui, SX + 5, y + 5, 9, 9, ready ? UI_ACCENT : UI_LINE);
        textf(ui, SX + 7, y + 6, ready ? UI_BG : UI_FAINT, "%c", RECIPE_KEY[i]);

        text(ui, SX + 18, y + 2, ready ? UI_TEXT : UI_FAINT, rc->name);
        recipe_inputs(rc, buf, sizeof buf);
        text(ui, SX + 18, y + 11, ready ? UI_DIM : 0xFF433F52u, buf);

        if (rc->station != TILE_AIR)
            tile_icon(ui, rc->station, PX_WIN_W - 18, y + 3, 13, ready ? 230 : 70);
        if (has_ach(e, rc->ach)) text(ui, PX_WIN_W - 8, y + 6, UI_GOOD, "*");
    }

    fill(ui, SX + 6, REC_Y0 + RECIPE_COUNT * REC_PITCH + 4, PX_SIDE_W - 12, 1, UI_LINE);

    for (i = 0; i < ACH_COUNT; i++) if (has_ach(e, i)) done++;
    textf(ui, SX + 6, ACH_Y0 - 12, UI_ACCENT, "ACHIEVEMENTS %d/%d", done, ACH_COUNT);

    for (i = 0; i < ACH_COUNT; i++) {
        int x = ACH_X0 + (i % ACH_COLS) * ACH_PITCH;
        int y = ACH_Y0 + (i / ACH_COLS) * ACH_PITCH;
        bool got = has_ach(e, i);
        fill(ui, x, y, ACH_CELL, ACH_CELL, got ? UI_GOOD : UI_BG2);
        frame(ui, x, y, ACH_CELL, ACH_CELL, got ? mix(UI_GOOD, 0xFFFFFFFFu, 80) : UI_LINE);
        if (got) fill(ui, x + 3, y + 3, ACH_CELL - 6, ACH_CELL - 6,
                      mix(UI_GOOD, 0xFFFFFFFFu, 120));
        if (v->hover_ach == i) frame(ui, x - 1, y - 1, ACH_CELL + 2, ACH_CELL + 2, UI_ACCENT);
    }

    /* Hovering names one; otherwise name the next one still locked, which is
       the closest thing this game has to a quest log. */
    if (v->hover_ach >= 0) {
        text(ui, SX + 6, ACH_Y0 + 3 * ACH_PITCH + 2,
             has_ach(e, v->hover_ach) ? UI_GOOD : UI_DIM, ACH_NAME[v->hover_ach]);
    } else {
        for (i = 0; i < ACH_COUNT && has_ach(e, i); i++) { }
        if (i < ACH_COUNT)
            textf(ui, SX + 6, ACH_Y0 + 3 * ACH_PITCH + 2, UI_FAINT, "next: %s", ACH_NAME[i]);
    }

    fill(ui, SX + 6, 322, PX_SIDE_W - 12, 1, UI_LINE);
    text(ui, SX + 6, 332, UI_DIM,   "REACH");
    text(ui, SX + 6, 342, UI_DIM,   "KEYS");
    text(ui, SX + 6, 358, UI_FAINT, "shift");
    text(ui, SX + 6, 368, UI_FAINT, "=place");
    draw_reach_key_grid(ui, v, SX + 74, 332);
}

/* ---- Overlays ----------------------------------------------------------- */

static void draw_toast(PxUi *ui, const PxView *v)
{
    uint32_t a;
    int w;
    if (!v->toast || v->toast_a <= 0.0f) return;
    a = (uint32_t)(v->toast_a * 255.0f);
    if (a > 255u) a = 255u;
    w = text_w(v->toast) + 16;
    fill(ui, (PX_VIEW_W - w) / 2, 12, w, 18, ((a * 3u / 4u) << 24));
    frame(ui, (PX_VIEW_W - w) / 2, 12, w, 18, (a << 24) | (UI_ACCENT & 0xFFFFFFu));
    text(ui, (PX_VIEW_W - w) / 2 + 8, 17, (a << 24) | (UI_ACCENT & 0xFFFFFFu), v->toast);
}

static void draw_hurt_vignette(PxUi *ui, const Env *e, const PxView *v)
{
    float pulse;
    int i, peak;

    if (e->health > 3 || e->health <= 0) return;
    pulse = 0.5f + 0.5f * sinf((float)v->clock * 6.0f);
    peak = 10 + (int)(pulse * 34.0f);
    for (i = 0; i < 14; i++) {
        uint32_t a = (uint32_t)(peak * (14 - i) / 14);
        frame(ui, i, i, PX_VIEW_W - 2 * i, PX_VIEW_H - 2 * i, (a << 24) | 0xC02020u);
    }
}

static void draw_gameover(PxUi *ui, const Env *e)
{
    int w = 300, h = 132;
    int x = (PX_VIEW_W - w) / 2, y = (PX_VIEW_H - h) / 2;
    int i, done = 0;

    fill(ui, 0, 0, PX_VIEW_W, PX_VIEW_H, 0xB4080610u);
    fill(ui, x, y, w, h, UI_BG);
    frame(ui, x, y, w, h, UI_ACCENT);
    frame(ui, x + 1, y + 1, w - 2, h - 2, UI_LINE);

    for (i = 0; i < ACH_COUNT; i++) if (has_ach(e, i)) done++;

    text(ui, x + 16, y + 16, e->terminated ? UI_BAD : UI_ACCENT,
         e->terminated ? "YOU DIED" : "OUT OF TIME");
    text(ui, x + 16, y + 30, UI_FAINT,
         e->terminated ? "the fall got you, or the dark did"
                       : "the step budget ran out");

    textf(ui, x + 16, y + 52,  UI_TEXT, "seed         %llu", (unsigned long long)e->seed);
    textf(ui, x + 16, y + 64,  UI_TEXT, "depth        %d", e->py);
    textf(ui, x + 16, y + 76,  UI_TEXT, "steps        %d / %d", e->steps, e->max_steps);
    textf(ui, x + 16, y + 88,  UI_TEXT, "return       %+.2f", (double)e->ep_return);
    textf(ui, x + 16, y + 100, UI_TEXT, "achievements %d / %d", done, ACH_COUNT);

    text(ui, x + 16, y + h - 18, UI_ACCENT, "[r] new world      [q] quit");
}

/* ---- Frame -------------------------------------------------------------- */

void px_draw(PxUi *ui, const Env *e, const PxView *v)
{
    SDL_Rect view = {0, 0, PX_VIEW_W, PX_VIEW_H};
    bool over = e->terminated || e->truncated;

    set_col(ui, VOID_COL);
    SDL_RenderClear(ui->ren);

    SDL_RenderSetClipRect(ui->ren, &view);
    draw_world(ui, e, v);
    draw_player(ui, e, v, 255);
    draw_light(ui, e, v);
    /* After the light pass so the dark never swallows you completely: the
       engine grants PLAYER_LIGHT 3, which is deliberately almost nothing. */
    draw_player(ui, e, v, 34);
    if (!over) draw_reach(ui, e, v);
    draw_hurt_vignette(ui, e, v);
    draw_toast(ui, v);
    if (over) draw_gameover(ui, e);
    SDL_RenderSetClipRect(ui->ren, NULL);

    draw_hud(ui, e, v);
    draw_sidebar(ui, e, v);

    SDL_RenderPresent(ui->ren);
}
