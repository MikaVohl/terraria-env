# cap provider=gateway usd=1.2
# 010-haiku-w301-15m: claude-haiku-5-5 (medium) on campaign-v07-32000301, 900 s; extra: --pve --hostile-damage off --observe-after-act --interface-card --clock realtime
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/campaign-v07-32000301 --output runs/llm-campaign-2026-11-08/haiku-w301-15m \
  --provider gateway --model claude-haiku-5-5 --reasoning medium --mode calibration --seconds 900 --calls 4096 --usd 1.2 --reserve-output-tokens 16384 \
  --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --hide-time --image-format jpeg --campaign-profile camp-v1 \
  --pve --hostile-damage off --observe-after-act --interface-card --clock realtime
code=$?
.venv/bin/python tools/run_evidence.py runs/llm-campaign-2026-11-08/haiku-w301-15m > /dev/null 2>&1
.venv/bin/python tools/extended_score.py runs/llm-campaign-2026-11-08/haiku-w301-15m > /dev/null 2>&1
exit $code
