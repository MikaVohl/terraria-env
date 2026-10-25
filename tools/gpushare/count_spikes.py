"""Count gradient-norm spikes in spike_probe.py gradnorms.npy files.

  python tools/gpushare/count_spikes.py ~/gsb/<run>/*/gradnorms.npy [--steps-per-update 2048]

One line per file: updates, env steps covered, median and max norm, the number
of updates with a norm > 100 / > 1e3 / non-finite, and the env step of the
first > 1e3 spike (2048 env steps per update for 1024 envs x 128 steps / 64
minibatch updates).
"""
import argparse

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--steps-per-update", type=int, default=2048)
a = ap.parse_args()
for f in a.files:
    g = np.load(f)
    finite = np.isfinite(g)
    big = np.flatnonzero(~finite | (g > 1e3))
    first = f"{big[0] * a.steps_per_update / 1e6:.1f}M" if len(big) else "-"
    print(f"{f}: {len(g)} updates = {len(g) * a.steps_per_update / 1e6:.0f}M steps, median {np.median(g[finite]):.3g}, "
          f"max {g[finite].max():.3g}, >100 {int((g[finite] > 100).sum())}, >1e3 {int((g[finite] > 1e3).sum())}, "
          f"non-finite {int((~finite).sum())}, first >1e3 at {first}")
