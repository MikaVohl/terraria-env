# cap gateway=0.6
# run runs/luna-factors-2026-11-10/a01-rt-w402
# window 1024x1024
# a01-rt-w402: unified gpt-6-luna (low), realtime, lf-v07-32000402, 600 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/lf-v07-32000402 --output runs/luna-factors-2026-11-10/a01-rt-w402 --profile default-v2 --clock realtime --game-seconds 600 --display "$TB_DISPLAY" --provider unified --model gpt-6-luna --reasoning low --mode calibration --seconds 1200 --calls 4096 --usd 0.6 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2 --campaign-profile luna-factors
