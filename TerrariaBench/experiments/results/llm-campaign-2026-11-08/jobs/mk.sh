#!/usr/bin/env bash
# Generate one queue job. Usage: mk.sh <jobname> <cap> <provider> <model> <reasoning> <fixture> <seconds> [extra flags...]
# camp-v1 defaults: real time, PvE on with hostile contact damage off (observer 0.7), screenshot after every act,
# JPEG q85, interface card v1, hidden remaining time, checkpoints visible, continuation message, 8-15 screenshots.
set -eu
name=$1 cap=$2 provider=$3 model=$4 reasoning=$5 fixture=$6 seconds=$7; shift 7
C=runs/llm-campaign-2026-11-08
reserve=""; [ "$provider" = gateway ] && reserve="--reserve-output-tokens 16384"
cat > /tmp/tbjobs/$name.sh <<EOF
# cap provider=gateway usd=$cap
# $name: $model ($reasoning) on $fixture, $seconds s; extra: $*
.venv/bin/python -u -m terrariabench run --fixture runs/fixtures/$fixture --output $C/${name#*-} \\
  --provider $provider --model $model --reasoning $reasoning --mode calibration --seconds $seconds --calls 4096 --usd $cap $reserve \\
  --keep-images 8 --max-context-tokens 120000 --max-tokens-total 400000000 --hide-time --image-format jpeg --campaign-profile camp-v1 \\
  $*
code=\$?
.venv/bin/python tools/run_evidence.py $C/${name#*-} > /dev/null 2>&1
.venv/bin/python tools/extended_score.py $C/${name#*-} > /dev/null 2>&1
exit \$code
EOF
echo /tmp/tbjobs/$name.sh
