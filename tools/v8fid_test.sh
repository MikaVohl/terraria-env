#!/bin/sh
# v8fid fixture tests (tools/v8fid_test.c), one binary per knob set, on top of
# the training build's base flags. Prints PASS/FAIL per check; exits non-zero
# if any configuration fails.
#   sh tools/v8fid_test.sh
cd "$(dirname "$0")/.." || exit 2
V=variants/v8fid
OUT=${TMPDIR:-/tmp}/v8fid-test
mkdir -p "$OUT"
BASE="-DORE_PCT=300 -DTREE_HEIGHT_PCT=200 -DINV_LOG=1"
status=0
for cfg in "mobs:-DFID_MOBS=1" "combat:-DFID_COMBAT=1" "physics:-DFID_PHYSICS=1" "mining:-DFID_MINING=1" \
           "trees:-DFID_TREES=1" "mobcombat:-DFID_MOBS=1 -DFID_COMBAT=1" \
           "all:-DFID_MOBS=1 -DFID_COMBAT=1 -DFID_PHYSICS=1 -DFID_MINING=1 -DFID_TREES=1"; do
  name=${cfg%%:*}; flags=${cfg#*:}
  cc -std=c11 -O2 -Wall -Wextra -Wno-unused-const-variable -I$V/include -I$V/src $BASE $flags \
     tools/v8fid_test.c $V/src/worldgen.c $V/src/light.c $V/src/obs.c -o "$OUT/$name" -lm || exit 2
  echo "== $name ($flags)"
  "$OUT/$name" || status=1
done
exit $status
