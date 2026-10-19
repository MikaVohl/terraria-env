#!/usr/bin/env bash
# Rerun of the four reference-gw-02 runs lost to the 2026-10-19 ~01:55 gateway outage.
# Same settings as reference-gw-02.sh, plus outage tolerance in the runner (game frozen, clock
# paused, requests never sent are not charged) and a route probe before every run.
# Spend check: reported + uncertain across all reference-gw-* runs, where reservations of
# connection failures (URLError: request never sent) are not counted, must stay within TOTAL_USD.
set -u
cd ~/Projects/TerrariaBench
TOTAL_USD=40
C=runs/reference-gw-02
spent() {
  .venv/bin/python - <<'PY'
import json, glob
from decimal import Decimal
total = Decimal(0)
for manifest in glob.glob("runs/reference-gw-0*/*/manifest.json"):
    d = manifest.rsplit("/", 1)[0]
    for name in ("result.json", "accounting.json"):
        try:
            a = json.load(open(f"{d}/{name}"))
        except OSError:
            continue
        a = a.get("accounting", a)
        uncertain = Decimal(a["uncertain_reserved_usd"])
        try:
            failures = [json.loads(l) for l in open(f"{d}/provider-failures.jsonl")]
        except OSError:
            failures = []
        unsent = sum("URLError" in f["error"] and f.get("sent", True) for f in failures)
        uncertain = max(Decimal(0), uncertain - unsent * Decimal(a["reservation_per_call_usd"]))
        total += Decimal(a["reported_usd"]) + uncertain
        break
print(total)
PY
}
route_up() {
  [ "$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$(.venv/bin/python -c 'from terrariabench.gateway import config; print(config()["base_url"])')/v1/messages")" != "000" ]
}
run() {  # name model reasoning usd_cap seconds extra-flags...
  local name=$1 model=$2 reasoning=$3 cap=$4 seconds=$5; shift 5
  local waited=0
  until route_up; do
    [ $waited -ge 3600 ] && { echo "$(date -Is) skip $name: gateway unreachable for 60 min"; return; }
    sleep 30; waited=$((waited + 30))
  done
  local s; s=$(spent)
  if .venv/bin/python -c "import sys; sys.exit(0 if $s + $cap <= $TOTAL_USD else 1)"; then
    echo "$(date -Is) start $name (spent $s)"
    .venv/bin/python -u -m terrariabench run --fixture runs/fixtures/reference-reconstructed-v1 \
      --output $C/$name --provider gateway --model $model --reasoning $reasoning --mode calibration \
      --seconds $seconds --calls 4096 --usd $cap --keep-images 8 --max-context-tokens 120000 \
      --max-tokens-total 200000000 "$@" > $C/$name.log 2>&1
    sleep 5
  else
    echo "$(date -Is) skip $name: spent $s + cap $cap > $TOTAL_USD"
  fi
}
run sonnet-low-ref-45min-02      claude-sonnet-5-5 low    12 2700 --hide-time
run opus-low-ref-30min-02        claude-opus-5-5   low    12 1800 --hide-time
run haiku-medium-hidden-45min-02 claude-haiku-5-5  medium 3  2700 --hide-progress
run sonnet-low-hidden-45min-02   claude-sonnet-5-5 low    10 2700 --hide-progress
echo "$(date -Is) done (spent $(spent))"
