#!/bin/bash
# Run policy_diagnostics on the final checkpoint of every finished run (loops until killed).
cd ~/Projects/RL-scaleff
export PYTHONPATH=$PWD/python TERRARIA_LITE_LIB=$PWD/perf/v7/build-lw2/libterraria.so
while true; do
  for run in ~/sff/*/runs/*; do
    [ -f $run/summary.json ] || continue
    [ -f $run/diagnostics.json ] && continue
    steps=$(~/Projects/RL/.venv/bin/python -c "import json;print(json.load(open('$run/protocol.json'))['actual_steps'])")
    nice ~/Projects/RL/.venv/bin/python tools/policy_diagnostics.py $run/step-$steps.pt --out $run/diagnostics.tmp \
      --episodes 128 --seed-start 23000001 > $run/diagnostics.log 2>&1 && mv $run/diagnostics.tmp $run/diagnostics.json && ln -sf diagnostics.json $run/diag.json
  done
  sleep 60
done
