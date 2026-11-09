# cap gateway=1.0
# run runs/landscape-2026-11-08/b15-haiku-rt-w403
# window 1024x1024
# b15-haiku-rt-w403: gateway claude-haiku-5-5 (medium), realtime, default-v07-32000403, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000403 --output runs/landscape-2026-11-08/b15-haiku-rt-w403 --profile default-v2 --clock realtime --game-seconds 1200 --display "$TB_DISPLAY"  --provider gateway --model claude-haiku-5-5 --reasoning medium --mode calibration --seconds 1800 --calls 4096 --usd 1.0 --reserve-output-tokens 16384 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
