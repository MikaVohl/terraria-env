#!/usr/bin/env python3
"""Replay oracle action tapes through the normal v7 Python binding.

For every world in a tape file, a fresh TerrariaLite(max_steps=horizon) is
reset with the same seed and fed the tape one action per step. Each action
must be legal under action_mask() before it is taken; the achievement set and
the step at which each achievement first appeared must equal the planner's
own record (results JSONL). Exit status 1 on any mismatch.

Usage: replay_verify.py TAPE.bin[.gz] RESULTS.jsonl [--lib path/to/libterraria]
"""
import argparse
import gzip
import json
import os
import struct
import sys

ap = argparse.ArgumentParser()
ap.add_argument("tape")
ap.add_argument("results")
ap.add_argument("--lib", default=None, help="libterraria to load (default: vendored v7 build)")
args = ap.parse_args()

here = os.path.dirname(os.path.abspath(__file__))
if args.lib:
    os.environ["TERRARIA_LITE_LIB"] = os.path.abspath(args.lib)
sys.path.insert(0, os.path.join(here, "v7", "python"))
from terraria_lite import SPEC, TerrariaLite  # noqa: E402

assert SPEC.version == 7, SPEC.version
expected = {}
with open(args.results) as f:
    for line in f:
        line = line.strip()
        if line:
            r = json.loads(line)
            expected[(r["seed"], r["horizon"])] = r

data = (gzip.open if args.tape.endswith(".gz") else open)(args.tape, "rb").read()
off, n_ok, n_bad, n_steps = 0, 0, 0, 0
while off < len(data):
    seed, horizon, nt = struct.unpack_from("<III", data, off)
    off += 12
    tape = data[off:off + nt]
    off += nt
    exp = expected.get((seed, horizon))
    if exp is None:
        print(f"seed {seed}: no planner record", file=sys.stderr)
        n_bad += 1
        continue
    env = TerrariaLite(max_steps=horizon, seed=seed)
    _, info = env.reset(seed=seed)
    first = [-1] * SPEC.n_achievements
    prev = 0
    bad = None
    for i, a in enumerate(tape):
        if not env.action_mask()[a]:
            bad = f"illegal action {SPEC.action_names[a]} at step {i}"
            break
        _, _, term, trunc, info = env.step(a)
        m = info["achievement_mask"]
        new = m & ~prev
        for k in range(SPEC.n_achievements):
            if new >> k & 1:
                first[k] = info["steps"]
        prev = m
        if (term or trunc) and i != len(tape) - 1:
            bad = f"episode ended at step {i + 1} before tape end {len(tape)}"
            break
    n_steps += len(tape)
    if bad is None and first != exp["ach_step"]:
        diff = [(SPEC.achievement_names[k], first[k], exp["ach_step"][k])
                for k in range(SPEC.n_achievements) if first[k] != exp["ach_step"][k]]
        bad = f"achievement mismatch {diff}"
    if bad is None and bin(prev).count("1") != exp["score"]:
        bad = f"score {bin(prev).count('1')} != {exp['score']}"
    env.close()
    if bad:
        n_bad += 1
        print(f"seed {seed} horizon {horizon}: FAIL {bad}")
    else:
        n_ok += 1
print(f"replayed {n_ok + n_bad} tapes ({n_steps} actions): {n_ok} identical, {n_bad} failed")
sys.exit(1 if n_bad else 0)
