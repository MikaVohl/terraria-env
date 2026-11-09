# cap gateway=3.0 openrouter=0.15
# run runs/landscape-2026-11-08/c3-combo-rt-w401
# window 1024x1024
# c3-combo-rt-w401: combo claude-opus-5-5 (low), realtime, default-v07-32000401, 1200 game-s
.venv/bin/python -u -m terrariabench.combo --fixture runs/fixtures/default-v07-32000401 --output runs/landscape-2026-11-08/c3-combo-rt-w401 --profile default-v2 --clock realtime --game-seconds 1200 --display "$TB_DISPLAY"  --planner claude-opus-5-5 --planner-reasoning low --executor jev --jev-frames 1 --ui-session --seconds 1800 --usd-planner 3.0 --usd-executor 0.15 --campaign-profile default-v2-combo
