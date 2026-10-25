"""Minimal repro: an atomic add sees memory older than the zero-fill launched just before it.

The pattern TorchInductor emits for the backward of a gather (log_prob of the
taken action, Categorical.log_prob -> gather -> scatter_add):

  kernel 1: buf[:] = 0                      (plain stores)
  kernel 2: atomic_add(buf[row, idx[row]], v[row])   (relaxed atomics, same stream)

Every iteration first fills buf with a sentinel (kernel 0), so a result that
still contains the sentinel means kernel 2's atomics read memory from before
kernel 1's stores. Alone this never happens; with several processes on the
same GPU it does (see docs/reports/GPU_SHARING_CORRUPTION_2026_10.md).

  python atomic_repro.py [--seconds 120] [--mode triton|torch]
"""
import argparse
import time

import torch
import triton
import triton.language as tl


@triton.jit
def fill_kernel(out_ptr, value, n, BLOCK: tl.constexpr):
    i = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
    tl.store(out_ptr + i, tl.full([BLOCK], value, tl.float32), mask=i < n)


@triton.jit
def scatter_kernel(idx_ptr, val_ptr, out_ptr, rows, cols: tl.constexpr, BLOCK: tl.constexpr):
    r = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
    m = r < rows
    idx = tl.load(idx_ptr + r, mask=m, other=0)
    v = tl.load(val_ptr + r, mask=m, other=0.0)
    tl.atomic_add(out_ptr + idx + cols * r, v, mask=m, sem="relaxed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--rows", type=int, default=8192)
    ap.add_argument("--cols", type=int, default=83)
    ap.add_argument("--mode", choices=["triton", "torch"], default="triton")
    ap.add_argument("--sentinel", type=float, default=1e30)
    args = ap.parse_args()
    dev = torch.device("cuda")
    rows, cols = args.rows, args.cols
    n = rows * cols
    g = torch.Generator().manual_seed(0)
    idx = torch.randint(0, cols, (rows,), generator=g).to(dev)
    val = torch.randn(rows, generator=g).to(dev)
    expect = torch.zeros(rows, cols, device=dev).scatter_(1, idx[:, None], val[:, None])
    buf = torch.empty(rows, cols, device=dev)
    B = 1024
    runs = bad = stale = 0
    t0 = time.time()
    while time.time() - t0 < args.seconds:
        if args.mode == "triton":
            fill_kernel[(triton.cdiv(n, B),)](buf, args.sentinel, n, BLOCK=B)
            fill_kernel[(triton.cdiv(n, B),)](buf, 0.0, n, BLOCK=B)
            scatter_kernel[(triton.cdiv(rows, B),)](idx, val, buf, rows, cols, BLOCK=B)
        else:
            buf.fill_(args.sentinel)
            buf.zero_()
            buf.scatter_add_(1, idx[:, None], val[:, None])
        wrong = (buf != expect)
        nwrong = int(wrong.sum())
        runs += 1
        if nwrong:
            bad += 1
            ns = int((buf.abs() > args.sentinel / 2).sum())
            stale += ns
            if bad <= 5:
                where = torch.nonzero(wrong)[:4].tolist()
                print(f"run {runs}: {nwrong} wrong elements ({ns} hold the sentinel), e.g. {where}", flush=True)
    print(f"{args.mode}: {bad} of {runs} iterations wrong, {stale} sentinel elements total "
          f"({torch.__version__}, hip {torch.version.hip}, {torch.cuda.get_device_name()})", flush=True)


if __name__ == "__main__":
    main()
