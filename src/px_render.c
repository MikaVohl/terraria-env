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
#include "keymap.h"

/* ---- Layout ------------------------------------------------------------- *
 * Shared between the draw code and the hit tests so a click always lands on
 * the thing it looks like it lands on. */

#define SX          PX_VIEW_W          /* left edge of the sidebar */
#define HY          PX_VIEW_H          /* top edge of the HUD strip */

#define REC_Y0      18
#define REC_PITCH   19
#define REC_H       18

#define ACH_X0      (PX_VIEW_W + 10)
#define ACH_Y0      (REC_Y0 + RECIPE_COUNT * REC_PITCH + 22)
#define ACH_PITCH   16
#define ACH_CELL    13
#define ACH_COLS    8                  /* v4; v10 lays out one row per tier */

#define INV_X0      6
#define INV_Y0      (HY + 29)
#define INV_PITCH   22
#define INV_SLOT    20
#define INV_COLS    21

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

/* Body armor sheets, by Env.armor - 1 (wood breastplate, iron chainmail, and
   v10's gold chainmail); NPC sheets by MobKind - 1. */
#if PX_V10
#define PX_ARMORS   ARMOR_LEVELS
#define PX_MOBS     (MOB_KINDS - 1)
#else
#define PX_ARMORS   3
#define PX_MOBS     2
#endif
static const char *const ARMOR_SHEET[PX_ARMORS - 1] = {
    "Armor/Armor_32", "Armor/Armor_2",
#if PX_V10
    "Armor/Armor_4",
#endif
};
static const char *const MOB_SHEET[PX_MOBS] = {
    "NPC_1", "NPC_49",
#if PX_V10
    "NPC_3", "NPC_2", "NPC_21",
#endif
};
#if PX_V10
#define PX_FLASH      0.12   /* hit flash, seconds */
#define PX_POP_LIFE   1.0    /* damage number lifetime, seconds (CombatText ~60 ticks) */
#define PX_STAB_TICKS 16     /* copper shortsword stab projectile life (AI_161) */
#endif
/* Mining tier: v10 derives it from the pickaxes owned (EXPLICIT_TOOLS); the
   sprite index is never below the copper pickaxe. */
#if PX_V10
#define PX_PICK(e) (pick_tier(e) > 1 ? pick_tier(e) : 1)
#else
#define PX_PICK(e) ((e)->tool_tier)
#endif


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
    SDL_Texture  *player[PX_ARMORS];  /* unequipped + each armor; original sheets */
    SDL_Texture  *mob[PX_MOBS];       /* unmodified original NPC sprite strips */
#if PX_V10
    SDL_Texture  *obj[TILE_COUNT];    /* multi-cell objects at full size (w*16 x h*16) */
    SDL_Texture  *boss;               /* NPC_4, Eye of Cthulhu */
    /* Held items at their original size for the use animations: weapons by
       WEAPON_ITEM index, then copper / iron / gold pickaxe and the axe. */
    SDL_Texture  *held[WEAPON_COUNT + 4];
    int           held_w[WEAPON_COUNT + 4], held_h[WEAPON_COUNT + 4];
    SDL_Texture  *tree_top;           /* Tree_Tops_0: 3 forest canopies, 80x80 */
    SDL_Texture  *tree_branch;        /* Tree_Branches_0: left / right x 3, 40x40 */
#if BG_WALLS
    SDL_Texture  *wall_sheet[WALL_COUNT]; /* original Wall_N sheets (36 px frames) */
#endif
#endif
    SDL_Texture  *pick[3];            /* copper, iron, gold: original item sprites */
    SDL_Texture  *axe;                /* starter Copper Axe, original Item_3506 */
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
#if PX_V10
    /* v10 objects really occupy their Terraria footprint (object_part), so
       the world draws the spliced frames at full size, one cell per frame;
       the shrunk single-cell art stays for icons. */
    if (ok && (tile_object_w(t) > 1 || tile_object_h(t) > 1)) {
        ui->obj[t] = mk_tex(ui->ren, obj.px, obj.w, obj.h);
        ok = ui->obj[t] != NULL;
    }
#endif
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

static bool load_item_tile(PxUi *ui,Tile tile,const char *dir,int id) {
    Sheet s; char name[32]; snprintf(name,sizeof name,"Item_%d",id);
    if(!sheet_load(ui,&s,dir,name)) return false;
    int crop[1][4]={{0,0,s.w,s.h}};
    bool ok=load_fitted(ui,tile,&s,crop,1,true); sheet_free(&s); return ok;
}

/* Original Item_N sheets, with IDs shared with the simulator's item table;
   nearest-sampled into 16x16 inventory cells, never substitute artwork. */
static bool load_items(PxUi *ui, const char *dir)
{
    static uint32_t buf[16 * 16];
    char name[32];
    Sheet s;
    int i;

    for (i = 0; i < ITEM_COUNT; i++) {
        int dw, dh, k;
        snprintf(name, sizeof name, "Item_%d", ITEM_TERRARIA_ID[i]);
        if (!sheet_load(ui, &s, dir, name)) return false;

        for (k = 0; k < 16 * 16; k++) buf[k] = 0u;
        dw = s.w >= s.h ? 16 : s.w * 16 / s.h;
        dh = s.h >= s.w ? 16 : s.h * 16 / s.w;
        blit_box(&s, 0, 0, s.w, s.h, buf, 16, (16 - dw) / 2, (16 - dh) / 2, dw, dh);
        sheet_free(&s);

        ui->item[i] = mk_tex(ui->ren, buf, 16, 16);
        if(!ui->item[i]) return false;
        ui->item_owned[i] = true;
        ui->real_items++;
    }
    return true;
}

static bool load_picks(PxUi *ui,const char *dir) {
    static const int ids[4]={3509,1,3521,3506};
    for(int i=0;i<4;i++) {
        Sheet s; char name[32]; uint32_t buf[16*16]={0};
        snprintf(name,sizeof name,"Item_%d",ids[i]);
        if(!sheet_load(ui,&s,dir,name)) return false;
        int dw=s.w>=s.h?16:s.w*16/s.h,dh=s.h>=s.w?16:s.h*16/s.w;
        blit_box(&s,0,0,s.w,s.h,buf,16,(16-dw)/2,(16-dh)/2,dw,dh);
        sheet_free(&s); SDL_Texture *texture=mk_tex(ui->ren,buf,16,16);
        if(i<3) ui->pick[i]=texture; else ui->axe=texture;
        if(!texture) return false;
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
#define PL_CW      40            /* original frame pixels, no downscaling */
#define PL_CH      56
#define PL_FRAMES  20
#define PL_JUMP     5
#define PL_WALK0    6
#define PL_WALKN   14

/* Original 40x56 source frames centered on the coarse 32x48 collision box.
   Terraria's 20x42 pixel hitbox rounds up to this 2x3 grid envelope; source
   art is no longer shrunk to the old 1x2 body. */
#define PL_OX      (-4)           /* centered on the 32px grid body */
#define PL_OY      (-8)           /* align feet with the 48px body bottom */

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
    Sheet sh[PL_LAYERS],armor[PX_ARMORS-1];
    bool ok = true;
    int i, f, x, y;

    /* Every layer is attempted even once one has failed, so that the single
       teardown below covers the whole array; sheet_fail keeps the first name. */
    for (i = 0; i < PL_LAYERS; i++)
        if (!sheet_load(ui, &sh[i], dir, PLAYER_LAYER[i].name)) ok = false;
    for(i=0;i<PX_ARMORS-1;i++)
        if(!sheet_load(ui,&armor[i],dir,ARMOR_SHEET[i])) ok=false;

    if (ok) {
        for(int equipped=0;equipped<PX_ARMORS;equipped++) {
        memset(atlas, 0, sizeof atlas);
        for (f = 0; f < PL_FRAMES; f++) {
            player_compose(frm, sh, f);
            if(equipped) for(int col=0;col<=7;col+=7)
                for(int y=0;y<PL_FH;y++) for(int x=0;x<PL_FW;x++) {
                    uint32_t src=sheet_at(&armor[equipped-1],col*PL_FW+x,y);
                    frm[y*PL_FW+x]=blend_over(frm[y*PL_FW+x],src);
                }
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
        ui->player[equipped] = mk_tex(ui->ren, atlas[0], PL_FRAMES * PL_CW, 2 * PL_CH);
        if(!ui->player[equipped]) ok=false;
        }
    }

    for (i = 0; i < PL_LAYERS; i++) sheet_free(&sh[i]);
    for(i=0;i<PX_ARMORS-1;i++) sheet_free(&armor[i]);
    return ok;
}

/* Original Tiles_4 frames: upright, attached left, attached right. The side
   crops keep the stems flush with their supporting cell; the upright crop
   stays unchanged for floor and background-wall attachments. */
static const int TORCH_SRC[3][4] = {{3, 2, 16, 16}, {22, 0, 16, 16}, {48, 0, 16, 16}};
/* Forest bark in Tiles_5, three original 20px trunk frames (22px pitch). */
static const int TRUNK_SRC[3][4]  = {{0,0,20,20},{0,22,20,20},{0,44,20,20}};

static const int LEAF_SRC[4][4]   = {{14, 22, 16, 16}, {30, 22, 16, 16},
                                     {46, 22, 16, 16}, {30, 38, 16, 16}};

/* Short-circuits at the first missing original sheet: no substitute fallback. */
static bool load_terraria(PxUi *ui, const char *dir)
{
    return load_grid(ui, TILE_DIRT,       dir, "Tiles_0",  100) &&
           load_grid(ui, TILE_STONE,      dir, "Tiles_1",  100) &&
           load_grid(ui, TILE_GRASS,      dir, "Tiles_2",  100) &&
           load_crops(ui,TILE_LOG,dir,"Tiles_5",TRUNK_SRC,3,false) &&
           load_grid(ui, TILE_WOOD,       dir, "Tiles_30", 100) &&
           load_grid(ui, TILE_COPPER_ORE, dir, "Tiles_7",  100) &&
           load_grid(ui, TILE_IRON_ORE,   dir, "Tiles_6",  100) &&
           load_grid(ui, TILE_GOLD_ORE,   dir, "Tiles_8",  100) &&
           load_grid(ui, TILE_SILVER_ORE, dir, "Tiles_9", 100) &&
           /* Ebonstone at 45% is near-black with a purple cast: unmistakably a
              wall you are never getting through, which is bedrock's job. */
           load_grid(ui, TILE_BEDROCK,    dir, "Tiles_25", 100) &&

           load_crops (ui, TILE_LEAVES,    dir, "Tree_Tops_0", LEAF_SRC,  4, false) &&
           load_crops (ui, TILE_TORCH,     dir, "Tiles_4",     TORCH_SRC, 3, false) &&
           load_object(ui,TILE_CAMPFIRE,dir,"Tiles_215",0,0,3,2) &&
           load_object(ui,TILE_PLATFORM,dir,"Tiles_19",0,0,1,1) &&
           load_object(ui,TILE_ROPE,dir,"Tiles_213",0,0,1,1) &&
           load_object(ui,TILE_CHEST,dir,"Tiles_21",0,0,2,2) &&
           load_object(ui,TILE_CHEST_OPEN,dir,"Tiles_21",0,76,2,2) &&
           load_object(ui,TILE_LIFE_CRYSTAL,dir,"Tiles_12",0,0,2,2) &&
           load_item_tile(ui,TILE_MUSHROOM,dir,5) &&
           load_object(ui, TILE_ANVIL,     dir, "Tiles_16", 0, 0, 2, 1) &&
           load_object(ui, TILE_WORKBENCH, dir, "Tiles_18", 0, 0, 2, 1) &&
           load_object(ui, TILE_FURNACE,   dir, "Tiles_17", 0, 0, 3, 2) &&
#if PX_V10
           /* Demon Altar: Tiles_26 style 0 (the Crimson altar is style 1). */
           load_object(ui, TILE_DEMON_ALTAR, dir, "Tiles_26", 0, 0, 3, 2) &&
#endif

           load_items(ui, dir) &&
           load_picks(ui,dir) &&
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
    SDL_Rect usable;
    int win_w = PX_WIN_W * scale, win_h = PX_WIN_H * scale;
    Uint32 win_flags = SDL_WINDOW_ALLOW_HIGHDPI;
#if PX_V10
    /* The v10 window is taller (30-row view) and would drop to zoom 1 on a
       laptop display. Fit the largest window, fractional zoom allowed, and
       let the user resize it; the logical size keeps the layout fixed. */
    if(SDL_GetDisplayUsableBounds(0,&usable)==0 &&
       (win_w>usable.w || win_h+32>usable.h)) {
        float f=fminf((float)usable.w/PX_WIN_W,(float)(usable.h-32)/PX_WIN_H);
        if(f<1.0f) f=1.0f;
        win_w=(int)(PX_WIN_W*f); win_h=(int)(PX_WIN_H*f);
    }
    win_flags|=SDL_WINDOW_RESIZABLE;
#else
    if(SDL_GetDisplayUsableBounds(0,&usable)==0) {
        while(scale>1 && (PX_WIN_W*scale>usable.w || PX_WIN_H*scale+32>usable.h)) scale--;
    }
    win_w = PX_WIN_W * scale; win_h = PX_WIN_H * scale;
#endif
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "0");   /* crisp pixels by default */

    ui.win = SDL_CreateWindow(PX_TITLE,
                              SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                              win_w, win_h, win_flags);
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
#if PX_V10
    SDL_RaiseWindow(ui.win);   /* launched from a shell, it would open behind it */
#endif

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

    /* Original NPC strips; Blue Slime's color passes are applied when drawn. */
    for(int k=0;k<PX_MOBS;k++) {
        Sheet s;
        if(!sheet_load(&ui,&s,dir,MOB_SHEET[k])) { complain(dir,MOB_SHEET[k]); px_shutdown(&ui); return NULL; }
        ui.mob[k]=mk_tex(ui.ren,s.px,s.w,s.h); sheet_free(&s);
        if(!ui.mob[k]) { px_shutdown(&ui); return NULL; }
    }
#if PX_V10
    {
        Sheet s;
        if(!sheet_load(&ui,&s,dir,"NPC_4")) { complain(dir,"NPC_4"); px_shutdown(&ui); return NULL; }
        ui.boss=mk_tex(ui.ren,s.px,s.w,s.h); sheet_free(&s);
        if(!ui.boss) { px_shutdown(&ui); return NULL; }
    }
    {   /* Use-animation sprites and the tree art, all original sheets. */
        static const int tool_id[4] = {3509, 1, 3521, 3506};
        char name[32];
        Sheet s;
        for (int k = 0; k < WEAPON_COUNT + 4; k++) {
            snprintf(name, sizeof name, "Item_%d", k < WEAPON_COUNT ? ITEM_TERRARIA_ID[WEAPON_ITEM[k]] : tool_id[k - WEAPON_COUNT]);
            if (!sheet_load(&ui, &s, dir, name)) { complain(dir, name); px_shutdown(&ui); return NULL; }
            ui.held[k] = mk_tex(ui.ren, s.px, s.w, s.h); ui.held_w[k] = s.w; ui.held_h[k] = s.h; sheet_free(&s);
            if (!ui.held[k]) { px_shutdown(&ui); return NULL; }
        }
        if (!sheet_load(&ui, &s, dir, "Tree_Tops_0")) { complain(dir, "Tree_Tops_0"); px_shutdown(&ui); return NULL; }
        ui.tree_top = mk_tex(ui.ren, s.px, s.w, s.h); sheet_free(&s);
        if (!sheet_load(&ui, &s, dir, "Tree_Branches_0")) { complain(dir, "Tree_Branches_0"); px_shutdown(&ui); return NULL; }
        ui.tree_branch = mk_tex(ui.ren, s.px, s.w, s.h); sheet_free(&s);
        if (!ui.tree_top || !ui.tree_branch) { px_shutdown(&ui); return NULL; }
    }
#if BG_WALLS
    {   /* Background walls: the original Wall_N sheets (13 x 5 frames of 36
           px); draw_world samples the 16 px cores of the interior frames. */
        char name[32];
        Sheet s;
        for (int w = WALL_NONE + 1; w < WALL_COUNT; w++) {
            snprintf(name, sizeof name, "Wall_%d", WALL_TERRARIA_ID[w]);
            if (!sheet_load(&ui, &s, dir, name)) { complain(dir, name); px_shutdown(&ui); return NULL; }
            ui.wall_sheet[w] = mk_tex(ui.ren, s.px, s.w, s.h); sheet_free(&s);
            if (!ui.wall_sheet[w]) { px_shutdown(&ui); return NULL; }
        }
    }
#endif
#endif

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
    for(i=0;i<PX_ARMORS;i++) if(ui->player[i]) SDL_DestroyTexture(ui->player[i]);
    for(i=0;i<PX_MOBS;i++) if(ui->mob[i]) SDL_DestroyTexture(ui->mob[i]);
#if PX_V10
    for(i=0;i<TILE_COUNT;i++) if(ui->obj[i]) SDL_DestroyTexture(ui->obj[i]);
    if(ui->boss) SDL_DestroyTexture(ui->boss);
    for(i=0;i<WEAPON_COUNT+4;i++) if(ui->held[i]) SDL_DestroyTexture(ui->held[i]);
    if(ui->tree_top) SDL_DestroyTexture(ui->tree_top);
    if(ui->tree_branch) SDL_DestroyTexture(ui->tree_branch);
#if BG_WALLS
    for(i=0;i<WALL_COUNT;i++) if(ui->wall_sheet[i]) SDL_DestroyTexture(ui->wall_sheet[i]);
#endif
#endif
    for(i=0;i<3;i++) if(ui->pick[i]) SDL_DestroyTexture(ui->pick[i]);
    if(ui->axe) SDL_DestroyTexture(ui->axe);
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

#if PX_V10
/* One achievement row per tier (13/12/8/7 cells, weights 1/3/5/8); the tiers
   are contiguous in ACH_TIER. Colours: green, blue, purple, gold. */
static const uint32_t TIER_COL[TIER_COUNT + 1] = {
    0, 0xFF74CF5Cu, 0xFF5CA8E8u, 0xFFB57CE8u, 0xFFE8A94Eu
};
static int tier_first(int t)
{
    int i = 0;
    while (i < ACH_COUNT && ACH_TIER[i] < t) i++;
    return i;
}
#endif

static void ach_cell(int i, int *x, int *y)
{
#if PX_V10
    *x = ACH_X0 + (i - tier_first(ACH_TIER[i])) * ACH_PITCH;
    *y = ACH_Y0 + (ACH_TIER[i] - 1) * ACH_PITCH;
#else
    *x = ACH_X0 + (i % ACH_COLS) * ACH_PITCH;
    *y = ACH_Y0 + (i / ACH_COLS) * ACH_PITCH;
#endif
}

int px_ach_at(int ax, int ay)
{
    int gx = ax - ACH_X0, gy = ay - ACH_Y0, c, r;
    if (gx < 0 || gy < 0) return -1;
    c = gx / ACH_PITCH;
    r = gy / ACH_PITCH;
    if (gx % ACH_PITCH >= ACH_CELL || gy % ACH_PITCH >= ACH_CELL) return -1;
#if PX_V10
    if (r >= TIER_COUNT) return -1;
    c += tier_first(r + 1);
    return c < ACH_COUNT && ACH_TIER[c] == r + 1 ? c : -1;
#else
    if (c >= ACH_COLS || r * ACH_COLS + c >= ACH_COUNT) return -1;
    return r * ACH_COLS + c;
#endif
}

#if PX_V10
/* Mirrors MOB_W / MOB_H in variants/v10/src/mobs.c (the real NPC sizes). */
static const int MOB_BOX_W[MOB_KINDS] = {0, 24, 22, 18, 30, 18};
static const int MOB_BOX_H[MOB_KINDS] = {0, 18, 18, 40, 32, 40};

void px_mob_box(const Mob *m, float *x, float *y, int *w, int *h)
{
    *w = MOB_BOX_W[m->kind];
    *h = MOB_BOX_H[m->kind];
#if FID_MOBS
    *x = (float)m->fx / FIX_ONE;
    *y = (float)m->fy / FIX_ONE;
#else
    *x = (float)(m->x * PX_TILE + (PX_TILE - *w) / 2);
    *y = (float)((m->y + 1) * PX_TILE - *h);
#endif
}
#endif

/* The inventory strip is one slot per *item*, but selection cycles over
   PLACEABLES, so a hit has to be translated back. Items with nothing to place
   -- ores, bars, the pickaxes -- are not on that cycle and report -1. */
int px_item_at(int ax,int ay)
{
    int gx=ax-INV_X0,gy=ay-INV_Y0,i;

    if(gx<0 || gy<0 || gy>=2*INV_PITCH || gy%INV_PITCH>=INV_SLOT || gx/INV_PITCH>=INV_COLS) return -1;
    i = gx/INV_PITCH + (gy/INV_PITCH)*INV_COLS;
    if (i >= ITEM_COUNT || gx % INV_PITCH >= INV_SLOT) return -1;
    return i;
}

int px_hotbar_at(int ax, int ay) {
    int i=px_item_at(ax,ay);
    if(i<0) return -1;
    for (int p = 0; p < PLACEABLE_COUNT; p++)
        if (PLACEABLES[p].item == (Item)i) return p;
    return -1;
}

/* ---- Crafting availability ---------------------------------------------- */

bool px_recipe_ready(const Env *e, int r)
{
    uint8_t mask[ACT_COUNT]; env_action_mask(e,mask);
    return r>=0 && r<RECIPE_COUNT && mask[RECIPE_FIRST_ACTION+r];
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

static uint32_t sky_col(const Env *e, int y)
{
    int t = y * 256 / (SURFACE_MAX + 8);
    if (t > 256) t = 256;
#if PX_V10
    /* The engine's sky light drops to NIGHT_SKY_LIGHT at once at dusk, so the
       backdrop switches with it rather than fading on its own clock. */
    if (is_night(e)) return mix(0xFF1A2860u, 0xFF4A64B0u, t); /* before the light pass dims it */
#else
    (void)e;
#endif
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

/* WorldGen.CheckTorch priority: floor, left, right, then background wall.
   Read current supports so mining an anchor also updates the visible mount. */
static int torch_frame(const Env *e, int x, int y)
{
    if (tile_solid(tile_at(e, x, y + 1))) return 0;
    if (tile_solid(tile_at(e, x - 1, y))) return 1;
    return tile_solid(tile_at(e, x + 1, y)) ? 2 : 0;
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
                fill(ui, sx, sy, PX_TILE, PX_TILE, sky_col(e, ty));
#if PX_V10
                if (is_night(e) && t == TILE_AIR && hash2(tx, ty, 0x57A2u) % 9u == 0u) {
                    uint32_t h = hash2(tx, ty, 0xB71Eu);
                    fill(ui, sx + (int)(h % 15u), sy + (int)(h / 15u % 15u), 1, 1, 0xFFFFFFFFu);
                }
#endif
            } else {
                /* Rows [surface + 1, surface + DIRT_DEPTH] are the dirt worldgen
                   lays down; stone starts below them. */
                SDL_Texture *wall = ty <= e->surface[tx] + DIRT_DEPTH ? ui->bg_dirt
                                                                      : ui->bg_stone;
                SDL_Rect base = {0, 0, PX_TILE, PX_TILE};
                bool far_bg = false;
#if PX_V10 && BG_WALLS
                /* A real background wall: the 16 px core of one of Wall_N's
                   six interior frames (columns 6-8, rows 1-2), varied per
                   cell. Cells without one show the old rock backdrop pushed
                   back (darkened), standing in for Terraria's distant
                   underground background. */
                if (e->wall[ty][tx] != WALL_NONE) {
                    uint32_t h = hash2(tx, ty, 0x3A11u);
                    wall = ui->wall_sheet[e->wall[ty][tx]];
                    base = (SDL_Rect){36 * (6 + (int)(h % 3u)) + 8, 36 * (1 + (int)(h / 3u % 2u)) + 8, PX_TILE, PX_TILE};
                } else far_bg = true;
#endif
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
                    SDL_Rect wsrc = {base.x + l, base.y + u, PX_TILE - l - r, PX_TILE - u};
                    SDL_Rect wdst = {sx + l, sy + u, wsrc.w, wsrc.h};

                    fill(ui, sx, sy, PX_TILE, PX_TILE, sky_col(e, ty));
                    SDL_RenderCopy(ui->ren, wall, &wsrc, &wdst);
                } else {
                    SDL_RenderCopy(ui->ren, wall, &base, &dst);
                }
                if (far_bg) fill(ui, sx + l, sy + u, PX_TILE - l - r, PX_TILE - u, 0x80000000u);
            }

            if (t == TILE_AIR) continue;

            a = &ui->art[t];
#if PX_V10
            /* A multi-cell object: this cell's frame of the full-size art. */
            if (ui->obj[t]) {
                int w = tile_object_w(t), part = e->object_part[ty][tx];
                SDL_Rect osrc = {part % w * PX_TILE, part / w * PX_TILE, PX_TILE, PX_TILE};
                SDL_RenderCopy(ui->ren, ui->obj[t], &osrc, &dst);
                continue;
            }
#endif
            int variant = t == TILE_TORCH ? torch_frame(e, tx, ty)
                : (int)(hash2(tx, ty, 0x5EEDu) % (uint32_t)a->nvar);
            src.x = variant * PX_TILE;
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

#if PX_V10 && FID_MINING
/* Accumulated pick damage (Terraria's HitTile cracks), darker with damage. */
static void draw_dig(PxUi *ui, const Env *e, const PxView *v)
{
    int camx = cam_px(v->cam_x), camy = cam_px(v->cam_y);
    for (int i = 0; i < HIT_SLOTS; i++) {
        const HitSlot *h = &e->hits[i];
        int d = h->damage > 100 ? 100 : h->damage;
        if (d <= 0 || !in_bounds(h->x, h->y) || tile_at(e, h->x, h->y) == TILE_AIR) continue;
        int sx = h->x * PX_TILE - camx, sy = h->y * PX_TILE - camy;
        fill(ui, sx, sy, PX_TILE, PX_TILE, (uint32_t)(d * 150 / 100) << 24);
        for (int k = 0; k < d / 20 + 1; k++) {
            uint32_t r = hash2(h->x * 7 + k, h->y, 0xC4ACu);
            fill(ui, sx + 2 + (int)(r % 12u), sy + 2 + (int)(r / 12u % 12u), 2, 1, 0xE0000000u);
        }
    }
}
#endif

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
 * 2x3 grid body box by a few pixels of hair and shoulder, which is decoration only:
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

    SDL_Texture *t = ui->player[e->armor];
#if PX_V10
    /* Player.immuneAlpha: the body blinks through the i-frames that follow
       a hit, and a fresh hit tints it red for a moment. */
    bool flash = v->clock >= v->player_hit_t && v->clock < v->player_hit_t + PX_FLASH;
    if (v->clock >= v->player_hit_t && v->clock < v->immune_end && (int)(v->clock * 20.0) % 2) alpha = alpha * 70 / 255;
    SDL_SetTextureColorMod(t, 255, flash ? 90 : 255, flash ? 90 : 255);
#endif
    SDL_SetTextureAlphaMod(t, (Uint8)alpha);
    SDL_RenderCopy(ui->ren, t, &src, &dst);
#if PX_V10
    SDL_SetTextureColorMod(t, 255, 255, 255);
#endif
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
    "bare hands", "copper pickaxe", "iron pickaxe", "gold pickaxe"
};

static void draw_hud(PxUi *ui, const Env *e, const PxView *v)
{
    char buf[96];
    int i, hearts;

    fill(ui, 0, HY, PX_VIEW_W, PX_HUD_H, UI_BG);
    fill(ui, 0, HY, PX_VIEW_W, 1, UI_LINE);

    hearts=(e->max_health+19)/20;
    for(i=0;i<hearts&&i<20;i++) draw_heart(ui,6+(i%10)*9,HY+1+(i/10)*8,e->health>i*20);

#if PX_V10 && EXPLICIT_TOOLS
    /* The item in hand (Player.HeldItem): auto-selected tool, weapon or block. */
    icon(ui, ui->item[e->held], 104, HY + 2, 16, 255);
    text(ui, 123, HY + 5, UI_ACCENT, ITEM_NAME[e->held]);
#else
#if PX_V10 && FID_MINING
    bool chopping=e->mining_tree && e->tool_time>0;
#else
    bool chopping=e->mining_tree && e->mine_cd;
#endif
    icon(ui,chopping?ui->axe:ui->pick[PX_PICK(e)-1],104,HY+2,16,255);
    text(ui, 123, HY + 5, UI_ACCENT,
         chopping?"Copper Axe":TIER_NAME[PX_PICK(e) < 4 ? PX_PICK(e) : 3]);
#endif

#if PX_V10
    {   /* Terraria's clock: day 4:30 AM - 7:30 PM, night until 4:30 AM. */
        static const char *const LAYER[3] = {"surface", "underground", "caverns"};
        int t = day_time(e), night = is_night(e), min;
        min = night ? 19 * 60 + 30 + (t - DAY_STEPS) * 9 * 60 / NIGHT_STEPS
                    : 4 * 60 + 30 + t * 15 * 60 / DAY_STEPS;
        min %= 24 * 60;
        snprintf(buf, sizeof buf, "%s  y%d", LAYER[player_layer(e)], e->py);
        text_right(ui, PX_VIEW_W - 6, HY + 5, UI_DIM, buf);
        {
            char tb[48];
            snprintf(tb, sizeof tb, "%s %d  %d:%02d %s", night ? "NIGHT" : "Day",
                     e->steps / DAY_CYCLE + 1, (min / 60 + 11) % 12 + 1, min % 60,
                     min < 12 * 60 ? "AM" : "PM");
            text_right(ui, PX_VIEW_W - 6 - text_w(buf) - 10, HY + 5,
                       night ? 0xFFA898FFu : 0xFFF2D35Bu, tb);
        }
    }
    textf(ui,6,HY+17,UI_TEXT,"hp %d/%d  %s  def %d  heal cd %d",
          e->health,e->max_health,ITEM_NAME[WEAPON_ITEM[e->weapon]],
          ARMOR_DEFENSE[e->armor],e->heal_cd);
    snprintf(buf, sizeof buf, "step %d/%d", e->steps, e->max_steps);
    text_right(ui, PX_VIEW_W - 6, HY + 17, UI_DIM, buf);
#else
    snprintf(buf, sizeof buf, "depth %d   step %d/%d   return %+.1f",
             e->py, e->steps, e->max_steps, (double)e->ep_return);
    text_right(ui, PX_VIEW_W - 6, HY + 5, UI_DIM, buf);

    textf(ui,6,HY+17,UI_TEXT,"hp %d/%d  %s  def %d  attack %d  heal %d",
          e->health,e->max_health,ITEM_NAME[WEAPON_ITEM[e->weapon]],
          ARMOR_DEFENSE[e->armor],e->attack_cd,e->heal_cd);
#endif
    text(ui,6,HY+98,e->msg[0]?UI_TEXT:UI_FAINT,e->msg[0]?e->msg:"-");

    /* Inventory: all 14 slots always, so the ladder you are climbing is
       visible as a row of things you do not have yet. Only the placeable ones
       are clickable, so only those light up under the cursor. */
    for (i = 0; i < ITEM_COUNT; i++) {
        int x=INV_X0+(i%INV_COLS)*INV_PITCH;
        int iy=INV_Y0+(i/INV_COLS)*INV_PITCH;
        int have = e->inv[i];
        bool hot = v->hover_slot >= 0 && PLACEABLES[v->hover_slot].item == (Item)i;
        fill(ui, x, iy, INV_SLOT, INV_SLOT, hot ? UI_BG3 : (have ? UI_BG2 : UI_BG));
        frame(ui, x, iy, INV_SLOT, INV_SLOT,
              hot ? (have ? UI_ACCENT : UI_FAINT) : (have ? UI_LINE : 0xFF262330u));
        icon(ui, ui->item[i], x + 2, iy + 2, PX_TILE, have ? 255 : 44);
        if (have) {
            snprintf(buf, sizeof buf, "%d", have);
            fill(ui, x + INV_SLOT - text_w(buf) - 2, iy + INV_SLOT - 8,
                 text_w(buf) + 2, 8, 0xC0000000u);
            text_right(ui, x + INV_SLOT - 1, iy + INV_SLOT - 8, UI_TEXT, buf);
        }
    }

    {   /* Selected placeable, called out because E is easy to forget. */
        int x=INV_X0+(ITEM_COUNT-INV_COLS)*INV_PITCH+8;
        int iy=INV_Y0+INV_PITCH;
        Item it = PLACEABLES[e->selected].item;
        int have = e->inv[it];
        fill(ui, x, iy, INV_SLOT, INV_SLOT, UI_BG3);
        frame(ui, x, iy, INV_SLOT, INV_SLOT, UI_ACCENT);
        tile_icon(ui, PLACEABLES[e->selected].tile, x + 2, iy + 2, PX_TILE, have ? 255 : 60);
        text(ui, x + 25, iy + 2, have ? UI_TEXT : UI_FAINT, ITEM_NAME[it]);
        textf(ui, x + 25, iy + 12, have ? UI_ACCENT : UI_BAD, "x%d  [e]", have);
    }

    /* What a click would do right now, spelled out. The hotbar wins the line
       when the cursor is on it: the reach target is unreachable from there by
       construction, so there is nothing else this row could be reporting. */
    if(v->hover_item>=0 && v->hover_slot<0) {
        Item it=(Item)v->hover_item;
        const char *hint="crafting material";
#if PX_V10
        if(it==ITEM_LESSER_POTION) hint="[c]/click heal 50; shared cooldown 60";
        else if(it==ITEM_MUSHROOM) hint="[v]/click heal 15; shared cooldown 60";
        else if(it==ITEM_LIFE_CRYSTAL) hint="[b]/click +20 max life, up to " PX_STR(HEALTH_CAP);
        else if(it==ITEM_SUSPICIOUS_EYE) hint="[enter]/click summon the Eye (night)";
        else if(it==ITEM_LENS) hint=PX_STR(EYE_LENSES) " at a Demon Altar: [`] Suspicious Eye";
        else if(it==ITEM_DEMONITE_ORE) hint="dropped by the Eye of Cthulhu";
#if EXPLICIT_TOOLS
        else if(it==ITEM_COPPER_PICK || it==ITEM_IRON_PICK || it==ITEM_GOLD_PICK) hint="the best pickaxe is auto-selected for mining";
        else if(it==ITEM_COPPER_AXE) hint="auto-selected for tree trunks";
#else
        else if(it==ITEM_IRON_PICK || it==ITEM_GOLD_PICK) hint="crafting upgrades your pickaxe";
#endif
        else if(it==ITEM_WOOD_ARMOR || it==ITEM_IRON_ARMOR || it==ITEM_GOLD_ARMOR) hint="crafting equips torso armor";
#else
        if(it==ITEM_LESSER_POTION) hint="[c] heal 50; shared cooldown 60";
        else if(it==ITEM_MUSHROOM) hint="[v] heal 15; shared cooldown 60";
        else if(it==ITEM_LIFE_CRYSTAL) hint="[b] +20 max life, up to 200";
        else if(it==ITEM_WOOD_ARMOR || it==ITEM_IRON_ARMOR) hint="crafting equips torso armor";
#endif
        else if(it==ITEM_CLOUD_BOTTLE) hint="[w] one extra airborne jump";
        else for(int k=0;k<WEAPON_COUNT;k++) if(it==WEAPON_ITEM[k]) hint="[t] cycle owned weapons";
        textf(ui,6,HY+76,UI_TEXT,"%s x%d: %s",ITEM_NAME[it],e->inv[it],hint);
    } else if (v->hover_slot >= 0) {
        Item it = PLACEABLES[v->hover_slot].item;
        int have = e->inv[it];
        snprintf(buf, sizeof buf, "hotbar  %s  x%d  -  %s", ITEM_NAME[it], have,
                 have ? (v->hover_slot == e->selected ? "already selected"
                                                      : "lmb selects it")
                      : "empty stack, cannot be selected");
        text(ui, 6, HY + 76, have ? UI_GOOD : UI_BAD, buf);
    } else if (v->hover_reach >= 0) {
        Tile t = tile_at(e, v->hover_x, v->hover_y);
        if(e->light[v->hover_y][v->hover_x]<DARK_THRESHOLD)
            snprintf(buf,sizeof buf,"target %s: unlit, try mining or add light",REACH_NAME[v->hover_reach]);
        else if(t==TILE_CHEST)
            snprintf(buf,sizeof buf,"chest: [z] loot when adjacent and visible");
        else if (t != TILE_AIR)
            snprintf(buf, sizeof buf, "target  %s  %s  -  %s", REACH_NAME[v->hover_reach],
                     TILE_INFO[t].name,
                     v->can_mine ? "lmb mines it"
                                 : (tile_tier(t) == TIER_NEVER ? "unbreakable"
                                                               : "pickaxe too weak"));
        else
            snprintf(buf, sizeof buf, "target  %s  empty  -  %s", REACH_NAME[v->hover_reach],
                     v->can_place ? "rmb places it" : "nothing to place");
        text(ui, 6, HY + 76, (v->can_mine || v->can_place) ? UI_GOOD : UI_BAD, buf);
    } else {
        text(ui, 6, HY + 76, UI_FAINT, "target  -  point into the world to aim");
    }

    text(ui, 6, HY + 87, UI_FAINT,
#if PX_V10
         "f attack  z loot  c/v heal  b life  j/l rope  ; drop  t weapon  F1 help");
#else
         "f attack  z loot  c/v heal  b life  j/l rope  ; drop  t weapon  F2 pause");
#endif
}

/* ---- Sidebar ------------------------------------------------------------ */

#define RECIPE_KEY KB_CRAFT

static void recipe_inputs(const Recipe *rc, char *out, size_t n)
{
    size_t used=0;
    for(int i=0;i<rc->n_in;i++) {
        int k=snprintf(out+used,n-used,"%s%d %s",i?" + ":"",rc->in_qty[i],ITEM_NAME[rc->in_item[i]]);
        if(k<0 || (size_t)k>=n-used) break;
        used+=(size_t)k;
    }
}

static void draw_reach_key_grid(PxUi *ui, const PxView *v, int gx, int gy)
{
    const char *KEYCH=KB_MINE;
    int col, row;

    for (row = 0; row < PLAYER_H+2; row++)
        for (col = 0; col < PLAYER_W+2; col++) {
            int x = gx + col * 16, y = gy + row * 14;
            int dx = col - 1, dy = row - PLAYER_H;
            int k;
            for (k = 0; k < REACH_COUNT; k++)
                if (REACH_DX[k] == dx && REACH_DY[k] == dy) break;
            bool body=dx>=0&&dx<PLAYER_W&&dy<=0&&dy>-PLAYER_H;
            fill(ui, x, y, 13, 12, v->hover_reach == k ? UI_ACCENT : body?UI_BG3:UI_BG2);
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
#if PX_V10
    {
        int score = 0, max = 0;
        for (i = 0; i < ACH_COUNT; i++) {
            max += TIER_WEIGHT[ACH_TIER[i]];
            if (has_ach(e, i)) score += TIER_WEIGHT[ACH_TIER[i]];
        }
        textf(ui, SX + 6, ACH_Y0 - 12, UI_ACCENT, "ACHIEVEMENTS %d/%d", done, ACH_COUNT);
        snprintf(buf, sizeof buf, "score %d/%d %.1f%%", score, max, 100.0 * score / max);
        text_right(ui, PX_WIN_W - 6, ACH_Y0 - 12, UI_GOOD, buf);
    }
    for (int t = 1; t <= TIER_COUNT; t++) {
        snprintf(buf, sizeof buf, "x%d", TIER_WEIGHT[t]);
        text_right(ui, PX_WIN_W - 6, ACH_Y0 + (t - 1) * ACH_PITCH + 3, TIER_COL[t], buf);
    }
#else
    textf(ui, SX + 6, ACH_Y0 - 12, UI_ACCENT, "ACHIEVEMENTS %d/%d", done, ACH_COUNT);
#endif

    for (i = 0; i < ACH_COUNT; i++) {
        int x, y;
        bool got = has_ach(e, i);
        uint32_t col = UI_GOOD;
        ach_cell(i, &x, &y);
#if PX_V10
        col = TIER_COL[ACH_TIER[i]];
#endif
        fill(ui, x, y, ACH_CELL, ACH_CELL, got ? col : UI_BG2);
        frame(ui, x, y, ACH_CELL, ACH_CELL, got ? mix(col, 0xFFFFFFFFu, 80)
                                                : (PX_V10 ? dim_col(col, 45, 100) : UI_LINE));
        if (got) fill(ui, x + 3, y + 3, ACH_CELL - 6, ACH_CELL - 6,
                      mix(col, 0xFFFFFFFFu, 120));
        if (v->hover_ach == i) frame(ui, x - 1, y - 1, ACH_CELL + 2, ACH_CELL + 2, UI_ACCENT);
    }

    /* Hovering names one; otherwise name the next one still locked, which is
       the closest thing this game has to a quest log. */
    if (v->hover_ach >= 0) {
#if PX_V10
        textf(ui, SX + 6, ACH_Y0 + 4 * ACH_PITCH + 2,
              has_ach(e, v->hover_ach) ? UI_GOOD : UI_DIM, "%s (T%d +%d)",
              ACH_NAME[v->hover_ach], ACH_TIER[v->hover_ach], TIER_WEIGHT[ACH_TIER[v->hover_ach]]);
#else
        text(ui, SX + 6, ACH_Y0 + 4 * ACH_PITCH + 2,
             has_ach(e, v->hover_ach) ? UI_GOOD : UI_DIM, ACH_NAME[v->hover_ach]);
#endif
    } else {
        for (i = 0; i < ACH_COUNT && has_ach(e, i); i++) { }
        if (i < ACH_COUNT)
            textf(ui, SX + 6, ACH_Y0 + 4 * ACH_PITCH + 2, UI_FAINT, "next: %s", ACH_NAME[i]);
    }

    text(ui,SX+6,PX_WIN_H-35,UI_DIM,"REACH: click / right-click");
    draw_reach_key_grid(ui,v,SX+174,PX_WIN_H-74);
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

    if (e->health > 30 || e->health <= 0) return;
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
#if PX_V10
    text(ui, x + 16, y + 30, UI_FAINT,
         e->terminated ? (e->msg[0] ? e->msg : "slain") : "the step budget ran out");
#else
    text(ui, x + 16, y + 30, UI_FAINT,
         e->terminated ? "the fall got you, or the dark did"
                       : "the step budget ran out");
#endif

    textf(ui, x + 16, y + 52,  UI_TEXT, "seed         %llu", (unsigned long long)e->seed);
    textf(ui, x + 16, y + 64,  UI_TEXT, "depth        %d", e->py);
    textf(ui, x + 16, y + 76,  UI_TEXT, "steps        %d / %d", e->steps, e->max_steps);
    textf(ui, x + 16, y + 88,  UI_TEXT, "return       %+.2f", (double)e->ep_return);
#if PX_V10
    {
        int score = 0, max = 0;
        for (i = 0; i < ACH_COUNT; i++) {
            max += TIER_WEIGHT[ACH_TIER[i]];
            if (has_ach(e, i)) score += TIER_WEIGHT[ACH_TIER[i]];
        }
        textf(ui, x + 16, y + 100, UI_TEXT, "achievements %d / %d   score %d / %d",
              done, ACH_COUNT, score, max);
    }
#else
    textf(ui, x + 16, y + 100, UI_TEXT, "achievements %d / %d", done, ACH_COUNT);
#endif

    text(ui, x + 16, y + h - 18, UI_ACCENT, "[r] new world      [q] quit");
}

/* ---- Frame -------------------------------------------------------------- */

#if PX_V10
/* Original strip frames by MobKind - 1: Blue Slime, Cave Bat, Zombie, Demon
   Eye, Skeleton. All face left; the Eye of Cthulhu's NPC_4 frames point down. */
static const int MOB_FW[PX_MOBS] = {32, 44, 38, 38, 40};
static const int MOB_FH[PX_MOBS] = {26, 32, 48, 24, 56};
#define EOC_FW 110
#define EOC_FH 166

static int mob_frame(const Mob *m, int i, const PxView *v)
{
#if FID_MOBS
    bool air = m->vy != 0, walk = m->vx > FIXC(0.1) || m->vx < -FIXC(0.1);
#else
    bool air = false, walk = true;
#endif
    double c = v->clock + i * 0.37;
    switch (m->kind) {
    case MOB_BLUE_SLIME: return air ? 1 : (int)(c * 4.0) % 2;
    case MOB_CAVE_BAT:   return (int)(c * 12.0) % 4;
    case MOB_ZOMBIE:     return air ? 1 : walk ? (int)(c * 8.0) % 3 : 0;
    case MOB_DEMON_EYE:  return (int)(c * 8.0) % 2;
    case MOB_SKELETON:   return air ? 1 : walk ? 2 + (int)(c * 14.0) % 13 : 0;
    default:             return 0;
    }
}

/* One pass over the regular mobs. `alpha` < 255 is the after-light pass that
   keeps a mob readable at night, as draw_player does for the player. */
static void draw_mobs_v10(PxUi *ui, const Env *e, const PxView *v, int alpha)
{
    int camx = cam_px(v->cam_x), camy = cam_px(v->cam_y);
    for (int i = 0; i < MAX_MOBS; i++) {
        const Mob *m = &e->mobs[i];
        if (!m->kind || !in_bounds(m->x, m->y) || e->light[m->y][m->x] < DARK_THRESHOLD) continue;
        int k = m->kind - 1, fw = MOB_FW[k], fh = MOB_FH[k], w, h, face = m->dir;
        float bx, by;
        px_mob_box(m, &bx, &by, &w, &h);
        bx = v->mob_x[i]; by = v->mob_y[i];
        double angle = 0.0;
        SDL_Rect src = {0, mob_frame(m, i, v) * fh, fw, fh};
        /* NPC draw: centred on the hitbox, frame bottom 4 px below its feet. */
        SDL_Rect dst = {(int)lroundf(bx) + w / 2 - fw / 2 - camx,
                        (int)lroundf(by) + h - fh + 4 - camy, fw, fh};
#if FID_MOBS
        if (m->kind == MOB_ZOMBIE || m->kind == MOB_SKELETON) face = m->sdir ? m->sdir : m->dir;
        if (m->kind == MOB_DEMON_EYE && (m->vx || m->vy)) {
            /* AI_002 rotation: the left-facing eye turned along its velocity. */
            angle = atan2((double)m->vy, (double)m->vx) * 180.0 / M_PI + 180.0;
            face = -1;
        }
#endif
        SDL_RendererFlip flip = face > 0 ? SDL_FLIP_HORIZONTAL : SDL_FLIP_NONE;
        SDL_Texture *t = ui->mob[k];
        if (k == 0) {
            /* NPC.SetDefaults(type=1): alpha 175, color (0,80,255,100); see v4. */
            SDL_SetTextureColorMod(t, 80, 80, 80);
            SDL_SetTextureAlphaMod(t, (Uint8)(80 * alpha / 255));
            SDL_RenderCopyEx(ui->ren, t, &src, &dst, angle, NULL, flip);
            SDL_SetTextureColorMod(t, 0, 80, 255);
            SDL_SetTextureAlphaMod(t, (Uint8)(100 * alpha / 255));
        } else {
            SDL_SetTextureColorMod(t, 255, 255, 255);
            SDL_SetTextureAlphaMod(t, (Uint8)alpha);
        }
        /* Hit flash: a brief red tint once the hit's game tick is shown. */
        if (v->clock >= v->mob_hit_t[i] && v->clock < v->mob_hit_t[i] + PX_FLASH) SDL_SetTextureColorMod(t, 255, 70, 70);
        SDL_RenderCopyEx(ui->ren, t, &src, &dst, angle, NULL, flip);
        SDL_SetTextureColorMod(t, 255, 255, 255);
        SDL_SetTextureAlphaMod(t, 255);
        if (alpha == 255) {
            int cx = (int)lroundf(bx) + w / 2 - camx, top = (int)lroundf(by) - camy - 6;
            fill(ui, cx - 8, top, 16, 2, UI_BG);
            fill(ui, cx - 8, top, 16 * m->hp / mob_max_hp(m->kind), 2, UI_BAD);
        }
    }
}

/* Eye of Cthulhu: drawn after the light pass (bosses are never lost in the
   dark), pupil towards the player while hovering, along the dash otherwise. */
static void draw_boss(PxUi *ui, const Env *e, const PxView *v)
{
    const Boss *b = &e->boss;
    if (!b->active) return;
    float cx = v->boss_x + EOC_SIZE * PX_TILE / 2.0f, cy = v->boss_y + EOC_SIZE * PX_TILE / 2.0f;
    float pcx = v->feet_x * PX_TILE + PLAYER_W * PX_TILE / 2.0f;
    float pcy = (v->feet_y + 1.0f) * PX_TILE - PLAYER_PX_H / 2.0f;
    double a = b->mode == BOSS_DASH && (b->vx || b->vy) ? atan2((double)b->vy, (double)b->vx)
                                                         : atan2((double)(pcy - cy), (double)(pcx - cx));
    bool p2 = 2 * b->hp <= EOC_HP;
    SDL_Rect src = {0, ((p2 ? 3 : 0) + (int)(v->clock * 8.0) % 3) * EOC_FH, EOC_FW, EOC_FH};
    SDL_Rect dst = {(int)lroundf(cx) - EOC_FW / 2 - cam_px(v->cam_x),
                    (int)lroundf(cy) - EOC_FH / 2 - cam_px(v->cam_y), EOC_FW, EOC_FH};
    bool flash = v->clock >= v->boss_hit_t && v->clock < v->boss_hit_t + PX_FLASH;
    SDL_SetTextureColorMod(ui->boss, 255, flash ? 90 : 255, flash ? 90 : 255);
    SDL_RenderCopyEx(ui->ren, ui->boss, &src, &dst, a * 180.0 / M_PI - 90.0, NULL, SDL_FLIP_NONE);
    SDL_SetTextureColorMod(ui->boss, 255, 255, 255);
}

static void draw_boss_bar(PxUi *ui, const Env *e)
{
    const Boss *b = &e->boss;
    if (!b->active) return;
    int w = 240, x = (PX_VIEW_W - w) / 2, y = PX_VIEW_H - 18, hp = b->hp < 0 ? 0 : b->hp;
    fill(ui, x - 2, y - 13, w + 4, 22, 0xC0000000u);
    textf(ui, x, y - 10, UI_TEXT, "Eye of Cthulhu  %d/%d%s", hp, EOC_HP,
          2 * hp <= EOC_HP ? "  (phase 2)" : "");
    fill(ui, x, y, w, 6, 0xFF3A1010u);
    fill(ui, x, y, w * hp / EOC_HP, 6, 0xFFD0303Au);
    frame(ui, x - 1, y - 1, w + 2, 8, UI_LINE);
}

/* Hitbox top-left of the interpolated player, screen px. */
static void player_box(const PxView *v, double *x, double *y)
{
    *x = v->feet_x * PX_TILE + PLAYER_W * PX_TILE / 2.0 - PLAYER_PX_W / 2.0 - cam_px(v->cam_x);
    *y = (v->feet_y + 1.0) * PX_TILE - PLAYER_PX_H - cam_px(v->cam_y);
}

/* ItemCheck_ApplyUseStyle, useStyle 1 (swing), at use progress p in [0, 1):
   itemRotation = (itemAnimation / itemAnimationMax - 0.5) * -dir * 3.5 -
   dir * 0.3, sprite drawn with its handle corner at itemLocation, which
   moves from behind the head (first third) to in front (second) and low
   (last). `k` indexes ui->held, at the sprite's original size. */
static void draw_swing(PxUi *ui, int k, int dir, double px, double py, double p)
{
    int w = ui->held_w[k], h = ui->held_h[k];
    double a = 1.0 - p, rot = (a - 0.5) * -dir * 3.5 - dir * 0.3, cx = px + PLAYER_PX_W / 2.0, lx, ly;
    if (a < 0.333)      { lx = cx + (w * 0.5 - (w > 32 ? 14 : 10)) * dir; ly = py + 24; }
    else if (a < 0.666) { lx = cx + (w * 0.5 - (w > 32 ? 18 : 10)) * dir; ly = py + (w > 32 ? 8 : 10); }
    else                { lx = cx - (w * 0.5 - (w > 32 ? 14 : 6)) * dir;  ly = py + (w > 32 ? 8 : 10); }
    SDL_Point pivot = {dir > 0 ? 0 : w, h};
    SDL_Rect dst = {(int)lround(lx) - pivot.x, (int)lround(ly) - pivot.y, w, h};
    SDL_SetTextureColorMod(ui->held[k], 255, 255, 255);
    SDL_SetTextureAlphaMod(ui->held[k], 255);
    SDL_RenderCopyEx(ui->ren, ui->held[k], NULL, &dst, rot * 180.0 / M_PI, &pivot,
                     dir > 0 ? SDL_FLIP_NONE : SDL_FLIP_HORIZONTAL);
}

/* The copper shortsword (useStyle 13): its stab projectile (AI_161_RapierStabs)
   thrusts the blade out from the body centre at 2.1 px per tick along its
   aim (ux, uy; the facing without AIM_ATTACK) for PX_STAB_TICKS, fading over
   the last quarter. The sprite's blade points up-right (up-left flipped). */
static void draw_stab(PxUi *ui, int dir, double ux, double uy, double px, double py, double p)
{
    int w = ui->held_w[0], h = ui->held_h[0];
    double reach = 2.1 * p * PX_STAB_TICKS - 4.0, deg = atan2(uy, ux) * 180.0 / M_PI;
    double hx = px + PLAYER_PX_W / 2.0 + ux * reach, hy = py + PLAYER_PX_H / 2.0 + uy * reach;
    SDL_Point pivot = {dir > 0 ? 0 : w, h};
    SDL_Rect dst = {(int)lround(hx) - pivot.x, (int)lround(hy) - pivot.y, w, h};
    SDL_SetTextureColorMod(ui->held[0], 255, 255, 255);
    SDL_SetTextureAlphaMod(ui->held[0], (Uint8)(p > 0.75 ? 255.0 * (1.0 - p) / 0.25 : 255.0));
    SDL_RenderCopyEx(ui->ren, ui->held[0], NULL, &dst, dir > 0 ? deg + 45.0 : deg + 135.0, &pivot,
                     dir > 0 ? SDL_FLIP_NONE : SDL_FLIP_HORIZONTAL);
    SDL_SetTextureAlphaMod(ui->held[0], 255);
}

static void draw_tools(PxUi *ui, const Env *e, const PxView *v)
{
    double px, py, p = v->swing_len > 0.0 ? (v->clock - v->swing_t0) / v->swing_len : 1.0;
    player_box(v, &px, &py);
    if (p >= 0.0 && p < 1.0) {
#if AIM_ATTACK
        if (v->swing_weapon == 0) draw_stab(ui, e->facing, e->stab_ux / 65536.0, e->stab_uy / 65536.0, px, py, p);
#else
        if (v->swing_weapon == 0) draw_stab(ui, e->facing, e->facing, 0.0, px, py, p);
#endif
        else draw_swing(ui, v->swing_weapon, e->facing, px, py, p);
        return;
    }
#if TOOL_DAMAGE
    /* Tool uses arrive as real swings through the fx channel (above). */
    (void)e;
#else
#if FID_MINING
    if (e->tool_time > 0) {
#else
    if (e->mine_cd) {
#endif
        /* Pickaxes and the axe swing like swords, one swing per use time
           (copper pickaxe 15 ticks, copper axe 21). */
        double use = (e->mining_tree ? 21 : 15) * (v->tick_s > 0.0 ? v->tick_s : 1.0 / 60.0);
        draw_swing(ui, WEAPON_COUNT + (e->mining_tree ? 3 : PX_PICK(e) - 1), e->facing, px, py,
                   fmod(v->clock, use) / use);
    }
#endif
}

/* Glyphs at an integer scale. */
static void text_scaled(PxUi *ui, int x, int y, int sc, uint32_t col, const char *s)
{
    SDL_Rect src = {0, 0, GLYPH_W, GLYPH_H}, dst = {x, y, GLYPH_W * sc, GLYPH_H * sc};
    SDL_SetTextureColorMod(ui->font, (Uint8)CR(col), (Uint8)CG(col), (Uint8)CB(col));
    SDL_SetTextureAlphaMod(ui->font, (Uint8)CA(col));
    for (; *s; s++, dst.x += CELL_W * sc) {
        int c = (unsigned char)*s;
        if (c <= 32 || c > 126) continue;
        src.x = (c - 32) * CELL_W;
        SDL_RenderCopy(ui->ren, ui->font, &src, &dst);
    }
}

/* Damage numbers (CombatText): orange on NPCs, deeper and larger on crits,
   red on the player; launched upward, slowing, fading over the last 40%. */
static void draw_pops(PxUi *ui, const PxView *v)
{
    int camx = cam_px(v->cam_x), camy = cam_px(v->cam_y);
    for (int i = 0; i < PX_POPS; i++) {
        const PxPop *p = &v->pop[i];
        double age = v->clock - p->t0, u = age / PX_POP_LIFE;
        if (p->dmg <= 0 || age < 0.0 || u >= 1.0) continue;
        char s[12];
        snprintf(s, sizeof s, "%d", p->dmg);
        uint32_t a = (uint32_t)(u < 0.6 ? 255.0 : 255.0 * (1.0 - u) / 0.4) << 24;
        uint32_t rgbc = p->target == FX_TARGET_PLAYER ? 0xFF505Au : p->crit ? 0xFF641Eu : 0xFFA050u;
        int sc = p->crit ? 3 : 2, w = text_w(s) * sc;
        int x = (int)lroundf(p->x) - camx - w / 2;
        int y = (int)lroundf(p->y) - camy - GLYPH_H * sc - 2 - (int)(30.0 * (1.0 - (1.0 - u) * (1.0 - u)));
        for (int d = 0; d < 4; d++)
            text_scaled(ui, x + (d == 0) - (d == 1), y + (d == 2) - (d == 3), sc, a | 0x101010u, s);
        text_scaled(ui, x, y, sc, a | rgbc, s);
    }
}

#if TREE_LEAF_VISUAL
/* Forest trees as TileDrawing.DrawTrees draws them: the canopy (Tree_Tops)
   on the trunk's top tile, leafy branches (Tree_Branches) beside inner trunk
   tiles. Positions are a deterministic function of the trunk cell (visual
   only: the core samples the branch wood when the tree is felled). Runs of
   fewer than 5 trunk tiles are stumps (trees grow 5-16): no crown. */
static bool trunk_branch(int x, int y, int side)
{
    uint32_t b = hash2(x, y, 0xB4A2u) % 10u;   /* GrowTree: 2 in 10 per side */
    return side ? (b == 6u || b == 7u) : (b == 5u || b == 7u);
}

static void draw_trees(PxUi *ui, const Env *e, const PxView *v)
{
    int camx = cam_px(v->cam_x), camy = cam_px(v->cam_y);
    int t0x = camx / PX_TILE, t0y = camy / PX_TILE;
    for (int ty = t0y - 17; ty <= t0y + PX_VIEW_TH + 5; ty++)
        for (int tx = t0x - 3; tx <= t0x + PX_VIEW_TW + 3; tx++) {
            if (!in_bounds(tx, ty) || e->tiles[ty][tx] != TILE_LOG || tile_at(e, tx, ty - 1) == TILE_LOG) continue;
            int base = ty;
            while (tile_at(e, tx, base + 1) == TILE_LOG) base++;
            if (base - ty + 1 < 5) continue;
            /* Branches on inner tiles (not the top two, not the base), never
               two in a row on one side. */
            for (int y = ty + 2; y < base; y++)
                for (int side = 0; side < 2; side++) {
                    int bx = tx + (side ? 1 : -1);
                    if (!trunk_branch(tx, y, side) || (y + 1 < base && trunk_branch(tx, y + 1, side))) continue;
                    if (tile_at(e, bx, y) != TILE_AIR) continue;
                    SDL_Rect src = {side * 42, (int)(hash2(tx, y, 0x3B1Fu) % 3u) * 42, 40, 40};
                    SDL_Rect dst = {bx * PX_TILE - (side ? 0 : 24) - camx, y * PX_TILE - 12 - camy, 40, 40};
                    SDL_RenderCopy(ui->ren, ui->tree_branch, &src, &dst);
                }
            SDL_Rect src = {(int)(hash2(tx, base, 0x7095u) % 3u) * 82, 0, 80, 80};
            SDL_Rect dst = {tx * PX_TILE + PX_TILE / 2 - 40 - camx, ty * PX_TILE + PX_TILE - 80 - camy, 80, 80};
            SDL_RenderCopy(ui->ren, ui->tree_top, &src, &dst);
        }
}
#endif

void px_fx_step(PxView *v, const Env *e, double t0, double tick_s)
{
    v->tick_s = tick_s;
    if (e->fx.swing) {
        /* Weapon uses start on the action's first tick; pickaxe / axe uses
           (TOOL_DAMAGE) at fx.swing_tick, with that tool's sprite. */
        v->swing_t0 = t0 + e->fx.swing_tick * tick_s;
        v->swing_weapon = e->fx.swing_tool >= 0 ? WEAPON_COUNT + e->fx.swing_tool : e->weapon;
#if FID_COMBAT
        v->swing_len = (v->swing_weapon == 0 ? PX_STAB_TICKS : e->item_anim_max) * tick_s;
#else
        v->swing_len = 20 * tick_s;
#endif
    }
#if FID_COMBAT
    if (e->immune_ticks > 0) v->immune_end = t0 + (FID_TICKS + e->immune_ticks) * tick_s;
#endif
    for (int i = 0; i < e->fx.n_hits; i++) {
        const FxHit *h = &e->fx.hit[i];
        double t = t0 + (h->tick + 1) * tick_s;   /* shown once its tick has run */
        if (h->target == FX_TARGET_MOB && h->slot < MAX_MOBS) v->mob_hit_t[h->slot] = t;
        else if (h->target == FX_TARGET_BOSS) v->boss_hit_t = t;
        else v->player_hit_t = t;
        /* CombatText spawns at a random point across the top of the body. */
        int jitter = (int)(hash2(h->x + i, (int)(t * 1000.0), 0x9017u) % 13u) - 6;
        v->pop[v->pop_next] = (PxPop){(float)(h->x + jitter), (float)h->y, t, h->dmg, h->target, h->crit};
        v->pop_next = (v->pop_next + 1) % PX_POPS;
    }
}

static void draw_help(PxUi *ui)
{
    static const char *const L[] = {
        "CONTROLS                          F1 toggles this help",
        "",
        "a d / arrows     run left / right (hold)",
        "w / up / space   jump (hold for a higher jump)",
        "j / l            climb rope up / down (hold)",
        ";                drop through a platform",
        "left click       mine the highlighted cell (hold)",
        "right click      place the selected block there",
        "e / wheel        cycle placeable;  click a hotbar slot",
#if AIM_ATTACK
        "f                attack toward the cursor (8 directions; hold)",
#else
        "f                attack (hold to keep swinging)",
#endif
        "t                cycle owned weapons",
        "z                open an adjacent chest",
        "c / v / b        potion / mushroom / life crystal",
        "click an item    use it (potion, mushroom, crystal, eye)",
        "1..0 - = o p [ ] g x \\ ' `    craft (or click a recipe)",
        "` at a Demon Altar   craft Suspicious Looking Eye",
        "enter            use the Eye at night: summon the boss",
        "y u i h k n m , . /   mine reach cells; shift = place",
        "F2 pause   r new world   q / esc quit",
        "",
        "Day 7.5 min, night 5 min of game time. Night spawns",
        "Zombies and Demon Eyes (lenses); caverns (y>=64) have",
        "Skeletons, bats and Demon Altars. 6 lenses at an altar",
        "make the Eye; defeat the Eye of Cthulhu for demonite.",
        "Score: achievement tiers weigh 1/3/5/8, max 145.",
        "",
        "press any key to play",
    };
    int n = (int)(sizeof L / sizeof *L), w = 340, h = n * 11 + 20;
    int x = (PX_VIEW_W - w) / 2, y = (PX_VIEW_H - h) / 2;
    fill(ui, 0, 0, PX_VIEW_W, PX_VIEW_H, 0x90000000u);
    fill(ui, x, y, w, h, 0xF014131Au);
    frame(ui, x, y, w, h, UI_ACCENT);
    for (int i = 0; i < n; i++)
        text(ui, x + 10, y + 10 + i * 11, i == 0 || i == n - 1 ? UI_ACCENT : UI_TEXT, L[i]);
}
#else
static void draw_mobs(PxUi *ui,const Env *e,const PxView *v) {
    for(int i=0;i<MAX_MOBS;i++) {
        const Mob *m=&e->mobs[i];
        if(!m->kind || !in_bounds(m->x,m->y) || e->light[m->y][m->x]<DARK_THRESHOLD) continue;
        int k=m->kind-1,w=k?44:32,h=k?32:26,n=k?5:2;
        SDL_Rect src={0,(m->phase*n/8)*h,w,h};
        int cx=m->x*PX_TILE+8-cam_px(v->cam_x),by=(m->y+1)*PX_TILE-cam_px(v->cam_y);
        SDL_Rect dst={cx-w/2,by-h,w,h};
        SDL_RendererFlip flip=m->dir<0?SDL_FLIP_HORIZONTAL:SDL_FLIP_NONE;
        if(k==0) {
            /* Installed Terraria.exe NPC.SetDefaults(type=1): alpha=175,
               color=(0,80,255,100). GetAlpha's daylight pass is (80,80,80,80);
               GetColor's overlay is (0,80,255,100). Keep the original pixels. */
            SDL_SetTextureColorMod(ui->mob[k],80,80,80);
            SDL_SetTextureAlphaMod(ui->mob[k],80);
            SDL_RenderCopyEx(ui->ren,ui->mob[k],&src,&dst,0,NULL,flip);
            SDL_SetTextureColorMod(ui->mob[k],0,80,255);
            SDL_SetTextureAlphaMod(ui->mob[k],100);
        }
        SDL_RenderCopyEx(ui->ren,ui->mob[k],&src,&dst,0,NULL,flip);
        SDL_SetTextureColorMod(ui->mob[k],255,255,255);
        SDL_SetTextureAlphaMod(ui->mob[k],255);
        fill(ui,cx-8,by-h-3,16,2,UI_BG);
        fill(ui,cx-8,by-h-3,16*m->hp/(k?16:25),2,UI_BAD);
    }
    /* Attach original held art symmetrically to the resized, interpolated body.
       This is display only: simulation reach and timing never use it. */
    int held_x=(int)lroundf(v->feet_x*PX_TILE)-cam_px(v->cam_x)
        +PLAYER_W*PX_TILE/2+e->facing*12-10;
    int held_y=(int)lroundf(v->feet_y*PX_TILE)-cam_px(v->cam_y)
        +PX_TILE-PLAYER_H*PX_TILE/2-10;
    if(e->attack_cd) icon(ui,ui->item[WEAPON_ITEM[e->weapon]],
        held_x,held_y,20,255);
    else if(e->mine_cd) icon(ui,e->mining_tree?ui->axe:ui->pick[e->tool_tier-1],
        held_x,held_y,20,255);
}
#endif

bool px_screenshot(PxUi *ui,const char *path) {
    int w,h; SDL_GetRendererOutputSize(ui->ren,&w,&h);
    SDL_Surface *s=SDL_CreateRGBSurfaceWithFormat(0,w,h,32,SDL_PIXELFORMAT_ARGB8888);
    if(!s) return false;
    bool ok=SDL_RenderReadPixels(ui->ren,NULL,s->format->format,s->pixels,s->pitch)==0;
    SDL_Surface *rgb=ok?SDL_ConvertSurfaceFormat(s,SDL_PIXELFORMAT_RGB24,0):NULL;
    ok=rgb && SDL_SaveBMP(rgb,path)==0;
    if(rgb) SDL_FreeSurface(rgb);
    SDL_FreeSurface(s); return ok;
}

void px_draw(PxUi *ui, const Env *env, const PxView *v)
{
    /* Light, hover and mob visibility read the whole map, not just the
       observation window the simulator keeps exact. */
    Env full = *env;
    light_full(&full);
    const Env *e = &full;
    SDL_Rect view = {0, 0, PX_VIEW_W, PX_VIEW_H};
    bool over = e->terminated || e->truncated;

    set_col(ui, VOID_COL);
    SDL_RenderClear(ui->ren);

    SDL_RenderSetClipRect(ui->ren, &view);
    draw_world(ui, e, v);
#if PX_V10 && TREE_LEAF_VISUAL
    draw_trees(ui, e, v);
#endif
#if PX_V10
#if FID_MINING
    draw_dig(ui, e, v);
#endif
    draw_mobs_v10(ui, e, v, 255);
    draw_player(ui, e, v, 255);
    draw_tools(ui, e, v);
    draw_light(ui, e, v);
    draw_mobs_v10(ui, e, v, 60);
    draw_player(ui, e, v, 34);
    draw_boss(ui, e, v);
    draw_pops(ui, v);
#else
    draw_mobs(ui,e,v);
    draw_player(ui, e, v, 255);
    draw_light(ui, e, v);
    /* After the light pass so the dark never swallows you completely: the
       engine grants PLAYER_LIGHT 3, which is deliberately almost nothing. */
    draw_player(ui, e, v, 34);
#endif
    if (!over) draw_reach(ui, e, v);
    draw_hurt_vignette(ui, e, v);
#if PX_V10
    draw_boss_bar(ui, e);
#endif
    draw_toast(ui, v);
    if (over) draw_gameover(ui, e);
#if PX_V10
    else if (v->help) draw_help(ui);
#endif
    SDL_RenderSetClipRect(ui->ren, NULL);

    draw_hud(ui, e, v);
    draw_sidebar(ui, e, v);

    SDL_RenderPresent(ui->ren);
}
