#!/bin/sh
# Trainer throughput for the exact options at 1024 and 4096 envs (GPU 7, 16 threads).
# Main-branch package first (true "before"), then this branch with flags.
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1 HIP_VISIBLE_DEVICES=7 OMP_NUM_THREADS=4
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
MAIN=${MAIN:-$HOME/Projects/RL/python}
run() { root=$1; shift; PYTHONPATH=$root taskset -c 368-383 $PY perf/bench_trainer.py "$@" 2>&1 | grep '^BENCH'; }
for n in 1024 4096; do
  it=6; [ $n = 4096 ] && it=5
  run $MAIN --envs $n --iters $it --label main
  run python --envs $n --iters $it --label branch-default
  run python --envs $n --iters $it --label native --set native_autoreset=1
  run python --envs $n --iters $it --label compact --set compact_obs=1
  run python --envs $n --iters $it --label native+compact --set native_autoreset=1 compact_obs=1
done
