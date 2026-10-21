#!/bin/sh
# (1) GPU simulator backend vs the exact CPU path at 1024-16384 envs;
# (2) v7: live v7 library + main's package (what live runs use) vs this branch's
#     v7 builds (perf/v7) with the exact options and the GPU backend.
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1 HIP_VISIBLE_DEVICES=7 OMP_NUM_THREADS=4
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
MAIN=${MAIN:-$HOME/Projects/RL/python}
V7LIVE=${V7LIVE:-$HOME/Projects/RL/builds/v7/python/terraria_lite/libterraria.so}
run() { root=$1; shift; PYTHONPATH=$root taskset -c 368-383 $PY perf/bench_trainer.py "$@" 2>&1 | grep '^BENCH'; }
for n in 1024 2048 4096 16384; do
  it=6; [ $n -ge 4096 ] && it=5; [ $n = 16384 ] && it=4
  run python --envs $n --iters $it --label cpu-exact --set native_autoreset=1 compact_obs=1
  run python --envs $n --iters $it --label gpu-sim --set sim_backend=gpu compact_obs=1
done
for n in 1024 4096; do
  it=6; [ $n = 4096 ] && it=5
  TERRARIA_LITE_LIB=$V7LIVE run $MAIN --envs $n --iters $it --label v7-live-main
  TERRARIA_LITE_LIB=$PWD/perf/v7/build/libterraria.so run python --envs $n --iters $it --label v7-perf-default
  TERRARIA_LITE_LIB=$PWD/perf/v7/build/libterraria.so run python --envs $n --iters $it --label v7-perf-exact --set native_autoreset=1 compact_obs=1
  TERRARIA_LITE_LIB=$PWD/perf/v7/build-lw/libterraria.so run python --envs $n --iters $it --label v7-perf-exact-lightwindow --set native_autoreset=1 compact_obs=1
  TERRARIA_LITE_LIB=$PWD/perf/v7/build/libterraria.so TERRARIA_GPUSIM_LIB=$PWD/perf/v7/build/libgpusim.so \
    run python --envs $n --iters $it --label v7-gpu-sim --set sim_backend=gpu compact_obs=1
done
