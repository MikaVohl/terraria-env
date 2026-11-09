# cap gateway=1.2
# run runs/landscape-2026-11-08/d2-haiku-rt-w401-40m
# window 1024x1024
# d2-haiku-rt-w401-40m: gateway claude-haiku-5-5 (medium), realtime, default-v07-32000401, 2400 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000401 --output runs/landscape-2026-11-08/d2-haiku-rt-w401-40m --profile default-v2 --clock realtime --game-seconds 2400 --display "$TB_DISPLAY"  --provider gateway --model claude-haiku-5-5 --reasoning medium --mode calibration --seconds 3000 --calls 4096 --usd 1.2 --reserve-output-tokens 16384 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
