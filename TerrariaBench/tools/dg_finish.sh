#!/usr/bin/env bash
# Close the default-game campaign unattended: wait until the parallel queue is empty, build the tables and the
# ledger, stop the queue, and remove the isolated displays (Xwayland servers + headless outputs).
set -u
Q=~/tb-queue; P=~/Projects/TerrariaBench; C=runs/default-game-2026-11-08
cd $P
while [ -n "$(ls $Q/dg-jobs/*.sh $Q/dg-running/*.sh 2>/dev/null)" ]; do sleep 30; done
sleep 60  # the queue runs evidence/extended score/clock check after the last job
for r in $C/*/; do
  [ -f $r/result.json ] && [ ! -f $r/evidence/clock.json ] && .venv/bin/python tools/clock_check.py $r > /dev/null 2>&1
done
.venv/bin/python tools/campaign_table.py $C --prefix m --json $C/summary-main.json > $C/results-table-main.md 2>&1
.venv/bin/python tools/campaign_table.py $C --prefix s --json $C/summary-screening.json > $C/results-table-screening.md 2>&1
python3 -c "import json; print(json.dumps([{'what': 'settings perception probe (Haiku + Luna, 144 calls)', 'provider': 'gateway', 'usd': json.load(open('$Q/dg-extra.json'))['gateway']}]))" > $C/ledger-extra.json
(cd tools && ../.venv/bin/python campaign_ledger.py ../$C --extra ../$C/ledger-extra.json) > $C/ledger.json 2>&1
touch $Q/dg-STOP
sleep 15
pkill -f "tools/parallel_queue.py" || true
.venv/bin/python tools/isolated_displays.py down --name wide || true
.venv/bin/python tools/isolated_displays.py down --name displays || true
echo "$(date -Is) default-game campaign finished" >> $Q/dg-queue.log
