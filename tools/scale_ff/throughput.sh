#!/bin/bash
# Throughput per model size on the max2 path: 1 run alone on HIP 2, 2 concurrent runs on HIP 3.
cd ~/Projects/RL-scaleff
export PYTHONPATH=$PWD/python TERRARIA_LITE_LIB=$PWD/perf/v7/build-lw2/libterraria.so
PY=~/Projects/RL/.venv/bin/python
OUT=~/sff/tput; mkdir -p $OUT
MAX2="native_autoreset=1 compact_obs=1 compile=1 bf16=1 fused_adam=1 compile_all=1"
while read label sets; do
  [ -z "$label" ] && continue
  HIP_VISIBLE_DEVICES=2 $PY perf/bench_trainer.py --iters 12 --label "$label/1" --set $MAX2 $sets > $OUT/$label-1.log 2>&1 &
  HIP_VISIBLE_DEVICES=3 $PY perf/bench_trainer.py --iters 12 --label "$label/2a" --set $MAX2 $sets > $OUT/$label-2a.log 2>&1 &
  HIP_VISIBLE_DEVICES=3 $PY perf/bench_trainer.py --iters 12 --seed 902 --label "$label/2b" --set $MAX2 $sets > $OUT/$label-2b.log 2>&1 &
  wait
  grep -h BENCH $OUT/$label-*.log | sed 's/^BENCH //' >> $OUT/bench.jsonl
done <<'CONFIGS'
t128 hidden=128
t256 hidden=256
t512 hidden=512
t1024 hidden=1024
t2048 hidden=2048
t512c64 hidden=512 cell_width=64
t512c128 hidden=512 cell_width=128
t512d3 hidden=512 depth=3
t512d4 hidden=512 depth=4
t2048c128d4 hidden=2048 cell_width=128 depth=4
m512 architecture=mlp hidden=512
m1024 architecture=mlp hidden=1024
m2048 architecture=mlp hidden=2048
CONFIGS
echo done > $OUT/DONE
