#!/bin/sh
# Concurrent runs on GPU 7 sharing 16 CPU threads (perf/bench_concurrency.py).
cd "$(dirname "$0")/.."
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
for cfg in exact max gpu gpu-max; do
  for n in 1024 2048; do
    HIP_VISIBLE_DEVICES=7 $PY perf/bench_concurrency.py --envs $n --runs 1 2 4 --config $cfg 2>&1 | grep '^CONC'
  done
done
