#!/bin/bash
# Launch K copies of the pot_e1024_max2 trainer on one GPU under spike_probe.py.
#   tools/gpushare/trainer_pair.sh <name> <hip-gpu> <copies> <steps> [extra iterate_ppo flags...]
# Flags are the explore_screen pot_e1024_max2 package (targets, hidden 128);
# later extra flags override earlier ones. Removing a boolean max2 flag: set
# NOFLAGS to a space-separated list (e.g. NOFLAGS="--compile-all --bf16"). CU_MASKS: one
# HSA_CU_MASK value per copy (e.g. CU_MASKS="0:0-127 0:128-255").
# Env passes through (e.g. per-process ROCm settings). Output: ~/gsb/<name>/<copy>/.
set -e
name=$1 gpu=$2 copies=$3 steps=$4; shift 4
root=$(cd "$(dirname "$0")/../.." && pwd)
base=(--architecture targets --gamma .999 --gae-lambda .99 --entropy .03 --envs 64 --rollout 128
      --validation-seed-start 23000001 --validation-episodes 128 --test-seed-start 25000001
      --device cuda --collect-device cpu --evaluation-device cpu --threads 1 --sim-workers 1)
max2=(--potential 3 --envs 1024 --minibatches 16 --collect-device cuda --sim-workers 12 --threads 4
      --native-autoreset --compact-obs --compile --bf16 --fused-adam --async-evaluation --compile-all)
flags=()
for f in "${max2[@]}"; do
  case " $NOFLAGS " in *" $f "*) continue;; esac
  flags+=("$f")
done
masks=($CU_MASKS)
for c in $(seq 1 "$copies"); do
  mask=${masks[$((c - 1))]:-}
  out=$HOME/gsb/$name/$c
  mkdir -p "$out"
  seed=$((1800 + c))
  (cd "$root" && env ${mask:+HSA_CU_MASK=$mask} PYTHONPATH=$root/python \
    TERRARIA_LITE_LIB=$root/perf/v7/build-lw2/libterraria.so HIP_VISIBLE_DEVICES=$gpu GSB_OUT=$out \
    nohup "$HOME/Projects/RL/.venv/bin/python" -u tools/gpushare/spike_probe.py \
    --out "$out/run" --seed $seed --steps "$steps" --interval 33554432 "${base[@]}" "${flags[@]}" "$@" \
    < /dev/null > "$out/log" 2>&1 &)
  echo "$name copy $c seed $seed -> $out"
done
