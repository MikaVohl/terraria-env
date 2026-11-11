# cap gateway=9.13
# run runs/astra-probe-2026-11-11/m01-medium-pa-20m-w401
# window 1024x1024
# m01-medium-pa-20m-w401: unified gpt-6-astra (medium), paused, lf-v07-32000401, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/lf-v07-32000401 --output runs/astra-probe-2026-11-11/m01-medium-pa-20m-w401 --profile default-v2 --clock paused --game-seconds 1200 --display "$TB_DISPLAY" --provider unified --model gpt-6-astra --reasoning medium --mode calibration --seconds 1800 --calls 4096 --usd 9.13 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2 --campaign-profile astra-probe
