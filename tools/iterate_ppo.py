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
from terraria_lite.ppo_eval import evaluate, evaluate_checkpoint, load_agent


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
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--encoder", type=int, default=128)
    p.add_argument("--hidden", type=int, default=0,
                   help="trunk width; 0 = architecture default (128 for lstm/lstm_targets)")
    p.add_argument("--depth", type=int, default=2, help="global trunk layers (targets, mlp)")
    p.add_argument("--cell-width", type=int, default=32, help="per-cell MLP width (targets)")
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
    p.add_argument("--sim-workers", type=int, default=4, help="C threads stepping the env batch (results unchanged)")
    p.add_argument("--archive-start-prob", type=float, default=0.0)
    p.add_argument("--archive-capacity", type=int, default=4096)
    p.add_argument("--sil-minibatches", type=int, default=0)
    p.add_argument("--sil-value-coef", type=float, default=0.01)
    p.add_argument("--novelty", type=float, default=0.0)
    p.add_argument("--potential", type=float, default=0.0)
    p.add_argument("--potential-mode", choices=["mean", "frontier", "frontier_surface"], default="mean",
                   help="frontier: shaping averages only over recipes whose achievement is not yet earned; "
                        "frontier_surface: plus a climb-back goal after descending deep")
    p.add_argument("--memory-features", default="", help='policy feature sets, e.g. "stations_v1+craftable_v1"')
    p.add_argument("--aux", type=float, default=0.0, help="predictive inventory/unlock auxiliary loss weight")
    p.add_argument("--episode-steps", type=int, default=0,
                   help="episode step limit for training AND validation; 0 = game default (3000)")
    # Performance options (perf/REPORT.md); exact ones leave results unchanged.
    p.add_argument("--native-autoreset", action="store_true", help="exact: reset finished lanes in C")
    p.add_argument("--compact-obs", action="store_true", help="exact: uint8 obs rows, one-hot on the GPU")
    p.add_argument("--compile", action="store_true", help="torch.compile the policy (changes rounding)")
    p.add_argument("--bf16", action="store_true", help="bfloat16 autocast in the PPO update (changes rounding)")
    p.add_argument("--fused-adam", action="store_true", help="fused Adam kernel (changes rounding)")
    p.add_argument("--compile-all", action="store_true",
                   help="also torch.compile the whole sampling forward and minibatch loss (changes rounding)")
    p.add_argument("--sim-backend", choices=["cpu", "gpu"], default="cpu",
                   help="exact: gpu simulates on --collect-device (needs perf/gpusim/libgpusim.so)")
    p.add_argument("--async-evaluation", action="store_true",
                   help="exact: evaluate the checkpoint copies in a worker process while training continues "
                        "(needs --evaluation-device other than --device)")
    a = p.parse_args()
    if a.out.exists():
        raise ValueError("Output exists; select a fresh directory")
    evaluation_device = a.evaluation_device or a.device
    if a.async_evaluation and evaluation_device == a.device:
        raise ValueError("--async-evaluation evaluates checkpoint copies: set --evaluation-device != --device")
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
                  minibatches=a.minibatches,epochs=a.epochs,bootstrap_time_limit=a.bootstrap_time_limit)
    if recurrent:
        kwargs.update(architecture=a.architecture,encoder=a.encoder,hidden=a.hidden or 128)
        if a.depth != 2 or a.cell_width != 32:
            raise ValueError("--depth/--cell-width are feed-forward size knobs")
    elif "architecture" in config_class.__dataclass_fields__:
        kwargs["architecture"] = a.architecture
        kwargs.update(hidden=a.hidden, depth=a.depth, cell_width=a.cell_width)
        kwargs["achievement_reward"] = a.achievement_reward
        kwargs["curiosity_coef"] = a.curiosity
        kwargs["curiosity_balanced"] = a.balanced_curiosity
        kwargs["curiosity_anneal"] = not a.persistent_curiosity
        kwargs.update(collect_device=a.collect_device, collect_threads=a.collect_threads, sim_workers=a.sim_workers,
                      archive_start_prob=a.archive_start_prob, archive_capacity=a.archive_capacity,
                      sil_minibatches=a.sil_minibatches, sil_value_coef=a.sil_value_coef,
                      novelty_coef=a.novelty, potential_coef=a.potential, potential_mode=a.potential_mode,
                      memory_features=a.memory_features, aux_coef=a.aux,
                      native_autoreset=a.native_autoreset, compact_obs=a.compact_obs,
                      compile=a.compile, bf16=a.bf16, fused_adam=a.fused_adam, compile_all=a.compile_all,
                      sim_backend=a.sim_backend, episode_steps=a.episode_steps)
    elif a.architecture != "mlp":
        raise ValueError("This implementation does not support CNN")
    cfg = config_class(**kwargs)
    if a.episode_steps and getattr(cfg, "episode_steps", 0) != a.episode_steps:
        raise ValueError("--episode-steps is supported by the feed-forward PPO trainer only")
    actual = a.steps // cfg.batch * cfg.batch
    if actual < cfg.batch:
        raise ValueError("At least one complete batch required")
    a.out.mkdir(parents=True)
    package = Path(terraria_lite.__file__).parent
    # The library actually loaded ($TERRARIA_LITE_LIB may select another game version).
    sources = [*package.glob("*.py"), Path(terraria_lite._lib._name).resolve()]
    from terraria_lite.achievement_rewards import reward_spec
    if recurrent:
        from terraria_lite.recurrent_ppo_agent import build_recurrent_agent
        build = lambda: build_recurrent_agent(cfg.architecture, cfg.encoder, cfg.hidden)
    else:
        from terraria_lite.spatial_agent import build_agent
        extra = 0
        if a.memory_features:
            from terraria_lite.memory_features import PolicyFeatures
            extra = PolicyFeatures(a.memory_features, 1).N_FEATURES
        build = lambda: build_agent(cfg.architecture, cfg.hidden, extra, depth=cfg.depth, cell_width=cfg.cell_width)
    with torch.random.fork_rng(devices=[]):
        parameters = sum(p.numel() for p in build().parameters())
    protocol = {"config": asdict(cfg), "actual_steps": actual, "parameters": parameters,
                "driver_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "evaluation_device":evaluation_device, "async_evaluation": a.async_evaluation,
                "environment_version": SPEC.version, "torch_threads": a.threads,
                "episode_steps": a.episode_steps or SPEC.default_steps,
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
    seeds = list(range(a.validation_seed_start, a.validation_seed_start+a.validation_episodes))
    # Asynchronous evaluation: the same evaluate(load_agent(checkpoint)) call
    # with the same torch thread count, in one spawned worker; rows are
    # recorded in checkpoint order as they complete.
    executor = pending = None
    if a.async_evaluation:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        executor, pending = ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn")), []

    def record(steps, profile, result, checkpoint_seconds):
        row = {"steps": steps, "elapsed_seconds": time.perf_counter()-start,
               "profile": profile, "evaluation": result}
        if executor is not None:
            row["checkpoint_elapsed_seconds"] = checkpoint_seconds
        curve.append(row)
        (a.out / "curve.json").write_text(json.dumps(curve, indent=2)+"\n")
        hits = result["hits"]
        print(f"{a.out.name}: {steps:,} {result['mean_achievements']:.3f}/32 "
              f"death={result['death_rate']:.1%} bench={hits.get('craft workbench',0)} "
              f"stone={hits.get('collect stone',0)} furnace={hits.get('craft furnace',0)} "
              f"peak-y={result['mean_peak_depth']:.1f} ({row['elapsed_seconds']:.1f}s)", flush=True)

    def drain(wait):
        while pending and (wait or pending[0][-1].done()):
            steps, profile, checkpoint_seconds, future = pending.pop(0)
            record(steps, profile, future.result(), checkpoint_seconds)

    def callback(agent, steps, profile):
        nonlocal next_eval
        if pending:
            drain(False)
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
        checkpoint = a.out / f"step-{steps}.pt"
        torch.save(data, checkpoint)
        next_eval += a.interval
        if executor is not None:
            pending.append((steps, profile, time.perf_counter()-start,
                            executor.submit(evaluate_checkpoint, checkpoint, evaluation_device, seeds,
                                            num_envs=64, sample_seed=54321, threads=a.threads,
                                            max_steps=a.episode_steps)))
            return
        with torch.random.fork_rng():
            # Never move the live learner: that can invalidate optimizer tensor
            # references/state. Restore a separate frozen checkpoint copy.
            evaluation_agent=agent if evaluation_device==a.device else load_agent(checkpoint,evaluation_device)
            result = evaluate(evaluation_agent, seeds, num_envs=64, sample_seed=54321, device=evaluation_device,
                              max_steps=a.episode_steps)
        record(steps, profile, result, None)
    summary = train_function(cfg, checkpoint_callback=callback)
    if executor is not None:
        drain(True)
        executor.shutdown()
    if a.device == "mps":
        torch.mps.synchronize()
    summary["wall_seconds_including_validation"] = time.perf_counter()-start
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(f"Completed {a.out.name}: {summary['wall_seconds_including_validation']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
