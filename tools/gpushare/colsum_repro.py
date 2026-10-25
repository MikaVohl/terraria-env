"""Repro: bf16 column sums go wrong while other processes keep the same AMD GPU busy.

  python colsum_repro.py                       # alone: every sum bit-identical
  for i in 1 2; do python stress.py --seconds 200 --only gemm_bf16,policy_bf16-compile & done
  sleep 40; python colsum_repro.py --seconds 150   # observed: 6144 of 322362 sums wrong

x.sum(0) of a bf16 [M, N] tensor (N a multiple of 2, M large enough for ATen's
multi-block "global" reduction, ReduceConfig.ctas_per_output > 1) is computed
once as a reference, then repeatedly; every result should be bit-identical.
The neighbour matters: three copies of this script together, or one --load
neighbour (a plain bf16 matmul loop), gave 0 wrong sums in 0.1-1.9M calls on
eg15; the mixed GEMM + compiled fwd/bwd neighbours above (or the colsum ops
of stress.py itself at 3 processes) did.
"""
import argparse
import time

import torch

ap = argparse.ArgumentParser()
ap.add_argument("--m", type=int, default=811008)
ap.add_argument("--n", type=int, default=32)
ap.add_argument("--seconds", type=float, default=120)
ap.add_argument("--dtype", default="bfloat16")
ap.add_argument("--load", action="store_true", help="be the busy neighbour instead")
a = ap.parse_args()

if a.load:
    x = torch.randn(8192, 8192, device="cuda", dtype=torch.bfloat16)
    t0 = time.time()
    while time.time() - t0 < a.seconds:
        for _ in range(20):
            y = x @ x
        torch.cuda.synchronize()
    raise SystemExit

g = torch.Generator().manual_seed(0)
x = (torch.randn(a.m, a.n, generator=g) * 1e-4).to("cuda", getattr(torch, a.dtype))
ref = x.sum(0)
torch.cuda.synchronize()
runs = bad = 0
worst = 0.0
t0 = time.time()
while time.time() - t0 < a.seconds:
    out = x.sum(0)
    err = float(((out.float() - ref.float()).abs().max() / ref.float().abs().max()))
    runs += 1
    if err > 0:
        bad += 1
        worst = max(worst, err)
        if bad <= 3:
            idx = torch.nonzero(out != ref).flatten().tolist()
            print(f"run {runs}: {len(idx)} of {a.n} outputs differ, rel. err {err:.3g}, indices {idx[:16]}", flush=True)
print(f"{torch.__version__} hip {torch.version.hip} {torch.cuda.get_device_name()} x[{a.m},{a.n}] {a.dtype}: "
      f"{bad} of {runs} sums differ from the first (worst rel. err {worst:.3g})", flush=True)
