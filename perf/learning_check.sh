#!/bin/sh
# Short learning checks for options that change floating-point results or the
# algorithm: 32M steps at 1024 envs per arm and seed (tools/iterate_ppo.py,
# explore_screen's pot_e1024 settings, validation seeds 23000001.., eval on CPU).
# $JOBS runs at a time on GPU $GPU, each pinned to its own slice of $CPUS.
# Usage: sh perf/learning_check.sh <arm>...   (arms below; results in perf/runs/)
#   GPU=0 CPUS=72-95 JOBS=3 SEEDS="901 902 903 904" sh perf/learning_check.sh fast fast_all
cd "$(dirname "$0")/.."
GPU=${GPU:-7}; CPUS=${CPUS:-368-383}; JOBS=${JOBS:-2}
export PYTHONDONTWRITEBYTECODE=1 HIP_VISIBLE_DEVICES=$GPU OMP_NUM_THREADS=2
export TORCHINDUCTOR_CACHE_DIR=$PWD/perf/.inductor
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
SEEDS=${SEEDS:-"901 902"}
BASE="--architecture targets --gamma .999 --gae-lambda .99 --entropy .03 --envs 1024 --rollout 128
 --minibatches 16 --potential 3 --steps 33554432 --interval 8388608
 --validation-seed-start 23000001 --validation-episodes 128 --test-seed-start 25000001
 --device cuda --collect-device cuda --evaluation-device cpu --threads 2 --sim-workers 6
 --native-autoreset --compact-obs"
FAST="--compile --bf16 --fused-adam"
flags() {
  case $1 in
    control) echo "" ;;
    compile) echo "--compile" ;;
    bf16) echo "--bf16 --fused-adam" ;;
    fast) echo "$FAST" ;;
    fast_all) echo "$FAST --compile-all" ;;
    # v7 "25 wall" settings (explore_screen wall_frontier_nov01)
    fn_fast) echo "$FAST --potential-mode frontier --novelty .01" ;;
    fn_fast_all) echo "$FAST --compile-all --potential-mode frontier --novelty .01" ;;
    epochs2) echo "--epochs 2" ;;
    epochs1) echo "--epochs 1" ;;
    *) echo "unknown arm $1" >&2; exit 2 ;;
  esac
}
lo=${CPUS%-*}; hi=${CPUS#*-}; share=$(( (hi - lo + 1) / JOBS ))
mkdir -p perf/runs
slot=0
for arm in "$@"; do
  for seed in $SEEDS; do
    out=perf/runs/$arm-s$seed
    [ -e $out ] && continue
    first=$((lo + slot * share))
    PYTHONPATH=python taskset -c $first-$((first + share - 1)) $PY tools/iterate_ppo.py --out $out --seed $seed $BASE $(flags $arm) \
      > perf/runs/$arm-s$seed.log 2>&1 &
    slot=$((slot + 1))
    [ $slot = $JOBS ] && { wait; slot=0; }
  done
done
wait
