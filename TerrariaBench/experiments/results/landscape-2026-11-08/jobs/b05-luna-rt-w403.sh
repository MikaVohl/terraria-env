# cap gateway=0.6
# run runs/landscape-2026-11-08/b05-luna-rt-w403
# window 1024x1024
# b05-luna-rt-w403: unified gpt-5.6-luna (low), realtime, default-v07-32000403, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000403 --output runs/landscape-2026-11-08/b05-luna-rt-w403 --profile default-v2 --clock realtime --game-seconds 1200 --display "$TB_DISPLAY"  --provider unified --model gpt-5.6-luna --reasoning low --mode calibration --seconds 1800 --calls 4096 --usd 0.6 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
