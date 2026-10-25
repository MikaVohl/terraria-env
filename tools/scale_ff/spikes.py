"""Throwaway: grad-norm spike counts per 10M env steps from a .gradnorms.npy (2048 steps/update)."""
import sys, numpy as np
for path in sys.argv[1:]:
    g = np.load(path)
    per = int(10_000_000 / 2048)
    print(path.split("/")[-1], f"{len(g)} updates = {len(g)*2048/1e6:.0f}M steps, nonfinite {int((~np.isfinite(g)).sum())}")
    for i in range(0, len(g), per):
        w = g[i:i+per]
        print(f"  {i*2048/1e6:5.0f}-{(i+len(w))*2048/1e6:4.0f}M: >10 {int((w>10).sum()):4d}  >1e4 {int((w>1e4).sum()):3d}  max {np.nanmax(w):.3g}  median {np.median(w):.3f}")
