#!/usr/bin/env bash
# Study reference-gw-03 (2026-10-19): two one-factor variants of the reconstructed reference
# profile, prompted by the reference-gw trace analysis. 15 minutes each, $10 session cap.
#   obsact = every act result carries a fresh screenshot (tests stale-observation hypothesis)
#   pve    = hostile NPCs active (slimes drop gel -> torches -> furnace become reachable)
set -u
cd ~/Projects/TerrariaBench
TOTAL_USD=10
C=runs/reference-gw-03
mkdir -p $C
spent() {
  .venv/bin/python - <<'PY'
import json, glob
from decimal import Decimal
total = Decimal(0)
for manifest in glob.glob("runs/reference-gw-03/*/manifest.json"):
    d = manifest.rsplit("/", 1)[0]
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
route_up() {
  [ "$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$(.venv/bin/python -c 'from terrariabench.gateway import config; print(config()["base_url"])')/v1/messages")" != "000" ]
}
run() {  # name model reasoning usd_cap seconds extra-flags...
  local name=$1 model=$2 reasoning=$3 cap=$4 seconds=$5; shift 5
  [ -e $C/$name ] && { echo "$(date -Is) skip $name: already exists"; return; }
  while pgrep -f "terrariabench run --fixture" >/dev/null; do sleep 10; done
  local waited=0
  until route_up; do
    [ $waited -ge 600 ] && { echo "$(date -Is) skip $name: gateway unreachable for 10 min"; return; }
    sleep 30; waited=$((waited + 30))
  done
  local s; s=$(spent)
  if .venv/bin/python -c "import sys; sys.exit(0 if $s + $cap <= $TOTAL_USD else 1)"; then
    echo "$(date -Is) start $name (spent $s)"
    .venv/bin/python -u -m terrariabench run --fixture runs/fixtures/reference-reconstructed-v1 \
      --output $C/$name --provider gateway --model $model --reasoning $reasoning --mode calibration \
      --seconds $seconds --calls 4096 --usd $cap --keep-images 8 --max-context-tokens 120000 \
      --max-tokens-total 200000000 --hide-time "$@" > $C/$name.log 2>&1
    sleep 5
  else
    echo "$(date -Is) skip $name: spent $s + cap $cap > $TOTAL_USD"
  fi
}
run haiku-medium-obsact-15min-01 claude-haiku-5-5  medium 1   900 --observe-after-act
run sonnet-low-pve-15min-01      claude-sonnet-5-5 low    3.5 900 --pve
run opus-low-pve-15min-01        claude-opus-5-5   low    5   900 --pve
echo "$(date -Is) done (spent $(spent))"
