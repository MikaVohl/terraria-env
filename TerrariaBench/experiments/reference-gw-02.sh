#!/usr/bin/env bash
# Study reference-gw-02 (2026-10-19): 45-minute single-model runs on the reconstructed reference
# profile through the gateway, run sequentially on Omarchy after reference-gw-01's hidden pair.
#   ref    = checkpoint tool + chat visible (as published); remaining time hidden in continuations
#   hidden = no checkpoint tool, no checkpoint chat, no remaining time
# Before each run, total gateway spend (reported + uncertain, all reference-gw-* runs) plus that
# run's own cap must stay within TOTAL_USD, otherwise the run is skipped.
set -u
cd ~/Projects/TerrariaBench
TOTAL_USD=40
C=runs/reference-gw-02
mkdir -p $C
while pgrep -f "bash /tmp/hidden_pair.sh" >/dev/null; do sleep 5; done
spent() {
  .venv/bin/python - <<'PY'
import json, glob
from decimal import Decimal
total = Decimal(0)
for run in glob.glob("runs/reference-gw-0*/*/manifest.json"):
    d = run.rsplit("/", 1)[0]
    for name in ("result.json", "accounting.json"):
        try:
            a = json.load(open(f"{d}/{name}"))
        except OSError:
            continue
        a = a.get("accounting", a)
        total += Decimal(a["reported_usd"]) + Decimal(a["uncertain_reserved_usd"])
        break
print(total)
PY
}
run() {  # name model reasoning usd_cap extra-flags...
  local name=$1 model=$2 reasoning=$3 cap=$4; shift 4
  local s; s=$(spent)
  if .venv/bin/python -c "import sys; sys.exit(0 if $s + $cap <= $TOTAL_USD else 1)"; then
    echo "$(date -Is) start $name (spent $s)"
    .venv/bin/python -u -m terrariabench run --fixture runs/fixtures/reference-reconstructed-v1 \
      --output $C/$name --provider gateway --model $model --reasoning $reasoning --mode calibration \
      --seconds 2700 --calls 4096 --usd $cap --keep-images 8 --max-context-tokens 120000 \
      --max-tokens-total 200000000 "$@" > $C/$name.log 2>&1
    sleep 5
  else
    echo "$(date -Is) skip $name: spent $s + cap $cap > $TOTAL_USD"
  fi
}
run haiku-medium-ref-45min-01  claude-haiku-5-5  medium 3  --hide-time
run sonnet-low-ref-45min-01    claude-sonnet-5-5 low    10 --hide-time
run opus-low-ref-45min-01      claude-opus-5-5   low    15 --hide-time
run haiku-medium-hidden-45min-01 claude-haiku-5-5 medium 3 --hide-progress
run sonnet-low-hidden-45min-01 claude-sonnet-5-5 low    10 --hide-progress
echo "$(date -Is) done (spent $(spent))"
