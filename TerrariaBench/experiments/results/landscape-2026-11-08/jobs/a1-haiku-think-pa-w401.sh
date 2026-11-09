# cap gateway=1.5
# run runs/landscape-2026-11-08/a1-haiku-think-pa-w401
# window 1024x1024
# a1-haiku-think-pa-w401: gateway claude-haiku-5-5 (medium), paused, default-v07-32000401, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000401 --output runs/landscape-2026-11-08/a1-haiku-think-pa-w401 --profile default-v2 --clock paused --game-seconds 1200 --display "$TB_DISPLAY"  --provider gateway --model claude-haiku-5-5 --reasoning medium --mode calibration --seconds 1800 --calls 4096 --usd 1.5 --reserve-output-tokens 16384 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
