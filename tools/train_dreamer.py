"""Fixed-budget Dreamer runs with periodic validation and provenance
(the Dreamer counterpart of tools/iterate_ppo.py; same curve.json layout).

    PYTHONPATH=python python tools/train_dreamer.py --out runs/d1 --steps 20000000 --device cuda --bf16
"""
import argparse
from dataclasses import asdict, fields
import hashlib
import json
from pathlib import Path
import time

import torch

import terraria_lite
from terraria_lite import SPEC
from terraria_lite.dreamer.agent import Config, train
from terraria_lite.dreamer.evaluate import evaluate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--steps", type=int, default=1_000_000, help="env steps")
    p.add_argument("--interval", type=int, default=4_194_304, help="env steps between validations")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--validation-episodes", type=int, default=128)
    p.add_argument("--validation-seed-start", type=int, default=23_000_001)
    p.add_argument("--log-every", type=float, default=60.0, help="seconds between training log lines")
    for f in fields(Config):
        if f.name == "total_steps":
            continue
        flag = "--" + f.name.replace("_", "-")
        if f.type in (bool, "bool"):
            p.add_argument(flag, action="store_true")
        else:
            p.add_argument(flag, type=type(f.default), default=f.default)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError("Output exists; select a fresh directory")
    torch.set_num_threads(a.threads)
    cfg = Config(total_steps=a.steps, **{f.name: getattr(a, f.name) for f in fields(Config) if f.name != "total_steps"})
    a.out.mkdir(parents=True)
    package = Path(terraria_lite.__file__).parent
    sources = [*package.glob("*.py"), *(package / "dreamer").glob("*.py"), Path(__file__),
               Path(terraria_lite._lib._name).resolve()]
    protocol = {"algorithm": "DreamerV3-style (see DREAMER_2026_10.md)", "config": asdict(cfg),
                "environment_version": SPEC.version, "library": str(Path(terraria_lite._lib._name).resolve()),
                "validation_seeds": [a.validation_seed_start, a.validation_seed_start + a.validation_episodes - 1],
                "sampler_seed": 54321, "training_worlds_start": cfg.seed * 10_000_000,
                "training_reward": {"extrinsic": "simulator reward (+1 per achievement, -1 death)",
                                    "potential_shaping": {"coef": cfg.potential, "mode": cfg.potential_mode,
                                                          "gamma": cfg.gamma} if cfg.potential else None,
                                    "novelty": cfg.novelty or None,
                                    "note": "shaping is training-only, learned by a separate head; evaluation is extrinsic"},
                "deadline": "cont=0 at death and at the 3,000-step deadline (zero future value, as PPO)",
                "demonstrations": False,
                "implementation_sha256": {str(f.relative_to(f.parents[1])) if f.suffix == ".py" else f.name:
                                          hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},
                "torch": torch.__version__}
    (a.out / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    curve = []
    next_eval = a.interval
    start = time.perf_counter()
    eval_seconds = 0.0
    seeds = list(range(a.validation_seed_start, a.validation_seed_start + a.validation_episodes))

    def validate(agent, steps, profile):
        nonlocal eval_seconds
        t0 = time.perf_counter()
        agent.save(a.out / f"step-{steps}.pt")
        agent.save(a.out / "latest.pt", optimizers=True)
        with torch.random.fork_rng(devices=[agent.device] if agent.device.type == "cuda" else []):
            result = evaluate(agent, seeds, num_envs=64, sample_seed=54321)
        eval_seconds += time.perf_counter() - t0
        row = {"steps": steps, "elapsed_seconds": time.perf_counter() - start,
               "training_seconds": time.perf_counter() - start - eval_seconds,
               "profile": profile, "evaluation": result}
        curve.append(row)
        (a.out / "curve.json").write_text(json.dumps(curve, indent=2) + "\n")
        hits = result["hits"]
        print(f"{a.out.name}: {steps:,} {result['mean_achievements']:.3f}/32 death={result['death_rate']:.1%} "
              f"bench={hits.get('craft workbench', 0)} furnace={hits.get('craft furnace', 0)} "
              f"anvil={hits.get('craft anvil', 0)} peak-y={result['mean_peak_depth']:.1f} "
              f"({row['elapsed_seconds']:.0f}s, eval {time.perf_counter() - t0:.0f}s)", flush=True)

    def callback(agent, steps, profile):
        nonlocal next_eval
        if steps >= next_eval or steps >= cfg.total_steps:
            validate(agent, steps, profile)
            while next_eval <= steps:
                next_eval += a.interval

    summary = train(cfg, callback=callback, log_every=a.log_every, log=lambda s: print(s, flush=True))
    summary["wall_seconds_including_validation"] = time.perf_counter() - start
    summary["validation_seconds"] = eval_seconds
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Completed {a.out.name}: {summary['wall_seconds_including_validation']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
