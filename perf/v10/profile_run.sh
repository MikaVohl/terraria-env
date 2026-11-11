#!/bin/sh
# One profiled production-arm run on eg18 (GPU and cores fixed below), plus a CPU/GPU utilisation trace.
#   sh perf/v10/profile_run.sh NAME [--sync] -- [extra iterate_ppo flags, appended after the arm's]
# Env: ARM (v10_shaped_g9999), LIB (perf/v7/build-v10), STEPS (16777216), INTERVAL (8388608), SEED (901),
#      GPU (4), CPUS (136-159), PYP (python: the package tree to run).
set -e
NAME=$1; shift
PRE=""; while [ $# -gt 0 ] && [ "$1" != "--" ]; do PRE="$PRE $1"; shift; done; [ "$1" = "--" ] && shift
ARM=${ARM:-v10_shaped_g9999}; LIB=${LIB:-perf/v7/build-v10}; STEPS=${STEPS:-16777216}; INTERVAL=${INTERVAL:-8388608}
SEED=${SEED:-901}; GPU=${GPU:-4}; CPUS=${CPUS:-136-159}
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}; PYP=${PYP:-python}
OUT=perf/v10/runs/$NAME; rm -rf "$OUT"; mkdir -p "$OUT"
export HIP_VISIBLE_DEVICES=$GPU PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PYP TERRARIA_LITE_LIB=$PWD/$LIB/libterraria.so
ARGV=$($PY perf/v10/arm_argv.py "$ARM" gpu | tr '\n' ' ')
echo "taskset -c $CPUS profile_train $PRE -- --out $OUT/run --seed $SEED --steps $STEPS --interval $INTERVAL $ARGV $*" > "$OUT/cmd.txt"
taskset -c "$CPUS" $PY perf/profile_train.py $PRE -- --out "$OUT/run" --seed "$SEED" --steps "$STEPS" --interval "$INTERVAL" \
  $ARGV "$@" > "$OUT/log.txt" 2>&1 &
PID=$!
$PY perf/v10/util_sample.py $PID "$GPU" "$OUT/util.jsonl" &
wait $PID; RC=$?
wait
grep PROFILE "$OUT/log.txt" | tail -1
exit $RC
