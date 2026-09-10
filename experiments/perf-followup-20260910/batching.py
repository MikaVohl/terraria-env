"""Matched PPO batch/minibatch sizes while varying inference batch and device.
Run only after study.py finishes. Changing rollout length is a learning change;
this measures throughput, not time to proficiency. No concurrent timed children.
"""
import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path
import study


def child(a):
    import terraria_lite.ppo_agent as ppo
    original = ppo.Config
    def config(**kwargs):
        kwargs.update(num_envs=a.envs, rollout=32768//a.envs, device=a.device)
        return original(**kwargs)
    ppo.Config = config
    study.child(a)


def run():
    rng=random.Random(20260911)
    jobs=[]
    # 4-worker control confirms the worker finding over a longer window.
    for repeat in range(3):
        block=[('mature',256,'mps',4,repeat)]
        block += [('mature',n,d,8,repeat) for n in [128,256,512] for d in ['cpu','mps']]
        rng.shuffle(block);jobs.extend(block)
    for repeat in range(2):
        block=[('fresh',n,'mps',8,repeat) for n in [128,256,512]]
        rng.shuffle(block);jobs.extend(block)
    env={**os.environ,'PYTHONPATH':str(study.SOURCE/'python')+os.pathsep+str(study.SOURCE/'tools'),
         'TERRARIA_LITE_LIB':str(study.OUT/'cached.dylib'),'PYTHONUNBUFFERED':'1'}
    with (study.OUT/'batching.jsonl').open('x') as output:
        for index,(workload,n,device,workers,repeat) in enumerate(jobs):
            cmd=[sys.executable,str(Path(__file__).resolve()),'--child','--workload',workload,
                 '--envs',str(n),'--device',device,'--workers',str(workers)]
            r=subprocess.run(cmd,env=env,cwd=study.SOURCE,capture_output=True,text=True,timeout=240)
            (study.OUT/f'batching-{index:02d}.log').write_text(r.stdout+r.stderr)
            if r.returncode:raise RuntimeError(r.stderr)
            row=json.loads(r.stdout.splitlines()[-1]);row.update(index=index,repeat=repeat)
            output.write(json.dumps(row)+'\n');output.flush()
            print(json.dumps({'index':index,'repeat':repeat,'workload':workload,'envs':n,
                              'device':device,'workers':workers,'sps':row['measured_sps'],
                              'hash':row['final_model_sha256']}),flush=True)
    print('BATCHING COMPLETE',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--child',action='store_true')
    p.add_argument('--envs',type=int,default=256);p.add_argument('--workers',type=int,default=8)
    p.add_argument('--device',choices=['cpu','mps'],default='mps')
    p.add_argument('--workload',choices=['fresh','mature'],default='mature')
    p.add_argument('--steps',type=int,default=1048576)
    a=p.parse_args();a.profile=False;a.library='cached'
    child(a) if a.child else run()
