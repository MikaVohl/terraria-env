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

/* A living world has no idle fixed point: mobs, spawning, cooldowns and
   regeneration advance even while the player stands still. Pause explicitly. */
static inline bool at_rest(const Env *e)
{
    (void)e;
    return false; /* v2: enemies, recovery and cooldowns keep the world alive. */
}

/* Achievements unlocked by the step just taken. Both frontends announce these;
   they differ only in where the text goes, so only the diff is shared. */
static inline uint32_t ach_gained(uint32_t before, uint32_t after)
{
    return after & ~before;
}

#endif /* FRONTEND_H */
