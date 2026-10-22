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
    # eg18 batch-scale study (gpu layout): same objective, larger env batches on
    # the GPU. Later flags override the 64-env package defaults.
    "pot_e1024": ["--potential", "3", "--envs", "1024", "--minibatches", "16", "--collect-device", "cuda",
                  "--sim-workers", "12", "--threads", "4"],
    "pot_e4096": ["--potential", "3", "--envs", "4096", "--minibatches", "16", "--collect-device", "cuda",
                  "--sim-workers", "16", "--threads", "4"],
    "pot_e4096_r32": ["--potential", "3", "--envs", "4096", "--rollout", "32", "--minibatches", "4",
                      "--collect-device", "cuda", "--sim-workers", "16", "--threads", "4"],
    "pot_e4096_lr1e3": ["--potential", "3", "--envs", "4096", "--minibatches", "16", "--lr", ".001",
                        "--collect-device", "cuda", "--sim-workers", "16", "--threads", "4"],
    "ctl_e4096": ["--envs", "4096", "--minibatches", "16", "--collect-device", "cuda",
                  "--sim-workers", "16", "--threads", "4"],
    "ctl_e1024": ["--envs", "1024", "--minibatches", "16", "--collect-device", "cuda",
                  "--sim-workers", "12", "--threads", "4"],
    # Batch x learning-rate x update-count study (potential, v4). Minibatch size
    # is held at 8,192 unless stated, so arms differ in envs/LR/gradient steps.
    "pot_e256": ["--potential", "3", "--envs", "256", "--minibatches", "4", "--collect-device", "cuda",
                 "--sim-workers", "4", "--threads", "2"],
    "pot_e1024_lr1e4": ["--potential", "3", "--envs", "1024", "--minibatches", "16", "--lr", ".0001",
                        "--collect-device", "cuda", "--sim-workers", "12", "--threads", "4"],
    "pot_e1024_lr6e4": ["--potential", "3", "--envs", "1024", "--minibatches", "16", "--lr", ".0006",
                        "--collect-device", "cuda", "--sim-workers", "12", "--threads", "4"],
    "pot_e1024_lr1e3": ["--potential", "3", "--envs", "1024", "--minibatches", "16", "--lr", ".001",
                        "--collect-device", "cuda", "--sim-workers", "12", "--threads", "4"],
    "pot_e2048": ["--potential", "3", "--envs", "2048", "--minibatches", "32", "--collect-device", "cuda",
                  "--sim-workers", "16", "--threads", "4"],
    "pot_e2048_lr6e4": ["--potential", "3", "--envs", "2048", "--minibatches", "32", "--lr", ".0006",
                        "--collect-device", "cuda", "--sim-workers", "16", "--threads", "4"],
    # 4,096 envs with the 1,024-env minibatch size (8,192): 4x the gradient steps of pot_e4096.
    "pot_e4096_mb64": ["--potential", "3", "--envs", "4096", "--minibatches", "64", "--collect-device", "cuda",
                       "--sim-workers", "16", "--threads", "4"],
    "pot_e4096_ep8": ["--potential", "3", "--envs", "4096", "--minibatches", "16", "--epochs", "8",
                      "--collect-device", "cuda", "--sim-workers", "16", "--threads", "4"],
    "pot_e4096_lr2e3": ["--potential", "3", "--envs", "4096", "--minibatches", "16", "--lr", ".002",
                        "--collect-device", "cuda", "--sim-workers", "16", "--threads", "4"],
    # Frontier: more gradient steps and higher LR together at larger batches.
    "pot_e2048_lr1e3": ["--potential", "3", "--envs", "2048", "--minibatches", "32", "--lr", ".001",
                        "--collect-device", "cuda", "--sim-workers", "16", "--threads", "4"],
    "pot_e4096_lr2e3_mb64": ["--potential", "3", "--envs", "4096", "--minibatches", "64", "--lr", ".002",
                             "--collect-device", "cuda", "--sim-workers", "16", "--threads", "4"],
    "pot_e8192_lr2e3_mb128": ["--potential", "3", "--envs", "8192", "--minibatches", "128", "--lr", ".002",
                              "--collect-device", "cuda", "--sim-workers", "24", "--threads", "4"],
    # Long-run default (1,024 envs, LR 3e-4) on the merged max-speed path (perf/REPORT.md).
    "pot_e1024_max": ["--potential", "3", "--envs", "1024", "--minibatches", "16", "--collect-device", "cuda",
                      "--sim-workers", "12", "--threads", "4",
                      "--native-autoreset", "--compact-obs", "--compile", "--bf16", "--fused-adam"],
}
# "25 wall" study (v7, max path): what moves the never/rarely earned achievements?
# Later flags override pot_e1024_max's (argparse keeps the last value).
for _name, _extra in {"wall_ctl": [], "wall_pot10": ["--potential", "10"], "wall_ent05": ["--entropy", ".05"],
                      "wall_nov01": ["--novelty", ".01"],
                      "wall_pot10_nov01": ["--potential", "10", "--novelty", ".01"],
                      # Shaping pull only toward not-yet-earned recipes (potential.py mode="frontier").
                      "wall_frontier": ["--potential-mode", "frontier"],
                      "wall_frontier_nov01": ["--potential-mode", "frontier", "--novelty", ".01"],
                      # Frontier plus a climb-back goal after descending deep (return to surface).
                      "wall_frontier_surface": ["--potential-mode", "frontier_surface"],
                      # Stockpiling study: the best policy never holds 10 iron bars / 30 wood
                      # (craft never legal); does a stronger frontier pull make it hoard?
                      "wall_fn_p10": ["--potential-mode", "frontier", "--novelty", ".01", "--potential", "10"],
                      "wall_fn_p30": ["--potential-mode", "frontier", "--novelty", ".01", "--potential", "30"],
                      "wall_fsn_p30": ["--potential-mode", "frontier_surface", "--novelty", ".01",
                                       "--potential", "30"]}.items():
    ARMS[_name] = ARMS["pot_e1024_max"] + _extra
# Standard for new studies after perf round 2 (perf/REPORT.md section 7): max path plus
# background evaluation (exact) and --compile-all (changes rounding, learning check
# passed). Not bit-comparable with pot_e1024_max runs: include a max2 control.
ARMS["pot_e1024_max2"] = ARMS["pot_e1024_max"] + ["--async-evaluation", "--compile-all"]
ARMS["max2_frontier_nov01"] = ARMS["pot_e1024_max2"] + ["--potential-mode", "frontier", "--novelty", ".01"]
# Horizon test: same arms with 6,000-step episodes for training and validation.
ARMS["max2_ep6000"] = ARMS["pot_e1024_max2"] + ["--episode-steps", "6000"]
ARMS["max2_fn_ep6000"] = ARMS["max2_frontier_nov01"] + ["--episode-steps", "6000"]
# Device layouts. Arms are only compared within one layout (seed blocks): the
# MPS learner differs from CPU by float rounding. collect_threads=1 on CPU is
# bit-identical to the original CPU learner. (An earlier "MPS stall" reading
# was a misdiagnosis: ps CPU time is unreliable here; 8 concurrent hybrid
# learners measured ~3.5k steps/s each alongside 8 CPU runs.)
LAYOUTS = {
    "cpu": ["--device", "cpu", "--collect-threads", "1", "--threads", "3"],
    "mps": ["--device", "mps", "--collect-device", "cpu", "--evaluation-device", "cpu", "--threads", "1"],
    # ROCm/CUDA learner, CPU rollouts; each run pinned to one GPU via --gpus.
    "gpu": ["--device", "cuda", "--collect-device", "cpu", "--evaluation-device", "cpu", "--threads", "1",
            "--sim-workers", "1"],
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
    p.add_argument("--gpus", nargs="+", default=[], help="device ids; each run goes to the least-loaded one")
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
        "environment": f"v{SPEC.version} ({os.environ.get('TERRARIA_LITE_LIB') or 'package library'}), unchanged mechanics",
        "gpus": a.gpus},
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
            env = dict(os.environ)
            gpu = None
            if a.gpus:
                load = {g: sum(r[2] == g for r in running.values()) for g in a.gpus}
                gpu = min(a.gpus, key=lambda g: (load[g], a.gpus.index(g)))
                env["HIP_VISIBLE_DEVICES"] = gpu   # ROCm; also setting CUDA_VISIBLE_DEVICES would filter twice
            log = (a.out / "logs" / f"{name}.log").open("w")
            running[name] = (subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT), log, gpu)
            print("started", name, f"gpu={gpu}" if gpu is not None else "", flush=True)
        for name, (proc, log, _) in list(running.items()):
            if proc.poll() is not None:
                log.close()
                del running[name]
                print("finished" if proc.returncode == 0 else f"FAILED rc={proc.returncode}", name, flush=True)
        time.sleep(5)
    print("screen complete", flush=True)


if __name__ == "__main__":
    main()
