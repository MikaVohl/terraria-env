"""Run an explicit diagnostic job list sequentially on the dedicated worker."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

# Infrastructure failures (startup, or a display that cannot show the whole game window) are not agent
# outcomes. Keep the evidence and retry the job once; any partial spend stays in the ledger.
INFRA_STOPS=('RuntimeError: startup_timeout','RuntimeError: heartbeat_timeout',
             'RuntimeError: display_too_small','RuntimeError: game_window_off_display')
INFRA_RETRIES=1


def infra_failed(output):
    path=output/'result.json'
    return path.exists() and json.loads(path.read_text())['stop_reason'].startswith(INFRA_STOPS)


def archive(root,job_id):
    n=1+sum(1 for p in root.glob(job_id+'.infra-failed-*') if p.is_dir())
    dest=f'{job_id}.infra-failed-{n}'
    (root/job_id).rename(root/dest)
    if (root/(job_id+'.log')).exists():(root/(job_id+'.log')).rename(root/(dest+'.log'))
    return dest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan',type=Path)
    args=p.parse_args();plan=json.loads(args.plan.read_text())
    root=Path(plan['campaign']);root.mkdir(parents=True,exist_ok=True)
    (root/(args.plan.stem+'-frozen.json')).write_text(json.dumps(plan,indent=2)+'\n')
    summary=[];unavailable=set()
    for job in plan['jobs']:
        output=root/job['id']
        if infra_failed(output):archive(root,job['id'])  # never reached gameplay; no model call was made
        if (output/'result.json').exists():
            summary.append({'id':job['id'],'status':'already_recorded'});continue
        if job.get('model') in unavailable:
            summary.append({'id':job['id'],'status':'not_run_route_unavailable'});continue
        ledger=json.loads((root/'ledger.json').read_text())
        exposure=float(ledger['spent_usd'])+sum(float(v) for v in ledger['pending'].values())
        if exposure>=float(ledger['limit_usd'])-.01:break
        module='terrariabench.'+job.get('runner','experiments')
        cmd=[sys.executable,'-u','-m',module,'--campaign',str(root),
             '--fixture',job.get('fixture',plan['fixture']),'--output',str(output)]
        settings={k:v for k,v in job.items() if k not in ('id','fixture','runner')}
        for key,value in settings.items():
            cmd.append('--'+key.replace('_','-'))
            if not isinstance(value,bool):cmd.append(str(value))
        print(json.dumps({'starting':job['id'],'exposure_usd':exposure,'unix':time.time()}),flush=True)
        for attempt in range(1+INFRA_RETRIES):
            with (root/(job['id']+'.log')).open('w') as log:
                proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
            if attempt<INFRA_RETRIES and infra_failed(output):
                print(json.dumps({'infra_failure':job['id'],'archived_as':archive(root,job['id']),'retrying':True}),flush=True)
                continue
            break
        if (output/'result.json').exists():
            result=json.loads((output/'result.json').read_text())
            score=result['metrics']['public_subset_score']
            calls=result['calls'] if 'calls' in result else {k:r['calls'] for k,r in result['roles'].items()}
            cost=result['accounting']['reported_usd'] if 'accounting' in result else {k:r['accounting']['reported_usd'] for k,r in result['roles'].items()}
            item={'id':job['id'],'exit_code':proc.returncode,'stop':result['stop_reason'],
                  'calls':calls,'cost':cost,
                  'milestones':score['milestones'],'target_killed':result['metrics']['target_killed'],
                  'player_damage':result['metrics']['player_damage_to_target']}
            if any(x in result['stop_reason'] for x in ['HTTP 400','HTTP 404','returned_model_mismatch']):unavailable.add(job.get('model'))
        else:item={'id':job['id'],'exit_code':proc.returncode,'status':'missing_result'}
        summary.append(item)
        (root/(args.plan.stem+'-progress.json')).write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(item),flush=True)
    print(json.dumps({'finished_plan':args.plan.stem,'jobs_recorded':len(summary)}),flush=True)

if __name__=='__main__':main()
