#!/usr/bin/env bash
# Job queue for the 30-minute pilot. Runs ~/tb-queue/jobs/*.sh in name order, one at a time.
# Each job declares its spend cap in a header line:  # cap provider=gateway usd=10
# Before a job starts, campaign spend (tools/pilot_spend.py) plus the job's cap must fit the budget,
# otherwise the job is moved to skipped/. Finished jobs move to done/ with their exit code.
set -u
Q=~/tb-queue
P=~/Projects/TerrariaBench
CAMPAIGN=${CAMPAIGN:-$P/runs/pilot-30min}
BUDGET_GATEWAY=${BUDGET_GATEWAY:-68}
BUDGET_OPENROUTER=${BUDGET_OPENROUTER:-4.8}
mkdir -p $Q/jobs $Q/done $Q/skipped $Q/logs
log() { echo "$(date -Is) $*" | tee -a $Q/queue.log; }
log "queue started (gateway budget $BUDGET_GATEWAY, openrouter budget $BUDGET_OPENROUTER)"
while true; do
  [ -f $Q/STOP ] && { log "STOP file found; exiting"; exit 0; }
  job=$(ls $Q/jobs/*.sh 2>/dev/null | sort | head -1)
  if [ -z "$job" ]; then sleep 20; continue; fi
  name=$(basename "$job" .sh)
  provider=$(grep -m1 -oP '# cap provider=\K\w+' "$job" || echo gateway)
  cap=$(grep -m1 -oP '# cap .*usd=\K[0-9.]+' "$job" || echo 0)
  spent=$(cd $P && .venv/bin/python tools/pilot_spend.py $CAMPAIGN)
  used=$(echo "$spent" | $P/.venv/bin/python -c "import json,sys; print(json.load(sys.stdin)['$provider'])")
  budget=$([ "$provider" = openrouter ] && echo $BUDGET_OPENROUTER || echo $BUDGET_GATEWAY)
  if ! $P/.venv/bin/python -c "import sys; sys.exit(0 if $used + $cap <= $budget else 1)" 2>/dev/null; then
    log "skip $name: $provider spent $used + cap $cap > $budget"; mv "$job" $Q/skipped/; continue
  fi
  until [ "$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$(cd $P && .venv/bin/python -c 'from terrariabench.gateway import config; print(config()["base_url"])')/v1/messages")" != "000" ]; do
    log "gateway unreachable; waiting before $name"; sleep 60
  done
  log "start $name (spent $spent)"
  mv "$job" $Q/running.sh
  (cd $P && bash $Q/running.sh) > $Q/logs/$name.log 2>&1
  code=$?
  mv $Q/running.sh $Q/done/$name.sh
  log "done $name exit=$code (spent $(cd $P && .venv/bin/python tools/pilot_spend.py $CAMPAIGN))"
  sleep 5
done
