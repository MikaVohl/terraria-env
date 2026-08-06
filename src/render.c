/* ANSI terminal frontend: cbreak input and a single-write, flicker-free frame. */
#if defined(__APPLE__)
#  define _DARWIN_C_SOURCE 1
#else
#  define _DEFAULT_SOURCE 1
#  define _POSIX_C_SOURCE 200809L
#endif

#include <errno.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

#include "render.h"

/* ---- Terminal state ----------------------------------------------------- *
 * The only file-scope mutable state in the project. The saved termios really
 * is process-global, and the signal handlers have to be able to reach it. */

static struct termios        g_saved;
static volatile sig_atomic_t g_raw     = 0;
static volatile sig_atomic_t g_resized = 0;

/* ---- Layout ------------------------------------------------------------- */

#define VIEW_W_MAX 72
#define VIEW_H_MAX 30
#define HUD_ROWS   12
#define ACH_COL    10   /* achievement grid starts here */
#define ACH_CELL   7    /* ...with fixed-width cells, so the two rows line up */
#define MIN_COLS   40
#define MIN_ROWS   20
#define FRAME_CAP  (96 * 1024)

/* ---- Palette ------------------------------------------------------------ *
 * Every tile carries a six-step ramp indexed by light level: fg paints the
 * glyph, bg the block behind it. Step 0 is "barely lit" (near black, hue only
 * hinted at), step 5 is full daylight. Torches cap out at emit 12, so step 5
 * is reachable only by sunlight -- which is why air's top step is sky blue
 * while its lower steps stay cave grey. Ore ramps start hued so a vein still
 * glints one step before the rock around it becomes readable. */

#define RAMP_STEPS 6

typedef struct {
    unsigned char fg[RAMP_STEPS];
    unsigned char bg[RAMP_STEPS];
} Ramp;

static const Ramp TILE_RAMP[TILE_COUNT] = {
    /* AIR       */ {{233, 233, 234, 234, 235,  67}, {233, 233, 234, 234, 235,  67}},
    /* DIRT      */ {{237,  58,  94, 137, 180, 223}, {233, 233, 234,  58,  94, 137}},
    /* GRASS     */ {{237,  58,  64,  70, 107, 113}, {233, 233,  22,  22,  64,  70}},
    /* STONE     */ {{236, 239, 240,  60, 103, 146}, {233, 234, 235, 236,  60, 103}},
    /* WOOD      */ {{ 52,  88,  94, 130, 137, 179}, {232, 233,  52,  88,  94, 130}},
    /* LEAVES    */ {{236,  22,  28,  34,  40,  77}, {233, 233,  22,  22,  22,  28}},
    /* COPPER    */ {{ 58,  94, 130, 166, 172, 208}, {233, 234, 234,  58,  94, 130}},
    /* IRON      */ {{ 52,  88, 124, 131, 167, 174}, {232, 232,  52,  52,  88, 124}},
    /* TORCH     */ {{172, 208, 214, 220, 226, 227}, {234,  58,  94, 130, 166, 172}},
    /* WORKBENCH */ {{237,  58,  94, 136, 173, 180}, {233, 233, 234,  58,  94, 136}},
    /* FURNACE   */ {{237, 238,  95, 131, 138, 174}, {233, 234,  52,  88,  95, 131}},
    /* BEDROCK   */ {{234, 235, 236, 238, 240, 242}, {232, 232, 233, 234, 235, 236}},
};

#define COLOR_UNSEEN 232  /* below DARK_THRESHOLD: a flat, honest void */
#define COLOR_INK    231  /* the player, on any dark cell */
#define COLOR_INK_ON 16   /* ...and on the rare bright one */

/* HUD ink. */
#define C_RULE   "\033[38;5;238m"
#define C_TITLE  "\033[1;38;5;180m"
#define C_LABEL  "\033[38;5;242m"
#define C_TEXT   "\033[38;5;252m"
#define C_MUTE   "\033[38;5;245m"
#define C_ACCENT "\033[38;5;180m"
#define C_KEY    "\033[38;5;214m"
#define C_GOLD   "\033[1;38;5;220m"
#define C_OFF    "\033[38;5;237m"
#define C_HP     "\033[38;5;203m"
#define C_HP_LOW "\033[1;38;5;196m"
#define C_DEAD   "\033[1;38;5;196m"
#define C_TIME   "\033[1;38;5;214m"

/* Newest log line brightest, so the eye lands on it first. */
static const char *const LOG_SHADE[RENDER_LOG_LINES] = {
    "\033[38;5;252m", "\033[38;5;246m", "\033[38;5;242m", "\033[38;5;239m",
};

/* UTF-8 spelled out, so the source encoding cannot bite us. */
#define G_HEART "\xe2\x99\xa5"  /* U+2665 */
#define G_RULE  "\xe2\x94\x80"  /* U+2500 */
#define G_DOT   "\xc2\xb7"      /* U+00B7 */

static const char *const TOOL_NAME[3] = { "hand", "stone pickaxe", "copper pickaxe" };

/* Alternating key / description pairs for the bottom legend. */
static const char *const LEGEND[] = {
    "wasd", " move  ", "ikjl", " mine  ", "tgfh", " place  ",
    "e", " cycle  ", "1-6", " craft  ", "r", " reset  ", "q", " quit",
};

/* Short forms so all sixteen achievements fit two rows. Same order as ACH_NAME. */
static const char *const ACH_TAG[ACH_COUNT] = {
    "wood",  "dirt",   "stone", "place",  "bench",  "+bench", "spick", "furn",
    "+furn", "copper", "bar",   "torch",  "+torch", "cpick",  "iron",  "deep",
};

static const int CUBE_LEVEL[6] = { 0, 95, 135, 175, 215, 255 };

/* ---- Small helpers ------------------------------------------------------ */

static int light_step(int l)
{
    int s = (l - DARK_THRESHOLD) * RAMP_STEPS / (LIGHT_MAX - DARK_THRESHOLD + 1);
    if (s < 0) return 0;
    if (s >= RAMP_STEPS) return RAMP_STEPS - 1;
    return s;
}

/* Rough perceived brightness of a 256-colour index, so the player glyph can
   flip to black ink on the rare bright cell. */
static int color_luma(int c)
{
    int i, r, g, b;
    if (c >= 232) return 8 + (c - 232) * 10;
    if (c < 16)   return 60;
    i = c - 16;
    r = CUBE_LEVEL[i / 36];
    g = CUBE_LEVEL[(i / 6) % 6];
    b = CUBE_LEVEL[i % 6];
    return (r * 30 + g * 59 + b * 11) / 100;
}

static int bitcount(uint32_t v)
{
    int n = 0;
    while (v) { v &= v - 1u; n++; }
    return n;
}

static void term_size(int *cols, int *rows)
{
    struct winsize ws;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 && ws.ws_col > 0 && ws.ws_row > 0) {
        *cols = ws.ws_col;
        *rows = ws.ws_row;
    } else {
        *cols = 80;
        *rows = 24;
    }
}

/* ---- Output buffer ------------------------------------------------------ */

typedef struct {
    char  *p;
    size_t cap;
    size_t len;
} Buf;

static void bput(Buf *b, const char *s, size_t n)
{
    size_t space = b->cap - b->len;
    if (n > space) n = space;
    memcpy(b->p + b->len, s, n);
    b->len += n;
}

static void bs(Buf *b, const char *s) { bput(b, s, strlen(s)); }

static void bc(Buf *b, char c) { if (b->len < b->cap) b->p[b->len++] = c; }

static void bnum(Buf *b, int v)
{
    char t[12];
    int n = 0;
    if (v < 0) { bc(b, '-'); v = -v; }
    do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n--) bc(b, t[n]);
}

/* Park at the start of *row, blank it, drop any colour. Erasing *before* the
   text rather than after matters: a line that fills the last column leaves the
   cursor in the pending-wrap state, where a trailing EL would eat the cell we
   just painted. Absolute positioning also means we never emit a newline, so
   the frame can never scroll. */
static void bline(Buf *b, int *row)
{
    bs(b, "\033[");
    bnum(b, (*row)++);
    bs(b, ";1H\033[0m\033[K");
}

/* Emit only the channels that actually changed; a long run of identical stone
   then costs one byte per cell. Pass -1 to leave a channel alone. */
static void bcolor(Buf *b, int *cfg, int *cbg, int fg, int bg)
{
    int need_fg = (fg >= 0 && fg != *cfg);
    int need_bg = (bg >= 0 && bg != *cbg);
    if (!need_fg && !need_bg) return;
    bs(b, "\033[");
    if (need_fg) { bs(b, "38;5;"); bnum(b, fg); *cfg = fg; }
    if (need_bg) { if (need_fg) bc(b, ';'); bs(b, "48;5;"); bnum(b, bg); *cbg = bg; }
    bc(b, 'm');
}

/* ---- Column-tracked line writer ----------------------------------------- *
 * HUD text is clipped at the layout width, so a narrow terminal degrades by
 * truncating rather than wrapping (a wrap would shove the whole frame down). */

typedef struct {
    Buf *b;
    int  col;
    int  max;
} Line;

static void lesc(Line *l, const char *esc) { bs(l->b, esc); }

static void lcolor(Line *l, int fg)
{
    bs(l->b, "\033[38;5;");
    bnum(l->b, fg);
    bc(l->b, 'm');
}

static void ltext(Line *l, const char *s)
{
    while (*s && l->col < l->max) { bc(l->b, *s++); l->col++; }
}

#if defined(__GNUC__)
__attribute__((format(printf, 2, 3)))
#endif
static void lfmt(Line *l, const char *fmt, ...)
{
    char t[192];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(t, sizeof t, fmt, ap);
    va_end(ap);
    ltext(l, t);
}

/* One multi-byte glyph of known display width. */
static void lglyph(Line *l, const char *utf8, int cols)
{
    if (l->col + cols > l->max) return;
    bs(l->b, utf8);
    l->col += cols;
}

static void lrule(Line *l, int to)
{
    while (l->col < to && l->col < l->max) lglyph(l, G_RULE, 1);
}

static void lpad(Line *l, int to)
{
    while (l->col < to && l->col < l->max) { bc(l->b, ' '); l->col++; }
}

static void lstart(Line *l, Buf *b, int *row, int w)
{
    bline(b, row);
    l->b = b;
    l->col = 0;
    l->max = w;
}

/* ---- Map ---------------------------------------------------------------- */

static void draw_map(Buf *b, const Env *e, int *row, int vw, int vh)
{
    int cam_x = e->px - vw / 2;
    int cam_y = e->py - vh / 2;
    int sx, sy;

    if (cam_x > WORLD_W - vw) cam_x = WORLD_W - vw;
    if (cam_x < 0) cam_x = 0;
    if (cam_y > WORLD_H - vh) cam_y = WORLD_H - vh;
    if (cam_y < 0) cam_y = 0;

    for (sy = 0; sy < vh; sy++) {
        int wy = cam_y + sy;
        int cf = -1, cb = -1;   /* bline() reset the terminal's colour state */

        bline(b, row);
        for (sx = 0; sx < vw; sx++) {
            int wx = cam_x + sx;
            int player = (wx == e->px && wy == e->py);
            int l = e->light[wy][wx];
            const Ramp *r;
            Tile t;
            int step, bg;

            if (l < DARK_THRESHOLD && !player) {
                bcolor(b, &cf, &cb, -1, COLOR_UNSEEN);
                bc(b, ' ');
                continue;
            }

            t = (Tile)e->tiles[wy][wx];
            r = &TILE_RAMP[t];
            step = light_step(l);
            bg = r->bg[step];

            if (player) {
                if (l < DARK_THRESHOLD) bg = TILE_RAMP[TILE_AIR].bg[0];
                bs(b, "\033[1m");
                cf = -1;
                bcolor(b, &cf, &cb,
                       color_luma(bg) > 128 ? COLOR_INK_ON : COLOR_INK, bg);
                bc(b, '@');
                bs(b, "\033[0m");
                cf = -1;
                cb = -1;
            } else if (t == TILE_AIR) {
                bcolor(b, &cf, &cb, -1, bg);
                bc(b, ' ');
            } else {
                bcolor(b, &cf, &cb, r->fg[step], bg);
                bc(b, TILE_INFO[t].glyph);
            }
        }
    }
}

/* ---- HUD ---------------------------------------------------------------- */

static void draw_hud(Buf *b, const Env *e, int *row, int w, int wide)
{
    Line L;
    int i, sel, tier, cnt;
    Item held;
    Tile held_tile;

    sel  = e->selected < PLACEABLE_COUNT ? e->selected : 0;
    held = PLACEABLES[sel].item;
    held_tile = PLACEABLES[sel].tile;
    cnt  = e->inv[held];
    tier = e->tool_tier < 3 ? e->tool_tier : 2;

    /* rule + identity */
    lstart(&L, b, row, w);
    lesc(&L, C_RULE);  lrule(&L, 2);
    lesc(&L, C_TITLE); ltext(&L, " terraria-lite ");
    lesc(&L, C_LABEL); lfmt(&L, " seed %llu ", (unsigned long long)e->seed);
    lesc(&L, C_RULE);  lrule(&L, w);

    /* health, tool tier, held stack */
    lstart(&L, b, row, w);
    lesc(&L, C_LABEL); ltext(&L, "hp ");
    for (i = 0; i < MAX_HEALTH; i++) {
        lesc(&L, i < e->health ? (e->health <= 3 ? C_HP_LOW : C_HP) : C_OFF);
        lglyph(&L, G_HEART, 1);
    }
    lesc(&L, C_TEXT);  lfmt(&L, " %d/%d", e->health, MAX_HEALTH);
    lesc(&L, C_LABEL); ltext(&L, "  tool ");
    lesc(&L, C_TEXT);  ltext(&L, TOOL_NAME[tier]);
    lesc(&L, C_LABEL); ltext(&L, "  hold ");
    lesc(&L, C_OFF);   ltext(&L, "[");
    lcolor(&L, TILE_RAMP[held_tile].fg[RAMP_STEPS - 1]);
    { char g[2]; g[0] = TILE_INFO[held_tile].glyph; g[1] = '\0'; ltext(&L, g); }
    lesc(&L, C_OFF);   ltext(&L, "] ");
    lesc(&L, cnt > 0 ? C_TEXT : C_OFF);
    lfmt(&L, "%s x%d", ITEM_NAME[held], cnt);

    /* depth, progress */
    lstart(&L, b, row, w);
    lesc(&L, C_LABEL); ltext(&L, "depth ");
    lesc(&L, e->py >= DEEP_Y ? C_KEY : C_TEXT);
    lfmt(&L, "%d", e->py);
    lesc(&L, C_LABEL); ltext(&L, "  step ");
    lesc(&L, C_TEXT);  lfmt(&L, "%d/%d", e->steps, e->max_steps);
    lesc(&L, C_LABEL); ltext(&L, "  return ");
    lesc(&L, C_TEXT);  lfmt(&L, "%.2f", (double)e->ep_return);

    /* Inventory is the one genuinely unbounded row, so it gets the whole
       window rather than the map width. */
    lstart(&L, b, row, wide);
    lesc(&L, C_LABEL); ltext(&L, "inv");
    {
        int any = 0;
        for (i = 0; i < ITEM_COUNT; i++) {
            if (e->inv[i] <= 0) continue;
            lesc(&L, C_MUTE);   lfmt(&L, "  %s ", ITEM_NAME[i]);
            lesc(&L, C_ACCENT); lfmt(&L, "%d", e->inv[i]);
            any = 1;
        }
        if (!any) { lesc(&L, C_OFF); ltext(&L, "  empty"); }
    }

    /* craft menu, straight out of the recipe table */
    lstart(&L, b, row, w);
    for (i = 0; i < RECIPE_COUNT; i++) {
        if (i) ltext(&L, " ");
        lesc(&L, C_KEY);  lfmt(&L, "%d", i + 1);
        lesc(&L, C_MUTE); lfmt(&L, " %s", RECIPES[i].name);
    }

    /* achievements: this is the score, so it gets a real grid */
    for (i = 0; i < 2; i++) {
        int j;
        lstart(&L, b, row, w);
        if (i == 0) {
            lesc(&L, C_LABEL); ltext(&L, "ach ");
            lesc(&L, C_GOLD);  lfmt(&L, "%d", bitcount(e->achievements));
            lesc(&L, C_LABEL); lfmt(&L, "/%d", ACH_COUNT);
        }
        lpad(&L, ACH_COL);
        for (j = 0; j < 8 && i * 8 + j < ACH_COUNT; j++) {
            int a = i * 8 + j;
            lesc(&L, has_ach(e, a) ? C_GOLD : C_OFF);
            ltext(&L, ACH_TAG[a]);
            lpad(&L, ACH_COL + (j + 1) * ACH_CELL);
        }
    }
}

static void draw_log(Buf *b, int *row, const char *log[], int nlog, int w)
{
    Line L;
    int i;

    for (i = 0; i < RENDER_LOG_LINES; i++) {
        int idx = nlog - RENDER_LOG_LINES + i;
        lstart(&L, b, row, w);
        if (idx >= 0 && idx < nlog && log[idx] && log[idx][0]) {
            const char *s = log[idx];
            lesc(&L, C_OFF);
            lglyph(&L, G_DOT, 1);
            ltext(&L, " ");
            lesc(&L, strncmp(s, "unlocked", 8) == 0
                     ? C_GOLD : LOG_SHADE[RENDER_LOG_LINES - 1 - i]);
            ltext(&L, s);
        }
    }
}

static void draw_summary(Buf *b, const Env *e, int *row, int w)
{
    Line L;
    int died = e->terminated;

    lstart(&L, b, row, w);
    lesc(&L, died ? C_DEAD : C_TIME);
    lrule(&L, w);

    lstart(&L, b, row, w);
    lesc(&L, C_TITLE); ltext(&L, "episode over  ");
    lesc(&L, died ? C_DEAD : C_TIME);
    ltext(&L, died ? "you died" : "out of time");

    lstart(&L, b, row, w);
    lesc(&L, C_LABEL); ltext(&L, "steps ");
    lesc(&L, C_TEXT);  lfmt(&L, "%d", e->steps);
    lesc(&L, C_LABEL); ltext(&L, "   achievements ");
    lesc(&L, C_GOLD);  lfmt(&L, "%d", bitcount(e->achievements));
    lesc(&L, C_LABEL); lfmt(&L, "/%d", ACH_COUNT);
    lesc(&L, C_LABEL); ltext(&L, "   return ");
    lesc(&L, C_TEXT);  lfmt(&L, "%.2f", (double)e->ep_return);

    lstart(&L, b, row, w);
    lesc(&L, C_KEY);  ltext(&L, "r");
    lesc(&L, C_MUTE); ltext(&L, " new world   ");
    lesc(&L, C_KEY);  ltext(&L, "q");
    lesc(&L, C_MUTE); ltext(&L, " quit");
}

static void draw_legend(Buf *b, int *row, int w)
{
    Line L;
    size_t i;

    lstart(&L, b, row, w);
    for (i = 0; i < sizeof LEGEND / sizeof LEGEND[0]; i++) {
        lesc(&L, (i % 2) ? C_LABEL : C_KEY);
        ltext(&L, LEGEND[i]);
    }
}

static size_t compose(char *out, size_t cap, const Env *e,
                      const char *log[], int nlog, int over)
{
    Buf b;
    int cols, rows, vw, vh, row = 1;

    b.p = out;
    b.cap = cap;
    b.len = 0;

    term_size(&cols, &rows);
    bs(&b, "\033[H");

    if (cols < MIN_COLS || rows < MIN_ROWS) {
        bline(&b, &row);
        bs(&b, "terraria-lite wants a window of at least ");
        bnum(&b, MIN_COLS); bc(&b, 'x'); bnum(&b, MIN_ROWS);
        bs(&b, "; this one is ");
        bnum(&b, cols); bc(&b, 'x'); bnum(&b, rows);
        bs(&b, ".");
        bs(&b, "\033[0m\033[J");
        return b.len;
    }

    vw = cols < VIEW_W_MAX ? cols : VIEW_W_MAX;
    vh = rows - HUD_ROWS;
    if (vh > VIEW_H_MAX) vh = VIEW_H_MAX;
    if (vw > WORLD_W) vw = WORLD_W;
    if (vh > WORLD_H) vh = WORLD_H;

    draw_map(&b, e, &row, vw, vh);
    draw_hud(&b, e, &row, vw, cols);
    if (over) draw_summary(&b, e, &row, vw);
    else      draw_log(&b, &row, log, nlog, vw);
    draw_legend(&b, &row, vw);

    bs(&b, "\033[0m");
    if (row <= rows) {          /* only if there is anything left below us */
        bs(&b, "\033[");
        bnum(&b, row);
        bs(&b, ";1H\033[J");
    }
    return b.len;
}

static void present(const Env *e, const char *log[], int nlog, int over)
{
    char frame[FRAME_CAP];
    size_t n = compose(frame, sizeof frame, e, log, nlog, over);
    size_t w = fwrite(frame, 1, n, stdout);
    (void)w;
    fflush(stdout);
}

void render_frame(const Env *e, const char *log[], int nlog)
{
    present(e, log, nlog, 0);
}

void render_gameover(const Env *e)
{
    present(e, NULL, 0, 1);
}

/* ---- Terminal mode ------------------------------------------------------ */

/* Async-signal-safe: tcsetattr and write only. */
static void restore_terminal(void)
{
    const char tail[] = "\033[0m\033[?25h\n";
    ssize_t w;
    if (!g_raw) return;
    g_raw = 0;
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &g_saved);
    w = write(STDOUT_FILENO, tail, sizeof tail - 1);
    (void)w;
}

static void on_fatal(int sig)
{
    restore_terminal();
    signal(sig, SIG_DFL);
    raise(sig);
}

static void on_winch(int sig)
{
    (void)sig;
    g_resized = 1;
}

static void install(int sig, void (*fn)(int))
{
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = fn;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;   /* deliberately no SA_RESTART: read() must see EINTR */
    sigaction(sig, &sa, NULL);
}

void render_init(void)
{
    struct termios raw;

    if (tcgetattr(STDIN_FILENO, &g_saved) != 0) return;
    raw = g_saved;
    raw.c_lflag &= (tcflag_t)~(ICANON | ECHO);  /* ISIG stays on: Ctrl-C signals */
    raw.c_cc[VMIN]  = 1;
    raw.c_cc[VTIME] = 0;
    if (tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw) != 0) return;

    g_raw = 1;
    atexit(restore_terminal);
    install(SIGINT,   on_fatal);
    install(SIGTERM,  on_fatal);
    install(SIGQUIT,  on_fatal);
    install(SIGHUP,   on_fatal);
    install(SIGSEGV,  on_fatal);
    install(SIGABRT,  on_fatal);
    install(SIGWINCH, on_winch);

    fputs("\033[?25l\033[2J\033[H", stdout);
    fflush(stdout);
}

void render_shutdown(void)
{
    fflush(stdout);
    restore_terminal();
}

/* ---- Input -------------------------------------------------------------- */

/* tenths == 0 blocks; otherwise waits at most tenths*100ms for a single byte. */
static int read_byte(int tenths)
{
    unsigned char c;
    ssize_t n;

    if (tenths > 0) {
        struct termios cur, tmp;
        if (!g_raw || tcgetattr(STDIN_FILENO, &cur) != 0) return KEY_EOF;
        tmp = cur;
        tmp.c_cc[VMIN]  = 0;
        tmp.c_cc[VTIME] = (cc_t)tenths;
        tcsetattr(STDIN_FILENO, TCSANOW, &tmp);
        n = read(STDIN_FILENO, &c, 1);
        tcsetattr(STDIN_FILENO, TCSANOW, &cur);
        return n == 1 ? (int)c : KEY_EOF;
    }

    for (;;) {
        n = read(STDIN_FILENO, &c, 1);
        if (n == 1) return (int)c;
        if (n < 0 && errno == EINTR) {
            if (g_resized) { g_resized = 0; return KEY_RESIZE; }
            continue;
        }
        return KEY_EOF;
    }
}

int render_getkey(void)
{
    int c = read_byte(0);
    int a, b;

    if (c != 0x1B) return c;

    a = read_byte(1);
    if (a != '[' && a != 'O') return 0x1B;
    b = read_byte(1);
    switch (b) {
    case 'A': return KEY_UP;
    case 'B': return KEY_DOWN;
    case 'C': return KEY_RIGHT;
    case 'D': return KEY_LEFT;
    default:  return 0x1B;
    }
}
