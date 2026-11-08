# cap provider=gateway usd=1.5
# 160-haiku-v2-w302-40m: claude-haiku-5-5 (medium) on campaign-v07-32000302, 2400 s; extra: --pve --hostile-damage off --observe-after-act --interface-card v3 --checkpoint-log extended --clock realtime
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/campaign-v07-32000302 --output runs/llm-campaign-2026-11-08/haiku-v2-w302-40m \
  --provider gateway --model claude-haiku-5-5 --reasoning medium --mode calibration --seconds 2400 --calls 4096 --usd 1.5 --reserve-output-tokens 16384 \
  --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --hide-time --image-format jpeg --campaign-profile camp-v2 \
  --pve --hostile-damage off --observe-after-act --interface-card v3 --checkpoint-log extended --clock realtime
code=$?
.venv/bin/python tools/run_evidence.py runs/llm-campaign-2026-11-08/haiku-v2-w302-40m > /dev/null 2>&1
.venv/bin/python tools/extended_score.py runs/llm-campaign-2026-11-08/haiku-v2-w302-40m > /dev/null 2>&1
exit $code
