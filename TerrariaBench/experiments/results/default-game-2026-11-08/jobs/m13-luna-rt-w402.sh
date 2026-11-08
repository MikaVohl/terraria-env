# cap gateway=0.6
# run runs/default-game-2026-11-08/m13-luna-rt-w402
# window 1024x1024
# m13-luna-rt-w402: unified gpt-5.6-luna (low), realtime, default-v07-32000402, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000402 --output runs/default-game-2026-11-08/m13-luna-rt-w402 --profile default-v1 --clock realtime --game-seconds 1200 --display "$TB_DISPLAY" --smart-cursor on --provider unified --model gpt-5.6-luna --reasoning low --mode calibration --seconds 1800 --calls 4096 --usd 0.6 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v1
