"""K simultaneous trainer runs on one GPU (GPU 7), splitting 16 CPU threads
(368-383) evenly: aggregate and per-run steady steps/s plus CPU time used.

    HIP_VISIBLE_DEVICES=7 python perf/bench_concurrency.py --envs 1024 --runs 1 2 4 --config exact
"""
import argparse, json, os, resource, subprocess, sys, time

CONFIGS = {"exact": "native_autoreset=1 compact_obs=1",
           "max": "native_autoreset=1 compact_obs=1 compile=1 bf16=1 fused_adam=1",
           "gpu": "sim_backend=gpu compact_obs=1",
           "gpu-max": "sim_backend=gpu compact_obs=1 compile=1 bf16=1 fused_adam=1"}
CPUS = list(range(368, 384))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--envs", type=int, default=1024)
    p.add_argument("--runs", type=int, nargs="+", default=[1, 2, 4])
    p.add_argument("--config", choices=list(CONFIGS), default="exact")
    p.add_argument("--iters", type=int, default=6)
    a = p.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "PYTHONPATH": os.path.join(root, "python"), "PYTHONDONTWRITEBYTECODE": "1",
           "HIP_VISIBLE_DEVICES": "7", "TORCHINDUCTOR_CACHE_DIR": os.path.join(root, "perf", ".inductor")}
    for k in a.runs:
        share = len(CPUS) // k
        procs = []
        t0 = time.perf_counter()
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        for r in range(k):
            cpus = CPUS[r * share:(r + 1) * share]
            cmd = ["taskset", "-c", ",".join(map(str, cpus)), sys.executable, "perf/bench_trainer.py",
                   "--envs", str(a.envs), "--iters", str(a.iters), "--seed", str(901 + r),
                   "--threads", str(max(1, share // 4)), "--sim-workers", str(share),
                   "--label", f"{a.config}-k{k}-r{r}", "--set", *CONFIGS[a.config].split()]
            procs.append(subprocess.Popen(cmd, cwd=root, env={**env, "OMP_NUM_THREADS": str(max(1, share // 4))},
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
        rows = []
        for pr in procs:
            out = pr.communicate()[0]
            line = [l for l in out.splitlines() if l.startswith("BENCH ")]
            rows.append(json.loads(line[-1][6:]) if line else {"error": out[-300:]})
        wall = time.perf_counter() - t0
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu_s = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
        ok = [r for r in rows if "steady_sps" in r]
        print("CONC " + json.dumps({"config": a.config, "envs": a.envs, "runs": k, "cpus_per_run": share,
                                    "per_run_sps": [r["steady_sps"] for r in ok],
                                    "aggregate_sps": sum(r["steady_sps"] for r in ok),
                                    "aggregate_incl_startup_sps": round(len(ok) * a.envs * 128 * a.iters / wall),
                                    "collect_share": [r["collect_share"] for r in ok],
                                    "cpu_cores_busy": round(cpu_s / wall, 1), "wall_s": round(wall, 1),
                                    "errors": [r["error"] for r in rows if "error" in r]}), flush=True)


if __name__ == "__main__":
    main()
