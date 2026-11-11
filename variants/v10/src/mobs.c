/* Regular mobs (design section 5): spawning by layer and time of day, one AI
   function per kind, contact damage, melee hits and drops. All state is in
   Env.mobs; every random draw comes from Env.rng. Knobs live in env.h.

   v10: with FID_MOBS every kind runs a behaviour port of its Terraria 1.4.4
   AI (decompiled tModLoader 2026.08; each function names its method) on a
   sub-tile fixed-point body, one call per 60 Hz tick (mobs_game_tick):
   Blue Slime aiStyle 1, Cave Bat aiStyle 14, Zombie and Skeleton aiStyle 3
   (fighters), Demon Eye aiStyle 2. With FID_COMBAT, melee hits follow
   ItemCheck_MeleeHitNPCs / NPC.StrikeNPC and contact damage Player.Hurt.
   Spawning, the despawn radius and the dawn rule stay v9's (real NPC
   spawning is a separate system that is not ported). */
#include <stdlib.h>

#include "env.h"
#include "rng.h"
#include "fid.h"

static const int MOB_HP[MOB_KINDS] = {0,SLIME_HP,BAT_HP,ZOMBIE_HP,DEMON_EYE_HP,SKELETON_HP};
static const int MOB_DMG[MOB_KINDS] = {0,SLIME_DMG,BAT_DMG,ZOMBIE_DMG,DEMON_EYE_DMG,SKELETON_DMG};
static const char *const MOB_NAME[MOB_KINDS] = {"","Blue Slime","Cave Bat","Zombie","Demon Eye","Skeleton"};
#if FID_MOBS || FID_COMBAT
/* NPC.SetDefaults types 1, 49, 3, 2, 21: defense, knockBackResist, hitbox. */
static const int MOB_DEF[MOB_KINDS] = {0,SLIME_DEF,BAT_DEF,ZOMBIE_DEF,DEMON_EYE_DEF,SKELETON_DEF};
static const fix_t MOB_KB_RESIST[MOB_KINDS] = {0,FIXC(1.0),FIXC(0.8),FIXC(0.5),FIXC(0.8),FIXC(0.5)};
static const int MOB_W[MOB_KINDS] = {0,24,22,18,30,18}, MOB_H[MOB_KINDS] = {0,18,18,40,32,40};
#endif
#if FID_MOBS
/* noGravity: the bat (aiStyle 14) and the Demon Eye (AI_002 sets it every tick). */
static inline bool no_gravity(int kind) { return kind==MOB_CAVE_BAT || kind==MOB_DEMON_EYE; }
#endif

int mob_max_hp(int kind) { return kind>0 && kind<MOB_KINDS ? MOB_HP[kind] : 1; }

static inline bool solid_at(const Env *e,int x,int y) { return tile_solid(tile_at(e,x,y)); }

#if FID_MOBS
/* Hitbox-centre cell, the grid view of an NPC (obs, despawn, grid melee). */
static void mob_sync_cell(Mob *m) {
    m->x = ((m->fx >> 16) + MOB_W[m->kind] / 2) / 16;
    m->y = ((m->fy >> 16) + MOB_H[m->kind] / 2) / 16;
}

/* A spawn cell becomes a hitbox centred on the cell, standing on its bottom.
   SetDefaults: direction 0, spriteDirection -1, ai[] 0. */
static void mob_place_fixed(Mob *m) {
    int x = m->x * 16 + (16 - MOB_W[m->kind]) / 2, y = m->y * 16 + 16 - MOB_H[m->kind];
    if (x < 0) x = 0;
    if (x > WORLD_W * 16 - MOB_W[m->kind]) x = WORLD_W * 16 - MOB_W[m->kind];
    if (y < 0) y = 0;
    m->fx = x * FIX_ONE; m->fy = y * FIX_ONE;
    m->vx = m->vy = m->ovx = m->ovy = m->ai3 = 0;
    m->ai0 = m->ai1 = m->ai2 = 0; m->diry = 1; m->cx = m->cy = false;
    m->dir = 0; m->sdir = -1; m->still = false; m->hit = false;
    mob_sync_cell(m);
}
#endif

void mobs_reset(Env *e) {
#if FID_MOBS
    for (int i = 0; i < MAX_MOBS; i++) if (e->mobs[i].kind) mob_place_fixed(&e->mobs[i]);
#else
    (void)e;
#endif
}

/* A fresh mob of `kind` with `hp` standing in cell (x, y) (fixtures, tools). */
void mob_place(Mob *m, int kind, int hp, int x, int y) {
    *m = MOB_INIT(x, y, hp, 0, 0, 1, (uint8_t)kind);
#if FID_MOBS
    mob_place_fixed(m);
#endif
}

/* ---- spawning ------------------------------------------------------------ */

/* Walkers stand on the first air cell above a solid floor within +-4 rows. */
static int floor_row(const Env *e,int x,int y) {
    for(int k=0;k<=8;k++) {
        int yy=y+(k%2?(k+1)/2:-(k/2));
        if(!solid_at(e,x,yy) && solid_at(e,x,yy+1)) return yy;
    }
    return -1;
}

/* One spawn attempt per period; one candidate column per attempt, never an
   unbounded rejection loop. Surface at night spawns twice as often. */
static void spawn(Env *e) {
    int layer=player_layer(e);
    bool night=is_night(e);
    int period=layer==0&&night?NIGHT_SPAWN_PERIOD:SPAWN_PERIOD;
    if(e->steps<period || e->steps%period) return;
    int x=e->px+(rng_below(&e->rng,2)?1:-1)*rng_range(&e->rng,8,14);
    if(x<0 || x>=WORLD_W) return;
    uint8_t kind; int y;
    if(layer==0) {
        if(!night) { kind=MOB_BLUE_SLIME; y=e->surface[x]-1; }
        else if((int)rng_below(&e->rng,100)<EYE_SPAWN_PCT) { kind=MOB_DEMON_EYE; y=e->surface[x]-rng_range(&e->rng,3,7); }
        else { kind=MOB_ZOMBIE; y=e->surface[x]-1; }
    } else if(layer==1) { kind=MOB_CAVE_BAT; y=e->py; }
    else if((int)rng_below(&e->rng,100)<SKELETON_SPAWN_PCT) { kind=MOB_SKELETON; y=floor_row(e,x,e->py); }
    else { kind=MOB_CAVE_BAT; y=e->py; }
    if(!in_bounds(x,y) || solid_at(e,x,y)) return;
    for(int i=0;i<MAX_MOBS;i++) if(!e->mobs[i].kind) {
        Mob m=MOB_INIT(x,y,MOB_HP[kind],0,0,1,kind);
#if FID_MOBS
        /* The real-size body must fit where the cell rule put it. */
        mob_place_fixed(&m);
        if(fid_solid_collision(e,m.fx,m.fy,MOB_W[kind],MOB_H[kind])) return;
#endif
        e->mobs[i]=m;
        return;
    }
}

/* Drops and achievements. Bats are not scored in v9. The Demon Eye's lens is
   ItemDropDatabase's rule (Black Lens 1/100, else Lens 1/3 = 33%; no Black
   Lens in this game), the LENS_DROP_PCT knob. */
static void killed(Env *e,const Mob *m) {
    switch(m->kind) {
    case MOB_BLUE_SLIME: env_give(e,ITEM_GEL,2); env_award(e,ACH_KILL_SLIME); break;
    case MOB_ZOMBIE: env_award(e,ACH_KILL_ZOMBIE); break;
    case MOB_SKELETON: env_award(e,ACH_KILL_SKELETON); break;
    case MOB_DEMON_EYE:
        env_award(e,ACH_KILL_DEMON_EYE);
        if((int)rng_below(&e->rng,100)<LENS_DROP_PCT) { env_give(e,ITEM_LENS,1); env_award(e,ACH_COLLECT_LENS); }
        break;
    default: break;
    }
}

#if !FID_MOBS
/* ---- per-kind grid AI (v9) ----------------------------------------------- */

static void ai_slime(Env *e,Mob *m) {
    bool on_ground=solid_at(e,m->x,m->y+1) || tile_at(e,m->x,m->y+1)==TILE_PLATFORM;
    if(on_ground && m->phase==0) m->jump=2;
    if(m->jump>0) {
        if(!solid_at(e,m->x,m->y-1)) m->y--;
        m->jump--;
    } else if(!on_ground) m->y++;
    if(m->phase%2==0 && !solid_at(e,m->x+m->dir,m->y)) m->x+=m->dir;
}

static void ai_bat(Env *e,Mob *m) {
    if(m->phase%3) return;
    int nx=m->x+m->dir,ny=m->y+(e->py>m->y?1:e->py<m->y?-1:0);
    if(!solid_at(e,nx,m->y)) m->x=nx;
    if(!solid_at(e,m->x,ny)) m->y=ny;
}

/* Zombies and Skeletons: gravity, walk toward the player, step up one tile.
   `moves` says on which of the 8 phases the walker advances. */
static void ai_walker(Env *e,Mob *m,uint8_t moves) {
    bool on_ground=solid_at(e,m->x,m->y+1) || tile_at(e,m->x,m->y+1)==TILE_PLATFORM;
    if(!on_ground) { m->y++; return; }
    if(!((moves>>m->phase)&1)) return;
    if(m->x>=e->px && m->x<e->px+PLAYER_W) return;    /* under/over the player */
    int nx=m->x+m->dir;
    if(!solid_at(e,nx,m->y)) m->x=nx;
    else if(!solid_at(e,nx,m->y-1) && !solid_at(e,m->x,m->y-1)) { m->x=nx; m->y--; }
}

/* Flying, weaving approach: one column every other tick, rows chase a target
   that oscillates around the player's head. */
static void ai_demon_eye(Env *e,Mob *m) {
    static const int WEAVE[8]={0,1,2,1,0,-1,-2,-1};
    if(m->phase%2) return;
    int nx=m->x+m->dir;
    if(!solid_at(e,nx,m->y)) m->x=nx;
    int target=e->py-1+WEAVE[m->phase];
    int ny=m->y+(target>m->y?1:target<m->y?-1:0);
    if(!solid_at(e,m->x,ny)) m->y=ny;
}

void mobs_tick(Env *e) {
    spawn(e);
    for(int i=0;i<MAX_MOBS;i++) {
        Mob *m=&e->mobs[i]; if(!m->kind) continue;
        if(abs(m->x-e->px)>28 || abs(m->y-e->py)>24) { m->kind=MOB_NONE; continue; }
        m->phase=(m->phase+1)%8;
        m->dir=e->px>=m->x?1:-1;
        switch(m->kind) {
        case MOB_BLUE_SLIME: ai_slime(e,m); break;
        case MOB_CAVE_BAT:   ai_bat(e,m); break;
        case MOB_ZOMBIE:     ai_walker(e,m,0x55); break;   /* every other tick */
        case MOB_SKELETON:   ai_walker(e,m,0xDB); break;   /* 6 of 8 ticks */
        case MOB_DEMON_EYE:  ai_demon_eye(e,m); break;
        default: break;
        }
        if(m->y>=WORLD_H) { m->kind=MOB_NONE; continue; }
        /* FID_COMBAT: through Player.Hurt, knocked away from the mob. */
        if(is_body(e,m->x,m->y))
            env_hurt(e,MOB_DMG[m->kind],m->x*16+8<(player_fx(e)>>16)+PLAYER_PX_W/2?1:-1,MOB_NAME[m->kind]);
    }
}
#else
/* ---- FID_MOBS: NPC AI ports, one 60 Hz tick ------------------------------ */
#define NPC_GRAVITY FIXC(0.3)       /* NPC.UpdateNPC_UpdateGravity (the near-space factor is 1 here) */
#define NPC_MAX_FALL FIXC(10)
/* Main.worldSurface stand-in: the row under the surface band. */
#define FID_WORLD_SURFACE ((SURFACE_MAX + 1) * TILE_FIX)

/* NPC.TargetClosest(faceTarget: true): face the player's hitbox centre. */
static void mob_target(const Env *e, Mob *m) {
    int tx = (player_fx(e) >> 16) + PLAYER_PX_W / 2, ty = (player_fy(e) >> 16) + PLAYER_PX_H / 2;
    m->dir = tx * FIX_ONE < m->fx + (MOB_W[m->kind] / 2) * FIX_ONE ? -1 : 1;
    m->diry = ty * FIX_ONE < m->fy + (MOB_H[m->kind] / 2) * FIX_ONE ? -1 : 1;
}

/* NPC.AI_001_Slimes for type 1 (no liquids, items in body or slime rain).
   Aggressive at night, when damaged or below worldSurface. Grounded, ai[0]
   counts up 1 per tick (2 when aggressive). Hops fire at ai[0] >= 0 (small:
   vy -6, vx += 2*dir, then ai[0] = -1120), at -1000 (small, then -2120) and
   at -2000 (big: vy -8, vx += 3*dir, then -200): passive gaps of 200, 120,
   120 grounded ticks. Airborne, it steers 0.2/tick toward its direction up
   to |vx| 3. */
static void slime_ai(Env *e, Mob *m) {
    const int w = MOB_W[MOB_BLUE_SLIME], h = MOB_H[MOB_BLUE_SLIME];
    const bool aggressive = is_night(e) || m->hp != MOB_HP[MOB_BLUE_SLIME] || m->fy > FID_WORLD_SURFACE;
    if (m->ai2 > 1) m->ai2--;
    if (m->ai2 == 0) { m->ai0 = -100; m->ai2 = 1; mob_target(e, m); }
    if (m->vy == 0) {
        if (m->cy && m->ovy != 0 && fid_solid_collision(e, m->fx, m->fy, w, h)) m->fx -= m->vx + m->dir * FIX_ONE;
        if (m->ai3 == m->fx) { m->dir = -m->dir; m->ai2 = 200; }   /* a big jump went nowhere */
        m->ai3 = 0;
        m->vx = fmul(m->vx, FIXC(0.8));
        if (m->vx > -FIXC(0.1) && m->vx < FIXC(0.1)) m->vx = 0;
        if (aggressive) m->ai0++;
        m->ai0++;
        int hop = 0;
        if (m->ai0 >= 0) hop = 1;
        if (m->ai0 >= -1000 && m->ai0 <= -500) hop = 2;
        if (m->ai0 >= -2000 && m->ai0 <= -1500) hop = 3;
        if (hop) {
            if (aggressive && m->ai2 == 1) mob_target(e, m);
            if (hop == 3) { m->vy = FIXC(-8); m->vx += 3 * FIX_ONE * m->dir; m->ai0 = -200; m->ai3 = m->fx; }
            else { m->vy = FIXC(-6); m->vx += 2 * FIX_ONE * m->dir; m->ai0 = -120 + (hop == 1 ? -1000 : -2000); }
        }
    } else if ((m->dir == 1 && m->vx < 3 * FIX_ONE) || (m->dir == -1 && m->vx > -3 * FIX_ONE)) {
        if (m->cx && fabsx(m->vx) == FIXC(0.2)) m->fx -= FIXC(1.4) * m->dir;
        if (m->cy && m->ovy != 0 && fid_solid_collision(e, m->fx, m->fy, w, h)) m->fx -= m->vx + m->dir * FIX_ONE;
        if ((m->dir == -1 && m->vx < FIXC(0.01)) || (m->dir == 1 && m->vx > -FIXC(0.01))) m->vx += FIXC(0.2) * m->dir;
        else m->vx = fmul(m->vx, FIXC(0.93));
    }
    /* Observation phase: grounded ticks to the next hop, in 30-tick bins. */
    int left = m->ai0 >= -200 ? -m->ai0 : m->ai0 >= -1120 ? -1000 - m->ai0 : -2000 - m->ai0;
    m->phase = m->vy != 0 || left < 0 ? 0 : left / 30 > 7 ? 7 : left / 30;
}

/* Flyer steering shared by NPC.AI aiStyle 14 (Cave Bat, type 49 branch) and
   NPC.AI_002_FloatingEye (Demon Eye, type 2): bounce off tiles at half the
   pre-collision speed (minimum 2 px/tick across, 1 down/up), re-target every
   tick, accelerate 0.1/tick toward the player up to |vx| 4 and 0.04/tick up
   to |vy| 1.5, with the real asymmetric slowdown when moving the wrong way. */
static void flyer_steer(Env *e, Mob *m) {
    const fix_t F = FIX_ONE;
    if (m->cx) {
        m->vx = fmul(m->ovx, FIXC(-0.5));
        if (m->dir == -1 && m->vx > 0 && m->vx < 2 * F) m->vx = 2 * F;
        if (m->dir == 1 && m->vx < 0 && m->vx > -2 * F) m->vx = -2 * F;
    }
    if (m->cy) {
        m->vy = fmul(m->ovy, FIXC(-0.5));
        if (m->vy > 0 && m->vy < F) m->vy = F;
        if (m->vy < 0 && m->vy > -F) m->vy = -F;
    }
    mob_target(e, m);
    if (m->dir == -1 && m->vx > -4 * F) {
        m->vx -= FIXC(0.1);
        if (m->vx > 4 * F) m->vx -= FIXC(0.1); else if (m->vx > 0) m->vx += FIXC(0.05);
        if (m->vx < -4 * F) m->vx = -4 * F;
    } else if (m->dir == 1 && m->vx < 4 * F) {
        m->vx += FIXC(0.1);
        if (m->vx < -4 * F) m->vx += FIXC(0.1); else if (m->vx < 0) m->vx -= FIXC(0.05);
        if (m->vx > 4 * F) m->vx = 4 * F;
    }
    if (m->diry == -1 && m->vy > -FIXC(1.5)) {
        m->vy -= FIXC(0.04);
        if (m->vy > FIXC(1.5)) m->vy -= FIXC(0.05); else if (m->vy > 0) m->vy += FIXC(0.03);
        if (m->vy < -FIXC(1.5)) m->vy = -FIXC(1.5);
    } else if (m->diry == 1 && m->vy < FIXC(1.5)) {
        m->vy += FIXC(0.04);
        if (m->vy < -FIXC(1.5)) m->vy += FIXC(0.05); else if (m->vy < 0) m->vy -= FIXC(0.03);
        if (m->vy > FIXC(1.5)) m->vy = FIXC(1.5);
    }
}

/* Cave Bat: flyer_steer, then after 200 ticks without line of sight the
   real ai[1]/ai[2] wander. No gravity; passes platforms. */
static void bat_ai(Env *e, Mob *m) {
    const fix_t F = FIX_ONE;
    flyer_steer(e, m);
    m->ai1++;
    if (m->ai1 > 200) {
        if (fid_can_hit(e, m->fx, m->fy, MOB_W[MOB_CAVE_BAT], MOB_H[MOB_CAVE_BAT],
                        player_fx(e), player_fy(e), PLAYER_PX_W, PLAYER_PX_H)) m->ai1 = 0;
        if (m->ai1 > 1000) m->ai1 = 0;
        m->ai2++;
        if (m->ai2 > 0) { if (m->vy < FIXC(1.5)) m->vy += FIXC(0.1); }
        else if (m->vy > -FIXC(1.5)) m->vy -= FIXC(0.1);
        if (m->ai2 < -150 || m->ai2 > 150) { if (m->vx < 4 * F) m->vx += FIXC(0.2); }
        else if (m->vx > -4 * F) m->vx -= FIXC(0.2);
        if (m->ai2 > 300) m->ai2 = -300;
    }
    m->phase = m->ai1 / 30 > 7 ? 7 : m->ai1 / 30;
}

/* NPC.AI_002_FloatingEye, type 2 (lines ~55707-56166): noGravity, bounce,
   TargetClosest, default acceleration (4 / 1.5 caps at scale 1). Its daytime
   branch (fly up and despawn above worldSurface) is not reached: v9's dawn
   rule removes Demon Eyes (mobs_dawn). Phase: vertical velocity in 8 bins. */
static void eye_ai(Env *e, Mob *m) {
    flyer_steer(e, m);
    int b = (int)(((int64_t)(m->vy + FIXC(1.5)) * 8) / FIXC(3.0));
    m->phase = b < 0 ? 0 : b > 7 ? 7 : b;
}

/* NPC.AI_003_Fighters for Zombie (type 3, final else branch, max speed 1)
   and Skeleton (type 21, line ~62246 branch, max speed 1.5); single player,
   normal mode, no doors, slopes or liquids. ai[3] (here an integer count in
   the fix_t slot) is the stuck counter, ai[0] the wander turn counter. */
static bool fid_any(const Env *e, int c, int r) { return fid_any_solid(tile_at(e, c, r)); }
static bool fid_full(const Env *e, int c, int r) { return fid_block(tile_at(e, c, r)); }
static void fighter_ai(Env *e, Mob *m, fix_t max_speed) {
    const int w = MOB_W[m->kind], h = MOB_H[m->kind];
    const fix_t pfx = player_fx(e), pfy = player_fy(e);
    /* 60550: feet level with the player's -> directionY -1. */
    if (pfy + PLAYER_PX_H * FIX_ONE == m->fy + h * FIX_ONE) m->diry = -1;
    const bool flag6 = m->vx == 0 && !m->hit;                 /* 61693 */
    /* Stuck counter (61794-61825): no horizontal displacement last move,
       already bored, or skidding against the facing. */
    const bool skid = m->vy == 0 && ((m->vx > 0 && m->dir < 0) || (m->vx < 0 && m->dir > 0));
    if (m->still || m->ai3 >= 60 || skid) m->ai3++;
    else if (fabsx(m->vx) > FIXC(0.9) && m->ai3 > 0) m->ai3--;
    if (m->ai3 > 600) m->ai3 = 0;
    if (m->hit) m->ai3 = 0;
    if (fid_rects(pfx, pfy, PLAYER_PX_W, PLAYER_PX_H, m->fx, m->fy, w, h)) m->ai3 = 0;
    /* 62021-62087: target, unless bored or by day on/above the surface
       (DespawnEncouragement_AIStyle3_Fighters_NotDiscouraged); then wander,
       turning after 2 grounded ticks without horizontal speed. The 10-tick
       EncourageDespawn is v9's despawn radius here. */
    if (m->ai3 < 60 && !(!is_night(e) && m->fy <= FID_WORLD_SURFACE)) {
        mob_target(e, m);
        if (m->diry > 0 && (pfy >> 16) + PLAYER_PX_H / 2 <= (m->fy + h * FIX_ONE) >> 16) m->diry = -1;
    } else {
        if (m->vx == 0) {
            if (m->vy == 0 && ++m->ai0 >= 2) { m->dir = -m->dir; m->sdir = (int8_t)m->dir; m->ai0 = 0; }
        } else m->ai0 = 0;
        if (m->dir == 0) m->dir = 1;
    }
    /* Horizontal speed: +-0.07/tick up to the type's max; x0.8 when grounded
       above it. */
    if (m->vx < -max_speed || m->vx > max_speed) { if (m->vy == 0) m->vx = fmul(m->vx, FIXC(0.8)); }
    else if (m->vx < max_speed && m->dir == 1) { m->vx += FIXC(0.07); if (m->vx > max_speed) m->vx = max_speed; }
    else if (m->vx > -max_speed && m->dir == -1) { m->vx -= FIXC(0.07); if (m->vx < -max_speed) m->vx = -max_speed; }
    /* 64426: grounded with a clear head (platforms count as solid). */
    bool flag5 = false;
    if (m->vy == 0) {
        const fix_t head = m->fy - 9 * FIX_ONE;
        const int y_floor = ftile(m->fy + (h + 7) * FIX_ONE), y_head = head > 0 ? ftile(head) : 0;
        for (int c = ftile(m->fx + 8 * FIX_ONE); c <= ftile(m->fx + (w - 8) * FIX_ONE); c++) {
            if (fid_any(e, c, y_head)) { flag5 = false; break; }
            if (fid_any(e, c, y_floor)) flag5 = true;
        }
    }
    /* 64465: the fighters' own step-up onto a full block at foot level. */
    if (m->vy >= 0) {
        const int s = m->vx > 0 ? 1 : m->vx < 0 ? -1 : 0;
        const fix_t nx = m->fx + m->vx, lead = nx + (w / 2) * FIX_ONE + (w / 2 + 1) * s * FIX_ONE;
        const int c = lead >= 0 ? ftile(lead) : -1, r = ftile(m->fy + (h - 1) * FIX_ONE);
        if (c >= 4 && c < WORLD_W - 4 && r >= 4 && r < WORLD_H - 4
            && c * TILE_FIX < nx + w * FIX_ONE && c * TILE_FIX + TILE_FIX > nx
            && fid_full(e, c, r) && !fid_full(e, c, r - 1) && !fid_full(e, c, r - 2) && !fid_full(e, c, r - 3)
            && !fid_any(e, c - s, r - 3)) {
            const fix_t top = r * TILE_FIX, feet = m->fy + h * FIX_ONE;
            if (top < feet && feet - top <= FIXC(16.1)) m->fy = top - h * FIX_ONE;
        }
    }
    /* 64542: jumps over walls (2-3 tiles: -7/-8, 1 tile: -6), across gaps
       toward a player level or above (-8, vx x1.5), and the first stuck hop. */
    if (flag5 && ((m->vx < 0 && m->sdir == -1) || (m->vx > 0 && m->sdir == 1))) {
        const int c = ftile(m->fx + (w / 2) * FIX_ONE + 15 * m->dir * FIX_ONE), r = ftile(m->fy + (h - 15) * FIX_ONE);
        if (fid_any(e, c, r - 2)) m->vy = fid_any(e, c, r - 3) ? FIXC(-8) : FIXC(-7);
        else if (fid_any(e, c, r - 1)) m->vy = FIXC(-6);
        else if (m->fy + h * FIX_ONE - r * TILE_FIX > 20 * FIX_ONE && fid_any(e, c, r)) m->vy = FIXC(-5);
        else if (m->diry < 0 && !fid_any(e, c, r + 1) && !fid_any(e, c + m->dir, r + 1)) {
            m->vy = FIXC(-8); m->vx = fmul(m->vx, FIXC(1.5));
        }
        if (m->vy == 0 && flag6 && m->ai3 == 1) m->vy = FIXC(-5);
    }
    /* Observation phase: stuck count in 10-tick bins; 7 = bored (wandering). */
    m->phase = m->ai3 >= 60 ? 7 : m->ai3 / 10;
}

/* NPC.UpdateNPC_Inner after AI: immunity countdown, gravity (0.3, cap 10)
   unless noGravity, tiny |vx| zeroed, then UpdateCollision: TileCollision
   (fall-through: bats and eyes always, fighters when directionY is 1), up ->
   vy 0.01, collideX/Y, move; FindFrame's fighter spriteDirection; justHit
   cleared. */
static void mob_update(Env *e, Mob *m) {
    const int k = m->kind;
    switch (k) {
    case MOB_BLUE_SLIME: slime_ai(e, m); break;
    case MOB_CAVE_BAT:   bat_ai(e, m); break;
    case MOB_DEMON_EYE:  eye_ai(e, m); break;
    case MOB_ZOMBIE:     fighter_ai(e, m, FIXC(1.0)); break;
    case MOB_SKELETON:   fighter_ai(e, m, FIXC(1.5)); break;
    default: break;
    }
#if FID_COMBAT
    if (m->immune > 0) m->immune--;
#endif
    if (!no_gravity(k)) { m->vy += NPC_GRAVITY; if (m->vy > NPC_MAX_FALL) m->vy = NPC_MAX_FALL; }
    if (m->vx < FIXC(0.005) && m->vx > -FIXC(0.005)) m->vx = 0;
    m->ovx = m->vx; m->ovy = m->vy;
    const bool fighter = k == MOB_ZOMBIE || k == MOB_SKELETON;
    const bool fall = no_gravity(k) || (fighter && m->diry == 1);
    FidHit hit;
    fid_tile_collision(e, m->fx, m->fy, &m->vx, &m->vy, MOB_W[k], MOB_H[k], fall, fall, &hit);
    if (hit.up) m->vy = FIXC(0.01);
    m->cx = m->ovx != m->vx; m->cy = m->ovy != m->vy;
    const fix_t old_x = m->fx;
    m->fx += m->vx; m->fy += m->vy;
    const fix_t max_x = (WORLD_W * 16 - MOB_W[k]) * FIX_ONE, max_y = (WORLD_H * 16 - MOB_H[k]) * FIX_ONE;
    if (m->fx < 0) { m->fx = 0; m->vx = 0; }
    if (m->fx > max_x) { m->fx = max_x; m->vx = 0; }
    if (m->fy < 0) { m->fy = 0; m->vy = 0; }
    if (m->fy > max_y) { m->fy = max_y; m->vy = 0; }
    m->still = m->fx == old_x;               /* position.X == oldPosition.X */
    if (fighter && m->vy == 0 && m->dir) m->sdir = (int8_t)m->dir;
    m->hit = false;
    mob_sync_cell(m);
}

/* Player.Update_NPCCollision: an NPC hitbox touching the player's deals
   contact damage, knocking the player away from the NPC's centre. */
void mobs_contact(Env *e) {
    const fix_t px = player_fx(e), py = player_fy(e);
    for (int i = 0; i < MAX_MOBS; i++) {
        Mob *m = &e->mobs[i];
        if (!m->kind || !fid_rects(px, py, PLAYER_PX_W, PLAYER_PX_H, m->fx, m->fy, MOB_W[m->kind], MOB_H[m->kind])) continue;
        int dir = m->fx + (MOB_W[m->kind] / 2) * FIX_ONE < px + (PLAYER_PX_W / 2) * FIX_ONE ? 1 : -1;
        env_hurt(e, MOB_DMG[m->kind], dir, MOB_NAME[m->kind]);
    }
}

/* Per action: v9's spawn rule (bodies placed in px) and despawn radius. */
void mobs_tick(Env *e) {
    spawn(e);
    for(int i=0;i<MAX_MOBS;i++) {
        Mob *m=&e->mobs[i];
        if(m->kind && (abs(m->x-e->px)>28 || abs(m->y-e->py)>24)) m->kind=MOB_NONE;
    }
}
#endif

#if FID_TICKED
/* One 60 Hz tick of every NPC (after the player): AI and movement with
   FID_MOBS, otherwise only the hit-immunity countdown of FID_COMBAT. */
void mobs_game_tick(Env *e) {
    for (int i = 0; i < MAX_MOBS; i++) {
        Mob *m = &e->mobs[i];
        if (!m->kind) continue;
#if FID_MOBS
        mob_update(e, m);
#elif FID_COMBAT
        if (m->immune > 0) m->immune--;
#endif
    }
}
#endif

#if !FID_COMBAT
/* Every mob inside the melee box with no solid tile between the facing edge
   and the mob is hit; survivors are knocked back one tile. */
void mobs_attack(Env *e,int x0,int y0,int x1,int y1,int damage) {
    int edge=e->px+(e->facing>0?PLAYER_W-1:0);
    for(int i=0;i<MAX_MOBS;i++) {
        Mob *m=&e->mobs[i];
        if(!m->kind || m->x<x0 || m->x>x1 || m->y<y0 || m->y>y1) continue;
        int dx=m->x-edge; bool blocked=false;
        if(!is_body(e,m->x,m->y))
            for(int s=1;s<abs(dx);s++) if(solid_at(e,edge+s*e->facing,m->y)) blocked=true;
        if(blocked) continue;
        m->hp-=damage;
        env_fx_hit(e,FX_TARGET_MOB,i,m->x*16+8,m->y*16,damage,false);
        if(m->hp<=0) {
            killed(e,m);
            SAY(e,"%s defeated",MOB_NAME[m->kind]);
            m->kind=MOB_NONE;
        } else {
            int nx=m->x+e->facing;
            if(!solid_at(e,nx,m->y)) {
                m->x=nx;
#if FID_MOBS
                /* the v9 one-cell shove, applied to the sub-tile body */
                m->fx+=e->facing*TILE_FIX;
                if(m->fx<0) m->fx=0;
                if(m->fx>(WORLD_W*16-MOB_W[m->kind])*FIX_ONE) m->fx=(WORLD_W*16-MOB_W[m->kind])*FIX_ONE;
#endif
            }
            SAY(e,"hit %s: %d hp",MOB_NAME[m->kind],m->hp);
        }
    }
}
#else
/* Hitbox in Q16 px: the NPC's own box, or its grid cell without FID_MOBS. */
static void mob_rect(const Mob *m, fix_t *x, fix_t *y, int *w, int *h) {
#if FID_MOBS
    *x = m->fx; *y = m->fy; *w = MOB_W[m->kind]; *h = MOB_H[m->kind];
#else
    *x = m->x * TILE_FIX; *y = m->y * TILE_FIX; *w = *h = 16;
#endif
}

#define FID_CRIT_PCT 4            /* base melee crit chance; the items add 0 */

/* NPC.HitModifiers.GetDamage + NPC.StrikeNPC: variance, max(d - defense*0.5,
   1), crit x2, then knockback. Knockback is weapon kb x knockBackResist
   (GetIncomingStrikeModifiers), x1.4 on crits; a blow worth more than a tenth
   of lifeMax pushes additively up to that, otherwise velocity is set to it
   x knockBackResist again (StrikeNPC; vanilla applies the resist twice). */
static void mob_strike(Env *e, Mob *m, int base, fix_t kb, int dir) {
    bool crit = rng_range(&e->rng, 1, 100) <= FID_CRIT_PCT;
    int twice = 2 * env_damage_var(e, base) - MOB_DEF[m->kind];
    if (twice < 2) twice = 2;
    if (crit) twice *= 2;
    int dmg = twice / 2;
    m->hp -= dmg;
    { fix_t hx, hy; int hw, hh; mob_rect(m, &hx, &hy, &hw, &hh);
      env_fx_hit(e, FX_TARGET_MOB, (int)(m - e->mobs), (int)(hx >> 16) + hw / 2, (int)(hy >> 16), dmg, crit); }
#if FID_MOBS
    const fix_t resist = MOB_KB_RESIST[m->kind];
    fix_t k = fmul(kb, resist);
    if (crit) k = fmul(k, FIXC(1.4));
    const fix_t up = no_gravity(m->kind) ? FIXC(0.5) : FIXC(0.75);
    if (dmg * 10 > MOB_HP[m->kind]) {
        if (dir < 0 && m->vx > -k) { if (m->vx > 0) m->vx -= k; m->vx -= k; if (m->vx < -k) m->vx = -k; }
        else if (dir > 0 && m->vx < k) { if (m->vx < 0) m->vx += k; m->vx += k; if (m->vx > k) m->vx = k; }
        fix_t k2 = -fmul(k, up);
        if (m->vy > k2) { m->vy += k2; if (m->vy < k2) m->vy = k2; }
    } else {
        m->vy = -fmul(fmul(k, up), resist);
        m->vx = fmul(k, resist) * dir;
    }
    m->hit = true;                         /* NPC.justHit */
#else
    (void)kb;
    { int nx = m->x + dir; if (!tile_solid(tile_at(e, nx, m->y))) m->x = nx; }
#endif
    if (m->hp <= 0) {
        killed(e, m);
        SAY(e, "%s defeated", MOB_NAME[m->kind]);
        m->kind = MOB_NONE;
    } else SAY(e, "hit %s: %d hp%s", MOB_NAME[m->kind], m->hp, crit ? " (crit)" : "");
}

/* ItemCheck_MeleeHitNPCs: each NPC once per swing (NPC.immune =
   itemAnimation), attackCD = max(1, itemAnimationMax*0.33) after a hit
   (blocking further hits while it runs), Collision.CanHit line of sight. */
void mobs_swing(Env *e, int X, int Y, int W, int H, int damage, fix_t kb, int dir, int anim) {
    const fix_t ppx = player_fx(e), ppy = player_fy(e);
    if (e->attack_cd_ticks > 0) return;   /* attackCD blocks every NPC this tick */
    for (int i = 0; i < MAX_MOBS; i++) {
        Mob *m = &e->mobs[i];
        /* The useStyle 1 box never reaches 8 cells from the body (cheap cull). */
        if (m->kind && (abs(m->x - e->px) > 8 || abs(m->y - e->py) > 8)) continue;
        if (!m->kind || m->immune > 0 || e->attack_cd_ticks > 0) continue;
        fix_t mx, my; int mw, mh; mob_rect(m, &mx, &my, &mw, &mh);
        if (!fid_rects(X * FIX_ONE, Y * FIX_ONE, W, H, mx, my, mw, mh)) continue;
        if (!fid_can_hit(e, ppx, ppy, PLAYER_PX_W, PLAYER_PX_H, mx, my, mw, mh)) continue;
        mob_strike(e, m, damage, kb, dir);
        m->immune = anim;
        e->attack_cd_ticks = e->item_anim_max * 33 / 100 > 1 ? e->item_anim_max * 33 / 100 : 1;
    }
}

/* Projectile AI_161_RapierStabs collision: one hit per NPC per stab. With
   AIM_ATTACK (x0, y0) .. (x1, y1) is the stab's segment, tested with
   CheckAABBvLineCollision width 10 (fid_line_hits); else a box. */
void mobs_stab(Env *e, fix_t x0, fix_t y0, fix_t x1, fix_t y1, int damage, fix_t kb, int dir) {
    const fix_t ppx = player_fx(e), ppy = player_fy(e);
    for (int i = 0; i < MAX_MOBS; i++) {
        Mob *m = &e->mobs[i];
        if (!m->kind || (e->stab_hits >> i & 1u)) continue;
        fix_t mx, my; int mw, mh; mob_rect(m, &mx, &my, &mw, &mh);
#if AIM_ATTACK
        if (!fid_line_hits(x0, y0, x1, y1, e->stab_ux, e->stab_uy, 10 * FIX_ONE, mx, my, mw, mh)) continue;
#else
        if (!(mx < x1 && x0 < mx + mw * FIX_ONE && my < y1 && y0 < my + mh * FIX_ONE)) continue;
#endif
        if (!fid_can_hit(e, ppx, ppy, PLAYER_PX_W, PLAYER_PX_H, mx, my, mw, mh)) continue;
        e->stab_hits |= 1u << i;
        mob_strike(e, m, damage, kb, dir);
    }
}
#endif

void mobs_dawn(Env *e) {
    for(int i=0;i<MAX_MOBS;i++) if(e->mobs[i].kind==MOB_DEMON_EYE) e->mobs[i].kind=MOB_NONE;
}
