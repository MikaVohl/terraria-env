# cap gateway=4.0
# run runs/landscape-2026-11-08/b10-terra-pa-w402
# window 1024x1024
# b10-terra-pa-w402: unified gpt-5.6-terra (low), paused, default-v07-32000402, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000402 --output runs/landscape-2026-11-08/b10-terra-pa-w402 --profile default-v2 --clock paused --game-seconds 1200 --display "$TB_DISPLAY"  --provider unified --model gpt-5.6-terra --reasoning low --mode calibration --seconds 1800 --calls 4096 --usd 4.0 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
