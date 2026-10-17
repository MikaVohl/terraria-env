"""Claim and consume one frozen policy's declared test split exactly once."""
import argparse
import hashlib
import json
from pathlib import Path
import torch
from terraria_lite import SPEC
from terraria_lite.ppo_eval import load_agent,evaluate

def main():
    p=argparse.ArgumentParser();p.add_argument('checkpoint',type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--seed-start',type=int,required=True)
    p.add_argument('--version',type=int,required=True);a=p.parse_args()
    assert SPEC.version==a.version
    claim=a.out.with_suffix('.claim.json')
    if a.out.exists():raise ValueError('Consumed test output exists')
    request={'checkpoint_sha256':hashlib.sha256(a.checkpoint.read_bytes()).hexdigest(),
             'environment_version':SPEC.version,'seeds':[a.seed_start,a.seed_start+127],'sampler_seed':54321}
    # A crash after this point preserves an ambiguous/consumed claim. Never retry.
    with claim.open('x') as h:json.dump(request,h,indent=2)
    torch.set_num_threads(6)
    result=evaluate(load_agent(a.checkpoint),list(range(a.seed_start,a.seed_start+128)),sample_seed=54321)
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({**request,'mean_achievements':result['mean_achievements'],'death_rate':result['death_rate']}))

if __name__=='__main__':main()
