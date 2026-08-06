/* Terminal frontend: raw-mode keyboard input and buffered ANSI rendering. */
#ifndef RENDER_H
#define RENDER_H

#include "env.h"

/* Number of log lines render_frame() draws; callers size their ring to match. */
#define RENDER_LOG_LINES 4

/* render_getkey() returns a plain byte, or one of these synthetic codes. */
#define KEY_EOF    (-1)
#define KEY_UP     0x100
#define KEY_DOWN   0x101
#define KEY_RIGHT  0x102
#define KEY_LEFT   0x103
#define KEY_RESIZE 0x104

void render_init(void);      /* cbreak mode, hide cursor, arm atexit + signal restore */
void render_shutdown(void);  /* restore termios and cursor; idempotent */
int  render_getkey(void);    /* blocking single keypress */

void render_frame(const Env *e, const char *log[], int nlog);
void render_gameover(const Env *e);

#endif /* RENDER_H */
