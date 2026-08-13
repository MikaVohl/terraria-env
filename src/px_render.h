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

#define PX_TILE     16                        /* texture edge, art px */
#define PX_VIEW_TW  30                        /* world viewport, tiles */
#define PX_VIEW_TH  20
#define PX_VIEW_W   (PX_VIEW_TW * PX_TILE)
#define PX_VIEW_H   (PX_VIEW_TH * PX_TILE)
#define PX_SIDE_W   192                       /* crafting / achievement column */
#define PX_HUD_H    80                        /* status strip under the world */
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

    const char *toast;        /* transient banner, or NULL */
    float  toast_a;           /* 0..1 opacity for the banner */
} PxView;

typedef struct PxUi PxUi;

/* `tex_dir` is a Terraria ExtractedTextures directory, or NULL to probe the
   default Steam location. Returns NULL, after saying on stderr which file was
   missing and where it looked, if the directory or any sheet in it is absent.
   Nothing is drawn without the real art, so this is a hard failure. */
PxUi *px_init(int scale, const char *tex_dir);
void  px_shutdown(PxUi *ui);
void  px_draw(PxUi *ui, const Env *e, const PxView *v);

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

/* True when the recipe's ingredients are in the pack and its station is in
   range. The frontend has to predict this to grey the panel out; sim.c remains
   the authority and a click on a greyed row still goes through so the engine
   can say exactly what is missing. */
bool px_recipe_ready(const Env *e, int r);

#endif /* PX_RENDER_H */
