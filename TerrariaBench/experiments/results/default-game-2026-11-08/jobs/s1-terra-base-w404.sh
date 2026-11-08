# cap gateway=1.8
# run runs/default-game-2026-11-08/s1-terra-base-w404
# window 1024x1024
# s1-terra-base-w404: unified gpt-5.6-terra (low), paused, screen-v07-32000404, 600 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/screen-v07-32000404 --output runs/default-game-2026-11-08/s1-terra-base-w404 --profile default-v1 --clock paused --game-seconds 600 --display "$TB_DISPLAY"  --provider unified --model gpt-5.6-terra --reasoning low --mode calibration --seconds 1200 --calls 4096 --usd 1.8 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v1
