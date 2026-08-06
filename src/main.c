/* Human frontend entry point: argument parsing, key mapping, episode loop. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "render.h"

#define LOG_COLS 96

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
        "usage: %s [--seed N] [--steps N] [--help]\n"
        "\n"
        "  --seed N   world seed (default 1)\n"
        "  --steps N  episode step limit (default %d)\n"
        "  --help     this message\n"
        "\n"
        "controls\n"
        "  a d      walk left / right        w  jump        s  wait\n"
        "  i k j l  mine up / down / left / right\n"
        "  t g f h  place up / down / left / right\n"
        "  e        cycle the selected placeable\n",
        prog, DEFAULT_MAX_STEPS);
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

int main(int argc, char **argv)
{
    const char *prog = argc > 0 && argv[0] ? argv[0] : "terraria-lite";
    unsigned long long seed = 1;
    unsigned long long steps = DEFAULT_MAX_STEPS;
    EnvConfig cfg;
    Env *e;
    Log lg;
    int i;

    for (i = 1; i < argc; i++) {
        const char *a = argv[i];
        unsigned long long *slot = NULL;

        if (!strcmp(a, "--help") || !strcmp(a, "-h")) { usage(stdout, prog); return 0; }
        if (!strcmp(a, "--seed"))  slot = &seed;
        if (!strcmp(a, "--steps")) slot = &steps;
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

    for (;;) {
        const char *view[RENDER_LOG_LINES];
        int nlog = log_view(&lg, view);
        int over = e->terminated || e->truncated;
        int key, act, a;
        uint32_t before, gained;

        if (over) render_gameover(e);
        else      render_frame(e, view, nlog);

        key = render_getkey();
        if (key == KEY_EOF) break;
        if (key == KEY_RESIZE) continue;
        if (key >= 'A' && key <= 'Z') key += 'a' - 'A';
        if (key == 'q') break;

        if (key == 'r') {
            char line[LOG_COLS];
            seed += 1;
            env_reset(e, (uint64_t)seed);
            log_reset(&lg);
            snprintf(line, sizeof line, "new world, seed %llu", seed);
            log_push(&lg, line);
            continue;
        }
        if (over) continue;  /* the summary screen only listens for r and q */

        act = key_to_action(key);
        if (act < 0) continue;

        before = e->achievements;
        env_step(e, act);

        if (e->msg[0]) log_push(&lg, e->msg);
        gained = e->achievements & ~before;
        for (a = 0; a < ACH_COUNT; a++) {
            if ((gained >> a) & 1u) {
                char line[LOG_COLS];
                snprintf(line, sizeof line, "unlocked: %s", ACH_NAME[a]);
                log_push(&lg, line);
            }
        }
    }

    render_shutdown();
    env_free(e);
    free(e);
    return 0;
}
