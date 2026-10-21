#!/bin/sh
# Short learning checks for options that change floating-point results or the
# algorithm: 32M steps at 1024 envs per arm and seed (tools/iterate_ppo.py,
# explore_screen's pot_e1024 settings, validation seeds 23000001.., eval on CPU).
# Two runs at a time on GPU 7, 8 CPU threads each.
# Usage: sh perf/learning_check.sh <arm>...   (arms below; results in perf/runs/)
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1 HIP_VISIBLE_DEVICES=7 OMP_NUM_THREADS=2
export TORCHINDUCTOR_CACHE_DIR=$PWD/perf/.inductor
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
SEEDS=${SEEDS:-"901 902"}
BASE="--architecture targets --gamma .999 --gae-lambda .99 --entropy .03 --envs 1024 --rollout 128
 --minibatches 16 --potential 3 --steps 33554432 --interval 8388608
 --validation-seed-start 23000001 --validation-episodes 128 --test-seed-start 25000001
 --device cuda --collect-device cuda --evaluation-device cpu --threads 2 --sim-workers 6
 --native-autoreset --compact-obs"
flags() {
  case $1 in
    control) echo "" ;;
    compile) echo "--compile" ;;
    bf16) echo "--bf16 --fused-adam" ;;
    fast) echo "--compile --bf16 --fused-adam" ;;
    epochs2) echo "--epochs 2" ;;
    epochs1) echo "--epochs 1" ;;
    *) echo "unknown arm $1" >&2; exit 2 ;;
  esac
}
mkdir -p perf/runs
jobs_running=0
for arm in "$@"; do
  for seed in $SEEDS; do
    out=perf/runs/$arm-s$seed
    [ -e $out ] && continue
    cpus=368-375; [ $((jobs_running % 2)) = 1 ] && cpus=376-383
    PYTHONPATH=python taskset -c $cpus $PY tools/iterate_ppo.py --out $out --seed $seed $BASE $(flags $arm) \
      > perf/runs/$arm-s$seed.log 2>&1 &
    jobs_running=$((jobs_running + 1))
    [ $((jobs_running % 2)) = 0 ] && wait
  done
done
wait
