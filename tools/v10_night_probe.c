/* B2 surface-night probe for v10 (DECISIONS.md B2, B15): a scripted fighter
   stands at the spawn from dusk through one full night (real HP, natural
   regen), 64 validation worlds (seeds 23000001+), three gear levels:
   copper shortsword / no armor, wooden sword + wood breastplate, iron sword +
   iron chainmail. Policies on the nearest mob within 6 cells (Manhattan):
     horizontal  turn toward it (one step), then `attack` (V10SurfaceBug's probe)
     turn        (AIM_ATTACK) `attack` or `attack back` toward its side: the
                 turn and the attack in one step, no vertical aim
     aimed       (AIM_ATTACK) the attack aimed at it: the nearest of the 8
                 directions from the body centre to the mob's box centre,
                 relative to the facing (the attack turns by itself)
   sim.c / mobs.c / boss.c are included for player_fx and mob_rect, so build
   it as one unit (knobs as for the library):

     V=variants/v10; cc -std=c11 -O2 -I$V/include -I$V/src tools/v10_night_probe.c \
        $V/src/{worldgen,light,obs}.c -o /tmp/v10-night -lm && /tmp/v10-night 64 */
#include "sim.c"
#include "mobs.c"
#include "boss.c"

static int mask_of(const Env *e, int a) { uint8_t m[ACT_COUNT]; env_action_mask(e, m); return m[a]; }

static int horizontal(const Env *e, const Mob *m) {
    int dx = m->x - e->px, dir = dx >= 1 ? 1 : -1;
    if (dx == 0 || dx == 1) dir = e->facing;
    if (dir != e->facing) return dir > 0 ? ACT_RIGHT : ACT_LEFT;
    return mask_of(e, ACT_ATTACK) ? ACT_ATTACK : ACT_NOOP;
}

#if AIM_ATTACK
/* vertical = 0: only `attack` / `attack back` toward the mob's side (the
   turn and the attack in one step, no up/down aim). */
static int aimed(const Env *e, const Mob *m, int vertical) {
    fix_t mx, my; int mw, mh; mob_rect(m, &mx, &my, &mw, &mh);
    long dx = (long)((mx + mw * FIX_ONE / 2) - (player_fx(e) + PLAYER_PX_W * FIX_ONE / 2)) >> 16;
    long dy = (long)((my + mh * FIX_ONE / 2) - (player_fy(e) + PLAYER_PX_H * FIX_ONE / 2)) >> 16;
    long adx = labs(dx), ady = labs(dy);
    int sx = (dx > 0) - (dx < 0), sy = (dy > 0) - (dy < 0);
    if (!vertical) sy = 0;
    else if (70 * ady < 29 * adx) sy = 0;     /* within 22.5 degrees of horizontal */
    else if (70 * adx < 29 * ady) sx = 0;     /* ... of vertical */
    static const int AIM[3][3] = {            /* [forward + 1][down + 1] */
        {ACT_ATTACK_UP_BACK, ACT_ATTACK_BACK, ACT_ATTACK_DOWN_BACK},
        {ACT_ATTACK_UP, ACT_ATTACK, ACT_ATTACK_DOWN},
        {ACT_ATTACK_UP_FORWARD, ACT_ATTACK, ACT_ATTACK_DOWN_FORWARD}};
    int a = AIM[sx * e->facing + 1][sy + 1];
    return mask_of(e, a) ? a : ACT_NOOP;
}
#endif

int main(int argc, char **argv) {
    int worlds = argc > 1 ? atoi(argv[1]) : 64;
    static Env env; Env *e = &env;
    env_init(e, (EnvConfig){100000});
    const int weapons[3] = {0, 1, 3}, armors[3] = {0, 1, 2};
    printf("v10 night probe (FID_MOBS=%d FID_COMBAT=%d AIM_ATTACK=%d), %d worlds\n", FID_MOBS, FID_COMBAT, AIM_ATTACK, worlds);
    for (int pol = 0; pol < 1 + 2 * AIM_ATTACK; pol++)
    for (int g = 0; g < 3; g++) {
        int deaths = 0, eyek = 0, zk = 0, lens = 0; long hp = 0;
        for (int w = 0; w < worlds; w++) {
            env_reset(e, 23000001 + (uint64_t)w);
            e->inv[WEAPON_ITEM[weapons[g]]] = 1; e->weapon = weapons[g]; e->armor = armors[g];
            e->steps = DAY_STEPS;
            for (int s = 0; s < NIGHT_STEPS && !e->terminated; s++) {
                int best = -1, bd = 1 << 30;
                for (int i = 0; i < MAX_MOBS; i++) if (e->mobs[i].kind) {
                    int d = abs(e->mobs[i].x - e->px) + abs(e->mobs[i].y - e->py);
                    if (d < bd) { bd = d; best = i; }
                }
                int a = ACT_NOOP;
                if (best >= 0 && bd <= 6) {
#if AIM_ATTACK
                    a = pol ? aimed(e, &e->mobs[best], pol == 2) : horizontal(e, &e->mobs[best]);
#else
                    a = horizontal(e, &e->mobs[best]);
#endif
                }
                int l0 = e->inv[ITEM_LENS];
                env_step(e, a);
                lens += e->inv[ITEM_LENS] - l0;
            }
            deaths += e->terminated; hp += e->health;
            eyek += has_ach(e, ACH_KILL_DEMON_EYE); zk += has_ach(e, ACH_KILL_ZOMBIE);
        }
        printf("  %-10s weapon %d armor %d: deaths %2d/%d, mean end hp %.0f, worlds with an eye kill %d, zombie kill %d, lenses %d\n",
               pol == 2 ? "aimed" : pol ? "turn" : "horizontal", weapons[g], armors[g], deaths, worlds, (double)hp / worlds, eyek, zk, lens);
    }
    return 0;
}
