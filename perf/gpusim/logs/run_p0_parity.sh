#!/bin/sh
# P0 parity: this branch (patched light.c) vs the UNMODIFIED main-branch library.
cd $(dirname $0)/..
export HIP_VISIBLE_DEVICES=7
MAIN=$HOME/Projects/RL/python/terraria_lite/libterraria.so
MINE=../../python/terraria_lite/libterraria.so
taskset -c 368-383 ./gs_main cpuparity $MINE $MAIN 4096 10000 10 1000 > logs/p0_cpuparity_branch_vs_main.log 2>&1
taskset -c 368-383 ./gs_main parity $MAIN 4096 20000 10 1000 1 > logs/p0_gpu_vs_mainlib_gpureset.log 2>&1
taskset -c 368-383 ./gs_main parity $MAIN 4096 10000 50 1000 0 > logs/p0_gpu_vs_mainlib_illegal50_blob.log 2>&1
taskset -c 368-383 ./gs_main parity $MINE 4096 10000 10 1000 1 > logs/p0_gpu_vs_branchlib_gpureset.log 2>&1
taskset -c 368-383 ./gs_main worldparity $MAIN 10000000 1048576 > logs/p0_worldparity_mainlib_1M.log 2>&1
