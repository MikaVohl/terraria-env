#!/usr/bin/env bash
# astra-probe 2026-11-11: gpt-6-astra (deployment gpt-6-astra-2026-09-03) on default-v2, worlds lf-v07-3200040x.
# $10 hard cap on the gateway for the whole campaign (conservative: reported + uncertain + running caps).
#   PHASE=probe   ./experiments/astra-probe-2026-11-11.sh   # 90 game-s cost probe, medium, paused, w404
#   PHASE=main CAP=<usd> WORLD=<n> [EFFORT=medium SECONDS_GAME=1200] ./experiments/astra-probe-2026-11-11.sh
set -eu
C=runs/astra-probe-2026-11-11
job() {  # name effort clock world seconds cap [factor flags...]
  local name=$1 effort=$2 clock=$3 world=$4 s=$5 cap=$6; shift 6
  .venv/bin/python tools/dg_job.py "$name" unified gpt-6-astra "$effort" "$clock" "lf-v07-3200040$world" $s "$cap" \
    --profile default-v2 --campaign $C --campaign-profile astra-probe "$@" > /dev/null
}
case "$PHASE" in
  probe) job "p00-med-pa-probe-w404" medium paused 4 90 3.0 ;;
  main)  job "m01-${EFFORT:-medium}-pa-20m-w40$WORLD" "${EFFORT:-medium}" paused "$WORLD" "${SECONDS_GAME:-1200}" "$CAP" ;;
esac
ls ~/tb-queue/dg-jobs
