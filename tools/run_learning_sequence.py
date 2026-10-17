"""Run the predeclared causal screen, method screen and matched scaling study.

Only frozen sources/packages are used. Logs and a resumable stage ledger stay
inside the local study; all output directories must be fresh. Completed runs
are skipped on resume, incomplete directories require explicit attention.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study",type=Path,required=True)
    p.add_argument("--workers",type=int,default=3)
    p.add_argument("--stage",choices=["all","causal","screen","scale"],default="all")
    a=p.parse_args();study=a.study.resolve();frozen=study/"production"
    protocol=json.loads((study/"study-protocol.json").read_text())
    # Preserve the venv symlink: resolving it selects the bare base interpreter
    # and loses the environment's installed NumPy/Torch dependencies.
    python=os.path.abspath(sys.executable);logs=study/"logs";logs.mkdir(exist_ok=True)
    for name,digest in protocol["implementation_sha256"].items():
        assert hashlib.sha256((frozen/name).read_bytes()).hexdigest()==digest,name
    active={}
    def interrupted(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    def environment(root):
        env=os.environ.copy();env["PYTHONPATH"]=str(root/"python");env.pop("TERRARIA_LITE_LIB",None)
        env["PYTHONUNBUFFERED"]="1";return env
    def jobs_for(stage):
        jobs=[]
        if stage=="causal":
            methods={"control":frozen,**{n:study/"variants"/n for n in protocol["causal_screen"]["variants"]}}
            for name,root in methods.items():
                if name!="control":
                    subprocess.run(["make","-B","-j4","lib"],cwd=root,check=True,stdout=subprocess.DEVNULL)
                    subprocess.run([python,"-m","terraria_lite.ppo_selftest"],cwd=root,env=environment(root),check=True,stdout=subprocess.DEVNULL)
                for seed in protocol["training_seeds"]:
                    jobs.append((f"{name}-{seed}",root,["--seed",str(seed),"--steps","1048576","--constant-lr"]))
        elif stage=="screen":
            for name,cfg in protocol["method_screen"]["configurations"].items():
                for seed in protocol["training_seeds"]:
                    jobs.append((f"{name}-{seed}",frozen,["--seed",str(seed),"--steps","4194304", "--architecture",cfg["architecture"],
                        "--gae-lambda",str(cfg["gae_lambda"]),"--entropy",str(cfg["entropy"])]))
        else:
            scores=[]
            for name,cfg in protocol["method_screen"]["configurations"].items():
                if name=="baseline":continue
                evaluations=[]
                for seed in protocol["training_seeds"]:
                    run=study/"screen"/f"{name}-{seed}"
                    assert (run/"summary.json").exists()
                    evaluations.append(json.loads((run/"curve.json").read_text())[-1]["evaluation"])
                scores.append({"name":name,"mean":sum(e["mean_achievements"] for e in evaluations)/len(evaluations),
                               "death_rate":sum(e["death_rate"] for e in evaluations)/len(evaluations)})
            ranked=sorted(scores,key=lambda x:(-x["mean"],x["death_rate"],x["name"]))
            winner=ranked[0]["name"]
            manifest={"criterion":"highest two-seed final validation mean; ties lower deaths, then name", "winner":winner,"candidates":ranked,
                      "note":"No reserved test data used. Compare this alternative against baseline at matched budgets."}
            (study/"scaling-selection.json").write_text(json.dumps(manifest,indent=2)+"\n")
            print("Scaling selection:",manifest,flush=True)
            for budget in protocol["scaling"]["budgets"]:
                for name in ("baseline",winner):
                    cfg=protocol["method_screen"]["configurations"][name]
                    for seed in protocol["training_seeds"]:
                        jobs.append((f"{name}-{budget}-{seed}",frozen,["--seed",str(seed),"--steps",str(budget),
                            "--interval","4194304","--architecture",cfg["architecture"],"--gae-lambda",str(cfg["gae_lambda"]),"--entropy",str(cfg["entropy"])]))
        return jobs
    def run_stage(stage):
        directory=study/stage;directory.mkdir(exist_ok=True);jobs=jobs_for(stage);pending=[]
        for name,root,args in jobs:
            dest=directory/name
            if (dest/"summary.json").exists():continue
            if dest.exists():raise ValueError(f"Incomplete run {dest}; preserve it and choose a fresh retry name")
            pending.append((name,root,args))
        offsets={};completed=[]
        while pending or active:
            while pending and len(active)<a.workers:
                name,root,args=pending.pop(0);dest=directory/name;log=logs/f"{stage}-{name}.log"
                handle=log.open("w")
                command=[python,str(frozen/"tools/iterate_ppo.py"),"--out",str(dest),"--threads","6",
                         "--validation-seed-start","6000001","--test-seed-start","7000001",*args]
                process=subprocess.Popen(command,cwd=root,env=environment(root),stdout=handle,stderr=subprocess.STDOUT)
                active[name]=(process,handle,log,command);offsets[name]=0
                print(f"Started {stage}/{name}, PID {process.pid}",flush=True)
            for name,(process,handle,log,command) in list(active.items()):
                with log.open() as reader:
                    reader.seek(offsets[name]);output=reader.read();offsets[name]=reader.tell()
                if output:print(output,end="",flush=True)
                code=process.poll()
                if code is not None:
                    handle.close();del active[name]
                    if code!=0:raise RuntimeError(f"{stage}/{name} exited {code}; see {log}")
                    completed.append(name)
            status={"stage":stage,"pending":[x[0] for x in pending],"active":{n:p[0].pid for n,p in active.items()},"completed_this_run":completed,"updated_utc":time.time()}
            (study/"status.json").write_text(json.dumps(status,indent=2)+"\n")
            if pending or active:time.sleep(2)
        print(f"Stage {stage} complete",flush=True)
    try:
        for stage in ("causal","screen","scale") if a.stage=="all" else (a.stage,):run_stage(stage)
    finally:
        for process,handle,_,_ in active.values():
            process.terminate();handle.close()


if __name__=="__main__":main()
