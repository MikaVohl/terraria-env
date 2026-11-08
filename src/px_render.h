/* Pixel frontend: SDL2 window, tile art, and all drawing.
 *
 * Everything here is expressed in "art pixels". The renderer runs on a logical
 * surface of PX_WIN_W x PX_WIN_H and lets SDL scale it up by an integer factor
 * with nearest-neighbour filtering, so the pixel grid stays crisp and callers
 * never have to think about the zoom level.
 *
 * Tiles come from a local Terraria install, which is required: there is no
 * synthesised art any more. See px_init. */
#ifndef PX_RENDER_H
#define PX_RENDER_H

#include "env.h"

/* One frontend, two cores. The Makefile builds `terraria-px` against the v4
   core in include/ and `terraria-px-v10` against variants/v10/include; the
   v10 build adds the day/night sky, the Demon Altar, the night and cavern
   mobs, the Eye of Cthulhu, multi-cell objects, fixed-point bodies and the
   tiered achievement score. Everything v10-only is under PX_V10. */
#define PX_V10      (ENV_VERSION >= 10)
#define PX_STR_(x)  #x
#define PX_STR(x)   PX_STR_(x)
#define PX_TITLE    "terraria-lite v" PX_STR(ENV_VERSION)

#define PX_TILE     16                        /* texture edge, art px */
#define PX_VIEW_TW  30                        /* world viewport, tiles */
#define PX_VIEW_TH  (PX_V10 ? 30 : 26)        /* v10: room for 21 recipes + 40 achievements */
#define PX_VIEW_W   (PX_VIEW_TW * PX_TILE)
#define PX_VIEW_H   (PX_VIEW_TH * PX_TILE)
#define PX_SIDE_W   256                       /* crafting / achievement column */
#define PX_HUD_H    112                       /* two inventory rows + equipment */
#define PX_WIN_W    (PX_VIEW_W + PX_SIDE_W)
#define PX_WIN_H    (PX_VIEW_H + PX_HUD_H)

/* Everything the drawing code needs that Env does not carry: the sub-tick
   interpolation state and where the pointer is. Positions are in tiles and
   fractional -- decoupling the 60 Hz frame from the fixed sim tick is the
   entire reason this frontend exists. */
typedef struct {
    float  cam_x, cam_y;      /* viewport top-left, in tiles */
    float  feet_x, feet_y;    /* interpolated FEET cell, in tiles */
    double clock;             /* seconds since launch; drives the animations */
    int    walk_dir;          /* -1 / 0 / +1: what the player is being told to do */
    bool   airborne;

    int    hover_reach;       /* nearest in-bounds reach cell to the cursor, or -1 */
    int    hover_x, hover_y;  /* world cell that reach index names */
    bool   can_mine;          /* a left click on hover_reach would actually work */
    bool   can_place;
    int    hover_recipe;      /* recipe row under the cursor, or -1 */
    int    hover_ach;         /* achievement cell under the cursor, or -1 */
    int    hover_slot;        /* PLACEABLES index under the cursor, or -1 */
    int    hover_item;        /* any item in either inventory row, or -1 */

    const char *toast;        /* transient banner, or NULL */
    float  toast_a;           /* 0..1 opacity for the banner */
#if PX_V10
    /* Mobs and the boss move several tiles per action at 15 game ticks per
       step, so they are interpolated like the player: world px, top-left of
       the hitbox (mobs) or of the 3x3 body (boss). */
    float  mob_x[MAX_MOBS], mob_y[MAX_MOBS];
    float  boss_x, boss_y;
    double swing_t0, swing_len; /* real-time melee swing, seconds on `clock` */
    bool   help;               /* controls overlay */
#endif
} PxView;

/* Interpolation anchor of the player, in tiles: the left column / feet row of
   the 2x3 body the sprite is drawn on. With v10's FID_PHYSICS the 20x42 px
   fixed-point hitbox moves freely, so the anchor is derived from it (sprite
   centred on the hitbox, frame bottom on its bottom pixel). */
static inline void px_feet(const Env *e, float *x, float *y)
{
#if PX_V10 && FID_PHYSICS
    *x = ((float)e->pos_x / FIX_ONE + PLAYER_PX_W / 2.0f - PLAYER_W * PX_TILE / 2.0f) / PX_TILE;
    *y = ((float)e->pos_y / FIX_ONE + PLAYER_PX_H - PX_TILE) / PX_TILE;
#else
    *x = (float)e->px;
    *y = (float)e->py;
#endif
}

#if PX_V10
/* A mob's hitbox in world px (top-left, size): its fixed-point NPC body with
   FID_MOBS, otherwise its grid cell. */
void px_mob_box(const Mob *m, float *x, float *y, int *w, int *h);
#endif

typedef struct PxUi PxUi;

/* `tex_dir` is a Terraria ExtractedTextures directory, or NULL to probe the
   default Steam location. Returns NULL, after saying on stderr which file was
   missing and where it looked, if the directory or any sheet in it is absent.
   Nothing is drawn without the real art, so this is a hard failure. */
PxUi *px_init(int scale, const char *tex_dir);
void  px_shutdown(PxUi *ui);
void  px_draw(PxUi *ui, const Env *e, const PxView *v);
bool  px_screenshot(PxUi *ui, const char *path); /* BMP, for reproducible UI QA */

/* Out-of-band status for the frame loop -- a replay's step counter, say --
   that does not belong in the drawn HUD. */
void  px_set_title(PxUi *ui, const char *title);

/* Current pointer position in window pixels. False when the window does not
   have mouse focus, in which case there is no meaningful pointer at all.
   Polled rather than tracked, so a gap in the motion-event stream cannot leave
   the caller's idea of the cursor stale. */
bool px_pointer(const PxUi *ui, int *wx, int *wy);

/* Window pixel -> art pixel, letterboxing and HiDPI included. */
void px_to_art(const PxUi *ui, int wx, int wy, int *ax, int *ay);

/* Art pixel -> world cell, using the same rounding the world draw does. */
void px_cell_at(const PxView *v, int ax, int ay, int *tx, int *ty);

/* World cell -> the art pixel at its centre. The inverse direction of
   px_cell_at, and what the nearest-cell snap in the frontend measures against:
   comparing cursor-to-centre distances is only meaningful in one space, and art
   pixels is the one both the cursor and the tile grid already live in. */
void px_cell_centre(const PxView *v, int tx, int ty, int *ax, int *ay);

/* Art pixel -> panel hit test; -1 when the point is outside that panel. */
int  px_recipe_at(int ax, int ay);
int  px_ach_at(int ax, int ay);
int  px_hotbar_at(int ax, int ay);   /* -> PLACEABLES index, not an item index */
int  px_item_at(int ax,int ay);

/* True when the recipe's ingredients are in the pack and its station is in
   range. The frontend has to predict this to grey the panel out; sim.c remains
   the authority and a click on a greyed row still goes through so the engine
   can say exactly what is missing. */
bool px_recipe_ready(const Env *e, int r);

#endif /* PX_RENDER_H */
