"""External wall-budget enforcement and partial reporting; frozen trials untouched.

Stops only the validated study supervisor/its recorded descendants. Never resumes
training, changes a source/config, selects a winner, or consumes reserved tests.
"""
import argparse
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
from datetime import datetime,timezone
from zoneinfo import ZoneInfo

def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def processes():
    out=subprocess.check_output(['ps','-axo','pid=,ppid=,command='],text=True)
    result={}
    for line in out.splitlines():
        fields=line.strip().split(None,2)
        if len(fields)==3:result[int(fields[0])]={'ppid':int(fields[1]),'command':fields[2]}
    return result
def descendants(table,pid):
    found=set();parents={pid}
    while parents:
        children={p for p,row in table.items() if row['ppid'] in parents}-found
        found.update(children);parents=children
    return found
def valid_supervisor(study,pid,table):
    row=table.get(pid)
    return bool(row and str(study/'runner.py') in row['command'] and '--mode run' in row['command']
                and read(study/'run-started.json')['pid']==pid)
def paired_stats(values):
    mean=statistics.mean(values);result={'n':len(values),'per_seed':values,'mean':mean}
    if len(values)>1:
        sd=statistics.stdev(values);crit={2:12.7062047364,3:4.30265272975,4:3.18244630528,5:2.77644510520}[len(values)]
        delta=crit*sd/len(values)**.5;result.update(sample_sd=sd,exploratory_t_95_interval=[mean-delta,mean+delta])
    else:result['exploratory_t_95_interval']=None
    return result

def report(study,repo):
    p=read(study/'study-protocol.json');runs={};warnings=[];complete_steps=0;verified_steps=0
    import torch
    for v in ('v4','v5'):
      for directory in sorted((study/'main'/v).iterdir()):
        if not directory.is_dir():continue
        name=f'{v}/{directory.name}';rows=[]
        try:curve=read(directory/'curve.json') if (directory/'curve.json').exists() else []
        except json.JSONDecodeError:
            warnings.append(f'{name}: interrupted curve JSON; preserve original and use pre-stop snapshot if available')
            backup=study/'budget-pre-stop'/v/directory.name/'curve.json'
            curve=read(backup) if backup.exists() else []
        for row in curve:
            weight=directory/f"step-{row['steps']}.pt"
            try:
                raw=torch.load(weight,map_location='cpu',weights_only=True)
                assert raw['environment_version']==int(v[1:]) and raw['obs_size']==2961 and raw['n_actions']==73
                assert row['evaluation']['episodes']==128
                assert sorted(z['seed'] for z in row['evaluation']['records'])==list(range(10000001,10000129))
                rows.append({**row,'checkpoint':str(weight),'checkpoint_sha256':sha(weight),
                    'evaluation':{k:z for k,z in row['evaluation'].items() if k!='records'}})
            except Exception as exc:warnings.append(f'{name} step {row["steps"]}: unusable checkpoint/record preserved ({type(exc).__name__})')
        summary=read(directory/'summary.json') if (directory/'summary.json').exists() else None
        complete=bool(summary and summary['steps']==p['steps_per_run'] and rows and rows[-1]['steps']==p['steps_per_run'])
        if complete:complete_steps+=summary['steps']
        if rows:verified_steps+=rows[-1]['steps']
        runs[name]={'complete_16m':complete,'summary':summary,'curve':rows,'protocol':read(directory/'protocol.json')}
    paired={}
    for method in p['methods']:
        finals=[];checkpoints=[]
        for seed in p['training_seeds']:
            a=runs.get(f'v4/{method}-{seed}');b=runs.get(f'v5/{method}-{seed}')
            if not a or not b:continue
            aa={x['steps']:x for x in a['curve']};bb={x['steps']:x for x in b['curve']}
            for steps in sorted(aa.keys()&bb.keys()):
                x=aa[steps]['evaluation'];y=bb[steps]['evaluation']
                row={'seed':seed,'steps':steps,'v4':x,'v5':y,'score_difference':y['mean_achievements']-x['mean_achievements'],
                     'death_difference':y['death_rate']-x['death_rate']}
                checkpoints.append(row)
                if steps==p['steps_per_run'] and a['complete_16m'] and b['complete_16m']:finals.append(row)
        paired[method]={'complete_final_pairs':finals,'equal_step_checkpoint_pairs':checkpoints,
            'final_score_difference':paired_stats([x['score_difference'] for x in finals]) if finals else None,
            'final_death_difference':paired_stats([x['death_difference'] for x in finals]) if finals else None}
    frozen_verified=all(all(sha(study/'variants'/v/k)==h for k,h in files.items()) for v,files in p['implementation_sha256'].items())
    assert frozen_verified
    claims=list((study/'selected').glob('*/test.claim.json')) if (study/'selected').exists() else []
    cutoff=read(study/'budget-enforcement.json') if (study/'budget-enforcement.json').exists() else None
    result={'complete':False,'status':'user-budget-limited partial study','study':str(study),
        'original_protocol':p,'budget_amendment':read(study/'budget-amendment.json'),'budget_enforcement':cutoff,
        'completed_main_runs':sum(x['complete_16m'] for x in runs.values()),'completed_main_transitions':complete_steps,
        'minimum_transitions_at_verified_checkpoints':verified_steps,'runs':runs,'paired_comparisons':paired,
        'frozen_sources_verified':frozen_verified,'reserved_test_claims':[str(x) for x in claims],
        'reserved_tests_not_consumed':not claims,'warnings':warnings,
        'note':'No official policy selection or additional test evaluation. Partial checkpoint curves are not independent seeds, not completed 16M runs, and retain the original 16M-ending LR schedule.'}
    write(repo/'docs/reports/FOOTPRINT_LEARNING_PARTIAL_2026_10.json',result)
    lines=['# Time-limited v4/v5 learning evidence','','Status: **partial — user-requested wall budget**, not a completed five-seed study.',
        f"\nCompleted 16M runs: {result['completed_main_runs']}/30 ({complete_steps:,} transitions). Across completed and unfinished runs, at least {verified_steps:,} transitions are represented by valid recorded checkpoints.",
        '\nThe original frozen sources, budgets, LR schedules and queue were not changed. An external user-authorized deadline ended computation. Reserved tests remain unused unless claims are explicitly listed below.','',
        '| Package | Completed paired seeds | v4 final mean /32 | v5 final mean /32 | Mean v5−v4 |',
        '| --- | ---: | ---: | ---: | ---: |']
    for method,data in paired.items():
        finals=data['complete_final_pairs']
        if finals:lines.append(f"| {method} | {len(finals)} | {statistics.mean(x['v4']['mean_achievements'] for x in finals):.3f} | {statistics.mean(x['v5']['mean_achievements'] for x in finals):.3f} | {data['final_score_difference']['mean']:+.3f} |")
        else:lines.append(f'| {method} | 0 | — | — | — |')
    lines+=['','## Limits','',
        'Only completed, matched 16M v4/v5 pairs enter the final table. Equal-step partial checkpoint comparisons are retained in JSON, separately. Do not compare mismatched budgets, count checkpoints as independent seeds, or call the five-seed non-inferiority gate passed from a truncated subset.',
        '\nCompletion/queue order, not an outcome-based stopping rule, determines which runs are available. Partial training is not resumable by the current frozen trainer; existing artifacts must never be silently restarted or pooled with a repaired implementation.',
        f"\nReserved test claims: {result['reserved_test_claims']}. No test was invoked by this budget controller. No game/model defaults promoted.",
        f'\nArtifacts: `{study}`. Full partial evidence: `FOOTPRINT_LEARNING_PARTIAL_2026_10.json`.']
    if warnings:lines+=['\nAudit warnings:',*[f'- {w}' for w in warnings]]
    (repo/'docs/reports/FOOTPRINT_LEARNING_PARTIAL_2026_10.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'completed_runs':result['completed_main_runs'],'verified_checkpoint_transitions':verified_steps,'paired_final_seeds':{m:len(x['complete_final_pairs']) for m,x in paired.items()},'warnings':warnings}),flush=True)

def enforce(study,repo,pid,stop_epoch,deadline_epoch):
    with (study/'budget-watchdog-started.json').open('x') as h:json.dump({'pid':os.getpid(),'supervisor_pid':pid,'stop_epoch':stop_epoch,'deadline_epoch':deadline_epoch},h)
    while time.time()<stop_epoch:
        table=processes()
        if not valid_supervisor(study,pid,table):
            print('Supervisor exited before cutoff; existing completion/failure follow-up handles it.',flush=True);return
        time.sleep(min(30,max(0,stop_epoch-time.time())))
    table=processes()
    if not valid_supervisor(study,pid,table):return
    children=descendants(table,pid)
    before=read(study/'status.json')
    # Preserve a valid copy of curves before interrupting any writers.
    for v in ('v4','v5'):
        for d in (study/'main'/v).iterdir():
            if (d/'curve.json').exists():
                try:
                    curve=read(d/'curve.json');dest=study/'budget-pre-stop'/v/d.name;dest.mkdir(parents=True)
                    write(dest/'curve.json',curve)
                except json.JSONDecodeError:pass
    event={'reason':'explicit user budget: about three more hours','stop_requested_utc':datetime.now(timezone.utc).isoformat(),
        'stop_epoch':stop_epoch,'report_deadline_epoch':deadline_epoch,'validated_supervisor_pid':pid,
        'validated_descendants':sorted(children),'status_before_stop':before,'state':'stopping'}
    write(study/'budget-enforcement.json',event)
    os.kill(pid,signal.SIGTERM)
    # Frozen supervisor catches this and terminates its active workers itself.
    end=time.time()+20
    while time.time()<end and valid_supervisor(study,pid,processes()):time.sleep(.5)
    after=processes()
    for target in sorted(children|{pid},reverse=True):
        if target in after and target in table and after[target]['command']==table[target]['command']:
            try:os.kill(target,signal.SIGTERM)
            except ProcessLookupError:pass
    time.sleep(1)
    after=processes()
    for target in sorted(children|{pid},reverse=True):
        if target in after and target in table and after[target]['command']==table[target]['command']:
            try:os.kill(target,signal.SIGKILL)
            except ProcessLookupError:pass
    event.update(state='stopped_by_user_budget',stop_finished_utc=datetime.now(timezone.utc).isoformat())
    write(study/'budget-enforcement.json',event)
    report(study,repo)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--mode',choices=['enforce','report'],required=True);p.add_argument('--runner-pid',type=int)
    p.add_argument('--stop-epoch',type=float);p.add_argument('--deadline-epoch',type=float);a=p.parse_args()
    s=a.study.resolve();r=a.repo.resolve()
    if a.mode=='report':report(s,r)
    else:
        assert a.runner_pid and a.stop_epoch and a.deadline_epoch and a.stop_epoch<a.deadline_epoch
        enforce(s,r,a.runner_pid,a.stop_epoch,a.deadline_epoch)

if __name__=='__main__':main()
