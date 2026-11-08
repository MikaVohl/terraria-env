# cap gateway=1.5
# run runs/default-game-2026-11-08/m12-haiku-pa-w402
# window 1024x1024
# m12-haiku-pa-w402: gateway claude-haiku-5-5 (medium), paused, default-v07-32000402, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000402 --output runs/default-game-2026-11-08/m12-haiku-pa-w402 --profile default-v1 --clock paused --game-seconds 1200 --display "$TB_DISPLAY" --smart-cursor on --provider gateway --model claude-haiku-5-5 --reasoning medium --mode calibration --seconds 1800 --calls 4096 --usd 1.5 --reserve-output-tokens 16384 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v1
