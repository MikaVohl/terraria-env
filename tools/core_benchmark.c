/* Identical harness for frozen v1 and v2: mask, step, observe, autoreset.
   Fixed 64-world cohort, deterministic uniform-legal action sampler. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "env.h"
#include "rng.h"
#ifndef ENV_VERSION
#define ENV_VERSION 1
#endif
static double now(void) {
 struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec*1e-9;
}
int main(void) {
 const int n=64,steps=262144; Env *env=calloc(n,sizeof *env);
 if(!env) return 1;
 double times[3]; unsigned long long checksum=0;
 for(int repeat=0;repeat<3;repeat++) {
  for(int i=0;i<n;i++) { env_init(&env[i],(EnvConfig){3000}); env_reset(&env[i],100+i); }
  uint64_t rng=54321; double start=now();
  for(int t=0;t<steps/n;t++) for(int i=0;i<n;i++) {
   uint8_t mask[ACT_COUNT]; Obs obs; int count=0,action=0;
   env_action_mask(&env[i],mask);
   for(int a=0;a<ACT_COUNT;a++) count+=mask[a];
   int pick=(int)rng_below(&rng,(uint32_t)count);
   for(int a=0;a<ACT_COUNT;a++) if(mask[a] && pick--==0) { action=a; break; }
   env_step(&env[i],action); env_obs(&env[i],&obs); checksum+=obs.tile[VIEW_CELLS/2];
   if(env[i].terminated || env[i].truncated) env_reset(&env[i],100000+(uint64_t)t*n+i);
  }
  times[repeat]=now()-start;
 }
 double median=times[0]+times[1]+times[2];
 double lo=times[0],hi=times[0];
 for(int i=1;i<3;i++) { if(times[i]<lo) lo=times[i]; if(times[i]>hi) hi=times[i]; }
 median-=lo+hi;
 printf("{\"environment_version\":%d,\"env_bytes\":%zu,\"envs\":64,\"transitions_per_repeat\":%d,\"seconds\":[%.6f,%.6f,%.6f],\"median_sps\":%.1f,\"checksum\":%llu}\n",
  ENV_VERSION,sizeof *env,steps,times[0],times[1],times[2],steps/median,checksum);
 free(env); return 0;
}
