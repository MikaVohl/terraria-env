/* The few things both frontends need and neither owns.
 *
 * Deliberately small. It does NOT hold the frame loop or the input queue: SDL
 * delivers real key-up events and a terminal only has OS key repeat, so the
 * two loops differ for a reason and the pixel queue has no need for the
 * repeat-collapsing the terminal one depends on. Folding them together would
 * trade a real difference for a fake abstraction.
 *
 * What is here is the part where drifting apart would be a bug rather than a
 * style difference.
 */
#ifndef FRONTEND_H
#define FRONTEND_H

#include <errno.h>
#include <stdlib.h>

#include "env.h"

/* Strict non-negative integer, no suffixes, no partial parses. Returns 0 on
   anything malformed so callers can report the offending argument. */
static inline int parse_u64(const char *s, unsigned long long *out)
{
    char *end;
    unsigned long long v;

    errno = 0;
    v = strtoull(s, &end, 10);
    if (*s == '\0' || *s == '-' || *end != '\0' || errno == ERANGE) return 0;
    *out = v;
    return 1;
}

/* True when an ACT_NOOP tick would change nothing but the step counter. The
   player is the only thing in this world that moves on its own, so grounded
   and not mid-jump is a genuine fixed point.

   This is a game rule wearing frontend clothing, which is exactly why it is
   shared: both frontends skip the tick when it holds, and 3000 no-ops at 80 ms
   is four minutes of standing still into a truncation. If the two copies ever
   disagreed, one frontend would silently spend a budget the other did not. */
static inline bool at_rest(const Env *e)
{
    return e->jump_left == 0 && tile_solid(tile_at(e, e->px, e->py + 1));
}

/* Achievements unlocked by the step just taken. Both frontends announce these;
   they differ only in where the text goes, so only the diff is shared. */
static inline uint32_t ach_gained(uint32_t before, uint32_t after)
{
    return after & ~before;
}

#endif /* FRONTEND_H */
