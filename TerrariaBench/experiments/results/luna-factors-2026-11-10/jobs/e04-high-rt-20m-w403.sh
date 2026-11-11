# cap gateway=1.5
# run runs/luna-factors-2026-11-10/e04-high-rt-20m-w403
# window 1024x1024
# e04-high-rt-20m-w403: unified gpt-6-luna (high), realtime, lf-v07-32000403, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/lf-v07-32000403 --output runs/luna-factors-2026-11-10/e04-high-rt-20m-w403 --profile default-v2 --clock realtime --game-seconds 1200 --display "$TB_DISPLAY" --provider unified --model gpt-6-luna --reasoning high --mode calibration --seconds 1800 --calls 4096 --usd 1.5 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2 --campaign-profile luna-factors
