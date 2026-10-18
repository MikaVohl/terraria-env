"""Explicit concurrency-only handoff: adopt live trials, start the last once.

Never edits/restarts frozen gameplay, learners, supervisor or existing trials.
The original dispatcher is stopped (not its workers) to prevent duplicate launch.
A fresh, hashed coordinator owns completion/diagnostics via original functions.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def identity(pid):
    r=subprocess.run(['ps','-p',str(pid),'-o','lstart=,stat=,command='],capture_output=True,text=True)
    if r.returncode:return None
    words=r.stdout.strip().split(maxsplit=6)
    return {'start':' '.join(words[:5]),'stat':words[5],'command':words[6] if len(words)>6 else ''}


def load(study):
    spec=importlib.util.spec_from_file_location('original_frozen_supervisor',study/'supervisor.py')
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    return original


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--amendment',type=Path,required=True)
    parser.add_argument('--mode',choices=['plan','run'],default='plan')
    args=parser.parse_args();study=args.study.resolve();amend=args.amendment.resolve()
    old=load(study);protocol=old.read(study/'study-protocol.json');old.verify_sources(study,protocol)
    prior=old.read(study/'status.json');launch=old.read(study/'launch.json')
    parent=launch['pid'];parent_id=identity(parent)
    assert parent==prior['runner_pid']==99218 and parent_id
    assert str(study/'supervisor.py') in parent_id['command'] and '--mode run' in parent_id['command']
    assert prior['stage']=='training' and len(prior['active'])==3
    assert prior['pending']==[['v7-difficulty-g999',805]]
    assert not (study/'runs/v7-difficulty-g999-805').exists()
    if args.mode=='plan':
        print(json.dumps({'old_dispatcher':parent,'adopt_unchanged_workers':prior['active'],
                          'launch_once':old.command(study,'v7-difficulty-g999',805),'new_max_workers':4,'api_calls':0},indent=2));return
    assert amend.is_dir() and not (amend/'started.json').exists()
    old.write(amend/'started.json',{'pid':os.getpid(),'started_utc':time.time(),'original_pid':parent,
                                  'coordinator_sha256':old.sha(Path(__file__)),'original_protocol_sha256':old.sha(study/'study-protocol.json')},exclusive=True)
    stopped=False;launched=False;success=False;active={};owned={};logs={};identities={};completed=list(prior['completed'])
    inhibitor=subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())])
    def status(stage,**extra):
        value={'stage':stage,'runner_pid':os.getpid(),'original_supervisor_pid':parent,'concurrency_amendment':str(amend),
               'updated_utc':time.time(),'active':dict(active),'completed':completed,'pending':[],**extra}
        old.write(amend/'status.json',value)
        temp=study/'status.parallel.tmp';old.write(temp,value);temp.replace(study/'status.json')
    def stop_exact(pid):
        current=identity(pid)
        if current and current['start']==identities[pid]['start'] and 'Z' not in current['stat']:
            os.kill(pid,signal.SIGTERM)
    try:
        # SIGSTOP is sent only to the validated dispatcher PID, never a group.
        os.kill(parent,signal.SIGSTOP);stopped=True
        for _ in range(20):
            if 'T' in identity(parent)['stat']:break
            time.sleep(.05)
        assert 'T' in identity(parent)['stat']
        stable=old.read(study/'status.json')
        assert stable['active']==prior['active'] and stable['pending']==prior['pending']
        for name,pid in prior['active'].items():
            current=identity(pid)
            assert current and str(study/'runs'/name) in current['command'] and 'iterate_ppo.py' in current['command']
            identities[pid]=current;active[name]=pid
        old.write(amend/'status-before.json',stable,exclusive=True)
        old.write(amend/'amendment.json',{
            'user_authorization':'can you run the queued one in parallel?',
            'change':'Allow four overlapping existing-protocol main trials for the final queued run only.',
            'original_supervisor_pid':parent,'original_supervisor_identity':parent_id,
            'original_supervisor_sha256':old.sha(study/'supervisor.py'),
            'original_protocol_sha256':old.sha(study/'study-protocol.json'),
            'coordinator_sha256':old.sha(Path(__file__)),
            'adopted_worker_identities':identities,'adopted_workers':dict(active),
            'original_workers':3,'temporary_max_workers':4,
            'unchanged':'Gameplay,learner bytes,all25 trials,seeds,rewards,16M LR schedules,checkpoints,validation,tests,diagnostic/report implementations.',
            'timing_caveat':'Final overlap uses four workers instead of three; report contention, not a speed/learning causal estimate.'},exclusive=True)
        name='v7-difficulty-g999-805';dest=study/'runs'/name
        assert not dest.exists()
        old.verify_sources(study,protocol)
        logs[name]=(study/'logs'/(name+'.log')).open('x')
        proc=subprocess.Popen(old.command(study,'v7-difficulty-g999',805),cwd=study/'variants/v7',env=old.environment(study,'v7'),stdout=logs[name],stderr=subprocess.STDOUT)
        launched=True;owned[name]=proc;active[name]=proc.pid;identities[proc.pid]=identity(proc.pid)
        old.write(amend/'last-trial-launch.json',{'name':name,'pid':proc.pid,'identity':identities[proc.pid],
                                                'command':old.command(study,'v7-difficulty-g999',805),'launched_utc':time.time()},exclusive=True)
        old.write(study/'parallel-amendment.json',{'amendment_root':str(amend),'coordinator_pid':os.getpid(),
                                                'original_supervisor_pid':parent,'original_dispatcher_suspended':True,
                                                'last_trial_pid':proc.pid,'protocol_sha256':old.sha(study/'study-protocol.json')},exclusive=True)
        print('Four trials running; adopted workers untouched; last trial started once',dict(active),flush=True)
        while active:
            for name,pid in list(active.items()):
                current=identity(pid)
                if current and current['start']!=identities[pid]['start']:raise RuntimeError('PID identity changed')
                if name in owned:
                    code=owned[name].poll()
                    if code is None:continue
                    if code:raise RuntimeError(f'New trial failed rc={code}')
                elif current and 'Z' not in current['stat']:
                    continue
                d=study/'runs'/name
                assert old.read(d/'summary.json')['steps']==protocol['steps_per_run']
                assert [r['steps'] for r in old.read(d/'curve.json')]==protocol['checkpoint_steps']
                assert all((d/f'step-{step}.pt').exists() for step in protocol['checkpoint_steps'])
                assert 'Completed '+name+':' in (study/'logs'/(name+'.log')).read_text()
                completed.append(name);del active[name]
                if name in logs:logs[name].close()
                print('Completed unchanged trial',name,flush=True)
            status('training')
            if active:time.sleep(3)
        assert len(completed)==25 and len(set(completed))==25
        old.verify_sources(study,protocol)
        # Identical original diagnostic commands/order and unchanged report code.
        for cell,seed in protocol['jobs']:
            version=old.CELLS[cell]['version'];name=f'{cell}-{seed}';dest=study/'runs'/name
            assert not (dest/'crafting.json').exists()
            command=[sys.executable,str(study/'variants'/version/'tools/crafting_diagnostics.py'),str(dest/f"step-{protocol['steps_per_run']}.pt"),'--probe',str(study/f'probe-{version}.dylib'),'--out',str(dest/'crafting.json'),'--episodes','128','--seed-start','17000001']
            with (study/'logs'/('crafting-'+name+'.log')).open('x') as log:
                proc=subprocess.Popen(command,cwd=study/'variants'/version,env=old.environment(study,version),stdout=log,stderr=subprocess.STDOUT)
                active['crafting-'+name]=proc.pid;identities[proc.pid]=identity(proc.pid)
                owned['crafting-'+name]=proc;status('diagnostics',latest_diagnostic=name)
                code=proc.wait();del active['crafting-'+name]
                if code:raise RuntimeError(f'Diagnostic failed: {name},rc={code}')
        status('reporting');old.verify_sources(study,protocol)
        report=old.report(study,protocol)
        status('complete',report=report);success=True
        print('Complete',report,flush=True)
    except BaseException as error:
        if launched:
            for pid in active.values():stop_exact(pid)
            status('failed',error_type=type(error).__name__,error=str(error))
        else:
            # No trial was launched: returning control cannot duplicate work.
            if stopped:os.kill(parent,signal.SIGCONT);stopped=False
        raise
    finally:
        if stopped:
            # All training ended, or validated live workers were terminated on
            # failure. Remove the suspended dispatcher; do not let it relaunch.
            for sig in (signal.SIGTERM,signal.SIGCONT):
                try:os.kill(parent,sig)
                except ProcessLookupError:pass
        if inhibitor.poll() is None:inhibitor.terminate();inhibitor.wait()
        for log in logs.values():
            if not log.closed:log.close()
        if success:old.write(amend/'completed.json',{'completed_utc':time.time(),'all25_main_runs_complete':True},exclusive=True)


if __name__=='__main__':main()
