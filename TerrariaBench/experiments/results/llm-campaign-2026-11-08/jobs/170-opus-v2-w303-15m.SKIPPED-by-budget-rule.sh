# cap provider=gateway usd=2.4
# 170-opus-v2-w303-15m: claude-opus-5-5 (low) on campaign-v07-32000303, 900 s; extra: --pve --hostile-damage off --observe-after-act --interface-card v3 --checkpoint-log extended --clock realtime
[ "$(date -u +%H%M)" -gt 1120 ] && { echo "too late for a 15-min run before the 11:45 UTC stop"; exit 3; }
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/campaign-v07-32000303 --output runs/llm-campaign-2026-11-08/opus-v2-w303-15m \
  --provider gateway --model claude-opus-5-5 --reasoning low --mode calibration --seconds 900 --calls 4096 --usd 2.4 --reserve-output-tokens 16384 \
  --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --hide-time --image-format jpeg --campaign-profile camp-v2 \
  --pve --hostile-damage off --observe-after-act --interface-card v3 --checkpoint-log extended --clock realtime
code=$?
.venv/bin/python tools/run_evidence.py runs/llm-campaign-2026-11-08/opus-v2-w303-15m > /dev/null 2>&1
.venv/bin/python tools/extended_score.py runs/llm-campaign-2026-11-08/opus-v2-w303-15m > /dev/null 2>&1
exit $code
