#!/bin/sh
# Trainer throughput for options that change floating-point results or the
# algorithm, all on top of the exact native_autoreset + compact_obs path.
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1 HIP_VISIBLE_DEVICES=7 OMP_NUM_THREADS=4
export TORCHINDUCTOR_CACHE_DIR=${TORCHINDUCTOR_CACHE_DIR:-$PWD/perf/.inductor}
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
EX="native_autoreset=1 compact_obs=1"
run() { PYTHONPATH=python taskset -c 368-383 $PY perf/bench_trainer.py "$@" 2>&1 | grep '^BENCH'; }
for n in 1024 4096; do
  it=8; [ $n = 4096 ] && it=6
  run --envs $n --iters $it --label exact --set $EX
  run --envs $n --iters $it --label compile --set $EX compile=1
  run --envs $n --iters $it --label bf16 --set $EX bf16=1
  run --envs $n --iters $it --label fused_adam --set $EX fused_adam=1
  run --envs $n --iters $it --label compile+bf16+fused --set $EX compile=1 bf16=1 fused_adam=1
  run --envs $n --iters $it --label epochs2 --epochs 2 --set $EX
  run --envs $n --iters $it --label epochs1 --epochs 1 --set $EX
  run --envs $n --iters $it --label minibatches4 --minibatches 4 --set $EX
done
