"""Fixed-budget sparse PPO experiments with validation and pre-run provenance."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import shutil
import torch
import terraria_lite
from terraria_lite import SPEC
from terraria_lite.ppo_agent import Config, train
from terraria_lite.ppo_eval import evaluate, load_agent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--steps", type=int, default=4_194_304)
    p.add_argument("--seed", type=int, default=101)
    p.add_argument("--envs", type=int, default=64)
    p.add_argument("--rollout", type=int, default=128)
    p.add_argument("--interval", type=int, default=1_048_576)
    p.add_argument("--threads", type=int, default=6)
    p.add_argument("--architecture", choices=["mlp", "cnn", "tokens", "separate","targets","lstm","lstm_targets"], default="mlp")
    p.add_argument("--minibatches", type=int, default=4)
    p.add_argument("--encoder", type=int, default=128)
    p.add_argument("--hidden", type=int, default=128)
    p.add_argument("--bootstrap-time-limit", action="store_true")
    p.add_argument("--persistent-curiosity", action="store_true")
    p.add_argument("--gamma", type=float, default=.999)
    p.add_argument("--achievement-reward", choices=["equal", "difficulty"], default="equal")
    p.add_argument("--gae-lambda", type=float, default=.95)
    p.add_argument("--entropy", type=float, default=.01)
    p.add_argument("--lr", type=float, default=.0003)
    p.add_argument("--device", default="cpu")
    p.add_argument("--evaluation-device",help="Optional checkpoint-copy evaluation backend; default is training device")
    p.add_argument("--constant-lr", action="store_true")
    p.add_argument("--curiosity", type=float, default=0.0)
    p.add_argument("--balanced-curiosity", action="store_true")
    p.add_argument("--validation-episodes", type=int, default=128)
    p.add_argument("--validation-seed-start",type=int,default=2_000_001)
    p.add_argument("--test-seed-start",type=int,default=7_000_001 if SPEC.version>=4 else 3_000_001)
    p.add_argument("--collect-device", default="")
    p.add_argument("--collect-threads", type=int, default=0)
    p.add_argument("--archive-start-prob", type=float, default=0.0)
    p.add_argument("--archive-capacity", type=int, default=4096)
    p.add_argument("--sil-minibatches", type=int, default=0)
    p.add_argument("--sil-value-coef", type=float, default=0.01)
    p.add_argument("--novelty", type=float, default=0.0)
    p.add_argument("--potential", type=float, default=0.0)
    p.add_argument("--memory-features", default="", help='policy feature sets, e.g. "stations_v1+craftable_v1"')
    p.add_argument("--aux", type=float, default=0.0, help="predictive inventory/unlock auxiliary loss weight")
    a = p.parse_args()
    if a.out.exists():
        raise ValueError("Output exists; select a fresh directory")
    torch.set_num_threads(a.threads)
    recurrent = a.architecture in ("lstm", "lstm_targets")
    config_class, train_function = Config, train
    if recurrent:
        if a.achievement_reward != "equal":
            raise ValueError("Weighted reward study currently supports feedforward PPO only")
        from terraria_lite.recurrent_ppo_agent import Config as RecurrentConfig, train as recurrent_train
        config_class, train_function = RecurrentConfig, recurrent_train
        if a.curiosity or a.balanced_curiosity or a.persistent_curiosity:
            raise ValueError("Recurrent novelty is not part of this implementation")
    kwargs = dict(total_steps=a.steps, num_envs=a.envs, rollout=a.rollout,
                  seed=a.seed, quiet=True, save="", gamma=a.gamma,
                  gae_lambda=a.gae_lambda, ent_coef=a.entropy, lr=a.lr,
                  anneal_lr=not a.constant_lr, device=a.device,
                  minibatches=a.minibatches,bootstrap_time_limit=a.bootstrap_time_limit)
    if recurrent:
        kwargs.update(architecture=a.architecture,encoder=a.encoder,hidden=a.hidden)
    elif "architecture" in config_class.__dataclass_fields__:
        kwargs["architecture"] = a.architecture
        kwargs["achievement_reward"] = a.achievement_reward
        kwargs["curiosity_coef"] = a.curiosity
        kwargs["curiosity_balanced"] = a.balanced_curiosity
        kwargs["curiosity_anneal"] = not a.persistent_curiosity
        kwargs.update(collect_device=a.collect_device, collect_threads=a.collect_threads,
                      archive_start_prob=a.archive_start_prob, archive_capacity=a.archive_capacity,
                      sil_minibatches=a.sil_minibatches, sil_value_coef=a.sil_value_coef,
                      novelty_coef=a.novelty, potential_coef=a.potential,
                      memory_features=a.memory_features, aux_coef=a.aux)
    elif a.architecture != "mlp":
        raise ValueError("This implementation does not support CNN")
    cfg = config_class(**kwargs)
    actual = a.steps // cfg.batch * cfg.batch
    if actual < cfg.batch:
        raise ValueError("At least one complete batch required")
    a.out.mkdir(parents=True)
    package = Path(terraria_lite.__file__).parent
    # The library actually loaded ($TERRARIA_LITE_LIB may select another game version).
    sources = [*package.glob("*.py"), Path(terraria_lite._lib._name).resolve()]
    from terraria_lite.achievement_rewards import reward_spec
    protocol = {"config": asdict(cfg), "actual_steps": actual,
                "driver_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "evaluation_device":a.evaluation_device or a.device,
                "environment_version": SPEC.version, "torch_threads": a.threads,
                "validation_seeds": [a.validation_seed_start, a.validation_seed_start+a.validation_episodes-1],
                "reserved_test_seeds": [a.test_seed_start,a.test_seed_start+127],
                "sampler_seed": 54321, "reward": reward_spec(a.achievement_reward),
                "training_objective": {"discount":cfg.gamma,
                    "deadline_future_value":"legacy bootstrap control" if cfg.bootstrap_time_limit else "zero (finite horizon)"},
                "demonstrations": False, "prerequisite_shaping": "potential-based recipe progress" if a.potential else False,
                "training_novelty": "RND observation prediction error" if a.curiosity else
                    "progress-cell episodic count bonus" if a.novelty else None,
                "training_start_states": "Go-Explore archive restores (training only)" if a.archive_start_prob else "fresh worlds",
                "implementation_sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},
                "package": str(package), "torch": torch.__version__}
    (a.out / "protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    snapshot=a.out/"implementation"; snapshot.mkdir()
    for source in sources: shutil.copy2(source,snapshot/source.name)
    curve = []; next_eval = a.interval; start = time.perf_counter()
    def callback(agent, steps, profile):
        nonlocal next_eval
        if steps < next_eval and steps != actual:
            return
        if a.device == "mps":
            torch.mps.synchronize()
        data = {"model": agent.state_dict(), "architecture": a.architecture,
                "environment_version": SPEC.version, "obs_size": SPEC.obs_size,
                "n_actions": SPEC.n_actions,"training_objective":protocol["training_objective"]}
        if getattr(agent, "memory_features", None):
            data.update(memory_features=agent.memory_features, extra=agent.trunk.extra)
        if recurrent:
            data.update(encoder=cfg.encoder,hidden=cfg.hidden)
        torch.save(data, a.out / f"step-{steps}.pt")
        evaluation_device=a.evaluation_device or a.device
        with torch.random.fork_rng():
            # Never move the live learner: that can invalidate optimizer tensor
            # references/state. Restore a separate frozen checkpoint copy.
            evaluation_agent=agent if evaluation_device==a.device else load_agent(a.out/f"step-{steps}.pt",evaluation_device)
            result = evaluate(evaluation_agent, list(range(a.validation_seed_start, a.validation_seed_start+a.validation_episodes)),
                              num_envs=64, sample_seed=54321, device=evaluation_device)
        row = {"steps": steps, "elapsed_seconds": time.perf_counter()-start,
               "profile": profile, "evaluation": result}
        curve.append(row)
        (a.out / "curve.json").write_text(json.dumps(curve, indent=2)+"\n")
        hits = result["hits"]
        print(f"{a.out.name}: {steps:,} {result['mean_achievements']:.3f}/32 "
              f"death={result['death_rate']:.1%} bench={hits.get('craft workbench',0)} "
              f"stone={hits.get('collect stone',0)} furnace={hits.get('craft furnace',0)} "
              f"peak-y={result['mean_peak_depth']:.1f} ({row['elapsed_seconds']:.1f}s)", flush=True)
        next_eval += a.interval
    summary = train_function(cfg, checkpoint_callback=callback)
    if a.device == "mps":
        torch.mps.synchronize()
    summary["wall_seconds_including_validation"] = time.perf_counter()-start
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(f"Completed {a.out.name}: {summary['wall_seconds_including_validation']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
