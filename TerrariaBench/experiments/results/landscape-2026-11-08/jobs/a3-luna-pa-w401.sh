# cap gateway=0.9
# run runs/landscape-2026-11-08/a3-luna-pa-w401
# window 1024x1024
# a3-luna-pa-w401: unified gpt-5.6-luna (low), paused, default-v07-32000401, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000401 --output runs/landscape-2026-11-08/a3-luna-pa-w401 --profile default-v2 --clock paused --game-seconds 1200 --display "$TB_DISPLAY"  --provider unified --model gpt-5.6-luna --reasoning low --mode calibration --seconds 1800 --calls 4096 --usd 0.9 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
