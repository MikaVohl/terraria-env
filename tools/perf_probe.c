/* Experimental only: separate shared library, never linked into production.
 * Fixed-size cache is intentionally a benchmark prototype, not a lifecycle API.
 */
#include <stdlib.h>
#include <string.h>
#include "env.h"
#ifdef __APPLE__
#include <dispatch/dispatch.h>
#endif

void light_reference(Env *e);
typedef struct { const Env *key; unsigned char tiles[WORLD_H][WORLD_W];
    unsigned char light[WORLD_H][WORLD_W]; } Cache;
static Cache cache[512];
static int used;

void light_recompute(Env *e) {
#ifndef PROBE_CACHE
    light_reference(e);
#else
    int k;
    for (k=0;k<used;k++) if (cache[k].key==e) break;
    if (k==used) {
        if (used==512) abort();
        cache[k].key=e; used++;
        memset(cache[k].tiles,255,sizeof e->tiles);
    }
    Cache *c=&cache[k];
    if (memcmp(c->tiles,e->tiles,sizeof e->tiles)) {
        Env tmp=*e;
        tmp.px=-100; tmp.py=-100; /* reference computes terrain-only lighting */
        light_reference(&tmp);
        memcpy(c->tiles,e->tiles,sizeof e->tiles);
        memcpy(c->light,tmp.light,sizeof e->light);
    }
    memcpy(e->light,c->light,sizeof e->light);
    /* Max-composition is exact: propagation attenuates independently of source.
       Only the player's small light cone needs updating on movement. */
    int queue[WORLD_W*WORLD_H], head=0, tail=0;
    for(int i=0;i<PLAYER_H;i++) {
        int x=e->px,y=e->py-i;
        if(in_bounds(x,y) && e->light[y][x]<PLAYER_LIGHT) {
            e->light[y][x]=PLAYER_LIGHT;
            if(!tile_opaque((Tile)e->tiles[y][x])) queue[tail++]=y*WORLD_W+x;
        }
    }
    const int dx[4]={1,-1,0,0},dy[4]={0,0,1,-1};
    while(head<tail) {
        int p=queue[head++],x=p%WORLD_W,y=p/WORLD_W;
        int child=e->light[y][x]-1;
        for(int d=0;d<4;d++) {
            int nx=x+dx[d],ny=y+dy[d];
            if(!in_bounds(nx,ny)||e->light[ny][nx]>=child) continue;
            e->light[ny][nx]=(unsigned char)child;
            if(child>1 && !tile_opaque((Tile)e->tiles[ny][nx])) queue[tail++]=ny*WORLD_W+nx;
        }
    }
#endif
}

/* All returned observations are pre-reset, preserving terminal observations.
   Resets remain caller-owned. Buffers are dense arrays of n rows. */
static void serial_batch(Env **envs,int n,const int *actions,Obs *obs,
                 unsigned char *masks,float *rewards,int *done) {
    for(int i=0;i<n;i++) {
        Env *e=envs[i]; env_step(e,actions[i]); env_obs(e,&obs[i]);
        env_action_mask(e,masks+i*ACT_COUNT);
        rewards[i]=e->reward; done[i]=e->terminated+2*e->truncated;
    }
}
static int workers=1;
void probe_workers(int n) { workers=n; }
#ifdef __APPLE__
typedef struct { Env **e; int n; const int *a; Obs *o;
    unsigned char *m; float *r; int *d; } Work;
static void chunk(void *ptr,size_t k) {
    Work *w=ptr; int start=w->n*k/workers,end=w->n*(k+1)/workers;
    serial_batch(w->e+start,end-start,w->a+start,w->o+start,
                 w->m+start*ACT_COUNT,w->r+start,w->d+start);
}
#endif
void probe_batch(Env **envs,int n,const int *actions,Obs *obs,
                 unsigned char *masks,float *rewards,int *done) {
#ifdef __APPLE__
    if(workers>1) {
        Work w={envs,n,actions,obs,masks,rewards,done};
        dispatch_apply_f(workers,dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT,0),&w,chunk);
        return;
    }
#endif
    serial_batch(envs,n,actions,obs,masks,rewards,done);
}
int probe_obs_bytes(void) { return sizeof(Obs); }
int probe_check(Env *e) {
    Env other=*e; light_reference(&other);
    return memcmp(other.light,e->light,sizeof e->light)==0;
}
