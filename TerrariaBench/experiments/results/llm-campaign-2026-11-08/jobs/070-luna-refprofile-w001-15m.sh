# cap provider=gateway usd=0.6
# 070-luna-refprofile-w001-15m: gpt-5.6-luna (low) on campaign-ref-v07, 900 s; extra: --image-format png --clock realtime
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/campaign-ref-v07 --output runs/llm-campaign-2026-11-08/luna-refprofile-w001-15m \
  --provider unified --model gpt-5.6-luna --reasoning low --mode calibration --seconds 900 --calls 4096 --usd 0.6  \
  --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --hide-time --campaign-profile reference-reconstructed-v1 \
  --image-format png --clock realtime
code=$?
.venv/bin/python tools/run_evidence.py runs/llm-campaign-2026-11-08/luna-refprofile-w001-15m > /dev/null 2>&1
.venv/bin/python tools/extended_score.py runs/llm-campaign-2026-11-08/luna-refprofile-w001-15m > /dev/null 2>&1
exit $code
