"""Screen training-only exploration aids against a matched control (targets PPO).

Every arm uses the same game, learner package, budget, device layout and fresh
validation worlds; arms differ only in the flags below. Runs execute as
independent iterate_ppo.py processes, at most --workers at a time, ordered
seed-major so partial results are paired across arms.

    PYTHONPATH=python .venv/bin/python tools/explore_screen.py --out experiments/explore-screen-YYYYMMDD
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from terraria_lite import SPEC

ROOT = Path(__file__).resolve().parents[1]
ARMS = {
    "control": [],
    "archive": ["--archive-start-prob", ".25"],
    "sil": ["--sil-minibatches", "4"],
    "archive_sil": ["--archive-start-prob", ".25", "--sil-minibatches", "4"],
    "novelty": ["--novelty", ".1"],
    "memory": ["--memory-features", "stations_v1"],
    "potential": ["--potential", "3"],
    "combined": ["--archive-start-prob", ".25", "--sil-minibatches", "4", "--novelty", ".1",
                 "--memory-features", "stations_v1"],
    # Added after launch of the first eight arms (same package and worlds).
    "aux": ["--aux", ".5"],
    "craftable": ["--memory-features", "craftable_v1"],
    # Second stage (seeds 904-906): stack the two arms that raised furnace rates.
    "potential_hi": ["--potential", "10"],
    "craft_potential": ["--memory-features", "craftable_v1", "--potential", "3"],
    "craft_mem_potential": ["--memory-features", "stations_v1+craftable_v1", "--potential", "3"],
}
# Device layouts. Arms are only compared within one layout (seed blocks): the
# MPS learner differs from CPU by float rounding. collect_threads=1 on CPU is
# bit-identical to the original CPU learner. (An earlier "MPS stall" reading
# was a misdiagnosis: ps CPU time is unreliable here; 8 concurrent hybrid
# learners measured ~3.5k steps/s each alongside 8 CPU runs.)
LAYOUTS = {
    "cpu": ["--device", "cpu", "--collect-threads", "1", "--threads", "3"],
    "mps": ["--device", "mps", "--collect-device", "cpu", "--evaluation-device", "cpu", "--threads", "1"],
}
PACKAGE = ["--architecture", "targets", "--gamma", ".999", "--gae-lambda", ".99", "--entropy", ".03",
           "--envs", "64", "--rollout", "128",
           "--validation-seed-start", "23000001", "--validation-episodes", "128",
           "--test-seed-start", "25000001"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--arms", nargs="+", default=list(ARMS))
    p.add_argument("--seeds", nargs="+", type=int, default=[901, 902])
    p.add_argument("--steps", type=int, default=16_777_216)
    p.add_argument("--interval", type=int, default=4_194_304)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--layout", choices=list(LAYOUTS), default="cpu")
    a = p.parse_args()
    (a.out / "runs").mkdir(parents=True, exist_ok=True)
    (a.out / "logs").mkdir(exist_ok=True)
    jobs = [(arm, seed) for seed in a.seeds for arm in a.arms
            if not (a.out / "runs" / f"{arm}-{seed}" / "summary.json").exists()]
    record = a.out / "screen.json"
    previous = json.loads(record.read_text()) if record.exists() else {}
    layouts = {**previous.get("seed_layouts", {}), **{str(s): LAYOUTS[a.layout] for s in a.seeds}}
    record.write_text(json.dumps({"arms": {**previous.get("arms", {}), **{k: ARMS[k] for k in a.arms}},
        "package": PACKAGE, "seed_layouts": layouts,
        "seeds": a.seeds, "steps": a.steps, "interval": a.interval, "workers": a.workers,
        "validation_worlds": [23000001, 23000128], "reserved_test_worlds_unused": [25000001, 25000128],
        "environment": f"v{SPEC.version} ({os.environ.get('TERRARIA_LITE_LIB') or 'package library'}), unchanged mechanics"},
        indent=2) + "\n")
    running = {}
    while jobs or running:
        while jobs and len(running) < a.workers:
            arm, seed = jobs.pop(0)
            name = f"{arm}-{seed}"
            out = a.out / "runs" / name
            if out.exists():  # interrupted earlier: keep evidence, do not overwrite
                out.rename(out.with_name(f"{name}.interrupted-{int(time.time())}"))
            cmd = [sys.executable, str(ROOT / "tools/iterate_ppo.py"), "--out", str(out), "--seed", str(seed),
                   "--steps", str(a.steps), "--interval", str(a.interval), *PACKAGE, *LAYOUTS[a.layout], *ARMS[arm]]
            log = (a.out / "logs" / f"{name}.log").open("w")
            running[name] = (subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT), log)
            print("started", name, flush=True)
        for name, (proc, log) in list(running.items()):
            if proc.poll() is not None:
                log.close()
                del running[name]
                print("finished" if proc.returncode == 0 else f"FAILED rc={proc.returncode}", name, flush=True)
        time.sleep(5)
    print("screen complete", flush=True)


if __name__ == "__main__":
    main()
