# cap provider=gateway usd=0.4
# 060-combo-luna-jev-w301-15m: planner gpt-5.6-luna (low, combo-v2 UI sessions) + Jev executor (1 screenshot/decision), camp-v1 world settings, 900 s real time
.venv/bin/python -u -m terrariabench.combo --fixture runs/fixtures/campaign-v07-32000301 --output runs/llm-campaign-2026-11-08/combo-luna-jev-w301-15m \
  --planner gpt-5.6-luna --planner-reasoning low --executor jev --jev-frames 1 --seconds 900 --usd-planner 0.4 --usd-executor 0.15 \
  --pve --hostile-damage off --ui-session --campaign-profile camp-v1-combo
code=$?
.venv/bin/python tools/run_evidence.py runs/llm-campaign-2026-11-08/combo-luna-jev-w301-15m > /dev/null 2>&1
.venv/bin/python tools/extended_score.py runs/llm-campaign-2026-11-08/combo-luna-jev-w301-15m > /dev/null 2>&1
exit $code
