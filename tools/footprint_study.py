"""Fresh paired v4/v5 learning study. Immutable snapshots, no automatic retries."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import statistics
import subprocess
import sys
import time

SEEDS=[501,502,503,504,505]
STEPS=16_777_216
INTERVAL=4_194_304
METHODS={'mlp':{'architecture':'mlp','gae_lambda':.95,'entropy':.01},
         'targets':{'architecture':'targets','gae_lambda':.99,'entropy':.03},
         'memory':{'architecture':'lstm_targets','gae_lambda':.99,'entropy':.03}}

def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def hashes(root):
    return {str(p.relative_to(root)):sha(p) for folder in ('include','src','python/terraria_lite','tools')
            for p in (root/folder).iterdir() if p.suffix in ('.c','.h','.py','.dylib','.so')}
def environment(root):
    e=os.environ.copy();e['PYTHONPATH']=str(root/'python');e['PYTHONUNBUFFERED']='1'
    e.pop('TERRARIA_LITE_LIB',None);return e
def args_for(cfg):return [v for k,value in cfg.items() for v in ('--'+k.replace('_','-'),str(value))]

def prepare(study,repo):
    if (study/'study-protocol.json').exists():raise ValueError('Protocol already exists')
    origins={'v4':repo/'experiments/credit-v4-20261011.naYwbC/production',
             'v5':repo/'experiments/object-scale-v5-20261011.44UmHy/v5'}
    for name,source in origins.items():
        dest=study/'variants'/name;shutil.copytree(source,dest)
        for tool in ('crafting_probe.c','crafting_diagnostics.py','evaluate_reserved.py'):
            shutil.copy2(repo/'tools'/tool,dest/'tools'/tool)
    a=study/'variants/v4/python/terraria_lite';b=study/'variants/v5/python/terraria_lite'
    assert {x.name for x in a.glob('*.py')}=={x.name for x in b.glob('*.py')}
    for x in a.glob('*.py'):
        # Only the version-identifying binding docstring differs.
        if x.name=='__init__.py':
            aa=ast.parse(x.read_text());bb=ast.parse((b/x.name).read_text());aa.body=aa.body[1:];bb.body=bb.body[1:]
            assert ast.dump(aa)==ast.dump(bb)
        else:assert sha(x)==sha(b/x.name),x.name
    differences=[str(x.relative_to(study/'variants/v4')) for folder in ('include','src')
        for x in (study/'variants/v4'/folder).iterdir() if x.suffix in ('.c','.h')
        and sha(x)!=sha(study/'variants/v5'/x.relative_to(study/'variants/v4'))]
    assert set(differences)=={'include/env.h','include/tiles.h','src/sim.c','src/worldgen.c','src/light.c','src/px_render.c','src/px_main.c'}
    shutil.copy2(Path(__file__),study/'runner.py')
    protocol={'date':'2026-10-11','study':str(study),'origins':{k:str(v) for k,v in origins.items()},
        'versions':[4,5],'training_seeds':SEEDS,'methods':METHODS,'steps_per_run':STEPS,
        'checkpoint_interval':INTERVAL,'main_runs':30,'main_transitions':30*STEPS,
        'calibration_runs':6,'calibration_steps_per_run':32768,'calibration_transitions':6*32768,
        'validation_seeds':[10_000_001,10_000_128],'reserved_test_seeds':[11_000_001,11_000_128],
        'sampler_seed':54321,'common':{'envs':64,'rollout':128,'epochs':4,'minibatches':4,
          'threads':6,'workers':3,'device':'cpu','gamma':.999,'lr':.0003,'anneal_lr':True},
        'reward':'new achievement +1; death -1; inherent 3000-action deadline has zero future value',
        'demonstrations':False,'strategic_masks':False,'prerequisite_shaping':False,'novelty':False,
        'comparison':'Fresh 16M-ending schedules for all 30 runs; final validation means primary; 4M checkpoints secondary. Paired RNG seeds, not identical rollout data.',
        'v5_changes':'Object footprints, corresponding placement/interaction/light/worldgen/UI corrections only. No recipe/resource/tool/observation changes.',
        'source_differences':differences,'learner_sources_semantically_identical':True,
        'selection':'After all runs: method with highest mean final validation score across both versions and all five seeds; tie lower mean death then name. Paired seed with highest average final v4/v5 score within that method; tie lower mean death then seed. Freeze both final policies before testing.',
        'test_rule':'Same new 128 world IDs once PER VERSION for the two frozen paired policies. Separate exclusive claim files; ambiguous/crashed tests never retried. No tuning against tests.',
        'simulator_gate':{'max_paired_median_throughput_loss':.10},
        'learning_gate':{'max_mean_score_loss':1.0,'max_mean_death_increase':.05,
          'rule':'Report five-seed paired 95% Student-t intervals. Non-inferiority supported only if lower score bound >= -1 and upper death-difference bound <= .05 in every package. Otherwise inconclusive or negative, not automatic promotion. Report furnace/anvil rates separately; do not hide regressions behind aggregate score.'},
        'initialization':'No policy warm starts; no transfer of v4 weights to v5.',
        'promotion':'None automatic. Main checkout stays v4; versioned preview/experiment artifacts preserved.',
        'implementation_sha256':{name:hashes(study/'variants'/name) for name in origins},
        'supervisor_sha256':sha(study/'runner.py')}
    write(study/'study-protocol.json',protocol)
    print(json.dumps({'study':str(study),'main_transitions':protocol['main_transitions'],'source_differences':differences}))

def verify_run(study,name,steps,episodes):
    d=study/name;p=read(d/'protocol.json');s=read(d/'summary.json');curve=read(d/'curve.json')
    assert s['steps']==p['actual_steps']==steps and curve[-1]['steps']==steps
    assert p['environment_version']==int(name.split('/')[1][1:])
    assert p['validation_seeds']==[10_000_001,10_000_000+episodes]
    assert p['reserved_test_seeds']==[11_000_001,11_000_128]
    assert p['config']['bootstrap_time_limit'] is False and p['config']['progress_coef']==0
    assert not p['demonstrations'] and not p['prerequisite_shaping']
    assert all(sha(Path(p['package'])/k)==v for k,v in p['implementation_sha256'].items())

def run(study,repo):
    p=read(study/'study-protocol.json');python=os.path.abspath(sys.executable)
    assert sha(study/'runner.py')==p['supervisor_sha256']
    assert all(hashes(study/'variants'/v)==h for v,h in p['implementation_sha256'].items())
    with (study/'run-started.json').open('x') as h:json.dump({'pid':os.getpid(),'utc':time.time()},h)
    logs=study/'logs';logs.mkdir();active={};stage='preflight'
    def status(**extras):write(study/'status.json',{'stage':stage,'runner_pid':os.getpid(),'updated_utc':time.time(),
        'active':{n:v[0].pid for n,v in active.items()},**extras})
    def interrupted(sig,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    def command(version,argv,label):
        frozen=study/'variants'/version
        with (logs/label).open('w') as h:subprocess.run(argv,cwd=frozen,env=environment(frozen),stdout=h,stderr=subprocess.STDOUT,check=True)
    def pool(stage_name,jobs,episodes):
        nonlocal stage
        stage=stage_name;pending=list(jobs);completed=[]
        while pending or active:
            while pending and len(active)<3:
                version,method,seed,steps=pending.pop(0);name=f'{stage}/{version}/{method}-{seed}'
                dest=study/name
                if dest.exists():raise ValueError(f'Existing trial preserved: {dest}')
                frozen=study/'variants'/version;handle=(logs/f'{stage}-{version}-{method}-{seed}.log').open('w')
                argv=[python,str(frozen/'tools/iterate_ppo.py'),'--out',str(dest),'--steps',str(steps),
                    '--seed',str(seed),'--threads','6','--envs','64','--interval',str(min(INTERVAL,steps)),
                    '--validation-episodes',str(episodes),'--validation-seed-start','10000001','--test-seed-start','11000001',*args_for(p['methods'][method])]
                proc=subprocess.Popen(argv,cwd=frozen,env=environment(frozen),stdout=handle,stderr=subprocess.STDOUT)
                active[name]=(proc,handle,steps);print(f'Started {name}, PID {proc.pid}',flush=True)
            for name,(proc,handle,steps) in list(active.items()):
                code=proc.poll()
                if code is not None:
                    handle.close();del active[name]
                    if code:raise RuntimeError(f'{name} exited {code}; preserve its log and trial')
                    verify_run(study,name,steps,episodes);completed.append(name)
                    print(f'Completed {name}',flush=True)
            status(pending=[f'{v}/{m}-{s}' for v,m,s,_ in pending],completed=completed)
            if active or pending:time.sleep(2)
    keepawake=subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())])
    try:
        status()
        for version in ('v4','v5'):
            frozen=study/'variants'/version
            command(version,['make','check','check-pixel'],f'preflight-{version}-mechanics.log')
            command(version,[python,'-m','terraria_lite.ppo_selftest'],f'preflight-{version}-ppo.log')
            command(version,['cc','-std=c11','-O2','-dynamiclib','-Iinclude','-Isrc','tools/crafting_probe.c','-o',str(study/f'probe-{version}.dylib')],f'probe-{version}-build.log')
        pool('calibration',[(v,m,77,32768) for m in p['methods'] for v in ('v4','v5')],4)
        for version in ('v4','v5'):
            frozen=study/'variants'/version
            command(version,[python,str(frozen/'tools/crafting_diagnostics.py'),str(study/f'calibration/{version}/memory-77/step-32768.pt'),
                '--probe',str(study/f'probe-{version}.dylib'),'--episodes','4','--seed-start','10000001','--out',str(study/f'probe-{version}-calibration.json')],f'probe-{version}-calibration.log')
        write(study/'preflight.json',{'passed':True,'both_versions_mechanics_pixels_ppo_parity':True,
            'six_end_to_end_calibrations':True,'observer_readonly_selftests_and_exact_furnace_mask_agreement':True})
        jobs=[(v,m,seed,STEPS) for i,seed in enumerate(p['training_seeds']) for m in p['methods']
              for v in (('v4','v5') if i%2==0 else ('v5','v4'))]
        pool('main',jobs,128)
        stage='finalizing';status()
        ranking=[]
        for method in p['methods']:
            es=[read(study/f'main/{v}/{method}-{seed}/curve.json')[-1]['evaluation'] for v in ('v4','v5') for seed in p['training_seeds']]
            ranking.append({'method':method,'mean':statistics.mean(e['mean_achievements'] for e in es),'death_rate':statistics.mean(e['death_rate'] for e in es)})
        ranking.sort(key=lambda x:(-x['mean'],x['death_rate'],x['method']));method=ranking[0]['method']
        pairs=[]
        for seed in p['training_seeds']:
            es=[read(study/f'main/{v}/{method}-{seed}/curve.json')[-1]['evaluation'] for v in ('v4','v5')]
            pairs.append({'seed':seed,'mean':statistics.mean(e['mean_achievements'] for e in es),'death_rate':statistics.mean(e['death_rate'] for e in es)})
        pairs.sort(key=lambda x:(-x['mean'],x['death_rate'],x['seed']));seed=pairs[0]['seed']
        selection={'criterion':p['selection'],'method_ranking':ranking,'paired_seed_ranking':pairs,'method':method,'seed':seed,'checkpoints':{}}
        for v in ('v4','v5'):
            dest=study/'selected'/v;dest.mkdir(parents=True)
            source=study/f'main/{v}/{method}-{seed}/step-{STEPS}.pt';shutil.copy2(source,dest/'model.pt')
            selection['checkpoints'][v]={'source':str(source),'sha256':sha(dest/'model.pt')}
        write(study/'selected/selection.json',selection)
        # Both policies are frozen before either reserved version is consumed.
        for v in ('v4','v5'):
            frozen=study/'variants'/v
            command(v,[python,str(frozen/'tools/evaluate_reserved.py'),str(study/f'selected/{v}/model.pt'),
                '--out',str(study/f'selected/{v}/test.json'),'--version',v[1:],'--seed-start','11000001'],f'reserved-{v}.log')
        stage='diagnostics';status()
        for v,m,seed,_ in jobs:
            frozen=study/'variants'/v;dest=study/f'main/{v}/{m}-{seed}'
            command(v,[python,str(frozen/'tools/crafting_diagnostics.py'),str(dest/f'step-{STEPS}.pt'),
                '--probe',str(study/f'probe-{v}.dylib'),'--episodes','128','--seed-start','10000001','--out',str(dest/'crafting.json')],f'crafting-{v}-{m}-{seed}.log')
        for v in ('v4','v5'):
            frozen=study/'variants'/v;tape=study/f'selected/{v}/seed9.tape'
            command(v,[python,'-m','terraria_lite.watch','--policy',str(study/f'selected/{v}/model.pt'),'--seed','9','--out',str(tape)],f'replay-{v}.log')
            command(v,[python,str(frozen/'tools/verify_replay.py'),str(tape),'--viewer',str(frozen/'terraria-px'),
                '--checkpoint',str(study/f'selected/{v}/model.pt'),'--out',str(study/f'selected/{v}/replay-verification.json')],f'replay-verify-{v}.log')
        report(study,repo);stage='complete';status(report=str(repo/'FOOTPRINT_LEARNING_2026_10.md'))
        print('All 30 main trials, paired one-shot tests, diagnostics and exact replays complete',flush=True)
    except BaseException as exc:
        status(error=f'{type(exc).__name__}: {exc}');raise
    finally:
        for proc,handle,_ in active.values():
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
            handle.close()
        keepawake.terminate();keepawake.wait()

def interval(values):
    mean=statistics.mean(values);sd=statistics.stdev(values)
    delta=2.7764451051977987*sd/len(values)**.5
    return {'per_seed':values,'mean':mean,'sample_sd':sd,'paired_t_95_interval':[mean-delta,mean+delta]}

def report(study,repo):
    p=read(study/'study-protocol.json');assert all(hashes(study/'variants'/v)==h for v,h in p['implementation_sha256'].items())
    groups={};comparisons={};runs=[]
    for m in p['methods']:
        vals={}
        for v in ('v4','v5'):
            rows=[]
            for seed in p['training_seeds']:
                name=f'main/{v}/{m}-{seed}';verify_run(study,name,STEPS,128);d=study/name
                curve=read(d/'curve.json');e=curve[-1]['evaluation'];s=read(d/'summary.json')
                rows.append(e);runs.append({'name':name,'protocol':read(d/'protocol.json'),'summary':s,
                    'curve':[{**x,'evaluation':{k:z for k,z in x['evaluation'].items() if k!='records'}} for x in curve],
                    'crafting':{k:z for k,z in read(d/'crafting.json').items() if k!='records'}})
            vals[v]=rows;scores=[e['mean_achievements'] for e in rows]
            groups[f'{v}/{m}']={'scores':scores,'mean':statistics.mean(scores),'sample_sd':statistics.stdev(scores),
                'death_rate':statistics.mean(e['death_rate'] for e in rows),
                'furnace_rate':sum(e['hits'].get('craft furnace',0) for e in rows)/640,
                'anvil_rate':sum(e['hits'].get('craft anvil',0) for e in rows)/640}
        score=interval([b['mean_achievements']-a['mean_achievements'] for a,b in zip(vals['v4'],vals['v5'])])
        death=interval([b['death_rate']-a['death_rate'] for a,b in zip(vals['v4'],vals['v5'])])
        supported=score['paired_t_95_interval'][0]>=-1 and death['paired_t_95_interval'][1]<=.05
        comparisons[m]={'v5_minus_v4_score':score,'v5_minus_v4_death':death,'learning_noninferiority_supported':supported,
            'note':'Five exploratory paired seeds; a failed support gate can mean inconclusive, not necessarily harmful.'}
    total=sum(x['summary']['steps'] for x in runs);assert total==p['main_transitions']
    tests={};replays={};selection=read(study/'selected/selection.json')
    for v in ('v4','v5'):
        d=study/'selected'/v;tests[v]=read(d/'test.json');claim=read(d/'test.claim.json')
        assert claim['seeds']==p['reserved_test_seeds'] and claim['checkpoint_sha256']==selection['checkpoints'][v]['sha256']==sha(d/'model.pt')
        assert sorted(x['seed'] for x in tests[v]['records'])==list(range(11000001,11000129))
        replays[v]=read(d/'replay-verification.json');assert replays[v]['python_sdl_final_state_exact'] and replays[v]['policy_provenance']['sampled_tape_exactly_reproduced']
        assert replays[v]['tape_sha256']==sha(d/'seed9.tape') and replays[v]['policy_provenance']['checkpoint_sha256']==sha(d/'model.pt')
    result={'complete':True,'study':str(study),'protocol':p,'main_transitions':total,'groups':groups,'paired_comparisons':comparisons,
        'runs':runs,'selection':selection,'tests':tests,'replays':replays,'simulator_benchmarks':read(study/'isolated-benchmarks.json')}
    write(repo/'FOOTPRINT_LEARNING_2026_10.json',result)
    lines=['# Fresh paired v4/v5 footprint learning study','','Status: **complete**.',f'\n{total:,} main transitions across 30 fresh runs; five paired seeds per policy package. No defaults or game versions automatically promoted.','',
        '| Package | v4 final /32 | v5 final /32 | Paired v5−v4 | 95% interval | Furnace v4/v5 |',
        '| --- | ---: | ---: | ---: | --- | --- |']
    for m,c in comparisons.items():
        a=groups[f'v4/{m}'];b=groups[f'v5/{m}'];d=c['v5_minus_v4_score']
        lines.append(f"| {m} | {a['mean']:.3f} | {b['mean']:.3f} | {d['mean']:+.3f} | {d['paired_t_95_interval']} | {a['furnace_rate']:.1%}/{b['furnace_rate']:.1%} |")
    lines+=['','## Frozen paired selection and one-shot test','',f"Selected package {selection['method']}, paired seed {selection['seed']}; both final policies were frozen before either test."]
    for v,t in tests.items():lines.append(f"\n{v}: {t['mean_achievements']:.3f}/32, death {t['death_rate']:.1%}, furnace {t['hits'].get('craft furnace',0)}/128.")
    lines+=['','Test worlds 11,000,001–11,000,128 are now consumed once per version. Do not rerun/tune against them.',
        '\nThe comparison is the footprint/worldgen/interaction package, not sprite scaling alone. Different game trajectories, five seeds, bundled policy settings and shared-desktop timings limit causal and efficiency claims.',
        '\nNo training controller, demonstrations, strategic masks, resource-floor or recipe changes. Diagnostic hidden-state reads never enter the policy. Full curves, gate telemetry, protocols, hashes and exact replays are preserved.',
        f'\nArtifacts: `{study}`. Numeric report: `FOOTPRINT_LEARNING_2026_10.json`.']
    (repo/'FOOTPRINT_LEARNING_2026_10.md').write_text('\n'.join(lines)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--mode',choices=['prepare','run','report'],required=True)
    a=p.parse_args();s=a.study.resolve();r=a.repo.resolve()
    {'prepare':prepare,'run':run,'report':report}[a.mode](s,r)

if __name__=='__main__':main()
