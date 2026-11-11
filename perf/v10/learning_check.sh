#!/bin/sh
# Matched-steps learning check on eg18 GPU 4: two arms of the v10 shaped production arm run side by
# side (two runs per GPU, as in production), one per core range, for each seed in turn.
#   sh perf/v10/learning_check.sh NAME_A "FLAGS_A" NAME_B "FLAGS_B"
# Env: SEEDS ("901 902"), STEPS (134217728), INTERVAL (33554432), GPU (4), CPUS_A (136-159), CPUS_B (160-183)
NA=$1; FA=$2; NB=$3; FB=$4
SEEDS=${SEEDS:-901 902}; STEPS=${STEPS:-134217728}; INTERVAL=${INTERVAL:-33554432}
GPU=${GPU:-4}; CPUS_A=${CPUS_A:-136-159}; CPUS_B=${CPUS_B:-160-183}
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
export HIP_VISIBLE_DEVICES=$GPU PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python TERRARIA_LITE_LIB=$PWD/perf/v7/build-v10/libterraria.so
ARGV=$($PY perf/v10/arm_argv.py v10_shaped_g9999 gpu | tr '\n' ' ')
mkdir -p perf/v10/learn
for s in $SEEDS; do
  for side in A B; do
    if [ $side = A ]; then n=$NA; f=$FA; c=$CPUS_A; else n=$NB; f=$FB; c=$CPUS_B; fi
    rm -rf perf/v10/learn/$n-$s
    timeout 1200 taskset -c $c $PY tools/iterate_ppo.py --out perf/v10/learn/$n-$s --seed $s --steps $STEPS \
      --interval $INTERVAL $ARGV $f > perf/v10/learn/$n-$s.log 2>&1 &
  done
  wait
  grep -h -E "^$NA-$s:|^$NB-$s:|Completed" perf/v10/learn/$NA-$s.log perf/v10/learn/$NB-$s.log
done
