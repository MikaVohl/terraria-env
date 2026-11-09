# cap gateway=2.5
# run runs/landscape-2026-11-08/d1-terra-pa-w401-40m
# window 1024x1024
# d1-terra-pa-w401-40m: unified gpt-5.6-terra (low), paused, default-v07-32000401, 2400 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000401 --output runs/landscape-2026-11-08/d1-terra-pa-w401-40m --profile default-v2 --clock paused --game-seconds 2400 --display "$TB_DISPLAY"  --provider unified --model gpt-5.6-terra --reasoning low --mode calibration --seconds 3000 --calls 4096 --usd 2.5 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
