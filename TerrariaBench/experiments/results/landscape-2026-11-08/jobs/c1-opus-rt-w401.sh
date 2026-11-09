# cap gateway=5.0
# run runs/landscape-2026-11-08/c1-opus-rt-w401
# window 1024x1024
# c1-opus-rt-w401: gateway claude-opus-5-5 (low), realtime, default-v07-32000401, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000401 --output runs/landscape-2026-11-08/c1-opus-rt-w401 --profile default-v2 --clock realtime --game-seconds 1200 --display "$TB_DISPLAY"  --provider gateway --model claude-opus-5-5 --reasoning low --mode calibration --seconds 1800 --calls 4096 --usd 5.0 --reserve-output-tokens 16384 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
