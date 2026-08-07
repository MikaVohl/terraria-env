/* Human frontend entry point: argument parsing, key mapping, episode loop. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static int key_to_action(int k)
{
    /* Digits index RECIPES directly; the craft actions are contiguous. */
    if (k >= '1' && k < '1' + RECIPE_COUNT) return RECIPE_FIRST_ACTION + (k - '1');

    switch (k) {
    case 'a': case KEY_LEFT:  return ACT_LEFT;
    case 'd': case KEY_RIGHT: return ACT_RIGHT;
    case 'w': case KEY_UP:    return ACT_JUMP;
    case 's': case KEY_DOWN:  return ACT_NOOP;
    case 'i': return ACT_MINE_UP;
    case 'k': return ACT_MINE_DOWN;
    case 'j': return ACT_MINE_LEFT;
    case 'l': return ACT_MINE_RIGHT;
    case 't': return ACT_PLACE_UP;
    case 'g': return ACT_PLACE_DOWN;
    case 'f': return ACT_PLACE_LEFT;
    case 'h': return ACT_PLACE_RIGHT;
    case 'e': return ACT_SELECT_NEXT;
    default:  return -1;
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
        "controls\n"
        "  a d      walk left / right        w  jump        s  wait\n"
        "  i k j l  mine up / down / left / right\n"
        "  t g f h  place up / down / left / right\n"
        "  e        cycle the selected placeable\n",
        prog, DEFAULT_MAX_STEPS, DEFAULT_TICK_MS);
    for (i = 0; i < RECIPE_COUNT; i++)
        fprintf(out, "  %d        craft %s\n", i + 1, RECIPES[i].name);
    fprintf(out,
        "  r        new world (seed + 1)\n"
        "  q        quit\n");
}

static int parse_u64(const char *s, unsigned long long *out)
{
    char *end;
    unsigned long long v;
    errno = 0;
    v = strtoull(s, &end, 10);
    if (*s == '\0' || *s == '-' || *end != '\0' || errno == ERANGE) return 0;
    *out = v;
    return 1;
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
    if (key >= 'A' && key <= 'Z') key += 'a' - 'A';
    if (key == 'q') return K_QUIT;
    if (key == 'r') return K_RESET;
    *act = key_to_action(key);
    return K_ACTION;
}

/* One tick per keypress. Deterministic under a scripted key tape, which is what
   tools/play.py replays against, so this path has to stay. */
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

/* True when an ACT_NOOP frame would change nothing but the step counter. The
   player is the only thing in this world that moves on its own, so grounded and
   not mid-jump is a genuine fixed point. */
static int at_rest(const Env *e)
{
    return e->jump_left == 0 && tile_solid(tile_at(e, e->px, e->py + 1));
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
