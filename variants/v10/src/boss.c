/* Eye of Cthulhu (design section 5), self-contained so its behaviour can be
   replaced without touching the rest of the simulator.

   State: Env.boss (Boss in env.h). Interface: boss_summon, boss_tick (AI and
   contact damage, once per step after the regular mobs), boss_attack (player
   melee box), boss_despawn. Timers, speeds, HP and damage are EOC_* knobs.

   A 3x3 flyer that ignores terrain. Phase 1: hover toward a point
   EOC_HOVER_HEIGHT rows above the player, then EOC_DASHES1 aimed dashes
   (EOC_DASH_SPEED1 tiles/tick for EOC_DASH_TICKS1 ticks, EOC_PAUSE_TICKS1
   between dashes), then hover again. Phase 2 (HP <= 50%): the same cycle with
   the *2 knobs: shorter hover, more, faster and more frequent charges, more
   contact damage. Despawns at dawn and when the player dies; defeat drops
   demonite ore.

   v10: the AI stays v9's (per action, grid cells). With FID_COMBAT the fight
   goes through the ported combat rules: the body is a 48x48 px hitbox, sword
   swings and shortsword stabs hit it per 60 Hz tick (ItemCheck_MeleeHitNPCs:
   once per swing, attackCD; no line-of-sight test, it has noTileCollide),
   damage follows
   NPC.HitModifiers (variance, EOC_DEF/2, crits; knockBackResist 0, so no
   knockback), and contact damage is checked every tick through Player.Hurt
   (i-frames, knockback away from the boss centre). */
#include <stdlib.h>

#include "env.h"
#include "rng.h"
#include "fid.h"

static inline bool phase2(const Boss *b) { return 2*b->hp<=EOC_HP; }

static inline int clampi(int v,int lo,int hi) { return v<lo?lo:v>hi?hi:v; }

static inline int sgn(int v) { return (v>0)-(v<0); }

/* Aim at the player's body centre: the dominant axis moves at full speed,
   the other proportionally (rounded), so dashes are straight lines. */
static void start_dash(Env *e,Boss *b) {
    int speed=phase2(b)?EOC_DASH_SPEED2:EOC_DASH_SPEED1;
    int dx=(2*e->px+PLAYER_W)-(2*b->x+EOC_SIZE), dy=(2*e->py-PLAYER_H+1)-(2*b->y+EOC_SIZE-1);
    int big=abs(dx)>abs(dy)?abs(dx):abs(dy);
    if(big==0) { b->vx=0; b->vy=speed; }
    else {
        b->vx=(dx*speed*2+sgn(dx)*big)/(2*big);
        b->vy=(dy*speed*2+sgn(dy)*big)/(2*big);
    }
    b->mode=BOSS_DASH;
    b->timer=phase2(b)?EOC_DASH_TICKS2:EOC_DASH_TICKS1;
}

static void start_hover(Boss *b) {
    b->mode=BOSS_HOVER;
    b->timer=phase2(b)?EOC_HOVER_TICKS2:EOC_HOVER_TICKS1;
}

static void move_to(Boss *b,int x,int y) {
    b->x=clampi(x,0,WORLD_W-EOC_SIZE);
    b->y=clampi(y,0,WORLD_H-EOC_SIZE);
}

#if !FID_COMBAT
static bool overlaps(const Boss *b,int x0,int y0,int x1,int y1) {
    return b->x<=x1 && b->x+EOC_SIZE-1>=x0 && b->y<=y1 && b->y+EOC_SIZE-1>=y0;
}
#endif

void boss_summon(Env *e) {
    Boss *b=&e->boss;
    int side=rng_below(&e->rng,2)?1:-1;
    *b=(Boss){0};   /* also clears the FID_COMBAT immunity */
    b->active=true; b->hp=EOC_HP;
    move_to(b,e->px+side*14-1,e->py-14);
    start_hover(b);
    SAY(e,"the Eye of Cthulhu has awoken!");
}

void boss_despawn(Env *e,const char *why) {
    e->boss.active=false;
    if(why) SAY(e,"%s",why);
}

void boss_tick(Env *e) {
    Boss *b=&e->boss;
    if(!b->active) return;
    bool p2=phase2(b);
    switch(b->mode) {
    case BOSS_HOVER: {
        int tx=e->px+PLAYER_W/2-EOC_SIZE/2, ty=e->py-EOC_HOVER_HEIGHT-EOC_SIZE/2;
        move_to(b,b->x+sgn(tx-b->x),b->y+sgn(ty-b->y));
        if(--b->timer<=0) { b->dashes_left=(uint8_t)(p2?EOC_DASHES2:EOC_DASHES1); start_dash(e,b); }
        break;
    }
    case BOSS_DASH:
        move_to(b,b->x+b->vx,b->y+b->vy);
        if(--b->timer<=0) {
            if(b->dashes_left>0) b->dashes_left--;
            if(b->dashes_left>0) { b->mode=BOSS_PAUSE; b->timer=p2?EOC_PAUSE_TICKS2:EOC_PAUSE_TICKS1; }
            else start_hover(b);
        }
        break;
    case BOSS_PAUSE:
        if(--b->timer<=0) start_dash(e,b);
        break;
    default: start_hover(b); break;
    }
#if !FID_COMBAT
    if(overlaps(b,e->px,e->py-PLAYER_H+1,e->px+PLAYER_W-1,e->py))
        env_hurt(e,p2?EOC_DMG2:EOC_DMG1,2*b->x+EOC_SIZE<2*e->px+PLAYER_W?1:-1,"Eye of Cthulhu");
#endif
}

/* Damage to the boss; defeat drops demonite ore. */
static void boss_damage(Env *e,int damage,bool crit) {
    Boss *b=&e->boss;
    b->hp-=damage;
    env_fx_hit(e,FX_TARGET_BOSS,0,b->x*16+EOC_SIZE*8,b->y*16,damage,crit);
    if(b->hp<=0) {
        b->active=false; b->hp=0;
        env_give(e,ITEM_DEMONITE_ORE,rng_range(&e->rng,EOC_DEMONITE_MIN,EOC_DEMONITE_MAX));
        env_award(e,ACH_DEFEAT_EOC);
        SAY(e,"the Eye of Cthulhu has been defeated!");
    } else SAY(e,"hit Eye of Cthulhu: %d hp",b->hp);
}

#if !FID_COMBAT
bool boss_attack(Env *e,int x0,int y0,int x1,int y1,int damage) {
    Boss *b=&e->boss;
    if(!b->active || !overlaps(b,x0,y0,x1,y1)) return false;
    boss_damage(e,damage,false);
    return true;
}
#else
#define BOSS_PX (EOC_SIZE*16)
#define FID_CRIT_PCT 4

/* NPC.HitModifiers.GetDamage: variance, max(d - defense*0.5, 1), crit x2. */
static void boss_strike(Env *e,int base) {
    int twice=2*env_damage_var(e,base)-EOC_DEF;
    if(twice<2) twice=2;
    bool crit=rng_range(&e->rng,1,100)<=FID_CRIT_PCT;
    if(crit) twice*=2;
    boss_damage(e,twice/2,crit);
}

/* ItemCheck_MeleeHitNPCs for the boss (see mobs_swing). The EoC has
   noTileCollide, so Player.ProcessHitAgainstNPC skips the Collision.CanHit
   line-of-sight test: it can be hit while overlapping terrain. */
void boss_swing(Env *e,int X,int Y,int W,int H,int damage,int anim) {
    Boss *b=&e->boss;
    if(!b->active || b->immune>0 || e->attack_cd_ticks>0) return;
    if(!fid_rects(X*FIX_ONE,Y*FIX_ONE,W,H,b->x*TILE_FIX,b->y*TILE_FIX,BOSS_PX,BOSS_PX)) return;
    boss_strike(e,damage);
    b->immune=anim;
    e->attack_cd_ticks=e->item_anim_max*33/100>1?e->item_anim_max*33/100:1;
}

/* Projectile AI_161_RapierStabs: once per stab (bit MAX_MOBS of stab_hits),
   no line-of-sight test against the noTileCollide boss either. */
void boss_stab(Env *e,fix_t x0,fix_t y0,fix_t x1,fix_t y1,int damage) {
    Boss *b=&e->boss;
    if(!b->active || (e->stab_hits>>MAX_MOBS&1u)) return;
    fix_t bx=b->x*TILE_FIX,by=b->y*TILE_FIX;
    if(!(bx<x1 && x0<bx+BOSS_PX*FIX_ONE && by<y1 && y0<by+BOSS_PX*FIX_ONE)) return;
    e->stab_hits|=1u<<MAX_MOBS;
    boss_strike(e,damage);
}

/* Player.Update_NPCCollision, every tick: contact damage through Player.Hurt,
   knocked away from the boss centre. */
void boss_contact(Env *e) {
    const Boss *b=&e->boss;
    if(!b->active) return;
    const fix_t px=player_fx(e),py=player_fy(e);
    if(!fid_rects(px,py,PLAYER_PX_W,PLAYER_PX_H,b->x*TILE_FIX,b->y*TILE_FIX,BOSS_PX,BOSS_PX)) return;
    int dir=b->x*TILE_FIX+(BOSS_PX/2)*FIX_ONE<px+(PLAYER_PX_W/2)*FIX_ONE?1:-1;
    env_hurt(e,phase2(b)?EOC_DMG2:EOC_DMG1,dir,"Eye of Cthulhu");
}
#endif
