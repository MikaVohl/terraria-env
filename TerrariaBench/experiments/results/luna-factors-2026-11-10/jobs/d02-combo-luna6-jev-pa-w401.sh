# cap gateway=0.4 openrouter=0.15
# run runs/luna-factors-2026-11-10/d02-combo-luna6-jev-pa-w401
# window 1024x1024
# d02-combo-luna6-jev-pa-w401: combo gpt-6-luna (low), paused, lf-v07-32000401, 600 game-s
.venv/bin/python -u -m terrariabench.combo --fixture runs/fixtures/lf-v07-32000401 --output runs/luna-factors-2026-11-10/d02-combo-luna6-jev-pa-w401 --profile default-v2 --clock paused --game-seconds 600 --display "$TB_DISPLAY" --planner gpt-6-luna --planner-reasoning low --executor jev --jev-frames 1 --ui-session --seconds 5400 --usd-planner 0.4 --usd-executor 0.15 --campaign-profile default-v2-combo --campaign-profile luna-factors
