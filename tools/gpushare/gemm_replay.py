"""Replay logged hipBLASLt GEMMs through torch and check every repeat is bit-identical.

  HIPBLASLT_LOG_MASK=32 HIPBLASLT_LOG_FILE=gemms.log <program>     # record the calls
  python gemm_replay.py gemms.log [--seconds 300] [--only bf16_r]  # replay them (alone / several at once)

Each unique hipblaslt-bench line becomes one torch matmul with the same
problem (m, n, k, transposes, leading dimensions, bias epilogue, dtype), so
torch hands hipBLASLt the same call; set HIPBLASLT_LOG_MASK=32 on the replay
to confirm the solution indices match. Outputs are compared with the first
result; mismatches are printed with the call line.
"""
import argparse
import json
import os
import shlex
import time

import torch

TYPES = {"bf16_r": torch.bfloat16, "f32_r": torch.float32, "f16_r": torch.float16}


def parse(line):
    tok = shlex.split(line)
    a = {}
    i = 1
    while i < len(tok):
        if tok[i].startswith("-"):
            key = tok[i].lstrip("-")
            if i + 1 < len(tok) and not tok[i + 1].startswith("-"):
                a[key] = tok[i + 1]
                i += 2
                continue
            a[key] = True
        i += 1
    return a


def view(buf_rows, cols, ld, dtype, gen, dev):
    """A row-major (buf_rows, cols) tensor with row stride ld (a column-major matrix with leading dim ld)."""
    storage = (torch.randn(buf_rows * ld, generator=gen) * 0.5).to(dev, dtype)
    return storage.as_strided((buf_rows, cols), (ld, 1))


def build(a, gen, dev):
    m, n, k = int(a["m"]), int(a["n"]), int(a["k"])
    dt = TYPES[a["a_type"]]
    lda, ldb = int(a["lda"]), int(a["ldb"])
    # Column-major A (m x k if N else k x m) is a row-major (cols, rows) view with stride lda.
    av = view(k, m, lda, dt, gen, dev) if a["transA"] == "N" else view(m, k, lda, dt, gen, dev)
    bv = view(n, k, ldb, dt, gen, dev) if a["transB"] == "N" else view(k, n, ldb, dt, gen, dev)
    opa_t = av if a["transA"] == "N" else av.t()           # op(A)^T : k x m
    opb_t = bv if a["transB"] == "N" else bv.t()           # op(B)^T : n x k
    beta = float(a.get("beta", 0))
    if "bias_vector" in a:
        bias = torch.randn(m, generator=gen).to(dev, TYPES.get(a.get("bias_type", a["a_type"]), dt))
        return lambda: torch.addmm(bias, opb_t, opa_t)
    if beta == 1.0:
        c = torch.randn(n, m, generator=gen).to(dev, dt)
        return lambda: torch.addmm(c, opb_t, opa_t)
    return lambda: opb_t @ opa_t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--seconds", type=float, default=300)
    ap.add_argument("--only", default="", help="substring filter on the log line (e.g. bf16_r)")
    ap.add_argument("--tag", default="replay")
    args = ap.parse_args()
    torch.backends.cuda.matmul.allow_tf32 = False
    dev = torch.device("cuda")
    lines = sorted({l.strip() for l in open(args.log) if l.startswith("hipblaslt-bench") and args.only in l})
    gen = torch.Generator().manual_seed(7)
    ops = [(l, build(parse(l), gen, dev)) for l in lines]
    refs = []
    for l, f in ops:
        f()
        torch.cuda.synchronize()
        refs.append(f().clone())
    torch.cuda.synchronize()
    stats = [dict(runs=0, nondet=0, worst=0.0, nonfinite=0) for _ in ops]
    t0 = time.time()
    while time.time() - t0 < args.seconds:
        for (l, f), r, s in zip(ops, refs, stats):
            out = f()
            err = float(((out.float() - r.float()).abs().max() / r.float().abs().max().clamp_min(1e-30)).nan_to_num(float("inf")))
            s["runs"] += 1
            if err > 0:
                s["nondet"] += 1
                s["worst"] = max(s["worst"], err)
                s["nonfinite"] += not bool(torch.isfinite(out).all())
                if s["nondet"] <= 3:
                    bad = torch.nonzero(out != r)
                    print(json.dumps(dict(tag=args.tag, run=s["runs"], relerr=err, nbad=int(bad.shape[0]),
                                          numel=out.numel(), first=bad[:4].tolist(), call=l)), flush=True)
    for (l, _), s in zip(ops, stats):
        p = parse(l)
        print(f"{args.tag} {p['a_type']} m{p['m']} n{p['n']} k{p['k']} {p['transA']}{p['transB']} "
              f"{'bias ' if 'bias_vector' in p else ''}sol {p.get('solution_index')}: runs {s['runs']} "
              f"nondet {s['nondet']} nonfinite {s['nonfinite']} worst {s['worst']:.3g}", flush=True)


if __name__ == "__main__":
    main()
