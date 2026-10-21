"""Throughput and determinism harness for the real trainer (ppo_agent.train).

Runs train() at realistic settings (targets model, potential 3, gamma .999,
GAE .99, entropy .03, rollout 128, 4 epochs, minibatches 16, collect and learn
on the GPU, like tools/explore_screen.py's pot_e1024/pot_e4096 arms) for a few
iterations and reports steady-state steps/s (first iteration excluded), the
collection/optimisation split, and a SHA-256 over the final parameters plus the
episode telemetry, so two runs can be compared for bit-identity.

    HIP_VISIBLE_DEVICES=7 PYTHONPATH=<checkout>/python python perf/bench_trainer.py \
        --envs 1024 --iters 6 [--set native_autoreset=1 compact_obs=1 ...]

Which checkout is measured is decided by PYTHONPATH (this branch or main).
"""
import argparse, hashlib, json, os, time

import torch


def parse_value(v):
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(v.lower(), v)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--envs", type=int, default=1024)
    p.add_argument("--iters", type=int, default=6)
    p.add_argument("--minibatches", type=int, default=16)
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--potential", type=float, default=3.0)
    p.add_argument("--seed", type=int, default=901)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--sim-workers", type=int, default=0, help="default: 12 at <=1024 envs, else 16")
    p.add_argument("--set", nargs="*", default=[], help="extra Config fields, key=value")
    p.add_argument("--label", default="")
    a = p.parse_args()
    torch.set_num_threads(a.threads)
    from terraria_lite.ppo_agent import Config, train
    import terraria_lite
    extra = {k: parse_value(v) for k, v in (s.split("=", 1) for s in a.set)}
    for k, v in list(extra.items()):
        if isinstance(v, int) and isinstance(getattr(Config, k, None), bool):
            extra[k] = bool(v)
    cfg = Config(total_steps=a.envs * 128 * a.iters, num_envs=a.envs, rollout=128, epochs=a.epochs,
                 minibatches=a.minibatches, gamma=.999, gae_lambda=.99, ent_coef=.03, seed=a.seed,
                 device="cuda", collect_device="cuda", sim_workers=a.sim_workers or (12 if a.envs <= 1024 else 16),
                 architecture="targets", potential_coef=a.potential, quiet=True, save="", **extra)
    marks = []

    def callback(agent, steps, profile):
        torch.cuda.synchronize()
        marks.append((time.perf_counter(), steps, profile["collection_seconds"], profile["optimisation_seconds"]))
        callback.agent = agent

    t0 = time.perf_counter()
    summary = train(cfg, checkpoint_callback=callback)
    (ta, sa, ca, oa), (tb, sb, cb, ob) = marks[0], marks[-1]
    h = hashlib.sha256()
    for k, v in sorted(callback.agent.state_dict().items()):
        h.update(k.encode()); h.update(v.detach().float().cpu().numpy().tobytes())
    tel = {k: summary[k] for k in ("n_ep", "ach", "ret", "len", "died", "hits")}
    h.update(json.dumps(tel, sort_keys=True).encode())
    out = {"label": a.label, "package": os.path.dirname(terraria_lite.__file__), "envs": a.envs,
           "iters_timed": len(marks) - 1, "flags": extra,
           "steady_sps": round((sb - sa) / (tb - ta)),
           "collect_s_per_iter": round((cb - ca) / (len(marks) - 1), 3),
           "learn_s_per_iter": round((ob - oa) / (len(marks) - 1), 3),
           "collect_share": round((cb - ca) / max((cb - ca) + (ob - oa), 1e-9), 3),
           "overall_sps_incl_first_iter": round(summary["sps"]), "wall_s": round(time.perf_counter() - t0, 1),
           "telemetry": tel, "result_sha256": h.hexdigest()[:16]}
    print("BENCH " + json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
