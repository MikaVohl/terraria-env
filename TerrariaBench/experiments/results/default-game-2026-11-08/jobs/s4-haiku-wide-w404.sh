# cap gateway=0.8
# run runs/default-game-2026-11-08/s4-haiku-wide-w404
# window 1280x720
# s4-haiku-wide-w404: gateway claude-haiku-5-5 (medium), paused, screen-v07-32000404, 600 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/screen-v07-32000404 --output runs/default-game-2026-11-08/s4-haiku-wide-w404 --profile default-v1 --clock paused --game-seconds 600 --display "$TB_DISPLAY" --window 1280x720 --provider gateway --model claude-haiku-5-5 --reasoning medium --mode calibration --seconds 1200 --calls 4096 --usd 0.8 --reserve-output-tokens 16384 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v1
