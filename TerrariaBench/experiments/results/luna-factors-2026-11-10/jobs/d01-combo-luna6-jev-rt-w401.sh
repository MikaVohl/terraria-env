# cap gateway=0.4 openrouter=0.15
# run runs/luna-factors-2026-11-10/d01-combo-luna6-jev-rt-w401
# window 1024x1024
# d01-combo-luna6-jev-rt-w401: combo gpt-6-luna (low), realtime, lf-v07-32000401, 600 game-s
.venv/bin/python -u -m terrariabench.combo --fixture runs/fixtures/lf-v07-32000401 --output runs/luna-factors-2026-11-10/d01-combo-luna6-jev-rt-w401 --profile default-v2 --clock realtime --game-seconds 600 --display "$TB_DISPLAY" --planner gpt-6-luna --planner-reasoning low --executor jev --jev-frames 1 --ui-session --seconds 1200 --usd-planner 0.4 --usd-executor 0.15 --campaign-profile default-v2-combo --campaign-profile luna-factors
