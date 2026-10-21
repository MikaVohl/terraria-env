#!/bin/sh
# Measurement sweep for REPORT.md (simulator + pipeline microbenchmarks).
# GPU 7 only, <= 16 CPU threads. Usage: sh sweep.sh > logs/sweep.log 2>&1
# MAIN_LIB: an unmodified main-branch library for before/after CPU numbers.
cd "$(dirname "$0")"
export HIP_VISIBLE_DEVICES=7 OMP_NUM_THREADS=8 PYTHONDONTWRITEBYTECODE=1
export TORCHINDUCTOR_CACHE_DIR="$PWD/.inductor"
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
MAIN_LIB=${MAIN_LIB:-$HOME/Projects/RL/python/terraria_lite/libterraria.so}
LIB=../../python/terraria_lite/libterraria.so
CPU="taskset -c 368-383"
echo "== A. GPU simulator (random legal actions, pool resets) =="
for n in 4096 16384 65536 262144; do $CPU ./gs_main bench $n 300 pool 256 | tail -1; done
echo "== A2. reset strategies at 65536 envs =="
for m in step auto pool; do $CPU ./gs_main bench 65536 300 $m 256 | tail -1; done
echo "== A3. + float32 one-hot encode kernel =="
$CPU ./gs_main bench 65536 200 pool+enc 256 | tail -1
echo "== B. per-phase profile =="
$CPU ./gs_main profile 65536 50 64; $CPU ./gs_main profile 262144 30 64
echo "== C. CPU library throughput (tl_batch_step_flat): main-branch lib vs this branch =="
for lib in $MAIN_LIB $LIB; do
  taskset -c 368 ./cpu_bench $lib 256 3000 1 1
  $CPU ./cpu_bench $lib 4096 400 16 1
done
echo "== D. pipeline microbenchmarks =="
$CPU $PY pipeline.py transfer 2>&1 | grep '^{'
$CPU $PY pipeline.py infer 2>&1 | grep '^{'
$CPU $PY pipeline.py learn 2>&1 | grep '^{'
echo "== done =="
