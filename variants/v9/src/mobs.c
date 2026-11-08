/* Regular mobs (design section 5): spawning by layer and time of day, one AI
   function per kind, contact damage, melee hits and drops. All state is in
   Env.mobs; every random draw comes from Env.rng. Knobs live in env.h. */
#include <stdlib.h>

#include "env.h"
#include "rng.h"

static const int MOB_HP[MOB_KINDS] = {0,SLIME_HP,BAT_HP,ZOMBIE_HP,DEMON_EYE_HP,SKELETON_HP};
static const int MOB_DMG[MOB_KINDS] = {0,SLIME_DMG,BAT_DMG,ZOMBIE_DMG,DEMON_EYE_DMG,SKELETON_DMG};
static const char *const MOB_NAME[MOB_KINDS] = {"","Blue Slime","Cave Bat","Zombie","Demon Eye","Skeleton"};

int mob_max_hp(int kind) { return kind>0 && kind<MOB_KINDS ? MOB_HP[kind] : 1; }

static inline bool solid_at(const Env *e,int x,int y) { return tile_solid(tile_at(e,x,y)); }

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
        e->mobs[i]=(Mob){x,y,MOB_HP[kind],0,0,1,kind};
        return;
    }
}

/* ---- per-kind AI --------------------------------------------------------- */

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
        if(is_body(e,m->x,m->y)) env_hurt(e,MOB_DMG[m->kind],MOB_NAME[m->kind]);
    }
}

/* Drops and achievements. Bats are not scored in v9. */
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
        if(m->hp<=0) {
            killed(e,m);
            SAY(e,"%s defeated",MOB_NAME[m->kind]);
            m->kind=MOB_NONE;
        } else {
            int nx=m->x+e->facing;
            if(!solid_at(e,nx,m->y)) m->x=nx;
            SAY(e,"hit %s: %d hp",MOB_NAME[m->kind],m->hp);
        }
    }
}

void mobs_dawn(Env *e) {
    for(int i=0;i<MAX_MOBS;i++) if(e->mobs[i].kind==MOB_DEMON_EYE) e->mobs[i].kind=MOB_NONE;
}
