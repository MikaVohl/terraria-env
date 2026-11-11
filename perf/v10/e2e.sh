#!/bin/sh
# End-to-end wall clock of the production arm (64M steps, evaluations at 32M and 64M, async), base
# (4ef5afa python + library, kept under perf/v10/base*) vs this branch: one run alone on GPU 4, then
# two runs sharing GPU 4 as in production (each on its own 24 cores). Prepare the base with
#   mkdir -p perf/v10/base perf/v10/base-lib && git archive 4ef5afa python | tar -x -C perf/v10/base
#   (and a 4ef5afa build of perf/v7/build-v10/libterraria.so copied to perf/v10/base-lib/)
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
ARGV=$(PYTHONPATH=python TERRARIA_LITE_LIB=$PWD/perf/v7/build-v10/libterraria.so $PY perf/v10/arm_argv.py v10_shaped_g9999 gpu | tr '\n' ' ')
mkdir -p perf/v10/e2e
run() {  # name pythonpath lib cpus
  rm -rf perf/v10/e2e/$1
  HIP_VISIBLE_DEVICES=4 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$2 TERRARIA_LITE_LIB=$PWD/$3/libterraria.so \
    timeout 1200 taskset -c $4 $PY tools/iterate_ppo.py --out perf/v10/e2e/$1 --seed 901 --steps 67108864 \
    --interval 33554432 $ARGV > perf/v10/e2e/$1.log 2>&1
}
for v in base new; do
  if [ $v = base ]; then P=perf/v10/base/python; L=perf/v10/base-lib; else P=python; L=perf/v7/build-v10; fi
  run solo_$v $P $L 136-159
  run pairA_$v $P $L 136-159 & run pairB_$v $P $L 160-183 & wait
done
for f in perf/v10/e2e/*.log; do echo "$f: $(grep Completed $f) $(python3 -c "import json;d=json.load(open('${f%.log}/summary.json'));print('train_sps',d['sps'],'collect',round(d['collection_seconds'],1),'opt',round(d['optimisation_seconds'],1))")"; done
