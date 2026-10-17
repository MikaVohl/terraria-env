#!/bin/sh
# Preserve the exact source and Python/frontend compatibility of published v1 runs.
set -eu
cd "$(dirname "$0")/.."
out=experiments/v1-frozen
if [ -e "$out" ]; then
    echo "$out already exists; leaving it untouched"
    exit 0
fi
mkdir -p "$out"
git archive 0f9170bd0571e872c1e8fea666a4a2f06cdc3ad8 | tar -x -C "$out"
make -C "$out" -j4 all lib
make -C "$out" check
echo "v1 source, binding and binaries: $out"
