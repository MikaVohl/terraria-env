"""Run an explicit diagnostic job list sequentially on the dedicated worker."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan',type=Path)
    args=p.parse_args();plan=json.loads(args.plan.read_text())
    root=Path(plan['campaign']);root.mkdir(parents=True,exist_ok=True)
    (root/(args.plan.stem+'-frozen.json')).write_text(json.dumps(plan,indent=2)+'\n')
    summary=[];unavailable=set()
    for job in plan['jobs']:
        output=root/job['id']
        if (output/'result.json').exists():
            summary.append({'id':job['id'],'status':'already_recorded'});continue
        if job['model'] in unavailable:
            summary.append({'id':job['id'],'status':'not_run_route_unavailable'});continue
        ledger=json.loads((root/'ledger.json').read_text())
        exposure=float(ledger['spent_usd'])+sum(float(v) for v in ledger['pending'].values())
        if exposure>=float(ledger['limit_usd'])-.01:break
        cmd=[sys.executable,'-u','-m','terrariabench.experiments','--campaign',str(root),
             '--fixture',plan['fixture'],'--output',str(output)]
        settings={k:v for k,v in job.items() if k!='id'}
        for key,value in settings.items():
            cmd.append('--'+key.replace('_','-'))
            if not isinstance(value,bool):cmd.append(str(value))
        print(json.dumps({'starting':job['id'],'exposure_usd':exposure,'unix':time.time()}),flush=True)
        with (root/(job['id']+'.log')).open('w') as log:
            proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
        if (output/'result.json').exists():
            result=json.loads((output/'result.json').read_text())
            score=result['metrics']['public_subset_score']
            item={'id':job['id'],'exit_code':proc.returncode,'stop':result['stop_reason'],
                  'calls':result['calls'],'cost':result['accounting']['reported_usd'],
                  'milestones':score['milestones'],'target_killed':result['metrics']['target_killed'],
                  'player_damage':result['metrics']['player_damage_to_target']}
            if any(x in result['stop_reason'] for x in ['HTTP 400','HTTP 404','returned_model_mismatch']):unavailable.add(job['model'])
        else:item={'id':job['id'],'exit_code':proc.returncode,'status':'missing_result'}
        summary.append(item)
        (root/(args.plan.stem+'-progress.json')).write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(item),flush=True)
    print(json.dumps({'finished_plan':args.plan.stem,'jobs_recorded':len(summary)}),flush=True)

if __name__=='__main__':main()
