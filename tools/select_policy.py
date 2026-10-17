"""Freeze validation selection, then evaluate exactly once on reserved worlds."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import torch
from terraria_lite import SPEC
from terraria_lite.ppo_eval import evaluate,load_agent,print_report


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--runs",nargs="+",required=True)
    a=p.parse_args()
    if a.out.exists(): raise ValueError("Selection/test output already exists; reserved test must not be rerun for tuning")
    candidates=[]
    for name in a.runs:
        run=a.study/name
        protocol=json.loads((run/"protocol.json").read_text())
        summary=json.loads((run/"summary.json").read_text()) # all must have finished
        assert protocol["environment_version"]==SPEC.version
        assert summary["steps"]==protocol["actual_steps"]
        validation_seeds=protocol["validation_seeds"]
        assert validation_seeds[1]-validation_seeds[0]+1==128
        test_seeds=protocol["reserved_test_seeds"]
        if candidates:
            assert test_seeds==reserved and validation_seeds==validation
        validation=validation_seeds
        reserved=test_seeds
        for row in json.loads((run/"curve.json").read_text()):
            path=run/f"step-{row['steps']}.pt"
            candidates.append({"run":name,"steps":row["steps"],"checkpoint":str(path.resolve()),
                "checkpoint_sha256":sha(path),"protocol_sha256":sha(run/"protocol.json"),
                "mean_achievements":row["evaluation"]["mean_achievements"],
                "death_rate":row["evaluation"]["death_rate"]})
    ranked=sorted(candidates,key=lambda r:(-r["mean_achievements"],r["death_rate"],r["steps"],r["run"]))
    a.out.mkdir(parents=True)
    selected=ranked[0]
    shutil.copy2(selected["checkpoint"],a.out/"model.pt")
    manifest={"environment_version":SPEC.version,"criterion":"highest validation mean; ties: lower death rate, fewer steps, run name",
              "validation_seeds":validation,"test_seeds":reserved,
              "sampler_seed":54321,"selection":selected,"candidates":ranked,
              "evaluation_source_sha256":sha(Path(__import__('terraria_lite.ppo_eval',fromlist=['evaluate']).__file__)),
              "note":"Selection frozen before test. The reserved split is now consumed; do not tune against its results."}
    (a.out/"selection.json").write_text(json.dumps(manifest,indent=2)+"\n")
    torch.set_num_threads(6)
    result=evaluate(load_agent(a.out/"model.pt"),list(range(reserved[0],reserved[1]+1)),sample_seed=54321)
    (a.out/"test.json").write_text(json.dumps(result,indent=2)+"\n")
    print_report(result,f"{selected['run']} step {selected['steps']:,}",False)


if __name__=="__main__": main()
