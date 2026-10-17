"""First unshaped v2 PPO learning curves; fixed validation, untouched test split."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time
import torch
from terraria_lite import SPEC
from terraria_lite.ppo_eval import evaluate
from terraria_lite import ppo_agent as ff, recurrent_ppo_agent as rnn

VALIDATION=list(range(2_000_001,2_000_129))
TEST=list(range(3_000_001,3_000_129))

def checkpoint(agent,kind):
    data={"model":agent.state_dict(),"architecture":kind,
          "environment_version":SPEC.version,"obs_size":SPEC.obs_size,
          "n_actions":SPEC.n_actions}
    if kind=="lstm":
        data.update(encoder=agent.encoder_size,hidden=agent.hidden_size)
    return data

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--steps",type=int,default=1_048_576)
    p.add_argument("--seeds",type=int,nargs="+",default=[101,202,303])
    p.add_argument("--kinds",nargs="+",choices=["mlp","lstm"],default=["mlp","lstm"])
    p.add_argument("--interval",type=int,default=262144)
    p.add_argument("--threads",type=int,default=6)
    p.add_argument("--out",type=Path,default=Path("experiments/v2-first-curves"))
    a=p.parse_args(); torch.set_num_threads(a.threads)
    a.out.mkdir(parents=True,exist_ok=True)
    protocol={"environment_version":SPEC.version,"reward":"one per achievement; death -1",
              "mask":"legal/epistemic only","demonstrations":False,"shaping":False,
              "validation_seeds":VALIDATION,"reserved_test_seeds":TEST,
              "sampler_seed":54321,"training_seeds":a.seeds,"budget":a.steps,
              "torch_threads":a.threads,"native_workers":4}
    protocol["training_world_seed_rule"]="training_seed * 10,000,000 + episode counter"
    protocol_path=a.out/"protocol.json"
    if protocol_path.exists() and json.loads(protocol_path.read_text())!=protocol:
        raise ValueError("Output already belongs to a different protocol; choose a new --out directory")
    protocol_path.write_text(json.dumps(protocol,indent=2)+"\n")
    for kind in a.kinds:
        for seed in a.seeds:
            path=a.out/f"{kind}-{seed}"; path.mkdir(exist_ok=True)
            if (path/"summary.json").exists():
                print(f"Already completed {kind} seed={seed}; leaving outputs untouched",flush=True); continue
            cfg=(ff.Config if kind=="mlp" else rnn.Config)(total_steps=a.steps,
                num_envs=64,rollout=128,seed=seed,progress_coef=0,quiet=True,save="")
            actual_steps=a.steps//cfg.batch*cfg.batch
            if (path/"config.json").exists():
                raise ValueError(f"Incomplete run already exists in {path}; choose a fresh --out rather than overwrite")
            (path/"config.json").write_text(json.dumps(asdict(cfg),indent=2)+"\n")
            curve=[]; next_eval=a.interval; began=time.perf_counter()
            def callback(agent,steps,profile):
                nonlocal next_eval
                if steps<next_eval and steps!=actual_steps: return
                model_path=path/f"step-{steps}.pt"
                torch.save(checkpoint(agent,kind),model_path)
                # Holdout evaluation cannot perturb training's RNG stream.
                with torch.random.fork_rng():
                    result=evaluate(agent,VALIDATION,num_envs=64,sample_seed=54321)
                row={"steps":steps,"elapsed_seconds":time.perf_counter()-began,
                     "profile":profile,"evaluation":result}
                curve.append(row)
                (path/"curve.json").write_text(json.dumps(curve,indent=2)+"\n")
                print(f"{kind} seed={seed} steps={steps:,}: validation "
                      f"{result['mean_achievements']:.3f}/32 death={result['death_rate']:.1%}",flush=True)
                next_eval+=a.interval
            print(f"Starting {kind} seed={seed}, {a.steps:,} unshaped transitions",flush=True)
            summary=(ff.train if kind=="mlp" else rnn.train)(cfg,checkpoint_callback=callback)
            summary.update(environment_version=SPEC.version,wall_seconds=time.perf_counter()-began)
            (path/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
            print(f"Completed {kind} seed={seed}: {summary['wall_seconds']:.1f}s",flush=True)

if __name__=="__main__": main()
