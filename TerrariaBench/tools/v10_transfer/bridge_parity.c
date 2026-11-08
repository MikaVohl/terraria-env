/* Parity check for bridge.c: rebuild real v10 sim states through br_set (window 49x37 around the player, the
   same size the real-game snapshot provides) and compare br_obs/br_mask with env_obs/env_action_mask.
   cc ... bridge.c bridge_parity.c (see the report for the full command); prints mismatching steps. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "env.h"

void *br_new(void);
void br_set(void *, const int *, const uint8_t *, const uint8_t *, const int *, const int *, int);
void br_obs(void *, float *);
void br_mask(void *, uint8_t *);
int br_flat_size(void);

int main(void)
{
    enum { W = 49, H = 37 };
    static Env e;
    void *b = br_new();
    int n = br_flat_size(), bad_obs = 0, bad_mask = 0, total = 0;
    float *a = calloc(n, sizeof *a), *c = calloc(n, sizeof *c);
    uint64_t rng = 7;
    for (int seed = 1; seed <= 4; seed++) {
        env_init(&e, (EnvConfig){ EPISODE_STEPS });
        env_reset(&e, 23000000 + seed);
        for (int t = 0; t < 600 && !e.terminated; t++) {
            Obs o; uint8_t m1[ACT_COUNT], m2[ACT_COUNT];
            env_action_mask(&e, m1);
            int legal[ACT_COUNT], k = 0;
            for (int i = 0; i < ACT_COUNT; i++) if (m1[i]) legal[k++] = i;
            rng = rng * 6364136223846793005ULL + 1442695040888963407ULL;
            env_step(&e, legal[(rng >> 33) % k]);
            env_obs(&e, &o);
            env_action_mask(&e, m1);
            static uint8_t tiles[W * H], light[W * H];
            int x0 = e.px - W / 2, y0 = e.py - H / 2;
            for (int r = 0; r < H; r++) for (int col = 0; col < W; col++) {
                int x = x0 + col, y = y0 + r;
                tiles[r * W + col] = in_bounds(x, y) ? e.tiles[y][x] : TILE_BEDROCK;
                light[r * W + col] = in_bounds(x, y) ? e.light[y][x] : LIGHT_MAX;
            }
            int inv[ITEM_COUNT], mobs[MAX_MOBS * 4], nm = 0;
            for (int i = 0; i < ITEM_COUNT; i++) inv[i] = e.inv[i];
            for (int i = 0; i < MAX_MOBS; i++) if (e.mobs[i].kind) {
                const Mob *m = &e.mobs[i];
                mobs[nm * 4] = m->kind; mobs[nm * 4 + 1] = m->x; mobs[nm * 4 + 2] = m->y;
                mobs[nm * 4 + 3] = (m->hp * 1000 + mob_max_hp(m->kind) - 1) / mob_max_hp(m->kind); nm++;
            }
            int dig = 0;
            for (int i = 0; i < HIT_SLOTS; i++)
                if (e.hits[i].ttl > 0 && e.hits[i].x == e.dig_x && e.hits[i].y == e.dig_y) dig = e.hits[i].damage;
            int s[] = { e.px, e.py, e.steps, e.max_steps, e.health, e.max_health, e.tool_tier, e.weapon, e.armor,
                        e.item_anim, e.item_anim_max, e.immune_ticks, e.heal_cd, e.facing, e.jump, e.air_jump_used,
                        e.fall_dist, e.pos_x, e.pos_y, e.vel_x, e.vel_y, e.selected, e.surface[e.px],
                        x0, y0, W, H, (int)(uint32_t)e.achievements, (int)(uint32_t)(e.achievements >> 32),
                        e.boss.active, e.boss.x, e.boss.y, e.boss.active ? e.boss.hp * 1000 / EOC_HP : 0, e.boss.mode,
                        e.tool_time, e.dig_x, e.dig_y, dig, e.safe_ticks };
            br_set(b, s, tiles, light, inv, mobs, nm);
            br_obs(b, c);
            br_mask(b, m2);
            /* Reference flat encoding of the real sim obs. */
            const int terrain = VIEW_CELLS * OBS_TILE_KINDS;
            memset(a, 0, (size_t)n * sizeof *a);
            for (int i = 0; i < VIEW_CELLS; i++) { a[i * OBS_TILE_KINDS + o.tile[i]] = 1.f; a[terrain + i] = (float)((double)o.light[i] / 15.); }
            memcpy(a + terrain + VIEW_CELLS, o.status, sizeof o.status);
            int diff = -1;
            /* Entity HP fraction tolerates permille rounding; the movement-phase channel (no real-game
               counterpart, the bridge sends 0) is excluded. */
            const int ent = terrain + VIEW_CELLS + OBS_ENTITY_0;
            for (int i = 0; i < n; i++) {
                if (a[i] == c[i]) continue;
                if (i >= ent && i < ent + VIEW_CELLS * OBS_ENTITY_CHANNELS) {
                    int ch = (i - ent) % OBS_ENTITY_CHANNELS;
                    if (ch == MOB_KINDS + 1) continue;
                    if (ch == MOB_KINDS && a[i] - c[i] < 1e-2f && c[i] - a[i] < 1e-2f) continue;
                }
                diff = i; break;
            }
            total++;
            if (diff >= 0) { if (bad_obs++ < 5) printf("seed %d step %d obs differs at %d: %g vs %g\n", seed, t, diff, a[diff], c[diff]); }
            if (memcmp(m1, m2, ACT_COUNT)) { if (bad_mask++ < 5) { printf("seed %d step %d mask differs:", seed, t); for (int i = 0; i < ACT_COUNT; i++) if (m1[i] != m2[i]) printf(" %s", action_name(i)); printf("\n"); } }
        }
    }
    printf("%d states: %d obs mismatches, %d mask mismatches\n", total, bad_obs, bad_mask);
    return 0;
}
