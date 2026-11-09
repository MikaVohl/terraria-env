# cap gateway=2.2
# run runs/landscape-2026-11-08/b09-terra-rt-w402
# window 1024x1024
# b09-terra-rt-w402: unified gpt-5.6-terra (low), realtime, default-v07-32000402, 1200 game-s
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/default-v07-32000402 --output runs/landscape-2026-11-08/b09-terra-rt-w402 --profile default-v2 --clock realtime --game-seconds 1200 --display "$TB_DISPLAY"  --provider unified --model gpt-5.6-terra --reasoning low --mode calibration --seconds 1800 --calls 4096 --usd 2.2 --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --campaign-profile default-v2
