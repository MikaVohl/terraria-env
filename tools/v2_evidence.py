"""Curate completed validation curves without selecting checkpoints or using test worlds."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import numpy as np
import torch
from terraria_lite import SPEC
from terraria_lite.ppo_agent import ActorCritic
from terraria_lite.ppo_eval import evaluate

def main():
    if SPEC.version!=2:
        raise ValueError("Historical v2 evidence requires the matching frozen v2 package. Use current iteration evidence for v3.")
    p=argparse.ArgumentParser(); p.add_argument("--study",type=Path,default=Path("experiments/v2-first-curves"))
    p.add_argument("--out",type=Path,default=Path("docs/reports/V2_RESULTS.json"))
    a=p.parse_args(); torch.set_num_threads(6); rows=[]
    for kind in ("mlp","lstm"):
        for seed in (101,202,303):
            root=a.study/f"{kind}-{seed}"
            curve=json.loads((root/"curve.json").read_text())
            summary=json.loads((root/"summary.json").read_text())
            last=curve[-1]; ev=last["evaluation"]
            rows.append({"kind":kind,"seed":seed,"steps":last["steps"],
                "mean_achievements":ev["mean_achievements"],"death_rate":ev["death_rate"],
                "max_achievements":ev["max_achievements"],"mean_length":ev["mean_length"],
                "wall_seconds_including_validation":summary["wall_seconds"],
                "achievement_rates":{n:ev["hits"].get(n,0)/ev["episodes"] for n in SPEC.achievement_names},
                "curve":[{"steps":c["steps"],"mean_achievements":c["evaluation"]["mean_achievements"],
                          "death_rate":c["evaluation"]["death_rate"]} for c in curve]})
    torch.manual_seed(42)
    random=ActorCritic(SPEC.obs_size,SPEC.n_actions)
    torch.nn.init.zeros_(random.actor.weight); torch.nn.init.zeros_(random.actor.bias)
    uniform=evaluate(random,list(range(2000001,2000129)),num_envs=64,sample_seed=54321)
    aggregate={}
    for kind in ("mlp","lstm"):
        group=[r for r in rows if r["kind"]==kind]
        aggregate[kind]={"mean_achievements":float(np.mean([r["mean_achievements"] for r in group])),
            "std_across_training_seeds":float(np.std([r["mean_achievements"] for r in group],ddof=1)),
            "mean_death_rate":float(np.mean([r["death_rate"] for r in group])),
            "achievement_rates":{n:float(np.mean([r["achievement_rates"][n] for r in group]))
                                 for n in SPEC.achievement_names}}
    # This is an implementation snapshot after non-semantic guard/UI repairs,
    # not a claim that it was recorded before the initial runs.
    files=[*Path("include").glob("*.h"),*Path("src").glob("*.c"),*Path("src").glob("*.h"),
           *Path("python/terraria_lite").glob("*.py"),Path("Makefile")]
    report={"environment_version":SPEC.version,"platform":platform.platform(),
        "torch":torch.__version__,"numpy":np.__version__,"primary_metric":"mean distinct achievements",
        "validation_seeds":[2000001,2000128],"sampler_seed":54321,
        "test_set":"3,000,001..3,000,128 reserved and unused",
        "selection":"final fixed-budget checkpoints, not best validation checkpoints",
        "schema":{"actions":SPEC.n_actions,"items":SPEC.n_items,"achievements":SPEC.n_achievements,
                  "obs_size":SPEC.obs_size},"runs":rows,"aggregate":aggregate,
        "uniform_legal":{"mean_achievements":uniform["mean_achievements"],
                         "death_rate":uniform["death_rate"],"max_achievements":uniform["max_achievements"]},
        "post_run_source_sha256":{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    a.out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"aggregate":aggregate,"uniform_legal":report["uniform_legal"]},indent=2))

if __name__=="__main__": main()
