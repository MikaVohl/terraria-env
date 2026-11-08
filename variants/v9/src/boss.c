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
   demonite ore. */
#include <stdlib.h>

#include "env.h"
#include "rng.h"

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

static bool overlaps(const Boss *b,int x0,int y0,int x1,int y1) {
    return b->x<=x1 && b->x+EOC_SIZE-1>=x0 && b->y<=y1 && b->y+EOC_SIZE-1>=y0;
}

void boss_summon(Env *e) {
    Boss *b=&e->boss;
    int side=rng_below(&e->rng,2)?1:-1;
    *b=(Boss){0};
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
    if(overlaps(b,e->px,e->py-PLAYER_H+1,e->px+PLAYER_W-1,e->py))
        env_hurt(e,p2?EOC_DMG2:EOC_DMG1,"Eye of Cthulhu");
}

bool boss_attack(Env *e,int x0,int y0,int x1,int y1,int damage) {
    Boss *b=&e->boss;
    if(!b->active || !overlaps(b,x0,y0,x1,y1)) return false;
    b->hp-=damage;
    if(b->hp<=0) {
        b->active=false; b->hp=0;
        env_give(e,ITEM_DEMONITE_ORE,rng_range(&e->rng,EOC_DEMONITE_MIN,EOC_DEMONITE_MAX));
        env_award(e,ACH_DEFEAT_EOC);
        SAY(e,"the Eye of Cthulhu has been defeated!");
    } else SAY(e,"hit Eye of Cthulhu: %d hp",b->hp);
    return true;
}
