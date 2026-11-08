# cap gateway=0.8
# run runs/default-game-2026-11-08/m09-luna-pa-w401-rerun
# window 1024x1024
# m09-luna-pa-w401-rerun: unified gpt-5.6-luna (low), paused, default-v07-32000401, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000401 --output runs/default-game-2026-11-08/m09-luna-pa-w401-rerun --profile default-v1 --clock paused --game-seconds 1200 --display "$TB_DISPLAY" --smart-cursor on --provider unified --model gpt-5.6-luna --reasoning low --mode calibration --seconds 1800 --calls 4096 --usd 0.8 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v1
