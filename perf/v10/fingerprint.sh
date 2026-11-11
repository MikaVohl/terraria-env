#!/bin/sh
# Trainer bit-identity: perf/bench_trainer.py SHA (final parameters + telemetry) on the deterministic
# exact path with the v10 shaped arm's shaping (frontier potential 3, novelty .01, unimix .01,
# gamma .9999), for one or more python trees.
#   sh perf/v10/fingerprint.sh LABEL=PYTHONPATH [LABEL=PYTHONPATH ...]
# Env: ITERS (6), SEED (901), LIB (perf/v7/build-v10), GPU (4), CPUS (136-159), EXTRA (more key=value)
ITERS=${ITERS:-6}; SEED=${SEED:-901}; LIB=${LIB:-perf/v7/build-v10}; GPU=${GPU:-4}; CPUS=${CPUS:-136-159}
PY=${PY:-$HOME/Projects/RL/.venv/bin/python}
for spec in "$@"; do
  label=${spec%%=*}; path=${spec#*=}
  HIP_VISIBLE_DEVICES=$GPU PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$path TERRARIA_LITE_LIB=$PWD/$LIB/libterraria.so \
    taskset -c "$CPUS" $PY perf/bench_trainer.py --envs 1024 --iters "$ITERS" --seed "$SEED" --label "$label" \
    --set native_autoreset=1 compact_obs=1 potential_mode=frontier novelty_coef=0.01 unimix=0.01 gamma=0.9999 $EXTRA \
    2>&1 | grep BENCH | python3 -c 'import sys,json; d=json.loads(sys.stdin.read()[6:]); print(d["label"], d["result_sha256"], "sps", d["steady_sps"], "collect", d["collect_s_per_iter"], "learn", d["learn_s_per_iter"])'
done
