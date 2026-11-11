# cap gateway=3.0
# run runs/astra-probe-2026-11-11/p00-med-pa-probe-w404
# window 1024x1024
# p00-med-pa-probe-w404: unified gpt-6-astra (medium), paused, lf-v07-32000404, 90 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/lf-v07-32000404 --output runs/astra-probe-2026-11-11/p00-med-pa-probe-w404 --profile default-v2 --clock paused --game-seconds 90 --display "$TB_DISPLAY" --provider unified --model gpt-6-astra --reasoning medium --mode calibration --seconds 690 --calls 4096 --usd 3.0 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2 --campaign-profile astra-probe
