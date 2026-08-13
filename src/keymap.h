/* Keyboard bindings, in one place.
 *
 * These lived in four: main.c owned the tables, render.c kept its own copy of
 * the craft row to label the HUD, px_main.c re-spelled the reach keys as a
 * switch over SDL keycodes, and selftest.c hand-aligned a 36-entry
 * action->key array for its replay tapes. Nothing made them agree; a whole
 * PTY-and-VT100 test harness existed largely to notice when they stopped.
 *
 * SDL keycodes equal their ASCII character for every printable key, so the
 * pixel frontend shares these tables directly. It reads shift as a modifier
 * rather than as a shifted character, which is the same binding seen from the
 * other side.
 */
#ifndef KEYMAP_H
#define KEYMAP_H

#include <string.h>

#include "env.h"

/* The mine keys sit on the keyboard the way the ten reach targets sit around
   the body: yui above the head, hk beside it, nm beside the feet, ,./ below --
   three rows of three with the body punched out of the middle column. Place is
   the same key with shift held, so the two halves of an action never need
   separate muscle memory. Both are in REACH_* order. */
#define KB_MINE  "yuihknm,./"
#define KB_PLACE "YUIHKNM<>?"

/* Eleven recipes outgrew the digit row, so 0 and - continue it. */
#define KB_CRAFT "1234567890-"

#define KB_LEFT   'a'
#define KB_RIGHT  'd'
#define KB_JUMP   'w'
#define KB_WAIT   's'
#define KB_SELECT 'e'

_Static_assert(sizeof KB_MINE  == REACH_COUNT + 1,  "a key per reach target");
_Static_assert(sizeof KB_PLACE == REACH_COUNT + 1,  "a key per reach target");
_Static_assert(sizeof KB_CRAFT == RECIPE_COUNT + 1, "a key per recipe");

/* Position of k in a NUL-terminated key table, or -1. The range guard keeps a
   synthetic key code (arrows, resize) from matching the terminator. */
static inline int kb_slot(const char *table, int k)
{
    const char *p = (k > 0 && k <= 0xFF) ? strchr(table, k) : NULL;
    return p ? (int)(p - table) : -1;
}

/* Printable key -> Action, or -1. Frontends layer their own aliases on top;
   the terminal maps the arrow keys, the pixel one folds shift into KB_MINE. */
static inline int kb_action(int k)
{
    int i;

    if ((i = kb_slot(KB_MINE,  k)) >= 0) return ACT_MINE_FIRST  + i;
    if ((i = kb_slot(KB_PLACE, k)) >= 0) return ACT_PLACE_FIRST + i;
    if ((i = kb_slot(KB_CRAFT, k)) >= 0) return RECIPE_FIRST_ACTION + i;

    switch (k) {
    case KB_LEFT:   return ACT_LEFT;
    case KB_RIGHT:  return ACT_RIGHT;
    case KB_JUMP:   return ACT_JUMP;
    case KB_WAIT:   return ACT_NOOP;
    case KB_SELECT: return ACT_SELECT_NEXT;
    default:        return -1;
    }
}

/* Action -> the key that produces it, or 0 if it has no binding. The scripted
   expert records replay tapes with this, so kb_action() has to invert it for
   every action -- test_keymap() in the selftest is what holds that. */
static inline char kb_key(int a)
{
    if (a >= ACT_MINE_FIRST  && a < ACT_MINE_FIRST  + REACH_COUNT)
        return KB_MINE[a - ACT_MINE_FIRST];
    if (a >= ACT_PLACE_FIRST && a < ACT_PLACE_FIRST + REACH_COUNT)
        return KB_PLACE[a - ACT_PLACE_FIRST];
    if (a >= RECIPE_FIRST_ACTION && a < RECIPE_FIRST_ACTION + RECIPE_COUNT)
        return KB_CRAFT[a - RECIPE_FIRST_ACTION];

    switch (a) {
    case ACT_LEFT:        return KB_LEFT;
    case ACT_RIGHT:       return KB_RIGHT;
    case ACT_JUMP:        return KB_JUMP;
    case ACT_NOOP:        return KB_WAIT;
    case ACT_SELECT_NEXT: return KB_SELECT;
    default:              return 0;
    }
}

#endif /* KEYMAP_H */
