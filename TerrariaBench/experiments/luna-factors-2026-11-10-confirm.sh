#!/usr/bin/env bash
# luna-factors 2026-11-10, phase C (confirmation at the benchmark length): gpt-6-luna, default-v2, 20 game-minutes,
# worlds 401/402/403; reasoning effort low vs high in both clocks, high + knowledge card (paused).
# Also Haiku thinking off (forced tool call) at 10 min for the effort factor on the second vendor (phase B).
set -eu
C=runs/luna-factors-2026-11-10
job() {  # name kind model effort clock world seconds cap [factor flags...]
  local name=$1 kind=$2 model=$3 effort=$4 clock=$5 world=$6 s=$7 cap=$8; shift 8
  .venv/bin/python tools/dg_job.py "$name" "$kind" "$model" "$effort" "$clock" "lf-v07-3200040$world" $s "$cap" \
    --profile default-v2 --campaign $C --campaign-profile luna-factors "$@" > /dev/null
}
L=gpt-6-luna
if [ -z "${FOLLOWUP:-}" ]; then
for w in 1 2; do
  job "b03-haiku-eff-none-w40$w" gateway claude-haiku-5-5 none paused $w 600 1.0
done
for w in 1 2 3; do
  job "e01-low-pa-20m-w40$w"       unified $L low    paused   $w 1200 0.8
  job "e02-high-pa-20m-w40$w"      unified $L high   paused   $w 1200 1.5
  job "e03-low-rt-20m-w40$w"       unified $L low    realtime $w 1200 0.8
  job "e04-high-rt-20m-w40$w"      unified $L high   realtime $w 1200 1.5
  job "e06-high-know-pa-20m-w40$w" unified $L high   paused   $w 1200 1.5 --knowledge-card
done
fi
# Follow-up after the 20-min results (high effort placed benches): bounded-staleness real time with high effort,
# and a fourth world (404) for high vs low paused.
for w in 1 2 3; do
  job "f01-high-grace2-rt-20m-w40$w" unified $L high realtime $w 1200 1.5 --think-grace 2
done
job "f02-high-pa-20m-w404" unified $L high paused 4 1200 1.5
job "f03-low-pa-20m-w404"  unified $L low  paused 4 1200 0.8
ls ~/tb-queue/dg-jobs | wc -l
