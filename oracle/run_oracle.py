#!/usr/bin/env python3
"""Run oracle_v7 over a seed range in parallel worker processes (CPU only).

Writes OUT.jsonl (one planner record per world, seed order) and OUT.bin (the
concatenated action tapes, same order) for replay_verify.py.

Usage: run_oracle.py --horizon 3000 --first 23000001 --count 128 --out results/h3000
"""
import argparse
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ap = argparse.ArgumentParser()
ap.add_argument("--horizon", type=int, default=3000)
ap.add_argument("--first", type=int, default=23000001)
ap.add_argument("--count", type=int, default=128)
ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
ap.add_argument("--out", required=True)
ap.add_argument("--extra", default="", help="extra oracle_v7 flags")
args = ap.parse_args()

here = os.path.dirname(os.path.abspath(__file__))
exe = os.path.join(here, "oracle_v7")
tmp = tempfile.mkdtemp(prefix="oracle_")


def one(i):
    seed = args.first + i
    tape = os.path.join(tmp, f"{i}.bin")
    out = subprocess.run([exe, "-h", str(args.horizon), "-s", str(seed), "-n", "1", "-t", tape,
                          *args.extra.split()], capture_output=True, text=True, check=True)
    if out.stderr.strip():
        sys.stderr.write(f"[{seed}] {out.stderr.strip()}\n")
    return out.stdout, open(tape, "rb").read()


with ThreadPoolExecutor(args.jobs) as pool:
    results = list(pool.map(one, range(args.count)))
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
with open(args.out + ".jsonl", "w") as f, open(args.out + ".bin", "wb") as g:
    for js, tape in results:
        f.write(js)
        g.write(tape)
print(f"wrote {args.out}.jsonl/.bin ({args.count} worlds, horizon {args.horizon})")
