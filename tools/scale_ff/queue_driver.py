"""eg15 job queue for the scale-ff study (throwaway driver; commands identical to explore_screen).

Reads ~/sff/queue.txt every loop: lines "study arm seed steps interval". Starts a job when its
run directory does not exist and a GPU has < PER_GPU live jobs (counted from /proc, so jobs of an
earlier queue instance count too). Edit the file to add/remove jobs; kill an iterate_ppo PID to
stop a run early (its partial curve stays). Lives in ~/sff/bin (never next to stdlib-shadowing names).
"""
import os, subprocess, sys, time
from pathlib import Path

ROOT = Path.home()/"Projects/RL-scaleff"
sys.path.insert(0, str(ROOT/"tools"))
from explore_screen import ARMS, PACKAGE, LAYOUTS  # noqa: E402

GPUS = os.environ.get("SFF_GPUS", "2,3").split(",")
PER_GPU = int(os.environ.get("SFF_PER_GPU", "2"))
HOME = Path.home()/"sff"
QUEUE = HOME/"queue.txt"
SCRIPTS = (str(ROOT/"tools/iterate_ppo.py").encode(), str(HOME/"dbg/nan_repro.py").encode())
env0 = dict(os.environ, PYTHONPATH=str(ROOT/"python"),
            TERRARIA_LITE_LIB=str(ROOT/"perf/v7/build-lw2/libterraria.so"))
python = str(Path.home()/"Projects/RL/.venv/bin/python")


def live_load():
    load = {g: 0 for g in GPUS}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            if not set(SCRIPTS) & set(open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")):
                continue
            env = dict(e.split(b"=", 1) for e in open(f"/proc/{pid}/environ", "rb").read().split(b"\0") if b"=" in e)
        except OSError:
            continue
        gpu = env.get(b"HIP_VISIBLE_DEVICES", b"").decode()
        if gpu in load:
            load[gpu] += 1
    return load


running = {}
while True:
    for name, (proc, log, gpu) in list(running.items()):
        if proc.poll() is not None:
            log.close(); del running[name]
            print(time.strftime("%H:%M:%S"), "finished" if proc.returncode == 0 else f"FAILED rc={proc.returncode}",
                  name, flush=True)
    jobs = [l.split() for l in QUEUE.read_text().splitlines() if l.strip() and not l.startswith("#")]
    for study, arm, seed, steps, interval in jobs:
        out = HOME/study/"runs"/f"{arm}-{seed}"
        if out.exists():
            continue
        load = live_load()
        gpu = min(GPUS, key=lambda g: (load[g], GPUS.index(g)))
        if load[gpu] >= PER_GPU:
            break
        (HOME/study/"logs").mkdir(parents=True, exist_ok=True)
        cmd = [python, str(ROOT/"tools/iterate_ppo.py"), "--out", str(out), "--seed", seed, "--steps", steps,
               "--interval", interval, *PACKAGE, *LAYOUTS["gpu"], *ARMS[arm]]
        log = (HOME/study/"logs"/f"{arm}-{seed}.log").open("w")
        log.write(" ".join(cmd)+"\n"); log.flush()
        running[f"{study}/{arm}-{seed}"] = (subprocess.Popen(cmd, cwd=ROOT, env=dict(env0, HIP_VISIBLE_DEVICES=gpu),
                                                             stdout=log, stderr=subprocess.STDOUT), log, gpu)
        print(time.strftime("%H:%M:%S"), "started", f"{study}/{arm}-{seed}", f"gpu={gpu}", flush=True)
        time.sleep(2)
    time.sleep(10)
