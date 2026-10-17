"""Exclusive fresh pilot supervisor. No test consumption, retries or promotion."""
import argparse,hashlib,json,os
from pathlib import Path
import shutil,subprocess,sys,time

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def hashes(root):
    return {str(p.relative_to(root)):sha(p) for folder in ('include','src','python/terraria_lite','tools') for p in (root/folder).iterdir() if p.suffix in ('.py','.c','.h','.dylib','.so')}

def prepare(study):
    if (study/'pilot-protocol.json').exists():raise ValueError('Already sealed')
    source=Path(__file__).resolve();shutil.copy2(source,study/'pilot-runner.py')
    jobs=[('v6','ppo',601),('v7','ppo',601),('v7','replay',601),('v7','ppo',602),('v6','ppo',602),('v7','replay',602)]
    p={'date':'2026-10-12','study':str(study),'runs':jobs,'steps_per_run':4194304,'main_transitions':25165824,'workers':3,'threads':read(study/'learner-cpu.json')['selected_threads'],'validation_seeds':[13000001,13000032],'reserved_tests':[15000001,15000128],'test_rule':'Not consumed in this exploratory pilot; no selection or promotion','sources':{v:hashes(study/v) for v in ('v6','v7')},'runner_sha256':sha(study/'pilot-runner.py'),'methods':{'ppo':'MLP512, gamma .999, lambda .95, entropy .01, 4M-ending LR3e-4; categorical evaluation','replay':'MLP512, uniform lossless replay131072, n-step20 Double DQN, gamma .999, Adam1e-4, batch512/every256 transitions, epsilon1 to .05 over2M; greedy evaluation'},'scope':'v6 versus v7 isolates direct placeable selection; both share task-correctness changes atop v5. Replay versus PPO is a package comparison, not a replay-only ablation. Two seeds/32 worlds exploratory, no noninferiority claims. Calibration excluded; no expert cloning, strategic masks, shaping, warmstarts, API spending or cluster.'}
    write(study/'pilot-protocol.json',p);print(json.dumps({k:p[k] for k in ('main_transitions','threads','runs')},indent=2))

def run(study):
    p=read(study/'pilot-protocol.json');assert sha(Path(__file__))==p['runner_sha256']
    assert all(hashes(study/v)==h for v,h in p['sources'].items())
    with (study/'pilot-started.json').open('x') as f:json.dump({'pid':os.getpid(),'utc':time.time()},f)
    (study/'logs').mkdir(exist_ok=True);pending=list(p['runs']);active={};completed=[]
    inhibitor=subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())])
    def status(stage,**extra):write(study/'pilot-status.json',{'stage':stage,'runner_pid':os.getpid(),'updated_utc':time.time(),'active':{n:z[0].pid for n,z in active.items()},'pending':pending,'completed':completed,**extra})
    def env(v):return {**os.environ,'PYTHONPATH':str(study/v/'python'),'TERRARIA_LITE_LIB':str(study/v/'python/terraria_lite/libterraria.dylib')}
    try:
        while pending or active:
            while pending and len(active)<p['workers']:
                v,method,seed=pending.pop(0);name=f'{v}/{method}-{seed}';dest=study/'runs'/name
                assert not dest.exists(),'Fresh trial directory required'
                driver='iterate_ppo.py' if method=='ppo' else 'train_replay.py'
                cmd=[sys.executable,str(study/v/'tools'/driver),'--out',str(dest),'--steps',str(p['steps_per_run']),'--seed',str(seed),'--threads',str(p['threads']),'--validation-seed-start','13000001','--validation-episodes','32']
                if method=='ppo':cmd+=['--interval','1048576','--test-seed-start','15000001']
                log=(study/'logs'/f'{v}-{method}-{seed}.log').open('x')
                proc=subprocess.Popen(cmd,cwd=study/v,env=env(v),stdout=log,stderr=subprocess.STDOUT)
                active[name]=(proc,log);print('Started',name,proc.pid,flush=True)
            for name,(proc,log) in list(active.items()):
                rc=proc.poll()
                if rc is None:continue
                log.close();del active[name]
                if rc:raise RuntimeError(f'{name} failed rc={rc}; preserve artifacts')
                assert read(study/'runs'/name/'summary.json')['steps']==p['steps_per_run']
                completed.append(name);print('Completed',name,flush=True)
            status('training');time.sleep(2)
        status('diagnostics')
        for v,method,seed in p['runs']:
            name=f'{v}/{method}-{seed}';dest=study/'runs'/name
            cmd=[sys.executable,str(study/v/'tools/crafting_diagnostics.py'),str(dest/'step-4194304.pt'),'--probe',str(study/f'probe-{v}.dylib'),'--out',str(dest/'crafting.json'),'--episodes','32','--seed-start','13000001']
            if method=='replay':cmd+=['--greedy']
            with (study/'logs'/f'crafting-{v}-{method}-{seed}.log').open('x') as log:subprocess.run(cmd,cwd=study/v,env=env(v),stdout=log,stderr=subprocess.STDOUT,check=True)
        assert all(hashes(study/v)==h for v,h in p['sources'].items())
        rows=[]
        for v,method,seed in p['runs']:
            d=study/f'runs/{v}/{method}-{seed}';e=read(d/'curve.json')[-1]['evaluation'];c=read(d/'crafting.json')
            assert e['mean_achievements']==c['mean_achievements']
            rows.append({'version':v,'method':method,'seed':seed,'summary':read(d/'summary.json'),'evaluation':{k:z for k,z in e.items() if k!='records'},'crafting':{k:z for k,z in c.items() if k!='records'}})
        write(study/'pilot-results.json',{'complete':True,'protocol':p,'runs':rows,'main_transitions':sum(x['summary']['steps'] for x in rows),'reserved_tests_consumed':False})
        status('complete',report=str(study/'pilot-results.json'));print('Pilot complete; reserved tests unused',flush=True)
    except BaseException as error:
        status('failed',error=repr(error));raise
    finally:
        for proc,log in active.values():
            if proc.poll() is None:proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
            log.close()
        if inhibitor.poll() is None:inhibitor.terminate();inhibitor.wait()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--mode',choices=['prepare','run'],required=True);a=p.parse_args()
    {'prepare':prepare,'run':run}[a.mode](a.study.resolve())

if __name__=='__main__':main()
