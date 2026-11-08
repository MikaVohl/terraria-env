#!/bin/sh
# v10 CPU training smoke (build-v10, INV_LOG=1): the v10_gen_g9999 / v10_shaped_g9999
# arms of tools/explore_screen.py with the CUDA-only options dropped
# (--collect-device cuda, --compile, --bf16, --fused-adam, --async-evaluation,
# --compile-all) and the cpu layout; 2,097,152 steps, validation every 1,048,576.
cd "$(dirname "$0")/../.." || exit 2
OUT=experiments/v10-smoke-20261108
export TERRARIA_LITE_LIB=$PWD/perf/v7/build-v10/libterraria.so PYTHONPATH=python
PKG="--architecture targets --gamma .999 --gae-lambda .99 --entropy .03 --envs 64 --rollout 128 \
 --validation-seed-start 23000001 --validation-episodes 128 --test-seed-start 25000001 \
 --device cpu --collect-threads 1 --threads 3"
COMMON="--potential 3 --envs 1024 --minibatches 16 --sim-workers 4 --native-autoreset --compact-obs"
GEN="$COMMON --potential 0 --novelty .01 --unimix .01 --gamma .9999"
SHAPED="$COMMON --potential-mode frontier --novelty .01 --unimix .01 --gamma .9999"
run() { .venv/bin/python tools/iterate_ppo.py --out $OUT/runs/$1-2001 --seed 2001 --steps 2097152 --interval 1048576 $PKG $2 \
        > $OUT/logs/$1-2001.log 2>&1; }
run v10_gen_g9999 "$GEN" &
run v10_shaped_g9999 "$SHAPED" &
wait
