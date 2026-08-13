/* Human frontend entry point: argument parsing, key mapping, episode loop. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "frontend.h"
#include "keymap.h"
#include "render.h"

#define LOG_COLS     96
#define DEFAULT_TICK_MS 80   /* 12.5 tiles/s walk speed at one tile per tick */
#define MIN_TICK_MS  10
#define MAX_TICK_MS  1000

/* Rolling window of the last few lines shown in the log pane. */
typedef struct {
    char text[RENDER_LOG_LINES][LOG_COLS];
    int  count;
} Log;

static void log_reset(Log *lg)
{
    memset(lg, 0, sizeof *lg);
}

static void log_push(Log *lg, const char *s)
{
    int i;
    if (!s || !*s) return;
    for (i = 0; i + 1 < RENDER_LOG_LINES; i++)
        memcpy(lg->text[i], lg->text[i + 1], LOG_COLS);
    snprintf(lg->text[RENDER_LOG_LINES - 1], LOG_COLS, "%s", s);
    if (lg->count < RENDER_LOG_LINES) lg->count++;
}

/* Newest last, so the pane fills from the bottom. */
static int log_view(const Log *lg, const char *out[RENDER_LOG_LINES])
{
    int i;
    for (i = 0; i < RENDER_LOG_LINES; i++)
        out[i] = (i < lg->count) ? lg->text[i + RENDER_LOG_LINES - lg->count] : NULL;
    return lg->count;
}

/* Arrows are a terminal-only alias; everything printable comes from keymap.h,
   which the pixel frontend and the selftest's replay tapes share. */
static int key_to_action(int k)
{
    int a = kb_action(k);
    if (a >= 0) return a;

    switch (k) {
    case KEY_LEFT:  return ACT_LEFT;
    case KEY_RIGHT: return ACT_RIGHT;
    case KEY_UP:    return ACT_JUMP;
    case KEY_DOWN:  return ACT_NOOP;
    default:        return -1;
    }
}

static void usage(FILE *out, const char *prog)
{
    int i;
    fprintf(out,
        "terraria-lite -- a small terminal Terraria\n"
        "\n"
        "usage: %s [--seed N] [--steps N] [--tick-ms N] [--lockstep] [--help]\n"
        "\n"
        "  --seed N     world seed (default 1)\n"
        "  --steps N    episode step limit (default %d)\n"
        "  --tick-ms N  real-time frame length in ms (default %d)\n"
        "  --lockstep   advance one tick per keypress instead of on a clock\n"
        "  --help       this message\n"
        "\n"
        "The engine is frame-by-frame either way -- one env_step per tick, one\n"
        "action per tick. Real time only changes who supplies the clock: idle\n"
        "frames become no-ops, so falls and jumps play out on their own.\n"
        "\n"
        "You are two tiles tall: the head is one row above the feet, and the\n"
        "position the HUD calls depth is the feet. Ten cells surround the body\n"
        "and every one of them can be mined or built into.\n"
        "\n"
        "controls\n"
        "  a d   walk left / right     w  jump     s  wait\n"
        "  e     cycle the selected placeable\n"
        "  r     new world (seed + 1)  q  quit\n"
        "\n"
        "reach -- lower case mines the cell, shift places into it\n"
        "\n"
        "        dx=-1   dx=0   dx=+1\n"
        "  dy=-2   y/Y    u/U    i/I     above the head\n"
        "  dy=-1   h/H   [head]  k/K\n"
        "  dy= 0   n/N   [feet]  m/M\n"
        "  dy=+1   ,/<    ./>    //?     below the feet\n"
        "\n"
        "Mining straight down (.) is a controlled descent and costs no fall\n"
        "damage. Placing into a down-diagonal (< or ?) bridges without losing\n"
        "altitude, and placing under your own feet (>) pillars upward.\n"
        "\n"
        "crafting -- the station must be within %d tiles of your feet\n",
        prog, DEFAULT_MAX_STEPS, DEFAULT_TICK_MS, STATION_RANGE);
    for (i = 0; i < RECIPE_COUNT; i++) {
        Tile st = RECIPES[i].station;
        fprintf(out, "  %c     %-12s %s\n", KB_CRAFT[i], RECIPES[i].name,
                st == TILE_AIR ? "anywhere" : TILE_INFO[st].name);
    }
}

/* Actions banked between two ticks. Bounded, and a repeat of whatever is
   already at the tail is dropped: terminal key repeat outruns the tick rate and
   there is no key-up event, so without the collapse a held key would bank
   several ticks of movement that keep firing after you let go. Two *different*
   keys pressed inside one frame both survive, which is what precision wants. */
#define QCAP 4

typedef struct {
    int act[QCAP];
    int head, n;
} Queue;

static void q_push(Queue *q, int act)
{
    if (q->n > 0 && q->act[(q->head + q->n - 1) % QCAP] == act) return;
    if (q->n == QCAP) return;
    q->act[(q->head + q->n) % QCAP] = act;
    q->n++;
}

static int q_pop(Queue *q)
{
    int act;
    if (q->n == 0) return ACT_NOOP;
    act = q->act[q->head];
    q->head = (q->head + 1) % QCAP;
    q->n--;
    return act;
}

/* One env_step plus the log bookkeeping that belongs with it. */
static void apply(Env *e, Log *lg, int act)
{
    uint32_t before = e->achievements, gained;
    int a;

    env_step(e, act);

    if (e->msg[0]) log_push(lg, e->msg);
    gained = e->achievements & ~before;
    for (a = 0; a < ACH_COUNT; a++) {
        if ((gained >> a) & 1u) {
            char line[LOG_COLS];
            snprintf(line, sizeof line, "unlocked: %s", ACH_NAME[a]);
            log_push(lg, line);
        }
    }
}

static void new_world(Env *e, Log *lg, unsigned long long *seed)
{
    char line[LOG_COLS];
    *seed += 1;
    env_reset(e, (uint64_t)*seed);
    log_reset(lg);
    snprintf(line, sizeof line, "new world, seed %llu", *seed);
    log_push(lg, line);
}

static void draw(const Env *e, const Log *lg)
{
    const char *view[RENDER_LOG_LINES];
    int nlog = log_view(lg, view);
    if (e->terminated || e->truncated) render_gameover(e);
    else                               render_frame(e, view, nlog);
}

/* Verdicts for keys that mean the same thing in either loop. */
enum { K_ACTION = 0, K_QUIT, K_RESET, K_REPAINT };

/* Classify a keypress and, when it is a game action, hand it back in *act
   (-1 if the key is unbound). */
static int classify(int key, int *act)
{
    *act = -1;
    if (key == KEY_EOF)    return K_QUIT;
    if (key == KEY_RESIZE) return K_REPAINT;

    /* Place keys are the shifted letters, so they must be looked up before
       the fold below -- which exists only so a stray Q or R still quits or
       resets -- destroys the shift. */
    *act = key_to_action(key);
    if (*act >= 0) return K_ACTION;

    if (key >= 'A' && key <= 'Z') key += 'a' - 'A';
    if (key == 'q') return K_QUIT;
    if (key == 'r') return K_RESET;
    *act = key_to_action(key);
    return K_ACTION;
}

/* One tick per keypress: the world only moves when you tell it to. Kept for
   stepping through physics by hand and for replaying a `selftest --record`
   tape, both of which want the clock out of the way. */
static void play_lockstep(Env *e, Log *lg, unsigned long long *seed)
{
    for (;;) {
        int over, act, verdict;

        draw(e, lg);
        over = e->terminated || e->truncated;

        verdict = classify(render_getkey(), &act);
        if (verdict == K_QUIT)  return;
        if (verdict == K_RESET) { new_world(e, lg, seed); continue; }
        if (verdict != K_ACTION) continue;
        if (over) continue;  /* the summary screen only listens for r and q */
        if (act < 0) continue;

        apply(e, lg, act);
    }
}

/* One tick per `tick_ms`, whether or not you pressed anything: an empty frame
   steps ACT_NOOP, so gravity, jump arcs and falls resolve on the clock instead
   of waiting on the next keystroke. The engine is untouched -- still exactly
   one env_step per tick. Input latency is at most one frame. */
static void play_realtime(Env *e, Log *lg, unsigned long long *seed, int tick_ms)
{
    Queue q;
    uint64_t next;

    memset(&q, 0, sizeof q);
    next = render_now_ms() + (uint64_t)tick_ms;

    for (;;) {
        int over, act, verdict;

        draw(e, lg);
        over = e->terminated || e->truncated;

        /* Two states the clock has nothing to say about: a finished episode,
           and a world at a fixed point with nothing queued. Ticking ACT_NOOP
           through those would change only `steps`, and 3000 of them at 80ms is
           four minutes of standing still into a truncation. Block instead.
           `next` is left alone, so the tick rate still caps how fast a held
           key can act. */
        if (over || (q.n == 0 && at_rest(e))) {
            verdict = classify(render_getkey(), &act);
            if (verdict == K_QUIT)  return;
            if (verdict == K_RESET) { new_world(e, lg, seed); memset(&q, 0, sizeof q); }
            else if (!over && act >= 0) q_push(&q, act);
            continue;
        }

        /* Otherwise collect whatever arrives before the frame is due. */
        for (;;) {
            uint64_t now = render_now_ms();
            int key;

            if (now >= next) break;
            key = render_getkey_timeout((int)(next - now));
            if (key == KEY_NONE) break;      /* the frame came due first */

            verdict = classify(key, &act);
            if (verdict == K_QUIT)    return;
            if (verdict == K_REPAINT) break;
            if (verdict == K_RESET) {
                new_world(e, lg, seed);
                memset(&q, 0, sizeof q);
                break;
            }
            if (act >= 0) q_push(&q, act);
        }

        /* Woken by a resize or a reset rather than by the clock: repaint only. */
        if (render_now_ms() < next) continue;

        apply(e, lg, q_pop(&q));
        next = render_now_ms() + (uint64_t)tick_ms;
    }
}

int main(int argc, char **argv)
{
    const char *prog = argc > 0 && argv[0] ? argv[0] : "terraria-lite";
    unsigned long long seed = 1;
    unsigned long long steps = DEFAULT_MAX_STEPS;
    unsigned long long tick = DEFAULT_TICK_MS;
    int lockstep = 0;
    EnvConfig cfg;
    Env *e;
    Log lg;
    int i;

    for (i = 1; i < argc; i++) {
        const char *a = argv[i];
        unsigned long long *slot = NULL;

        if (!strcmp(a, "--help") || !strcmp(a, "-h")) { usage(stdout, prog); return 0; }
        if (!strcmp(a, "--lockstep")) { lockstep = 1; continue; }
        if (!strcmp(a, "--seed"))     slot = &seed;
        if (!strcmp(a, "--steps"))    slot = &steps;
        if (!strcmp(a, "--tick-ms"))  slot = &tick;
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

    e = calloc(1, sizeof *e);  /* ~25 KB: too big for a comfortable stack frame */
    if (!e) {
        fprintf(stderr, "%s: out of memory\n", prog);
        return 1;
    }

    cfg.max_steps = (int)steps;
    env_init(e, cfg);
    env_reset(e, (uint64_t)seed);

    log_reset(&lg);
    log_push(&lg, "chop a tree for wood, then craft a workbench");

    render_init();
    if (lockstep) play_lockstep(e, &lg, &seed);
    else          play_realtime(e, &lg, &seed, (int)tick);
    render_shutdown();

    env_free(e);
    free(e);
    return 0;
}
