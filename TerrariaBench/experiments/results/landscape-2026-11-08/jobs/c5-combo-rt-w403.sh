# cap gateway=1.8 openrouter=0.15
# run runs/landscape-2026-11-08/c5-combo-rt-w403
# window 1024x1024
# c5-combo-rt-w403: combo claude-opus-5-5 (low), realtime, default-v07-32000403, 1200 game-s
.venv/bin/python -u -m terrariabench.combo --fixture runs/fixtures/default-v07-32000403 --output runs/landscape-2026-11-08/c5-combo-rt-w403 --profile default-v2 --clock realtime --game-seconds 1200 --display "$TB_DISPLAY"  --planner claude-opus-5-5 --planner-reasoning low --executor jev --jev-frames 1 --ui-session --seconds 1800 --usd-planner 1.8 --usd-executor 0.15 --campaign-profile default-v2-combo
