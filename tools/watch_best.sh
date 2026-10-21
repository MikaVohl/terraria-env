#!/bin/sh
# Replay the best eg18 policy so far in the pixel GUI (terraria-px).
#
#   tools/watch_best.sh [v4|v7] [world-seed] [tick-ms]
#
# Records one sampled rollout of the checkpoint on the chosen world (default:
# validation world 23000001) with the matching game library, writes a tape to
# experiments/eg18/best/, and plays it in terraria-px. The engine is
# deterministic, so the GUI shows exactly the recorded episode.
set -eu
cd "$(dirname "$0")/.."
version=${1:-v7}
seed=${2:-23000001}
tick=${3:-60}
best=experiments/eg18/best
case "$version" in
  v7) policy=$best/v7_pot_e1024_seed1201_512M.pt
      lib=experiments/explore-v7-20261019/build/python/terraria_lite/libterraria.dylib
      viewer=experiments/v7-reward-20261017.sGYPqq/variants/v7/terraria-px ;;
  v4) policy=$best/v4_pot_e1024_seed1201_416M.pt
      lib=python/terraria_lite/libterraria.dylib
      viewer=./terraria-px ;;
  *) echo "usage: $0 [v4|v7] [world-seed] [tick-ms]" >&2; exit 2 ;;
esac
for f in "$policy" "$lib" "$viewer"; do
  [ -e "$f" ] || { echo "missing $f" >&2; exit 1; }
done
TERRARIA_LITE_LIB="$PWD/$lib" PYTHONPATH=python .venv/bin/python -m terraria_lite.watch \
  --policy "$policy" --seed "$seed" --out "$best/${version}_seed${seed}.tape" \
  --viewer "$viewer" --tick-ms "$tick" --play
