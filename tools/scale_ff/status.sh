#!/bin/bash
# Latest validation line per run, plus queue events.
echo __BEGIN__
date -u +%H:%M
for f in ~/sff/*/logs/*.log; do
  last=$(grep -E '/32 ' "$f" | tail -1)
  [ -n "$last" ] && echo "$last" | cut -c1-120
done
grep -E 'FAILED|finished' ~/sff/queue.log | tail -20
