#!/usr/bin/env python3
"""Per-world best of several planner configurations (same horizon).

Each input is a run prefix (PREFIX.jsonl + PREFIX.bin). For every seed the
record with the highest score wins (ties: earliest step of the last earned
achievement). Every chosen tape is itself a legal action sequence, so the
best-of score is still an achievable lower bound on that world's ceiling.

Usage: build_portfolio.py OUT PREFIX[=label] [PREFIX[=label] ...]
"""
import json
import struct
import sys

out, inputs = sys.argv[1], sys.argv[2:]
best = {}
for spec in inputs:
    prefix, _, label = spec.partition("=")
    recs = [json.loads(l) for l in open(prefix + ".jsonl")]
    data, off, tapes = open(prefix + ".bin", "rb").read(), 0, {}
    while off < len(data):
        seed, horizon, nt = struct.unpack_from("<III", data, off)
        tapes[seed] = data[off:off + 12 + nt]
        off += 12 + nt
    for r in recs:
        key = (r["score"], -max(r["ach_step"]))
        r["config"] = label or prefix
        if r["seed"] not in best or key > best[r["seed"]][0]:
            best[r["seed"]] = (key, r, tapes[r["seed"] & 0xFFFFFFFF])
with open(out + ".jsonl", "w") as f, open(out + ".bin", "wb") as g:
    for seed in sorted(best):
        _, r, tape = best[seed]
        f.write(json.dumps(r, separators=(",", ":")) + "\n")
        g.write(tape)
print(f"wrote {out}.jsonl/.bin: {len(best)} worlds from {len(inputs)} configurations")
