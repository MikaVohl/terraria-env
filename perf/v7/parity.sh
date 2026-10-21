#!/bin/sh
# v7 parity: this branch's builds of the frozen v7 sources against the live v7
# library (~/Projects/RL/builds/v7, built from the same sources with main's capi.c).
cd "$(dirname "$0")"
export HIP_VISIBLE_DEVICES=7
LIVE=${LIVE:-$HOME/Projects/RL/builds/v7/python/terraria_lite/libterraria.so}
G=build/gs_main   # compiled against the v7 headers
mkdir -p logs
taskset -c 368-383 $G cpuparity $PWD/build/libterraria.so $LIVE 4096 6000 10 1000 > logs/cpuparity_capi_vs_live.log 2>&1
taskset -c 368-383 $G cpuparity $PWD/build-lw/libterraria.so $LIVE 4096 6000 10 1000 > logs/cpuparity_lightwindow_vs_live.log 2>&1
taskset -c 368-383 build/gs_main parity $LIVE 4096 6000 10 1000 1 > logs/gpu_vs_live_gpureset.log 2>&1
taskset -c 368-383 build/gs_main worldparity $LIVE 70000000 524288 > logs/worldparity_vs_live.log 2>&1
