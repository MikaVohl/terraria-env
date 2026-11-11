# cap gateway=0.6
# run runs/luna-factors-2026-11-10/a12-norm-w401
# window 1024x1024
# a12-norm-w401: unified gpt-6-luna (low), paused, lf-v07-32000401, 600 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/lf-v07-32000401 --output runs/luna-factors-2026-11-10/a12-norm-w401 --profile default-v2 --clock paused --game-seconds 600 --display "$TB_DISPLAY" --provider unified --model gpt-6-luna --reasoning low --mode calibration --seconds 1200 --calls 4096 --usd 0.6 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2 --campaign-profile luna-factors --coords normalized
