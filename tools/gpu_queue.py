"""Unattended GPU job queue for explore_screen arms (one run per job).

Fills each allowed HIP GPU up to --per-gpu concurrent iterate_ppo runs, in
queue order, as slots free up. A live explore_screen launcher that is not ours
reserves its --workers slots on its GPU, so queued jobs never squeeze in next
to another launcher's pending runs. When a run has written summary.json the
driver evaluates its final checkpoint with tools/policy_diagnostics.py on CPU
(diag.json next to curve.json). State is kept in <out>/queue_state.json, so a
restarted driver skips jobs it already launched.

Queue file: JSON list of {"name", "lib", "arm", "seed", "steps", "interval",
"max_steps" (0 or the episode limit used for diagnostics)}; "lib" is a
directory under perf/v7 containing libterraria.so.

    python tools/gpu_queue.py --queue q.json --out experiments/<study> --gpus 0 1 2 3 4 5 6 7
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def procs():
    """(pid, cmdline list, HIP_VISIBLE_DEVICES) for this user's processes."""
    out = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            env = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        except OSError:
            continue
        hip = next((e.split(b"=", 1)[1].decode() for e in env if e.startswith(b"HIP_VISIBLE_DEVICES=")), None)
        out.append((int(pid), [c.decode(errors="replace") for c in cmd if c], hip))
    return out


def arg(cmd, flag, default=None):
    return cmd[cmd.index(flag) + 1] if flag in cmd else default


def used_slots(out_dir, gpus):
    """Per GPU: our running iterate_ppo runs plus slots reserved by foreign launchers."""
    used = {g: 0 for g in gpus}
    for pid, cmd, hip in procs():
        joined = " ".join(cmd)
        if "explore_screen.py" in joined and str(out_dir) not in joined:
            g = arg(cmd, "--gpus")
            if g is not None and int(g) in used:
                used[int(g)] += int(arg(cmd, "--workers", "1"))
        elif "iterate_ppo.py" in joined and str(out_dir) in joined and hip is not None and int(hip) in used:
            used[int(hip)] += 1
    return used


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--queue", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--gpus", type=int, nargs="+", required=True)
    p.add_argument("--per-gpu", type=int, default=2)
    p.add_argument("--poll", type=int, default=60)
    p.add_argument("--diag-cpus", default="200-263", help="taskset core range for diagnostics")
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    jobs = json.loads(a.queue.read_text())
    state_path = out / "queue_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    diag = {}

    def log(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)

    while True:
        used = used_slots(out, a.gpus)
        pending = [j for j in jobs if j["name"] not in state]
        for g in a.gpus:
            while pending and used[g] < a.per_gpu:
                j = pending.pop(0)
                lib = ROOT / "perf/v7" / j["lib"] / "libterraria.so"
                env = dict(os.environ, PYTHONPATH=str(ROOT / "python"), TERRARIA_LITE_LIB=str(lib))
                run_out = out / j["name"]
                cmd = [sys.executable, "-u", str(ROOT / "tools/explore_screen.py"), "--out", str(run_out),
                       "--layout", "gpu", "--gpus", str(g), "--arms", j["arm"], "--seeds", str(j["seed"]),
                       "--steps", str(j["steps"]), "--interval", str(j["interval"]), "--workers", "1"]
                with open(out / f"{j['name']}.launcher.log", "w") as f:
                    subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
                state[j["name"]] = {"gpu": g, "launched": time.time()}
                state_path.write_text(json.dumps(state, indent=2))
                used[g] += 1
                log(f"launched {j['name']} on GPU {g}")
                time.sleep(20)   # let it start before counting slots again
        # Diagnostics for finished runs (at most 4 at a time).
        for j in jobs:
            if j["name"] not in state or j["name"] in diag:
                continue
            run_dir = out / j["name"] / "runs" / f"{j['arm']}-{j['seed']}"
            final = run_dir / f"step-{j['steps'] // (1024 * 128) * (1024 * 128)}.pt"
            if not (run_dir / "summary.json").exists() or (run_dir / "diag.json").exists():
                continue
            if sum(1 for d in diag.values() if d.poll() is None) >= 4:
                break
            ckpt = final if final.exists() else max(run_dir.glob("step-*.pt"), key=lambda q: int(q.stem[5:]))
            lib = ROOT / "perf/v7" / j["lib"] / "libterraria.so"
            env = dict(os.environ, PYTHONPATH=str(ROOT / "python"), TERRARIA_LITE_LIB=str(lib),
                       CUDA_VISIBLE_DEVICES="", HIP_VISIBLE_DEVICES="")
            cmd = ["taskset", "-c", a.diag_cpus, sys.executable, str(ROOT / "tools/policy_diagnostics.py"), str(ckpt),
                   "--out", str(run_dir / "diag.json"), "--episodes", "128", "--seed-start", "23000001",
                   "--max-steps", str(j.get("max_steps", 0))]
            diag[j["name"]] = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                                               stderr=open(run_dir / "diag.log", "w"))
            log(f"diagnostics {j['name']}")
        done = all((out / j["name"] / "runs" / f"{j['arm']}-{j['seed']}" / "diag.json").exists() for j in jobs)
        if done:
            log("queue complete")
            return
        time.sleep(a.poll)


if __name__ == "__main__":
    main()
