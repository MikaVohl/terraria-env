# cap gateway=0.35
# run runs/landscape-2026-11-08/d3-luna-rt-w401-40m
# window 1024x1024
# d3-luna-rt-w401-40m: unified gpt-5.6-luna (low), realtime, default-v07-32000401, 2400 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000401 --output runs/landscape-2026-11-08/d3-luna-rt-w401-40m --profile default-v2 --clock realtime --game-seconds 2400 --display "$TB_DISPLAY"  --provider unified --model gpt-5.6-luna --reasoning low --mode calibration --seconds 3000 --calls 4096 --usd 0.35 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
