"""Sample CPU (process tree, from /proc) and GPU busy % (amd-smi) once per second until the pid exits.

    python perf/v10/util_sample.py PID GPU_INDEX OUT.jsonl
Each line: {"t", "cpu_cores" (busy cores of the process tree over the last second), "gpu_busy", "gpu_mem_busy"}.
"""
import json
import os
import subprocess
import sys
import time

pid, gpu, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
tick = os.sysconf("SC_CLK_TCK")


def tree_ticks(root):
    kids = {}
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                with open(f"/proc/{p}/stat") as f:
                    s = f.read().rsplit(")", 1)[1].split()
                kids.setdefault(int(s[1]), []).append((int(p), int(s[11]) + int(s[12])))
            except (OSError, IndexError):
                pass
    total, stack = 0, [root]
    try:
        with open(f"/proc/{root}/stat") as f:
            s = f.read().rsplit(")", 1)[1].split()
        total = int(s[11]) + int(s[12])
    except OSError:
        return None
    while stack:
        for c, t in kids.get(stack.pop(), []):
            total += t
            stack.append(c)
    return total


def gpu_busy():
    try:
        r = subprocess.run(["amd-smi", "metric", "-g", gpu, "-u", "--json"], capture_output=True, text=True, timeout=5)
        d = json.loads(r.stdout)
        d = d[0] if isinstance(d, list) else d
        d = d.get("gpu_data", [d])[0] if "gpu_data" in d else d
        u = d["usage"]
        val = lambda x: x["value"] if isinstance(x, dict) else x
        return val(u.get("gfx_activity")), val(u.get("umc_activity"))
    except Exception:
        return None, None


prev, t_prev = tree_ticks(pid), time.time()
with open(out, "w") as f:
    while prev is not None:
        time.sleep(1.0)
        cur, t = tree_ticks(pid), time.time()
        if cur is None:
            break
        g, m = gpu_busy()
        f.write(json.dumps({"t": round(t, 2), "cpu_cores": round((cur - prev) / tick / (t - t_prev), 2),
                            "gpu_busy": g, "gpu_mem_busy": m}) + "\n")
        f.flush()
        prev, t_prev = cur, t
