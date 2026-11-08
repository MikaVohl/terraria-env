# cap provider=gateway usd=2.5
# 100-sol-w301-15m: gpt-5.6-sol (low) on campaign-v07-32000301, 900 s; extra: --pve --hostile-damage off --observe-after-act --interface-card --clock realtime
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/campaign-v07-32000301 --output runs/llm-campaign-2026-11-08/sol-w301-15m \
  --provider unified --model gpt-5.6-sol --reasoning low --mode calibration --seconds 900 --calls 4096 --usd 2.5  \
  --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --hide-time --image-format jpeg --campaign-profile camp-v1 \
  --pve --hostile-damage off --observe-after-act --interface-card --clock realtime
code=$?
.venv/bin/python tools/run_evidence.py runs/llm-campaign-2026-11-08/sol-w301-15m > /dev/null 2>&1
.venv/bin/python tools/extended_score.py runs/llm-campaign-2026-11-08/sol-w301-15m > /dev/null 2>&1
exit $code
