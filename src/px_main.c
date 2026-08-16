/* Pixel frontend entry point: argument parsing, input, and the frame loop.
 *
 * The engine is strictly lockstep -- one env_step per tick, one action per
 * tick -- and nothing here changes that. What changes is who watches the
 * clock: the simulation advances every --tick-ms, the window redraws at 60 Hz,
 * and the player and camera are drawn interpolated between the previous tile
 * and the current one. Discrete grid physics, continuous motion, and the core
 * pays nothing for it. */
#define SDL_MAIN_HANDLED
#include <SDL.h>

#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "frontend.h"
#include "keymap.h"
#include "px_render.h"

#define DEFAULT_TICK_MS 80    /* 12.5 tiles/s walk speed at one tile per tick */
#define MIN_TICK_MS     10
#define MAX_TICK_MS     1000
#define DEFAULT_SCALE   2
#define MIN_SCALE       1
#define MAX_SCALE       6

#define FPS             60    /* render rate; the sim rate is --tick-ms */
#define CAM_LAG         9.0f  /* camera catch-up rate, 1/seconds */
#define TOAST_SECS      2.2

/* Actions banked between two ticks. Unlike the terminal frontend this does
   *not* collapse a repeated tail: SDL reports real key-down and key-up, so a
   held key is genuinely held and is serviced from the live keyboard state
   instead of being banked. Only discrete one-shot actions -- mine, place,
   craft, cycle -- come through here, and every one of them was a deliberate
   press that deserves its own tick.

   16 rather than 8 because one hotbar click can bank a whole lap of the
   selection cycle: PLACEABLE_COUNT - 1 = 7 ACT_SELECT_NEXT in a single burst.
   At 8 that burst plus anything already queued would silently lose its tail
   and land the selection on the wrong slot. */
#define QCAP 16

typedef struct {
    int act[QCAP];
    int head, n;
} Queue;

static void q_push(Queue *q, int act)
{
    if (q->n == QCAP) return;
    q->act[(q->head + q->n) % QCAP] = act;
    q->n++;
}

static int q_pop(Queue *q)
{
    int act;
    if (q->n == 0) return -1;
    act = q->act[q->head];
    q->head = (q->head + 1) % QCAP;
    q->n--;
    return act;
}

/* Held state, refreshed from SDL events rather than polled per tick. */
typedef struct {
    bool left, right, jump;
    bool lmb, rmb;
    int  mx, my;          /* window pixels */
} Input;

/* ---- Agent tape --------------------------------------------------------- *
 *
 * A recorded rollout: the seed a policy played, and the action it chose on
 * every tick. Replaying that reproduces the episode exactly rather than
 * approximating it, because the engine is deterministic -- selftest pins
 * byte-identical state after 1500 identical actions.
 *
 * Which is why the trainer does not have to live in this process. torch stays
 * on the Python side, SDL stays out of the shared library the trainer loads,
 * and neither has to know the other exists. The alternative -- driving this
 * renderer live from Python -- would mean re-implementing the interpolation,
 * camera easing and frame pacing below on that side, or exporting all of it. */

typedef struct {
    int  *act;
    int   n, i;
    unsigned long long seed;
    int   max_steps;
    char  label[80];
} Tape;

static bool tape_fail(const char *prog, const char *path, int line,
                      const char *what)
{
    if (line > 0) fprintf(stderr, "%s: %s:%d: %s\n", prog, path, line, what);
    else          fprintf(stderr, "%s: %s: %s\n", prog, path, what);
    return false;
}

/* Header lines are `key value`, then `actions N` followed by N integers, one
   per line. Blank lines and `#` comments are skipped. Deliberately text: a
   tape is small, worth diffing, and worth being able to hand-edit. */
static bool tape_load(Tape *t, const char *path, const char *prog)
{
    char  buf[256];
    FILE *f = fopen(path, "r");
    int   line = 0, got = 0;

    if (!f) return tape_fail(prog, path, 0, strerror(errno));

    memset(t, 0, sizeof *t);
    t->seed = 1;
    snprintf(t->label, sizeof t->label, "agent");

    while (fgets(buf, sizeof buf, f)) {
        char *s = buf;
        line++;
        while (*s == ' ' || *s == '\t') s++;
        if (*s == '#' || *s == '\n' || *s == '\0') continue;

        if (t->act) {                     /* past the header: action lines */
            char *end;
            long v = strtol(s, &end, 10);
            if (end == s) { fclose(f); return tape_fail(prog, path, line, "not an action"); }
            if (v < 0 || v >= ACT_COUNT) {
                fclose(f);
                return tape_fail(prog, path, line, "action out of range");
            }
            if (got == t->n) { fclose(f); return tape_fail(prog, path, line, "more actions than declared"); }
            t->act[got++] = (int)v;
            continue;
        }

        if (!strncmp(s, "seed ", 5))            t->seed = strtoull(s + 5, NULL, 10);
        else if (!strncmp(s, "max_steps ", 10)) t->max_steps = (int)strtol(s + 10, NULL, 10);
        else if (!strncmp(s, "label ", 6)) {
            size_t k = strcspn(s + 6, "\r\n");
            if (k >= sizeof t->label) k = sizeof t->label - 1;
            memcpy(t->label, s + 6, k);
            t->label[k] = '\0';
        } else if (!strncmp(s, "actions ", 8)) {
            long n = strtol(s + 8, NULL, 10);
            if (n <= 0) { fclose(f); return tape_fail(prog, path, line, "actions count must be positive"); }
            t->n   = (int)n;
            t->act = calloc((size_t)n, sizeof *t->act);
            if (!t->act) { fclose(f); return tape_fail(prog, path, 0, "out of memory"); }
        } else {
            fclose(f);
            return tape_fail(prog, path, line, "unknown header key");
        }
    }
    fclose(f);

    if (!t->act)     return tape_fail(prog, path, 0, "no 'actions N' header");
    if (got != t->n) return tape_fail(prog, path, 0, "fewer actions than declared");
    return true;
}


/* ---- Argument parsing (same shape as src/main.c) ------------------------ */

static void usage(FILE *out, const char *prog)
{
    int i;
    fprintf(out,
        "terraria-px -- the pixel frontend for terraria-lite\n"
        "\n"
        "usage: %s [--seed N] [--steps N] [--tick-ms N] [--scale N]\n"
        "          [--textures DIR] [--watch TAPE] [--help]\n"
        "\n"
        "  --seed N        world seed (default 1)\n"
        "  --steps N       episode step limit (default %d)\n"
        "  --tick-ms N     simulation tick length in ms (default %d)\n"
        "  --scale N       integer pixel zoom, 1..%d (default %d)\n"
        "  --textures DIR  Terraria ExtractedTextures directory; without one\n"
        "                  the default Steam location is probed. A Terraria\n"
        "                  install is required -- there is no fallback art\n"
        "  --watch TAPE    replay a recorded agent rollout instead of taking\n"
        "                  input. The tape carries its own seed and step\n"
        "                  limit, so --seed and --steps are ignored. Write one\n"
        "                  with: uv run python -m terraria_lite.watch\n"
        "  --help          this message\n"
        "\n"
        "The simulation still takes exactly one step per tick. The window\n"
        "renders at 60 fps and interpolates the player and camera between\n"
        "ticks, and a tick where nothing is queued and the world is at rest is\n"
        "skipped outright so standing still costs no steps.\n"
        "\n"
        "controls\n"
        "  a d / arrows  walk        w or space  jump      e  cycle placeable\n"
        "  left click    mine the cell under the cursor\n"
        "  right click   place there\n"
        "  wheel         cycle placeable\n"
        "  y u i         mine up-left / up / up-right      (hold shift to place)\n"
        "  h   k         mine head-left / head-right\n"
        "  n   m         mine foot-left / foot-right\n"
        "  , . /         mine down-left / down / down-right\n",
        prog, DEFAULT_MAX_STEPS, DEFAULT_TICK_MS, MAX_SCALE, DEFAULT_SCALE);
    for (i = 0; i < RECIPE_COUNT; i++)
        fprintf(out, "  %c             craft %s\n", KB_CRAFT[i], RECIPES[i].name);
    fprintf(out,
        "  r             new world (seed + 1)\n"
        "  q or escape   quit\n"
        "\n"
        "watch mode (--watch) ignores the controls above except\n"
        "  space         pause / resume\n"
        "  . or right    single step while paused\n"
        "  r             restart the tape from the top\n"
        "  q or escape   quit\n");
}


/* ---- Input mapping ------------------------------------------------------ */

/* SDL keycodes equal their ASCII character for every printable key, so the
   shared tables in keymap.h work verbatim. The pixel frontend reads shift as
   a modifier rather than as a shifted character, so it only needs the mine
   row: place is the same slot with KMOD_SHIFT held. */
static int key_reach(SDL_Keycode k)  { return kb_slot(KB_MINE,  (int)k); }
static int key_recipe(SDL_Keycode k) { return kb_slot(KB_CRAFT, (int)k); }

/* ---- Episode plumbing --------------------------------------------------- */

/* What a held key or held mouse button means this tick. Mining outranks
   walking: holding the button over a cell is an explicit instruction, and one
   action per tick means something has to yield. A jump is only issued when it
   would actually take, so holding W through the rise leaves those ticks free
   for the walk keys and you get a real diagonal arc.

   Auto-repeat is gated on the action actually landing. A held button over an
   empty cell or an ore your pickaxe cannot touch would otherwise bank one
   failed step per tick for as long as you leaned on it, and the step budget is
   the scarce resource here. Deliberate failures still go through: those come
   from the key queue, which is never filtered. */
static int continuous_action(const Env *e, const PxView *v, const Input *in)
{
    if (v->hover_reach >= 0) {
        if (in->lmb && v->can_mine)  return ACT_MINE_FIRST + v->hover_reach;
        if (in->rmb && v->can_place) return ACT_PLACE_FIRST + v->hover_reach;
    }
    if (in->jump && at_rest(e)) return ACT_JUMP;
    if (in->left != in->right)  return in->left ? ACT_LEFT : ACT_RIGHT;
    return -1;
}

/* How many ACT_SELECT_NEXT presses it takes to land on `want`, or 0 when it
   cannot be reached.

   The frontend must never assign e->selected itself. There is exactly one
   selection action and it only cycles, so a human who could jump straight to a
   slot would be playing a cheaper game than the agent the benchmark scores.
   Simulating do_select's rule -- advance to the next slot holding stock,
   wrapping, stand still when the current slot is the only stocked one -- and
   then queueing that many real presses costs exactly what mashing `e` costs. */
static int select_presses(const Env *e, int want)
{
    int sel = e->selected, n;

    /* An empty stack is not on the cycle at all, so there is no press count
       that reaches it and clicking it must be inert. */
    if (want == sel || e->inv[PLACEABLES[want].item] <= 0) return 0;
    for (n = 1; n <= PLACEABLE_COUNT; n++) {
        int i, next = (sel + 1) % PLACEABLE_COUNT;
        for (i = 0; i < PLACEABLE_COUNT; i++) {
            int cand = (sel + 1 + i) % PLACEABLE_COUNT;
            if (e->inv[PLACEABLES[cand].item] > 0) { next = cand; break; }
        }
        if (next == sel) return 0;   /* the cycle has stalled short of `want` */
        sel = next;
        if (sel == want) return n;
    }
    return 0;
}

/* Where the cursor is pointing and what a click there would do. Recomputed
   every frame, before any tick consumes it, so a held mouse button follows the
   player as it moves.

   The target is the reach cell whose centre is *nearest* the cursor rather than
   the one under it: ten 16 px squares scattered around the player are a fiddly
   thing to hit exactly, and every point in the viewport has an unambiguous
   nearest one. Distances are compared squared, in art pixels, so this is a
   handful of integer multiplies and no sqrtf. */
static void update_hover(PxView *v, const Env *e, const PxUi *ui, const Input *in)
{
    int ax, ay, i, best = -1;
    long best_d2 = 0;

    v->hover_reach = -1;
    v->can_mine = v->can_place = false;

    px_to_art(ui, in->mx, in->my, &ax, &ay);
    v->hover_recipe = px_recipe_at(ax, ay);
    v->hover_ach    = px_ach_at(ax, ay);
    v->hover_slot   = px_hotbar_at(ax, ay);

    /* Snapping only applies inside the world viewport. Over the sidebar or the
       HUD there is no aim at all -- otherwise crossing the window to click a
       recipe would drag a live mine target along under a held button. */
    if (ax < 0 || ay < 0 || ax >= PX_VIEW_W || ay >= PX_VIEW_H) return;

    for (i = 0; i < REACH_COUNT; i++) {
        int tx = e->px + REACH_DX[i], ty = e->py + REACH_DY[i], cx, cy;
        long dx, dy, d2;

        /* At the world edge some of the ten cells do not exist. */
        if (!in_bounds(tx, ty)) continue;
        px_cell_centre(v, tx, ty, &cx, &cy);
        dx = ax - cx;
        dy = ay - cy;
        d2 = dx * dx + dy * dy;
        if (best < 0 || d2 < best_d2) { best = i; best_d2 = d2; }
    }
    if (best < 0) return;

    v->hover_reach = best;
    v->hover_x = e->px + REACH_DX[best];
    v->hover_y = e->py + REACH_DY[best];

    {
        Tile t = tile_at(e, v->hover_x, v->hover_y);
        v->can_mine  = t != TILE_AIR && tile_tier(t) != TIER_NEVER &&
                       e->tool_tier >= tile_tier(t);
        v->can_place = t == TILE_AIR && e->inv[PLACEABLES[e->selected].item] > 0;
    }
}

typedef struct {
    char   text[64];
    double until;      /* seconds on the frontend clock */
} Toast;

/* One env_step, plus catching whatever it unlocked for the banner. */
static void apply(Env *e, int act, Toast *t, double clock)
{
    uint32_t before = e->achievements, gained;
    int a;

    env_step(e, act);

    gained = e->achievements & ~before;
    for (a = 0; a < ACH_COUNT; a++)
        if ((gained >> a) & 1u) {
            snprintf(t->text, sizeof t->text, "unlocked: %s", ACH_NAME[a]);
            t->until = clock + TOAST_SECS;
            break;   /* one per tick is all that ever fires */
        }
}

static void snap_camera(PxView *v, const Env *e)
{
    float mx = (float)(WORLD_W - PX_VIEW_TW), my = (float)(WORLD_H - PX_VIEW_TH);

    v->feet_x = (float)e->px;
    v->feet_y = (float)e->py;
    v->cam_x  = v->feet_x + 0.5f - PX_VIEW_TW / 2.0f;
    v->cam_y  = v->feet_y - 0.5f - PX_VIEW_TH / 2.0f;
    if (v->cam_x < 0.0f) v->cam_x = 0.0f;
    if (v->cam_y < 0.0f) v->cam_y = 0.0f;
    if (v->cam_x > mx) v->cam_x = mx;
    if (v->cam_y > my) v->cam_y = my;
}

int main(int argc, char **argv)
{
    const char *prog = argc > 0 && argv[0] ? argv[0] : "terraria-px";
    const char *tex_dir = NULL;
    const char *tape_path = NULL;
    Tape tape;
    bool watching = false, paused = false;
    int  step_once = 0;
    unsigned long long seed = 1;
    unsigned long long steps = DEFAULT_MAX_STEPS;
    unsigned long long tick = DEFAULT_TICK_MS;
    unsigned long long scale = DEFAULT_SCALE;
    EnvConfig cfg;
    Env *e;
    PxUi *ui;
    PxView view;
    Queue q;
    Input in;
    Toast toast;
    uint64_t next_tick, last_frame, frame_epoch, frames = 0;
    int prev_px, prev_py, last_act = ACT_NOOP;
    bool running = true;
    int i;

    memset(&tape, 0, sizeof tape);

    for (i = 1; i < argc; i++) {
        const char *a = argv[i];
        unsigned long long *slot = NULL;

        if (!strcmp(a, "--help") || !strcmp(a, "-h")) { usage(stdout, prog); return 0; }
        if (!strcmp(a, "--textures")) {
            if (i + 1 >= argc) {
                fprintf(stderr, "%s: '%s' needs a value\n", prog, a);
                return 2;
            }
            tex_dir = argv[++i];
            continue;
        }
        if (!strcmp(a, "--watch")) {
            if (i + 1 >= argc) {
                fprintf(stderr, "%s: '%s' needs a value\n", prog, a);
                return 2;
            }
            tape_path = argv[++i];
            continue;
        }
        if (!strcmp(a, "--seed"))    slot = &seed;
        if (!strcmp(a, "--steps"))   slot = &steps;
        if (!strcmp(a, "--tick-ms")) slot = &tick;
        if (!strcmp(a, "--scale"))   slot = &scale;
        if (!slot) {
            fprintf(stderr, "%s: unknown option '%s'\n\n", prog, a);
            usage(stderr, prog);
            return 2;
        }
        if (i + 1 >= argc) {
            fprintf(stderr, "%s: '%s' needs a value\n", prog, a);
            return 2;
        }
        if (!parse_u64(argv[++i], slot)) {
            fprintf(stderr, "%s: '%s' is not a non-negative integer\n", prog, argv[i]);
            return 2;
        }
    }
    if (steps == 0 || steps > 100000000ULL) {
        fprintf(stderr, "%s: --steps must be between 1 and 100000000\n", prog);
        return 2;
    }
    if (tick < MIN_TICK_MS || tick > MAX_TICK_MS) {
        fprintf(stderr, "%s: --tick-ms must be between %d and %d\n",
                prog, MIN_TICK_MS, MAX_TICK_MS);
        return 2;
    }
    if (scale < MIN_SCALE || scale > MAX_SCALE) {
        fprintf(stderr, "%s: --scale must be between %d and %d\n",
                prog, MIN_SCALE, MAX_SCALE);
        return 2;
    }

    if (tape_path) {
        if (!tape_load(&tape, tape_path, prog)) return 2;
        /* The tape owns the world it was recorded against. Honouring --seed
           here would replay a policy's actions into a different world, which
           looks plausible for a few ticks and then diverges into nonsense. */
        watching = true;
        seed     = tape.seed;
        if (tape.max_steps > 0) steps = (unsigned long long)tape.max_steps;
        printf("watching %s: %d actions, seed %llu\n",
               tape.label, tape.n, (unsigned long long)tape.seed);
    }

    e = calloc(1, sizeof *e);   /* ~25 KB: too big for a comfortable stack frame */
    if (!e) {
        fprintf(stderr, "%s: out of memory\n", prog);
        return 1;
    }
    cfg.max_steps = (int)steps;
    env_init(e, cfg);
    env_reset(e, (uint64_t)seed);

    SDL_SetMainReady();
    ui = px_init((int)scale, tex_dir);
    if (!ui) { env_free(e); free(e); return 1; }

    memset(&q, 0, sizeof q);
    memset(&in, 0, sizeof in);
    memset(&toast, 0, sizeof toast);
    memset(&view, 0, sizeof view);
    view.hover_recipe = view.hover_ach = view.hover_reach = view.hover_slot = -1;
    snap_camera(&view, e);
    prev_px = e->px;
    prev_py = e->py;

    next_tick   = SDL_GetTicks64() + tick;
    last_frame  = SDL_GetTicks64();
    frame_epoch = last_frame;

    while (running) {
        SDL_Event ev;
        uint64_t now;
        bool over;
        float alpha, dt, tgt_x, tgt_y, k;

        while (SDL_PollEvent(&ev)) {
            switch (ev.type) {
            case SDL_QUIT:
                running = false;
                break;

            case SDL_MOUSEMOTION:
                break;              /* position comes from the per-frame poll */

            case SDL_MOUSEBUTTONDOWN:
            case SDL_MOUSEBUTTONUP: {
                bool down = (ev.type == SDL_MOUSEBUTTONDOWN);
                in.mx = ev.button.x;
                in.my = ev.button.y;
                if (ev.button.button == SDL_BUTTON_LEFT) {
                    int ax, ay, r, s;
                    px_to_art(ui, in.mx, in.my, &ax, &ay);
                    r = px_recipe_at(ax, ay);
                    s = px_hotbar_at(ax, ay);
                    if (!down) {
                        /* Release anywhere ends the drag, panel or not, so a
                           press in the world that lifts over the sidebar
                           cannot leave the button latched down. */
                        in.lmb = false;
                    } else if (r >= 0) {
                        /* A click in the recipe panel crafts; sim.c decides
                           whether it succeeds and says why when it does not. */
                        q_push(&q, RECIPE_FIRST_ACTION + r);
                    } else if (s >= 0) {
                        /* Selection is a cycle in the action space, so a click
                           on a slot buys it the honest way: n real presses. */
                        int n = select_presses(e, s);
                        while (n-- > 0) q_push(&q, ACT_SELECT_NEXT);
                    } else {
                        in.lmb = true;
                    }
                } else if (ev.button.button == SDL_BUTTON_RIGHT) {
                    in.rmb = down;
                }
                break;
            }

            case SDL_MOUSEWHEEL:
                if (ev.wheel.y != 0) q_push(&q, ACT_SELECT_NEXT);
                break;

            case SDL_KEYDOWN:
            case SDL_KEYUP: {
                bool down = (ev.type == SDL_KEYDOWN);
                SDL_Keycode k2 = ev.key.keysym.sym;
                int r;

                /* Watch mode owns the action stream, so gameplay keys would
                   only fight the tape. Transport controls only. */
                if (watching) {
                    if (!down || ev.key.repeat) break;
                    if (k2 == SDLK_ESCAPE || k2 == SDLK_q) { running = false; break; }
                    if (k2 == SDLK_SPACE) { paused = !paused; break; }
                    if (k2 == SDLK_PERIOD || k2 == SDLK_RIGHT) {
                        paused = true;
                        step_once = 1;
                        break;
                    }
                    if (k2 == SDLK_r) {
                        tape.i = 0;
                        env_reset(e, (uint64_t)seed);
                        toast.until = 0.0;
                        snap_camera(&view, e);
                        prev_px = e->px;
                        prev_py = e->py;
                        last_act = ACT_NOOP;
                    }
                    break;
                }

                switch (k2) {
                case SDLK_a: case SDLK_LEFT:  in.left  = down; continue;
                case SDLK_d: case SDLK_RIGHT: in.right = down; continue;
                case SDLK_w: case SDLK_UP: case SDLK_SPACE: in.jump = down; continue;
                default: break;
                }
                if (!down || ev.key.repeat) break;   /* the rest are one-shots */

                if (k2 == SDLK_ESCAPE || k2 == SDLK_q) { running = false; break; }
                if (k2 == SDLK_r) {
                    seed += 1;
                    env_reset(e, (uint64_t)seed);
                    memset(&q, 0, sizeof q);
                    toast.until = 0.0;
                    snap_camera(&view, e);
                    prev_px = e->px;
                    prev_py = e->py;
                    last_act = ACT_NOOP;
                    break;
                }
                if (k2 == SDLK_e) { q_push(&q, ACT_SELECT_NEXT); break; }

                r = key_reach(k2);
                if (r >= 0) {
                    q_push(&q, ((ev.key.keysym.mod & KMOD_SHIFT) ? ACT_PLACE_FIRST
                                                                 : ACT_MINE_FIRST) + r);
                    break;
                }
                r = key_recipe(k2);
                if (r >= 0) q_push(&q, RECIPE_FIRST_ACTION + r);
                break;
            }

            default:
                break;
            }
        }

        now  = SDL_GetTicks64();
        over = e->terminated || e->truncated || (watching && tape.i >= tape.n);

        /* The pointer is polled, never accumulated from motion events. Any gap
           in that stream -- the cursor moved while another window had focus, a
           warp from outside the process, a coalesced burst -- would otherwise
           leave mx/my stale for good, and the hover would sit tiles away from
           the real pointer until you jiggled it back inside the window.
           Measured: an unfocused move left the two 277 points apart.

           Without mouse focus there is no pointer to speak of, so drop the
           buttons too: a click that lands elsewhere must not stay latched and
           fire the moment focus returns. */
        if (!px_pointer(ui, &in.mx, &in.my)) in.lmb = in.rmb = false;

        /* Hover has to be current before the tick loop reads it, or a held
           mouse button would act on where the player was last frame. */
        update_hover(&view, e, ui, &in);

        if (over) {
            next_tick = now + tick;
            memset(&q, 0, sizeof q);
            prev_px = e->px;
            prev_py = e->py;
        }

        while (!over && now >= next_tick) {
            int act;

            if (watching) {
                /* Re-arm the deadline before bailing, or unpausing would cash
                   in every tick banked while the window sat still. */
                if (paused && step_once == 0) { next_tick = now + tick; break; }
                if (step_once > 0) step_once--;
                act = tape.act[tape.i++];
            } else {
                act = q_pop(&q);
                if (act < 0) act = continuous_action(e, &view, &in);
            }

            prev_px = e->px;
            prev_py = e->py;

            /* Nothing asked for and nothing in motion: the world is a fixed
               point, so an ACT_NOOP here would spend a step and change
               nothing. Skip the tick and keep rendering. */
            if (act < 0 && at_rest(e)) {
                last_act = ACT_NOOP;
            } else {
                if (act < 0) act = ACT_NOOP;
                apply(e, act, &toast, (double)now / 1000.0);
                last_act = act;
            }

            next_tick += tick;
            /* A stalled window (drag, sleep) must not cash in a burst of
               banked ticks the moment it comes back. */
            if (now > next_tick + 4 * tick) next_tick = now + tick;
            if (e->terminated || e->truncated) break;
        }

        /* Sub-tick position. `next_tick - tick` is when the last tick fired. */
        alpha = (float)((double)(now + tick - next_tick) / (double)tick);
        if (alpha < 0.0f) alpha = 0.0f;
        if (alpha > 1.0f) alpha = 1.0f;
        view.feet_x = (float)prev_px + ((float)e->px - (float)prev_px) * alpha;
        view.feet_y = (float)prev_py + ((float)e->py - (float)prev_py) * alpha;

        dt = (float)(now - last_frame) / 1000.0f;
        if (dt > 0.1f) dt = 0.1f;
        last_frame = now;

        /* The camera chases rather than tracks: an exponential ease is what
           keeps a one-tile-per-tick teleport from reading as a jolt. */
        tgt_x = view.feet_x + 0.5f - PX_VIEW_TW / 2.0f;
        tgt_y = view.feet_y - 0.5f - PX_VIEW_TH / 2.0f;
        if (tgt_x < 0.0f) tgt_x = 0.0f;
        if (tgt_y < 0.0f) tgt_y = 0.0f;
        if (tgt_x > (float)(WORLD_W - PX_VIEW_TW)) tgt_x = (float)(WORLD_W - PX_VIEW_TW);
        if (tgt_y > (float)(WORLD_H - PX_VIEW_TH)) tgt_y = (float)(WORLD_H - PX_VIEW_TH);
        k = 1.0f - expf(-CAM_LAG * dt);
        view.cam_x += (tgt_x - view.cam_x) * k;
        view.cam_y += (tgt_y - view.cam_y) * k;

        view.clock    = (double)now / 1000.0;
        view.walk_dir = (last_act == ACT_LEFT) ? -1 : (last_act == ACT_RIGHT ? 1 : 0);
        view.airborne = e->jump_left > 0 || !tile_solid(tile_at(e, e->px, e->py + 1));

        if (toast.until > view.clock) {
            double left = toast.until - view.clock;
            view.toast   = toast.text;
            view.toast_a = (float)(left < 0.5 ? left / 0.5 : 1.0);
        } else {
            view.toast   = NULL;
            view.toast_a = 0.0f;
        }

        /* The title bar is the whole watch-mode HUD: it costs nothing in
           px_render.c, which knows nothing about tapes and should stay that
           way. Refreshed only when something in it changed -- setting a window
           title talks to the window server, and at 60 fps that would be 60
           round trips a second to rewrite a string that changes 12 times. */
        if (watching) {
            static int  shown_i = -1;
            static bool shown_p = false, shown_o = false;
            if (tape.i != shown_i || paused != shown_p || over != shown_o) {
                char t[192];
                shown_i = tape.i;
                shown_p = paused;
                shown_o = over;
                snprintf(t, sizeof t, "%s -- step %d/%d | %s | %s%s",
                         tape.label, tape.i, tape.n, action_name(last_act),
                         paused ? "PAUSED" : "playing",
                         over ? " | done" : "");
                px_set_title(ui, t);
            }
        }

        px_draw(ui, e, &view);

        /* Deadline-based rather than "sleep the remainder": SDL_Delay rounds
           up, so a per-frame remainder drifts to about 52 fps. Pinning frame
           n to epoch + n/60 s absorbs that overshoot. Under vsync the deadline
           has usually already passed and this costs nothing. */
        frames++;
        {
            uint64_t due = frame_epoch + frames * 1000ull / FPS;
            uint64_t t   = SDL_GetTicks64();
            if (t < due) SDL_Delay((Uint32)(due - t));
            else if (t > due + 250ull) { frame_epoch = t; frames = 0; }
        }
    }

    px_shutdown(ui);
    env_free(e);
    free(e);
    free(tape.act);
    return 0;
}
