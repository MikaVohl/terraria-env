#!/usr/bin/env bash
# luna-factors 2026-11-10, phase B (does a factor effect generalize to another vendor?): Claude Haiku 5.5 (thinking
# medium = the default-v2 Haiku setting, unforced), 10 game-minutes, paused unless the factor is the clock, worlds 401 + 402;
# and phase D (agent system): gpt-6-luna (low) planner + TypeSafe Jev 1.14 executor (combo.py), both clocks.
set -eu
C=runs/luna-factors-2026-11-10
S=600
job() {  # name kind model effort clock world cap [factor flags...]
  local name=$1 kind=$2 model=$3 effort=$4 clock=$5 world=$6 cap=$7; shift 7
  .venv/bin/python tools/dg_job.py "$name" "$kind" "$model" "$effort" "$clock" "lf-v07-3200040$world" $S "$cap" \
    --profile default-v2 --campaign $C --campaign-profile luna-factors "$@" > /dev/null
}
H=claude-haiku-5-5
for w in ${WORLDS:-1 2}; do
  job "b00-haiku-base-pa-w40$w"     gateway $H medium paused   $w 1.0
  job "b01-haiku-rt-w40$w"          gateway $H medium realtime $w 0.6
  job "b06-haiku-hostoff-w40$w"     gateway $H medium paused   $w 1.0 --hostile-damage off
  job "b07-haiku-know-w40$w"        gateway $H medium paused   $w 1.0 --knowledge-card
  job "b08-haiku-feedback-w40$w"    gateway $H medium paused   $w 1.0 --progress-feedback
  job "b09-haiku-notes-w40$w"       gateway $H medium paused   $w 1.0 --notes
  job "d01-combo-luna6-jev-rt-w40$w" combo gpt-6-luna low realtime $w 0.4
  job "d02-combo-luna6-jev-pa-w40$w" combo gpt-6-luna low paused   $w 0.4
done
ls ~/tb-queue/dg-jobs | wc -l
