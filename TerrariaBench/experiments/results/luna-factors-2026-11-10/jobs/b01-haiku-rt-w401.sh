# cap gateway=0.6
# run runs/luna-factors-2026-11-10/b01-haiku-rt-w401
# window 1024x1024
# b01-haiku-rt-w401: gateway claude-haiku-5-5 (medium), realtime, lf-v07-32000401, 600 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/lf-v07-32000401 --output runs/luna-factors-2026-11-10/b01-haiku-rt-w401 --profile default-v2 --clock realtime --game-seconds 600 --display "$TB_DISPLAY" --provider gateway --model claude-haiku-5-5 --reasoning medium --mode calibration --seconds 1200 --calls 4096 --usd 0.6 --reserve-output-tokens 16384 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2 --campaign-profile luna-factors
