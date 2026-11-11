#!/usr/bin/env bash
# luna-factors 2026-11-10, phase A (screening): gpt-6-luna, default-v2 + one declared factor at a time,
# 10 game-minutes, paused clock unless the factor is the clock; worlds 401 + 402 first, then 403 (WORLDS=3).
# Writes queue jobs (tools/parallel_queue.py) via tools/dg_job.py. Run on Omarchy from ~/Projects/TerrariaBench.
set -eu
C=runs/luna-factors-2026-11-10
S=600
job() {  # name model effort clock world cap [factor flags...]
  local name=$1 model=$2 effort=$3 clock=$4 world=$5 cap=$6; shift 6
  .venv/bin/python tools/dg_job.py "$name" unified "$model" "$effort" "$clock" "lf-v07-3200040$world" $S "$cap" \
    --profile default-v2 --campaign $C --campaign-profile luna-factors "$@" > /dev/null
}
L=gpt-6-luna
for w in ${WORLDS:-1 2}; do
  job "a00-base-pa-w40$w"     $L low  paused   $w 0.6
  job "a01-rt-w40$w"          $L low  realtime $w 0.6
  job "a02-grace2-w40$w"      $L low  realtime $w 0.6 --think-grace 2
  job "a03-eff-none-w40$w"    $L none paused   $w 0.6
  job "a04-eff-med-w40$w"     $L medium paused $w 0.8
  job "a05-eff-high-w40$w"    $L high paused   $w 1.2
  job "a06-hostoff-w40$w"     $L low  paused   $w 0.6 --hostile-damage off
  job "a07-know-w40$w"        $L low  paused   $w 0.6 --knowledge-card
  job "a08-feedback-w40$w"    $L low  paused   $w 0.6 --progress-feedback
  job "a09-notes-w40$w"       $L low  paused   $w 0.6 --notes
  job "a10-keep1-w40$w"       $L low  paused   $w 0.6 --keep-images 1 --image-block 1
  job "a11-obs512-w40$w"      $L low  paused   $w 0.6 --obs-size 512
  job "a12-norm-w40$w"        $L low  paused   $w 0.6 --coords normalized
  job "a13-max4-w40$w"        $L low  paused   $w 0.6 --max-actions 4
  job "a14-noctrl-w40$w"      $L low  paused   $w 0.6 --controls-card off
  job "a15-ctx30k-w40$w"      $L low  paused   $w 0.6 --max-context-tokens 30000
  job "a16-split-w40$w"       $L low  paused   $w 0.6 --tool-set split
  job "a17-luna56-pa-w40$w"   gpt-5.6-luna low paused $w 0.8
done
ls ~/tb-queue/dg-jobs | wc -l
