"""Summarise stress.py logs: per op, runs / corrupt / nonfinite / nondeterministic / worst rel. error."""
import json
import sys

for path in sys.argv[1:]:
    final = None
    with open(path) as f:
        for line in f:
            if line.startswith('{"final"'):
                final = json.loads(line)
    if final is None:
        print(path, "unfinished")
        continue
    print(f"{path} ({final['final']['tag']}, {final['seconds']}s)")
    for op, s in final["stats"].items():
        print(f"  {op:32s} runs {s['runs']:6d} corrupt {s['corrupt']:5d} nonfinite {s['nonfinite']:4d} "
              f"nondet {s['nondet']:6d} worst {s['worst']:.3g}")
